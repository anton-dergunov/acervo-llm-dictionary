import { describe, expect, it, vi } from "vitest";
import { MemoryDatabase } from "./localDatabase";
import { LOCAL_SCHEMA_VERSION, LocalAcervoRepository } from "./repository";
import { fakeRemote } from "./testRemote";
import { articleFor } from "./selectors";
import { parseArticle, YAML_TEMPLATE, yamlFor } from "./yaml";

const lexemeInput = {
  language: "es", headword: "desmayarse", lemma: "desmayarse", reading: null, ipa: null, pos: "verb" as const,
  gender: null, register: "neutral" as const, dialect: null, emoji: "😵‍💫", topicIds: [],
  status: "active" as const, shortGloss: null, notes: [], primaryGloss: null, emotion: null, clipsSearchedAt: null
};

describe("the Acervo repository", () => {
  it("commits valid multi-collection graph writes atomically", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: repository.snapshot().deviceId, revision: 0
    };
    await repository.writeGraph({
      topics: [{ id: "topic0000000001", name: "Health", icon: "🩺", order: 0, ...sync }],
      lexemes: [{ id: "lexeme000000001", ...lexemeInput, topicIds: ["topic0000000001"], ...sync }],
      senses: [{
        id: "sense0000000001", lexemeId: "lexeme000000001", definition: "Perder el conocimiento.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to faint"] }], domain: null, emoji: null, order: 0, ...sync
      }]
    });
    expect(repository.snapshot().topics).toHaveLength(1);
    expect(repository.snapshot().lexemes).toHaveLength(1);
    expect(repository.snapshot().senses).toHaveLength(1);
  });

  it("leaves every store untouched when a graph write is invalid", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    const sync = {
      ownerId: "owner0000000001", deleted: false, createdAt: "2026-08-28T12:00:00.000Z",
      editedAt: "2026-08-28T12:00:00.000Z", editedBy: repository.snapshot().deviceId, revision: 0
    };
    await expect(repository.writeGraph({ senses: [{
      id: "sense0000000001", lexemeId: "missing00000001", definition: "Missing", definitionLang: "en",
      glosses: [{ lang: "en", terms: ["missing"] }], domain: null, emoji: null, order: 0, ...sync
    }] })).rejects.toThrow("missing lexeme");
    expect((await database.read()).senses).toEqual([]);
  });

  it("stores a complete graph with the revisions the server allocated", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    const topic = await repository.saveTopic({ name: "Health", icon: "🩺", order: 0 }, "topic0000000001");
    const lexeme = await repository.saveLexeme({ ...lexemeInput, topicIds: [topic.id] }, "lexeme000000001");
    const sense = await repository.saveSense({
      lexemeId: lexeme.id, definition: "Perder brevemente el conocimiento.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to faint", "to pass out"] }], domain: "health", emoji: null, order: 0
    }, "sense0000000001");
    const attestation = await repository.saveAttestation({
      lexemeId: lexeme.id, text: "Se desmayó durante la clase.", translation: null, sourceUrl: null,
      sourceTitle: "Language lesson", sourceKind: "lesson", capturedAt: "2026-08-28T12:00:00.000Z",
      photoRef: null, photoRegion: null
    }, "attest000000001");
    await repository.saveExample({
      senseId: sense.id, text: "Se desmayó durante la clase.", textLang: "es", translation: "They fainted during class.",
      translationLang: "en", origin: "attestation", sourceAttestationId: attestation.id, modelId: null,
      videoRef: null, videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null,
      clipRef: null, imageRef: null, emotion: null, note: null,
      matchedForm: null, matchedTranslationForm: null
    }, "example00000001");
    expect(repository.snapshot()).toMatchObject({ ready: true, ownerId: "owner0000000001" });
    // Every stored record carries the revision the server allocated, never a locally invented one.
    const stored = await database.read();
    expect([...stored.topics, ...stored.lexemes, ...stored.senses, ...stored.attestations, ...stored.examples]
      .map((record) => record.revision).sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5]);
  });

  it("atomically refuses invalid relations and Chinese records without readings", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    await expect(repository.saveSense({
      lexemeId: "missing00000001", definition: "Missing", definitionLang: "en",
      glosses: [{ lang: "en", terms: ["missing"] }], domain: null, emoji: null, order: 0
    })).rejects.toThrow("missing lexeme");
    await expect(repository.saveLexeme({ ...lexemeInput, language: "zh-Hans", headword: "图书馆", lemma: "图书馆" }))
      .rejects.toThrow("require a reading");
    expect(repository.snapshot().senses).toHaveLength(0);
    expect(repository.snapshot().lexemes).toHaveLength(0);
  });

  it("tombstones a lexeme and its dependent graph in one write", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    const lexeme = await repository.saveLexeme(lexemeInput, "lexeme000000001");
    await repository.saveSense({
      lexemeId: lexeme.id, definition: "Perder el conocimiento.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["faint"] }], domain: null, emoji: null, order: 0
    }, "sense0000000001");
    await repository.delete("lexemes", lexeme.id);
    expect(repository.snapshot().lexemes[0].deleted).toBe(true);
    expect(repository.snapshot().senses[0].deleted).toBe(true);
    // The lexeme and its dependent sense travel to the server as one batch.
    expect(Object.keys(remote.sent.at(-1)!).sort()).toEqual(["lexemes", "senses"]);
  });

  it("tombstones a topic and removes it from related lexemes atomically", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    const topic = await repository.saveTopic({ name: "Health", icon: "🩺", order: 0 }, "topic0000000001");
    await repository.saveLexeme({ ...lexemeInput, topicIds: [topic.id] }, "lexeme000000001");
    await repository.delete("topics", topic.id);
    expect(repository.snapshot().topics[0].deleted).toBe(true);
    expect(repository.snapshot().lexemes[0].topicIds).toEqual([]);
    expect(Object.keys(remote.sent.at(-1)!).sort()).toEqual(["lexemes", "topics"]);
  });

  it("leaves every store untouched when the server refuses the write", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    await repository.saveLexeme(lexemeInput, "lexeme000000001");
    const before = await database.read();

    remote.fail = new Error("This entry was changed somewhere else.");
    await expect(repository.delete("lexemes", "lexeme000000001")).rejects.toThrow("changed somewhere else");

    expect(await database.read()).toEqual(before);
    expect(repository.snapshot().lexemes[0].deleted).toBe(false);
  });

  it("refuses to write with no transport attached, rather than queueing", async () => {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    await expect(repository.saveLexeme(lexemeInput, "lexeme000000001")).rejects.toThrow("not connected");
    expect((await database.read()).lexemes).toEqual([]);
  });

  it("does not let two graph writes landing at once drop each other's records", async () => {
    // The window is the await inside a commit: both callers copy the graph, both store, and the
    // later assignment would silently discard the earlier one's records.
    const database = new MemoryDatabase();
    const write = database.write.bind(database);
    let gate: Promise<void> | null = null;
    database.write = async (changes) => { if (gate) await gate; return write(changes); };

    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const topic = (id: string, name: string, revision: number) => ({
      id, name, icon: null, order: 0, ownerId: "owner0000000001", deleted: false,
      createdAt: "2026-08-29T12:00:00.000Z", editedAt: "2026-08-29T12:00:00.000Z",
      editedBy: "device000000001", revision
    });

    let release: () => void = () => {};
    gate = new Promise<void>((resolve) => { release = resolve; });
    const first = repository.applyRemote({ topics: [topic("topic0000000001", "Health", 1)] }, 1, "dataset00000001");
    const second = repository.applyRemote({ topics: [topic("topic0000000002", "Travel", 2)] }, 2, "dataset00000001");
    release();
    await Promise.all([first, second]);

    expect(repository.snapshot().topics.map((entry) => entry.id).sort())
      .toEqual(["topic0000000001", "topic0000000002"]);
    expect(repository.snapshot().cursor).toBe(2);
    expect((await database.read()).topics).toHaveLength(2);
  });

  it("wipes another owner's replica without converting it and preserves the device id", async () => {
    const database = new MemoryDatabase();
    const first = new LocalAcervoRepository(database);
    await first.load("owner0000000001");
    first.attachRemote(fakeRemote());
    await first.saveLexeme(lexemeInput, "lexeme000000001");
    const deviceId = first.snapshot().deviceId;
    const second = new LocalAcervoRepository(database);
    await second.load("owner0000000002");
    expect(second.snapshot().lexemes).toEqual([]);
    expect(second.snapshot().deviceId).toBe(deviceId);
    expect(second.snapshot().ownerId).toBe("owner0000000002");
  });

  it("wipes a stored copy the checks refuse and keeps storing, rather than living in memory", async () => {
    // A copy written under a record shape the code has moved on from. It used to make `load` fall
    // back to memory: the stored copy was never repaired, and every cold start downloaded the whole
    // vocabulary again while the interface showed none of it.
    const database = new MemoryDatabase();
    const first = new LocalAcervoRepository(database);
    await first.load("owner0000000001");
    first.attachRemote(fakeRemote());
    await first.saveLexeme(lexemeInput, "lexeme000000001");
    const stored = await database.read();
    await database.write({ senses: [{
      id: "sense0000000009", lexemeId: "lexeme000000999", definition: "Refers to nothing.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["nothing"] }], domain: null, emoji: null, order: 0,
      ownerId: "owner0000000001", deleted: false, createdAt: stored.lexemes[0].createdAt,
      editedAt: stored.lexemes[0].editedAt, editedBy: "device000000001", revision: 3
    }] });

    const reopened = new LocalAcervoRepository(database);
    await reopened.load("owner0000000001");
    expect(reopened.snapshot().lexemes).toEqual([]);
    expect(reopened.state()).toMatchObject({ persistent: true, cursor: 0, deviceId: first.state().deviceId });
    // Wiped in storage too, so the pull that follows lands where the next open will read it.
    const after = await database.read();
    expect(after.lexemes).toEqual([]);
    expect(after.senses).toEqual([]);
    expect(after.meta.schemaVersion).toBe(LOCAL_SCHEMA_VERSION);
  });

  it("wipes a mismatched local schema instead of transforming it", async () => {
    const database = new MemoryDatabase();
    await database.write({ meta: {
      ownerId: "owner0000000001", deviceId: "device000000001", schemaVersion: 999
    } });
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    expect(repository.snapshot()).toMatchObject({
      lexemes: [], cursor: 0, datasetId: "", deviceId: "device000000001", ownerId: "owner0000000001"
    });
    expect((await database.read()).meta.schemaVersion).toBe(LOCAL_SCHEMA_VERSION);
  });
});

describe("saving an article edited as YAML", () => {
  /* What the save *means* is the server's — `tests/unit/server/test_articles.py` is that suite.
     What is left here is the device's half: one round trip carrying the draft, the ids it minted
     and what the replica held, and nothing local moving until the server has answered. */

  async function seeded() {
    const database = new MemoryDatabase();
    const repository = new LocalAcervoRepository(database);
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    await repository.saveTopic({ name: "Health", icon: "🩺", order: 0 }, "topic0000000001");
    await repository.saveLexeme({ ...lexemeInput, topicIds: ["topic0000000001"] }, "lexeme000000001");
    await repository.saveSense({
      lexemeId: "lexeme000000001", definition: "Perder el conocimiento.", definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to faint"] }], domain: null, emoji: null, order: 0
    }, "sense0000000001");
    await repository.saveExample({
      senseId: "sense0000000001", text: "Me desmayé.", textLang: "es", translation: "I fainted.",
      translationLang: "en", origin: "manual", sourceAttestationId: null, modelId: null,
      videoRef: null, videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null,
      clipRef: null, imageRef: null, emotion: null,
      note: null, matchedForm: null, matchedTranslationForm: null
    }, "example00000001");
    const draft = () => parseArticle(yamlFor(articleFor(repository.snapshot(), "lexeme000000001")!));
    return { database, repository, remote, draft };
  }

  it("sends the document once and stores what the server wrote", async () => {
    const { repository, remote, draft } = await seeded();
    const save = vi.spyOn(remote, "saveArticle");
    const article = draft();
    article.headword = "desvanecerse";
    const minted = new Set(["attest000000077"]);

    expect(await repository.saveArticle(article, minted)).toBe("lexeme000000001");

    expect(save).toHaveBeenCalledTimes(1);
    const [sent, named, base] = save.mock.calls[0];
    expect(sent).toEqual(article);
    expect(named).toBe(minted);
    // Every record of the entry, at the revision this replica holds it — nothing else.
    const snapshot = repository.snapshot();
    expect(Object.keys(base).sort()).toEqual(["example00000001", "lexeme000000001", "sense0000000001"]);
    expect(base.lexeme000000001).toBeLessThan(snapshot.lexemes[0].revision);
    expect(snapshot.lexemes[0].headword).toBe("desvanecerse");
  });

  it("names no base for an entry that does not exist yet", async () => {
    const { repository, remote } = await seeded();
    const save = vi.spyOn(remote, "saveArticle");
    const article = parseArticle(YAML_TEMPLATE
      .replace('headword: ""', "headword: sobremesa")
      .replace('definition: ""', "definition: Charla tras la comida.")
      .replace('terms: [""]', "terms: [after-dinner talk]")
      .replace('- text: ""', "- text: La sobremesa duró dos horas.")
      .replace('translation: ""', "translation: The talk lasted two hours."));
    const id = await repository.saveArticle(article);
    expect(save.mock.calls[0][2]).toEqual({});
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === id)!.headword).toBe("sobremesa");
  });

  it("passes on a request to hold enrichment back", async () => {
    const { repository, remote, draft } = await seeded();
    await repository.saveArticle(draft(), undefined, { enrich: false });
    expect(remote.options.at(-1)).toEqual({ enrich: false });
  });

  it("changes nothing locally when the server refuses the save", async () => {
    const { database, repository, remote, draft } = await seeded();
    const before = await database.read();
    const article = draft();
    article.headword = "desvanecerse";

    remote.fail = new Error("This entry was changed somewhere else.");
    await expect(repository.saveArticle(article)).rejects.toThrow("changed somewhere else");

    expect(await database.read()).toEqual(before);
    expect(repository.snapshot().lexemes[0].headword).toBe("desmayarse");
  });

  it("refuses to save without a server, and changes nothing", async () => {
    const { repository, draft } = await seeded();
    repository.attachRemote(null);
    await expect(repository.saveArticle(draft())).rejects.toThrow("not connected to the server");
  });
});

describe("loops", () => {
  const seeded = async () => {
    const repository = new LocalAcervoRepository(new MemoryDatabase());
    await repository.load("owner0000000001");
    repository.attachRemote(fakeRemote());
    await repository.saveVocabulary({
      language: "es", definitionLang: "es", glossLangs: ["en"], notesLang: "en",
      displayName: null, flag: null, order: 0
    }, "vocabes00000001");
    await repository.saveLexeme({ ...lexemeInput, primaryGloss: "to faint" }, "lexeme000000001");
    return repository;
  };

  const loopInput = {
    language: "es", styleId: "sunlit-acoustic", seed: 104740, engineVersion: "1.4.0",
    bedFingerprint: "90c6ad267d159b0e", format: "classic", switches: {}, fallbackFrom: null,
    audioRef: "loops/es/90c6ad267d159b0e.mp3", audioMime: "audio/mpeg",
    durationSeconds: 124.5, position: 0
  };

  const itemInput = {
    loopId: "loop00000000001", lexemeId: "lexeme000000001", position: 0,
    sourceText: "desmayarse", targetText: "to faint", emotion: "alarmed",
    startSeconds: 8.82, sourceRevealSeconds: 8.82, targetRevealSeconds: 17.65, endSeconds: 44.12
  };

  it("round-trips a loop and its item through the server and into the replica", async () => {
    const repository = await seeded();
    const loop = await repository.saveLoop(loopInput, "loop00000000001");
    await repository.writeGraph({
      loopItems: [{ id: "loopitem0000001", ...itemInput, ownerId: "owner0000000001", deleted: false,
        createdAt: loop.createdAt, editedAt: loop.editedAt, editedBy: loop.editedBy, revision: 0 }]
    });
    const snapshot = repository.snapshot();
    expect(snapshot.loops.map((one) => one.audioRef)).toEqual(["loops/es/90c6ad267d159b0e.mp3"]);
    expect(snapshot.loopItems.map((one) => one.sourceText)).toEqual(["desmayarse"]);
    // Only the server mints a revision, and both records took one.
    expect(snapshot.loops[0].revision).toBeGreaterThan(0);
    expect(snapshot.loopItems[0].revision).toBeGreaterThan(0);
  });

  it("tombstones a loop's items and lines with it, and nothing else", async () => {
    const repository = await seeded();
    const loop = await repository.saveLoop(loopInput, "loop00000000001");
    const stamp = { ownerId: "owner0000000001", deleted: false, createdAt: loop.createdAt,
      editedAt: loop.editedAt, editedBy: loop.editedBy, revision: 0 };
    await repository.writeGraph({
      loopItems: [{ id: "loopitem0000001", ...itemInput, ...stamp }],
      loopCues: [{ id: "loopcue00000001", loopId: "loop00000000001", position: 0, group: 0, kind: "say",
        section: "words", loopItemId: "loopitem0000001", side: "source", role: "native", language: "es",
        text: "desmayarse", take: 0, startSeconds: 8.82, endSeconds: 9.5, ...stamp }]
    });
    await repository.delete("loops", "loop00000000001");
    const snapshot = repository.snapshot();
    expect(snapshot.loops[0].deleted).toBe(true);
    expect(snapshot.loopItems[0].deleted).toBe(true);
    expect(snapshot.loopCues[0].deleted).toBe(true);
    // The word it named is untouched: deleting a loop deletes a recording, not vocabulary.
    expect(snapshot.lexemes[0].deleted).toBe(false);
  });

  it("leaves a loop item alive when its word is deleted, so the caption stays truthful", async () => {
    const repository = await seeded();
    const loop = await repository.saveLoop(loopInput, "loop00000000001");
    await repository.writeGraph({
      loopItems: [{ id: "loopitem0000001", ...itemInput, ownerId: "owner0000000001", deleted: false,
        createdAt: loop.createdAt, editedAt: loop.editedAt, editedBy: loop.editedBy, revision: 0 }]
    });
    await repository.delete("lexemes", "lexeme000000001");
    const snapshot = repository.snapshot();
    expect(snapshot.lexemes[0].deleted).toBe(true);
    // A loop is a recording. It keeps playing, captioned with what was actually said, and the item
    // simply points at a tombstone from here on.
    expect(snapshot.loopItems[0].deleted).toBe(false);
    expect(snapshot.loopItems[0].sourceText).toBe("desmayarse");
    expect(snapshot.loops[0].deleted).toBe(false);
  });
});

describe("taking words out of the Inbox", () => {
  const seeded = async (statuses: ("inbox" | "active" | "learned")[]) => {
    const repository = new LocalAcervoRepository(new MemoryDatabase());
    await repository.load("owner0000000001");
    const remote = fakeRemote();
    repository.attachRemote(remote);
    const ids = await Promise.all(statuses.map((status, index) =>
      repository.saveLexeme({ ...lexemeInput, headword: `word${index}`, status },
        `lexeme00000000${index}`).then((lexeme) => lexeme.id)));
    remote.calls = 0;
    remote.sent = [];
    return { repository, remote, ids };
  };

  it("files every named inbox word in one round trip", async () => {
    const { repository, remote, ids } = await seeded(["inbox", "inbox", "inbox"]);
    expect(await repository.fileWords(ids)).toBe(3);

    // One change set, not one request each: this exists to empty an Inbox a whole imported
    // vocabulary landed in, and a few hundred round trips is minutes on a tablet.
    expect(remote.calls).toBe(1);
    expect(remote.sent[0].lexemes).toHaveLength(3);
    expect(repository.snapshot().lexemes.map((lexeme) => lexeme.status)).toEqual(["active", "active", "active"]);
  });

  it("leaves a word that is not in the Inbox exactly as it is", async () => {
    const { repository, remote, ids } = await seeded(["inbox", "learned", "active"]);
    expect(await repository.fileWords(ids)).toBe(1);
    expect(remote.sent[0].lexemes).toHaveLength(1);
    expect(repository.snapshot().lexemes.map((lexeme) => lexeme.status)).toEqual(["active", "learned", "active"]);

    // Filing twice costs one empty call and never a revision.
    expect(await repository.fileWords(ids)).toBe(0);
    expect(remote.calls).toBe(1);
  });

  it("changes nothing locally when the server refuses", async () => {
    const { repository, remote, ids } = await seeded(["inbox", "inbox"]);
    remote.fail = new Error("Acervo is not connected to the server, so this change was not saved.");
    await expect(repository.fileWords(ids)).rejects.toThrow(/was not saved/);
    expect(repository.snapshot().lexemes.map((lexeme) => lexeme.status)).toEqual(["inbox", "inbox"]);
  });
});
