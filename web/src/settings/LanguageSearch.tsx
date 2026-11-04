/**
 * Finding a language by its name, in English or in itself, with its flag: what Settings ▸
 * Vocabularies offers wherever a language is chosen — a new vocabulary, and the languages one is
 * defined, translated and annotated in.
 *
 * The list is CLDR's, from the server (`GET /languages`), most speakers first. A tag it does not list
 * is still offered as typed, named by the platform, so a language too small for the list can be kept.
 */

import { useMemo, useState } from "react";
import type { LanguageEntry } from "../api";
import { flagOf, languageName, mainRegion } from "../languages";
import { SETTINGS, useServerSetting } from "./cache";
import { Group, Notice, Placeholder } from "./kit";

const LANGUAGE_TAG = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;
/** Enough to find a language by scrolling once the first letters are typed. */
const SHOWN = 40;

function folded(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/**
 * A typed tag in its canonical form — `eng` → `en`, `ZHO` → `zh` — or null when it is not one the
 * platform can name. Three-letter codes are tags too, and the list stores the two-letter ones, so
 * without this "eng" would find English twice: once from the list, once as the tag typed.
 */
function typedTag(text: string): string | null {
  if (!LANGUAGE_TAG.test(text)) return null;
  try {
    const tag = Intl.getCanonicalLocales(text)[0];
    const named = new Intl.DisplayNames(["en"], { type: "language", fallback: "none" }).of(tag.split("-")[0]);
    return named ? tag : null;
  } catch {
    return null;
  }
}

const base = (tag: string) => tag.split("-")[0].toLowerCase();

/** How well `entry` answers `query`, lower first; null for not at all. `tag` is the query as a tag. */
function rank(entry: LanguageEntry, query: string, tag: string | null): number | null {
  if (!query) return 0;
  // The tag typed, in any spelling of it: `eng` finds English, `zho` both Chinese scripts.
  if (tag && (entry.tag.toLowerCase() === tag.toLowerCase() || base(entry.tag) === base(tag))) return 0;
  const names = [folded(entry.name), folded(entry.autonym)];
  if (names.some((name) => name.startsWith(query))) return 1;
  // A word inside the name: "trad" for "Chinese (Traditional)". Only where a word begins, so "eng"
  // does not find Vietnamese through "Tiếng".
  if (names.some((name) => name.split(/[\s()\-,]+/).some((word) => word.startsWith(query)))) return 2;
  return null;
}

/** The languages in the list that answer `query`, best first, and a typed tag the list lacks. */
export function search(languages: readonly LanguageEntry[], query: string): LanguageEntry[] {
  const wanted = folded(query.trim());
  const tag = typedTag(query.trim());
  const found = languages
    .map((entry, order) => ({ entry, order, score: rank(entry, wanted, tag) }))
    .filter((one): one is { entry: LanguageEntry; order: number; score: number } => one.score !== null)
    .sort((a, b) => a.score - b.score || a.order - b.order)
    .map((one) => one.entry);
  // A language too small for the list, kept by its tag — only when nothing listed is that language.
  if (tag && !languages.some((entry) => base(entry.tag) === base(tag))) {
    found.unshift({ tag, name: languageName(tag), autonym: "", region: mainRegion(tag), varieties: [] });
  }
  return found;
}

export function LanguageSearch({ label, unavailable = {}, onChoose }: {
  /** What the box is for, for a screen reader: "Find a language". */
  label: string;
  /** Languages that cannot be chosen here, each with why: "Already kept". */
  unavailable?: Record<string, string>;
  onChoose(language: LanguageEntry): void;
}) {
  const catalogue = useServerSetting(SETTINGS.languages);
  const [query, setQuery] = useState("");
  const results = useMemo(() => search(catalogue.value?.languages ?? [], query).slice(0, SHOWN),
    [catalogue.value, query]);

  return <>
    <Group>
      <label className="pref-row">
        <input
          className="pref-input" type="search" value={query} placeholder="Search by name, such as Spanish or español"
          aria-label={label} autoComplete="off" spellCheck={false} autoFocus
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
    </Group>
    {!catalogue.value
      ? catalogue.error ? <Notice>{catalogue.error}</Notice> : <Placeholder rows={4} />
      : results.length
        ? <Group>
          {results.map((entry) => {
            const why = unavailable[entry.tag];
            return <button
              key={entry.tag} type="button" className="pref-row pref-language" disabled={Boolean(why)}
              onClick={() => onChoose(entry)}
            >
              <span className="pref-flag" aria-hidden="true">{flagOf(entry.region)}</span>
              <span className="pref-text">
                <span className="pref-label">{entry.name}</span>
                {entry.autonym && entry.autonym !== entry.name && <span className="pref-hint">{entry.autonym}</span>}
              </span>
              {why && <span className="pref-value">{why}</span>}
            </button>;
          })}
        </Group>
        : <Notice>No language is called that. A language tag, such as gsw or es-419, works too.</Notice>}
  </>;
}
