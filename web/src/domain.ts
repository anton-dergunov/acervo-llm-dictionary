export const PARTS_OF_SPEECH = ["noun", "verb", "adj", "adv", "phrase", "idiom", "expression"] as const;
export const GENDERS = ["masculine", "feminine", "common", "neuter"] as const;
export const REGISTERS = ["neutral", "formal", "colloquial", "slang", "vulgar"] as const;
export const LEXEME_STATUSES = ["inbox", "active", "learned", "retired", "suppressed"] as const;
/** `sign` is text met out in the world rather than read — a street sign, a menu, a label — usually kept as a photo. */
export const SOURCE_KINDS = ["web", "book", "conversation", "video", "lesson", "sign", "unknown"] as const;
export const EXAMPLE_ORIGINS = ["attestation", "llm", "tatoeba", "subtitle", "wiktionary", "manual"] as const;

export type PartOfSpeech = typeof PARTS_OF_SPEECH[number];
export type Gender = typeof GENDERS[number];
export type Register = typeof REGISTERS[number];
export type LexemeStatus = typeof LEXEME_STATUSES[number];
export type SourceKind = typeof SOURCE_KINDS[number];
export type ExampleOrigin = typeof EXAMPLE_ORIGINS[number];
export type EntityKind = "vocabularies" | "topics" | "lexemes" | "senses" | "attestations" | "examples" | "imagePrompts" | "pronunciations" | "studyStates" | "loops" | "loopItems" | "loopCues" | "stories" | "storyParts" | "storyWords" | "beds";
/** What a pronunciation reads: a lexeme's headword, a sense's definition, an example's or an attestation's text. */
export const PRONUNCIATION_TARGETS = ["lexeme", "sense", "example", "attestation"] as const;
export type PronunciationTarget = typeof PRONUNCIATION_TARGETS[number];

export interface SyncFields {
  deleted: boolean;
  createdAt: string;
  editedAt: string;
  editedBy: string;
  revision: number;
}

export interface OwnedFields {
  ownerId: string;
}

export interface Gloss {
  lang: string;
  terms: string[];
}

/**
 * One language this owner studies, and how they want it presented
 * (`docs/architecture/data-model.md`).
 *
 * A vocabulary exists independently of whether it holds any words yet — that is the whole point,
 * since a language has to be configured before its first word can be captured. `languages.ts`
 * supplies the flag and name when the record leaves them empty.
 */
export interface Vocabulary extends SyncFields, OwnedFields {
  id: string;
  language: string;
  /** The language a sense is defined in — usually the target language itself. */
  definitionLang: string;
  /** The languages to translate into, most preferred first. Never empty. */
  glossLangs: string[];
  /**
   * The language usage notes are written in. Neither of the two above: a definition is short and
   * formulaic, so reading it in the target language is cheap practice, while a note is unbounded
   * contrastive prose and the part of an article you skim. Defaults to the first gloss language,
   * and is configurable because immersion becomes the better answer at some point.
   */
  notesLang: string;
  displayName: string | null;
  flag: string | null;
  order: number;
}

export interface Topic extends SyncFields, OwnedFields {
  id: string;
  name: string;
  icon: string | null;
  order: number;
}

export interface Lexeme extends SyncFields, OwnedFields {
  id: string;
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
  topicIds: string[];
  status: LexemeStatus;
  shortGloss: string | null;
  /**
   * The single most common translation, and how the word itself sounds when said.
   *
   * `shortGloss` is right for the list and wrong for a beat: `house, home` cannot be spoken on one.
   * `primaryGloss` is the one term you would give if allowed only one, in `glossLangs[0]` exactly as
   * `shortGloss` and a sense `domain` are — reordering a vocabulary's gloss languages *is* the
   * control, and a setting over a single stored string could only end up naming a language the
   * stored text is not in.
   *
   * `emotion` is the same field an example carries, one level up: a short English direction, for the
   * word wherever it is used rather than for one sentence. Both are null for most words, and a word
   * without a `primaryGloss` is simply not eligible for a loop — nothing fills it in later.
   */
  primaryGloss: string | null;
  emotion: string | null;
  notes: string[];
  /**
   * When the spoken-usage corpus was last successfully consulted for this lexeme, or null.
   *
   * One field answers two questions. Null means never consulted, which is what the server's
   * enrichment looks for and what an imported word looks like. Set with no `subtitle` examples means consulted and
   * nothing was good enough — a normal answer for most words, not a gap to fill again. Set and
   * older than the corpus's own `built_at` means the corpus has moved on since.
   *
   * Written only on a *successful* consultation, so a retrieval service that was down leaves the
   * word looking untouched and Try again finds it.
   */
  clipsSearchedAt: string | null;
}

export interface Sense extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  definition: string;
  definitionLang: string;
  glosses: Gloss[];
  domain: string | null;
  /** The sense's own emoji, beside the word's: what the article's sense selector shows. */
  emoji: string | null;
  order: number;
}

export interface Attestation extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  text: string;
  translation: string | null;
  sourceUrl: string | null;
  sourceTitle: string | null;
  sourceKind: SourceKind;
  capturedAt: string;
  /**
   * The photo the word was met in, relative to the media root, and where on it the word and its
   * sentence are. Both null for an attestation that was typed or pasted. With a photo the text may
   * be empty: a street sign has no sentence, and the photo is kept as the place the word was met.
   */
  photoRef: string | null;
  photoRegion: PhotoRegion | null;
}

/** Outlines on a photo, normalised to it: the tapped word's pieces and the sentence's lines. */
export interface PhotoRegion {
  words: [number, number][][];
  sentence: [number, number][][];
}

export interface Example extends SyncFields, OwnedFields {
  id: string;
  senseId: string;
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
  /** The corpus's own stable `segment_id`, so the stored text can be audited against the segment. */
  clipRef: string | null;
  imageRef: string | null;
  /**
   * How a native speaker would sound saying this sentence, as a short English direction a voice that
   * takes one can follow. Null reads it neutrally.
   */
  emotion: string | null;
  note: string | null;
  matchedForm: string | null;
  matchedTranslationForm: string | null;
}

/**
 * One sense's picture, and everything about how it came to exist or failed to.
 *
 * The state a picture is in is derived from these fields rather than named by a status:
 * `imageRef` set is *ready*; empty with no attempts is *briefed, not yet drawn*; empty with a
 * `failureReason` is *failed*; and `suppressed` is the owner having ruled on it. A status column
 * would be a fifth thing to keep in step with the four facts that already say all of this.
 *
 * `suppressed` is deliberately not a tombstone. An image prompt's id is derived from its `senseId`,
 * so a tombstoned row is invisible to enrichment, which re-briefs the sense and mints the same id —
 * tombstoning does not prevent regeneration, it guarantees a collision.
 */
export interface ImagePrompt extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  senseId: string | null;
  /** The example the scene was built from, so the article can put the picture under it. */
  exampleId: string | null;
  /** The scene brief. Empty on a picture the owner attached, and on one the writer refused. */
  prompt: string;
  styleId: string;
  seed: number;
  modelId: string;
  promptVersion: string;
  imageRef: string | null;
  /** Absent on a picture the owner supplied — provenance modelled, never a flag. */
  imageModelId: string | null;
  attempts: number;
  failureReason: string | null;
  suppressed: boolean;
}

/**
 * A recording of one spoken field, made by the server when somebody pressed play.
 *
 * Its id is derived from what it reads (`pronunciationId(targetKind, targetId)`), so a field has at
 * most one clip and recording it again rewrites this row. `text` is the words actually spoken: a
 * record edited since no longer matches it, and that is what makes the clip stale.
 */
export interface Pronunciation extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  targetKind: PronunciationTarget;
  targetId: string;
  text: string;
  lang: string;
  /** The emotion the voice was actually given, which is null when it could not take one. */
  emotion: string | null;
  audioRef: string;
  audioMime: string;
  providerId: string;
  modelId: string;
  voice: string | null;
}

export interface StudyState extends SyncFields, OwnedFields {
  id: string;
  lexemeId: string;
  system: string;
  noteId: number | null;
  cardIds: number[];
  reps: number;
  lapses: number;
  stability: number;
  difficulty: number;
  retrievability: number;
  lastReview: string | null;
  syncedAt: string | null;
}

/**
 * A rendered track: some words, spoken over a bar grid with a silence to recall the answer in.
 *
 * **Its state is derived.** An empty `audioRef` is *not rendered yet*, and the job says the rest; a
 * status column would be a fifth thing to keep in step with four facts that already say all of it.
 * Nor is the resolved bed stored: `styleId`, `seed` and `engineVersion` replay it byte-identically
 * and `bedFingerprint` is what proves a replay produced the same one.
 *
 * There is no title either. `loopTitle` derives one from the words that fit, as `shortGlossOf`
 * derives a gloss.
 */
export interface Loop extends SyncFields, OwnedFields {
  id: string;
  language: string;
  styleId: string | null;
  seed: number;
  engineVersion: string | null;
  bedFingerprint: string | null;
  /** Which of the generator's formats this loop is (`classic`, `radio-lesson`, …): its catalogue id. */
  format: string;
  /** The listener's choices for the switches that format offers, sent with every render of it. */
  switches: Record<string, boolean | string>;
  /** The format asked for, when the render lacked something it requires and made its fallback —
   *  `format` then names what the track is. Null otherwise. */
  fallbackFrom: string | null;
  /** Null until it has been rendered, which is the whole of what "not ready" means here. */
  audioRef: string | null;
  audioMime: string | null;
  durationSeconds: number | null;
  /** Sparse, renumbered on reorder. Ordering is respected rather than enforced. */
  position: number;
}

/**
 * One word inside a loop, and when its own block is heard.
 *
 * `sourceText` and `targetText` are denormalised on purpose: they record what was *said*, so editing
 * the word afterwards cannot make the player caption a recording that no longer matches. Identical
 * reasoning to `Pronunciation.text`, and the reason deleting the word leaves this row alone — the
 * caption stays truthful and `lexemeId` simply points at a tombstone.
 *
 * `startSeconds` and `endSeconds` bound the word's block in the words section; the reveals are when
 * each side is first heard there, and null for a side the format never says in it. Every line, the
 * word's own and everything else, is a `LoopCue`.
 */
export interface LoopItem extends SyncFields, OwnedFields {
  id: string;
  loopId: string;
  lexemeId: string;
  position: number;
  sourceText: string;
  targetText: string;
  emotion: string | null;
  startSeconds: number;
  sourceRevealSeconds: number | null;
  targetRevealSeconds: number | null;
  endSeconds: number;
}

/**
 * One line of a loop, in the order it is heard: a word, its translation, an example, a remark, a
 * line of a story, an announcement.
 *
 * Written by the render and only by it: new music tombstones a loop's lines and writes new ones.
 * `group` is what the player shows together — a word's own lines, a line and its translation — as
 * the generator numbered it, so the player never guesses which line translates which. `text` is
 * denormalised for `LoopItem.sourceText`'s reason. `loopItemId` names the word a line belongs to,
 * and is null for a line of no word; `side` says which half of the pair a word's own line is.
 */
export interface LoopCue extends SyncFields, OwnedFields {
  id: string;
  loopId: string;
  position: number;
  group: number;
  kind: string;
  section: string;
  loopItemId: string | null;
  side: "source" | "target" | null;
  role: "native" | "guide";
  language: string;
  text: string;
  take: number;
  startSeconds: number;
  endSeconds: number;
}

/**
 * A bed the owner kept: the music of one loop, to be asked for again for new words.
 *
 * `styleId` and `seed` replay it — the generator's bed does not depend on the words — and
 * `bedFingerprint` is what proves a replay made the same one. It is a record of its own rather than
 * a flag on the loop, so deleting the loop does not take the favourite with it: `sourceLoopId` then
 * points at a tombstone, as a loop item's `lexemeId` does at a deleted word, and the favourite simply
 * has nothing left to preview.
 */
export interface Bed extends SyncFields, OwnedFields {
  id: string;
  styleId: string;
  seed: number;
  engineVersion: string | null;
  bedFingerprint: string | null;
  sourceLoopId: string;
}

/**
 * A story: a handful of words told back to you as a short illustrated tale.
 *
 * **Its state is derived and there is no status column**, exactly as for a `Loop`. A story with no
 * live `StoryPart`s was asked for and never written; a part with no `imageRef` has not been drawn.
 * Both facts are already in the graph, so a fifth one would only be something to keep in step.
 *
 * `typeId` and `styleId` are chosen when the story is *asked for* rather than when it is written,
 * so Try again reaches for the same kind of story and the same look rather than quietly becoming a
 * different one. Both are ids into tracked config the server ships, never enums in this code.
 */
export interface Story extends SyncFields, OwnedFields {
  id: string;
  language: string;
  typeId: string | null;
  styleId: string | null;
  /** Null until the story has been written, which is also what having no parts says. */
  title: string | null;
  titleTranslation: string | null;
  emoji: string | null;
  /** The model that answered, not the one asked first. Provenance, like `Example.modelId`. */
  modelId: string | null;
  /** Sparse, renumbered on reorder. Ordering is respected rather than enforced. */
  position: number;
  /** What the owner asked the writer for, in their own words. Null when nothing was asked. */
  guidance: string | null;
}

/**
 * One part of a story: a picture, a paragraph, and the same paragraph translated.
 *
 * The translation is hidden until the reader asks for it, which is why it travels with the part
 * rather than being fetched — a reveal that had to wait for the network would not be a reveal.
 *
 * `imageRef` carries a digest of the picture's bytes, so a redraw is a *new* reference and a device
 * holding the old one simply misses. That is what lets `mediaStore.ts` be a cache with no
 * invalidation, and it is the rule every picture in Acervo follows.
 */
export interface StoryPart extends SyncFields, OwnedFields {
  id: string;
  storyId: string;
  position: number;
  heading: string | null;
  headingTranslation: string | null;
  text: string;
  translation: string;
  imagePrompt: string | null;
  /** Null until drawn. `failureReason` says why when it stayed that way. */
  imageRef: string | null;
  imageModelId: string | null;
  attempts: number;
  failureReason: string | null;
  /** The pair and voice that read it. A story is read in one, and the first part recorded chooses. */
  audioProviderId: string | null;
  audioModelId: string | null;
  audioVoice: string | null;
  /**
   * The part read aloud, **one recording per passage**, in reading order. No passages is the whole
   * of what "not recorded" means: there is no status and no separate reference to disagree with it.
   * A clear voice records one passage covering the whole part, so the shape is the same either way
   * and the reader simply has nothing to tap.
   *
   * The passages join back to `text` exactly, so where one sits in the text is the lengths of those
   * before it. A file each rather than one joined file because **a passage must start where its
   * first word does**: a joined file has to be seeked into, and a browser seeks a compressed stream
   * to a page boundary, landing after the target or before it — and reporting the time that was
   * asked for either way, so there is nothing to correct against.
   */
  audioSegments: AudioSegment[];
}

export interface AudioSegment {
  text: string;
  /** What the voice was actually sent. Empty when it was sent nothing. */
  direction: string;
  /** This passage's own recording. It carries a digest of its bytes, as every media name does. */
  audioRef: string;
  audioMime: string;
  durationSeconds: number;
}

/**
 * One word a story was asked to teach, and the forms it actually used.
 *
 * `sourceText` is denormalised for `LoopItem.sourceText`'s reason: it records what was *asked for*,
 * so editing the word afterwards cannot rewrite what the story set out to teach — and it is why
 * deleting the word leaves this row alone, with `lexemeId` pointing at a tombstone.
 *
 * **An empty `forms` means the story did not manage to use the word**, which is a fact worth
 * showing rather than hiding, and the reason this is a list and not a boolean. The forms are the
 * surface strings the writer actually wrote, verified against the text on the server, and they are
 * what the reader searches for to mark the word in the story.
 */
export interface StoryWord extends SyncFields, OwnedFields {
  id: string;
  storyId: string;
  lexemeId: string;
  position: number;
  sourceText: string;
  forms: string[];
  /**
   * The words of the *translation* that render this one, reported by the translator and kept only
   * where they really appear in what it wrote. The reader searches the translation for them the way
   * it searches the story for `forms`. Empty is ordinary — the translation did not say, or the story
   * predates it — and marks nothing.
   */
  translationForms: string[];
}

export interface VocabularyGraph {
  vocabularies: Vocabulary[];
  topics: Topic[];
  lexemes: Lexeme[];
  senses: Sense[];
  attestations: Attestation[];
  examples: Example[];
  imagePrompts: ImagePrompt[];
  pronunciations: Pronunciation[];
  studyStates: StudyState[];
  loops: Loop[];
  loopItems: LoopItem[];
  loopCues: LoopCue[];
  stories: Story[];
  storyParts: StoryPart[];
  storyWords: StoryWord[];
  beds: Bed[];
}

export type VocabularyInput = Omit<Vocabulary, "id" | keyof SyncFields | keyof OwnedFields>;
export type TopicInput = Omit<Topic, "id" | keyof SyncFields | keyof OwnedFields>;
export type LexemeInput = Omit<Lexeme, "id" | keyof SyncFields | keyof OwnedFields>;
export type SenseInput = Omit<Sense, "id" | keyof SyncFields | keyof OwnedFields>;
export type AttestationInput = Omit<Attestation, "id" | keyof SyncFields | keyof OwnedFields>;
export type ExampleInput = Omit<Example, "id" | keyof SyncFields | keyof OwnedFields>;
export type ImagePromptInput = Omit<ImagePrompt, "id" | keyof SyncFields | keyof OwnedFields>;
export type StudyStateInput = Omit<StudyState, "id" | keyof SyncFields | keyof OwnedFields>;
export type LoopInput = Omit<Loop, "id" | keyof SyncFields | keyof OwnedFields>;
export type LoopItemInput = Omit<LoopItem, "id" | keyof SyncFields | keyof OwnedFields>;
export type LoopCueInput = Omit<LoopCue, "id" | keyof SyncFields | keyof OwnedFields>;
export type StoryInput = Omit<Story, "id" | keyof SyncFields | keyof OwnedFields>;
export type StoryPartInput = Omit<StoryPart, "id" | keyof SyncFields | keyof OwnedFields>;
export type StoryWordInput = Omit<StoryWord, "id" | keyof SyncFields | keyof OwnedFields>;
export type BedInput = Omit<Bed, "id" | keyof SyncFields | keyof OwnedFields>;

const RECORD_ID = /^[a-z0-9]{15}$/;
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const LANGUAGE = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;

function invariant(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function oneOf<T extends string>(value: unknown, values: readonly T[], label: string): asserts value is T {
  invariant(typeof value === "string" && values.includes(value as T), `${label} is invalid.`);
}

function photoRegion(value: unknown, hasPhoto: boolean): void {
  if (value === null || value === undefined) return;
  invariant(hasPhoto, "A photo region needs a photo.");
  invariant(typeof value === "object" && !Array.isArray(value), "A photo region must be an object.");
  for (const key of ["words", "sentence"] as const) {
    const polygons = (value as Record<string, unknown>)[key] ?? [];
    invariant(Array.isArray(polygons), "A photo region's polygons must be a list.");
    for (const polygon of polygons) {
      invariant(Array.isArray(polygon) && polygon.length >= 3, "A photo region's polygon needs three points.");
      for (const point of polygon) {
        invariant(
          Array.isArray(point) && point.length === 2 && point.every((axis) => typeof axis === "number" && axis >= 0 && axis <= 1),
          "A photo region's points must be [x, y] between 0 and 1."
        );
      }
    }
  }
}

function optionalString(value: unknown, label: string): asserts value is string | null {
  invariant(value === null || (typeof value === "string" && value.trim().length > 0), `${label} must be null or non-empty.`);
}

function stringArray(value: unknown, label: string, allowEmpty = true): asserts value is string[] {
  invariant(Array.isArray(value) && value.every((item) => typeof item === "string" && item.trim()), `${label} must contain strings.`);
  invariant(allowEmpty || value.length > 0, `${label} must not be empty.`);
  invariant(new Set(value).size === value.length, `${label} must not contain duplicates.`);
}

function language(value: unknown, label: string): asserts value is string {
  invariant(typeof value === "string" && LANGUAGE.test(value), `${label} must be a BCP-47 language tag.`);
}

export function validateRecordId(value: unknown): asserts value is string {
  invariant(typeof value === "string" && RECORD_ID.test(value), "Record id must contain 15 lowercase letters or digits.");
}

export function validateInstant(value: unknown, label = "Timestamp"): asserts value is string {
  invariant(typeof value === "string" && INSTANT.test(value) && !Number.isNaN(Date.parse(value)), `${label} must be an ISO-8601 UTC instant with milliseconds.`);
}

function syncFields(record: SyncFields & OwnedFields & { id: string }) {
  validateRecordId(record.id);
  validateRecordId(record.ownerId);
  invariant(typeof record.deleted === "boolean", "Deleted must be boolean.");
  validateInstant(record.createdAt, "Created time");
  validateInstant(record.editedAt, "Edited time");
  invariant(/^[a-z0-9]{1,32}$/.test(record.editedBy), "Editor id is invalid.");
  invariant(Number.isSafeInteger(record.revision) && record.revision >= 0, "Revision is invalid.");
}

/**
 * The records a check may look up: each kind refers only to kinds checked before it, so a lookup over
 * the whole graph is exactly what the old in-order maps held.
 */
type AnyRecord = VocabularyGraph[EntityKind][number];

interface Find {
  topics(id: string): Topic | undefined;
  lexemes(id: string): Lexeme | undefined;
  senses(id: string): Sense | undefined;
  attestations(id: string): Attestation | undefined;
  examples(id: string): Example | undefined;
  loops(id: string): Loop | undefined;
  loopItems(id: string): LoopItem | undefined;
  stories(id: string): Story | undefined;
}

/** What one record must satisfy on its own and against the records it names, per kind. */
const CHECKS: { [K in EntityKind]: (record: VocabularyGraph[K][number], find: Find) => void } = {
  vocabularies(record: Vocabulary): void {
    language(record.language, "Vocabulary language");
    language(record.definitionLang, "Vocabulary definition language");
    stringArray(record.glossLangs, "Vocabulary gloss languages", false);
    record.glossLangs.forEach((code) => language(code, "Vocabulary gloss language"));
    language(record.notesLang, "Vocabulary notes language");
    optionalString(record.displayName, "Vocabulary name");
    optionalString(record.flag, "Vocabulary flag");
    invariant(Number.isSafeInteger(record.order) && record.order >= 0, "Vocabulary order is invalid.");
  },
  topics(record: Topic): void {
    invariant(record.name.trim().length > 0, "Topic name is required.");
    optionalString(record.icon, "Topic icon");
    invariant(Number.isSafeInteger(record.order) && record.order >= 0, "Topic order is invalid.");
  },
  lexemes(record: Lexeme, find: Find): void {
    language(record.language, "Lexeme language");
    invariant(record.headword.trim().length > 0 && record.lemma.trim().length > 0, "Lexeme headword and lemma are required.");
    optionalString(record.reading, "Reading");
    optionalString(record.ipa, "IPA");
    if (record.language.toLowerCase().startsWith("zh")) invariant(Boolean(record.reading?.trim()), "Chinese lexemes require a reading.");
    oneOf(record.pos, PARTS_OF_SPEECH, "Part of speech");
    if (record.gender !== null) oneOf(record.gender, GENDERS, "Gender");
    if (record.register !== null) oneOf(record.register, REGISTERS, "Register");
    optionalString(record.dialect, "Dialect");
    optionalString(record.emoji, "Emoji");
    stringArray(record.topicIds, "Topic ids");
    record.topicIds.forEach((topicId) => {
      validateRecordId(topicId);
      const topic = find.topics(topicId);
      invariant(topic, "Lexeme references a missing topic.");
      invariant(topic.ownerId === record.ownerId, "Lexeme and topic must have the same owner.");
    });
    oneOf(record.status, LEXEME_STATUSES, "Lexeme status");
    optionalString(record.shortGloss, "Short gloss");
    optionalString(record.primaryGloss, "Primary gloss");
    optionalString(record.emotion, "Lexeme emotion");
    stringArray(record.notes, "Notes");
    if (record.clipsSearchedAt !== null) validateInstant(record.clipsSearchedAt, "Clip search time");
  },
  senses(record: Sense, find: Find): void {
    const lexeme = find.lexemes(record.lexemeId);
    invariant(lexeme, "Sense references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Sense and lexeme must have the same owner.");
    invariant(record.definition.trim().length > 0, "Sense definition is required.");
    language(record.definitionLang, "Definition language");
    invariant(Number.isSafeInteger(record.order) && record.order >= 0, "Sense order is invalid.");
    optionalString(record.domain, "Sense domain");
    optionalString(record.emoji, "Sense emoji");
    invariant(Array.isArray(record.glosses) && record.glosses.length > 0, "A sense requires at least one gloss group.");
    const glossLanguages = new Set<string>();
    record.glosses.forEach((gloss) => {
      language(gloss.lang, "Gloss language");
      invariant(!glossLanguages.has(gloss.lang), "Gloss languages must be unique per sense.");
      glossLanguages.add(gloss.lang);
      stringArray(gloss.terms, "Gloss terms", false);
    });
  },
  attestations(record: Attestation, find: Find): void {
    const lexeme = find.lexemes(record.lexemeId);
    invariant(lexeme, "Attestation references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Attestation and lexeme must have the same owner.");
    invariant(record.text.trim().length > 0 || Boolean(record.photoRef), "Attestation text is required.");
    optionalString(record.photoRef, "Attestation photo");
    photoRegion(record.photoRegion, Boolean(record.photoRef));
    optionalString(record.translation, "Attestation translation");
    optionalString(record.sourceUrl, "Source URL");
    optionalString(record.sourceTitle, "Source title");
    oneOf(record.sourceKind, SOURCE_KINDS, "Source kind");
    validateInstant(record.capturedAt, "Capture time");
  },
  examples(record: Example, find: Find): void {
    const sense = find.senses(record.senseId);
    invariant(sense, "Example references a missing sense.");
    invariant(record.ownerId === sense.ownerId, "Example and sense must have the same owner.");
    invariant(record.text.trim().length > 0, "Example text is required.");
    language(record.textLang, "Example language");
    optionalString(record.translation, "Example translation");
    optionalString(record.translationLang, "Translation language");
    invariant(Boolean(record.translation) === Boolean(record.translationLang), "Translation and translation language must be supplied together.");
    if (record.translationLang) language(record.translationLang, "Translation language");
    oneOf(record.origin, EXAMPLE_ORIGINS, "Example origin");
    optionalString(record.sourceAttestationId, "Source attestation id");
    if (record.origin === "attestation") invariant(record.sourceAttestationId, "Attestation examples require a source attestation.");
    if (record.sourceAttestationId) {
      const attestation = find.attestations(record.sourceAttestationId);
      invariant(attestation, "Example references a missing attestation.");
      invariant(record.ownerId === attestation.ownerId, "Example and attestation must have the same owner.");
      invariant(attestation.lexemeId === sense.lexemeId, "Example sense and attestation must belong to one lexeme.");
  }
    [record.modelId, record.videoRef, record.videoTitle, record.videoChannel, record.clipRef, record.imageRef, record.emotion, record.note].forEach((value) => optionalString(value, "Example optional field"));
    [record.videoStart, record.videoEnd].forEach((value) => invariant(value === null || (Number.isSafeInteger(value) && value >= 0), "Example video timing is invalid."));
    // `videoRef` is what every clip field hangs on: a title, a channel, a timing or the corpus's
    // own segment id without one describes a clip that names no video.
    if (record.videoTitle || record.videoChannel || record.clipRef || record.videoStart !== null || record.videoEnd !== null) {
      invariant(record.videoRef, "An example clip title, channel, segment or timing requires a video reference.");
  }
    // Zero reads as "no end", matching the server: the projection emits the stored integer and a
    // clip example without an end carries 0, exactly as one without a start does.
    if (record.videoEnd) invariant(record.videoEnd > (record.videoStart ?? 0), "An example clip must end after it starts.");
    optionalString(record.matchedForm, "Matched form");
    optionalString(record.matchedTranslationForm, "Matched translation form");
    if (record.matchedForm) invariant(record.text.includes(record.matchedForm), "The matched form must occur in the example text.");
    if (record.matchedTranslationForm) {
      invariant(record.translation, "A matched translation form requires a translation.");
      invariant(record.translation.includes(record.matchedTranslationForm), "The matched translation form must occur in the translation.");
  }
  },
  imagePrompts(record: ImagePrompt, find: Find): void {
    const lexeme = find.lexemes(record.lexemeId);
    invariant(lexeme, "Image prompt references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Image prompt and lexeme must have the same owner.");
    optionalString(record.senseId, "Image prompt sense id");
    if (record.senseId) {
      const sense = find.senses(record.senseId);
      invariant(sense?.lexemeId === record.lexemeId, "Image prompt sense belongs to another lexeme.");
      invariant(sense.ownerId === record.ownerId, "Image prompt and sense must have the same owner.");
  }
    optionalString(record.exampleId, "Image prompt example id");
    if (record.exampleId) {
      const example = find.examples(record.exampleId);
      invariant(example?.senseId === record.senseId, "Image prompt example belongs to another sense.");
      invariant(example.ownerId === record.ownerId, "Image prompt and example must have the same owner.");
  }
    // A brief is three fields or none of them: without the style and the version there is no way to
    // rebuild the prompt that was actually sent, so half a brief reproduces nothing.
    if (record.prompt.trim()) {
      invariant(record.styleId.trim() && record.promptVersion.trim(), "An image brief must name its style and prompt version.");
  }
    invariant(Number.isSafeInteger(record.seed) && record.seed >= 0 && record.seed <= 2147483647, "Image prompt seed is invalid.");
    invariant(Number.isSafeInteger(record.attempts) && record.attempts >= 0, "Image prompt attempt count is invalid.");
    invariant(typeof record.suppressed === "boolean", "Image prompt suppression is invalid.");
    optionalString(record.failureReason, "Image failure reason");
    optionalString(record.imageRef, "Rendered image reference");
    optionalString(record.imageModelId, "Rendering model id");
    // One direction only. A rendering model with nothing rendered is nonsense; a rendered image
    // with no model is a picture the owner attached themselves.
    invariant(!record.imageModelId || Boolean(record.imageRef), "A rendering model without a rendered image is not a record of anything.");
  },
  pronunciations(record: Pronunciation, find: Find): void {
    const lexeme = find.lexemes(record.lexemeId);
    invariant(lexeme, "Pronunciation references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Pronunciation and lexeme must have the same owner.");
    oneOf(record.targetKind, PRONUNCIATION_TARGETS, "Pronunciation target kind");
    const word = record.targetKind === "lexeme" ? find.lexemes(record.targetId)?.id
      : record.targetKind === "sense" ? find.senses(record.targetId)?.lexemeId
      : record.targetKind === "attestation" ? find.attestations(record.targetId)?.lexemeId
      : find.senses(find.examples(record.targetId)?.senseId ?? "")?.lexemeId;
    invariant(word === record.lexemeId, "A pronounced record must belong to the pronunciation's lexeme.");
    invariant(record.text.length > 0, "Pronunciation text is required.");
    language(record.lang, "Pronunciation language");
    optionalString(record.emotion, "Pronunciation emotion");
    [record.audioRef, record.audioMime, record.providerId, record.modelId].forEach((value) =>
      invariant(typeof value === "string" && value.trim().length > 0, "A pronunciation names its file and who recorded it."));
    optionalString(record.voice, "Pronunciation voice");
  },
  studyStates(record: StudyState, find: Find): void {
    const lexeme = find.lexemes(record.lexemeId);
    invariant(lexeme, "Study state references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Study state and lexeme must have the same owner.");
    invariant(record.system.trim().length > 0, "Study system is required.");
    invariant(record.noteId === null || (Number.isSafeInteger(record.noteId) && record.noteId >= 0), "Study note id is invalid.");
    invariant(Array.isArray(record.cardIds) && record.cardIds.every((id) => Number.isSafeInteger(id) && id >= 0), "Study card ids are invalid.");
    [record.reps, record.lapses].forEach((value) => invariant(Number.isSafeInteger(value) && value >= 0, "Study count is invalid."));
    [record.stability, record.difficulty].forEach((value) => invariant(Number.isFinite(value) && value >= 0, "Study metric is invalid."));
    invariant(Number.isFinite(record.retrievability) && record.retrievability >= 0 && record.retrievability <= 1, "Retrievability is invalid.");
    if (record.lastReview) validateInstant(record.lastReview, "Last review");
    if (record.syncedAt) validateInstant(record.syncedAt, "Study sync time");
  },
  loops(record: Loop): void {
    language(record.language, "Loop language");
    [record.styleId, record.engineVersion, record.bedFingerprint]
      .forEach((value) => optionalString(value, "Loop bed field"));
    invariant(typeof record.format === "string" && record.format.trim().length > 0, "A loop names its format.");
    optionalString(record.fallbackFrom, "Loop fallback");
    invariant(typeof record.switches === "object" && record.switches !== null && !Array.isArray(record.switches)
      && Object.values(record.switches).every((value) => typeof value === "boolean" || typeof value === "string"),
    "A loop's switches are on/off or one of their choices.");
    /* `isSafeInteger` is the whole bound, not 2^31: a JSON number is a double here, so the largest
       seed that can reach this replica intact is 2^53 − 1. The generator mints 64-bit seeds when it
       is not given one, which is why Acervo sends it one. */
    invariant(Number.isSafeInteger(record.seed) && record.seed >= 0, "Loop seed is invalid.");
    invariant(Number.isSafeInteger(record.position) && record.position >= 0, "Loop position is invalid.");
    optionalString(record.audioRef, "Loop audio reference");
    optionalString(record.audioMime, "Loop audio type");
    // A rendered track is bytes plus the type of those bytes. This is the *whole* of what "rendered"
    // means: there is no status column, so an absent reference is the state.
    invariant(Boolean(record.audioRef) === Boolean(record.audioMime), "A loop's audio reference and type must be supplied together.");
    invariant(record.durationSeconds === null || (Number.isFinite(record.durationSeconds) && record.durationSeconds >= 0), "Loop duration is invalid.");
    invariant(Boolean(record.audioRef) || record.durationSeconds === null, "A loop that has not been rendered has no duration.");
  },
  loopItems(record: LoopItem, find: Find): void {
    const loop = find.loops(record.loopId);
    invariant(loop, "Loop item references a missing loop.");
    invariant(record.ownerId === loop.ownerId, "Loop item and loop must have the same owner.");
    // Looked up among *all* lexemes, tombstones included. A loop is a recording: deleting the word
    // leaves it playing, captioned with what was actually said, and this reference then points at a
    // tombstone — which is the honest state rather than a dangling one.
    const lexeme = find.lexemes(record.lexemeId);
    invariant(lexeme, "Loop item references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Loop item and lexeme must have the same owner.");
    invariant(Number.isSafeInteger(record.position) && record.position >= 0, "Loop item position is invalid.");
    invariant(record.sourceText.length > 0 && record.targetText.length > 0, "A loop item records both words it spoke.");
    optionalString(record.emotion, "Loop item emotion");
    [record.startSeconds, record.endSeconds].forEach((value) =>
      invariant(Number.isFinite(value) && value >= 0, "Loop item timing is invalid."));
    invariant(record.endSeconds >= record.startSeconds, "A loop item's times must not run backwards.");
    // Either side may come first — a format may ask for the translation before the word — but each
    // is heard inside the word's own block.
    [record.sourceRevealSeconds, record.targetRevealSeconds].forEach((value) => invariant(
      value === null || (Number.isFinite(value) && value >= record.startSeconds && value <= record.endSeconds),
      "A loop item's reveal lies within its block."));
  },
  loopCues(record: LoopCue, find: Find): void {
    const loop = find.loops(record.loopId);
    invariant(loop, "Loop line references a missing loop.");
    invariant(record.ownerId === loop.ownerId, "Loop line and loop must have the same owner.");
    if (record.loopItemId !== null) {
      const item = find.loopItems(record.loopItemId);
      invariant(item, "Loop line references a missing word.");
      invariant(item.ownerId === record.ownerId, "Loop line and word must have the same owner.");
    }
    invariant(record.side === null || record.loopItemId !== null, "Only a word's own line has a side.");
    invariant(record.side === null || record.side === "source" || record.side === "target", "Loop line side is invalid.");
    invariant(record.role === "native" || record.role === "guide", "Loop line role is invalid.");
    language(record.language, "Loop line language");
    invariant(record.kind.trim().length > 0 && record.section.trim().length > 0, "A loop line says what it is.");
    invariant(record.text.length > 0, "A loop line records what it said.");
    [record.position, record.group, record.take].forEach((value) =>
      invariant(Number.isSafeInteger(value) && value >= 0, "Loop line number is invalid."));
    invariant(Number.isFinite(record.startSeconds) && record.startSeconds >= 0
      && Number.isFinite(record.endSeconds) && record.endSeconds >= record.startSeconds, "A loop line's times must not run backwards.");
  },
  stories(record: Story): void {
    language(record.language, "Story language");
    optionalString(record.typeId, "Story kind");
    optionalString(record.styleId, "Story style");
    optionalString(record.title, "Story title");
    optionalString(record.titleTranslation, "Story title translation");
    optionalString(record.emoji, "Story emoji");
    optionalString(record.modelId, "Story model");
    optionalString(record.guidance, "Story guidance");
    invariant(Number.isSafeInteger(record.position) && record.position >= 0, "Story position is invalid.");
  },
  storyParts(record: StoryPart, find: Find): void {
    const story = find.stories(record.storyId);
    invariant(story, "Story part references a missing story.");
    invariant(record.ownerId === story.ownerId, "Story part and story must have the same owner.");
    invariant(Number.isSafeInteger(record.position) && record.position >= 0, "Story part position is invalid.");
    invariant(typeof record.text === "string", "Story part text is invalid.");
    invariant(typeof record.translation === "string", "Story part translation is invalid.");
    optionalString(record.heading, "Story part heading");
    optionalString(record.headingTranslation, "Story part heading translation");
    optionalString(record.imagePrompt, "Story part image brief");
    optionalString(record.imageRef, "Story part image reference");
    optionalString(record.imageModelId, "Story part image model");
    optionalString(record.failureReason, "Story part failure");
    // A drawn picture is bytes plus the model that made them. There is no status column, so an
    // absent reference is the whole of what "not drawn" means — and naming a model that drew
    // nothing would be the one fact contradicting it.
    invariant(Boolean(record.imageRef) || !record.imageModelId, "A story part with no picture cannot name the model that drew one.");
    invariant(Number.isSafeInteger(record.attempts) && record.attempts >= 0, "Story part attempts are invalid.");
    optionalString(record.audioProviderId, "Story part recording provider");
    optionalString(record.audioModelId, "Story part recording model");
    optionalString(record.audioVoice, "Story part recording voice");
    invariant(
      Array.isArray(record.audioSegments) && record.audioSegments.every((one) =>
        typeof one.text === "string" && typeof one.direction === "string"
        && typeof one.audioRef === "string" && one.audioRef.length > 0
        && Number.isFinite(one.durationSeconds) && one.durationSeconds >= 0
      ),
      "Story part passages are invalid."
    );
    invariant(
      record.audioSegments.length > 0
        || (!record.audioProviderId && !record.audioModelId && !record.audioVoice),
      "A story part that has not been read aloud cannot say who spoke it."
    );
  },
  storyWords(record: StoryWord, find: Find): void {
    const story = find.stories(record.storyId);
    invariant(story, "Story word references a missing story.");
    invariant(record.ownerId === story.ownerId, "Story word and story must have the same owner.");
    // Looked up among *all* lexemes, tombstones included, for a loop item's reason: a story that
    // has been written stays readable and still truthfully says which word it was built around.
    const lexeme = find.lexemes(record.lexemeId);
    invariant(lexeme, "Story word references a missing lexeme.");
    invariant(record.ownerId === lexeme.ownerId, "Story word and lexeme must have the same owner.");
    invariant(Number.isSafeInteger(record.position) && record.position >= 0, "Story word position is invalid.");
    invariant(record.sourceText.length > 0, "A story word records the word it was asked to teach.");
    invariant(Array.isArray(record.forms) && record.forms.every((one) => typeof one === "string"), "Story word forms are invalid.");
    invariant(
      Array.isArray(record.translationForms) && record.translationForms.every((one) => typeof one === "string"),
      "Story word translated forms are invalid."
    );
  },
  beds(record: Bed, find: Find): void {
    invariant(typeof record.styleId === "string" && record.styleId.length > 0, "A kept bed names its style.");
    optionalString(record.engineVersion, "Kept bed engine version");
    optionalString(record.bedFingerprint, "Kept bed fingerprint");
    // A loop's own bound, since a kept bed's seed is a loop's seed.
    invariant(Number.isSafeInteger(record.seed) && record.seed >= 0, "Kept bed seed is invalid.");
    // Among *all* loops, tombstones included: a favourite outlives the loop it was kept from.
    const loop = find.loops(record.sourceLoopId);
    invariant(loop, "Kept bed references a missing loop.");
    invariant(record.ownerId === loop.ownerId, "Kept bed and loop must have the same owner.");
  }
};

/** Checked in this order, which is the order the old single pass built its maps in. */
const CHECKED_KINDS = Object.keys(CHECKS) as EntityKind[];

type Indexed = { [K in EntityKind]?: ReadonlyMap<string, VocabularyGraph[K][number]> };

/** Records of one graph by id, per kind — built by a caller that keeps it, or on demand. */
export type GraphIndex = { get<K extends EntityKind>(kind: K, id: string): VocabularyGraph[K][number] | undefined };

function findIn(index: GraphIndex): Find {
  return {
    topics: (id) => index.get("topics", id),
    lexemes: (id) => index.get("lexemes", id),
    senses: (id) => index.get("senses", id),
    attestations: (id) => index.get("attestations", id),
    examples: (id) => index.get("examples", id),
    loops: (id) => index.get("loops", id),
    loopItems: (id) => index.get("loopItems", id),
    stories: (id) => index.get("stories", id)
  };
}

function indexOf(graph: VocabularyGraph): GraphIndex {
  const maps: Indexed = {};
  return {
    get<K extends EntityKind>(kind: K, id: string) {
      let map = maps[kind] as Map<string, VocabularyGraph[K][number]> | undefined;
      if (!map) {
        map = new Map((graph[kind] as VocabularyGraph[K][number][]).map((record) => [record.id, record]));
        (maps as Record<string, unknown>)[kind] = map;
      }
      return map.get(id);
    }
  };
}

function checkVocabularyLanguages(vocabularies: readonly Vocabulary[]): void {
  // Not a storage constraint (`docs/architecture/data-model.md` forbids those on replicated
  // collections) — a graph-level one, so two devices that each added the same language offline
  // cannot both be believed at once.
  const claimed = new Set<string>();
  vocabularies.forEach((record) => {
    if (record.deleted) return;
    invariant(!claimed.has(record.language), `Two vocabularies claim ${record.language}.`);
    claimed.add(record.language);
  });
}

export function validateGraph(graph: VocabularyGraph): void {
  const ids = new Set<string>();
  let ownerId: string | null = null;
  const find = findIn(indexOf(graph));
  CHECKED_KINDS.forEach((kind) => {
    (graph[kind] as AnyRecord[]).forEach((record) => {
      syncFields(record);
      ownerId ??= record.ownerId;
      invariant(record.ownerId === ownerId, "A vocabulary graph must contain records for one owner only.");
      invariant(!ids.has(record.id), `Duplicate record id ${record.id}.`);
      ids.add(record.id);
      (CHECKS[kind] as (record: AnyRecord, find: Find) => void)(record, find);
    });
  });
  checkVocabularyLanguages(graph.vocabularies);
}

/**
 * The fields other records' checks read from a record, per kind. Changing one of these on a record
 * already held can invalidate records that are *not* in the change set, so `validateChanges` then
 * falls back to the whole graph — re-parenting is rare, and a replica that no longer loads is not.
 */
const REREAD: { [K in EntityKind]?: readonly (keyof VocabularyGraph[K][number])[] } = {
  senses: ["lexemeId"],
  attestations: ["lexemeId"],
  examples: ["senseId"]
};

/**
 * `validateGraph` for a graph already known to be valid and the records about to replace or join
 * it: the same checks, run on the incoming records alone, resolving every reference through the
 * incoming records first and then the graph. Equivalent to validating the merged graph, at the
 * cost of the change rather than the replica — which is what every save and pull used to pay.
 */
export function validateChanges(
  graph: VocabularyGraph, changes: Partial<VocabularyGraph>, index: GraphIndex = indexOf(graph)
): void {
  const incoming = indexOf({ ...EMPTY_KINDS(), ...changes } as VocabularyGraph);
  const merged: GraphIndex = { get: (kind, id) => incoming.get(kind, id) ?? index.get(kind, id) };
  let owner: string | null = graph.vocabularies[0]?.ownerId ?? graph.topics[0]?.ownerId ?? graph.lexemes[0]?.ownerId ?? null;
  for (const kind of CHECKED_KINDS) {
    const records = (changes[kind] ?? []) as AnyRecord[];
    for (const record of records) {
      const held = index.get(kind, record.id) as AnyRecord | undefined;
      const fields = (REREAD[kind] ?? []) as string[];
      if (held && fields.some((field) => (held as unknown as Record<string, unknown>)[field] !== (record as unknown as Record<string, unknown>)[field])) {
        validateGraph(mergedGraph(graph, changes));
        return;
      }
    }
  }
  const find = findIn(merged);
  CHECKED_KINDS.forEach((kind) => {
    ((changes[kind] ?? []) as AnyRecord[]).forEach((record) => {
      syncFields(record);
      owner ??= record.ownerId;
      invariant(record.ownerId === owner, "A vocabulary graph must contain records for one owner only.");
      CHECKED_KINDS.forEach((other) => {
        if (other === kind) return;
        invariant(!merged.get(other, record.id), `Duplicate record id ${record.id}.`);
      });
      (CHECKS[kind] as (record: AnyRecord, find: Find) => void)(record, find);
    });
  });
  if (changes.vocabularies?.length) checkVocabularyLanguages(mergedGraph(graph, { vocabularies: changes.vocabularies }).vocabularies);
}

const EMPTY_KINDS = (): VocabularyGraph => ({
  vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [],
  pronunciations: [], studyStates: [], loops: [], loopItems: [], loopCues: [], stories: [], storyParts: [], storyWords: [],
  beds: []
});

/** The graph with the change set laid over it, a replaced record keeping its place. */
function mergedGraph(graph: VocabularyGraph, changes: Partial<VocabularyGraph>): VocabularyGraph {
  const next = { ...graph };
  (Object.keys(changes) as EntityKind[]).forEach((kind) => {
    const records = (changes[kind] ?? []) as AnyRecord[];
    if (!records.length) return;
    const list = (graph[kind] as AnyRecord[]).slice();
    const at = new Map(list.map((record, position) => [record.id, position]));
    records.forEach((record) => {
      const position = at.get(record.id);
      if (position === undefined) { at.set(record.id, list.length); list.push(record); } else list[position] = record;
    });
    (next as Record<string, unknown>)[kind] = list;
  });
  return next;
}

export function effectiveShortGloss(graph: VocabularyGraph, lexemeId: string): string | null {
  const lexeme = graph.lexemes.find((candidate) => candidate.id === lexemeId && !candidate.deleted);
  if (!lexeme) return null;
  if (lexeme.shortGloss?.trim()) return lexeme.shortGloss.trim();
  const sense = graph.senses
    .filter((candidate) => candidate.lexemeId === lexemeId && !candidate.deleted)
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id))[0];
  return sense?.glosses[0]?.terms[0] ?? null;
}
