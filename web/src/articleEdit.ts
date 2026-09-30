/* ── applying a proposal, and showing what it did ────────────────────────
   `docs/features/article-chat.md`. A turn of conversation returns prose and, when it implies a
   change, a small set of operations addressed by record id. This module applies them to a draft and
   compares the two drafts; nothing else in the interface knows the operation language exists.

   Pure, like `selectors.ts` and `yaml.ts` beside it: no storage, no network, no DOM, no clock. The
   one thing it cannot compute — a new record id — is handed in, so the module stays testable and
   the minting stays where the rest of the minting is.

   **The change marks come from `diffDrafts`, not from the operations.** That is deliberate and it
   is what makes the wire format replaceable: if a future model is better at returning a whole
   article than a list of edits, this file's first half goes and the second half, the review surface
   and the save path are all untouched. It also means a hand-edit in the YAML tab could be marked by
   the same machinery if that ever proves useful.

   Operations are a wire format for one request. They are applied to an `ArticleDraft` and then they
   cease to exist: there is no second article format, and the one writer is still
   `repository.saveArticle(parseArticle(text))`. */

import {
  GENDERS, LEXEME_STATUSES, PARTS_OF_SPEECH, REGISTERS, SOURCE_KINDS,
  type Gender, type Gloss, type LexemeStatus, type PartOfSpeech, type Register, type PhotoRegion,
  type SourceKind
} from "./domain";
import { draftKeys } from "./selectors";
import { lcs, similarity, wordDiff, words, type DiffPart } from "./wordDiff";
import type { ArticleDraft, AttestationDraft, ExampleDraft, SenseDraft } from "./yaml";

/* ── the wire format ────────────────────────────────────────────────── */

export type Target = "lexeme" | `sense:${string}` | `example:${string}` | `attestation:${string}`;

/**
 * Every operation is an `op` and a `target`.
 *
 * `target` names a record — `lexeme`, or `<kind>:<id>` — except on `add` and `reorder`, where the
 * record does not exist yet and it names a kind instead. That uniformity is the whole point of the
 * shape: one vocabulary of targets, and the parent is named by a field (`after`, `in`) rather than
 * encoded in the operation's name.
 */
export type EditOp =
  | { op: "set"; target: string; field: string; value: unknown }
  | { op: "add"; target: "sense"; after?: string | null; value: Record<string, unknown> }
  | {
      op: "add"; target: "example"; in: string; fromAttestation?: string | null;
      value: Record<string, unknown>;
    }
  | { op: "add"; target: "attestation"; ref: string; value: Record<string, unknown> }
  | { op: "remove"; target: string; reason?: string }
  | { op: "reorder"; target: "senses"; ids: string[] };

/** At most twelve. A cap the model cannot argue with is worth more than a paragraph it can. */
export const OP_LIMIT = 12;

export interface EditContext {
  /** The model that answered, for `modelId` on anything it wrote. */
  modelId: string;
  /** `article.glossLangs[0]`, for an example that gains a translation it did not have. */
  glossLang: string | null;
  /** `ids.newId` at the call site. Injected so this module stays pure. */
  mintId(): string;
  /** A photo folded in with this conversation, which the device attaches and the model never sees. */
  photo?: FoldedPhoto | null;
}

/**
 * The photo a sentence was read from, when that sentence is folded into a word already held.
 *
 * The conversation carries text, and a model may not write a reference, so the photo is attached
 * here rather than asked for: to the sentence the conversation adds that is the one photographed,
 * or — a sign, which has no sentence — as an attestation of its own, the shape a new word's capture
 * gives it. Attached at most once, however many turns build on the draft.
 */
export interface FoldedPhoto {
  /** The photographed sentence as it was sent, or null for a sign. */
  sentence: string | null;
  photoRef: string;
  photoRegion: PhotoRegion | null;
  sourceKind: SourceKind;
}

export interface AppliedEdit {
  draft: ArticleDraft;
  /**
   * Ids minted just now, handed to `saveArticle` so they read as creations rather than as ids
   * naming nothing. An argument, never a field in the document — a document editing a stored entry
   * still may not carry ids its producer minted, and this does not change that.
   *
   * **Every added record is minted, not only an attestation.** It used to be only the attestation,
   * because that is the one an example has to name; everything else was left null for `saveArticle`
   * to mint on the way out. But a record with no id has no name in the document the *next* turn is
   * given, so "add an example" followed by "make that example more concrete" asked the model to
   * address something anonymous — and it did the only thing it could, which was invent an id, which
   * is refused. Minting here is what makes a conversation able to talk about what it just did.
   */
  minted: ReadonlySet<string>;
}

/** A refusal the reader sees, in one plain sentence. */
export class EditRefused extends Error {}

const refuse = (message: string): never => {
  throw new EditRefused(message);
};

/** A draft record seen as the loose bag `setField` and `changedFields` work over. */
type Fields = Record<string, unknown>;
const fieldsOf = (record: object): Fields => record as unknown as Fields;

/** A field a new record cannot do without. Returns it, so the caller keeps a narrowed `string`. */
function required(value: unknown, message: string): string {
  if (typeof value !== "string" || !value.trim()) throw new EditRefused(message);
  return value.trim();
}

const REWRITE = "That was a rewrite rather than an edit, so nothing was changed.";
const UNKNOWN = "The model referred to a part of the entry that is not there, so nothing was changed.";

/* ── what may be set ────────────────────────────────────────────────────
   Declared explicitly rather than derived from `yaml.ts`'s key arrays, because those are *document*
   vocabularies and include `id`, `language` and `origin` — none of which chat may touch. A test
   asserts each table below is a strict subset of the matching array, so one vocabulary stays one
   place a new field is noticed. */

type Coerce =
  | "text" | "textOrNull" | "strings" | "glosses"
  | { choice: readonly string[] }
  | { choiceOrNull: readonly string[] };

const LEXEME_FIELDS: Record<string, Coerce> = {
  headword: "text", lemma: "text", reading: "textOrNull", ipa: "textOrNull",
  pos: { choice: PARTS_OF_SPEECH }, gender: { choiceOrNull: GENDERS },
  register: { choiceOrNull: REGISTERS }, dialect: "textOrNull", emoji: "textOrNull",
  shortGloss: "textOrNull", primaryGloss: "textOrNull", emotion: "textOrNull",
  notes: "strings", topics: "strings",
  status: { choice: LEXEME_STATUSES }
};
const SENSE_FIELDS: Record<string, Coerce> = {
  definition: "text", definitionLang: "text", domain: "textOrNull", emoji: "textOrNull", glosses: "glosses"
};
const EXAMPLE_FIELDS: Record<string, Coerce> = {
  text: "text", translation: "textOrNull", note: "textOrNull",
  matchedForm: "textOrNull", matchedTranslationForm: "textOrNull"
};
const ATTESTATION_FIELDS: Record<string, Coerce> = {
  text: "text", translation: "textOrNull", sourceTitle: "textOrNull",
  sourceUrl: "textOrNull", sourceKind: { choice: SOURCE_KINDS }
};

export const SETTABLE = {
  lexeme: LEXEME_FIELDS, sense: SENSE_FIELDS, example: EXAMPLE_FIELDS, attestation: ATTESTATION_FIELDS
};

function coerce(field: string, rule: Coerce, value: unknown): unknown {
  const wrong = () => refuse(`\`${field}\` was given a value of the wrong kind, so nothing was changed.`);
  if (rule === "text") {
    if (typeof value !== "string" || !value.trim()) return wrong();
    return value.trim();
  }
  if (rule === "textOrNull") {
    if (value === null || value === undefined) return null;
    if (typeof value !== "string") return wrong();
    return value.trim() || null;
  }
  if (rule === "strings") {
    if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) return wrong();
    return (value as string[]).map((item) => item.trim()).filter(Boolean);
  }
  if (rule === "glosses") {
    if (!Array.isArray(value)) return wrong();
    const groups: Gloss[] = [];
    for (const item of value) {
      if (!item || typeof item !== "object") return wrong();
      const { lang, terms } = item as { lang?: unknown; terms?: unknown };
      if (typeof lang !== "string" || !lang.trim()) return wrong();
      if (!Array.isArray(terms) || terms.some((term) => typeof term !== "string")) return wrong();
      const kept = (terms as string[]).map((term) => term.trim()).filter(Boolean);
      if (!kept.length) return wrong();
      groups.push({ lang: lang.trim(), terms: kept });
    }
    if (!groups.length) return wrong();
    return groups;
  }
  if ("choice" in rule) {
    if (typeof value !== "string" || !rule.choice.includes(value)) return wrong();
    return value;
  }
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || !rule.choiceOrNull.includes(value)) return wrong();
  return value;
}

/* ── applying ───────────────────────────────────────────────────────── */

const RECORD_ID = /^[a-z0-9]{15}$/;

/** A record reference that may come as `sense:ID` or as a bare `ID`, which models do both of. */
function reference(value: string, kind: string): string {
  return splitTarget(value.includes(":") ? value : `${kind}:${value}`).id;
}

function splitTarget(target: string): { kind: string; id: string } {
  if (target === "lexeme") return { kind: "lexeme", id: "" };
  const at = target.indexOf(":");
  if (at < 0) return refuse(UNKNOWN);
  return { kind: target.slice(0, at), id: target.slice(at + 1) };
}

/**
 * Apply a proposal to a draft. All-or-nothing: the work happens on a clone and is returned only if
 * every operation applied, so no partial edit is reachable even in principle.
 */
export function applyOps(draft: ArticleDraft, ops: EditOp[], context: EditContext): AppliedEdit {
  // A sign's photo is a change of its own, so it may be proposed with nothing from the model.
  const sign = context.photo?.sentence === null && !holdsPhoto(draft, context.photo);
  if (!ops.length && !sign) refuse("That proposal changes nothing, so nothing was changed.");
  if (ops.length > OP_LIMIT) refuse(REWRITE);

  const next: ArticleDraft = structuredClone(draft);
  const minted = new Set<string>();
  /** `ref` -> the id minted for it, so an example written in the same answer can name it. */
  const refs = new Map<string, string>();
  const touched = new Set<string>();

  const senseAt = (id: string) => {
    const found = next.senses.find((sense) => sense.id === id);
    return found ?? refuse(UNKNOWN);
  };

  for (const op of ops) {
    switch (op.op) {
      case "set": {
        const { kind, id } = splitTarget(op.target);
        if (kind === "lexeme") {
          setField(fieldsOf(next), LEXEME_FIELDS, op.field, op.value, "lexeme");
          touched.add(draftKeys.lexeme(next));
        } else if (kind === "sense") {
          setField(fieldsOf(senseAt(id)), SENSE_FIELDS, op.field, op.value, "sense");
          touched.add(id);
        } else if (kind === "example") {
          const example = next.senses.flatMap((sense) => sense.examples).find((item) => item.id === id)
            ?? refuse(UNKNOWN);
          setField(fieldsOf(example), EXAMPLE_FIELDS, op.field, op.value, "example");
          realign(example, context);
          touched.add(id);
        } else if (kind === "attestation") {
          const attestation = next.attestations.find((item) => item.id === id) ?? refuse(UNKNOWN);
          setField(fieldsOf(attestation), ATTESTATION_FIELDS, op.field, op.value, "attestation");
          touched.add(id);
        } else refuse(UNKNOWN);
        break;
      }

      /* `op.target` here is a bare kind word, so it deliberately does NOT go through
         `splitTarget` — that function refuses a target with no colon, which is correct for a
         record reference and wrong for a kind. */
      case "add": {
        if (op.target === "sense") {
          const after = op.after ? reference(op.after, "sense") : null;
          const at = after ? next.senses.findIndex((sense) => sense.id === after) : -1;
          if (after && at < 0) refuse(UNKNOWN);
          const sense = newSense(op.value, next, context, minted);
          next.senses.splice(at + 1, 0, sense);
          next.senses.forEach((item, index) => { item.order = index; });
          touched.add(draftKeys.sense(sense, next.senses.indexOf(sense)));
        } else if (op.target === "example") {
          const sense = senseAt(reference(op.in, "sense"));
          const example = newExample(op.value, next, context, op.fromAttestation ?? null, refs, minted);
          sense.examples.push(example);
          touched.add(draftKeys.example(example, next.senses.indexOf(sense), sense.examples.length - 1));
        } else if (op.target === "attestation") {
          const id = context.mintId();
          minted.add(id);
          refs.set(op.ref, id);
          next.attestations.push(newAttestation(op.value, id));
          touched.add(id);
        } else refuse(UNKNOWN);
        break;
      }

      case "remove": {
        const { kind, id } = splitTarget(op.target);
        if (kind === "sense") {
          if (next.senses.length <= 1) {
            refuse("That would leave the entry with no meanings, so nothing was changed.");
          }
          const at = next.senses.findIndex((sense) => sense.id === id);
          if (at < 0) refuse(UNKNOWN);
          for (const example of next.senses[at].examples) if (example.id) touched.add(example.id);
          next.senses.splice(at, 1);
          next.senses.forEach((item, index) => { item.order = index; });
        } else if (kind === "example") {
          const sense = next.senses.find((item) => item.examples.some((example) => example.id === id))
            ?? refuse(UNKNOWN);
          sense.examples = sense.examples.filter((example) => example.id !== id);
        } else if (kind === "attestation") {
          const named = next.senses
            .flatMap((sense) => sense.examples)
            .some((example) => example.sourceAttestationId === id);
          if (named) {
            refuse("That sentence is where an example came from, so nothing was changed.");
          }
          const before = next.attestations.length;
          next.attestations = next.attestations.filter((item) => item.id !== id);
          if (next.attestations.length === before) refuse(UNKNOWN);
        } else refuse(UNKNOWN);
        touched.add(id);
        break;
      }

      case "reorder": {
        if (op.target !== "senses") refuse(UNKNOWN);
        const ids = op.ids.map((id) => reference(id, "sense"));
        const held = next.senses.map((sense) => sense.id);
        if (ids.length !== held.length || held.some((id) => !id || !ids.includes(id))) {
          refuse("That reordering does not list the entry's meanings, so nothing was changed.");
        }
        next.senses = ids.map((id) => senseAt(id));
        next.senses.forEach((item, index) => { item.order = index; });
        for (const id of ids) touched.add(id);
        break;
      }

      default:
        refuse("The model asked for a change Acervo does not know how to make, so nothing was changed.");
    }
  }

  /* The half rule. As §5.3 states it unconditionally it misfires on small entries — a one-sense
     entry has two records, so "fix the definition and add an example" is already over half, and
     that is an ordinary edit rather than a rewrite. Below three touched records the twelve-op cap
     is the only limit, which is enough. */
  const total = 1 + draft.senses.length
    + draft.senses.reduce((count, sense) => count + sense.examples.length, 0)
    + draft.attestations.length;
  if (touched.size > 2 && touched.size * 2 > total) refuse(REWRITE);

  // After the half rule: the photo is the device's addition, not the model's rewrite.
  if (context.photo) attachPhoto(next, context.photo, minted, context);
  return { draft: next, minted };
}

function holdsPhoto(draft: ArticleDraft, photo: FoldedPhoto): boolean {
  return draft.attestations.some((attestation) => attestation.photoRef === photo.photoRef);
}

/** Quotes and spacing aside: the sentence goes to the model in «», and may come back without them. */
function sameSentence(one: string, other: string): boolean {
  const plain = (text: string) => text.replace(/[«»"“”]/g, "").replace(/\s+/g, " ").trim().toLowerCase();
  return plain(one) === plain(other);
}

function attachPhoto(next: ArticleDraft, photo: FoldedPhoto, minted: Set<string>, context: EditContext): void {
  if (holdsPhoto(next, photo)) return;
  const kept = { photoRef: photo.photoRef, photoRegion: photo.photoRegion, sourceKind: photo.sourceKind };
  if (photo.sentence === null) {
    const id = context.mintId();
    minted.add(id);
    next.attestations.push({ ...newAttestation({}, id, true), ...kept });
    return;
  }
  const added = next.attestations.filter((attestation) => attestation.id !== null && minted.has(attestation.id));
  const target = added.find((attestation) => sameSentence(attestation.text, photo.sentence!))
    ?? (added.length === 1 ? added[0] : null);
  if (target) Object.assign(target, kept);
}

function setField(
  record: Record<string, unknown>, table: Record<string, Coerce>, field: string, value: unknown,
  what: string
): void {
  const rule = table[field];
  if (!rule) {
    refuse(`\`${field}\` is not something chat can change on a ${what}, so nothing was changed.`);
  }
  record[field] = coerce(field, rule, value);
}

/**
 * The two agreements `validateGraph` enforces, kept after a `set` rather than before it.
 *
 * A `translation` and its `translationLang` must be present together, and a `matchedForm` must
 * occur verbatim in the text it marks. A marker that does not occur is **dropped and the rest of
 * the edit stands** — the rule `services/capture/draft.py` already applies, and the one deliberate
 * exception to all-or-nothing: a model that retypes an inflected form instead of copying it should
 * cost the emphasis, not the whole answer.
 */
function realign(example: ExampleDraft, context: EditContext): void {
  if (example.translation === null) example.translationLang = null;
  else if (!example.translationLang) example.translationLang = context.glossLang ?? "en";
  if (example.matchedForm && !example.text.includes(example.matchedForm)) example.matchedForm = null;
  if (example.matchedTranslationForm
    && !(example.translation ?? "").includes(example.matchedTranslationForm)) {
    example.matchedTranslationForm = null;
  }
}

function read(raw: Record<string, unknown>, table: Record<string, Coerce>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(raw)) {
    // A field chat may not set is ignored on a *new* record rather than refused: the model
    // volunteering `origin: "llm"` on an example it wrote is right about the fact and wrong about
    // whose job it is, and refusing the answer over that would help nobody.
    if (table[field]) out[field] = coerce(field, table[field], value);
  }
  return out;
}

function newSense(
  raw: Record<string, unknown>, draft: ArticleDraft, context: EditContext, minted: Set<string>
): SenseDraft {
  const fields = read(raw, SENSE_FIELDS);
  const definition = required(fields.definition, "A new meaning needs a definition, so nothing was changed.");
  const examples = Array.isArray(raw.examples) ? raw.examples : [];
  const id = context.mintId();
  minted.add(id);
  return {
    id,
    order: draft.senses.length,
    definition,
    definitionLang: (fields.definitionLang as string | undefined)
      ?? draft.senses[0]?.definitionLang ?? draft.language,
    glosses: (fields.glosses as Gloss[] | undefined) ?? [],
    domain: (fields.domain as string | null | undefined) ?? null,
    emoji: (fields.emoji as string | null | undefined) ?? null,
    examples: examples.map((item) =>
      newExample(item as Record<string, unknown>, draft, context, null, new Map(), minted)),
    images: []
  };
}

function newExample(
  raw: Record<string, unknown>, draft: ArticleDraft, context: EditContext,
  fromAttestation: string | null, refs: Map<string, string>, minted: Set<string>
): ExampleDraft {
  const fields = read(raw, EXAMPLE_FIELDS);
  const text = required(fields.text, "A new example needs a sentence, so nothing was changed.");

  /* Provenance is derived here, never read from the model. A sentence the owner supplied is an
     attestation and the example names it; anything else the model wrote is generated and records
     the model that wrote it. There is no field meaning "a person wrote this", and chat does not
     get one. */
  let sourceAttestationId: string | null = null;
  if (fromAttestation) {
    const resolved = refs.get(fromAttestation)
      // Also accept an id already in the document, which is how a new example is folded onto a
      // sentence the entry already holds.
      ?? (RECORD_ID.test(fromAttestation)
        && draft.attestations.some((item) => item.id === fromAttestation)
        ? fromAttestation : null);
    if (!resolved) refuse("The model quoted a sentence it did not supply, so nothing was changed.");
    sourceAttestationId = resolved;
  }

  const translation = (fields.translation as string | null | undefined) ?? null;
  const id = context.mintId();
  minted.add(id);
  const example: ExampleDraft = {
    id,
    text,
    textLang: draft.language,
    translation,
    translationLang: translation ? context.glossLang ?? "en" : null,
    origin: sourceAttestationId ? "attestation" : "llm",
    sourceAttestationId,
    modelId: sourceAttestationId ? null : context.modelId,
    videoRef: null, videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null,
    clipRef: null, imageRef: null, emotion: null,
    note: (fields.note as string | null | undefined) ?? null,
    matchedForm: (fields.matchedForm as string | null | undefined) ?? null,
    matchedTranslationForm: (fields.matchedTranslationForm as string | null | undefined) ?? null
  };
  realign(example, context);
  return example;
}

function newAttestation(raw: Record<string, unknown>, id: string, sign = false): AttestationDraft {
  const fields = read(raw, ATTESTATION_FIELDS);
  const text = sign ? "" : required(fields.text, "A new sentence needs some text, so nothing was changed.");
  return {
    id,
    text,
    translation: (fields.translation as string | null | undefined) ?? null,
    sourceUrl: (fields.sourceUrl as string | null | undefined) ?? null,
    sourceTitle: (fields.sourceTitle as string | null | undefined) ?? null,
    sourceKind: ((fields.sourceKind as SourceKind | undefined) ?? "unknown"),
    /* A document may not assert a clock, and this module has none. `saveArticle` stamps what it
       must; `capturedAt` is the one field a draft carries that has to say something, so it says
       the epoch and the save replaces it. */
    capturedAt: new Date(0).toISOString().replace(/\.\d+Z$/, ".000Z"),
    // The model never names a photo; `attachPhoto` adds the one the device folded in.
    photoRef: null,
    photoRegion: null
  };
}

/* ── the diff ─────────────────────────────────────────────────────────────
   What a proposal did, computed by comparing two drafts and never by reading the operations. That
   is what keeps the wire format replaceable, and it is the whole reason the operations are allowed
   to be a detail of one request.

   Two things here are more than bookkeeping. A changed field carries a **word diff**, so a reworded
   sentence says which words moved rather than only that it moved. And a record that merely changed
   position is `moved` rather than unmarked — a reorder used to produce no marks and a count of zero
   while the article silently renumbered itself. */

export type Mark = "added" | "changed" | "removed" | "moved";

/** What happened to one field, or to one note. `words` is null for anything that is not prose. */
export interface Change {
  mark: Mark;
  words: DiffPart[] | null;
}

export interface RecordDiff {
  /** The block treatment. Precedence: removed, added, moved, changed. */
  mark: Mark;
  /** Which fields moved, so a tint lands on the line that changed rather than on the whole record. */
  fields: ReadonlyMap<string, Change>;
  /** For a `moved` record only: the position it held before, counting from one. */
  wasAt?: number;
}

export interface DraftDiff {
  /** Record key -> what happened. Keys are exactly `articleFromDraft(graph, shown)`'s record ids. */
  records: ReadonlyMap<string, RecordDiff>;
  /**
   * Notes, keyed by their index in `shown.notes` — ghosts included.
   *
   * Indexed rather than keyed by text, which is what the first version did. Text is not an identity:
   * two identical notes collided in the map and produced a duplicate React key, a reordered note was
   * invisible, and — the one that mattered — a *reworded* note had no partner to diff against, so it
   * read as a deletion beside an addition instead of as one change.
   */
  notes: ReadonlyMap<number, Change>;
  /**
   * Every change, in the order the article draws them: the head, then each sense with its examples,
   * then attestations, then notes as `note:<index into shown.notes>`.
   *
   * This is what the review bar's next and previous step through, and it is why that component needs
   * to know nothing about record ids. A `note:` key cannot collide with a record key: stored ids are
   * fifteen characters of `[a-z0-9]` and placeholders are `draft:`-prefixed.
   */
  order: readonly string[];
  /**
   * RENDER ONLY: `after`, plus every removed record put back where it was.
   *
   * A removed record is not in `after`, so `articleFromDraft` would never emit it and "drawn where
   * it was, struck through" would need a second rendering path. Put back, a ghost is an ordinary
   * draft record that draws for free and needs only a class. **Never saved, never serialised** —
   * `App` holds `after` separately for that, and saving this would resurrect what was removed.
   */
  shown: ArticleDraft;
  /** What the review bar counts. One marked record is one change, however many of its fields moved. */
  count: number;
}

const changedFields = (
  before: Record<string, unknown>, after: Record<string, unknown>, table: Record<string, Coerce>
): string[] =>
  Object.keys(table).filter((field) =>
    JSON.stringify(before[field] ?? null) !== JSON.stringify(after[field] ?? null));

const blank = (value: unknown) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length);

/** Which fields moved, how, and — for prose — which words. */
function fieldChanges(
  before: Record<string, unknown>, after: Record<string, unknown>, table: Record<string, Coerce>
): Map<string, Change> {
  const changes = new Map<string, Change>();
  for (const field of changedFields(before, after, table)) {
    const was = before[field];
    const now = after[field];
    const mark: Mark = blank(was) ? "added" : blank(now) ? "removed" : "changed";
    changes.set(field, {
      mark,
      words: typeof was === "string" && typeof now === "string" ? wordDiff(was, now) : null
    });
  }
  return changes;
}

/**
 * Positions in `sequence` that kept their relative order. Everything else is what actually moved.
 *
 * `sequence` is where each surviving record *used* to be, read in the order they appear now, so the
 * longest increasing run is the set that did not move and the complement is minimal. Rotating three
 * senses therefore reports one change for one drag rather than three.
 */
function anchored(sequence: readonly number[]): Set<number> {
  // The longest increasing subsequence of a list is its common subsequence with its sorted self.
  const rising = [...sequence].sort((one, other) => one - other);
  return new Set(lcs(sequence, rising, (one, other) => one === other).map((pair) => pair.a));
}

const NOTE_PAIR = 0.5;
const NOTE_TOKENS = 3;
const NOTE_LIMIT = 24;

interface NoteRow {
  text: string;
  change: Change | null;
}

/**
 * Match the notes of one draft against another's, so a reworded note is one change and not two.
 *
 * `set notes` takes the whole list, so a model fixing one word in the second note sends all three.
 * Exact pairing silences the two it did not touch; similarity pairing recognises the one it did.
 *
 * Four passes: exact matches, *consuming* so two identical notes pair with two identical notes
 * rather than collapsing into one; then the most similar remaining pairs, greedily; then the longest
 * run that kept its order, so the rest read as moved; then whatever is left over is an addition or a
 * removal.
 */
function pairNotes(before: readonly string[], after: readonly string[]): NoteRow[] {
  const takenBefore = new Set<number>();
  const takenAfter = new Set<number>();
  /** after index -> before index */
  const pairs = new Map<number, number>();

  const same = (one: string, other: string) => one.normalize("NFC") === other.normalize("NFC");
  for (let j = 0; j < after.length; j += 1) {
    for (let i = 0; i < before.length; i += 1) {
      if (takenBefore.has(i) || !same(before[i], after[j])) continue;
      pairs.set(j, i);
      takenBefore.add(i);
      takenAfter.add(j);
      break;
    }
  }

  /* Dice over the same word tokens the diff will draw, which is the quantity being asked about:
     how much of this note survived. Above half, or the rendered diff is all deletions and
     insertions and "removed, and here is a new one" is the more honest reading. Three tokens
     minimum, because at two a single shared word scores exactly a half and would pair "Rare."
     with "Common.". */
  if (before.length <= NOTE_LIMIT && after.length <= NOTE_LIMIT) {
    const candidates: { i: number; j: number; score: number }[] = [];
    for (let j = 0; j < after.length; j += 1) {
      if (takenAfter.has(j) || words(after[j]).length < NOTE_TOKENS) continue;
      for (let i = 0; i < before.length; i += 1) {
        if (takenBefore.has(i) || words(before[i]).length < NOTE_TOKENS) continue;
        const score = similarity(before[i], after[j]);
        if (score > NOTE_PAIR) candidates.push({ i, j, score });
      }
    }
    // Best first, and deterministic where scores tie.
    candidates.sort((one, other) => other.score - one.score || one.j - other.j || one.i - other.i);
    for (const candidate of candidates) {
      if (takenBefore.has(candidate.i) || takenAfter.has(candidate.j)) continue;
      pairs.set(candidate.j, candidate.i);
      takenBefore.add(candidate.i);
      takenAfter.add(candidate.j);
    }
  }

  const ordered = [...pairs.keys()].sort((one, other) => one - other);
  const stayed = anchored(ordered.map((j) => pairs.get(j)!));
  const kept = new Set(ordered.filter((_, position) => stayed.has(position)));

  const rows: NoteRow[] = after.map((text, j) => {
    const i = pairs.get(j);
    if (i === undefined) return { text, change: { mark: "added", words: null } };
    const moved = !kept.has(j);
    if (same(before[i], text)) return { text, change: moved ? { mark: "moved", words: null } : null };
    // Reworded, and possibly moved as well. `moved` wins the label and the words come along, so the
    // reader still sees which words changed.
    return { text, change: { mark: moved ? "moved" : "changed", words: wordDiff(before[i], text) } };
  });

  /* Ghosts go back where they were: walk `before` in order and flush each paired note's partner as
     it comes up, so a removed note lands among the notes it used to sit between. */
  const partnerOf = new Map<number, number>();
  for (const [j, i] of pairs) partnerOf.set(i, j);
  const merged: NoteRow[] = [];
  let cursor = 0;
  for (let i = 0; i < before.length; i += 1) {
    const j = partnerOf.get(i);
    if (j === undefined) {
      merged.push({ text: before[i], change: { mark: "removed", words: null } });
      continue;
    }
    while (cursor <= j) merged.push(rows[cursor++]);
  }
  while (cursor < rows.length) merged.push(rows[cursor++]);
  return merged;
}

export function diffDrafts(before: ArticleDraft, after: ArticleDraft): DraftDiff {
  const records = new Map<string, RecordDiff>();
  const noteMarks = new Map<number, Change>();
  const shown: ArticleDraft = structuredClone(after);

  /* The head. `notes` is excluded because the notes section marks its own lines, and letting the
     head claim the change as well would mark nothing extra on screen and count one edit twice. */
  const headFields = fieldChanges(fieldsOf(before), fieldsOf(after), LEXEME_FIELDS);
  headFields.delete("notes");
  if (headFields.size) {
    records.set(draftKeys.lexeme(shown), { mark: "changed", fields: headFields });
  }

  /* Notes, matched rather than compared, and indexed against what will be drawn. */
  const noteRows = pairNotes(before.notes, after.notes);
  shown.notes = noteRows.map((row) => row.text);
  noteRows.forEach((row, index) => { if (row.change) noteMarks.set(index, row.change); });

  /* Senses. One held in `before` and missing from `after` goes back at its old index, and its
     examples come with it — the reader has to see what a proposal takes away. */
  const keptSenses = new Set(after.senses.map((sense) => sense.id).filter(Boolean) as string[]);
  before.senses.forEach((sense, index) => {
    if (sense.id && !keptSenses.has(sense.id)) {
      shown.senses.splice(Math.min(index, shown.senses.length), 0, structuredClone(sense));
    }
  });

  const beforeSenses = new Map(before.senses.filter((sense) => sense.id).map((sense) => [sense.id!, sense]));
  const beforeExamples = new Map(
    before.senses.flatMap((sense) => sense.examples).filter((example) => example.id)
      .map((example) => [example.id!, example])
  );
  const afterExamples = new Set(
    after.senses.flatMap((sense) => sense.examples).map((example) => example.id).filter(Boolean) as string[]
  );

  /* Which senses actually moved, rather than which ones are in a different place. Rotating three
     senses moves one of them, and the review bar should say one change for one drag. */
  const wasAt = new Map(
    (before.senses.map((sense) => sense.id).filter(Boolean) as string[]).map((id, index) => [id, index])
  );
  const survived = after.senses
    .map((sense) => sense.id)
    .filter((id): id is string => Boolean(id) && wasAt.has(id as string));
  const stayed = anchored(survived.map((id) => wasAt.get(id)!));
  const held = new Set(survived.filter((_, position) => stayed.has(position)));

  const empty: ReadonlyMap<string, Change> = new Map();
  shown.senses.forEach((sense, senseIndex) => {
    const key = draftKeys.sense(sense, senseIndex);
    const was = sense.id ? beforeSenses.get(sense.id) : undefined;
    const gone = Boolean(sense.id) && !keptSenses.has(sense.id!);
    if (gone) {
      records.set(key, { mark: "removed", fields: empty });
    } else if (!sense.id || !was) {
      records.set(key, { mark: "added", fields: empty });
    } else {
      const fields = fieldChanges(fieldsOf(was), fieldsOf(sense), SENSE_FIELDS);
      if (!held.has(sense.id)) {
        records.set(key, { mark: "moved", fields, wasAt: wasAt.get(sense.id)! + 1 });
      } else if (fields.size) {
        records.set(key, { mark: "changed", fields });
      }
    }

    const removedHere = was
      ? was.examples.filter((example) => example.id && !afterExamples.has(example.id))
      : [];
    for (const example of removedHere) {
      const at = was!.examples.indexOf(example);
      if (!sense.examples.some((item) => item.id === example.id)) {
        sense.examples.splice(Math.min(at, sense.examples.length), 0, structuredClone(example));
      }
    }
    sense.examples.forEach((example, index) => {
      const exampleKey = draftKeys.example(example, senseIndex, index);
      const previous = example.id ? beforeExamples.get(example.id) : undefined;
      // A removed sense's examples are removed with it, whatever they say on their own.
      if (gone || (example.id && !afterExamples.has(example.id))) {
        records.set(exampleKey, { mark: "removed", fields: empty });
      } else if (!example.id || !previous) {
        records.set(exampleKey, { mark: "added", fields: empty });
      } else {
        const fields = fieldChanges(fieldsOf(previous), fieldsOf(example), EXAMPLE_FIELDS);
        if (fields.size) records.set(exampleKey, { mark: "changed", fields });
      }
    });
  });

  /* Attestations, the same way. */
  const afterAttestations = new Set(
    after.attestations.map((item) => item.id).filter(Boolean) as string[]
  );
  before.attestations.forEach((attestation, index) => {
    if (attestation.id && !afterAttestations.has(attestation.id)) {
      shown.attestations.splice(Math.min(index, shown.attestations.length), 0, structuredClone(attestation));
    }
  });
  const beforeAttestations = new Map(
    before.attestations.filter((item) => item.id).map((item) => [item.id!, item])
  );
  shown.attestations.forEach((attestation, index) => {
    const key = draftKeys.attestation(attestation, index);
    const was = attestation.id ? beforeAttestations.get(attestation.id) : undefined;
    if (!attestation.id || !was) {
      records.set(key, { mark: "added", fields: empty });
    } else if (!afterAttestations.has(attestation.id)) {
      records.set(key, { mark: "removed", fields: empty });
    } else {
      const fields = fieldChanges(fieldsOf(was), fieldsOf(attestation), ATTESTATION_FIELDS);
      if (fields.size) records.set(key, { mark: "changed", fields });
    }
  });

  /* Document order, which is not the order this function computed things in: the article draws the
     head, then the senses, then where you met it, then the notes. Next and previous have to move
     down the page. */
  const order: string[] = [];
  const at = (key: string) => { if (records.has(key)) order.push(key); };
  at(draftKeys.lexeme(shown));
  shown.senses.forEach((sense, senseIndex) => {
    at(draftKeys.sense(sense, senseIndex));
    sense.examples.forEach((example, index) => at(draftKeys.example(example, senseIndex, index)));
  });
  shown.attestations.forEach((attestation, index) => at(draftKeys.attestation(attestation, index)));
  for (const index of [...noteMarks.keys()].sort((one, other) => one - other)) order.push(`note:${index}`);

  return { records, notes: noteMarks, order, shown, count: records.size + noteMarks.size };
}
