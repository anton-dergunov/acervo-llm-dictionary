import { describe, expect, it } from "vitest";
import { articleFor } from "./selectors";
import { testGraph } from "./testGraph";
import { draftFor, parseArticle, YAML_TEMPLATE, YamlProblems, yamlFor, yamlForDraft, type ArticleDraft } from "./yaml";

const articles = () => {
  const graph = testGraph();
  return graph.lexemes.map((lexeme) => articleFor(graph, lexeme.id)!);
};

const problemsOf = (text: string): string[] => {
  try { parseArticle(text); }
  catch (error) { return (error as YamlProblems).problems.map((problem) => problem.message); }
  throw new Error("expected the document to be refused");
};

describe("the YAML projection", () => {
  it("writes the record, its ids and the fields the reader will need back", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain("id: lexemepicar0001");
    expect(document).toContain("topics: [Food]");
    expect(document).toContain("- {lang: en, terms: [to itch]}");
    expect(document).toContain("id: sensepicaritch0");
    // Rendered in the read view, and dropped by the projection before this change.
    expect(document).toContain("emotion: exasperated, scratching at the collar");
    expect(document).toContain("matchedTranslationForm: itches");
  });

  it("keeps an instant a string, so it is not read back as a date", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain('capturedAt: "2026-02-11T12:00:00.000Z"');
    expect(parseArticle(document).attestations[0].capturedAt).toBe("2026-02-11T12:00:00.000Z");
  });

  it("writes study state as comments, because the scheduler owns it", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain("# study · anki · reps 21 · lapses 4");
    expect(parseArticle(document)).not.toHaveProperty("study");
  });

  it("quotes a headword that would otherwise read as something else", () => {
    const graph = testGraph();
    graph.lexemes[1].headword = "yes: really";
    const document = yamlFor(articleFor(graph, graph.lexemes[1].id)!);
    expect(document).toContain('headword: "yes: really"');
    expect(parseArticle(document).headword).toBe("yes: really");
  });

  it("tells the reader of a composed word under review that its ids are kept", () => {
    // Not stored, so no lexeme id — but the senses carry the ids the server minted, and a chat edit
    // addresses them. "No ids here" over a body full of ids is a contradiction a model reads literally.
    const draft: ArticleDraft = { ...draftFor(articleFor(testGraph(), "lexemepicar0001")!), id: null };
    const document = yamlForDraft(draft);
    expect(document).toContain("# Not saved yet. Every record keeps its id");
    expect(document).not.toContain("No ids here");
    expect(document).toContain("id: sensepicaritch0");
  });
});

describe("reading YAML back", () => {
  // The safety argument for editing: anything the writer forgets is a field the next save deletes.
  it("round-trips every entry in the fixture without losing a field", () => {
    articles().forEach((article) => {
      expect(parseArticle(yamlFor(article))).toEqual(draftFor(article));
    });
  });

  it("carries every clip field through the document, so export and import keep them", () => {
    // The fixture's `picar` holds one clip. A word file is what `yamlForDraft` writes with its ids
    // stripped, so anything the format drops here is lost on the way through a bundle.
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain("clipRef: seg_7c3d18e5b04a92f6de27");
    const clip = parseArticle(document).senses
      .flatMap((sense) => sense.examples)
      .find((example) => example.origin === "subtitle")!;
    expect(clip.videoChannel).toBe("Easy Spanish");
    expect(clip.videoStart).toBe(461);
    expect(clip.videoEnd).toBe(468);
    expect(clip.clipRef).toBe("seg_7c3d18e5b04a92f6de27");
  });

  it("carries a sense's emoji through the document", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(parseArticle(document).senses.find((sense) => sense.domain === "cooking")!.emoji).toBe("🔪");
  });

  it("reads a document that states no status as an ordinary word, not an Inbox one", () => {
    // The Inbox holds what arrived without anyone reading it. A document is typed or reviewed.
    expect(parseArticle(YAML_TEMPLATE.replace("status: active\n", "").replace('headword: ""', "headword: casa")
      .replace('lemma: ""              # leave empty to reuse the headword', "lemma: casa")
      .replace('definition: ""     # in the target language', "definition: Edificio.")
      .replace('terms: [""]', "terms: [house]").replace('- text: ""', "- text: Mi casa.")).status).toBe("active");
  });

  it("refuses a clip field the format does not know, rather than dropping it", () => {
    // `EXAMPLE_KEYS` is a closed allow-list, which is what makes a forgotten field an error.
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!)
      .replace("clipRef: seg_", "clipSegment: seg_");
    expect(() => parseArticle(document)).toThrow("clipSegment");
  });

  it("treats a record with no id as new and keeps the ids of the rest", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    const document = yamlFor(article)
      .replace("- id: examplepicar010\n        text:", "- text:");
    const draft = parseArticle(document);
    expect(draft.senses[0].examples[0].id).toBeNull();
    expect(draft.senses[0].id).toBe("sensepicaritch0");
  });

  it("reports the field and the line rather than failing as a whole document", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    const document = yamlFor(article).replace("pos: verb", "pos: preposition");
    try {
      parseArticle(document);
      throw new Error("expected the document to be refused");
    } catch (error) {
      const [problem] = (error as YamlProblems).problems;
      expect(problem.message).toContain('pos: must be one of');
      expect(problem.message).toContain('found "preposition"');
      expect(document.split("\n")[problem.line! - 1]).toBe("pos: preposition");
    }
  });

  it("collects every problem in one pass", () => {
    expect(problemsOf("language: es\nheadword: \"\"\nsenses: []\n")).toEqual([
      "headword: is required.",
      "senses: an entry needs at least one sense."
    ]);
  });

  it("refuses a key it does not know, rather than ignoring the typo", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!).replace("emoji:", "emojis:");
    expect(problemsOf(document)[0]).toContain("document.emojis: is not a field Acervo knows");
  });

  it("keeps a picture's state out of the document, so editing YAML cannot rewrite it", () => {
    // `attempts`, `failureReason` and `suppressed` are facts about what the server did, like
    // `revision` — not things a document can assert. They are carried through a save by the
    // repository's `...existing` spread instead, which is what stops editing a word's YAML from
    // un-suppressing a picture you deleted or zeroing an attempt counter.
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).not.toContain("attempts:");
    expect(document).not.toContain("suppressed:");
    expect(document).not.toContain("failureReason:");
    expect(problemsOf(document.replace("styleId:", "suppressed: true\n        styleId:"))[0])
      .toContain("is not a field Acervo knows");
  });

  it("quotes a gloss term that a stricter reader would read as something else", () => {
    /* The gloss line is flow style because it reads better on one line, and a flow collection is
       where plain scalars are most constrained. How constrained depends on the reader: this package
       writes YAML 1.2, where `?` is an indicator only at the start of a token, while PyYAML
       implements 1.1 and refuses it anywhere in a flow scalar. Five of 1,481 real word files were
       unreadable by any Python tool as a result, and half of this repository is Python. */
    const draft = parseArticle(yamlFor(articleFor(testGraph(), "lexemepicar0001")!));
    draft.senses[0].glosses = [{
      lang: "en",
      terms: ["who is calling?", "plain term", "a: b", "trailing space ", "-leading dash", "#hash"]
    }];

    const document = yamlForDraft(draft);
    expect(document).toContain('"who is calling?"');
    expect(document).toContain('"a: b"');
    expect(document).toContain('"trailing space "');
    expect(document).toContain('"-leading dash"');
    expect(document).toContain('"#hash"');
    // Left alone, because nothing reads it as anything else and quotes would only add noise.
    expect(document).toContain("plain term");
    expect(document).not.toContain('"plain term"');

    // And it still means the same thing when read back.
    expect(parseArticle(document).senses[0].glosses[0].terms).toEqual([
      "who is calling?", "plain term", "a: b", "trailing space ", "-leading dash", "#hash"
    ]);
  });

  it("leaves accented and non-Latin terms unquoted, which are the common case", () => {
    const draft = parseArticle(yamlFor(articleFor(testGraph(), "lexemepicar0001")!));
    draft.senses[0].glosses = [{ lang: "en", terms: ["comezón", "l'appétit", "picar (algo)"] }];
    const document = yamlForDraft(draft);
    expect(document).toContain("comezón");
    expect(document).not.toContain('"comezón"');
    expect(parseArticle(document).senses[0].glosses[0].terms)
      .toEqual(["comezón", "l'appétit", "picar (algo)"]);
  });

  it("quotes a topic name the same way, since topics are a flow list too", () => {
    const draft = parseArticle(yamlFor(articleFor(testGraph(), "lexemepicar0001")!));
    draft.topics = ["Food", "What? Where?"];
    expect(yamlForDraft(draft)).toContain('"What? Where?"');
  });

  it("refuses an id that is not an Acervo id", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!)
      .replace("id: sensepicaritch0", "id: sense-2");
    expect(problemsOf(document)[0]).toContain("is not an Acervo id");
  });

  // The document repeats `text:` and `id:` many times; a text search would name the first one.
  it("points at the offending record, not the first one that looks like it", () => {
    const article = articleFor(testGraph(), "lexemepicar0001")!;
    const document = yamlFor(article).replace("origin: subtitle", "origin: overheard");
    try {
      parseArticle(document);
      throw new Error("expected the document to be refused");
    } catch (error) {
      const [problem] = (error as YamlProblems).problems;
      expect(problem.message).toContain("senses[1].examples[0].origin");
      expect(document.split("\n")[problem.line! - 1]).toContain("origin: overheard");
    }
  });

  it("reports a syntax error with its line", () => {
    try {
      parseArticle("language: es\nsenses:\n  - order: 0\n   definition: x\n");
      throw new Error("expected the document to be refused");
    } catch (error) {
      const [problem] = (error as YamlProblems).problems;
      expect(problem.line).toBe(4);
    }
  });
});

describe("the new-entry template", () => {
  // Not "it parses" — a blank template deliberately does not. What matters is that every key it
  // offers is one the reader accepts, so the only complaints are the blanks you came to fill in.
  it("names exactly the fields you have to fill in", () => {
    expect(problemsOf(YAML_TEMPLATE)).toEqual([
      "headword: is required.",
      "senses[0].definition: is required.",
      "senses[0].examples[0].text: is required."
    ]);
  });

  it("renders a generated draft through the same serialiser, ids and all", () => {
    // What the ingest endpoint returns: no lexeme id, because the entry is new, but minted ids on
    // the records that have to reference each other before anything is stored.
    const generated: ArticleDraft = {
      id: null, language: "es", headword: "el garfio", lemma: "garfio", reading: null, ipa: null,
      pos: "noun", gender: "masculine", register: "neutral", dialect: null, emoji: "🪝",
      topics: ["Travel"], status: "inbox", shortGloss: "hook",
      primaryGloss: "hook", emotion: "sharp and piratical",
      notes: ["Not the same as el gancho."],
      senses: [{
        id: "sense0000000091", order: 0, definition: "Gancho de metal curvo.", definitionLang: "es",
        glosses: [{ lang: "en", terms: ["hook"] }], domain: null, emoji: null, images: [],
        examples: [{
          id: "example00000091", text: "El disfraz de pirata viene con un garfio.", textLang: "es",
          translation: "The pirate costume comes with a hook.", translationLang: "en",
          origin: "attestation", sourceAttestationId: "attest000000091", modelId: null,
          videoRef: null, videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null,
          clipRef: null, imageRef: null, emotion: null,
          note: null, matchedForm: "un garfio", matchedTranslationForm: "hook"
        }]
      }],
      attestations: [{
        id: "attest000000091", text: "El disfraz de pirata viene con un garfio.", translation: null,
        sourceUrl: null, sourceTitle: null, sourceKind: "unknown",
        capturedAt: "2026-08-29T12:00:00.000Z", photoRef: null, photoRegion: null
      }],
      images: []
    };
    // The contract that makes review safe: what the model proposed is exactly what a save applies.
    expect(parseArticle(yamlForDraft(generated))).toEqual(generated);
  });

  it("keeps a photo with its sentence, the region on one line, and lets a photo stand without one", () => {
    const region = { words: [[[0.1, 0.2], [0.3, 0.2], [0.3, 0.25]]], sentence: [[[0.05, 0.2], [0.9, 0.2], [0.9, 0.25], [0.05, 0.25]]] } as const;
    const draft = parseArticle(yamlForDraft({
      ...parseArticle(YAML_TEMPLATE.replace('headword: ""', "headword: salida")
        .replace('definition: ""', "definition: Lugar por donde se sale.")
        .replace('terms: [""]', "terms: [exit]")
        .replace('- text: ""', "- text: La salida está al fondo.")),
      attestations: [
        { id: null, text: "La salida está al fondo.", translation: null, sourceUrl: null, sourceTitle: null,
          sourceKind: "book", capturedAt: "2026-09-20T10:00:00.000Z",
          photoRef: "photos/owner0000000001/0123456789abcdef.jpg",
          photoRegion: { words: region.words.map((p) => p.map((q) => [...q] as [number, number])), sentence: region.sentence.map((p) => p.map((q) => [...q] as [number, number])) } },
        { id: null, text: "", translation: null, sourceUrl: null, sourceTitle: null, sourceKind: "sign",
          capturedAt: "2026-09-20T10:00:00.000Z", photoRef: "photos/owner0000000001/fedcba9876543210.jpg", photoRegion: null }
      ]
    }));
    expect(draft.attestations[0].photoRef).toBe("photos/owner0000000001/0123456789abcdef.jpg");
    expect(draft.attestations[0].photoRegion).toEqual(region);
    expect(draft.attestations[1]).toMatchObject({ text: "", sourceKind: "sign", photoRef: "photos/owner0000000001/fedcba9876543210.jpg" });
    const document = yamlForDraft(draft);
    // One line: a few dozen coordinates nobody reads should not bury the sentence above them.
    expect(document).toMatch(/\n {4}photoRegion: \{words: \[\[\[0\.1, 0\.2\].*\]\]\}\n/);
  });

  it("still needs text for an attestation with no photo", () => {
    const document = yamlForDraft({
      ...parseArticle(YAML_TEMPLATE.replace('headword: ""', "headword: salida")
        .replace('definition: ""', "definition: Lugar por donde se sale.")
        .replace('terms: [""]', "terms: [exit]")
        .replace('- text: ""', "- text: La salida está al fondo.")),
      attestations: [{ id: null, text: "", translation: null, sourceUrl: null, sourceTitle: null, sourceKind: "book",
        capturedAt: "2026-09-20T10:00:00.000Z", photoRef: null, photoRegion: null }]
    });
    expect(problemsOf(document).some((message) => message.startsWith("attestations[0].text"))).toBe(true);
  });

  it("parses once filled in, and creates everything it describes", () => {
    const filled = YAML_TEMPLATE
      .replace('headword: ""', 'headword: sobremesa')
      .replace('definition: ""', 'definition: Charla tras la comida.')
      .replace('terms: [""]', 'terms: [after-dinner talk]')
      .replace('- text: ""', '- text: La sobremesa duró dos horas.')
      .replace('translation: ""', 'translation: The after-dinner talk lasted two hours.');
    const draft = parseArticle(filled);
    expect(draft.id).toBeNull();
    expect(draft.headword).toBe("sobremesa");
    // Left empty in the template, and the only default in the format.
    expect(draft.lemma).toBe("sobremesa");
    expect(draft.senses[0].id).toBeNull();
    expect(draft.senses[0].examples[0].id).toBeNull();
    expect(draft.senses[0].examples[0].textLang).toBe("es");
  });
});

describe("the loop line a word carries", () => {
  it("writes both fields, and reads them back unchanged", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain("primaryGloss: to sting");
    expect(document).toContain("emotion: wincing slightly, as if something just bit you");
    const draft = parseArticle(document);
    expect(draft.primaryGloss).toBe("to sting");
    expect(draft.emotion).toBe("wincing slightly, as if something just bit you");
    // Stable across a round trip: the key order is fixed, so re-serialising changes neither line.
    const again = yamlForDraft(draft);
    expect(again).toContain("primaryGloss: to sting");
    expect(again).toContain("emotion: wincing slightly, as if something just bit you");
    expect(parseArticle(again)).toEqual(draft);
  });

  it("keeps them separate from shortGloss, which may carry several meanings", () => {
    const draft = parseArticle(yamlFor(articleFor(testGraph(), "lexemepicar0001")!));
    expect(draft.shortGloss).toBe("to itch; to chop");
    expect(draft.primaryGloss).toBe("to sting");
  });

  it("treats a word without one as an ordinary word", () => {
    const draft = parseArticle(yamlFor(articleFor(testGraph(), "lexemeespolv001")!));
    expect(draft.primaryGloss).toBeNull();
    expect(draft.emotion).toBeNull();
  });

  it("offers both in the new-entry template, as nulls", () => {
    expect(YAML_TEMPLATE).toContain("primaryGloss: null");
    expect(YAML_TEMPLATE).toContain("emotion: null");
    // The template's own test asserts which blanks it leaves; neither of these is one of them.
    expect(problemsOf(YAML_TEMPLATE).join(" ")).not.toContain("primaryGloss");
    expect(problemsOf(YAML_TEMPLATE).join(" ")).not.toContain("emotion");
    const draft = parseArticle(YAML_TEMPLATE
      .replace('headword: ""', "headword: asco")
      .replace('definition: ""', "definition: Repulsion.")
      .replace('- text: ""', "- text: Qué asco."));
    expect(draft.primaryGloss).toBeNull();
    expect(draft.emotion).toBeNull();
  });
});
