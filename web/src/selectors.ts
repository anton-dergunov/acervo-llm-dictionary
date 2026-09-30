/**
 * Pure derivation from a vocabulary graph to the view models the interface renders.
 *
 * Nothing here touches storage or the network, so the whole list/article/search surface is
 * testable without a replica. Tombstone filtering lives here and only here.
 */

import {
  effectiveShortGloss,
  type Attestation, type Example, type ImagePrompt, type Lexeme, type LexemeStatus,
  type AudioSegment, type Bed, type Loop, type LoopCue, type LoopItem, type OwnedFields, type Sense, type Story, type StoryPart,
  type StoryWord, type StudyState, type SyncFields,
  type Topic, type Vocabulary, type VocabularyGraph
} from "./domain";
import { glossLanguagesFor, languageOf, notesLanguageFor, presentationOf, type LanguagePresentation } from "./languages";
// Type-only, so it is erased at build time and the cycle with `yaml.ts` — which imports `Article`
// from here — never exists at runtime.
import type { ArticleDraft, AttestationDraft, ExampleDraft, SenseDraft } from "./yaml";
import type { ServerMap } from "./api";
import type { MapData, MapPoint } from "./meaningMap";

export type SortKey = "recent" | "alpha" | "hard";
/** A topic record id, or one of the two synthetic collections the rail offers. */
export type TopicSelection = "all" | "inbox" | string;

export interface ListRow {
  id: string;
  headword: string;
  reading: string | null;
  emoji: string | null;
  shortGloss: string;
  senseCount: number;
  status: LexemeStatus;
  /** Zero when the word has never been scheduled, otherwise one to four bars. */
  strength: number;
  strengthLabel: string;
}

export interface ArticleSense {
  sense: Sense;
  examples: Example[];
  images: ImagePrompt[];
}

export interface Article {
  lexeme: Lexeme;
  topics: Topic[];
  senses: ArticleSense[];
  attestations: Attestation[];
  /** Lexeme-level prompts — the card image, as opposed to a per-sense one. */
  images: ImagePrompt[];
  study: StudyState | null;
  /**
   * The languages this vocabulary is translated into, most preferred first.
   *
   * On the article because the reader needs it: a clip's player asks the corpus for its target text
   * in `glossLangs[0]`, which is the same language the stored translation line is written in, so
   * the two say the same thing in the same tongue rather than disagreeing on screen.
   */
  glossLangs: string[];
  /** The language the notes are written in, so a selection of one is read in that language. */
  notesLang: string;
}

export interface LanguageOption extends LanguagePresentation {
  count: number;
  /** False for a language that has words but no vocabulary record behind it any more. */
  configured: boolean;
}

export interface TopicOption {
  id: TopicSelection;
  name: string;
  icon: string;
  count: number | null;
}

const live = <T extends SyncFields>(records: T[]): T[] => records.filter((record) => !record.deleted);

const LEADING_ARTICLE = /^(el|la|los|las|le|les|der|die|das|the) /i;

function sortKeyOf(lexeme: Lexeme): string {
  return lexeme.headword.replace(LEADING_ARTICLE, "");
}

export function strengthOf(study: StudyState | null): number {
  if (!study) return 0;
  return Math.min(4, Math.max(1, Math.round(Math.log10(Math.max(study.stability, 1.1)) * 1.7 + 1)));
}

export function lexemesIn(graph: VocabularyGraph, language: string): Lexeme[] {
  return live(graph.lexemes).filter((lexeme) => lexeme.language === language);
}

/** What a look-up sheet says about a word the owner already has. */
export interface HeldWord {
  id: string;
  headword: string;
  gloss: string;
}

const bare = (form: string) => form.normalize("NFD").replace(/\p{Mn}/gu, "").toLowerCase().trim();

/**
 * The word the owner holds that a tapped form names, read from the replica — so a word you have is
 * answered at once and offline (`docs/features/look-up.md`). A story's mark says which word it is;
 * otherwise the form is compared with each headword, with and without its article, and each lemma.
 * An inflected form this misses is found by the server's look-up, which answers with the word held.
 */
export function heldWord(graph: VocabularyGraph, language: string, form: string,
                         lexemeId: string | null = null): HeldWord | null {
  const words = lexemesIn(graph, language);
  const want = bare(form);
  const found = (lexemeId ? words.find((lexeme) => lexeme.id === lexemeId) : undefined)
    ?? words.find((lexeme) => [lexeme.headword, lexeme.lemma, lexeme.headword.replace(LEADING_ARTICLE, "")]
      .some((candidate) => bare(candidate) === want));
  return found ? { id: found.id, headword: found.headword, gloss: shortGlossOf(graph, found) } : null;
}

export function vocabularies(graph: VocabularyGraph): Vocabulary[] {
  return live(graph.vocabularies)
    .slice()
    .sort((left, right) => left.order - right.order || left.language.localeCompare(right.language));
}

export function vocabularyFor(graph: VocabularyGraph, language: string): Vocabulary | null {
  return live(graph.vocabularies).find((entry) => entry.language === language) ?? null;
}

/**
 * Every language the switcher offers: the ones configured, in the owner's order, plus any that
 * still hold words without a record behind them.
 *
 * A configured language with no words has to appear, or a vocabulary could never be filled — there
 * would be nowhere to switch to before the first capture. That is why this is no longer derived
 * from the lexemes alone.
 */
export function languageOptions(graph: VocabularyGraph): LanguageOption[] {
  const counts = new Map<string, number>();
  live(graph.lexemes).forEach((lexeme) => counts.set(lexeme.language, (counts.get(lexeme.language) ?? 0) + 1));
  const configured = vocabularies(graph).map((entry) => ({
    ...presentationOf(entry), count: counts.get(entry.language) ?? 0, configured: true
  }));
  const known = new Set(configured.map((option) => option.code));
  const orphaned = [...counts.entries()]
    .filter(([code]) => !known.has(code))
    .map(([code, count]) => ({ ...languageOf(code), count, configured: false }))
    .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name));
  return [...configured, ...orphaned];
}

export function inboxCount(graph: VocabularyGraph, language: string): number {
  return lexemesIn(graph, language).filter((lexeme) => lexeme.status === "inbox").length;
}

export function topicOptions(graph: VocabularyGraph, language: string): TopicOption[] {
  const filed = lexemesIn(graph, language).filter((lexeme) => lexeme.status !== "inbox");
  return live(graph.topics)
    .slice()
    .sort((left, right) => left.order - right.order || left.name.localeCompare(right.name))
    .map((topic) => ({
      id: topic.id,
      name: topic.name,
      icon: topic.icon ?? "📌",
      count: filed.filter((lexeme) => lexeme.topicIds.includes(topic.id)).length || null
    }));
}

const bySenseOrder = (left: Sense, right: Sense) => left.order - right.order || left.id.localeCompare(right.id);

export function sensesOf(graph: VocabularyGraph, lexemeId: string): Sense[] {
  return live(graph.senses)
    .filter((sense) => sense.lexemeId === lexemeId)
    .sort(bySenseOrder);
}

/**
 * The one-line form: the curated override when there is one, otherwise the first sense's gloss in
 * the language configured for this vocabulary language. A projection, never a stored second record.
 */
export function shortGlossOf(graph: VocabularyGraph, lexeme: Lexeme): string {
  if (lexeme.shortGloss?.trim()) return lexeme.shortGloss.trim();
  const sense = sensesOf(graph, lexeme.id)[0];
  if (sense) {
    const preferred = glossLanguagesFor(lexeme.language, graph.vocabularies)
      .map((lang) => sense.glosses.find((gloss) => gloss.lang === lang))
      .find(Boolean);
    const gloss = preferred ?? sense.glosses[0];
    if (gloss) return gloss.terms.join("; ");
  }
  return effectiveShortGloss(graph, lexeme.id) ?? "";
}

function searchHaystack(graph: VocabularyGraph, lexeme: Lexeme): string {
  const senses = sensesOf(graph, lexeme.id);
  return [
    lexeme.headword, lexeme.lemma, lexeme.reading ?? "", lexeme.shortGloss ?? "",
    ...senses.map((sense) => sense.definition),
    ...senses.flatMap((sense) => sense.glosses.flatMap((gloss) => gloss.terms))
  ].join(" ").toLowerCase();
}

export interface ListQuery {
  language: string;
  topic: TopicSelection;
  query: string;
  sort: SortKey;
}

export function visibleRows(graph: VocabularyGraph, { language, topic, query, sort }: ListQuery): ListRow[] {
  const search = query.trim().toLowerCase();
  let rows = lexemesIn(graph, language);
  if (search) {
    rows = rows.filter((lexeme) => searchHaystack(graph, lexeme).includes(search));
  } else if (topic === "inbox") {
    rows = rows.filter((lexeme) => lexeme.status === "inbox");
  } else {
    rows = rows.filter((lexeme) => lexeme.status !== "inbox");
    if (topic !== "all") rows = rows.filter((lexeme) => lexeme.topicIds.includes(topic));
  }
  const studyOf = (lexeme: Lexeme) => studyStateOf(graph, lexeme.id);
  const sorters: Record<SortKey, (left: Lexeme, right: Lexeme) => number> = {
    recent: (left, right) => right.createdAt.localeCompare(left.createdAt),
    alpha: (left, right) => sortKeyOf(left).localeCompare(sortKeyOf(right), language),
    hard: (left, right) => (studyOf(right)?.difficulty ?? -1) - (studyOf(left)?.difficulty ?? -1)
  };
  return rows.slice().sort(sorters[sort]).map((lexeme) => {
    const study = studyOf(lexeme);
    return {
      id: lexeme.id,
      headword: lexeme.headword,
      reading: lexeme.reading,
      emoji: lexeme.emoji,
      shortGloss: shortGlossOf(graph, lexeme),
      senseCount: sensesOf(graph, lexeme.id).length,
      status: lexeme.status,
      strength: strengthOf(study),
      strengthLabel: study
        ? `stability ${study.stability} d · difficulty ${study.difficulty}`
        : "not scheduled yet"
    };
  });
}

export function studyStateOf(graph: VocabularyGraph, lexemeId: string): StudyState | null {
  return weakestOf(live(graph.studyStates).filter((state) => state.lexemeId === lexemeId));
}

/**
 * A word's rows as the one a list shows: the least stable of those reviewed at least once, since
 * that is the meaning (or the sound) that will come up first and says how well the word is known.
 * A word none of whose cards has been reviewed shows its first row, which reads as unscheduled.
 */
export function weakestOf(states: StudyState[]): StudyState | null {
  const reviewed = states.filter((state) => state.reps > 0);
  if (!reviewed.length) return states[0] ?? null;
  return reviewed.reduce((weakest, state) => (state.stability < weakest.stability ? state : weakest));
}

/**
 * Neither examples nor attestations carry an order field, so graph order would be whatever the last
 * sync happened to deliver. The YAML projection is edited by hand and diffed against what was
 * shown, so the sequence has to be the same every time it is rendered.
 */
const byAge = <T extends SyncFields & { id: string }>(records: T[]): T[] =>
  [...records].sort((left, right) =>
    left.createdAt.localeCompare(right.createdAt) || left.id.localeCompare(right.id));

/**
 * At most one picture per sense, which is what §02 decided and what the article should show.
 *
 * Belt and braces rather than the mechanism: an image prompt's id is *derived* from its sense, so a
 * second row for one sense cannot be created any more. It could be before — `saveArticle` minted a
 * random id while the server derived one, so importing a bundle left a sense with an empty frame
 * carrying the brief and a picture carrying none. This keeps such a pair from being *shown* while
 * it exists in a replica written by the older code.
 *
 * The one kept is the drawn one, then the most recently edited: a picture beats a bare brief, and
 * "the newest thing that happened to this sense" is the only other honest tie-break.
 */
function onePicture(images: ImagePrompt[]): ImagePrompt[] {
  if (images.length < 2) return images;
  const ranked = images.slice().sort((left, right) =>
    Number(Boolean(right.imageRef)) - Number(Boolean(left.imageRef))
    || right.editedAt.localeCompare(left.editedAt)
  );
  return [ranked[0]];
}

/**
 * The server's map joined to the replica, as the map component draws it.
 *
 * The server sends positions and ids and never a sense's text, so an edited headword shows at once
 * and a map already drawn reads offline. A sense deleted since the map was drawn is dropped here —
 * and every other point's neighbours are re-indexed around it — rather than drawn as a ghost; the
 * next map from the server will not have it either.
 */
export function mapDataFor(graph: VocabularyGraph, map: ServerMap): MapData {
  const lexemes = new Map(live(graph.lexemes).map((lexeme) => [lexeme.id, lexeme]));
  const senses = new Map(live(graph.senses).map((sense) => [sense.id, sense]));
  const glossLang = glossLanguagesFor(map.language, graph.vocabularies)[0];
  const kept = new Map<number, number>();
  map.points.forEach((point, index) => {
    const sense = senses.get(point.sense);
    if (sense && sense.lexemeId === point.lexeme && lexemes.has(point.lexeme)) kept.set(index, kept.size);
  });
  const points: MapPoint[] = [];
  kept.forEach((_, index) => {
    const point = map.points[index];
    const sense = senses.get(point.sense) as Sense;
    const lexeme = lexemes.get(point.lexeme) as Lexeme;
    const gloss = sense.glosses.find((entry) => entry.lang === glossLang) ?? sense.glosses[0];
    points.push({
      id: sense.id, word: lexeme.id, headword: lexeme.headword,
      emoji: sense.emoji || lexeme.emoji || "", gloss: gloss?.terms[0] ?? "",
      x: point.x, y: point.y, region: point.r, hood: point.h, rank: point.rank,
      near: point.nb.flatMap((near) => {
        const at = kept.get(near);
        return at === undefined ? [] : [at];
      })
    });
  });
  return { side: map.side, points, regions: map.regions, contours: map.contours };
}

/** What a tap on the map shows of one sense: enough to recognise it, and the way to its article. */
export interface MapPeek {
  sense: Sense;
  lexeme: Lexeme;
  /* Every sense of the word, in order, this one among them. */
  senses: Sense[];
  terms: string[];
  glossLang: string | null;
  picture: ImagePrompt | null;
}

export function mapPeekFor(graph: VocabularyGraph, senseId: string): MapPeek | null {
  const sense = live(graph.senses).find((entry) => entry.id === senseId);
  const lexeme = sense && live(graph.lexemes).find((entry) => entry.id === sense.lexemeId);
  if (!sense || !lexeme) return null;
  const glossLang = glossLanguagesFor(lexeme.language, graph.vocabularies)[0] ?? null;
  const gloss = sense.glosses.find((entry) => entry.lang === glossLang) ?? sense.glosses[0];
  return {
    sense,
    lexeme,
    senses: sensesOf(graph, lexeme.id),
    terms: gloss?.terms ?? [],
    glossLang: gloss?.lang ?? glossLang,
    picture: onePicture(byAge(live(graph.imagePrompts).filter((image) => image.senseId === sense.id)))[0] ?? null
  };
}

export function articleFor(graph: VocabularyGraph, lexemeId: string): Article | null {
  return articleReader(graph)(lexemeId);
}

/** Records grouped by one field, each group in graph order. */
function groupBy<T, K>(records: T[], keyOf: (record: T) => K): Map<K, T[]> {
  const groups = new Map<K, T[]>();
  records.forEach((record) => {
    const key = keyOf(record);
    const group = groups.get(key);
    if (group) group.push(record); else groups.set(key, [record]);
  });
  return groups;
}

/**
 * `articleFor` for many words of one graph: every collection is grouped once, so each article then
 * costs its own records rather than a pass over the replica. An export assembles every word, and
 * doing that with `articleFor` was a pass over the replica per word — a second of work for a
 * vocabulary of 1,700, repeated on every repaint of the panel that counts its pictures.
 */
export function articleReader(graph: VocabularyGraph): (lexemeId: string) => Article | null {
  const lexemes = new Map(live(graph.lexemes).map((lexeme) => [lexeme.id, lexeme]));
  const topics = new Map(live(graph.topics).map((topic) => [topic.id, topic]));
  const senses = groupBy(live(graph.senses), (sense) => sense.lexemeId);
  const examples = groupBy(live(graph.examples), (example) => example.senseId);
  const images = groupBy(live(graph.imagePrompts), (image) => image.lexemeId);
  const attestations = groupBy(live(graph.attestations), (attestation) => attestation.lexemeId);
  const study = groupBy(live(graph.studyStates), (state) => state.lexemeId);
  return (lexemeId) => {
    const lexeme = lexemes.get(lexemeId);
    if (!lexeme) return null;
    const own = images.get(lexemeId) ?? [];
    return {
      lexeme,
      topics: lexeme.topicIds
        .map((id) => topics.get(id))
        .filter((topic): topic is Topic => Boolean(topic)),
      senses: (senses.get(lexemeId) ?? []).slice().sort(bySenseOrder).map((sense) => ({
        sense,
        examples: byAge(examples.get(sense.id) ?? []),
        images: onePicture(byAge(own.filter((image) => image.senseId === sense.id)))
      })),
      attestations: byAge(attestations.get(lexemeId) ?? []),
      // Without these the card image is invisible in the projection, so saving would orphan it.
      images: byAge(own.filter((image) => image.senseId === null)),
      study: weakestOf(study.get(lexemeId) ?? []),
      glossLangs: glossLanguagesFor(lexeme.language, graph.vocabularies),
      notesLang: notesLanguageFor(lexeme.language, graph.vocabularies)
    };
  };
}

/* ── the second feeder ──────────────────────────────────────────────────
   An article the store has never seen — what capture proposes, or what you have typed into the
   editor and not saved — assembled into the same view model a stored one produces, so there is one
   renderer rather than a second surface for reviewing a proposal (`docs/features/capture.md`).

   The output is RENDER-ONLY. It is not a graph, it is not validated, and it must never be written:
   the one writer is `repository.saveArticle(parseArticle(text))`, which reads the document again
   rather than trusting anything assembled here. The placeholder ids below carry a `draft:` prefix
   precisely so a leak fails loudly — no record id is allowed to look like that. */

/** What a record that has never been stored knows about itself: nothing. */
const UNSAVED: SyncFields & OwnedFields = {
  ownerId: "", deleted: false, createdAt: "", editedAt: "", editedBy: "", revision: 0
};

/** A React key for a record the document did not name, stable across re-parses of the same text. */
const placeholder = (path: string) => `draft:${path}`;

/**
 * What `articleFromDraft` will call each record, before it builds anything.
 *
 * Exported because a proposal's change marks are keyed by record id and consumed by a component
 * rendering this function's output, so the two have to agree exactly. Having `articleEdit.ts`
 * compute the same strings independently would be an agreement that holds until someone renumbers
 * a placeholder; calling the same four functions is an agreement that cannot come apart.
 */
export const draftKeys = {
  lexeme: (draft: ArticleDraft) => draft.id ?? placeholder("lexeme"),
  sense: (sense: SenseDraft, index: number) => sense.id ?? placeholder(`sense:${index}`),
  example: (example: ExampleDraft, senseIndex: number, index: number) =>
    example.id ?? placeholder(`example:${senseIndex}:${index}`),
  attestation: (attestation: AttestationDraft, index: number) =>
    attestation.id ?? placeholder(`attestation:${index}`)
};

function topicsFromNames(graph: VocabularyGraph, names: string[]): Topic[] {
  const stored = live(graph.topics);
  return names.map((name) => {
    const match = stored.find((topic) => topic.name.toLowerCase() === name.toLowerCase());
    // A name that matches nothing is still shown. The preview's job is to say what the document
    // says; refusing an unknown topic is `saveArticle`'s job, and it does it on the way out.
    return match ?? { ...UNSAVED, id: placeholder(`topic:${name}`), name, icon: null, order: 0 };
  });
}

export function articleFromDraft(graph: VocabularyGraph, draft: ArticleDraft): Article {
  const lexemeId = draftKeys.lexeme(draft);
  const topics = topicsFromNames(graph, draft.topics);
  const lexeme: Lexeme = {
    ...UNSAVED,
    id: lexemeId,
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
    topicIds: topics.map((topic) => topic.id),
    status: draft.status,
    shortGloss: draft.shortGloss,
    primaryGloss: draft.primaryGloss,
    emotion: draft.emotion,
    notes: draft.notes,
    // An unsaved proposal has never been through a clip search: capture never consults the corpus.
    clipsSearchedAt: null
  };

  const promptsOf = (drafts: ArticleDraft["images"], senseId: string | null, path: string): ImagePrompt[] =>
    drafts.map((image, index) => ({
      ...UNSAVED,
      id: image.id ?? placeholder(`${path}:${index}`),
      lexemeId,
      senseId,
      exampleId: image.exampleId,
      // A draft is a proposal, so nothing has been attempted, refused or ruled on yet.
      attempts: 0,
      failureReason: null,
      suppressed: false,
      prompt: image.prompt,
      styleId: image.styleId,
      seed: image.seed,
      modelId: image.modelId,
      promptVersion: image.promptVersion,
      imageRef: image.imageRef,
      imageModelId: image.imageModelId
    }));

  return {
    lexeme,
    topics,
    // Document order throughout, not `byAge`: the placeholder timestamps are all equal, and the
    // order you wrote is the order you are reviewing.
    senses: draft.senses.map((senseDraft, senseIndex) => {
      const senseId = draftKeys.sense(senseDraft, senseIndex);
      const sense: Sense = {
        ...UNSAVED,
        id: senseId,
        lexemeId,
        definition: senseDraft.definition,
        definitionLang: senseDraft.definitionLang,
        glosses: senseDraft.glosses,
        domain: senseDraft.domain,
        emoji: senseDraft.emoji,
        order: senseDraft.order
      };
      return {
        sense,
        examples: senseDraft.examples.map((example, index): Example => ({
          ...UNSAVED,
          id: draftKeys.example(example, senseIndex, index),
          senseId,
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
        })),
        images: promptsOf(senseDraft.images, senseId, `senseImage:${senseIndex}`)
      };
    }),
    attestations: draft.attestations.map((attestation, index): Attestation => ({
      ...UNSAVED,
      id: draftKeys.attestation(attestation, index),
      lexemeId,
      text: attestation.text,
      translation: attestation.translation,
      sourceUrl: attestation.sourceUrl,
      sourceTitle: attestation.sourceTitle,
      sourceKind: attestation.sourceKind,
      capturedAt: attestation.capturedAt,
      photoRef: attestation.photoRef,
      photoRegion: attestation.photoRegion
    })),
    images: promptsOf(draft.images, null, "image"),
    // A document cannot carry study state, so a proposal never has any to show.
    study: null,
    glossLangs: glossLanguagesFor(draft.language, graph.vocabularies),
    notesLang: notesLanguageFor(draft.language, graph.vocabularies)
  };
}


/* ── loops ──────────────────────────────────────────────────────────────
   A loop is a rendered track over some of the owner's words. Everything the interface needs to show
   one is derived here: there is no title column, no status column, and no stored list of which words
   were eligible. */

/** The loops of one language, in the order the owner put them. */
export function loopsIn(graph: VocabularyGraph, language: string): Loop[] {
  return live(graph.loops)
    .filter((loop) => loop.language === language)
    .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id));
}

/** One loop's words, in the order they are heard. */
export function loopItemsOf(graph: VocabularyGraph, loopId: string): LoopItem[] {
  return live(graph.loopItems)
    .filter((item) => item.loopId === loopId)
    .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id));
}

/** One loop's lines, in the order they are heard. */
export function loopCuesOf(graph: VocabularyGraph, loopId: string): LoopCue[] {
  return live(graph.loopCues)
    .filter((cue) => cue.loopId === loopId)
    .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id));
}

/** What a player needs to play one loop: the loop, its words and its lines. */
export interface LoopTrack {
  loop: Loop;
  items: LoopItem[];
  cues: LoopCue[];
}

export function loopTrackOf(graph: VocabularyGraph, loop: Loop): LoopTrack {
  return { loop, items: loopItemsOf(graph, loop.id), cues: loopCuesOf(graph, loop.id) };
}

/** Whether a loop has been rendered. The absence of a reference is the whole of what says so. */
export function loopIsReady(loop: Loop): boolean {
  return Boolean(loop.audioRef);
}

/**
 * A name for a loop, derived from the words it teaches.
 *
 * There is no title column, for `shortGlossOf`'s reason: a stored second string is one more thing to
 * keep in step with the records that already say it. As many source words as fit, then a count of
 * what is left — so two loops over the same twelve words in a different order still read differently.
 */
export function loopTitle(graph: VocabularyGraph, loop: Loop, limit = 3): string {
  const items = loopItemsOf(graph, loop.id);
  if (!items.length) return "Empty loop";
  const named = items.slice(0, limit).map((item) => item.sourceText);
  const rest = items.length - named.length;
  return rest > 0 ? `${named.join(", ")} +${rest}` : named.join(", ");
}

/**
 * The beds the owner kept, newest first, one per piece of music.
 *
 * A favourite *is* its style and seed, so two records naming the same pair — kept twice, or from
 * two devices — are one favourite here. There is no uniqueness constraint to lean on instead: that
 * is the data rule for every replicated collection.
 */
export function favouriteBeds(graph: VocabularyGraph): Bed[] {
  const seen = new Set<string>();
  return live(graph.beds)
    .slice()
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt) || left.id.localeCompare(right.id))
    .filter((bed) => {
      const key = `${bed.styleId}\u0000${bed.seed}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

/** The kept bed a loop's music is, if it is one: the same style and the same seed. */
export function bedOfLoop(graph: VocabularyGraph, loop: Loop): Bed | undefined {
  if (!loop.styleId) return undefined;
  return live(graph.beds).find((bed) => bed.styleId === loop.styleId && bed.seed === loop.seed);
}

/** A style's name in words: the generator's label where it gave one, else the id with its hyphens gone. */
export function styleLabel(families: readonly { id: string; label: string }[] | undefined, styleId: string | null): string {
  if (!styleId) return "No music yet";
  const named = families?.find((family) => family.id === styleId)?.label;
  if (named) return named;
  const words = styleId.replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Words a loop could be made from, sampled out of what is on screen.
 *
 * Eligibility is `primaryGloss`: `shortGloss` may carry several distinct meanings and a loop must
 * choose between them, so a word whose writer left it without one is simply not eligible — nothing
 * backfills it. The sample is deterministic given a seed so the same scope offers the same words
 * until something changes, which is what makes "Surprise me" repeatable rather than merely random.
 */
export function loopCandidates(graph: VocabularyGraph, query: ListQuery): Lexeme[] {
  const rows = new Set(visibleRows(graph, query).map((row) => row.id));
  return live(graph.lexemes).filter((lexeme) => rows.has(lexeme.id) && loopEligible(graph, lexeme));
}

/** Whether one word can be in a loop: it has the single term a loop speaks. */
export function loopEligible(_graph: VocabularyGraph, lexeme: Lexeme): boolean {
  return Boolean(lexeme.primaryGloss?.trim());
}

/**
 * The sample a dialog sends. `candidates` is which words the kind can use — a loop's by default,
 * and a story's from the story dialog, which used to sample a loop's and so could send a story no
 * words at all from a scope full of words it could have used.
 */
export function sampleLexemeIds(
  graph: VocabularyGraph, query: ListQuery, count: number, seed = 0,
  candidatesOf: (graph: VocabularyGraph, query: ListQuery) => Lexeme[] = loopCandidates
): string[] {
  const candidates = candidatesOf(graph, query);
  // A small deterministic shuffle: xorshift over the seed, so the same scope and seed pick the same
  // words. Nothing here needs cryptographic quality, and `Math.random` would make it untestable.
  let state = (seed || 1) >>> 0;
  const next = () => {
    state ^= state << 13; state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5; state >>>= 0;
    return state / 0x100000000;
  };
  const pool = candidates.slice();
  for (let index = pool.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(next() * (index + 1));
    [pool[index], pool[swap]] = [pool[swap], pool[index]];
  }
  return pool.slice(0, Math.max(count, 0)).map((lexeme) => lexeme.id);
}

/* ── playing a loop ──────────────────────────────────────────────────────
   What the player draws at one instant, derived and never stored. Pure, so the whole of the
   reveal rule can be tested without an audio element — and so that dragging the line backwards
   withholds an answer again rather than leaving it up because it was once shown. */

/** One line as a card shows it: a line said several times — a drill's word — is one row. */
export interface LoopCardLine {
  text: string;
  language: string;
  role: "native" | "guide";
  side: "source" | "target" | null;
  /** When it is first said, which is when it may be drawn. */
  heard: number;
  /** Every time it is said, for the mark. */
  starts: number[];
}

/** What the player shows together: one `group` of a loop's lines. */
export interface LoopCard {
  group: number;
  section: string;
  kind: string;
  /** The word the card belongs to, or null for a card of no word — an intro, a story line. */
  loopItemId: string | null;
  start: number;
  lines: LoopCardLine[];
}

/** A loop's lines, as the cards the player draws — one per group, in the order heard. */
export function loopCards(cues: readonly LoopCue[]): LoopCard[] {
  const cards: LoopCard[] = [];
  for (const cue of cues) {
    let card = cards[cards.length - 1];
    if (!card || card.group !== cue.group) {
      card = { group: cue.group, section: cue.section, kind: cue.kind, loopItemId: cue.loopItemId, start: cue.startSeconds, lines: [] };
      cards.push(card);
    }
    const same = card.lines.find((line) => line.text === cue.text && line.language === cue.language);
    if (same) same.starts.push(cue.startSeconds);
    else card.lines.push({ text: cue.text, language: cue.language, role: cue.role, side: cue.side, heard: cue.startSeconds, starts: [cue.startSeconds] });
  }
  return cards;
}

export interface LoopMoment {
  /** Which card is showing, or -1 before the first line. */
  card: number;
  /** Which of its lines was said most recently — what the mark follows — or -1. */
  sounding: number;
}

/**
 * What the player marks at one instant.
 *
 * The gap after a card belongs to it until the next begins, so a card does not go dark while its bed
 * plays on. `sounding` is the line most recently said rather than the one making sound this
 * millisecond: a word is half a second long every few, and a mark that blinked for half a second
 * would be unreadable at a glance — which is the whole way this screen is used.
 */
export function loopMomentAt(cards: readonly LoopCard[], at: number): LoopMoment {
  let card = -1;
  cards.forEach((one, index) => { if (at >= one.start) card = index; });
  if (card < 0) return { card, sounding: -1 };
  let sounding = -1;
  let latest = -Infinity;
  cards[card].lines.forEach((line, index) => {
    for (const start of line.starts) if (start <= at && start >= latest) { latest = start; sounding = index; }
  });
  return { card, sounding };
}

/**
 * Whether a line may be drawn yet. **Within a card, nothing after its first line is drawn before it
 * has been said**: a translation not before it is spoken, a quiz's answer not before it is given, an
 * example's meaning not before it is heard. The first line is the question, and is always there.
 */
export function loopLineShown(card: LoopCard, index: number, at: number): boolean {
  return index === 0 || at >= card.lines[index].heard;
}

/** The word a loop is on at one instant: the card's, else the last word whose block has begun. */
export function loopWordAt(items: readonly LoopItem[], cards: readonly LoopCard[], at: number): LoopItem | null {
  const card = cards[loopMomentAt(cards, at).card];
  const own = card?.loopItemId ? items.find((item) => item.id === card.loopItemId) : undefined;
  if (own) return own;
  let latest: LoopItem | null = null;
  for (const item of items) if (at >= item.startSeconds) latest = item;
  return latest;
}

/** A format's name in words: the generator's label where it gave one, else the id made readable. */
export function formatLabel(formats: readonly { id: string; label: string }[] | undefined, formatId: string): string {
  const named = formats?.find((format) => format.id === formatId)?.label;
  if (named) return named;
  const words = formatId.replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/* ── stories ────────────────────────────────────────────────────────────
   A story is a handful of words told back as a short illustrated tale. As with a loop, everything
   the interface shows is derived: there is no status column and no stored list of marks. */

/** The stories of one language, in the order the owner put them. */
export function storiesIn(graph: VocabularyGraph, language: string): Story[] {
  return live(graph.stories)
    .filter((story) => story.language === language)
    .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id));
}

/** One story's parts, in reading order. */
export function storyPartsOf(graph: VocabularyGraph, storyId: string): StoryPart[] {
  return live(graph.storyParts)
    .filter((part) => part.storyId === storyId)
    .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id));
}

/** One story's words, in the order they were asked for. */
export function storyWordsOf(graph: VocabularyGraph, storyId: string): StoryWord[] {
  return live(graph.storyWords)
    .filter((word) => word.storyId === storyId)
    .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id));
}

/**
 * Whether a story has been written. Having no parts is the whole of what says it has not.
 *
 * `loopIsReady`'s counterpart, and derived for the same reason: a status column would be a fifth
 * fact to keep in step with four that already say all of it.
 */
export function storyIsWritten(graph: VocabularyGraph, storyId: string): boolean {
  return storyPartsOf(graph, storyId).length > 0;
}

/** How many of a story's pictures have been drawn, out of how many parts. */
export function storyPictures(graph: VocabularyGraph, storyId: string): { drawn: number; total: number } {
  const parts = storyPartsOf(graph, storyId);
  return { drawn: parts.filter((part) => part.imageRef).length, total: parts.length };
}

/**
 * A name for a story: its own title once it has one, else the words it was asked to teach.
 *
 * Unlike a loop, a story *does* have a title — it is a thing the writer produced, not a string
 * derived to stand in for one. Before it is written there is no title to show, and the words are
 * the only honest description of what was asked for.
 */
export function storyTitle(graph: VocabularyGraph, story: Story, limit = 3): string {
  const title = story.title?.trim();
  if (title) return title;
  const words = storyWordsOf(graph, story.id);
  if (!words.length) return "Empty story";
  const named = words.slice(0, limit).map((word) => word.sourceText);
  const rest = words.length - named.length;
  return rest > 0 ? `${named.join(", ")} +${rest}` : named.join(", ");
}

/** One line of the story's closing page: a word it was asked to teach. */
export interface StoryWordEntry {
  lexemeId: string;
  /** As it was asked for — the same text the story's row in the list shows. */
  headword: string;
  emoji: string;
  /** The word's own list line, in the language the story is translated into. Empty if it has none. */
  gloss: string;
  /** False for a word the writer could not work in: asked for and honestly not used. */
  used: boolean;
}

/**
 * The words a story was made from, for the page at its end.
 *
 * Each is looked up among **all** lexemes, tombstones included, for the reason `domain.ts` states for
 * the reference itself: a word deleted since the story was written is still a word the story taught,
 * and the page should say so rather than lose a line. Its emoji and gloss then come from the record
 * that is left, and a lexeme that is gone altogether leaves the words the story kept on its own.
 */
export function storyWordEntries(graph: VocabularyGraph, storyId: string): StoryWordEntry[] {
  const held = new Map(graph.lexemes.map((lexeme) => [lexeme.id, lexeme]));
  return storyWordsOf(graph, storyId).map((word) => {
    const lexeme = held.get(word.lexemeId);
    return {
      lexemeId: word.lexemeId,
      headword: word.sourceText,
      emoji: lexeme?.emoji || "📄",
      gloss: lexeme ? shortGlossOf(graph, lexeme) : "",
      used: word.forms.length > 0
    };
  });
}

/**
 * Words a story could be built from, sampled out of what is on screen.
 *
 * Eligibility is deliberately **weaker than a loop's**: a loop speaks one term on a beat and so
 * needs `primaryGloss`, while a story only needs to know roughly what a word means and can read
 * that from `shortGloss` or a sense. So a word that cannot be in a loop can still be in a story,
 * which is most of the vocabulary.
 */
export function storyCandidates(graph: VocabularyGraph, query: ListQuery): Lexeme[] {
  const rows = new Set(visibleRows(graph, query).map((row) => row.id));
  return live(graph.lexemes).filter((lexeme) => rows.has(lexeme.id) && storyEligible(graph, lexeme));
}

/** Whether one word can be in a story: something says roughly what it means. */
export function storyEligible(graph: VocabularyGraph, lexeme: Lexeme): boolean {
  return Boolean(lexeme.shortGloss?.trim() || lexeme.primaryGloss?.trim()
    || effectiveShortGloss(graph, lexeme.id));
}

/* ── the selection ───────────────────────────────────────────────────────
   Words put aside by hand to make something from. Which ids are selected is `wordSelection.ts`'s,
   kept on this device; what they are is read here, from the replica, every time. */

/** One selected word, as the selection bar, its list and the make dialogs draw it. */
export interface SelectedWord {
  id: string;
  headword: string;
  emoji: string | null;
  shortGloss: string;
  lexeme: Lexeme;
}

/**
 * The selected words that still exist in this language, in the order they were chosen. A word
 * deleted since, or one whose id this replica does not hold, simply is not here: nothing repairs the
 * stored selection, because nothing needs to.
 */
export function selectedWords(graph: VocabularyGraph, language: string, ids: readonly string[]): SelectedWord[] {
  const byId = new Map(live(graph.lexemes).map((lexeme) => [lexeme.id, lexeme]));
  return ids.flatMap((id) => {
    const lexeme = byId.get(id);
    if (!lexeme || lexeme.language !== language) return [];
    return [{ id, headword: lexeme.headword, emoji: lexeme.emoji, shortGloss: shortGlossOf(graph, lexeme), lexeme }];
  });
}

/** A selected word as a make dialog shows it: used, or left out and why. */
export interface ChosenWord extends SelectedWord {
  /** Empty when the word will be sent; otherwise the reason it will not be. */
  skip: string;
}

/**
 * What a dialog will send from the selection: every word, in order, each either used or left out
 * with a reason — one the kind cannot use, or one past the kind's limit, where the first chosen
 * are the ones used. The dialog draws exactly this, so what is undimmed is exactly what is sent.
 */
export function chosenFor(
  graph: VocabularyGraph, words: readonly SelectedWord[],
  rule: { eligible(graph: VocabularyGraph, lexeme: Lexeme): boolean; why: string; max: number; noun: string }
): ChosenWord[] {
  let used = 0;
  return words.map((word) => {
    if (!rule.eligible(graph, word.lexeme)) return { ...word, skip: rule.why };
    used += 1;
    return { ...word, skip: used > rule.max ? `a ${rule.noun} takes at most ${rule.max}` : "" };
  });
}

/** One run of a story's text: plain, or one of the words the story was asked to teach. */
export interface StorySpan {
  text: string;
  /** The word this run is a form of, when it is one. */
  lexemeId: string | null;
}

/**
 * A part's text, split into the runs the reader draws — the target words marked, the rest plain.
 *
 * **Marks are found rather than stored**, and that is the design. The writer reports the surface
 * forms it actually wrote and the server verifies each one appears in the text and is a form of the
 * word it was reported against; this then locates them. Putting markers in the text itself would
 * leak them into the translation, into anything that reads the story aloud, and into every diff.
 *
 * A form that cannot be found simply is not marked — degraded, never broken. Longest forms are
 * matched first so `asombrosos` wins over `asombroso`, and matching is accent- and case-insensitive
 * because a word at the start of a sentence is capitalised and is still the word.
 *
 * `field` says which language is being searched: the forms the story was written with, or the words
 * the translator reported for its translation. The same rules serve both, because they are the same
 * problem — a string the server has already checked is in the text.
 */
export function storySpans(
  text: string, words: StoryWord[], field: "forms" | "translationForms" = "forms"
): StorySpan[] {
  const wanted: { form: string; lexemeId: string }[] = [];
  words.forEach((word) => word[field].forEach((form) => {
    const trimmed = form.trim();
    if (trimmed) wanted.push({ form: trimmed, lexemeId: word.lexemeId });
  }));
  if (!wanted.length) return [{ text, lexemeId: null }];
  // Longest first, so a longer form is never pre-empted by a shorter one it contains.
  wanted.sort((left, right) => right.form.length - left.form.length);

  const flat = fold(text);
  const claimed: ({ lexemeId: string; length: number } | null)[] = new Array(text.length).fill(null);
  const taken = new Array(text.length).fill(false);

  wanted.forEach(({ form, lexemeId }) => {
    const needle = fold(form);
    if (!needle) return;
    let from = 0;
    for (;;) {
      const at = flat.indexOf(needle, from);
      if (at < 0) break;
      from = at + needle.length;
      // Only on a word boundary: `pan` must not mark the middle of `panadería`.
      if (isWordish(flat[at - 1]) || isWordish(flat[at + needle.length])) continue;
      if (taken.slice(at, at + needle.length).some(Boolean)) continue;
      for (let index = at; index < at + needle.length; index += 1) taken[index] = true;
      claimed[at] = { lexemeId, length: needle.length };
    }
  });

  const spans: StorySpan[] = [];
  let index = 0;
  let plain = "";
  while (index < text.length) {
    const mark = claimed[index];
    if (!mark) { plain += text[index]; index += 1; continue; }
    if (plain) { spans.push({ text: plain, lexemeId: null }); plain = ""; }
    spans.push({ text: text.slice(index, index + mark.length), lexemeId: mark.lexemeId });
    index += mark.length;
  }
  if (plain) spans.push({ text: plain, lexemeId: null });
  return spans;
}

/** The runs of one passage of a part read aloud, or of the whole text when there are no passages. */
export interface SegmentRun {
  /** Index into the part's `audioSegments`, or null when the text has none to mark. */
  segment: number | null;
  spans: StorySpan[];
}

/**
 * A part's text as `storySpans` draws it, grouped by the passage each run belongs to.
 *
 * A passage's place in the text is the lengths of the passages before it — they join back to `text`
 * exactly, which is the server's guarantee and is checked here rather than trusted: passages that do
 * *not* join to this text (a recording made from words that have since changed, or none at all) give
 * one ungrouped run, and the reader is then exactly what it was before anything was read aloud.
 * A marked word that straddles two passages is cut at the seam and each half keeps its mark.
 */
export function segmentSpans(text: string, words: StoryWord[], segments: AudioSegment[]): SegmentRun[] {
  const spans = storySpans(text, words);
  // One passage is the whole part: there is nothing to tell it from, so there is nothing to tap.
  if (segments.length < 2 || segments.map((one) => one.text).join("") !== text) {
    return [{ segment: null, spans }];
  }
  const ends: number[] = [];
  segments.reduce((at, one) => { ends.push(at + one.text.length); return at + one.text.length; }, 0);

  const runs: SegmentRun[] = segments.map((_, index) => ({ segment: index, spans: [] }));
  let at = 0;
  spans.forEach((span) => {
    let from = 0;
    while (from < span.text.length) {
      let segment = ends.findIndex((end) => at + from < end);
      if (segment < 0) segment = ends.length - 1;
      const room = ends[segment] - (at + from);
      const part = span.text.slice(from, from + room);
      runs[segment].spans.push({ text: part, lexemeId: span.lexemeId });
      from += part.length;
    }
    at += span.text.length;
  });
  return runs.filter((run) => run.spans.length > 0);
}

/** Lowercased and stripped of accents, **without changing length**, so offsets still line up. */
function fold(value: string): string {
  return Array.from(value).map((character) => {
    const bare = character.normalize("NFD").replace(/\p{Mn}/gu, "");
    // A character whose decomposition is not one character would move every later offset, so it is
    // left exactly as it was. Marking is best-effort; alignment is not negotiable.
    return (bare.length === 1 ? bare : character).toLowerCase();
  }).join("");
}

function isWordish(character: string | undefined): boolean {
  return character !== undefined && /[\p{L}\p{N}]/u.test(character);
}
