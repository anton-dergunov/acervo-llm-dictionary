import { afterEach, describe, expect, it, vi } from "vitest";
import { forgetPlace, lastPlace, placeIn, rememberPlace } from "./lastPlace";
import { ENGLISH, SPANISH, testGraph } from "./testGraph";

describe("where you were", () => {
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

  it("remembers a place and forgets it on sign-out", () => {
    rememberPlace({ vocabularyId: SPANISH, topic: "all", openId: "lexemepicar0001" });
    expect(lastPlace()).toEqual({ vocabularyId: SPANISH, topic: "all", openId: "lexemepicar0001" });
    forgetPlace();
    expect(lastPlace()).toBeNull();
  });

  it("keeps only what the graph still holds", () => {
    const graph = testGraph();
    expect(placeIn(graph, { vocabularyId: SPANISH, topic: "all", openId: "lexemepicar0001" }))
      .toEqual({ vocabularyId: SPANISH, topic: "all", openId: "lexemepicar0001" });
    // A word that has gone is not reopened; a topic that has gone falls back to all words.
    expect(placeIn(graph, { vocabularyId: SPANISH, topic: "topicgone000001", openId: "lexeme000000999" }))
      .toEqual({ vocabularyId: SPANISH, topic: "all", openId: null });
    // A word is reopened only in its own vocabulary.
    expect(placeIn(graph, { vocabularyId: ENGLISH, topic: "all", openId: "lexemepicar0001" })?.openId ?? null).toBeNull();
    // A vocabulary the replica no longer holds means no place at all.
    expect(placeIn(graph, { vocabularyId: "vocabgone000001", topic: "all", openId: null })).toBeNull();
    expect(placeIn(graph, null)).toBeNull();
  });

  it("does not reopen a deleted word", () => {
    const graph = testGraph();
    graph.lexemes = graph.lexemes.map((one) => one.id === "lexemepicar0001" ? { ...one, deleted: true } : one);
    expect(placeIn(graph, { vocabularyId: SPANISH, topic: "all", openId: "lexemepicar0001" })?.openId).toBeNull();
  });

  it("treats storage that is unreadable or refuses as having nothing", () => {
    localStorage.setItem("acervo-last-place", "{not json");
    expect(lastPlace()).toBeNull();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => rememberPlace({ vocabularyId: SPANISH, topic: "all", openId: null })).not.toThrow();
    expect(lastPlace()).toBeNull();
  });
});
