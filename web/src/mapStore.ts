/* The last meaning map this device was given, per account and vocabulary.

   Its own IndexedDB database, like `dictionaryStore.ts`, so wiping the replica leaves it alone and
   wiping it leaves the replica alone. It is what makes the map open at once and offline: the map drawn
   last time is on screen before the server has been asked whether it is still current. Keyed by the
   account as well as the vocabulary, so a device signed into another account never draws the first
   account's map, even for the moment before the server answers. A map is of one vocabulary, so it
   is kept under that vocabulary's id. */

import type { ServerMap } from "./api";

const DATABASE_NAME = "acervo-maps";
const DATABASE_VERSION = 1;
const STORE = "maps";

export interface MapStore {
  read(owner: string, vocabularyId: string): Promise<ServerMap | null>;
  save(owner: string, vocabularyId: string, map: ServerMap): Promise<void>;
  clear(): Promise<void>;
}

const keyOf = (owner: string, vocabularyId: string) => `${owner}\u001f${vocabularyId}`;

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

class IndexedMapStore implements MapStore {
  private handle: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (this.handle) return this.handle;
    this.handle = new Promise((resolve, reject) => {
      const opening = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      opening.onupgradeneeded = () => {
        const database = opening.result;
        if (!database.objectStoreNames.contains(STORE)) database.createObjectStore(STORE, { keyPath: "key" });
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => reject(opening.error);
    });
    return this.handle;
  }

  async read(owner: string, vocabularyId: string): Promise<ServerMap | null> {
    const database = await this.open();
    const record = await request(database.transaction(STORE, "readonly").objectStore(STORE).get(keyOf(owner, vocabularyId)));
    return (record as { map: ServerMap } | undefined)?.map ?? null;
  }

  async save(owner: string, vocabularyId: string, map: ServerMap): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).put({ key: keyOf(owner, vocabularyId), map, savedAt: new Date().toISOString() });
    return settled(transaction);
  }

  async clear(): Promise<void> {
    const database = await this.open();
    const transaction = database.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).clear();
    return settled(transaction);
  }
}

/* Where IndexedDB is unavailable the map still works; it is simply asked for each time. */
export class MemoryMapStore implements MapStore {
  private maps = new Map<string, ServerMap>();
  async read(owner: string, vocabularyId: string) { return this.maps.get(keyOf(owner, vocabularyId)) ?? null; }
  async save(owner: string, vocabularyId: string, map: ServerMap) { this.maps.set(keyOf(owner, vocabularyId), map); }
  async clear() { this.maps.clear(); }
}

export const createMapStore = (): MapStore => {
  try {
    return typeof indexedDB !== "undefined" ? new IndexedMapStore() : new MemoryMapStore();
  } catch {
    return new MemoryMapStore();
  }
};
