import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";
import { createLocalDatabase } from "./localDatabase";
import { LocalAcervoRepository } from "./repository";
import { fakeRemote } from "./testRemote";

const SPANISH = "vocabes00000001";
const spanish = {
  language: "es", definitionLang: "es", glossLangs: ["en"], notesLang: "en", displayName: null, flag: null,
  region: null, level: null, learnerNote: null, order: 0
};

const lexemeInput = {
  vocabularyId: SPANISH, language: "es", headword: "la balsa", lemma: "balsa", reading: null, ipa: null, pos: "noun" as const,
  gender: "feminine" as const, register: "neutral" as const, dialect: null, emoji: "🛶",
  topicIds: [], status: "active" as const, shortGloss: null, notes: [], primaryGloss: null, emotion: null, clipsSearchedAt: null
};

describe("IndexedDB Acervo repository", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: new IDBFactory() });
  });

  it("persists an atomic multi-store graph, and the cursor that covers it", async () => {
    const first = new LocalAcervoRepository(createLocalDatabase());
    await first.load("owner0000000001");
    first.attachRemote(fakeRemote());
    await first.saveVocabulary(spanish, SPANISH);
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: first.snapshot().deviceId, revision: 0
    };
    await first.writeGraph({
      topics: [{ id: "topic0000000001", name: "Travel", icon: "🧭", order: 0, ...sync }],
      lexemes: [{ id: "lexeme000000001", ...lexemeInput, topicIds: ["topic0000000001"], ...sync }],
      senses: [{
        id: "sense0000000001", lexemeId: "lexeme000000001", definition: "Una embarcación sencilla.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["raft"] }], domain: null, emoji: null, order: 0, ...sync
      }]
    });

    await first.applyRemote({}, 41, "dataset00000001");

    const reopened = new LocalAcervoRepository(createLocalDatabase());
    await reopened.load("owner0000000001");
    // The cursor and the dataset it counts within survive a reload, or the next pull would either
    // refetch everything or silently skip what it already asked for.
    expect(reopened.snapshot()).toMatchObject({ persistent: true, cursor: 41, datasetId: "dataset00000001" });
    expect(reopened.snapshot().topics[0].name).toBe("Travel");
    expect(reopened.snapshot().lexemes[0].headword).toBe("la balsa");
    expect(reopened.snapshot().senses[0].lexemeId).toBe("lexeme000000001");
  });

  it("wipes the IndexedDB replica when the authenticated owner changes", async () => {
    const first = new LocalAcervoRepository(createLocalDatabase());
    await first.load("owner0000000001");
    first.attachRemote(fakeRemote());
    await first.saveVocabulary(spanish, SPANISH);
    await first.saveLexeme(lexemeInput, "lexeme000000001");
    const deviceId = first.snapshot().deviceId;

    const second = new LocalAcervoRepository(createLocalDatabase());
    await second.load("owner0000000002");
    expect(second.snapshot().lexemes).toEqual([]);
    expect(second.snapshot()).toMatchObject({ ownerId: "owner0000000002", deviceId, persistent: true });
  });
});
