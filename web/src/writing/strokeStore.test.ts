import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StrokeAnswer } from "../api";
import { BATCH, createShelf, STROKE_DATASET, StrokeStore } from "./strokeStore";
import { FIXTURES } from "./testStrokes";

function server(dataset = STROKE_DATASET) {
  return vi.fn(async (characters: string): Promise<StrokeAnswer> => {
    const asked = Array.from(characters);
    return {
      dataset,
      characters: Object.fromEntries(asked.filter((one) => one in FIXTURES).map((one) => [one, FIXTURES[one]])),
      missing: asked.filter((one) => !(one in FIXTURES))
    };
  });
}

describe("stroke data on the device", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: new IDBFactory() });
  });
  afterEach(() => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: undefined });
  });

  it("fetches what it does not hold, and answers from the device after that", async () => {
    const fetcher = server();
    const store = new StrokeStore(createShelf(), fetcher);
    const first = await store.strokesOf(["人", "口"]);
    expect(first.found.get("人")).toEqual(FIXTURES["人"]);
    expect(fetcher).toHaveBeenCalledWith("人口");

    const again = new StrokeStore(createShelf(), fetcher);
    const second = await again.strokesOf(["人", "口", "水"]);
    expect(fetcher).toHaveBeenLastCalledWith("水");
    expect([...second.found.keys()].sort()).toEqual(["人", "口", "水"].sort());
  });

  it("remembers a character the dataset lacks, so it is not asked for again", async () => {
    const fetcher = server();
    const store = new StrokeStore(createShelf(), fetcher);
    expect((await store.strokesOf(["𠮷"])).found.get("𠮷")).toBeNull();
    await store.strokesOf(["𠮷"]);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("asks in batches the server accepts", async () => {
    const fetcher = server();
    const store = new StrokeStore(createShelf(), fetcher);
    const many = Array.from({ length: BATCH + 5 }, (_, index) => String.fromCodePoint(0x4E00 + index));
    await store.strokesOf(many);
    expect(fetcher.mock.calls.map(([asked]) => Array.from(asked).length)).toEqual([BATCH, 5]);
  });

  it("names what it could not get when the server cannot be reached, and answers the rest", async () => {
    await new StrokeStore(createShelf(), server()).strokesOf(["人"]);
    const offline = new StrokeStore(createShelf(), vi.fn(async () => { throw new Error("offline"); }));
    const answer = await offline.strokesOf(["人", "口"]);
    expect(answer.found.get("人")).toEqual(FIXTURES["人"]);
    expect(answer.unreachable).toEqual(["口"]);
  });

  it("forgets what an earlier dataset left behind", async () => {
    const opening = indexedDB.open("acervo-strokes", 1);
    await new Promise<void>((resolve) => {
      opening.onupgradeneeded = () => opening.result.createObjectStore("characters", { keyPath: "key" });
      opening.onsuccess = () => {
        const transaction = opening.result.transaction("characters", "readwrite");
        transaction.objectStore("characters").put({ key: "old@1/人", dataset: "old@1", character: "人", strokes: null });
        transaction.oncomplete = () => { opening.result.close(); resolve(); };
      };
    });
    const fetcher = server();
    await new StrokeStore(createShelf(), fetcher).strokesOf(["人"]);
    const reading = indexedDB.open("acervo-strokes", 1);
    const keys = await new Promise<IDBValidKey[]>((resolve) => {
      reading.onsuccess = () => {
        const all = reading.result.transaction("characters").objectStore("characters").getAllKeys();
        all.onsuccess = () => resolve(all.result);
      };
    });
    expect(keys).toEqual([`${STROKE_DATASET}/人`]);
  });

  it("refuses a server answering with another dataset", async () => {
    const store = new StrokeStore(createShelf(), server("hanzi-writer-data@9.0.0"));
    await expect(store.strokesOf(["人"])).rejects.toThrow(/Reload/);
  });

  it("keeps only the Han characters of the words it is given", async () => {
    const fetcher = server();
    await new StrokeStore(createShelf(), fetcher).keep(["妈妈", "水 (water)", "OK"]);
    expect(fetcher).toHaveBeenCalledWith("妈水");
  });
});
