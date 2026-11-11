/**
 * The Obsidian projection: a generated, read-only mirror of the vocabulary as markdown.
 *
 * A second projection alongside `yaml.ts`, and the same rule applies — this is the only place
 * markdown is written. It is export-only by design (`docs/features/export.md`): reconciling
 * free-form markdown against a structured store is the coupling this application exists to escape,
 * so nothing reads it back.
 *
 * The shape is the convention the vault already uses, because a generated file that does not look
 * like the hand-written ones beside it is a file nobody reads:
 *
 *     ##### **el parlante** 🔊
 *     *speaker; loudspeaker*
 *     > Nos estamos conectando al **parlante** por Bluetooth. - We're connecting to the **speaker** via Bluetooth.
 *
 * Three lines at most, and that is the point. This file is scanned, not studied: a word, its
 * one-line gloss, and — only if there is one worth keeping — a sentence. Every sense, the notes and
 * the generated examples are deliberately left out; they are what the article is for, and putting
 * them here would turn a page you can run your eye down into a second copy of the vocabulary.
 *
 * Pure: no storage, no network, no DOM.
 */

import type { Example, Lexeme, VocabularyGraph } from "./domain";
import { isMandarin, languageOf } from "./languages";
import { accentedPinyin } from "./pinyin";
import { articleReader, lexemesIn, shortGlossOf, type Article } from "./selectors";

/** Words waiting to be filed, which the rail also keeps out of every topic. */
const INBOX_FILE = "Inbox";
/** Filed words that belong to no topic. The vault already calls this heap Misc. */
const UNFILED_FILE = "Misc";

/** Characters no filesystem agrees on. A topic is free text, so it can hold any of them. */
const ILLEGAL = /[/\\:*?"<>|#^[\]]/g;

function safeName(value: string): string {
  return value.replace(ILLEGAL, " ").replace(/\s+/g, " ").trim();
}

/**
 * `Spanish vocab - Technology.md`.
 *
 * The language is in the name rather than only in the directory, because Obsidian is searched by
 * note name: two languages with a Technology topic would otherwise be two notes called Technology,
 * and neither would be distinguishable from ordinary notes about technology.
 */
export function fileNameFor(language: string, section: string): string {
  return `${safeName(languageOf(language).name)} vocab - ${safeName(section)}.md`;
}

/** Bolds the form the example was matched on, which is what `matchedForm` is for. */
function emphasise(text: string, form: string | null): string {
  if (!form) return text;
  const at = text.indexOf(form);
  if (at < 0) return text;
  return `${text.slice(0, at)}**${form}**${text.slice(at + form.length)}`;
}

/**
 * A sentence earns its place here by having been met or written, not produced.
 *
 * Provenance is already modelled rather than flagged, so this needs no new field: an example drawn
 * from a sentence the owner supplied is `attestation`, and one they typed is `manual`. Everything
 * generated — `llm`, and the corpus origins — belongs to the article, where it can be judged.
 */
const KEPT: Example["origin"][] = ["attestation", "manual"];

export function entryFor(graph: VocabularyGraph, article: Article): string {
  const { lexeme, senses } = article;
  const heading = [
    `##### **${lexeme.headword}**`,
    lexeme.reading ? `*${isMandarin(lexeme.language) ? accentedPinyin(lexeme.reading) : lexeme.reading}*` : "",
    lexeme.emoji ?? ""
  ].filter(Boolean).join(" ");

  // The one-line form, exactly as the list shows it: the curated gloss when there is one, and the
  // first sense's otherwise. Not every sense — a word with four of them still gets one line here.
  const lines = [heading, `*${shortGlossOf(graph, lexeme)}*`];
  senses
    .flatMap((entry) => entry.examples)
    .filter((example) => KEPT.includes(example.origin))
    .forEach((example) => {
      const text = emphasise(example.text, example.matchedForm);
      const translation = example.translation
        ? ` - ${emphasise(example.translation, example.matchedTranslationForm)}`
        : "";
      lines.push(`> ${text}${translation}`);
    });
  return lines.join("\n");
}

/** Which file a word belongs in. Inbox first, mirroring the rail, which files nothing until it is out. */
function sectionsFor(graph: VocabularyGraph, lexeme: Lexeme): string[] {
  if (lexeme.status === "inbox") return [INBOX_FILE];
  const names = lexeme.topicIds
    .map((id) => graph.topics.find((topic) => topic.id === id && !topic.deleted))
    .filter((topic): topic is NonNullable<typeof topic> => Boolean(topic))
    .map((topic) => topic.name);
  return names.length ? names : [UNFILED_FILE];
}

export interface MarkdownFile { path: string; text: string }

/**
 * One file per language and section. A word filed under two topics appears in both — the file is a
 * view, not a home, and Obsidian is happier with a word present twice than absent once.
 */
export function markdownFor(graph: VocabularyGraph, language: string, exportedAt: string): MarkdownFile[] {
  const collator = new Intl.Collator(language);
  const sections = new Map<string, Article[]>();
  const articleOf = articleReader(graph);

  lexemesIn(graph, language).forEach((lexeme) => {
    const article = articleOf(lexeme.id);
    if (!article) return;
    sectionsFor(graph, lexeme).forEach((section) => {
      const bucket = sections.get(section) ?? [];
      bucket.push(article);
      sections.set(section, bucket);
    });
  });

  return [...sections.entries()]
    .sort(([left], [right]) => collator.compare(left, right))
    .map(([section, articles]) => {
      // Alphabetical, so re-exporting after adding a word is a one-hunk diff rather than a rewrite.
      const sorted = articles
        .slice()
        .sort((left, right) => collator.compare(left.lexeme.headword, right.lexeme.headword));
      const frontMatter = [
        "---",
        `acervo-export: "${exportedAt}"`,
        `language: ${language}`,
        `section: ${JSON.stringify(section)}`,
        "---",
        ""
      ].join("\n");
      const body = sorted.map((article) => entryFor(graph, article)).join("\n\n");
      return { path: fileNameFor(language, section), text: `${frontMatter}\n${body}\n` };
    });
}
