/**
 * The YAML pane is a projection of the record, in the same spirit as the short form: one source,
 * two presentations. Unlike the short form it is also an *input*, so both directions live here and
 * both go through the same library — a hand-written serialiser paired with a parser drifts apart
 * the first time someone adds a field to one of them.
 *
 * The contract the tests hold to: `parseArticle(yamlFor(article))` reproduces the article's
 * editable fields exactly. That is what makes editing safe. A field this file forgets to write is
 * a field the next save deletes.
 *
 * Pure: no storage, no network, no DOM. Generated YAML arrives here from a model on exactly the
 * same footing as YAML someone typed.
 */

import { Document, isMap, isNode, isScalar, isSeq, LineCounter, parseDocument, Scalar } from "yaml";
import {
  EXAMPLE_ORIGINS, GENDERS, LEXEME_STATUSES, PARTS_OF_SPEECH, REGISTERS, SOURCE_KINDS,
  type Example, type ExampleOrigin, type Gender, type Gloss, type ImagePrompt,
  type LexemeStatus, type PartOfSpeech, type PhotoRegion, type Register, type SourceKind, type StudyState
} from "./domain";
import { languageOf } from "./languages";
import type { Article } from "./selectors";

/* ── the draft ──────────────────────────────────────────────────────────
   What a document means, before it is matched against anything stored. Ids are optional
   throughout: an absent id is a record that does not exist yet. Topics are names, because a rail
   label is what someone editing an article can actually see. */

export interface ExampleDraft {
  id: string | null;
  text: string;
  textLang: string;
  translation: string | null;
  translationLang: string | null;
  origin: ExampleOrigin;
  sourceAttestationId: string | null;
  modelId: string | null;
  videoRef: string | null;
  videoTitle: string | null;
  videoChannel: string | null;
  videoStart: number | null;
  videoEnd: number | null;
  clipRef: string | null;
  imageRef: string | null;
  /** How the sentence should sound when read aloud: a short English direction, or null for neutral. */
  emotion: string | null;
  note: string | null;
  matchedForm: string | null;
  matchedTranslationForm: string | null;
}

/**
 * What a document says about a picture, which is deliberately less than the record holds.
 *
 * `attempts`, `failureReason` and `suppressed` are state, like `revision`, and are not in the
 * projection: they are facts about what the server did, not things a document can assert. A save
 * carries them through untouched (`repository.saveArticle`), so editing a word's YAML cannot
 * un-suppress a picture you deleted or zero an attempt counter.
 */
export interface ImagePromptDraft {
  id: string | null;
  /** The example the scene was built from — content, so it travels with the document. */
  exampleId: string | null;
  prompt: string;
  styleId: string;
  seed: number;
  modelId: string;
  promptVersion: string;
  imageRef: string | null;
  imageModelId: string | null;
}

export interface SenseDraft {
  id: string | null;
  order: number;
  definition: string;
  definitionLang: string;
  glosses: Gloss[];
  domain: string | null;
  emoji: string | null;
  examples: ExampleDraft[];
  images: ImagePromptDraft[];
}

export interface AttestationDraft {
  id: string | null;
  /** May be empty only when there is a photo: a street sign has no sentence. */
  text: string;
  translation: string | null;
  sourceUrl: string | null;
  sourceTitle: string | null;
  sourceKind: SourceKind;
  capturedAt: string;
  /** The photo it was met in. Delete the line to let the photo go. */
  photoRef: string | null;
  /** Where on the photo the word and its sentence are: geometry, written on one line. */
  photoRegion: PhotoRegion | null;
}

export interface ArticleDraft {
  id: string | null;
  language: string;
  headword: string;
  lemma: string;
  reading: string | null;
  ipa: string | null;
  pos: PartOfSpeech;
  gender: Gender | null;
  register: Register | null;
  dialect: string | null;
  emoji: string | null;
  topics: string[];
  status: LexemeStatus;
  shortGloss: string | null;
  /** The one term a loop speaks, and how the word itself sounds. Both are usually null. */
  primaryGloss: string | null;
  emotion: string | null;
  notes: string[];
  senses: SenseDraft[];
  attestations: AttestationDraft[];
  images: ImagePromptDraft[];
}

/** Where a problem is, so the panel can say "line 14" instead of "somewhere". */
export interface YamlProblem {
  line: number | null;
  message: string;
}

export class YamlProblems extends Error {
  constructor(readonly problems: YamlProblem[]) {
    super(problems.map((problem) => problem.message).join("\n"));
    this.name = "YamlProblems";
  }
}

/* ── writing ────────────────────────────────────────────────────────────
   Every non-null field is written. Absence therefore means null, which is what makes the round
   trip exact rather than merely careful: there is no field the reader has to guess at. */

type Plain = Record<string, unknown>;

/** Drops nulls and empty lists so a sparse record reads as a short one, not as a wall of nulls. */
function compact(fields: Plain): Plain {
  const kept: Plain = {};
  Object.entries(fields).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (Array.isArray(value) && value.length === 0) return;
    kept[key] = value;
  });
  return kept;
}

function exampleFields(example: ExampleDraft): Plain {
  return compact({
    id: example.id,
    text: example.text,
    textLang: example.textLang,
    translation: example.translation,
    translationLang: example.translationLang,
    origin: example.origin,
    sourceAttestationId: example.sourceAttestationId,
    modelId: example.modelId,
    videoRef: example.videoRef,
    videoTitle: example.videoTitle,
    videoChannel: example.videoChannel,
    videoStart: example.videoStart,
    videoEnd: example.videoEnd,
    clipRef: example.clipRef,
    imageRef: example.imageRef,
    note: example.note,
    matchedForm: example.matchedForm,
    matchedTranslationForm: example.matchedTranslationForm,
    emotion: example.emotion
  });
}

function promptFields(image: ImagePromptDraft): Plain {
  return compact({
    id: image.id,
    exampleId: image.exampleId,
    prompt: image.prompt,
    styleId: image.styleId,
    seed: image.seed,
    modelId: image.modelId,
    promptVersion: image.promptVersion,
    imageRef: image.imageRef,
    imageModelId: image.imageModelId
  });
}

/**
 * A scalar that is safe unquoted inside a flow collection, by the strictest reader rather than the
 * most permissive one.
 *
 * The gloss line is written in flow style — `{lang: en, terms: [to itch]}` — because it reads far
 * better on one line. But a flow collection is where plain scalars are most constrained, and how
 * constrained depends on the reader: the `yaml` package writes and reads YAML 1.2, where `?` is an
 * indicator only at the start of a token, while PyYAML implements 1.1 and refuses it anywhere in a
 * flow scalar. So `terms: [who is calling?, on the line]` round-tripped perfectly through Acervo
 * and could not be read by any Python tool at all — and half of this repository is Python.
 *
 * The rule here is deliberately conservative rather than a transcription of either spec: a term is
 * left plain only when it is letters, digits, spaces and a few marks that no reader treats
 * specially, and quoted otherwise. Over-quoting costs two characters; under-quoting costs a file
 * one reader cannot open, which is the failure that actually happened.
 */
const PLAIN_IN_FLOW = /^[\p{L}\p{N}][\p{L}\p{N} ().'\u2019/–-]*$/u;

function plainInFlow(text: string): boolean {
  return PLAIN_IN_FLOW.test(text) && !text.endsWith(" ");
}

/** Quotes every scalar in a flow sequence that any reader might read as something else. */
function quoteInFlow(node: unknown): void {
  if (!isSeq(node)) return;
  node.items.forEach((item) => {
    if (!isScalar(item) || typeof item.value !== "string") return;
    if (!plainInFlow(item.value)) item.type = Scalar.QUOTE_DOUBLE;
  });
}

/** An instant must survive as the string the validator expects, never as a parsed date. */
function instant(value: string): Scalar {
  const node = new Scalar(value);
  node.type = Scalar.QUOTE_DOUBLE;
  return node;
}

/* Field by field rather than by spread: a draft is only the editable half of a record, and a
   spread would quietly carry ownership and revision into the document. */

function exampleDraft(example: Example): ExampleDraft {
  return {
    id: example.id,
    text: example.text,
    textLang: example.textLang,
    translation: example.translation,
    translationLang: example.translationLang,
    origin: example.origin,
    sourceAttestationId: example.sourceAttestationId,
    modelId: example.modelId,
    videoRef: example.videoRef,
    videoTitle: example.videoTitle,
    videoChannel: example.videoChannel,
    videoStart: example.videoStart,
    videoEnd: example.videoEnd,
    clipRef: example.clipRef,
    imageRef: example.imageRef,
    emotion: example.emotion,
    note: example.note,
    matchedForm: example.matchedForm,
    matchedTranslationForm: example.matchedTranslationForm
  };
}

function promptDraft(image: ImagePrompt): ImagePromptDraft {
  return {
    id: image.id,
    exampleId: image.exampleId,
    prompt: image.prompt,
    styleId: image.styleId,
    seed: image.seed,
    modelId: image.modelId,
    promptVersion: image.promptVersion,
    imageRef: image.imageRef,
    imageModelId: image.imageModelId
  };
}

export function draftFor(article: Article): ArticleDraft {
  const { lexeme, topics, senses, attestations, images } = article;
  return {
    id: lexeme.id,
    language: lexeme.language,
    headword: lexeme.headword,
    lemma: lexeme.lemma,
    reading: lexeme.reading,
    ipa: lexeme.ipa,
    pos: lexeme.pos,
    gender: lexeme.gender,
    register: lexeme.register,
    dialect: lexeme.dialect,
    emoji: lexeme.emoji,
    topics: topics.map((topic) => topic.name),
    status: lexeme.status,
    shortGloss: lexeme.shortGloss,
    primaryGloss: lexeme.primaryGloss,
    emotion: lexeme.emotion,
    notes: [...lexeme.notes],
    senses: senses.map(({ sense, examples, images: senseImages }) => ({
      id: sense.id,
      order: sense.order,
      definition: sense.definition,
      definitionLang: sense.definitionLang,
      glosses: sense.glosses.map((gloss) => ({ lang: gloss.lang, terms: [...gloss.terms] })),
      domain: sense.domain,
      emoji: sense.emoji,
      examples: examples.map(exampleDraft),
      images: senseImages.map(promptDraft)
    })),
    attestations: attestations.map((attestation) => ({
      id: attestation.id,
      text: attestation.text,
      translation: attestation.translation,
      sourceUrl: attestation.sourceUrl,
      sourceTitle: attestation.sourceTitle,
      sourceKind: attestation.sourceKind,
      capturedAt: attestation.capturedAt,
      photoRef: attestation.photoRef,
      photoRegion: attestation.photoRegion
    })),
    images: images.map(promptDraft)
  };
}

export function yamlFor(article: Article): string {
  return yamlForDraft(draftFor(article), article.study);
}

/**
 * The same document, from a draft that may never have been stored.
 *
 * Generation produces a draft directly, and it must reach the review surface through this
 * serialiser rather than a second one — a hand-written writer for generated articles would drift
 * from the reader the moment a field is added, which is the failure this file exists to prevent.
 */
export function yamlForDraft(draft: ArticleDraft, study: StudyState | null = null): string {
  const document = new Document(compact({
    id: draft.id,
    language: draft.language,
    headword: draft.headword,
    lemma: draft.lemma,
    reading: draft.reading,
    ipa: draft.ipa,
    pos: draft.pos,
    gender: draft.gender,
    register: draft.register,
    dialect: draft.dialect,
    emoji: draft.emoji,
    status: draft.status,
    topics: draft.topics,
    shortGloss: draft.shortGloss,
    primaryGloss: draft.primaryGloss,
    emotion: draft.emotion,
    notes: draft.notes,
    senses: draft.senses.map((sense) => compact({
      id: sense.id,
      order: sense.order,
      definition: sense.definition,
      definitionLang: sense.definitionLang,
      domain: sense.domain,
      emoji: sense.emoji,
      glosses: sense.glosses.map((gloss) => ({ lang: gloss.lang, terms: gloss.terms })),
      examples: sense.examples.map(exampleFields),
      imagePrompts: sense.images.map(promptFields)
    })),
    attestations: draft.attestations.map((attestation) => compact({
      id: attestation.id,
      text: attestation.text,
      translation: attestation.translation,
      sourceKind: attestation.sourceKind,
      sourceTitle: attestation.sourceTitle,
      sourceUrl: attestation.sourceUrl,
      capturedAt: instant(attestation.capturedAt),
      photoRef: attestation.photoRef,
      // Only beside the photo it describes: a region with no photo is refused on save.
      photoRegion: attestation.photoRef ? attestation.photoRegion : null
    })),
    imagePrompts: draft.images.map(promptFields)
  }));

  // What the ids mean depends on whether the document names a stored entry. An edit keeps them; a
  // document that names nothing — an exported file — has none to keep, and telling its reader to
  // preserve ids it does not carry is worse than saying nothing. A composed word under review is
  // the third case: not stored, but its senses and examples already carry the ids the server minted
  // for them, which a chat edit addresses. Telling that document's reader "no ids here" over four
  // ids is a contradiction a model reads literally. Told apart by the sense ids, which an export
  // strips (`transfer.ts`, `stripIds`) and a composed word carries.
  const named = draft.senses.some((sense) => sense.id);
  document.commentBefore = ` ${draft.headword} — ${languageOf(draft.language).name}\n `
    + (draft.id
      ? "Every record keeps its id. Delete a block to remove it; omit an id to add something new."
      : named
        ? "Not saved yet. Every record keeps its id; omit an id to add something new."
        : "No ids here: everything in this document is created when you save.");

  // Study state flows in from the scheduler and is never edited here (`docs/features/anki.md`), so
  // it is written as comments: visible where you would look for it, and impossible to save back by
  // accident.
  const notes = study
    ? [
      "",
      ` study · ${study.system} · reps ${study.reps} · lapses ${study.lapses}`,
      ` stability ${study.stability} · difficulty ${study.difficulty} · retrievability ${study.retrievability}`,
      ` last review ${study.lastReview ?? "never"} — read-only, reported by the scheduler`
    ].join("\n")
    : null;
  if (notes) document.comment = notes;

  // Flow style for the small pairs, which are far more readable on one line than as four.
  const senses = document.get("senses", true);
  if (isSeq(senses)) {
    senses.items.forEach((sense) => {
      if (!isMap(sense)) return;
      const glosses = sense.get("glosses", true);
      if (isSeq(glosses)) glosses.items.forEach((gloss) => {
        if (!isMap(gloss)) return;
        gloss.flow = true;
        quoteInFlow(gloss.get("terms", true));
      });
    });
  }
  const topicsNode = document.get("topics", true);
  if (isSeq(topicsNode)) {
    topicsNode.flow = true;
    quoteInFlow(topicsNode);
  }
  // A photo region is a few dozen coordinates nobody reads: one line, so it does not bury the text.
  const attestationsNode = document.get("attestations", true);
  if (isSeq(attestationsNode)) attestationsNode.items.forEach((attestation) => {
    if (!isMap(attestation)) return;
    const region = attestation.get("photoRegion", true);
    if (isMap(region)) region.flow = true;
  });

  return document.toString({ lineWidth: 0, singleQuote: false, flowCollectionPadding: false });
}

/* ── reading ────────────────────────────────────────────────────────────
   Every message names the field and, where the parser gives one, the line. A save is refused as a
   whole: half an applied article is worse than none, which is the same rule the write route uses. */

/** `senses[0].examples[1].text` → `["senses", 0, "examples", 1, "text"]`. */
function pathSteps(path: string): (string | number)[] {
  return path
    .replace(/^document\.?/, "")
    .split(".")
    .filter(Boolean)
    .flatMap((part) => {
      const [name, ...indices] = part.split("[");
      return [name, ...indices.map((index) => Number(index.replace("]", "")))];
    });
}

function readPhotoRegion(reader: Reader, value: unknown, path: string): PhotoRegion | null {
  const region = reader.map(value, path);
  if (!region) return null;
  const polygons = (key: "words" | "sentence"): [number, number][][] => reader.list(region[key], `${path}.${key}`)
    .flatMap((polygon, index) => {
      const points = reader.list(polygon, `${path}.${key}[${index}]`);
      const valid = points.length >= 3 && points.every((point) =>
        Array.isArray(point) && point.length === 2
        && point.every((axis) => typeof axis === "number" && axis >= 0 && axis <= 1));
      if (!valid) {
        reader.fail(`${path}.${key}[${index}]`, "expected a polygon of [x, y] points between 0 and 1.");
        return [];
      }
      return [points as [number, number][]];
    });
  return { words: polygons("words"), sentence: polygons("sentence") };
}

class Reader {
  readonly problems: YamlProblem[] = [];

  constructor(
    private readonly document: Document.Parsed,
    private readonly lines: LineCounter
  ) {}

  /**
   * Asked of the parsed tree rather than matched against the text, because a document has many
   * lines reading `text:` and pointing at the wrong one is worse than pointing at none. Walks up
   * the path until something exists, so a complaint about a field that is missing entirely still
   * lands on the record it is missing from.
   */
  private lineOf(path: string): number | null {
    const steps = pathSteps(path);
    for (let depth = steps.length; depth > 0; depth -= 1) {
      const node: unknown = this.document.getIn(steps.slice(0, depth), true);
      const offset = isNode(node) ? node.range?.[0] : undefined;
      if (offset !== undefined) return this.lines.linePos(offset).line;
    }
    return null;
  }

  fail(path: string, message: string): void {
    this.problems.push({ line: this.lineOf(path), message: `${path}: ${message}` });
  }

  map(value: unknown, path: string): Plain | null {
    if (value === null || value === undefined) return null;
    if (typeof value !== "object" || Array.isArray(value)) {
      this.fail(path, "expected a block of fields.");
      return null;
    }
    return value as Plain;
  }

  list(value: unknown, path: string): unknown[] {
    if (value === null || value === undefined) return [];
    if (!Array.isArray(value)) { this.fail(path, "expected a list."); return []; }
    return value;
  }

  text(value: unknown, path: string, fallback = ""): string {
    if (value === null || value === undefined) return fallback;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (typeof value !== "string") { this.fail(path, "expected text."); return fallback; }
    return value;
  }

  required(value: unknown, path: string): string {
    const text = this.text(value, path);
    if (!text.trim()) this.fail(path, "is required.");
    return text;
  }

  optional(value: unknown, path: string): string | null {
    if (value === null || value === undefined) return null;
    const text = this.text(value, path);
    return text.trim() ? text : null;
  }

  id(value: unknown, path: string): string | null {
    const text = this.optional(value, path);
    if (text === null) return null;
    if (!/^[a-z0-9]{15}$/.test(text)) {
      this.fail(path, "is not an Acervo id. Remove the line to create a new record instead.");
      return null;
    }
    return text;
  }

  number(value: unknown, path: string, fallback: number): number {
    if (value === null || value === undefined) return fallback;
    if (typeof value !== "number" || !Number.isFinite(value)) {
      this.fail(path, "expected a number.");
      return fallback;
    }
    return value;
  }

  optionalNumber(value: unknown, path: string): number | null {
    if (value === null || value === undefined) return null;
    return this.number(value, path, 0);
  }

  boolean(value: unknown, path: string, fallback: boolean): boolean {
    if (value === null || value === undefined) return fallback;
    if (typeof value !== "boolean") { this.fail(path, "expected true or false."); return fallback; }
    return value;
  }

  choice<T extends string>(value: unknown, path: string, allowed: readonly T[], fallback: T): T {
    const text = this.text(value, path);
    if (!text.trim()) return fallback;
    if (!allowed.includes(text as T)) {
      this.fail(path, `must be one of ${allowed.join(", ")} — found "${text}".`);
      return fallback;
    }
    return text as T;
  }

  optionalChoice<T extends string>(value: unknown, path: string, allowed: readonly T[]): T | null {
    if (value === null || value === undefined) return null;
    const text = this.text(value, path);
    if (!text.trim()) return null;
    if (!allowed.includes(text as T)) {
      this.fail(path, `must be one of ${allowed.join(", ")} — found "${text}".`);
      return null;
    }
    return text as T;
  }

  strings(value: unknown, path: string): string[] {
    return this.list(value, path)
      .map((item, index) => this.text(item, `${path}[${index}]`))
      .filter((item) => item.trim().length > 0);
  }

  /** Unknown keys are refused rather than ignored: a typo that silently does nothing is worse. */
  keys(fields: Plain, path: string, allowed: string[]): void {
    Object.keys(fields).forEach((key) => {
      if (!allowed.includes(key)) {
        this.fail(`${path}.${key}`, `is not a field Acervo knows. Expected one of ${allowed.join(", ")}.`);
      }
    });
  }
}

export const EXAMPLE_KEYS = [
  "id", "text", "textLang", "translation", "translationLang", "origin", "sourceAttestationId",
  "modelId", "videoRef", "videoTitle", "videoChannel", "videoStart", "videoEnd", "clipRef",
  "imageRef", "emotion", "note", "matchedForm", "matchedTranslationForm"
];
export const PROMPT_KEYS = [
  "id", "exampleId", "prompt", "styleId", "seed", "modelId", "promptVersion", "imageRef",
  "imageModelId"
];
export const SENSE_KEYS = [
  "id", "order", "definition", "definitionLang", "domain", "emoji", "glosses", "examples", "imagePrompts"
];
export const ATTESTATION_KEYS = [
  "id", "text", "translation", "sourceKind", "sourceTitle", "sourceUrl", "capturedAt", "photoRef",
  "photoRegion"
];
export const ARTICLE_KEYS = [
  "id", "language", "headword", "lemma", "reading", "ipa", "pos", "gender", "register", "dialect",
  "emoji", "status", "topics", "shortGloss", "primaryGloss", "emotion", "notes", "senses",
  "attestations", "imagePrompts"
];

function readExample(reader: Reader, raw: unknown, path: string, textLang: string): ExampleDraft | null {
  const fields = reader.map(raw, path);
  if (!fields) return null;
  reader.keys(fields, path, EXAMPLE_KEYS);
  return {
    id: reader.id(fields.id, `${path}.id`),
    text: reader.required(fields.text, `${path}.text`),
    // An example is in the article's language unless it says otherwise, which is the only default
    // in the format — and it is safe because writing always states it.
    textLang: reader.text(fields.textLang, `${path}.textLang`, textLang) || textLang,
    translation: reader.optional(fields.translation, `${path}.translation`),
    translationLang: reader.optional(fields.translationLang, `${path}.translationLang`),
    origin: reader.choice(fields.origin, `${path}.origin`, EXAMPLE_ORIGINS, "manual"),
    sourceAttestationId: reader.id(fields.sourceAttestationId, `${path}.sourceAttestationId`),
    modelId: reader.optional(fields.modelId, `${path}.modelId`),
    videoRef: reader.optional(fields.videoRef, `${path}.videoRef`),
    videoTitle: reader.optional(fields.videoTitle, `${path}.videoTitle`),
    videoChannel: reader.optional(fields.videoChannel, `${path}.videoChannel`),
    videoStart: reader.optionalNumber(fields.videoStart, `${path}.videoStart`),
    videoEnd: reader.optionalNumber(fields.videoEnd, `${path}.videoEnd`),
    clipRef: reader.optional(fields.clipRef, `${path}.clipRef`),
    imageRef: reader.optional(fields.imageRef, `${path}.imageRef`),
    emotion: reader.optional(fields.emotion, `${path}.emotion`),
    note: reader.optional(fields.note, `${path}.note`),
    matchedForm: reader.optional(fields.matchedForm, `${path}.matchedForm`),
    matchedTranslationForm: reader.optional(fields.matchedTranslationForm, `${path}.matchedTranslationForm`)
  };
}

function readPrompt(reader: Reader, raw: unknown, path: string): ImagePromptDraft | null {
  const fields = reader.map(raw, path);
  if (!fields) return null;
  reader.keys(fields, path, PROMPT_KEYS);
  return {
    id: reader.id(fields.id, `${path}.id`),
    exampleId: reader.id(fields.exampleId, `${path}.exampleId`),
    // Not `required` any more, and both for the same reason: a picture the owner attached has no
    // brief and no style, because no writer produced it.
    prompt: reader.text(fields.prompt, `${path}.prompt`),
    styleId: reader.text(fields.styleId, `${path}.styleId`),
    seed: reader.number(fields.seed, `${path}.seed`, 0),
    modelId: reader.text(fields.modelId, `${path}.modelId`),
    promptVersion: reader.text(fields.promptVersion, `${path}.promptVersion`),
    imageRef: reader.optional(fields.imageRef, `${path}.imageRef`),
    imageModelId: reader.optional(fields.imageModelId, `${path}.imageModelId`)
  };
}

function readGlosses(reader: Reader, raw: unknown, path: string): Gloss[] {
  return reader.list(raw, path).flatMap((item, index) => {
    const where = `${path}[${index}]`;
    const fields = reader.map(item, where);
    if (!fields) return [];
    reader.keys(fields, where, ["lang", "terms"]);
    return [{
      lang: reader.required(fields.lang, `${where}.lang`),
      terms: reader.strings(fields.terms, `${where}.terms`)
    }];
  });
}

/**
 * Reads a document into a draft. Throws `YamlProblems` carrying every problem found, not only the
 * first: someone correcting a hand-written article should see the whole list in one pass.
 */
export function parseArticle(text: string): ArticleDraft {
  const lineCounter = new LineCounter();
  const document = parseDocument(text, { prettyErrors: true, lineCounter });
  const syntax: YamlProblem[] = document.errors.map((error) => ({
    line: error.linePos?.[0]?.line ?? null,
    message: error.message
  }));
  if (syntax.length) throw new YamlProblems(syntax);

  const reader = new Reader(document, lineCounter);
  const root = document.toJS({ maxAliasCount: 100 }) as unknown;
  const fields = reader.map(root, "document");
  if (!fields) throw new YamlProblems(reader.problems.length ? reader.problems : [
    { line: null, message: "The document is empty." }
  ]);
  reader.keys(fields, "document", ARTICLE_KEYS);

  const language = reader.required(fields.language, "language");
  const draft: ArticleDraft = {
    id: reader.id(fields.id, "id"),
    language,
    headword: reader.required(fields.headword, "headword"),
    // Lemma defaults to the headword, which is what it is for every word that is not inflected.
    lemma: reader.text(fields.lemma, "lemma") || reader.text(fields.headword, "headword"),
    reading: reader.optional(fields.reading, "reading"),
    ipa: reader.optional(fields.ipa, "ipa"),
    pos: reader.choice(fields.pos, "pos", PARTS_OF_SPEECH, "noun"),
    gender: reader.optionalChoice(fields.gender, "gender", GENDERS),
    register: reader.optionalChoice(fields.register, "register", REGISTERS),
    dialect: reader.optional(fields.dialect, "dialect"),
    emoji: reader.optional(fields.emoji, "emoji"),
    topics: reader.strings(fields.topics, "topics"),
    // A document someone typed or reviewed is an ordinary word; the Inbox holds what arrived unread.
    status: reader.choice(fields.status, "status", LEXEME_STATUSES, "active"),
    shortGloss: reader.optional(fields.shortGloss, "shortGloss"),
    primaryGloss: reader.optional(fields.primaryGloss, "primaryGloss"),
    emotion: reader.optional(fields.emotion, "emotion"),
    notes: reader.strings(fields.notes, "notes"),
    senses: reader.list(fields.senses, "senses").flatMap((item, index) => {
      const where = `senses[${index}]`;
      const sense = reader.map(item, where);
      if (!sense) return [];
      reader.keys(sense, where, SENSE_KEYS);
      return [{
        id: reader.id(sense.id, `${where}.id`),
        order: reader.number(sense.order, `${where}.order`, index),
        definition: reader.required(sense.definition, `${where}.definition`),
        definitionLang: reader.text(sense.definitionLang, `${where}.definitionLang`, language) || language,
        glosses: readGlosses(reader, sense.glosses, `${where}.glosses`),
        domain: reader.optional(sense.domain, `${where}.domain`),
        emoji: reader.optional(sense.emoji, `${where}.emoji`),
        examples: reader.list(sense.examples, `${where}.examples`)
          .map((example, position) => readExample(reader, example, `${where}.examples[${position}]`, language))
          .filter((example): example is ExampleDraft => example !== null),
        images: reader.list(sense.imagePrompts, `${where}.imagePrompts`)
          .map((image, position) => readPrompt(reader, image, `${where}.imagePrompts[${position}]`))
          .filter((image): image is ImagePromptDraft => image !== null)
      }];
    }),
    attestations: reader.list(fields.attestations, "attestations").flatMap((item, index) => {
      const where = `attestations[${index}]`;
      const attestation = reader.map(item, where);
      if (!attestation) return [];
      reader.keys(attestation, where, ATTESTATION_KEYS);
      const photoRef = reader.optional(attestation.photoRef, `${where}.photoRef`);
      return [{
        id: reader.id(attestation.id, `${where}.id`),
        // A photo is a place the word was met, with or without a sentence to go with it.
        text: photoRef
          ? reader.text(attestation.text, `${where}.text`)
          : reader.required(attestation.text, `${where}.text`),
        translation: reader.optional(attestation.translation, `${where}.translation`),
        sourceUrl: reader.optional(attestation.sourceUrl, `${where}.sourceUrl`),
        sourceTitle: reader.optional(attestation.sourceTitle, `${where}.sourceTitle`),
        sourceKind: reader.choice(attestation.sourceKind, `${where}.sourceKind`, SOURCE_KINDS, "unknown"),
        capturedAt: reader.text(attestation.capturedAt, `${where}.capturedAt`),
        photoRef,
        photoRegion: photoRef ? readPhotoRegion(reader, attestation.photoRegion, `${where}.photoRegion`) : null
      }];
    }),
    images: reader.list(fields.imagePrompts, "imagePrompts")
      .map((image, index) => readPrompt(reader, image, `imagePrompts[${index}]`))
      .filter((image): image is ImagePromptDraft => image !== null)
  };

  if (!draft.senses.length) reader.fail("senses", "an entry needs at least one sense.");
  if (reader.problems.length) throw new YamlProblems(reader.problems);
  return draft;
}

/**
 * The starting point for a new entry. It carries no ids, so everything in it is created — which is
 * the only difference between this and an edit. Asserted to parse, so the shape someone is invited
 * to fill in can never fall behind the shape the reader accepts.
 */
export const YAML_TEMPLATE = `# New entry — fill in what you know and delete the rest.
# No ids here: everything in this document is created when you save.
language: es
headword: ""
lemma: ""              # leave empty to reuse the headword
pos: noun              # noun verb adj adv phrase idiom expression
register: neutral      # neutral formal colloquial slang vulgar
emoji: ""
status: active
topics: []             # existing topic names, e.g. [Food, Travel]
shortGloss: null       # null = derived from the first gloss below
primaryGloss: null     # the ONE term a loop speaks, e.g. disgust
emotion: null          # how the word itself sounds, e.g. repulsed, recoiling slightly
notes: []
senses:
  - order: 0
    definition: ""     # in the target language
    definitionLang: es
    domain: ""         # one word for this meaning, e.g. cooking
    emoji: ""
    glosses:
      - { lang: en, terms: [""] }
    examples:
      - text: ""
        translation: ""
        translationLang: en
        origin: manual
attestations: []       # the sentence you actually met it in, verbatim
`;
