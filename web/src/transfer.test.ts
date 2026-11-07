import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import { SCHEMA_VERSION } from "./api";
import type { VocabularyGraph } from "./domain";
import { MemoryDatabase } from "./localDatabase";
import { LocalAcervoRepository } from "./repository";
import { articleFor, lexemesIn } from "./selectors";
import { testGraph, TEST_OWNER } from "./testGraph";
import { fakeRemote } from "./testRemote";
import {
  BUNDLE_FORMAT, bundleName, exportBundle, importBundle, MANIFEST_FILE, picturesIn, pronunciationsIn,
  readBundle, remintIds, slugFor, TOPICS_FILE, VOCABULARIES_FILE, type BundleFile, type ExportOptions
} from "./transfer";
import { imagePromptId } from "./ids";
import { draftFor, parseArticle } from "./yaml";

const AT = "2026-09-01T12:00:00.000Z";
const everything: ExportOptions = { language: "all", markdown: true, images: false, pronunciations: false };

const bundle = (graph = testGraph(), options: ExportOptions = everything) => exportBundle(graph, options, AT);
const at = (files: BundleFile[], path: string) => files.find((file) => file.path === path)!;

async function emptyReplica() {
  const repository = new LocalAcervoRepository(new MemoryDatabase());
  await repository.load(TEST_OWNER);
  repository.attachRemote(fakeRemote());
  return repository;
}

describe("exporting a bundle", () => {
  it("lays the files out by language, with the shared records at the root", () => {
    const paths = bundle().map((file) => file.path);
    expect(paths.slice(0, 3)).toEqual([MANIFEST_FILE, VOCABULARIES_FILE, TOPICS_FILE]);
    expect(paths).toContain("es/picar.yaml");
    expect(paths).toContain("en/turmoil.yaml");
    expect(paths).toContain("markdown/Spanish vocab - Food.md");
  });

  it("carries no loop, in any file", () => {
    // A loop is a rendering of words the bundle already carries, from a seed the record names — so
    // it is reproducible, and megabytes of it is not what a text archive is for. The fixture has
    // two loops and two items; none of them may appear anywhere.
    const files = bundle();
    expect(testGraph().loops.length).toBeGreaterThan(0);
    files.forEach((file) => {
      expect(file.path).not.toContain("loop");
      if (typeof file.text === "string") {
        expect(file.text).not.toContain("loopmorning0001");
        expect(file.text).not.toContain("bedFingerprint");
      }
    });
  });

  it("carries a manifest that says what it is, and nothing about the account", () => {
    const manifest = parse(at(bundle(), MANIFEST_FILE).text) as Record<string, unknown>;
    expect(manifest).toEqual({
      format: BUNDLE_FORMAT,
      schemaVersion: SCHEMA_VERSION,
      exportedAt: AT,
      languages: ["es", "en"],
      counts: { vocabularies: 2, topics: 2, lexemes: 4 }
    });
    const text = bundle().map((file) => file.text).join("\n");
    expect(text).not.toContain(TEST_OWNER);
    expect(text).not.toContain("dataset");
  });

  it("writes the vocabulary and topic records the article documents cannot express", () => {
    expect(parse(at(bundle(), VOCABULARIES_FILE).text)).toEqual([
      { language: "es", definitionLang: "es", glossLangs: ["en"], notesLang: "en", displayName: null, flag: null, region: null, level: null, learnerNote: null, order: 0 },
      { language: "en", definitionLang: "en", glossLangs: ["ru"], notesLang: "ru", displayName: null, flag: null, region: null, level: null, learnerNote: null, order: 1 }
    ]);
    expect(parse(at(bundle(), TOPICS_FILE).text)).toEqual([
      { name: "Food", icon: "🍽️", order: 0 },
      { name: "Travel", icon: "🧭", order: 1 }
    ]);
  });

  it("strips every id but the ones the file itself points at", () => {
    /* eslint-disable @typescript-eslint/no-explicit-any */
    const word = parse(at(bundle(), "es/picar.yaml").text) as any;
    expect(word.id).toBeUndefined();
    expect(word.senses[0].id).toBeUndefined();
    expect(word.senses[0].imagePrompts[0].id).toBeUndefined();
    // Kept, because something in this same document names them: an example names the attestation it
    // was drawn from, and a picture names the example whose scene it draws. Drop either and the
    // lineage is gone. `remintIds` re-mints both on import, so the bundle depends on no account.
    expect(word.attestations[0].id).toBe("attestpicar0010");
    expect(word.senses[0].examples[0].sourceAttestationId).toBe("attestpicar0010");
    expect(word.senses[0].examples[0].id).toBe("examplepicar010");
  });

  it("names a picture after the word file it belongs to, and carries no bytes by default", () => {
    // `readBundle` never looks at `media/`: a picture is not a graph record, so it does not come
    // in through the document reader. The bytes are `TransferPanel`'s business, and putting one
    // back is the route that attaches one by hand — this module names the pictures and takes a
    // callback, because it holds no transport and should not grow one.
    expect(bundle().map((file) => file.path).some((path) => path.startsWith("media/"))).toBe(false);
    expect(picturesIn(testGraph(), { language: "es", markdown: false, images: true, pronunciations: false })).toEqual([
      { path: "media/es/picar-1.webp", reference: "images/lexemepicar0001/imagepicar00010.webp" }
    ]);
  });

  it("leaves the server's path behind but carries the model that drew the picture", () => {
    /* eslint-disable @typescript-eslint/no-explicit-any */
    const word = parse(at(bundle(), "es/picar.yaml").text) as any;
    // `imageRef` is a path on the server, embedding a lexeme id that will not exist after import —
    // keeping it imports a live-looking reference to a file nobody has.
    expect(word.senses[0].imagePrompts[0].imageRef).toBeUndefined();
    // `imageModelId` is not a path. It is the name of the model that drew this picture, which is a
    // fact about the past exactly as an example's `origin` and `modelId` are, and it is what lets a
    // restored picture keep its provenance instead of reading as one the owner attached.
    expect(word.senses[0].imagePrompts[0].imageModelId).toBe("demo-painter");
  });

  it("leaves photos behind: a server path the bundle does not carry, and a sign with nothing else to say", () => {
    const graph = testGraph();
    const kept = graph.attestations[0];
    graph.attestations = [
      { ...kept, photoRef: "photos/owner0000000001/0123456789abcdef.jpg", photoRegion: { words: [], sentence: [] } },
      { ...kept, id: "attestsign00001", text: "", photoRef: "photos/owner0000000001/fedcba9876543210.jpg", photoRegion: null }
    ];
    const document = at(bundle(graph), "es/picar.yaml").text;
    expect(document).not.toContain("photo");
    expect(parseArticle(document).attestations.map((one) => one.text)).toEqual([kept.text]);
  });

  it("says what an id-less document means in its own header", () => {
    expect(at(bundle(), "es/picar.yaml").text)
      .toContain("# No ids here: everything in this document is created when you save.");
  });

  it("leaves study state out — it is review history, not vocabulary", () => {
    expect(at(bundle(), "es/picar.yaml").text).not.toContain("study ·");
  });

  it("exports one language on its own, for handing to someone else", () => {
    const paths = bundle(testGraph(), { language: "es", markdown: true, images: false, pronunciations: false }).map((file) => file.path);
    expect(paths).toContain("es/picar.yaml");
    expect(paths.some((path) => path.startsWith("en/"))).toBe(false);
    expect(parse(at(bundle(testGraph(), { language: "es", markdown: true, images: false, pronunciations: false }), VOCABULARIES_FILE).text))
      .toHaveLength(1);
  });

  it("omits the markdown when it is not wanted", () => {
    const paths = bundle(testGraph(), { language: "all", markdown: false, images: false, pronunciations: false }).map((file) => file.path);
    expect(paths.some((path) => path.startsWith("markdown/"))).toBe(false);
  });

  it("names the file after what is in it", () => {
    expect(bundleName("all", AT)).toBe("acervo-all-2026-09-01.zip");
    expect(bundleName("es", AT)).toBe("acervo-es-2026-09-01.zip");
  });
});

describe("naming a word file", () => {
  const word = (lemma: string, reading: string | null = null) =>
    slugFor({ headword: lemma, lemma, reading });

  it("strips accents and spaces rather than leaving them in a filename", () => {
    expect(word("ponerse malo")).toBe("ponerse-malo");
    expect(word("desmayarse")).toBe("desmayarse");
    expect(word("niño")).toBe("nino");
    expect(word("¿qué tal?")).toBe("que-tal");
  });

  it("uses the lemma, so the article does not file half a vocabulary under la-", () => {
    expect(slugFor({ headword: "la balsa", lemma: "balsa", reading: null })).toBe("balsa");
  });

  it("transliterates Cyrillic", () => {
    expect(word("суматоха")).toBe("sumatokha");
    expect(word("ёжик")).toBe("ezhik");
  });

  it("falls back to the reading for a script with no Latin form", () => {
    expect(word("麻烦", "máfan")).toBe("mafan");
    expect(word("麻烦")).toBe("word");
  });

  it("separates two words that would share a name", () => {
    const graph = testGraph();
    graph.lexemes[1] = { ...graph.lexemes[1], headword: "picár", lemma: "picár" };
    const paths = exportBundle(graph, everything, AT).map((file) => file.path);
    expect(paths).toContain("es/picar.yaml");
    expect(paths).toContain("es/picar-2.yaml");
  });
});

describe("reading a bundle", () => {
  it("reads back everything it wrote", () => {
    const plan = readBundle(bundle());
    expect(plan.problems).toEqual([]);
    expect(plan.vocabularies).toHaveLength(2);
    expect(plan.topics).toHaveLength(2);
    expect(plan.articles.map((article) => article.path))
      .toEqual(["en/turmoil.yaml", "es/balsa.yaml", "es/espolvorear.yaml", "es/picar.yaml"]);
  });

  it("accepts a single word document on its own", () => {
    const plan = readBundle([at(bundle(), "es/picar.yaml")]);
    expect(plan.articles).toHaveLength(1);
    expect(plan.articles[0].draft.headword).toBe("picar");
  });

  it("looks through the folder a re-zipped export is wrapped in", () => {
    const wrapped = bundle().map((file) => ({ ...file, path: `acervo-2026-09-01/${file.path}` }));
    expect(readBundle(wrapped).articles).toHaveLength(4);
  });

  it("reports a broken word file by name and keeps the rest", () => {
    const files = bundle().map((file) =>
      file.path === "es/picar.yaml" ? { ...file, text: "headword: picar\nsenses: []\n" } : file);
    const plan = readBundle(files);
    expect(plan.articles.map((article) => article.path)).not.toContain("es/picar.yaml");
    expect(plan.problems).toHaveLength(1);
    expect(plan.problems[0].path).toBe("es/picar.yaml");
    expect(plan.problems[0].message).toContain("at least one sense");
  });

  it("reads a version 6 bundle, which is the safety net the database rebuild rested on", () => {
    // A real version 6 word file, pinned as text rather than derived from today's writer: examples
    // carry no ids, and a picture has none of version 7's keys. Nothing was renamed and nothing
    // removed, so `upgradeBundle` rewrites no text — it accepts the version and the reader finds
    // the new keys simply absent.
    const older = [
      "language: es",
      "headword: picar",
      "lemma: picar",
      "pos: verb",
      "status: active",
      "shortGloss: to itch",
      "senses:",
      "  - order: 0",
      "    definition: Producir comezón.",
      "    definitionLang: es",
      "    glosses:",
      "      - {lang: en, terms: [to itch]}",
      "    examples:",
      "      - text: Me pica la nariz.",
      "        textLang: es",
      "        origin: llm",
      "    imagePrompts:",
      "      - prompt: A hand hovering near an itchy nose.",
      "        styleId: flat-vector",
      "        seed: 184521",
      "        modelId: demo-prompt",
      "        promptVersion: demo-v1",
      ""
    ].join("\n");

    const files = bundle()
      .filter((file) => !file.path.endsWith(".yaml") || file.path === MANIFEST_FILE
        || file.path === VOCABULARIES_FILE || file.path === TOPICS_FILE)
      .map((file) => file.path === MANIFEST_FILE
        ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 6") }
        : file)
      .concat([{ path: "es/picar.yaml", text: older }]);

    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    const word = plan.articles.find((article) => article.path === "es/picar.yaml")!.draft;
    const image = word.senses.flatMap((sense) => sense.images)[0];
    expect(image.prompt).toBe("A hand hovering near an itchy nose.");
    // No anchor is invented for it. A version 6 bundle carries no example ids at all, so matching
    // by position or by text would be a guess — and a wrong anchor puts the picture under the
    // wrong sentence, which is worse than putting it under none.
    expect(image.exampleId).toBeNull();
  });

  it("gives an imported clip the derived id, so the clip search cannot write it twice", () => {
    // Every other id is re-minted at random, which is what stops a bundle depending on the account
    // it came from. A clip's cannot be: it is a function of the sense and the segment, and a random
    // one here would let enrichment add a second row for the same pair with nothing failing.
    const word = draftFor(articleFor(testGraph(), "lexemepicar0001")!);
    const reminted = remintIds(word);
    const clip = reminted.senses.flatMap((sense) => sense.examples)
      .find((example) => example.origin === "subtitle")!;
    expect(clip.clipRef).toBe("seg_7c3d18e5b04a92f6de27");
    expect(clip.id).toBeNull();
    // Its neighbours are re-minted as usual.
    const written = reminted.senses.flatMap((sense) => sense.examples)
      .filter((example) => example.origin !== "subtitle");
    expect(written.every((example) => example.id && example.id.length === 15)).toBe(true);
  });

  it("reads a version 7 bundle, whose examples carry none of the clip keys", () => {
    // Version 8 added a clip's channel, its end and the corpus segment it names. A version 7 word
    // file simply does not carry them and `readExample` reads them as absent, so this is another
    // version being *accepted* rather than rewritten — the cheapest form the exception takes.
    const older = [
      "language: es",
      "headword: picar",
      "lemma: picar",
      "pos: verb",
      "status: active",
      "shortGloss: to itch",
      "senses:",
      "  - order: 0",
      "    definition: Producir comezón.",
      "    definitionLang: es",
      "    glosses:",
      "      - {lang: en, terms: [to itch]}",
      "    examples:",
      "      - text: Me pica la nariz.",
      "        textLang: es",
      "        origin: subtitle",
      "        videoRef: https://youtu.be/od_YtGbRC48",
      "        videoTitle: Comiendo en un mercado",
      "        videoStart: 461",
      ""
    ].join("\n");

    const files = bundle()
      .filter((file) => !file.path.endsWith(".yaml") || file.path === MANIFEST_FILE
        || file.path === VOCABULARIES_FILE || file.path === TOPICS_FILE)
      .map((file) => file.path === MANIFEST_FILE
        ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 7") }
        : file)
      .concat([{ path: "es/picar.yaml", text: older }]);

    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    const clip = plan.articles.find((article) => article.path === "es/picar.yaml")!
      .draft.senses[0].examples[0];
    expect(clip.videoTitle).toBe("Comiendo en un mercado");
    expect(clip.videoStart).toBe(461);
    expect(clip.videoChannel).toBeNull();
    expect(clip.videoEnd).toBeNull();
    expect(clip.clipRef).toBeNull();
  });

  it("reads a version 8 bundle, dropping the approval nothing ever set", () => {
    // Version 9 removed an example's `approved` and added an optional emoji to a sense. Every older
    // word file carries the first, which the reader now refuses as unknown, so this is the one step
    // that rewrites text: the line goes. It carried no information, so there is nothing to keep.
    const older = [
      "language: es",
      "headword: picar",
      "lemma: picar",
      "pos: verb",
      "status: active",
      "senses:",
      "  - order: 0",
      "    definition: Producir comezón.",
      "    definitionLang: es",
      "    glosses:",
      "      - {lang: en, terms: [to itch]}",
      "    examples:",
      "      - text: Me pica la nariz.",
      "        textLang: es",
      "        origin: manual",
      "        approved: false",
      ""
    ].join("\n");

    const files = bundle()
      .filter((file) => !file.path.endsWith(".yaml") || file.path === MANIFEST_FILE
        || file.path === VOCABULARIES_FILE || file.path === TOPICS_FILE)
      .map((file) => file.path === MANIFEST_FILE
        ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 8") }
        : file)
      .concat([{ path: "es/picar.yaml", text: older }]);

    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    const sense = plan.articles.find((article) => article.path === "es/picar.yaml")!.draft.senses[0];
    expect(sense.examples[0].text).toBe("Me pica la nariz.");
    expect(sense.emoji).toBeNull();
  });

  it("reads a version 9 bundle, dropping the example audio reference that has become a record", () => {
    const older = [
      "language: es", "headword: picar", "lemma: picar", "pos: verb", "status: active",
      "senses:",
      "  - order: 0",
      "    definition: Producir comezón.",
      "    definitionLang: es",
      "    glosses:",
      "      - {lang: en, terms: [to itch]}",
      "    examples:",
      "      - text: Me pica la nariz.",
      "        textLang: es",
      "        origin: manual",
      "        audioRef: audio/picar.mp3",
      ""
    ].join("\n");

    const files = bundle()
      .filter((file) => !file.path.endsWith(".yaml") || file.path === MANIFEST_FILE
        || file.path === VOCABULARIES_FILE || file.path === TOPICS_FILE)
      .map((file) => file.path === MANIFEST_FILE
        ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 9") }
        : file)
      .concat([{ path: "es/picar.yaml", text: older }]);

    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    const example = plan.articles.find((article) => article.path === "es/picar.yaml")!.draft.senses[0].examples[0];
    expect(example.text).toBe("Me pica la nariz.");
    expect(example.emotion).toBeNull();
  });

  it("reads a bundle from the version before stories were recorded exactly as it stands", () => {
    const files = bundle().map((file) => file.path === MANIFEST_FILE
      ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 14") }
      : file);
    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    expect(plan.articles.length).toBeGreaterThan(0);
  });

  it("carries a vocabulary's level and its learner's note there and back", () => {
    const graph = testGraph();
    const described = { ...graph, vocabularies: graph.vocabularies.map((entry) =>
      entry.language === "es" ? { ...entry, level: "B1" as const, learnerNote: "Off to Argentina." } : entry) };
    const plan = readBundle(bundle(described));
    const spanish = plan.vocabularies.find((entry) => entry.language === "es");
    expect(spanish?.level).toBe("B1");
    expect(spanish?.learnerNote).toBe("Off to Argentina.");
    expect(plan.vocabularies.find((entry) => entry.language === "en")?.level).toBeNull();
  });

  it("reads a bundle from the version before levels exactly as it stands, with none", () => {
    const files = bundle().map((file) => {
      if (file.path === MANIFEST_FILE) {
        return { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 20") };
      }
      return file.path === VOCABULARIES_FILE
        ? { ...file, text: file.text.replace(/^\s*(level|learnerNote):.*\r?\n/gm, "") }
        : file;
    });
    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    expect(plan.vocabularies.every((entry) => entry.level === null && entry.learnerNote === null)).toBe(true);
  });

  it("carries a vocabulary's accent there and back", () => {
    const graph = testGraph();
    const accented = { ...graph, vocabularies: graph.vocabularies.map((entry) =>
      entry.language === "es" ? { ...entry, region: "AR" } : entry) };
    const plan = readBundle(bundle(accented));
    expect(plan.vocabularies.find((entry) => entry.language === "es")?.region).toBe("AR");
    expect(plan.vocabularies.find((entry) => entry.language === "en")?.region).toBeNull();
  });

  it("reads a bundle from the version before accents exactly as it stands, with none", () => {
    const files = bundle().map((file) => {
      if (file.path === MANIFEST_FILE) {
        return { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 19") };
      }
      return file.path === VOCABULARIES_FILE ? { ...file, text: file.text.replace(/^\s*region:.*\r?\n/gm, "") } : file;
    });
    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    expect(plan.vocabularies.every((entry) => entry.region === null)).toBe(true);
  });

  it("reads a word its owner had put away, from the version before one status said so, as set aside", () => {
    const files = bundle().map((file) => {
      if (file.path === MANIFEST_FILE) {
        return { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 21") };
      }
      if (file.path.endsWith("/turmoil.yaml")) return { ...file, text: file.text.replace(/^status: .*$/m, "status: learned") };
      if (file.path.endsWith("/picar.yaml")) return { ...file, text: file.text.replace(/^status: .*$/m, "status: suppressed") };
      return file;
    });
    const plan = readBundle(files);
    expect(plan.problems).toEqual([]);
    const statuses = Object.fromEntries(plan.articles.map((article) => [article.draft.headword, article.draft.status]));
    expect(statuses.turmoil).toBe("aside");
    expect(statuses.picar).toBe("aside");
  });

  it("refuses a bundle from another schema version, naming both", () => {
    const files = bundle().map((file) => file.path === MANIFEST_FILE
      ? { ...file, text: file.text.replace(`schemaVersion: ${SCHEMA_VERSION}`, "schemaVersion: 4") }
      : file);
    expect(() => readBundle(files))
      .toThrow(new RegExp(`schema version 4 .*version ${SCHEMA_VERSION}`));
  });

  it("refuses an unknown layout separately from an unknown record shape", () => {
    const files = bundle().map((file) => file.path === MANIFEST_FILE
      ? { ...file, text: file.text.replace(BUNDLE_FORMAT, "acervo-export/2") }
      : file);
    expect(() => readBundle(files)).toThrow(/acervo-export\/2 layout/);
  });

  it("refuses a file that is not an export at all", () => {
    expect(() => readBundle([{ path: "notes.txt", text: "hello" }])).toThrow(/does not look like/);
  });
});

describe("putting pictures back", () => {
  /* The round trip the export exists for, and the half that was missing: the bundle carried the
     files and the import ignored them, so a restored word showed its brief and "Not drawn yet". */

  const media = () => new Map([
    ["media/es/picar-1.webp", new Uint8Array([1, 2, 3])],
    ["media/es/picar-2.webp", new Uint8Array([4, 5, 6])]
  ]);

  it("hands each picture to the sense it belongs to, with the model that drew it", async () => {
    const repository = await emptyReplica();
    const restored: { senseId: string; bytes: number; drawnBy: string | null }[] = [];

    const report = await importBundle(
      repository, readBundle(bundle()), undefined, undefined, media(),
      async (senseId, bytes, drawnBy) => { restored.push({ senseId, bytes: bytes[0], drawnBy }); }
    );

    expect(report.picturesRestored).toBe(2);
    expect(report.failed).toEqual([]);

    // Matched by position, which is the only pairing a bundle can express: it carries no ids a
    // person or a second account could use. `picar-2.webp` is the second sense of `es/picar.yaml`.
    const graph = repository.snapshot() as VocabularyGraph;
    const picar = lexemesIn(graph, "es").find((lexeme) => lexeme.headword === "picar")!;
    const senses = articleFor(graph, picar.id)!.senses.map((entry) => entry.sense.id);
    expect(restored.map((one) => one.senseId)).toEqual(senses);
    expect(restored.map((one) => one.bytes)).toEqual([1, 4]);
    // Provenance, so a restored picture is not mistaken for one the owner attached.
    expect(restored.map((one) => one.drawnBy)).toEqual(["demo-painter", null]);
  });

  it("writes one row per sense, not one for the document and one for the picture", async () => {
    /* The bug this closes. `saveArticle` minted a random id for an image prompt while everything
       server-side derived one from the sense, so an import produced two rows: an empty frame
       carrying the brief, and a picture carrying none. */
    const repository = await emptyReplica();
    const restored: string[] = [];
    await importBundle(
      repository, readBundle(bundle()), undefined, undefined, media(),
      async (senseId) => { restored.push(senseId); }
    );

    const graph = repository.snapshot() as VocabularyGraph;
    const picar = lexemesIn(graph, "es").find((lexeme) => lexeme.headword === "picar")!;
    const senses = articleFor(graph, picar.id)!.senses;

    // The document's own row is at the id the restore would also compute, so the picture lands on
    // the row that already holds the brief.
    expect(senses[0].images.map((image) => image.id)).toEqual([imagePromptId(senses[0].sense.id)]);
    const forThisWord = graph.imagePrompts.filter(
      (row) => !row.deleted && row.lexemeId === picar.id
    );
    expect(forThisWord).toHaveLength(1);
    expect(restored).toEqual([senses[0].sense.id, senses[1].sense.id]);
  });

  it("asks for enrichment only once the pictures are back, so nothing is drawn over them", async () => {
    const repository = new LocalAcervoRepository(new MemoryDatabase());
    await repository.load(TEST_OWNER);
    const remote = fakeRemote();
    repository.attachRemote(remote);
    const order: string[] = [];

    const report = await importBundle(
      repository, readBundle(bundle()), undefined, undefined, media(),
      async (senseId) => { order.push(`picture ${senseId}`); },
      null,
      async (lexemeId) => { order.push(`enrich ${lexemeId}`); }
    );

    // Every word was saved asking the server not to enrich it on its own.
    const saves = remote.sent.map((changes, index) => ({ changes, options: remote.options[index] }))
      .filter(({ changes }) => changes.lexemes?.length);
    expect(saves).toHaveLength(report.added);
    expect(saves.every(({ options }) => options?.enrich === false)).toBe(true);
    // And asked afterwards, once per word, after that word's pictures.
    const graph = repository.snapshot() as VocabularyGraph;
    const picar = lexemesIn(graph, "es").find((lexeme) => lexeme.headword === "picar")!;
    expect(order.filter((line) => line.startsWith("enrich"))).toHaveLength(report.added);
    const lastPicture = Math.max(...order.map((line, index) => line.startsWith("picture") ? index : -1));
    expect(order.indexOf(`enrich ${picar.id}`)).toBeGreaterThan(lastPicture);
  });

  it("keeps a word whose enrichment could not be asked for", async () => {
    const repository = await emptyReplica();
    const report = await importBundle(
      repository, readBundle(bundle()), undefined, undefined, new Map(), null, null,
      async () => { throw new Error("offline"); }
    );
    expect(report.added).toBe(4);
    expect(report.failed).toEqual([]);
  });

  it("keeps the word when a picture cannot be put back", async () => {
    const repository = await emptyReplica();
    const report = await importBundle(
      repository, readBundle(bundle()), undefined, undefined, media(),
      async () => { throw new Error("the server refused the picture"); }
    );

    // The words are the part that cannot be regenerated; a picture is regenerable by design, so
    // losing the whole import over one refused upload would be the wrong trade.
    expect(report.added).toBe(4);
    expect(report.picturesRestored).toBe(0);
    expect(report.failed.map((problem) => problem.path)).toEqual([
      "media/es/picar-1.webp", "media/es/picar-2.webp"
    ]);
  });

  it("asks for nothing when the bundle carries no pictures", async () => {
    const repository = await emptyReplica();
    const restore = vi.fn(async () => undefined);
    const report = await importBundle(
      repository, readBundle(bundle()), undefined, undefined, new Map(), restore
    );
    expect(restore).not.toHaveBeenCalled();
    expect(report.picturesRestored).toBe(0);
  });

  it("puts nothing back for a word it skipped as already present", async () => {
    // A word you already have is left exactly as it is — pictures included, or an import would
    // overwrite the picture you chose with the one the bundle happened to carry.
    const repository = await emptyReplica();
    await importBundle(repository, readBundle(bundle()));
    const restore = vi.fn(async () => undefined);
    const again = await importBundle(
      repository, readBundle(bundle()), undefined, undefined, media(), restore
    );
    expect(again.skipped).toHaveLength(4);
    expect(restore).not.toHaveBeenCalled();
  });
});

describe("importing a bundle", () => {
  it("restores a whole vocabulary into an empty replica, lineage included", async () => {
    const repository = await emptyReplica();
    const report = await importBundle(repository, readBundle(bundle()));

    expect(report).toMatchObject({ vocabulariesAdded: 2, topicsAdded: 2, added: 4, aborted: false });
    expect(report.failed).toEqual([]);
    expect(report.skipped).toEqual([]);

    const restored = repository.snapshot() as VocabularyGraph;
    expect(lexemesIn(restored, "es").map((lexeme) => lexeme.headword).sort())
      .toEqual(["espolvorear", "la balsa", "picar"]);

    const picar = lexemesIn(restored, "es").find((lexeme) => lexeme.headword === "picar")!;
    const article = articleFor(restored, picar.id)!;
    expect(article.senses.map((entry) => entry.sense.definition))
      .toEqual(["Producir comezón.", "Cortar en trozos pequeños."]);
    expect(article.topics.map((topic) => topic.name)).toEqual(["Food"]);
    expect(article.lexeme.notes).toEqual(["The sense is carried by the object, not the verb."]);

    // The reference survived the round trip and points at this word's own attestation.
    const example = article.senses[0].examples[0];
    expect(example.origin).toBe("attestation");
    expect(example.sourceAttestationId).toBe(article.attestations[0].id);
    expect(article.attestations[0].text).toBe("cuidado que esa salsa pica un monton");

    // Every id is this database's own, not the one the bundle was written from.
    expect(picar.id).not.toBe("lexemepicar0001");
    expect(article.attestations[0].id).not.toBe("attestpicar0010");
  });

  it("files a word the bundle left in the Inbox, and leaves the other statuses alone", async () => {
    // Every bundle that exists was written when a captured word carried `status: inbox`, so
    // honouring the line files a whole vocabulary into a room it has to be emptied out of by hand.
    // Curation the owner did is a different thing and survives.
    const files = bundle().map((file) => file.path.endsWith("/picar.yaml")
      ? { ...file, text: file.text.replace(/^status: .*$/m, "status: inbox") }
      : file.path.endsWith("/turmoil.yaml")
        ? { ...file, text: file.text.replace(/^status: .*$/m, "status: aside") }
        : file);

    const repository = await emptyReplica();
    await importBundle(repository, readBundle(files));

    const restored = repository.snapshot() as VocabularyGraph;
    const statusOf = (headword: string) =>
      restored.lexemes.find((lexeme) => lexeme.headword === headword)!.status;
    expect(statusOf("picar")).toBe("active");
    expect(statusOf("turmoil")).toBe("aside");
    // Filed *into its topics* — the topic line was always read; the status is what hid it.
    const picar = restored.lexemes.find((lexeme) => lexeme.headword === "picar")!;
    expect(articleFor(restored, picar.id)!.topics.map((topic) => topic.name)).toEqual(["Food"]);
  });

  it("skips a word already held rather than overwriting or duplicating it", async () => {
    const repository = await emptyReplica();
    const plan = readBundle(bundle());
    await importBundle(repository, plan);
    const second = await importBundle(repository, readBundle(bundle()));

    expect(second).toMatchObject({ vocabulariesAdded: 0, topicsAdded: 0, added: 0 });
    expect(second.skipped.map((entry) => entry.headword).sort())
      .toEqual(["espolvorear", "la balsa", "picar", "turmoil"]);
    expect(repository.snapshot().lexemes.filter((lexeme) => !lexeme.deleted)).toHaveLength(4);
  });

  it("reports one refused word by file and imports the others", async () => {
    const repository = await emptyReplica();
    const plan = readBundle(bundle());
    // A topic nothing created: `saveArticle` refuses it deliberately, and only that word suffers.
    plan.articles.find((article) => article.path === "es/picar.yaml")!.draft.topics = ["Medicina"];
    const report = await importBundle(repository, plan);

    expect(report.added).toBe(3);
    expect(report.failed).toHaveLength(1);
    expect(report.failed[0].path).toBe("es/picar.yaml");
    expect(report.failed[0].message).toContain("Medicina");
  });

  it("stops at the first word when the server is unreachable, and writes nothing", async () => {
    const repository = await emptyReplica();
    repository.attachRemote(null);
    const report = await importBundle(repository, readBundle(bundle()));

    expect(report.aborted).toBe(true);
    expect(report.added).toBe(0);
    expect(report.vocabulariesAdded).toBe(0);
    expect(repository.snapshot().lexemes).toEqual([]);
  });

  it("stops when it is cancelled", async () => {
    const repository = await emptyReplica();
    const signal = { cancelled: false };
    const report = await importBundle(repository, readBundle(bundle()), (done) => {
      if (done >= 3) signal.cancelled = true;
    }, signal);

    expect(report.aborted).toBe(true);
    expect(report.added).toBe(0);
  });

  it("counts every record it is going to touch as it goes", async () => {
    const repository = await emptyReplica();
    const steps: [number, number][] = [];
    await importBundle(repository, readBundle(bundle()), (done, total) => steps.push([done, total]));
    expect(steps).toHaveLength(8);
    expect(steps.at(-1)).toEqual([8, 8]);
  });
});

describe("re-minting ids", () => {
  it("rewrites a reference to match the attestation it now names", () => {
    const draft = parseArticle(at(bundle(), "es/picar.yaml").text);
    const minted = remintIds(draft);
    expect(minted.id).toBeNull();
    expect(minted.attestations[0].id).not.toBe("attestpicar0010");
    expect(minted.attestations[0].id).toMatch(/^[a-z0-9]{15}$/);
    expect(minted.senses[0].examples[0].sourceAttestationId).toBe(minted.attestations[0].id);
    expect(minted.senses[0].id).toBeNull();
  });

  it("rewrites a picture's anchor to match the example it now names", () => {
    const draft = parseArticle(at(bundle(), "es/picar.yaml").text);
    const minted = remintIds(draft);
    const example = minted.senses[0].examples[0];
    expect(example.id).not.toBe("examplepicar010");
    expect(example.id).toMatch(/^[a-z0-9]{15}$/);
    expect(minted.senses[0].images[0].exampleId).toBe(example.id);
  });

  it("drops a reference that names nothing in the document rather than inventing one", () => {
    const draft = parseArticle(at(bundle(), "es/picar.yaml").text);
    draft.attestations = [];
    draft.senses[0].examples = [];
    const minted = remintIds(draft);
    expect(minted.senses[0].examples).toEqual([]);
    // The picture survives its anchor: a sentence you deleted must not take the drawing with it.
    expect(minted.senses[0].images[0].exampleId).toBeNull();
  });
});

describe("the pronunciations a bundle carries", () => {
  const withClips: ExportOptions = { language: "all", markdown: false, images: false, pronunciations: true };

  it("names each clip after what it reads, beside its word file", () => {
    const { files, clips } = pronunciationsIn(testGraph(), withClips);
    expect(clips.map((clip) => clip.path)).toEqual(["audio/es/picar/headword.mp3"]);
    expect(clips[0].reference).toBe(testGraph().pronunciations[0].audioRef);
    const manifest = parse(at(files, "audio/es/picar/clips.yaml").text) as Record<string, unknown>[];
    expect(manifest[0]).toMatchObject({
      file: "headword.mp3", target: "lexeme", text: "picar", lang: "es",
      providerId: "google-tts", modelId: "wavenet", voice: "es-ES-Wavenet-F"
    });
    // Off, and neither the manifest nor the clips are in the bundle at all.
    expect(bundle(testGraph(), { ...withClips, pronunciations: false }).some((file) => file.path.startsWith("audio/"))).toBe(false);
    expect(bundle(testGraph(), withClips).some((file) => file.path === "audio/es/picar/clips.yaml")).toBe(true);
  });

  it("leaves out a clip of words its record no longer says", () => {
    const graph = testGraph();
    graph.lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.headword = "picarse";
    expect(pronunciationsIn(graph, withClips).clips).toEqual([]);
  });

  it("puts a clip back on the record that says its words, and keeps who recorded it", async () => {
    const repository = await emptyReplica();
    const plan = readBundle(bundle(testGraph(), withClips));
    expect([...plan.clips.keys()]).toEqual(["es/picar.yaml"]);

    const restored: { target: string; id: string; voice: string | null }[] = [];
    const report = await importBundle(
      repository, plan, () => {}, { cancelled: false }, new Map(), null,
      {
        files: new Map([["audio/es/picar/headword.mp3", new Uint8Array([1, 2, 3])]]),
        restore: async (target, id, _bytes, entry) => { restored.push({ target, id, voice: entry.voice }); }
      }
    );

    expect(report.pronunciationsRestored).toBe(1);
    const lexeme = lexemesIn(repository.snapshot(), "es").find((one) => one.headword === "picar")!;
    expect(restored).toEqual([{ target: "lexeme", id: lexeme.id, voice: "es-ES-Wavenet-F" }]);
  });

  it("puts nothing back when the bundle carries no recordings", async () => {
    const repository = await emptyReplica();
    const plan = readBundle(bundle(testGraph(), withClips));
    const report = await importBundle(repository, plan, () => {}, { cancelled: false }, new Map(), null, null);
    expect(report.pronunciationsRestored).toBe(0);
  });
});
