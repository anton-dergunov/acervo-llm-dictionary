/**
 * Presentation for the languages a replica happens to contain: a name and a flag for any tag.
 *
 * Configuration lives in the owner's `vocabularies` records (`docs/architecture/data-model.md`).
 * What is derived here is derived from the platform's own locale data, so it works offline and
 * nothing renders as a bare tag: a name from `Intl.DisplayNames`, and a flag from the vocabulary's
 * variety or, without one, from the region the language is most likely spoken in.
 */

import type { Vocabulary } from "./domain";

export interface LanguagePresentation {
  code: string;
  flag: string;
  name: string;
  glossLangs: string[];
}

/**
 * The gloss languages to assume for a lexeme whose language has no vocabulary record at all — one
 * the owner has since removed. A new vocabulary takes its defaults from the owner's others instead.
 */
const GLOSS_DEFAULTS: Record<string, string[]> = {
  es: ["en"], en: ["ru"], ru: ["en"], "zh-Hans": ["ru", "en"], "zh-Hant": ["ru", "en"]
};

/** A language's name in English: "Spanish", "Chinese (Traditional)". The tag where none is known. */
export function languageName(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "language", languageDisplay: "standard" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** The region a language is most likely spoken in, from the platform's likely subtags: `es` → `ES`. */
export function mainRegion(code: string): string | null {
  try {
    return new Intl.Locale(code).maximize().region ?? null;
  } catch {
    return null;
  }
}

/** A region's flag: `AR` → 🇦🇷. A wider region (`419`, Latin America) has none and gets a globe. */
export function flagOf(region: string | null | undefined): string {
  if (!region) return "🌐";
  if (!/^[A-Za-z]{2}$/.test(region)) return "🌐";
  return String.fromCodePoint(...[...region.toUpperCase()].map((letter) => 0x1F1E6 + letter.charCodeAt(0) - 65));
}

/** The flag a vocabulary shows: the owner's own, else its variety's, else its language's main region's. */
export function flagFor(vocabulary: Pick<Vocabulary, "language" | "flag" | "region">): string {
  return vocabulary.flag ?? automaticFlag(vocabulary.language, vocabulary.region);
}

/** The flag that follows a variety, before the owner pastes their own over it. */
export function automaticFlag(language: string, region: string | null): string {
  return flagOf(region ?? mainRegion(language));
}

export function languageOf(code: string): LanguagePresentation {
  return { code, flag: flagOf(mainRegion(code)), name: languageName(code), glossLangs: GLOSS_DEFAULTS[code] ?? [] };
}

/** What a configured vocabulary looks like in the switcher: its own labels, defaults behind them. */
export function presentationOf(vocabulary: Vocabulary): LanguagePresentation {
  return {
    code: vocabulary.language,
    flag: flagFor(vocabulary),
    name: vocabulary.displayName ?? languageName(vocabulary.language),
    glossLangs: vocabulary.glossLangs
  };
}

/**
 * Which languages to reach for when reducing a sense to one line. The owner's own preference wins;
 * the defaults answer for a lexeme in a language they have since removed.
 */
export function glossLanguagesFor(code: string, vocabularies: Vocabulary[] = []): string[] {
  const configured = vocabularies.find((entry) => !entry.deleted && entry.language === code);
  if (configured) return configured.glossLangs;
  return languageOf(code).glossLangs;
}

/** The language usage notes are written in: the owner's choice, else the first gloss language. */
export function notesLanguageFor(code: string, vocabularies: Vocabulary[] = []): string {
  const configured = vocabularies.find((entry) => !entry.deleted && entry.language === code);
  return configured?.notesLang ?? glossLanguagesFor(code, vocabularies)[0] ?? code;
}

/** The definition language for a new sense: the owner's choice, else the target language itself. */
export function definitionLanguageFor(code: string, vocabularies: Vocabulary[] = []): string {
  return vocabularies.find((entry) => !entry.deleted && entry.language === code)?.definitionLang ?? code;
}

/* ── varieties ───────────────────────────────────────────────────────── */

/** A region subtag of a locale: `AR` of `es-AR`, `CN` of `zh-Hans-CN`. Null for a bare language. */
export function regionOf(locale: string | null | undefined): string | null {
  const found = (locale ?? "").split("-").slice(1).find((part) => /^([A-Za-z]{2}|\d{3})$/.test(part));
  return found ? found.toUpperCase() : null;
}

/** What a region is called: "Argentina", "Latin America". The code where the platform has no name. */
export function regionName(region: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(region) ?? region;
  } catch {
    return region;
  }
}

/**
 * The varieties a vocabulary may choose, as `{value, label}` with each one's flag: the regions the
 * server derived from CLDR for the language, most speakers first, then any a voice is `declared`
 * for, then the one already chosen — so a choice never disappears from its own list.
 */
export function varietyOptions(choices: readonly string[], declared: Iterable<string> = [], current?: string | null): { value: string; label: string }[] {
  const regions = [...choices];
  for (const region of [...[...declared].map(regionOf), current ?? null]) {
    if (region && !regions.includes(region)) regions.push(region);
  }
  return regions.map((region) => ({ value: region, label: `${flagOf(region)} ${regionName(region)}` }));
}

/**
 * Whether a lexeme's reading is Hanyu Pinyin: Mandarin, written in either script.
 *
 * The same prefix test that makes a reading required for Chinese, less Cantonese, whose reading is
 * Jyutping with six tones and must never be given Mandarin's marks. A Cantonese reading under a
 * plain `zh` tag is safe anyway: it does not parse as Pinyin, so it is shown as written.
 */
export function isMandarin(language: string): boolean {
  const lower = language.toLowerCase();
  if (lower.startsWith("cmn")) return true;
  return lower.startsWith("zh") && !/^zh-yue\b/.test(lower);
}
