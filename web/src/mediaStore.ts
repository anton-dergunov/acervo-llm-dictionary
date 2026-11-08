/**
 * Where the pictures this device has seen actually live.
 *
 * A **third** IndexedDB database, beside the replica and the dictionaries, for the reason each of
 * those is separate from the other: a picture is bulk, it is replaceable from the server, and it is
 * not the owner's vocabulary. Wiping a replica that belongs to another account must not throw away
 * a hundred megabytes of pictures that are still perfectly good, and clearing the pictures must not
 * go near `localDatabase.ts`.
 *
 * **One record per file, never one per record field.** The same rule `dictionaryStore.ts` states,
 * and here it is the difference between storing WebP bytes as WebP bytes and paying per-record
 * overhead on every one of a few thousand pictures.
 *
 * Keyed by the reference the record itself carries — `imageRef`, `audioRef` — rather than by a
 * record id, because a reference is what a component has in its hand and what the media route wants.
 * **Both carry a digest of the bytes**, so a redrawn picture and a re-recorded clip each get a new
 * reference and the old key is simply never asked for again. Neither needs an invalidation of its
 * own, which is what lets this be a plain cache with no eviction: a key here names immutable bytes.
 *
 * A picture used to be the exception — overwritten in place, on the theory that the key was stable
 * and the newest bytes won. They did not: the device went on serving what it had already
 * downloaded, and the invalidation bolted on beside it lost a race it could not win.
 *
 * **One object store per kind of media**, so pronunciations can be switched off and forgotten on a
 * device without touching a single picture, and the other way round — and so that loops, which are
 * megabytes each where a clip is kilobytes, can be switched off on their own. Music heard on its
 * own — a kept bed's, a style's sample — is a fourth, so it is kept while loops are not.
 */

const DATABASE_NAME = "acervo-media";
const DATABASE_VERSION = 4;
export const MEDIA_KINDS = ["pictures", "pronunciations", "loops", "music"] as const;
export type MediaKind = typeof MEDIA_KINDS[number];

export interface StoredMedia {
  /** The reference the record carries, relative to the server's media directory. */
  reference: string;
  blob: Blob;
  fetchedAt: string;
}

export interface MediaStore {
  read(reference: string): Promise<StoredMedia | null>;
  save(reference: string, blob: Blob): Promise<void>;
  remove(reference: string): Promise<void>;
  clear(): Promise<void>;
  bytes(): Promise<number>;
}

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

let opened: Promise<IDBDatabase> | null = null;

/** One connection for both stores, so opening pictures and pronunciations cannot race an upgrade. */
function openDatabase(): Promise<IDBDatabase> {
  if (opened) return opened;
  opened = new Promise((resolve, reject) => {
    const opening = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    opening.onupgradeneeded = () => {
      const database = opening.result;
      MEDIA_KINDS.forEach((store) => {
        if (!database.objectStoreNames.contains(store)) database.createObjectStore(store, { keyPath: "reference" });
      });
    };
    opening.onsuccess = () => resolve(opening.result);
    opening.onerror = () => { opened = null; reject(opening.error); };
  });
  return opened;
}

class IndexedMediaStore implements MediaStore {
  constructor(private readonly store: MediaKind) {}

  private open(): Promise<IDBDatabase> {
    return openDatabase();
  }

  async read(reference: string): Promise<StoredMedia | null> {
    const database = await this.open();
    const record = await request(
      database.transaction(this.store, "readonly").objectStore(this.store).get(reference)
    );
    return (record as StoredMedia | undefined) ?? null;
  }

  async save(reference: string, blob: Blob): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(this.store, "readwrite");
    transaction.objectStore(this.store).put({ reference, blob, fetchedAt: new Date().toISOString() });
    return settled(transaction);
  }

  async remove(reference: string): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(this.store, "readwrite");
    transaction.objectStore(this.store).delete(reference);
    return settled(transaction);
  }

  async clear(): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(this.store, "readwrite");
    transaction.objectStore(this.store).clear();
    return settled(transaction);
  }

  async bytes(): Promise<number> {
    const database = await this.open();
    const records = await request(
      database.transaction(this.store, "readonly").objectStore(this.store).getAll()
    );
    return (records as StoredMedia[]).reduce((total, record) => total + record.blob.size, 0);
  }
}

/** Used where IndexedDB is unavailable, so a picture degrades to one fetch per view, not to none. */
export class MemoryMediaStore implements MediaStore {
  private records = new Map<string, StoredMedia>();

  async read(reference: string) { return this.records.get(reference) ?? null; }
  async save(reference: string, blob: Blob) {
    this.records.set(reference, { reference, blob, fetchedAt: new Date().toISOString() });
  }
  async remove(reference: string) { this.records.delete(reference); }
  async clear() { this.records.clear(); }
  async bytes() {
    return [...this.records.values()].reduce((total, record) => total + record.blob.size, 0);
  }
}

export function createMediaStore(kind: MediaKind): MediaStore {
  return typeof indexedDB === "undefined" ? new MemoryMediaStore() : new IndexedMediaStore(kind);
}
