/**
 * Export and import of a whole vocabulary as a bundle of files.
 *
 * Three needs, one mechanism: surviving a schema change without losing curation, mirroring the
 * vocabulary into Obsidian (`docs/features/export.md`), and handing a vocabulary to someone else.
 * All three want the same thing — the words as files, in a representation that outlives the
 * database that produced them.
 *
 * A word file is exactly the document `yaml.ts` already writes, with its ids stripped. There is no
 * second format and no second parser: a bundle is read back through `parseArticle` and written
 * through `repository.saveArticle`, which is the one write path with the diffing, validation and
 * atomicity every other caller gets.
 *
 * Export is built from the replica alone, so it works with the server unreachable, like every other
 * read. Import is a sequence of ordinary writes, so it is online-only and fails loudly, like every
 * other write.
 */

import { Document, isScalar, isSeq, parse, Scalar, visit } from "yaml";
import { SCHEMA_VERSION } from "./api";
import type { Lexeme, PronunciationTarget, TopicInput, VocabularyGraph, VocabularyInput } from "./domain";
import { newId } from "./ids";
import { markdownFor } from "./markdown";
import type { AcervoRepository } from "./repository";
import { articleReader, lexemesIn, languageOptions, sensesOf, vocabularies } from "./selectors";
import { draftFor, parseArticle, yamlForDraft, YamlProblems, type ArticleDraft } from "./yaml";

/**
 * The layout: which files exist and what they are called. Versioned separately from
 * `schemaVersion`, which versions the records inside them, so a directory rename and a field rename
 * never have to be disentangled from one number.
 */
export const BUNDLE_FORMAT = "acervo-export/1";

export const MANIFEST_FILE = "acervo.yaml";
export const VOCABULARIES_FILE = "vocabularies.yaml";
export const TOPICS_FILE = "topics.yaml";
export const MARKDOWN_DIRECTORY = "markdown";
export const MEDIA_DIRECTORY = "media";
export const AUDIO_DIRECTORY = "audio";
export const CLIPS_FILE = "clips.yaml";

const RESERVED = [MANIFEST_FILE, VOCABULARIES_FILE, TOPICS_FILE];

export interface BundleFile {
  path: string;
  text: string;
}

export interface ExportOptions {
  /** A language tag, or every language the replica holds. */
  language: string | "all";
  markdown: boolean;
  /**
   * Whether to carry the picture files as well as the records that name them.
   *
   * Off by default and deliberately so. A bundle is a text archive you can read, and pictures are
   * regenerable by design — what must not be lost is the brief that produced one, and that is in
   * the word file either way. It is also the one export that is not offline-capable: the bytes come
   * from the server, or from this device's cache if it happens to hold them.
   */
  images: boolean;
  /**
   * Whether to carry the pronunciation clips, with who recorded each one.
   *
   * On by default, unlike pictures: a clip is a few kilobytes, and a voice you have listened to for
   * a month is worth keeping even though it could be recorded again. Like pictures, the bytes come
   * from this device where it has them and from the server where it does not.
   */
  pronunciations: boolean;
}

/* ── filenames ──────────────────────────────────────────────────────────
   The headword is the name, because a directory of ids is a directory nobody can read. */

const CYRILLIC: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "y",
  к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f",
  х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya"
};

function latinise(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .split("")
    .map((character) => CYRILLIC[character] ?? character)
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/, "");
}

/**
 * `la balsa` → `balsa`, `ponerse malo` → `ponerse-malo`, `суматоха` → `sumatokha`, `麻烦` → `mafan`.
 *
 * Named after the lemma rather than the headword, because the lemma is the dictionary form and the
 * headword carries the article — a directory named from headwords files half a Spanish vocabulary
 * under `el-` and `la-`. The parser already defaults the lemma to the headword, so it is always
 * there.
 *
 * A script with no Latin form falls back to the reading, which Chinese lexemes are already required
 * to carry and which is the pinyin — so the hardest case needs no dictionary and no guessing.
 */
export function slugFor(lexeme: Pick<Lexeme, "headword" | "lemma" | "reading">): string {
  return latinise(lexeme.lemma) || latinise(lexeme.headword) || latinise(lexeme.reading ?? "") || "word";
}

/** Two words that latinise the same still need two files. Deterministic, so re-exports are stable. */
function uniqueNames(lexemes: Lexeme[]): Map<string, string> {
  const taken = new Map<string, number>();
  const names = new Map<string, string>();
  lexemes.forEach((lexeme) => {
    const base = slugFor(lexeme);
    const seen = taken.get(base) ?? 0;
    taken.set(base, seen + 1);
    names.set(lexeme.id, seen === 0 ? base : `${base}-${seen + 1}`);
  });
  return names;
}

/* ── writing ────────────────────────────────────────────────────────────*/

/** An instant must survive as the string it is, never as a parsed date. */
function quoted(value: string): Scalar {
  const node = new Scalar(value);
  node.type = Scalar.QUOTE_DOUBLE;
  return node;
}

function document(value: unknown): string {
  const node = new Document(value);
  // Short lists of plain values read better on one line, the way the article documents already
  // write `topics: [Food]`. Anything holding records keeps its block form.
  visit(node, (_key, item) => {
    if (isSeq(item) && item.items.length <= 8 && item.items.every(isScalar)) item.flow = true;
  });
  return node.toString({ lineWidth: 0, singleQuote: false, flowCollectionPadding: false });
}

/**
 * Ids leave, except the ones that mean something.
 *
 * Two kinds of id survive, and they are the same kind: a reference between two records **in this
 * file**. An example drawn from a sentence the owner supplied names its attestation, and a picture
 * names the example whose scene it draws. Drop either id and the lineage is gone, so both stay and
 * `remintIds` re-mints them on the way in — which is what keeps a bundle from depending on the
 * account it came from. Every other id is the database's private business: dropping them is what
 * lets a file be read as a new word, in any account, including a rebuilt one, where a stated lexeme
 * id would be refused.
 *
 * `imageRef` goes with the ids and is not a reference at all: it is a path on the server that drew
 * the picture, embedding a lexeme id that will not exist after import — keeping it imported a
 * live-looking reference to a file nobody has.
 *
 * `imageModelId` **stays**, and the distinction is worth stating: it is not a path, it is the name
 * of the model that drew this picture, which is a fact about the past exactly as an example's
 * `origin` and `modelId` are. Provenance travels in a bundle; server paths do not. `remintIds`
 * drops it again on the way in, because a row cannot name a rendering model with nothing rendered —
 * it is handed to the step that supplies the bytes instead.
 */
export function stripIds(draft: ArticleDraft): ArticleDraft {
  const forget = (image: ArticleDraft["images"][number]) => ({
    ...image, id: null, imageRef: null
  });
  return {
    ...draft,
    id: null,
    // A photo is a server path to a file the bundle does not carry, so it goes like a picture's
    // `imageRef` does — and an attestation that was only a photo, a sign with no sentence, has
    // nothing left to say without it.
    attestations: draft.attestations
      .filter((attestation) => attestation.text.trim())
      .map((attestation) => ({ ...attestation, photoRef: null, photoRegion: null })),
    senses: draft.senses.map((sense) => ({
      ...sense,
      id: null,
      images: sense.images.map(forget)
    })),
    images: draft.images.map(forget)
  };
}

function vocabularyContent(graph: VocabularyGraph, languages: string[]): VocabularyInput[] {
  return vocabularies(graph)
    .filter((entry) => languages.includes(entry.language))
    .map((entry) => ({
      language: entry.language,
      definitionLang: entry.definitionLang,
      glossLangs: entry.glossLangs,
      notesLang: entry.notesLang,
      displayName: entry.displayName,
      flag: entry.flag,
      region: entry.region,
      order: entry.order
    }));
}

/**
 * Every topic, not only the ones this language uses. Topics are global in the model, and inventing
 * a per-language topic list here would invent a relationship the records do not have — a full
 * backup would also quietly lose the empty topics the owner deliberately created.
 */
function topicContent(graph: VocabularyGraph): TopicInput[] {
  return graph.topics
    .filter((topic) => !topic.deleted)
    .slice()
    .sort((left, right) => left.order - right.order || left.name.localeCompare(right.name))
    .map((topic) => ({ name: topic.name, icon: topic.icon, order: topic.order }));
}

/** One picture to carry: where it goes in the bundle, and the reference it comes from. */
export interface BundlePicture {
  path: string;
  reference: string;
}

/**
 * Which pictures a bundle would carry, named after the word file they belong to.
 *
 * Named rather than fetched, because this module has no transport and should not grow one:
 * `TransferPanel.tsx` owns the zip and the browser's file handling, and the bytes are its business.
 * The name pairs by eye with the word file — `es/picar.yaml` and `media/es/picar-1.webp` — which is
 * what makes an archive you can open in Finder worth having.
 *
 * Suffixed by sense order rather than by prompt id: a bundle carries no ids a human can use, and
 * "the second sense of picar" is a thing you can find in the word file.
 */
export function picturesIn(graph: VocabularyGraph, options: ExportOptions): BundlePicture[] {
  const present = languageOptions(graph).map((option) => option.code);
  const articleOf = articleReader(graph);
  const languages = options.language === "all"
    ? present
    : present.filter((code) => code === options.language);

  const pictures: BundlePicture[] = [];
  languages.forEach((language) => {
    const words = lexemesIn(graph, language)
      .slice()
      .sort((left, right) => left.lemma.localeCompare(right.lemma) || left.id.localeCompare(right.id));
    const names = uniqueNames(words);
    words.forEach((lexeme) => {
      const article = articleOf(lexeme.id);
      if (!article) return;
      article.senses.forEach((entry, index) => {
        entry.images.forEach((image) => {
          if (!image.imageRef) return;
          pictures.push({
            path: `${MEDIA_DIRECTORY}/${language}/${names.get(lexeme.id)}-${index + 1}.webp`,
            reference: image.imageRef
          });
        });
      });
    });
  });
  return pictures;
}

/** One clip to carry: where it goes in the bundle, and the reference its bytes come from. */
export interface BundleClip {
  path: string;
  reference: string;
}

/**
 * What a bundle says about one clip, beside the file. `target` and `text` are how it finds its
 * record again: a clip of a sentence belongs to whichever record says that sentence.
 */
export interface ClipEntry {
  file: string;
  target: PronunciationTarget;
  text: string;
  lang: string;
  emotion: string | null;
  providerId: string;
  modelId: string;
  voice: string | null;
}

const extensionOf = (reference: string) => reference.split(".").pop() || "mp3";

/**
 * Which clips a bundle would carry, and the per-word `clips.yaml` that describes them.
 *
 * Under `audio/<language>/<slug>/`, beside the word file of the same slug, and named for what they
 * read — `headword.mp3`, `example-2-1.mp3` — so the directory can be browsed and played by ear.
 * Only a clip that still says what its record says: a stale one is a recording of words the word no
 * longer has, and carrying it would import it as current.
 */
export function pronunciationsIn(graph: VocabularyGraph, options: ExportOptions): { files: BundleFile[]; clips: BundleClip[] } {
  const present = languageOptions(graph).map((option) => option.code);
  const articleOf = articleReader(graph);
  const languages = options.language === "all" ? present : present.filter((code) => code === options.language);
  const files: BundleFile[] = [];
  const clips: BundleClip[] = [];
  const live = graph.pronunciations.filter((clip) => !clip.deleted);

  languages.forEach((language) => {
    const words = lexemesIn(graph, language)
      .slice()
      .sort((left, right) => left.lemma.localeCompare(right.lemma) || left.id.localeCompare(right.id));
    const names = uniqueNames(words);
    words.forEach((lexeme) => {
      const article = articleOf(lexeme.id);
      if (!article) return;
      const directory = `${AUDIO_DIRECTORY}/${language}/${names.get(lexeme.id)}`;
      const entries: ClipEntry[] = [];
      const carry = (target: PronunciationTarget, id: string, text: string, name: string) => {
        const clip = live.find((one) => one.targetKind === target && one.targetId === id && one.text === text);
        if (!clip) return;
        const file = `${name}.${extensionOf(clip.audioRef)}`;
        clips.push({ path: `${directory}/${file}`, reference: clip.audioRef });
        entries.push({
          file, target, text: clip.text, lang: clip.lang, emotion: clip.emotion,
          providerId: clip.providerId, modelId: clip.modelId, voice: clip.voice
        });
      };
      carry("lexeme", lexeme.id, lexeme.headword, "headword");
      article.senses.forEach(({ sense, examples }, index) => {
        carry("sense", sense.id, sense.definition, `definition-${index + 1}`);
        examples.forEach((example, position) => carry("example", example.id, example.text, `example-${index + 1}-${position + 1}`));
      });
      article.attestations.forEach((attestation, index) =>
        carry("attestation", attestation.id, attestation.text, `attestation-${index + 1}`));
      if (entries.length) files.push({ path: `${directory}/${CLIPS_FILE}`, text: document(entries) });
    });
  });
  return { files, clips };
}

export function exportBundle(graph: VocabularyGraph, options: ExportOptions, exportedAt: string): BundleFile[] {
  const present = languageOptions(graph).map((option) => option.code);
  const articleOf = articleReader(graph);
  const languages = options.language === "all"
    ? present
    : present.filter((code) => code === options.language);

  const files: BundleFile[] = [];
  let lexemes = 0;

  languages.forEach((language) => {
    // Sorted before naming, so which of two colliding slugs gets the suffix never depends on the
    // order the replica happened to store them in.
    const words = lexemesIn(graph, language)
      .slice()
      .sort((left, right) => left.lemma.localeCompare(right.lemma) || left.id.localeCompare(right.id));
    const names = uniqueNames(words);
    words.forEach((lexeme) => {
      const article = articleOf(lexeme.id);
      if (!article) return;
      lexemes += 1;
      files.push({
        path: `${language}/${names.get(lexeme.id)}.yaml`,
        // No study state: review history is irreplaceable but it is not vocabulary, and it is
        // backed up with the Anki collection it belongs to (`docs/plans/backups.md`).
        text: yamlForDraft(stripIds(draftFor(article)))
      });
    });
    if (options.markdown) {
      markdownFor(graph, language, exportedAt).forEach((file) => {
        files.push({ path: `${MARKDOWN_DIRECTORY}/${file.path}`, text: file.text });
      });
    }
  });

  const vocabularyRecords = vocabularyContent(graph, languages);
  const topicRecords = topicContent(graph);

  return [
    {
      path: MANIFEST_FILE,
      // No ownerId, no datasetId, no cursor: a bundle is not a replica, and a shared vocabulary
      // must not carry the account it came from.
      text: document({
        format: BUNDLE_FORMAT,
        schemaVersion: SCHEMA_VERSION,
        exportedAt: quoted(exportedAt),
        languages,
        counts: { vocabularies: vocabularyRecords.length, topics: topicRecords.length, lexemes }
      })
    },
    { path: VOCABULARIES_FILE, text: document(vocabularyRecords) },
    { path: TOPICS_FILE, text: document(topicRecords) },
    ...files,
    ...(options.pronunciations ? pronunciationsIn(graph, options).files : [])
  ];
}

export function bundleName(language: string | "all", exportedAt: string): string {
  return `acervo-${language === "all" ? "all" : language}-${exportedAt.slice(0, 10)}.zip`;
}

/* ── reading ────────────────────────────────────────────────────────────*/

export interface BundleProblem {
  path: string;
  message: string;
}

export interface BundlePlan {
  schemaVersion: number;
  vocabularies: VocabularyInput[];
  topics: TopicInput[];
  articles: { path: string; draft: ArticleDraft }[];
  /** Word file path (`es/picar.yaml`) → the clips its `clips.yaml` describes. */
  clips: Map<string, ClipEntry[]>;
  problems: BundleProblem[];
}

/**
 * The only compatibility step in Acervo, and a deliberate exception to the rule against them.
 *
 * Everywhere else the current model simply replaces the old one, because there is nothing to
 * protect. A bundle is different: it is a file that has left the application and outlived the
 * schema it was written under, which is the entire reason it exists. So an easy adaptation — a
 * renamed field, a new one with a sensible default, an enum value that maps cleanly — belongs here,
 * in one function, rewriting the text before `parseArticle` ever sees it. Anything that is not easy
 * is refused and converted outside the application, and this function must never grow into a second
 * pipeline.
 *
 * Version 6 is readable as it stands. Version 7 added optional keys to a picture — the example it
 * anchors on, and the state the server keeps about drawing it — and a version 6 word file simply
 * does not carry them, which `readPrompt` already reads as "none" and "nothing attempted". Version
 * 8 added optional keys to an example — a clip's channel, its end, and the corpus segment it names
 * — and neither an older word file carries them, which `readExample` already reads as absent.
 * Nothing was renamed and nothing was removed in either step, so there is no text to rewrite: these
 * are versions being *accepted*, which is the cheapest form the exception takes and the one to
 * prefer.
 *
 * Version 9 added an optional `emoji` to a sense, which an older file simply lacks, and removed an
 * example's `approved`, which every older file carries and the reader now refuses as unknown. That
 * is the one rewrite here: the line is dropped from each word file. It carried no information —
 * nothing ever set it true — so there is nothing to carry forward.
 *
 * Version 10 added an optional `emotion` to an example, which an older file simply lacks, and removed
 * an example's `audioRef`, a pasted reference nothing ever generated. That line is dropped the way
 * `approved` is; a clip is its own record now, carried under `audio/` rather than in the word file.
 *
 * `clipsSearchedAt` is deliberately not in the format at all. It is state the server keeps, like a
 * picture's attempt counter, so an imported word arrives never-consulted and its enrichment finds it —
 * which is the right answer for a word that has just changed accounts.
 *
 * Note what is not here. A version 6 bundle carries no example ids, so a picture in one cannot name
 * the sentence it illustrates and does not get an anchor invented for it — matching by position or
 * by text would be a guess, and a wrong anchor puts the picture under the wrong sentence.
 */
const READABLE = new Set([SCHEMA_VERSION, 19, 14, 9, 8, 7, 6]);

/**
 * Version 15 gave a story part a recording. A story is not in a bundle and no word file changed, so
 * a version 14 bundle is read exactly as it stands — accepted, with nothing to rewrite, which is the
 * form of this exception to prefer. Without this line every bundle exported the day before would
 * have been refused for a change that has nothing to do with it.
 */
/*
 * Version 20 gave a vocabulary an accent. A version 19 bundle names none, and a vocabulary without
 * one is exactly what an absent `region` reads as, so it too is accepted as it stands.
 */
function upgradeBundle(files: BundleFile[], from: number): BundleFile[] {
  if (from === SCHEMA_VERSION || from === 19 || from === 14) return files;
  if (READABLE.has(from)) {
    return files.map((file) => isWordFile(file.path)
      ? {
          ...file,
          text: file.text
            .replace(/^[ \t]*approved:[ \t]*(?:true|false)[ \t]*\r?\n/gm, "")
            .replace(/^[ \t]*audioRef:.*\r?\n/gm, "")
        }
      : file);
  }
  throw new Error(
    `This bundle was exported from schema version ${from} and Acervo now uses version ${SCHEMA_VERSION}. `
    + "Convert its YAML files to the current shape and import it again."
  );
}

/** macOS zips a folder as a folder. Strip the wrapper so a re-zipped export still reads. */
function unwrap(files: BundleFile[]): BundleFile[] {
  const roots = new Set(files.map((file) => file.path.split("/")[0]));
  if (roots.size !== 1) return files;
  const [root] = [...roots];
  if (files.some((file) => file.path === root)) return files;
  return files.map((file) => ({ ...file, path: file.path.slice(root.length + 1) }));
}

function isWordFile(path: string): boolean {
  if (RESERVED.includes(path)) return false;
  if (path.startsWith(`${MARKDOWN_DIRECTORY}/`)) return false;
  if (path.startsWith(`${MEDIA_DIRECTORY}/`)) return false;
  if (path.startsWith(`${AUDIO_DIRECTORY}/`)) return false;
  if (!/\.ya?ml$/i.test(path)) return false;
  return path.split("/").length <= 2;
}

function readRecords<T>(
  files: BundleFile[], path: string, problems: BundleProblem[], read: (raw: Record<string, unknown>) => T
): T[] {
  const file = files.find((candidate) => candidate.path === path);
  if (!file) return [];
  let parsed: unknown;
  try { parsed = parse(file.text); }
  catch (error) {
    problems.push({ path, message: error instanceof Error ? error.message : "could not be read." });
    return [];
  }
  if (parsed === null || parsed === undefined) return [];
  if (!Array.isArray(parsed)) {
    problems.push({ path, message: "expected a list of records." });
    return [];
  }
  return parsed.flatMap((raw, index) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      problems.push({ path, message: `entry ${index + 1} is not a block of fields.` });
      return [];
    }
    try { return [read(raw as Record<string, unknown>)]; }
    catch (error) {
      problems.push({ path, message: `entry ${index + 1} ${error instanceof Error ? error.message : "is invalid."}` });
      return [];
    }
  });
}

const text = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value.trim() : null;

export function readBundle(input: BundleFile[]): BundlePlan {
  const problems: BundleProblem[] = [];
  const unwrapped = unwrap(input);

  const manifestFile = unwrapped.find((file) => file.path === MANIFEST_FILE);
  let schemaVersion = SCHEMA_VERSION;
  if (manifestFile) {
    const manifest = parse(manifestFile.text) as Record<string, unknown> | null;
    const format = text(manifest?.format);
    if (format && format !== BUNDLE_FORMAT) {
      throw new Error(
        `This bundle uses the ${format} layout and Acervo reads ${BUNDLE_FORMAT}. It cannot be imported as it is.`
      );
    }
    if (typeof manifest?.schemaVersion === "number") schemaVersion = manifest.schemaVersion;
  } else if (!unwrapped.some((file) => isWordFile(file.path))) {
    throw new Error(`This file does not look like an Acervo export — it has no ${MANIFEST_FILE} and no entries.`);
  }

  const files = upgradeBundle(unwrapped, schemaVersion);

  const vocabularyRecords = readRecords<VocabularyInput>(files, VOCABULARIES_FILE, problems, (raw) => {
    const language = text(raw.language);
    if (!language) throw new Error("has no language.");
    const glossLangs = Array.isArray(raw.glossLangs)
      ? raw.glossLangs.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      : [];
    if (!glossLangs.length) throw new Error("has no gloss languages.");
    return {
      language,
      definitionLang: text(raw.definitionLang) ?? language,
      glossLangs,
      notesLang: text(raw.notesLang) ?? glossLangs[0],
      displayName: text(raw.displayName),
      flag: text(raw.flag),
      region: text(raw.region)?.toUpperCase() ?? null,
      order: typeof raw.order === "number" ? raw.order : 0
    };
  });

  const topicRecords = readRecords<TopicInput>(files, TOPICS_FILE, problems, (raw) => {
    const name = text(raw.name);
    if (!name) throw new Error("has no name.");
    return { name, icon: text(raw.icon), order: typeof raw.order === "number" ? raw.order : 0 };
  });

  const articles = files
    .filter((file) => isWordFile(file.path))
    .sort((left, right) => left.path.localeCompare(right.path))
    .flatMap(({ path, text: source }) => {
      try { return [{ path, draft: parseArticle(source) }]; }
      catch (error) {
        const message = error instanceof YamlProblems
          ? error.problems.map((problem) => problem.message).join("; ")
          : error instanceof Error ? error.message : "could not be read.";
        problems.push({ path, message });
        return [];
      }
    });

  const clips = new Map<string, ClipEntry[]>();
  files
    .filter((file) => file.path.startsWith(`${AUDIO_DIRECTORY}/`) && file.path.endsWith(`/${CLIPS_FILE}`))
    .forEach((file) => {
      const word = `${file.path.slice(AUDIO_DIRECTORY.length + 1, -(CLIPS_FILE.length + 1))}.yaml`;
      const entries = readRecords<ClipEntry>(files, file.path, problems, (raw) => {
        const target = text(raw.target) as PronunciationTarget | null;
        const said = typeof raw.text === "string" ? raw.text : null;
        const [fileName, lang, providerId, modelId] = [text(raw.file), text(raw.lang), text(raw.providerId), text(raw.modelId)];
        if (!fileName || !target || !["lexeme", "sense", "example", "attestation"].includes(target) || !said || !lang || !providerId || !modelId) {
          throw new Error("does not say which file, record, words and model it is.");
        }
        return { file: fileName, target, text: said, lang, emotion: text(raw.emotion), providerId, modelId, voice: text(raw.voice) };
      });
      if (entries.length) clips.set(word, entries);
    });

  return { schemaVersion, vocabularies: vocabularyRecords, topics: topicRecords, articles, clips, problems };
}

/* ── importing ──────────────────────────────────────────────────────────*/

export interface ImportReport {
  vocabulariesAdded: number;
  topicsAdded: number;
  added: number;
  /** Pictures put back from the bundle's `media/` directory. */
  picturesRestored: number;
  /** Pronunciations put back from the bundle's `audio/` directory. */
  pronunciationsRestored: number;
  skipped: { language: string; headword: string }[];
  failed: BundleProblem[];
  /** True when the run stopped early: the server went away, or the owner cancelled. */
  aborted: boolean;
}

export interface ImportSignal { cancelled: boolean }

/**
 * The bytes of one picture, and the model that drew it, on their way back into a word.
 *
 * A callback rather than a transport, so this module keeps holding neither: `TransferPanel.tsx`
 * owns the zip and the browser's file handling, and putting a picture back is the same act — and
 * the same route — as attaching one by hand.
 */
export type RestorePicture = (
  senseId: string,
  bytes: Uint8Array,
  drawnBy: string | null
) => Promise<void>;

/** `media/<language>/<slug>-<sense number>.webp` -> its bytes, as the zip holds them. */
export type BundlePictures = ReadonlyMap<string, Uint8Array>;

/** Put one clip back on the record it reads, with who recorded it. The same callback shape as a picture. */
export type RestoreClip = (target: PronunciationTarget, id: string, bytes: Uint8Array, entry: ClipEntry) => Promise<void>;

/** The bundle's clip files by path, and how to put one back — or nothing, when that was switched off. */
export interface BundleRecordings {
  files: ReadonlyMap<string, Uint8Array>;
  restore: RestoreClip;
}

const DISCONNECTED = "not connected to the server";

/**
 * Every id in a document is re-minted on the way in.
 *
 * An imported bundle must not depend on where it came from, and re-importing the same file twice
 * must not collide with what the first import created. Nulling the article id is also what makes
 * the document mean "a new word" to `saveArticle`, which is the only thing it can honestly mean in
 * a database that has never seen it.
 */
export function remintIds(draft: ArticleDraft): ArticleDraft {
  const minted = new Map<string, string>();
  const mint = (id: string | null) => {
    if (id) minted.set(id, newId());
  };
  draft.attestations.forEach((attestation) => mint(attestation.id));
  // A clip is the exception: its id is derived from its sense and the segment it quotes, so minting
  // a random one here would hand the destination account a row the clip search then writes again
  // under the derived id — one sense, one segment, two examples, and nothing failing. Leaving it
  // null lets `saveArticle` derive it against the sense this account just created.
  draft.senses.forEach((sense) => sense.examples.forEach((example) => {
    if (!example.clipRef) mint(example.id);
  }));
  // A reference to an id this file never stated cannot be honoured, so it becomes none rather than
  // pointing at whatever happens to hold that id in the destination account.
  const remap = (id: string | null) => (id ? minted.get(id) ?? null : null);

  const stripped = stripIds(draft);
  return {
    ...stripped,
    attestations: draft.attestations.map((attestation) => ({
      ...attestation,
      id: remap(attestation.id)
    })),
    senses: draft.senses.map((sense, index) => ({
      ...sense,
      id: null,
      examples: sense.examples.map((example) => ({
        ...example,
        id: remap(example.id),
        sourceAttestationId: remap(example.sourceAttestationId)
      })),
      images: stripped.senses[index].images.map((image) => ({
        ...image,
        exampleId: remap(image.exampleId),
        // The validator refuses a rendering model with nothing rendered, and the picture arrives
        // separately — so this is carried by `restoredPictures` and written with the bytes.
        imageModelId: null
      }))
    }))
  };
}

/**
 * An imported word is filed, never left in the Inbox.
 *
 * The Inbox holds what arrived without anyone reading it, which is why only unattended capture puts
 * a word there. A bundle is chosen from a file picker and applied on a button press, so nothing in
 * it arrived unread — and the bundles that exist were written when every captured word carried
 * `status: inbox`, so honouring the line files a whole vocabulary into a room it has to be emptied
 * out of one word at a time.
 *
 * Only `inbox` is rewritten. `learned`, `retired` and `suppressed` are curation the owner did, and
 * a bundle is a backup of that; the export still writes all four, and the asymmetry is the point —
 * the file records what a word *was*, this decides what it *becomes*.
 */
export function filed(draft: ArticleDraft): ArticleDraft {
  return draft.status === "inbox" ? { ...draft, status: "active" } : draft;
}

const key = (language: string, headword: string) => `${language}\n${headword.trim().toLowerCase()}`;

/**
 * Applies a bundle, one word at a time, through the one write path.
 *
 * A word already in the vocabulary is skipped rather than merged or duplicated: an import must
 * never cost you curation you did after the export, and the report says exactly what it left alone.
 * A word that fails is reported by file and the run continues — during the phase where the schema
 * moves, knowing which three of four hundred entries were refused is the whole value.
 */
export async function importBundle(
  repository: AcervoRepository,
  plan: BundlePlan,
  onProgress: (done: number, total: number) => void = () => {},
  signal: ImportSignal = { cancelled: false },
  pictures: BundlePictures = new Map(),
  restore: RestorePicture | null = null,
  recordings: BundleRecordings | null = null,
  enrich: ((lexemeId: string) => Promise<unknown>) | null = null
): Promise<ImportReport> {
  const report: ImportReport = {
    vocabulariesAdded: 0, topicsAdded: 0, added: 0, picturesRestored: 0, pronunciationsRestored: 0,
    skipped: [], failed: [], aborted: false
  };

  const snapshot = repository.snapshot();
  const live = <T extends { deleted: boolean }>(records: T[]) => records.filter((record) => !record.deleted);
  const languages = new Set(live(snapshot.vocabularies).map((entry) => entry.language));
  const topics = new Set(live(snapshot.topics).map((topic) => topic.name.trim().toLowerCase()));
  const words = new Set(live(snapshot.lexemes).map((lexeme) => key(lexeme.language, lexeme.headword)));

  const total = plan.vocabularies.length + plan.topics.length + plan.articles.length;
  let done = 0;
  const step = () => onProgress((done += 1), total);

  /** Only a lost server stops the run; a refused record is this record's problem, not the batch's. */
  const disconnected = (error: unknown) => error instanceof Error && error.message.includes(DISCONNECTED);
  const messageOf = (error: unknown) => error instanceof Error ? error.message : String(error);

  // Vocabularies and topics first: `saveArticle` resolves topics by name and refuses one it does
  // not hold, so a bundle would otherwise fail on every word that carries a new topic.
  for (const vocabulary of plan.vocabularies) {
    if (signal.cancelled) return { ...report, aborted: true };
    if (!languages.has(vocabulary.language)) {
      try {
        await repository.saveVocabulary(vocabulary);
        languages.add(vocabulary.language);
        report.vocabulariesAdded += 1;
      } catch (error) {
        report.failed.push({ path: VOCABULARIES_FILE, message: `${vocabulary.language}: ${messageOf(error)}` });
        if (disconnected(error)) return { ...report, aborted: true };
      }
    }
    step();
  }

  for (const topic of plan.topics) {
    if (signal.cancelled) return { ...report, aborted: true };
    if (!topics.has(topic.name.trim().toLowerCase())) {
      try {
        await repository.saveTopic(topic);
        topics.add(topic.name.trim().toLowerCase());
        report.topicsAdded += 1;
      } catch (error) {
        report.failed.push({ path: TOPICS_FILE, message: `${topic.name}: ${messageOf(error)}` });
        if (disconnected(error)) return { ...report, aborted: true };
      }
    }
    step();
  }

  for (const { path, draft } of plan.articles) {
    if (signal.cancelled) return { ...report, aborted: true };
    const identity = key(draft.language, draft.headword);
    if (words.has(identity)) {
      report.skipped.push({ language: draft.language, headword: draft.headword });
      step();
      continue;
    }
    try {
      // Enrichment is asked for once the bundle's pictures and clips are back, so the server fills
      // in only what the bundle did not carry and never draws over a picture it is about to get.
      const lexemeId = await repository.saveArticle(filed(remintIds(draft)), undefined, { enrich: false });
      words.add(identity);
      report.added += 1;
      // After the word exists, because a picture belongs to a sense that has to be there first —
      // and the sense ids are the ones just minted, which only the replica knows.
      report.picturesRestored += await restorePictures(
        repository, lexemeId, path, draft, pictures, restore, report
      );
      report.pronunciationsRestored += await restoreClips(repository, lexemeId, plan.clips.get(path) ?? [], path, recordings, report);
      // A word whose enrichment could not be asked for is still imported; Try again is on its page.
      if (enrich) await enrich(lexemeId).catch(() => undefined);
    } catch (error) {
      report.failed.push({ path, message: messageOf(error) });
      if (disconnected(error)) return { ...report, aborted: true };
    }
    step();
  }

  return report;
}

/**
 * Put a word's pictures back, one per sense, from the bundle's `media/` directory.
 *
 * Matched by **position**: `media/es/picar-2.webp` is the second sense of `es/picar.yaml`, which is
 * the same pairing the export writes and the only one a bundle can express — it carries no ids a
 * person or a second account could use. So the sense ids come from the replica, in the order
 * `sensesOf` gives, which is the order the article numbers them in.
 *
 * A picture that cannot be put back is reported and the word is kept. The words are the part that
 * cannot be regenerated; a picture is regenerable by design, and losing the whole import over one
 * refused upload would be the wrong trade.
 */
async function restorePictures(
  repository: AcervoRepository,
  lexemeId: string,
  path: string,
  draft: ArticleDraft,
  pictures: BundlePictures,
  restore: RestorePicture | null,
  report: ImportReport
): Promise<number> {
  if (!restore || pictures.size === 0) return 0;
  const base = path.replace(/\.ya?ml$/i, "");
  const senses = sensesOf(repository.snapshot(), lexemeId);
  // By `order`, matching how `sensesOf` sorts and how the export numbered the files. Not document
  // order: a hand-edited word file may list its senses in any order, and indexing by position
  // would then put each picture under the wrong sense — the one failure here that says nothing.
  const written = draft.senses.slice().sort((left, right) => left.order - right.order);

  let restored = 0;
  for (const [index, sense] of senses.entries()) {
    const name = `${MEDIA_DIRECTORY}/${base}-${index + 1}.webp`;
    const bytes = pictures.get(name) ?? bySuffix(pictures, name);
    if (!bytes) continue;
    // The model that drew it, carried by the word file and written together with the bytes: a row
    // may not name a rendering model with nothing rendered, so neither travels without the other.
    const drawnBy = written[index]?.images[0]?.imageModelId ?? null;
    try {
      await restore(sense.id, bytes, drawnBy);
      restored += 1;
    } catch (error) {
      report.failed.push({
        path: name,
        message: error instanceof Error ? error.message : String(error)
      });
    }
  }
  return restored;
}

/**
 * Put a word's clips back, each on the record that says its words.
 *
 * Matched by **text**, which is the one place in a bundle where that is right rather than a guess: a
 * clip is a recording of particular words, so the record it belongs to is whichever record now says
 * them, and the server refuses it anyway if the words differ. A clip with no such record is left out
 * quietly — the word file was edited after the export, and the recording is of something else.
 */
async function restoreClips(
  repository: AcervoRepository,
  lexemeId: string,
  entries: ClipEntry[],
  path: string,
  recordings: BundleRecordings | null,
  report: ImportReport
): Promise<number> {
  if (!recordings || !entries.length) return 0;
  const graph = repository.snapshot();
  const live = <T extends { deleted: boolean }>(records: T[]) => records.filter((record) => !record.deleted);
  const senses = live(graph.senses).filter((sense) => sense.lexemeId === lexemeId);
  const senseIds = new Set(senses.map((sense) => sense.id));
  const find = (entry: ClipEntry): string | undefined => {
    switch (entry.target) {
      case "lexeme": return graph.lexemes.find((lexeme) => lexeme.id === lexemeId && lexeme.headword === entry.text)?.id;
      case "sense": return senses.find((sense) => sense.definition === entry.text)?.id;
      case "example": return live(graph.examples).find((example) => senseIds.has(example.senseId) && example.text === entry.text)?.id;
      case "attestation": return live(graph.attestations).find((one) => one.lexemeId === lexemeId && one.text === entry.text)?.id;
    }
  };
  const directory = `${AUDIO_DIRECTORY}/${path.replace(/\.ya?ml$/i, "")}`;
  let restored = 0;
  for (const entry of entries) {
    const name = `${directory}/${entry.file}`;
    const bytes = recordings.files.get(name) ?? bySuffix(recordings.files, name);
    const id = find(entry);
    if (!bytes || !id) continue;
    try {
      await recordings.restore(entry.target, id, bytes, entry);
      restored += 1;
    } catch (error) {
      report.failed.push({ path: name, message: error instanceof Error ? error.message : String(error) });
    }
  }
  return restored;
}

/**
 * The same picture under a folder the archiver added.
 *
 * `readBundle` already unwraps a single wrapping directory from the text files — re-zipping a
 * bundle on a Mac produces one — but the pictures are read straight from the archive, so their
 * keys would still carry it and every lookup would miss in silence. The suffix includes the
 * language directory and the word's own slug, so it is specific enough to match on.
 */
function bySuffix(pictures: BundlePictures, name: string): Uint8Array | undefined {
  for (const [path, bytes] of pictures) {
    if (path.endsWith(`/${name}`)) return bytes;
  }
  return undefined;
}
