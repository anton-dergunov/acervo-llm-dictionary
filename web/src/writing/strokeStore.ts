/**
 * How characters are written, kept on this device so the Write sheet works offline.
 *
 * Reference data, not the vocabulary: the same for every owner, read from the server's pinned
 * dataset (`deploy/acervo/strokes/pin.json`) and never replicated. So it is its own IndexedDB
 * database, beside the replica, the dictionaries and the media, for the reason each of those is
 * separate from the others — clearing one must not go near the rest.
 *
 * **A record names immutable data.** Each is keyed by the dataset and the character, so it needs no
 * invalidation: a new pin is a new dataset name, and what the old one left behind is deleted on open.
 * A character the dataset lacks is kept too, as a record with no strokes, so a prefetch does not ask
 * the server for it again after every pull.
 *
 * One record per character, not one file for the dataset: the owner's vocabulary uses a few hundred
 * characters of the ten thousand, which is about a megabyte, and that is what a device holds.
 */

import { backendSession, type StrokeAnswer } from "../api";
import { hanCharacters, type CharacterStrokes } from "./strokeData";

/** The dataset this interface draws with. Held equal to the pin by `tests/unit/server/test_strokes.py`. */
export const STROKE_DATASET = "hanzi-writer-data@2.0.1";
/** What one request asks for: the server's bound. */
export const BATCH = 200;

const DATABASE_NAME = "acervo-strokes";
const DATABASE_VERSION = 1;
const STORE = "characters";

interface Stored {
  key: string;
  dataset: string;
  character: string;
  /** Null for a character the dataset does not have. */
  strokes: CharacterStrokes | null;
}

export interface StrokeShelf {
  read(characters: string[]): Promise<Map<string, CharacterStrokes | null>>;
  save(records: Map<string, CharacterStrokes | null>): Promise<void>;
}

const keyOf = (character: string) => `${STROKE_DATASET}/${character}`;

function request<T>(value: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    value.onsuccess = () => resolve(value.result);
    value.onerror = () => reject(value.error);
  });
}

function settled(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

class IndexedShelf implements StrokeShelf {
  private opened: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (this.opened) return this.opened;
    this.opened = new Promise<IDBDatabase>((resolve, reject) => {
      const opening = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      opening.onupgradeneeded = () => {
        if (!opening.result.objectStoreNames.contains(STORE)) opening.result.createObjectStore(STORE, { keyPath: "key" });
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => { this.opened = null; reject(opening.error); };
    }).then(async (database) => {
      await this.forgetOtherDatasets(database);
      return database;
    });
    return this.opened;
  }

  /** What an earlier pin left behind. A few hundred records at most, so a walk is cheap. */
  private async forgetOtherDatasets(database: IDBDatabase): Promise<void> {
    const transaction = database.transaction(STORE, "readwrite");
    const cursor = transaction.objectStore(STORE).openCursor();
    cursor.onsuccess = () => {
      const at = cursor.result;
      if (!at) return;
      if ((at.value as Stored).dataset !== STROKE_DATASET) at.delete();
      at.continue();
    };
    await settled(transaction);
  }

  async read(characters: string[]): Promise<Map<string, CharacterStrokes | null>> {
    const database = await this.open();
    const store = database.transaction(STORE, "readonly").objectStore(STORE);
    const found = new Map<string, CharacterStrokes | null>();
    await Promise.all(characters.map(async (character) => {
      const record = await request(store.get(keyOf(character))) as Stored | undefined;
      if (record) found.set(character, record.strokes);
    }));
    return found;
  }

  async save(records: Map<string, CharacterStrokes | null>): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    const store = transaction.objectStore(STORE);
    for (const [character, strokes] of records) {
      store.put({ key: keyOf(character), dataset: STROKE_DATASET, character, strokes } satisfies Stored);
    }
    await settled(transaction);
  }
}

/** Where there is no IndexedDB — a test, a private window that refuses it. */
class MemoryShelf implements StrokeShelf {
  private records = new Map<string, CharacterStrokes | null>();
  async read(characters: string[]) {
    return new Map(characters.filter((one) => this.records.has(one)).map((one) => [one, this.records.get(one) ?? null] as const));
  }
  async save(records: Map<string, CharacterStrokes | null>) {
    for (const [character, strokes] of records) this.records.set(character, strokes);
  }
}

export function createShelf(): StrokeShelf {
  return typeof indexedDB !== "undefined" ? new IndexedShelf() : new MemoryShelf();
}

export type Fetcher = (characters: string) => Promise<StrokeAnswer>;

export interface Strokes {
  /** Each character's strokes; null for one the dataset does not have. */
  found: Map<string, CharacterStrokes | null>;
  /** Characters neither on this device nor fetched, because the server could not be asked. */
  unreachable: string[];
}

export class StrokeStore {
  constructor(private shelf: StrokeShelf = createShelf(), private fetcher: Fetcher = (characters) => backendSession.strokes(characters)) {}

  /**
   * The strokes of these characters, from this device where it has them and from the server for the
   * rest. A server that cannot be reached is not an error here: what was on the device is answered,
   * and the rest are named as unreachable, which the sheet says in one line.
   */
  async strokesOf(characters: string[]): Promise<Strokes> {
    const wanted = [...new Set(characters)];
    const found = await this.shelf.read(wanted).catch(() => new Map<string, CharacterStrokes | null>());
    const missing = wanted.filter((one) => !found.has(one));
    const unreachable: string[] = [];
    for (let start = 0; start < missing.length; start += BATCH) {
      const batch = missing.slice(start, start + BATCH);
      let answer: StrokeAnswer;
      try {
        answer = await this.fetcher(batch.join(""));
      } catch {
        unreachable.push(...missing.slice(start));
        break;
      }
      if (answer.dataset !== STROKE_DATASET) {
        // The server and this interface ship together, so this is a page older than its server.
        throw new Error(`The server's stroke data is ${answer.dataset}; this page expects ${STROKE_DATASET}. Reload to update it.`);
      }
      const fetched = new Map<string, CharacterStrokes | null>();
      for (const character of batch) fetched.set(character, answer.characters[character] ?? null);
      await this.shelf.save(fetched).catch(() => undefined);
      for (const [character, strokes] of fetched) found.set(character, strokes);
    }
    return { found, unreachable };
  }

  /** Every Han character in these words, fetched once onto this device. Quiet: it is opportunistic. */
  async keep(words: string[]): Promise<void> {
    const characters = [...new Set(words.flatMap(hanCharacters))];
    if (!characters.length) return;
    try { await this.strokesOf(characters); } catch { /* the next pull tries again */ }
  }
}

let shared: StrokeStore | null = null;
export function strokeStore(): StrokeStore {
  shared ??= new StrokeStore();
  return shared;
}
