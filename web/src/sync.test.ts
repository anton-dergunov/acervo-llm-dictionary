import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, SCHEMA_VERSION } from "./api";
import type { VocabularyGraph } from "./domain";
import { repository } from "./repository";
import { syncEngine } from "./sync";
import { TEST_OWNER, testGraph } from "./testGraph";

const DATASET = "dataset00000001";
const EMPTY = (): VocabularyGraph => ({
  vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [], pronunciations: [], studyStates: [], loops: [], loopItems: [], loopCues: [], stories: [], storyParts: [], storyWords: [], beds: []
});

/** The server numbers every row it hands back; the cursor is the highest of them. */
function numbered(graph: VocabularyGraph = testGraph()) {
  let revision = 0;
  (Object.keys(graph) as (keyof VocabularyGraph)[]).forEach((kind) => {
    (graph[kind] as { revision: number }[]).forEach((record) => { record.revision = ++revision; });
  });
  return { graph, cursor: revision };
}

function pullResponse(changes: VocabularyGraph, cursor: number, datasetId = DATASET) {
  return { schemaVersion: SCHEMA_VERSION, datasetId, cursor, serverTime: "2026-08-29T12:00:00.000Z", changes };
}

const signedIn = () => vi.spyOn(backendSession, "current")
  .mockReturnValue({ baseUrl: "https://acervo.example.com", email: "learner@account.example.com", token: "t", userId: TEST_OWNER });

describe("the cursor pull", () => {
  beforeEach(async () => {
    await repository.clear();
    await repository.load(TEST_OWNER);
    signedIn();
    syncEngine.start();
  });
  afterEach(() => { syncEngine.stop(); vi.restoreAllMocks(); });

  it("fills an empty replica and remembers where it got to", async () => {
    const { graph, cursor } = numbered();
    const pull = vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);
    expect(pull).toHaveBeenCalledWith(0);
    const snapshot = repository.snapshot();
    expect(snapshot.lexemes).toHaveLength(4);
    expect(snapshot.senses).toHaveLength(5);
    expect(snapshot.cursor).toBe(cursor);
    expect(snapshot.datasetId).toBe(DATASET);
    expect(syncEngine.getStatus().state).toBe("idle");
  });

  it("asks only for what it has not seen, and an empty delta changes nothing", async () => {
    const { graph, cursor } = numbered();
    const pull = vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);

    pull.mockResolvedValue(pullResponse(EMPTY(), cursor));
    await syncEngine.syncNow(true);
    expect(pull).toHaveBeenLastCalledWith(cursor);
    expect(repository.snapshot().lexemes).toHaveLength(4);
  });

  it("applies a tombstone that arrives in a later delta", async () => {
    const { graph, cursor } = numbered();
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);

    const removed = { ...graph.lexemes[0], deleted: true, revision: cursor + 1 };
    vi.spyOn(backendSession, "pullGraph")
      .mockResolvedValue(pullResponse({ ...EMPTY(), lexemes: [removed] }, cursor + 1));
    await syncEngine.syncNow(true);
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === removed.id)?.deleted).toBe(true);
  });

  it("ignores a record older than the one it already holds", async () => {
    const { graph, cursor } = numbered();
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);

    const stale = { ...graph.lexemes[0], headword: "stale", revision: 1 };
    vi.spyOn(backendSession, "pullGraph")
      .mockResolvedValue(pullResponse({ ...EMPTY(), lexemes: [stale] }, cursor));
    await syncEngine.syncNow(true);
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === stale.id)?.headword).not.toBe("stale");
  });

  it("keeps the replica and reports offline when the server cannot be reached", async () => {
    const { graph, cursor } = numbered();
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);

    vi.spyOn(backendSession, "pullGraph")
      .mockRejectedValue(new AcervoApiError("The Acervo server could not be reached.", 0, "offline"));
    await syncEngine.syncNow(true);
    expect(syncEngine.getStatus().state).toBe("offline");
    expect(repository.snapshot().lexemes).toHaveLength(4);
  });

  it("refuses a graph containing another account's records", async () => {
    const { graph, cursor } = numbered();
    graph.topics[0].ownerId = "owner0000000002";
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);
    expect(syncEngine.getStatus().state).toBe("offline");
    expect(repository.snapshot().lexemes).toHaveLength(0);
  });

  it("runs at most one more request however many callers ask while one is running", async () => {
    const pull = vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(EMPTY(), 0));
    await Promise.all([syncEngine.syncNow(), syncEngine.syncNow(), syncEngine.syncNow(), syncEngine.syncNow()]);
    expect(pull).toHaveBeenCalledTimes(2);
    await syncEngine.syncNow();
    expect(pull).toHaveBeenCalledTimes(3);
  });

  it("fetches a change announced while a pull that left before it was still running", async () => {
    // The lost revision: the first request was answered from before the change, and a caller that
    // heard about the change used to be handed that same answer.
    const { graph, cursor } = numbered();
    const pull = vi.spyOn(backendSession, "pullGraph")
      .mockResolvedValueOnce(pullResponse(EMPTY(), 0))
      .mockResolvedValueOnce(pullResponse(graph, cursor));
    const first = syncEngine.syncNow();
    const announced = syncEngine.syncNow();
    await Promise.all([first, announced]);
    expect(pull).toHaveBeenCalledTimes(2);
    expect(repository.snapshot().lexemes).toHaveLength(graph.lexemes.length);
  });

  it("hands out the same snapshot until something changes", async () => {
    const { graph, cursor } = numbered();
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);
    const before = repository.snapshot();
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(EMPTY(), cursor));
    await syncEngine.syncNow(true);
    expect(repository.snapshot().lexemes).toBe(before.lexemes);
    expect(repository.snapshot().senses).toBe(before.senses);
  });

  it("shares collections a pull did not touch and refuses to be edited in place", async () => {
    const { graph, cursor } = numbered();
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);
    const before = repository.snapshot();
    const renamed = { ...graph.lexemes[0], headword: "renamed", revision: cursor + 1 };
    vi.spyOn(backendSession, "pullGraph")
      .mockResolvedValue(pullResponse({ ...EMPTY(), lexemes: [renamed] }, cursor + 1));
    await syncEngine.syncNow(true);
    const after = repository.snapshot();
    expect(after).not.toBe(before);
    expect(after.senses).toBe(before.senses);
    expect(after.lexemes.find((lexeme) => lexeme.id === renamed.id)?.headword).toBe("renamed");
    expect(before.lexemes.find((lexeme) => lexeme.id === renamed.id)?.headword).not.toBe("renamed");
    expect(() => { (after.lexemes as unknown[]).push({}); }).toThrow();
    expect(() => { (after.lexemes[0] as { headword: string }).headword = "edited"; }).toThrow();
  });
});

describe("synchronisation that must stop", () => {
  beforeEach(async () => {
    await repository.clear();
    await repository.load(TEST_OWNER);
    signedIn();
    syncEngine.start();
  });
  afterEach(() => { syncEngine.stop(); vi.restoreAllMocks(); });

  it("blocks on a schema mismatch and stops asking, while reading still works", async () => {
    const pull = vi.spyOn(backendSession, "pullGraph")
      .mockRejectedValue(new AcervoApiError("Update the app to continue.", 409, "schema_version_mismatch"));
    await syncEngine.syncNow(true);
    expect(syncEngine.getStatus().state).toBe("blocked");

    await syncEngine.syncNow(true);
    expect(pull).toHaveBeenCalledTimes(1);
    expect(repository.snapshot().ready).toBe(true);
  });

  it("stops without destroying anything when the server database changed identity", async () => {
    const { graph, cursor } = numbered();
    const pull = vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);

    pull.mockResolvedValue(pullResponse(EMPTY(), 3, "dataset00000002"));
    await syncEngine.syncNow(true);
    expect(syncEngine.getStatus().state).toBe("datasetChanged");
    // The whole point: this replica may be the most complete copy left, so it is untouched.
    const snapshot = repository.snapshot();
    expect(snapshot.lexemes).toHaveLength(4);
    expect(snapshot.datasetId).toBe(DATASET);
    expect(snapshot.cursor).toBe(cursor);
  });

  it("makes no request at all when nobody is signed in", async () => {
    vi.spyOn(backendSession, "current").mockReturnValue(null);
    const pull = vi.spyOn(backendSession, "pullGraph");
    await syncEngine.syncNow(true);
    expect(pull).not.toHaveBeenCalled();
    expect(syncEngine.getStatus().state).toBe("signedOut");
  });
});

describe("writing through the server", () => {
  beforeEach(async () => {
    await repository.clear();
    await repository.load(TEST_OWNER);
    signedIn();
    syncEngine.start();
    const { graph, cursor } = numbered();
    vi.spyOn(backendSession, "pullGraph").mockResolvedValue(pullResponse(graph, cursor));
    await syncEngine.syncNow(true);
  });
  afterEach(() => { syncEngine.stop(); vi.restoreAllMocks(); });

  it("stores what the server returns, not what was sent", async () => {
    const cursor = repository.snapshot().cursor;
    const push = vi.spyOn(backendSession, "pushGraph").mockImplementation(async (_device, changes) => ({
      schemaVersion: SCHEMA_VERSION, datasetId: DATASET, cursor: cursor + 1,
      serverTime: "2026-08-29T12:00:01.000Z",
      // The server allocates the revision; the client never invents one.
      records: { topics: (changes.topics ?? []).map((topic) => ({ ...topic, revision: cursor + 1 })) }
    }));

    const topic = await repository.saveTopic({ name: "Slang", icon: "🗣️", order: 2 });
    expect(push).toHaveBeenCalledOnce();
    const stored = repository.snapshot().topics.find((candidate) => candidate.id === topic.id);
    expect(stored?.revision).toBe(cursor + 1);
  });

  it("changes nothing locally when the write cannot reach the server", async () => {
    vi.spyOn(backendSession, "pushGraph")
      .mockRejectedValue(new AcervoApiError("The Acervo server could not be reached.", 0, "offline"));
    const before = repository.snapshot();

    await expect(repository.delete("lexemes", "lexemebalsa0001")).rejects.toThrow("could not be reached");

    const after = repository.snapshot();
    expect(after.lexemes).toEqual(before.lexemes);
    expect(after.cursor).toBe(before.cursor);
    expect(syncEngine.getStatus().state).toBe("offline");
  });

  it("surfaces a refused stale write and leaves the entry as it was", async () => {
    vi.spyOn(backendSession, "pushGraph").mockRejectedValue(
      new AcervoApiError("This entry was changed somewhere else.", 409, "stale_record")
    );
    const before = repository.snapshot();
    await expect(repository.delete("lexemes", "lexemebalsa0001")).rejects.toThrow("changed somewhere else");
    expect(repository.snapshot().lexemes).toEqual(before.lexemes);
  });

  it("refuses to write at all with no transport attached", async () => {
    syncEngine.stop();
    const before = repository.snapshot();
    await expect(repository.saveTopic({ name: "Slang", icon: null, order: 2 })).rejects.toThrow("not connected");
    expect(repository.snapshot().topics).toEqual(before.topics);
  });
});
