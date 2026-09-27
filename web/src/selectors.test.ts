import { describe, expect, it } from "vitest";
import { validateGraph, type LoopCue, type LoopItem } from "./domain";
import {
  articleFor, articleFromDraft, bedOfLoop, chosenFor, favouriteBeds, loopEligible, selectedWords, inboxCount, styleLabel, languageOptions, loopCandidates, loopIsReady,
  formatLabel, loopCards, loopItemsOf, loopLineShown, loopMomentAt, loopTitle, loopWordAt, loopsIn, sampleLexemeIds, shortGlossOf,
  strengthOf, topicOptions, visibleRows
} from "./selectors";
import { drillCues, testGraph } from "./testGraph";
import { draftFor, parseArticle, yamlFor } from "./yaml";

const query = { language: "es", topic: "all" as const, query: "", sort: "recent" as const };

describe("vocabulary selectors", () => {
  it("keeps the fixture graph valid against the canonical model", () => {
    expect(() => validateGraph(testGraph())).not.toThrow();
  });

  it("offers a configured language that holds no words yet", () => {
    const graph = testGraph();
    graph.vocabularies.push({
      ...graph.vocabularies[0], id: "vocabru00000001", language: "ru", definitionLang: "ru", notesLang: "en",
      glossLangs: ["en"], order: 2
    });
    const options = languageOptions(graph);
    // Without this a vocabulary could never be filled: there would be nowhere to switch to before
    // its first word, and capture is the thing that would have created that word.
    const russian = options.find((option) => option.code === "ru");
    expect(russian).toMatchObject({ count: 0, configured: true, name: "Russian" });
    // Configured languages keep the owner's order rather than being ranked by size.
    expect(options.map((option) => option.code)).toEqual(["es", "en", "ru"]);
  });

  it("keeps showing a language whose vocabulary record has been removed", () => {
    const graph = testGraph();
    graph.vocabularies = graph.vocabularies.filter((entry) => entry.language !== "en");
    const options = languageOptions(graph);
    expect(options.find((option) => option.code === "en")).toMatchObject({ configured: false });
  });

  it("lists one language at a time and keeps the inbox out of the filed collections", () => {
    const graph = testGraph();
    expect(visibleRows(graph, query).map((row) => row.headword)).toEqual(["picar", "la balsa"]);
    expect(inboxCount(graph, "es")).toBe(1);
    expect(visibleRows(graph, { ...query, topic: "inbox" }).map((row) => row.headword)).toEqual(["espolvorear"]);
    expect(visibleRows(graph, { ...query, language: "en" }).map((row) => row.headword)).toEqual(["turmoil"]);
  });

  it("sorts recently added first, alphabetically past the article, and hardest first", () => {
    const graph = testGraph();
    expect(visibleRows(graph, { ...query, sort: "recent" })[0].headword).toBe("picar");
    expect(visibleRows(graph, { ...query, sort: "alpha" }).map((row) => row.headword)).toEqual(["la balsa", "picar"]);
    expect(visibleRows(graph, { ...query, sort: "hard" })[0].headword).toBe("picar");
  });

  it("searches headwords, definitions and gloss terms", () => {
    const graph = testGraph();
    expect(visibleRows(graph, { ...query, query: "dice" }).map((row) => row.headword)).toEqual(["picar"]);
    expect(visibleRows(graph, { ...query, query: "embarcación" }).map((row) => row.headword)).toEqual(["la balsa"]);
    // Search reaches the inbox, which the topic collections deliberately exclude.
    expect(visibleRows(graph, { ...query, query: "espolvorear" })).toHaveLength(1);
  });

  it("excludes tombstoned records everywhere", () => {
    const graph = testGraph();
    graph.lexemes[1].deleted = true;
    expect(visibleRows(graph, query).map((row) => row.headword)).toEqual(["picar"]);
    graph.senses[1].deleted = true;
    expect(articleFor(graph, "lexemepicar0001")!.senses).toHaveLength(1);
    expect(articleFor(graph, "lexemebalsa0001")).toBeNull();
  });

  it("derives the short form from the configured gloss language, honouring an override", () => {
    const graph = testGraph();
    const balsa = graph.lexemes[1];
    expect(shortGlossOf(graph, balsa)).toBe("raft");
    balsa.shortGloss = "a makeshift raft";
    expect(shortGlossOf(graph, balsa)).toBe("a makeshift raft");
    // English is glossed in Russian, so the Russian terms are the one-liner.
    expect(shortGlossOf(graph, graph.lexemes[3])).toBe("суматоха; смятение");
  });

  it("orders topics by their stored order and counts only filed words", () => {
    const graph = testGraph();
    const topics = topicOptions(graph, "es");
    expect(topics.map((topic) => topic.name)).toEqual(["Food", "Travel"]);
    // espolvorear is Food but still in the inbox, so it is not counted.
    expect(topics[0].count).toBe(1);
  });

  it("offers only the languages the replica actually holds", () => {
    expect(languageOptions(testGraph()).map((option) => [option.code, option.count]))
      .toEqual([["es", 3], ["en", 1]]);
  });

  it("assembles an article with its senses, examples, images, lineage and schedule", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    expect(article.senses.map((entry) => entry.sense.order)).toEqual([0, 1]);
    expect(article.senses[0].examples[0].matchedForm).toBe("pica");
    expect(article.senses[0].images).toHaveLength(1);
    expect(article.senses[1].examples[0].videoTitle).toBe("Comiendo en un mercado");
    expect(article.topics.map((topic) => topic.name)).toEqual(["Food"]);
    expect(article.attestations).toHaveLength(1);
    expect(article.study?.reps).toBe(21);
  });

  it("assembles an article the store has never seen, so a proposal renders like an entry", () => {
    const graph = testGraph();
    const draft = draftFor(articleFor(graph, "lexemepicar0001")!);
    // What capture returns: no lexeme id, a topic the owner keeps, and one the owner does not.
    const proposal = { ...draft, id: null, topics: ["food", "Cetrería"] };

    const article = articleFromDraft(graph, proposal);
    expect(article.lexeme.headword).toBe("picar");
    // Topic names are matched the way a save matches them, so what you review is what will be filed.
    expect(article.topics.map((topic) => topic.id)).toEqual(["topicfood000001", "draft:topic:Cetrería"]);
    expect(article.topics.map((topic) => topic.name)).toEqual(["Food", "Cetrería"]);
    // Senses keep the parentage the document expressed by nesting, and their order.
    expect(article.senses.map((entry) => entry.sense.order)).toEqual([0, 1]);
    expect(article.senses[0].examples.every((example) => example.senseId === article.senses[0].sense.id))
      .toBe(true);
    expect(article.senses[0].images.every((image) => image.lexemeId === article.lexeme.id)).toBe(true);
    // A document cannot carry study state, so a proposal never claims to have any.
    expect(article.study).toBeNull();
  });

  it("keeps a proposal's placeholder ids out of the shape the server accepts", () => {
    const graph = testGraph();
    const stripped = { ...draftFor(articleFor(graph, "lexemepicar0001")!), id: null };
    const lexemeId = articleFromDraft(graph, stripped).lexeme.id;
    // Render-only: nothing assembled here may be written, and a leak has to fail loudly rather
    // than land in the store, so a placeholder is deliberately not a valid record id.
    expect(lexemeId).toBe("draft:lexeme");
    expect(lexemeId).not.toMatch(/^[a-z0-9]{15}$/);
  });

  it("shows exactly what the document says, so approving the preview approves the save", () => {
    const graph = testGraph();
    const document = yamlFor(articleFor(graph, "lexemepicar0001")!);
    const draft = parseArticle(document);
    // The preview is a lossless reading of the document — the other half of the round trip
    // `yaml.test.ts` pins — which is what makes reviewing the article equivalent to reviewing YAML.
    expect(draftFor(articleFromDraft(graph, draft))).toEqual(draft);
  });

  it("scales study strength from stability and leaves unscheduled words empty", () => {
    expect(strengthOf(null)).toBe(0);
    expect(strengthOf({ stability: 4.2 } as never)).toBeLessThan(strengthOf({ stability: 402.7 } as never));
    expect(strengthOf({ stability: 402.7 } as never)).toBe(4);
  });
});


describe("how many pictures a sense shows", () => {
  it("shows one, keeping the drawn one over a bare brief", () => {
    // What an import used to leave behind: the document's row under a random id and the restored
    // picture's under the derived one, so the sense had an empty frame *and* a picture.
    const graph = testGraph();
    const [drawn] = graph.imagePrompts;
    graph.imagePrompts.push({
      ...drawn, id: "imagepicar00099", imageRef: null, imageModelId: null,
      editedAt: "2030-01-01T00:00:00.000Z"
    });

    const [sense] = articleFor(graph, "lexemepicar0001")!.senses;
    expect(sense.images.map((image) => image.id)).toEqual(["imagepicar00010"]);
  });

  it("falls back to the most recently edited when neither has a picture", () => {
    const graph = testGraph();
    const [first] = graph.imagePrompts;
    Object.assign(first, { imageRef: null, imageModelId: null, editedAt: "2026-01-01T00:00:00.000Z" });
    graph.imagePrompts.push({
      ...first, id: "imagepicar00099", editedAt: "2026-06-01T00:00:00.000Z"
    });

    const [sense] = articleFor(graph, "lexemepicar0001")!.senses;
    expect(sense.images.map((image) => image.id)).toEqual(["imagepicar00099"]);
  });
});

describe("loops", () => {
  const graph = testGraph();

  it("is a valid graph with loops in it", () => {
    expect(() => validateGraph(graph)).not.toThrow();
  });

  it("orders loops by position and their items by the order they are heard", () => {
    const loops = loopsIn(graph, "es");
    expect(loops.map((loop) => loop.id)).toEqual(["loopmorning0001", "loopqueued00001"]);
    expect(loopItemsOf(graph, "loopmorning0001").map((item) => item.sourceText))
      .toEqual(["picar", "la balsa"]);
    // Another language's loops are not this language's.
    expect(loopsIn(graph, "en")).toEqual([]);
  });

  it("reads readiness off the reference and nothing else", () => {
    const [rendered, queued] = loopsIn(graph, "es");
    expect(loopIsReady(rendered)).toBe(true);
    expect(loopIsReady(queued)).toBe(false);
  });

  it("finds the kept bed a loop's music is, by style and seed", () => {
    const [rendered, queued] = loopsIn(graph, "es");
    expect(bedOfLoop(graph, rendered)?.id).toBe("bedmorning00001");
    expect(bedOfLoop(graph, queued)).toBeUndefined();
    expect(bedOfLoop(graph, { ...rendered, seed: rendered.seed + 1 })).toBeUndefined();
  });

  it("lists each kept piece of music once, newest first, and never a tombstone", () => {
    const kept = graph.beds[0];
    const twice = { ...graph, beds: [
      kept,
      { ...kept, id: "bedmorning00002", createdAt: "2026-09-05T00:00:00.000Z" },
      { ...kept, id: "bedother0000001", seed: 3, createdAt: "2026-09-04T00:00:00.000Z" },
      { ...kept, id: "bedgone00000001", seed: 4, deleted: true }
    ] };
    expect(favouriteBeds(twice).map((bed) => bed.id)).toEqual(["bedmorning00002", "bedother0000001"]);
  });

  it("names a style in words, the generator's where it gave them", () => {
    expect(styleLabel([{ id: "acoustic-flow", label: "Acoustic flow" }], "acoustic-flow")).toBe("Acoustic flow");
    expect(styleLabel(undefined, "bright-pastoral")).toBe("Bright pastoral");
    expect(styleLabel(undefined, null)).toBe("No music yet");
  });

  it("derives a title from the words rather than storing one", () => {
    expect(loopTitle(graph, loopsIn(graph, "es")[0])).toBe("picar, la balsa");
    expect(loopTitle(graph, loopsIn(graph, "es")[1])).toBe("Empty loop");
    // Past the limit it counts the rest, so two loops over the same words still read differently.
    expect(loopTitle(graph, loopsIn(graph, "es")[0], 1)).toBe("picar +1");
  });

  it("captions what was said, so editing the word afterwards changes nothing", () => {
    const edited = testGraph();
    const picar = edited.lexemes.find((one) => one.id === "lexemepicar0001")!;
    picar.headword = "picotear";
    picar.primaryGloss = "to peck";
    expect(loopItemsOf(edited, "loopmorning0001")[0].sourceText).toBe("picar");
    expect(loopTitle(edited, loopsIn(edited, "es")[0])).toBe("picar, la balsa");
  });

  it("offers only words a loop could actually speak", () => {
    // `lexemeespolv001` has no primaryGloss: `shortGloss` may carry several meanings and a loop
    // must choose between them, so a word without one is simply not eligible.
    const candidates = loopCandidates(graph, query).map((lexeme) => lexeme.id);
    expect(candidates).toContain("lexemepicar0001");
    expect(candidates).toContain("lexemebalsa0001");
    expect(candidates).not.toContain("lexemeespolv001");
  });

  it("samples the same words for the same scope and seed, and never more than there are", () => {
    const once = sampleLexemeIds(graph, query, 2, 7);
    expect(once).toHaveLength(2);
    expect(sampleLexemeIds(graph, query, 2, 7)).toEqual(once);
    expect(new Set(once).size).toBe(2);
    expect(sampleLexemeIds(graph, query, 99, 7)).toHaveLength(loopCandidates(graph, query).length);
    expect(sampleLexemeIds(graph, query, 0, 7)).toEqual([]);
  });
});

describe("the selection", () => {
  const graph = testGraph();

  it("keeps the words that still exist in this language, in the order chosen", () => {
    const deleted = testGraph();
    deleted.lexemes.find((one) => one.id === "lexemebalsa0001")!.deleted = true;
    const ids = ["lexemeturmoil01", "lexemebalsa0001", "lexemepicar0001", "lexemenothere01"];
    expect(selectedWords(graph, "es", ids).map((word) => word.id)).toEqual(["lexemebalsa0001", "lexemepicar0001"]);
    expect(selectedWords(deleted, "es", ids).map((word) => word.id)).toEqual(["lexemepicar0001"]);
  });

  it("says which chosen words a kind will leave out, and why", () => {
    const words = selectedWords(graph, "es", ["lexemeespolv001", "lexemebalsa0001", "lexemepicar0001"]);
    const chosen = chosenFor(graph, words, { eligible: loopEligible, why: "no single term to say", max: 1, noun: "loop" });
    expect(chosen.map((word) => [word.id, word.skip])).toEqual([
      ["lexemeespolv001", "no single term to say"],
      ["lexemebalsa0001", ""],
      ["lexemepicar0001", "a loop takes at most 1"]
    ]);
  });
});

describe("playing a loop", () => {
  /* The cadence a real render produced: `asco` at 8.82, `disgust` at 17.65, then the pair again at
     22.06 / 26.47 and at 30.88 / 35.29, the word running to 44.12. */
  const word = (over: Partial<LoopItem> = {}): LoopItem => ({
    id: "loopitem0000001", loopId: "loop00000000001", lexemeId: "lexeme000000001", position: 0,
    sourceText: "asco", targetText: "disgust", emotion: "repulsed",
    startSeconds: 8.82, sourceRevealSeconds: 8.82, targetRevealSeconds: 17.65, endSeconds: 44.12,
    ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
    editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1, ...over
  });
  const line = (over: Partial<LoopCue>): LoopCue => ({
    id: `cue${String(over.position ?? 0).padStart(12, "0")}`, loopId: "loop00000000001", position: 0,
    group: 0, kind: "say", section: "words", loopItemId: null, side: null, role: "native",
    language: "es", text: "", take: 0, startSeconds: 0, endSeconds: 0,
    ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
    editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1, ...over
  });
  const drill = drillCues("loop00000000001", [word()], 4.41);

  it("draws a drill as one card whose word and translation are each one row", () => {
    const [card] = loopCards(drill);
    expect(card.lines.map((one) => [one.text, one.language, one.starts.length])).toEqual([
      ["asco", "es", 3], ["disgust", "en", 3]
    ]);
    expect(card.lines[1].starts).toEqual([17.65, 26.47, 35.29].map((at) => expect.closeTo(at, 5)));
  });

  it("follows which line was said most recently", () => {
    const cards = loopCards(drill);
    const sounding = (at: number) => loopMomentAt(cards, at).sounding;
    expect(sounding(5)).toBe(-1);                 // the bed, before the first word
    expect(sounding(9)).toBe(0);
    expect(sounding(17)).toBe(0);                 // still the word: the answer has not been said
    expect(sounding(18)).toBe(1);
    expect(sounding(23)).toBe(0);
    expect(sounding(27)).toBe(1);
    expect(sounding(31)).toBe(0);
    expect(sounding(36)).toBe(1);
    expect(sounding(43)).toBe(1);                 // held through the tail, being the last heard
  });

  it("withholds everything after a card's first line until it is said, and again if you wind back", () => {
    const [card] = loopCards(drill);
    expect(loopLineShown(card, 0, 0)).toBe(true);  // the question is always there
    expect(loopLineShown(card, 1, 12)).toBe(false);
    expect(loopLineShown(card, 1, 18)).toBe(true);
    // A function of the clock and not a latch, so this is the same question again.
    expect(loopLineShown(card, 1, 12)).toBe(false);
  });

  it("keeps a quiz's answer back, since there the translation comes first", () => {
    const [card] = loopCards([
      line({ position: 0, section: "quiz", side: "target", role: "guide", language: "en", text: "disgust", startSeconds: 100, loopItemId: "loopitem0000001" }),
      line({ position: 1, section: "quiz", side: "source", text: "asco", startSeconds: 104, loopItemId: "loopitem0000001" })
    ]);
    expect(card.lines.map((one) => one.text)).toEqual(["disgust", "asco"]);
    expect(loopLineShown(card, 1, 102)).toBe(false);
    expect(loopLineShown(card, 1, 104)).toBe(true);
  });

  it("gives every other line its own card, and an example's meaning after it is heard", () => {
    const cards = loopCards([
      line({ position: 0, group: 0, kind: "intro", section: "intro", role: "guide", language: "en", text: "Two words today.", startSeconds: 2 }),
      line({ position: 1, group: 1, kind: "example", text: "Me da asco.", startSeconds: 10 }),
      line({ position: 2, group: 1, kind: "translation", role: "guide", language: "en", text: "It disgusts me.", startSeconds: 13 })
    ]);
    expect(cards.map((card) => card.kind)).toEqual(["intro", "example"]);
    expect(loopLineShown(cards[1], 1, 12)).toBe(false);
    expect(loopLineShown(cards[1], 1, 13)).toBe(true);
  });

  it("gives the gap after a card to the card just heard rather than to the next one", () => {
    const second = word({ id: "loopitem0000002", position: 1, sourceText: "la balsa", targetText: "raft",
                          startSeconds: 60, sourceRevealSeconds: 60, targetRevealSeconds: 68.8, endSeconds: 95 });
    const cards = loopCards(drillCues("loop00000000001", [word(), second], 4.41));
    // 44.12 is where the first word ends and 60 is where the second begins: the bed in between
    // belongs to the first, so the card does not go dark while its music plays on.
    expect(loopMomentAt(cards, 50).card).toBe(0);
    expect(loopMomentAt(cards, 60).card).toBe(1);
    expect(loopMomentAt(cards, 0).card).toBe(-1);
    expect(loopWordAt([word(), second], cards, 61)?.sourceText).toBe("la balsa");
    expect(loopWordAt([word(), second], cards, 0)).toBeNull();
  });

  it("names a format by the generator's label, else by its id made readable", () => {
    expect(formatLabel([{ id: "radio-lesson", label: "Radio lesson" }], "radio-lesson")).toBe("Radio lesson");
    expect(formatLabel(undefined, "radio-lesson")).toBe("Radio lesson");
  });
});
