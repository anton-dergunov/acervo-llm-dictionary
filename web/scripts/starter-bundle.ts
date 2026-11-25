/**
 * The starter vocabularies as bundles: `npx tsx scripts/starter-bundle.ts [--only es-MX,ru] [--tag TAG]`
 * (run from `web/`).
 *
 * A laptop tool, not part of the app (`docs/plans/first-use/starter-vocabularies.md`, step 7). It
 * reads what the builder made — each word's final draft in `data/starter/<id>/compose/`, each
 * sense's concept in `data/starter/<id>/match/`, the shared pictures in `vocabularies/pictures/` —
 * and writes, per vocabulary:
 *
 * - `vocabularies/<id>/`: the bundle's text, unzipped and tracked, so a word can be read on GitHub
 *   and `git log` of its file is its history. Written by `bundleFiles`, the function export uses, so
 *   a starter is byte for byte what exporting the same words writes;
 * - `vocabularies/<id>/placement.json`: which shared picture each bundle picture path takes;
 * - `vocabularies/out/acervo-starter-<id>.zip` (ignored): the text and the placed pictures, for a
 *   GitHub release. Deterministic: rebuilt from the same inputs it has the same digest;
 * - `vocabularies/catalogue.json`: every starter, its size and digest, and the release to fetch it
 *   from; and `vocabularies/out/SHA256SUMS`.
 *
 * Every bundle is read back through `readBundle` before it is written, and refused if any word file
 * does not parse.
 */

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { zipSync, type Zippable } from "fflate";
import { parse } from "yaml";
import type { VocabularyInput, TopicInput } from "../src/domain";
import { automaticFlag, languageOf } from "../src/languages";
import { bundleFiles, namedWords, picturePath, readBundle, type BundleFile } from "../src/transfer";
import type { ArticleDraft, ImagePromptDraft } from "../src/yaml";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const BUILDER = join(ROOT, "data", "starter");
const CONFIG = join(ROOT, "scripts", "starter", "vocabularies.yaml");
const PACKAGE = join(ROOT, "vocabularies");
const PICTURES = join(PACKAGE, "pictures");
const OUT = join(PACKAGE, "out");
const CATALOGUE = join(PACKAGE, "catalogue.json");
const REPOSITORY = "https://github.com/anton-dergunov/acervo-llm-dictionary";

/** How the app names the model that drew the starter pictures: Nano Banana, through Google Cloud. */
const DRAWN_BY = "google-cloud:gemini-nano-banana-2.1";

interface Config {
  vocabularies: Array<Record<string, unknown> & { id: string; language: string }>;
  defaults: Record<string, unknown>;
  topics: Record<string, string>;
  topicIcons: Record<string, string>;
}

interface PictureRecord {
  sense: string;
  styleId: string;
  brief: string;
  model: string;
  drawnAt: string;
  promptVersion: string;
  briefModel: string | null;
  seed: number | null;
}

interface Composed {
  word: { key: string };
  at: string;
  corrected?: { at: string };
  draft: ArticleDraft;
}

interface MatchFile {
  at: string;
  matches: Array<{ id: string; concept: string | null }>;
  followUps?: Array<{ at: string }>;
}

interface Starter {
  id: string;
  language: string;
  region: string | null;
  displayName: string;
  flag: string;
  definitionLang: string;
  glossLangs: string[];
  level: string | null;
  words: number;
  pictured: number;
  file: string;
  bytes: number;
  sha256: string;
}

const readJson = <T>(path: string): T => JSON.parse(readFileSync(path, "utf8")) as T;
const latest = (instants: string[]) => instants.map((at) => new Date(at).toISOString()).sort().at(-1)!;

function options(argv: string[]): { only: string[] | null; tag: string | null } {
  const value = (flag: string) => {
    const at = argv.indexOf(flag);
    return at >= 0 ? argv[at + 1] ?? null : null;
  };
  const only = value("--only");
  return { only: only ? only.split(",").map((id) => id.trim()).filter(Boolean) : null, tag: value("--tag") };
}

function vocabularyRecord(entry: Record<string, unknown>, defaults: Record<string, unknown>): VocabularyInput {
  const merged = { ...defaults, ...entry } as Record<string, unknown>;
  const language = merged.language as string;
  const region = (merged.region as string | undefined) ?? null;
  const glossLangs = merged.glossLangs as string[];
  const flag = (merged.flag as string | undefined) ?? null;
  return {
    language,
    definitionLang: merged.definitionLang as string,
    glossLangs,
    notesLang: (merged.notesLang as string | undefined) ?? glossLangs[0],
    displayName: (merged.displayName as string | undefined) ?? null,
    // A stored flag that restated the automatic one would stop following the variety
    // (`docs/architecture/data-model.md`), so only a different one is kept.
    flag: flag && flag !== automaticFlag(language, region) ? flag : null,
    region,
    level: (merged.level as VocabularyInput["level"]) ?? null,
    learnerNote: null,
    order: 0
  };
}

/** The concept's picture, as the record a picture drawn in the app would have. */
function pictureEntry(picture: PictureRecord): ImagePromptDraft {
  return {
    id: null,
    exampleId: null,
    prompt: picture.brief,
    styleId: picture.styleId,
    seed: picture.seed ?? 0,
    // The brief writer; empty for the two briefs written by hand in a session.
    modelId: picture.briefModel ?? "",
    promptVersion: picture.promptVersion,
    imageRef: null,
    imageModelId: DRAWN_BY
  };
}

function concepts(folder: string): { byId: Map<string, string | null>; at: string[] } {
  const byId = new Map<string, string | null>();
  const at: string[] = [];
  const directory = join(folder, "match");
  readdirSync(directory).filter((name) => name.endsWith(".json")).sort().forEach((name) => {
    const matched = readJson<MatchFile>(join(directory, name));
    at.push(matched.at, ...(matched.followUps ?? []).map((call) => call.at));
    matched.matches.forEach((entry) => byId.set(entry.id, entry.concept));
  });
  return { byId, at };
}

function build(entry: Config["vocabularies"][number], config: Config, pictures: Record<string, PictureRecord>,
               tag: string | null): Starter {
  const id = entry.id;
  const folder = join(BUILDER, id);
  const vocabulary = vocabularyRecord(entry, config.defaults);
  const language = vocabulary.language;
  const { byId: conceptOf, at: matchedAt } = concepts(folder);

  const composed = readdirSync(join(folder, "compose"))
    .filter((name) => name.endsWith(".json") && !name.endsWith(".failed.json"))
    .sort()
    .map((name) => readJson<Composed>(join(folder, "compose", name)));

  const placement: Record<string, string> = {};
  const lexemes = composed.map((one) => ({
    id: one.word.key, headword: one.draft.headword, lemma: one.draft.lemma, reading: one.draft.reading, one
  }));
  const words = namedWords(lexemes).map(({ lexeme, name }) => {
    const draft = lexeme.one.draft;
    const placed = new Set<string>();
    const senses = draft.senses.slice().sort((left, right) => left.order - right.order).map((sense, index) => {
      const concept = sense.id ? conceptOf.get(sense.id) ?? null : null;
      // One picture of a meaning per word: two senses matched to one concept show it once, on the first.
      if (!concept || !pictures[concept] || placed.has(concept)) return sense;
      placed.add(concept);
      placement[picturePath(language, name, index)] = concept;
      return { ...sense, images: [pictureEntry(pictures[concept])] };
    });
    return { language, name, draft: { ...draft, senses } };
  });

  const topics: TopicInput[] = Object.entries(config.topics).map(([key, name], order) => ({
    name, icon: config.topicIcons[key] ?? null, order
  }));
  const exportedAt = latest([
    ...composed.flatMap((one) => [one.at, ...(one.corrected ? [one.corrected.at] : [])]),
    ...matchedAt,
    ...Object.values(placement).map((concept) => pictures[concept].drawnAt)
  ]);
  const files = bundleFiles({ exportedAt, languages: [language], vocabularies: [vocabulary], topics, words });

  const plan = readBundle(files);
  if (plan.problems.length || plan.articles.length !== words.length) {
    const shown = plan.problems.slice(0, 5).map((problem) => `${problem.path}: ${problem.message}`).join("\n  ");
    throw new Error(`${id}: the bundle does not read back (${plan.problems.length} problems)\n  ${shown}`);
  }

  writeText(join(PACKAGE, id), files, placement);
  const file = `acervo-starter-${id}.zip`;
  const bytes = zipped(files, placement, exportedAt);
  writeFileSync(join(OUT, file), bytes);
  const pictured = new Set(Object.keys(placement).map((path) => path.replace(/-\d+\.webp$/, ""))).size;
  console.log(`${id}: ${words.length} words, ${pictured} with a picture, ${(bytes.length / 1e6).toFixed(1)} MB`
    + (tag ? "" : " (no --tag: the catalogue keeps its release)"));
  return {
    id, language, region: vocabulary.region, displayName: vocabulary.displayName ?? language,
    flag: vocabulary.flag ?? automaticFlag(language, vocabulary.region),
    definitionLang: vocabulary.definitionLang, glossLangs: vocabulary.glossLangs, level: vocabulary.level,
    words: words.length, pictured, file, bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex")
  };
}

/** The tracked text: rewritten whole, so a word the builder dropped leaves with its file. */
function writeText(directory: string, files: BundleFile[], placement: Record<string, string>): void {
  rmSync(directory, { recursive: true, force: true });
  files.forEach((file) => {
    const path = join(directory, file.path);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, file.text);
  });
  writeFileSync(join(directory, "placement.json"), `${JSON.stringify(placement, null, 2)}\n`);
}

/** Same inputs, same bytes: every entry carries the bundle's own date, and pictures are stored. */
function zipped(files: BundleFile[], placement: Record<string, string>, exportedAt: string): Uint8Array {
  const mtime = new Date(exportedAt);
  const entries: Zippable = {};
  files.forEach((file) => { entries[file.path] = [new TextEncoder().encode(file.text), { mtime, level: 9 }]; });
  Object.entries(placement).sort(([left], [right]) => left.localeCompare(right)).forEach(([path, concept]) => {
    entries[path] = [readFileSync(join(PICTURES, `${concept}.webp`)), { mtime, level: 0 }];
  });
  return zipSync(entries);
}

function main(): void {
  const { only, tag } = options(process.argv.slice(2));
  const config = parse(readFileSync(CONFIG, "utf8")) as Config;
  const pictures = readJson<Record<string, PictureRecord>>(join(PACKAGE, "pictures.json"));
  const chosen = config.vocabularies.filter((entry) => !only || only.includes(entry.id));
  const unknown = (only ?? []).filter((id) => !config.vocabularies.some((entry) => entry.id === id));
  if (unknown.length) throw new Error(`unknown vocabulary: ${unknown.join(", ")}`);
  mkdirSync(OUT, { recursive: true });

  const previous = existsSync(CATALOGUE)
    ? readJson<{ tag: string | null; starters: Starter[] }>(CATALOGUE)
    : { tag: null, starters: [] };
  const built = new Map(previous.starters.map((starter) => [starter.id, starter]));
  chosen.forEach((entry) => built.set(entry.id, build(entry, config, pictures, tag)));
  const starters = config.vocabularies.flatMap((entry) => built.get(entry.id) ?? []);
  const release = tag ?? previous.tag;

  writeFileSync(CATALOGUE, `${JSON.stringify({
    note: "The starter vocabularies a person can install: each is an acervo-export/1 bundle attached to the "
      + "GitHub release `tag`, at <repository>/releases/download/<tag>/<file>. Written by "
      + "web/scripts/starter-bundle.ts; see vocabularies/README.md.",
    repository: REPOSITORY,
    tag: release,
    starters
  }, null, 2)}\n`);
  writeFileSync(join(OUT, "SHA256SUMS"), starters.map((starter) => `${starter.sha256}  ${starter.file}\n`).join(""));
  writeTable(starters, release);
}

const TABLE_BEGIN = "<!-- starters: written by web/scripts/starter-bundle.ts -->";
const TABLE_END = "<!-- /starters -->";

/** The README's table of starters, rewritten from the catalogue so its links and sizes never drift. */
function writeTable(starters: Starter[], release: string | null): void {
  const readme = join(PACKAGE, "README.md");
  const text = readFileSync(readme, "utf8");
  const begin = text.indexOf(TABLE_BEGIN);
  const end = text.indexOf(TABLE_END);
  if (begin < 0 || end < begin) throw new Error(`vocabularies/README.md has no ${TABLE_BEGIN} … ${TABLE_END} block`);
  const rows = starters.map((starter) => {
    const size = `${Math.round(starter.bytes / 1e6)} MB`;
    const download = release ? `[${size}](${REPOSITORY}/releases/download/${release}/${starter.file})` : `${size}, not published yet`;
    return `| ${starter.flag} ${starter.displayName} | ${languageOf(starter.definitionLang).name} | ${starter.words} | `
      + `${starter.pictured} | [words](${starter.id}/) | ${download} |`;
  });
  const table = [
    "| Vocabulary | Defined in | Words | With a picture | Read | Download |",
    "| --- | --- | ---: | ---: | --- | --- |",
    ...rows
  ].join("\n");
  writeFileSync(readme, `${text.slice(0, begin + TABLE_BEGIN.length)}\n${table}\n${text.slice(end)}`);
}

main();
