/**
 * Presentation for the languages a replica happens to contain.
 *
 * Configuration now lives in the owner's `vocabularies` records
 * (`docs/architecture/data-model.md`), so this table is only the *defaults* a record falls back on:
 * the flag and name to offer when someone adds a language, and the gloss languages to assume for a
 * lexeme whose language has no record at all. Tags absent from both fall back to the platform's own
 * display names, so nothing renders as a bare tag.
 */

import type { Vocabulary } from "./domain";

export interface LanguagePresentation {
  code: string;
  flag: string;
  name: string;
  glossLangs: string[];
}

const TABLE: Record<string, Omit<LanguagePresentation, "code">> = {
  es: { flag: "🇪🇸", name: "Spanish", glossLangs: ["en"] },
  en: { flag: "🇬🇧", name: "English", glossLangs: ["ru"] },
  ru: { flag: "🇷🇺", name: "Russian", glossLangs: ["en"] },
  "zh-Hans": { flag: "🇨🇳", name: "Chinese (Simplified)", glossLangs: ["ru", "en"] },
  "zh-Hant": { flag: "🇹🇼", name: "Chinese (Traditional)", glossLangs: ["ru", "en"] }
};

function displayName(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

export function languageOf(code: string): LanguagePresentation {
  const known = TABLE[code];
  if (known) return { code, ...known };
  return { code, flag: "🏳️", name: displayName(code), glossLangs: [] };
}

/** What a configured vocabulary looks like in the switcher: its own labels, defaults behind them. */
export function presentationOf(vocabulary: Vocabulary): LanguagePresentation {
  const fallback = languageOf(vocabulary.language);
  return {
    code: vocabulary.language,
    flag: vocabulary.flag ?? fallback.flag,
    name: vocabulary.displayName ?? fallback.name,
    glossLangs: vocabulary.glossLangs
  };
}

/**
 * Which languages to reach for when reducing a sense to one line. The owner's own preference wins;
 * the table is what answers for a lexeme in a language they have since removed.
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

/* ── accents ─────────────────────────────────────────────────────────── */

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
 * The accents a vocabulary may choose, as `{value, label}`: the regions the server derived from CLDR
 * for the language, most speakers first, then any a voice is `declared` for, then the one already
 * chosen — so a choice never disappears from its own list.
 */
export function accentOptions(choices: readonly string[], declared: Iterable<string> = [], current?: string | null): { value: string; label: string }[] {
  const regions = [...choices];
  for (const region of [...[...declared].map(regionOf), current ?? null]) {
    if (region && !regions.includes(region)) regions.push(region);
  }
  return regions.map((region) => ({ value: region, label: regionName(region) }));
}
