import type { VocabularyGraph } from "./domain";

const DATABASE_NAME = "acervo";
const DATABASE_VERSION = 10;
export const RECORD_STORES = ["vocabularies", "topics", "lexemes", "senses", "attestations", "examples", "imagePrompts", "pronunciations", "studyStates", "loops", "loopItems", "loopCues", "stories", "storyParts", "storyWords", "beds"] as const;
const STORES = [...RECORD_STORES, "meta"] as const;
/** Stores from superseded schemas. Opening the database drops them rather than reading around them. */
const RETIRED_STORES = ["pending"] as const;
export type RecordStore = typeof RECORD_STORES[number];

export interface ReplicaMeta {
  ownerId: string;
  deviceId: string;
  schemaVersion: number;
  /** Which server database the cursor counts within. A change means it was rebuilt or restored. */
  datasetId: string;
  /** The highest revision this replica has received. */
  cursor: number;
  lastPulledAt: string | null;
  lastWroteAt: string | null;
}

export interface DatabaseContents extends VocabularyGraph {
  meta: Partial<ReplicaMeta>;
}

/**
 * One atomic unit of work. Applied records, the tombstones that came with them and the cursor that
 * covers them must move together: a crash between two writes would leave a cursor claiming records
 * the replica does not hold, and nothing would ever fetch them again.
 */
export interface DatabaseWrite extends Partial<VocabularyGraph> {
  meta?: Partial<ReplicaMeta>;
}

export interface LocalDatabase {
  read(): Promise<DatabaseContents>;
  write(changes: DatabaseWrite): Promise<void>;
  wipe(): Promise<void>;
}

function request<T>(value: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    value.onsuccess = () => resolve(value.result);
    value.onerror = () => reject(value.error);
  });
}

class IndexedDatabase implements LocalDatabase {
  private handle: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (this.handle) return this.handle;
    this.handle = new Promise((resolve, reject) => {
      const opening = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      opening.onupgradeneeded = () => {
        const database = opening.result;
        STORES.forEach((store) => {
          if (!database.objectStoreNames.contains(store)) database.createObjectStore(store);
        });
        RETIRED_STORES.forEach((store) => {
          if (database.objectStoreNames.contains(store)) database.deleteObjectStore(store);
        });
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => reject(opening.error);
    });
    return this.handle;
  }

  async read(): Promise<DatabaseContents> {
    const database = await this.open();
    const transaction = database.transaction(STORES, "readonly");
    const records = await Promise.all(RECORD_STORES.map((store) => request(transaction.objectStore(store).getAll())));
    const [metaKeys, metaValues] = await Promise.all([
      request(transaction.objectStore("meta").getAllKeys()),
      request(transaction.objectStore("meta").getAll())
    ]);
    const meta: Record<string, unknown> = {};
    metaKeys.forEach((key, index) => { meta[String(key)] = metaValues[index]; });
    // Assembled by name rather than by position: reading `records[4]` as the examples is correct
    // only until a store is added, and then it is wrong everywhere at once and silently.
    const contents = EMPTY_CONTENTS();
    RECORD_STORES.forEach((store, index) => { contents[store] = records[index] as never; });
    return { ...contents, meta: meta as Partial<ReplicaMeta> };
  }

  async write(changes: DatabaseWrite): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORES, "readwrite");
    RECORD_STORES.forEach((store) => {
      changes[store]?.forEach((record) => transaction.objectStore(store).put(record, record.id));
    });
    Object.entries(changes.meta ?? {}).forEach(([key, value]) => transaction.objectStore("meta").put(value, key));
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  async wipe(): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORES, "readwrite");
    STORES.forEach((store) => transaction.objectStore(store).clear());
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }
}

const EMPTY_CONTENTS = (): DatabaseContents => ({
  vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [],
  imagePrompts: [], pronunciations: [], studyStates: [], loops: [], loopItems: [], loopCues: [], stories: [], storyParts: [], storyWords: [], beds: [], meta: {}
});

export class MemoryDatabase implements LocalDatabase {
  private contents: DatabaseContents = EMPTY_CONTENTS();

  async read(): Promise<DatabaseContents> {
    return structuredClone(this.contents);
  }

  async write(changes: DatabaseWrite): Promise<void> {
    const next = EMPTY_CONTENTS();
    RECORD_STORES.forEach((store) => {
      const result = [...this.contents[store]] as { id: string }[];
      (changes[store] as { id: string }[] | undefined)?.forEach((update) => {
        const index = result.findIndex((record) => record.id === update.id);
        if (index < 0) result.push(update); else result[index] = update;
      });
      next[store] = structuredClone(result) as never;
    });
    next.meta = { ...this.contents.meta, ...changes.meta };
    this.contents = next;
  }

  async wipe(): Promise<void> {
    this.contents = EMPTY_CONTENTS();
  }
}

function indexedDatabaseAvailable(): boolean {
  try { return typeof indexedDB !== "undefined"; } catch { return false; }
}

export const createLocalDatabase = (): LocalDatabase => indexedDatabaseAvailable() ? new IndexedDatabase() : new MemoryDatabase();
