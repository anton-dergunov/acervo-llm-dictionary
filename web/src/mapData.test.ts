import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";
import type { ServerMap } from "./api";
import { createMapStore, MemoryMapStore } from "./mapStore";
import { mapDataFor, mapPeekFor } from "./selectors";
import { testGraph } from "./testGraph";

/* The server's map for the test graph's Spanish: positions and ids only, as the server sends it. */
function serverMap(overrides: Partial<ServerMap> = {}): ServerMap {
  return {
    language: "es", fingerprint: "fp-1", version: "fp-1.none", model: "intfloat/multilingual-e5-small", side: 1000,
    words: 3, senses: 4, names: "none", regions: [], contours: [],
    points: [
      { sense: "sensepicaritch0", lexeme: "lexemepicar0001", x: 100, y: 100, r: -1, h: -1, rank: 1, nb: [2, 3] },
      { sense: "sensepicarchop0", lexeme: "lexemepicar0001", x: 800, y: 700, r: -1, h: -1, rank: 0.5, nb: [3] },
      { sense: "sensebalsaraft0", lexeme: "lexemebalsa0001", x: 300, y: 400, r: -1, h: -1, rank: 0.2, nb: [0, 3] },
      { sense: "senseespolvor10", lexeme: "lexemeespolv001", x: 700, y: 650, r: -1, h: -1, rank: 0.7, nb: [1] }
    ],
    ...overrides
  };
}

describe("the map joined to the replica", () => {
  it("labels each point from the replica, with the sense's emoji and first gloss", () => {
    const data = mapDataFor(testGraph(), serverMap(), "vocabes00000001");
    expect(data.points.map((p) => [p.headword, p.emoji, p.gloss])).toEqual([
      ["picar", "🌶️", "to itch"], ["picar", "🔪", "to chop"], ["la balsa", "🛶", "raft"], ["espolvorear", "🧀", "to sprinkle"]
    ]);
    expect(data.points[0].word).toBe(data.points[1].word);
  });

  it("drops a sense deleted since the map was drawn and re-indexes everyone's neighbours", () => {
    const graph = testGraph();
    graph.senses = graph.senses.map((s) => (s.id === "sensepicarchop0" ? { ...s, deleted: true } : s));
    const data = mapDataFor(graph, serverMap(), "vocabes00000001");
    expect(data.points.map((p) => p.id)).toEqual(["sensepicaritch0", "sensebalsaraft0", "senseespolvor10"]);
    // Point 0 was near [2, 3] — the raft and the sprinkling, now at 1 and 2.
    expect(data.points[0].near).toEqual([1, 2]);
    // The sprinkling was near only the deleted sense.
    expect(data.points[2].near).toEqual([]);
  });

  it("carries the server's regions and contours as they are", () => {
    const regions = [{ id: "r0", level: "region" as const, index: 0, x: 1, y: 2, count: 4,
                       labels: { words: ["picar"], terms: ["cortar"], name: "cocina" } }];
    const data = mapDataFor(testGraph(), serverMap({ regions, contours: [[0, [1, 2, 3, 4, 5, 6]]] }), "vocabes00000001");
    expect(data.regions).toBe(regions);
    expect(data.contours).toEqual([[0, [1, 2, 3, 4, 5, 6]]]);
  });
});

describe("the peek", () => {
  it("shows a sense with its word, every sense of the word and its picture", () => {
    const peek = mapPeekFor(testGraph(), "sensepicaritch0");
    expect(peek?.lexeme.headword).toBe("picar");
    expect(peek?.senses.map((s) => s.id)).toEqual(["sensepicaritch0", "sensepicarchop0"]);
    expect(peek?.terms).toEqual(["to itch"]);
    expect(peek?.glossLang).toBe("en");
    expect(peek?.picture?.id).toBe("imagepicar00010");
  });

  it("is nothing for a sense the replica does not hold", () => {
    expect(mapPeekFor(testGraph(), "sensenotheld000")).toBeNull();
  });
});

describe("the map store", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: new IDBFactory() });
  });

  it("keeps the last map per account and vocabulary, two of one language apart", async () => {
    const store = createMapStore();
    await store.save("owner-a", "vocabes00000001", serverMap());
    await store.save("owner-a", "vocabstarter001", serverMap({ fingerprint: "fp-starter" }));
    expect((await store.read("owner-a", "vocabes00000001"))?.fingerprint).toBe("fp-1");
    expect((await store.read("owner-a", "vocabstarter001"))?.fingerprint).toBe("fp-starter");
    expect(await store.read("owner-b", "vocabes00000001")).toBeNull();
    await store.save("owner-a", "vocabes00000001", serverMap({ fingerprint: "fp-2" }));
    expect((await store.read("owner-a", "vocabes00000001"))?.fingerprint).toBe("fp-2");
  });

  it("falls back to memory where there is no IndexedDB", async () => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: undefined });
    const store = createMapStore();
    expect(store).toBeInstanceOf(MemoryMapStore);
    await store.save("owner-a", "vocabes00000001", serverMap());
    expect((await store.read("owner-a", "vocabes00000001"))?.fingerprint).toBe("fp-1");
  });
});
