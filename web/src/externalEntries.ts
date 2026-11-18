/**
 * Pure derivation from what the external dictionaries answered to what the interface renders.
 *
 * The same standing as `selectors.ts`, and for the same reason: nothing here touches storage or the
 * network, so the whole external search and article surface is testable without a device holding a
 * single artifact. `dictionaries.ts` owns the transports; this owns what their answers mean.
 *
 * Two rules run through all of it. **These are never Acervo records.** They carry no id, no
 * revision and no study state, they are ordered separately from the owner's own words and they are
 * never interleaved with them. And **the source's own words are kept**: `posLabel` is displayed
 * verbatim, never bucketed into Acervo's part-of-speech enum, which §11.3 established does not
 * survive contact with real dictionaries.
 */

import type { OnlineArticle } from "./api";
import type { DictionaryArticle, DictionaryEntry, DictionaryTier } from "./dictionary";
import type { LookupResult } from "./dictionaries";
import { normaliseDictionaryHtml } from "./externalHtml";
import { accentedPinyin, accentedPinyinInText } from "./pinyin";

/** Where an answer came from. The interface says this out loud so nothing looks offline that isn't. */
export type ExternalOrigin = "device" | "server" | "online";

export interface SourceRef {
  dictionaryId: string;
  name: string;
  origin: ExternalOrigin;
}

/** One headword a dictionary holds. The gloss arrives later — listing costs far less than reading. */
export interface RawHit extends SourceRef {
  word: string;
  gloss?: string | null;
}

export interface ExternalRow {
  word: string;
  gloss: string;
  /** Every dictionary holding this word, best first. A row is a word, not a word-per-dictionary. */
  sources: SourceRef[];
  /** The nearest source, which decides the plate: stored here, on the server, or out on the web. */
  origin: ExternalOrigin;
}

export interface ExternalSection extends SourceRef {
  attribution: string;
  licence: string;
  /** What the catalogue says this dictionary is in, which an `html` payload never carries itself. */
  sourceLang: string;
  tier: DictionaryTier;
  /** `fields` and online sources. Render-only — `posLabel` is free text, `pos` may be absent. */
  articles: DictionaryArticle[];
  /** `html` sources: already sanitised and restyled by `externalHtml.ts`. */
  html: string;
}

export interface ExternalEntry {
  word: string;
  language: string | null;
  reading: string | null;
  ipa: string | null;
  posLabel: string | null;
  /** The first source's genders, joined: `masculine / feminine`. */
  gender: string | null;
  sections: ExternalSection[];
}

/** A noun's genders as one line, or `null` when the source gives none. */
export const genderOf = (article: DictionaryArticle): string | null =>
  article.genders?.length ? article.genders.join(" / ") : null;

/* ── ordering ───────────────────────────────────────────────────────────
   Nearest source first, everywhere: what this device holds answers before what the server holds,
   which answers before the web. It is also the order the artifact reader resolves in, so the two
   never disagree about which copy of a dictionary is "the" one. */

const ORIGIN_ORDER: Record<ExternalOrigin, number> = { device: 0, server: 1, online: 2 };

const encoder = new TextEncoder();

/**
 * Byte-wise comparison, matching the order the dictionary index is built in.
 *
 * Deliberately not `localeCompare` and not `<`: JavaScript compares UTF-16 code units, which
 * disagrees with UTF-8 byte order above the BMP (§11.2). Using one order in the reader and another
 * in the list would put rows in an order the reader would not reproduce.
 */
function compareWords(left: string, right: string): number {
  const a = encoder.encode(left);
  const b = encoder.encode(right);
  const limit = Math.min(a.length, b.length);
  for (let index = 0; index < limit; index += 1) {
    if (a[index] !== b[index]) return a[index] < b[index] ? -1 : 1;
  }
  return a.length - b.length;
}

/** The spelling the compiler also stores as an alias, so `Casa` and `casa` are one row. */
const folded = (word: string): string => word.normalize("NFC").toLowerCase();

/**
 * Every headword any dictionary offered, as one ranked list.
 *
 * Three dictionaries holding `casa` is one row naming three sources, not three rows of `casa`.
 * Grouping by dictionary was the alternative and it floods the section: the reader is looking for a
 * word, and which books happen to carry it is a fact about the word, not a way to organise it.
 */
export function mergeHits(query: string, hits: RawHit[]): ExternalRow[] {
  const target = folded(query.trim());
  const rows = new Map<string, ExternalRow>();
  for (const hit of hits) {
    const key = folded(hit.word);
    const existing = rows.get(key);
    const source: SourceRef = { dictionaryId: hit.dictionaryId, name: hit.name, origin: hit.origin };
    if (!existing) {
      rows.set(key, { word: hit.word, gloss: hit.gloss?.trim() ?? "", sources: [source], origin: hit.origin });
      continue;
    }
    if (!existing.sources.some((candidate) => candidate.dictionaryId === hit.dictionaryId)) {
      existing.sources.push(source);
    }
    // The first gloss offered wins, so the list does not flicker as slower sources land.
    if (!existing.gloss && hit.gloss?.trim()) existing.gloss = hit.gloss.trim();
    if (ORIGIN_ORDER[hit.origin] < ORIGIN_ORDER[existing.origin]) existing.origin = hit.origin;
  }

  for (const row of rows.values()) {
    row.sources.sort((left, right) => ORIGIN_ORDER[left.origin] - ORIGIN_ORDER[right.origin]
      || left.name.localeCompare(right.name));
  }

  return [...rows.values()].sort((left, right) => {
    // The word actually typed comes first even when it sorts late — it is the answer to the question.
    const exact = Number(folded(right.word) === target) - Number(folded(left.word) === target);
    if (exact) return exact;
    if (left.word.length !== right.word.length) return left.word.length - right.word.length;
    return compareWords(left.word, right.word);
  });
}

/* ── the gloss on a row ─────────────────────────────────────────────────
   One line, from whatever the source actually has. A dictionary's first definition is not a gloss
   in Acervo's sense and is not stored as one; it is the best one-line answer available, and saying
   nothing would make the row unreadable. */

const FIRST_LINE_LIMIT = 140;

function clamp(line: string): string {
  const collapsed = line.replace(/\s+/g, " ").trim();
  return collapsed.length > FIRST_LINE_LIMIT ? `${collapsed.slice(0, FIRST_LINE_LIMIT - 1).trimEnd()}…` : collapsed;
}

/** The one-line form of an entry, for the search row. Empty when the payload says nothing useful. */
export function glossOf(entry: DictionaryEntry): string {
  if (entry.tier === "fields") {
    const definitions = (entry.articles ?? [])
      .flatMap((article) => article.senses.map((sense) => sense.definition.trim()))
      .filter(Boolean);
    return clamp(definitions.slice(0, 3).join("; "));
  }
  // An html payload has no field to read, so the visible text is the honest answer — but its
  // structure is the only thing separating one meaning from the next, and `textContent` throws that
  // away: `noun`, `brothel`, `whorehouse` came out as `nounbrothelwhorehouse`.
  const body = new DOMParser().parseFromString(
    `<body>${normaliseDictionaryHtml(entry.html ?? "", entry.word)}</body>`, "text/html");
  /** Marks that say something *about* the word rather than what it means. */
  const ASIDE = new Set(["ext-gram", "ext-tag", "ext-tags", "ext-links", "ext-formof"]);
  const parts: string[] = [];
  // `div` is in the list because a source that wraps nothing leaves its definition loose inside
  // one; a wrapper contributes nothing anyway, since only a block's own words are taken.
  for (const node of body.body.querySelectorAll("li, p, div")) {
    if ([...node.classList].some((mark) => ASIDE.has(mark))) continue;
    // This block's own words: a clone with the nested blocks taken out, so a definition and the
    // translation beneath it are two parts rather than one run-on, and neither is counted twice.
    const own = node.cloneNode(true) as Element;
    own.querySelectorAll("li, p, div, ol, ul, details").forEach((nested) => nested.remove());
    const line = (own.textContent ?? "").replace(/\s+/g, " ").trim();
    if (line && !parts.includes(line)) parts.push(line);
  }
  return clamp(parts.length ? parts.join("; ") : (body.body.textContent ?? ""));
}

/**
 * How many external rows a search shows.
 *
 * The cap is not tidiness. Every row shown gets its meaning read out of the dictionary that holds
 * it, and a merged search across ten dictionaries produces far more rows than are worth paying that
 * for — `casa` matched thirty-four. Showing what is not described, as a column of em-dashes, is
 * worse than not showing it: it reads as a search that found nothing.
 */
export const EXTERNAL_ROW_LIMIT = 12;

/* ── cleaning what the sources actually contain ─────────────────────────
   Surveyed across all 45 compiled dictionaries rather than guessed at. None of this invents
   anything: it removes markup the source never meant to publish, promotes a label the source
   already wrote to the field it belongs in, and collapses senses that say the same thing twice. A
   source that is genuinely poor stays poor — that is its own business — but it should not also
   look broken. */

/** `[[учебный]] [[пример]]` — FreeDict and TEI carry wiki link syntax straight through. */
const WIKI_LINK = /\[\[([^\]|]*\|)?([^\]]+)\]\]/g;

/**
 * `Química| Compuesto orgánico…` — WikDict writes the domain and the definition into one string.
 *
 * The pipe is only a label when a space follows it and the left side is short and bracket-free.
 * CC-CEDICT's `呂梁市|吕梁市[Lu:3 liang2 Shi4]` is a cross-reference in the middle of a sentence and
 * matches none of that, which is why the test for it is this fussy.
 */
const LABELLED = /^([^|[\]]{1,28})\|[ \t]+(\S[\s\S]*)$/;

function cleanText(value: string): string {
  return accentedPinyinInText(value
    .replace(WIKI_LINK, (_match, _target, label: string) => label)
    .replace(/\s+/g, " ")
    .trim());
}

/**
 * The key two senses are "the same" under.
 *
 * Combining acute is stripped because Russian dictionaries mark stress with it and list the same
 * word twice, once marked and once not. Precomposed accents — Spanish `papá` against `papa` — are
 * untouched by that, which is the whole reason it is `\u0301` and not a diacritic strip.
 */
function senseKey(definition: string): string {
  return definition.normalize("NFC").replace(/\u0301/g, "").toLowerCase();
}

type Sense = DictionaryArticle["senses"][number];

function cleanSenses(senses: Sense[]): Sense[] {
  const kept = new Map<string, Sense>();
  for (const sense of senses) {
    let definition = cleanText(sense.definition ?? "");
    let domain = sense.domain?.trim() || undefined;
    const labelled = LABELLED.exec(definition);
    if (labelled) {
      // The source wrote a domain; it belongs in the field the interface already has for one.
      domain = domain ?? cleanText(labelled[1]);
      definition = labelled[2].trim();
    }
    // `inflection of lastimar:` — wiktextract leaves the colon in front of a tag list that the
    // artifact does not carry, so it dangles.
    definition = definition.replace(/[:,;]\s*$/, "");
    if (!definition) continue;

    const examples = (sense.examples ?? [])
      .map((example) => ({ ...example, text: cleanText(example.text),
                           translation: example.translation ? cleanText(example.translation) : example.translation }))
      .filter((example) => example.text);

    const key = senseKey(definition);
    const existing = kept.get(key);
    if (!existing) {
      kept.set(key, { ...sense, definition, domain, examples: examples.length ? examples : undefined });
      continue;
    }
    // The same sense twice, one copy carrying the examples: `malo` lists "bad (of bad quality)"
    // bare and then again with three sentences. Keeping both loses nothing but reads as a fault.
    const merged = [...(existing.examples ?? []), ...examples];
    const seen = new Set<string>();
    existing.examples = merged.filter((example) => {
      const id = senseKey(example.text);
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    if (!existing.examples.length) delete existing.examples;
    existing.domain = existing.domain ?? domain;
  }
  return [...kept.values()];
}

export function cleanArticle(article: DictionaryArticle): DictionaryArticle {
  const headword = article.headword?.trim() ?? "";
  const reading = article.reading?.trim();
  return {
    ...article,
    headword,
    // JMdict stores the reading even when it is the headword — `ゼーマンこうか` under itself — and
    // printing a word twice under itself says nothing. CC-CEDICT stores `Fang1 shan1 Xian4`,
    // which is the storage format rather than the word (`pinyin.ts`).
    reading: reading && reading !== headword ? accentedPinyin(reading) : undefined,
    senses: cleanSenses(article.senses ?? [])
  };
}

/* ── the article ────────────────────────────────────────────────────────
   One page with a section per source, in resolution order, rather than a tab per dictionary. What
   several dictionaries say about a word is worth reading together — that is most of why anyone
   installs more than one — and jumping between sources is navigation, not a change of view. */

/** An online answer is a narrower `DictionaryArticle`, so one renderer serves both. */
function fromOnline(article: OnlineArticle): DictionaryArticle {
  return {
    headword: article.headword,
    language: article.language,
    ipa: article.ipa,
    posLabel: article.posLabel,
    senses: article.senses.map((sense) => ({
      definition: sense.definition,
      examples: sense.examples?.map((example) => ({
        text: example.text,
        translation: example.translation ?? undefined
      }))
    }))
  };
}

/** A mapped entry leads a restyled one: it is the section that looks most like an Acervo article. */
const tierRank = (result: LookupResult) => (result.entry?.tier === "html" ? 1 : 0);

export function externalEntryOf(word: string, results: LookupResult[]): ExternalEntry {
  const sections: ExternalSection[] = results
    .slice()
    .sort((left, right) => ORIGIN_ORDER[left.origin] - ORIGIN_ORDER[right.origin]
      || tierRank(left) - tierRank(right)
      || left.name.localeCompare(right.name))
    .map((result) => ({
      dictionaryId: result.dictionaryId,
      name: result.name,
      origin: result.origin,
      attribution: result.attribution,
      licence: result.licence,
      sourceLang: result.sourceLang,
      tier: result.entry?.tier ?? "fields",
      articles: (result.articles
        ? result.articles.map(fromOnline)
        : result.entry?.articles ?? []).map(cleanArticle),
      html: result.entry?.tier === "html"
        ? normaliseDictionaryHtml(result.entry.html ?? "", result.entry.word)
        : ""
    }));

  // The masthead takes the first source that knows each fact. Every section still shows its own,
  // so nothing is hidden by the choice — it only decides what is said once, at the top.
  const articles = sections.flatMap((section) => section.articles);
  const firstOf = (pick: (article: DictionaryArticle) => string | undefined): string | null =>
    articles.map(pick).find((value) => value && value.trim())?.trim() ?? null;

  // An `html` section carries no fields at all, so without the catalogue's answer the masthead of
  // a WikDict-only entry could not even say which language the word is in.
  const declared = sections.map((section) => section.sourceLang)
    .find((code) => code && code !== "*");
  return {
    word,
    language: firstOf((article) => article.language) ?? declared ?? null,
    reading: firstOf((article) => article.reading),
    ipa: firstOf((article) => article.ipa),
    posLabel: firstOf((article) => article.posLabel ?? article.pos),
    gender: firstOf((article) => genderOf(article) ?? undefined),
    sections
  };
}

/**
 * The entry as plain text, for grounding a generated article on what the reader actually saw.
 *
 * Deliberately built from the *rendered* model rather than the raw payloads: what goes to the model
 * should be what is on screen, not a second, richer thing the reader never agreed to.
 */
export function referenceTextOf(entry: ExternalEntry): string {
  const lines: string[] = [];
  for (const section of entry.sections) {
    lines.push(`## ${section.name}`);
    for (const article of section.articles) {
      const heading = [article.headword, article.reading, article.ipa,
                       article.posLabel ?? article.pos, genderOf(article)].filter(Boolean).join(" · ");
      if (heading) lines.push(heading);
      article.senses.forEach((sense, index) => {
        lines.push(`${index + 1}. ${sense.definition}${sense.domain ? ` (${sense.domain})` : ""}`);
        for (const example of sense.examples ?? []) {
          lines.push(`   - ${example.text}${example.translation ? ` — ${example.translation}` : ""}`);
        }
      });
    }
    if (section.html) {
      const body = new DOMParser().parseFromString(`<body>${section.html}</body>`, "text/html");
      for (const node of body.body.querySelectorAll("li, p, div, tr, summary, br")) {
        node.parentNode?.insertBefore(body.createTextNode("\n"), node);
      }
      lines.push(...(body.body.textContent ?? "").split("\n")
        .map((line) => line.replace(/\s+/g, " ").trim()).filter(Boolean));
    }
  }
  return lines.join("\n");
}
