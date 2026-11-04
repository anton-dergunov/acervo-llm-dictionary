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

function known(tag: string): boolean {
  try {
    return Boolean(new Intl.DisplayNames(["en"], { type: "language", fallback: "none" }).of(tag.split("-")[0]));
  } catch {
    return false;
  }
}

/** How well `entry` answers `query`, lower first; null for not at all. */
function rank(entry: LanguageEntry, query: string): number | null {
  if (!query) return 0;
  if (folded(entry.tag) === query) return 0;
  const names = [folded(entry.name), folded(entry.autonym)];
  if (names.some((name) => name.startsWith(query))) return 1;
  // A word inside the name: "trad" for "Chinese (Traditional)", "chin" for "Simplified Chinese".
  if (names.some((name) => name.split(/[\s()\-,]+/).some((word) => word.startsWith(query)))) return 2;
  if (names.some((name) => name.includes(query))) return 3;
  return null;
}

/** The languages in the list that answer `query`, best first, and a typed tag the list lacks. */
export function search(languages: readonly LanguageEntry[], query: string): LanguageEntry[] {
  const wanted = folded(query.trim());
  const found = languages
    .map((entry, order) => ({ entry, order, score: rank(entry, wanted) }))
    .filter((one): one is { entry: LanguageEntry; order: number; score: number } => one.score !== null)
    .sort((a, b) => a.score - b.score || a.order - b.order)
    .map((one) => one.entry);
  const typed = query.trim();
  if (LANGUAGE_TAG.test(typed) && !languages.some((entry) => entry.tag.toLowerCase() === typed.toLowerCase())) {
    // Only a language the platform can name: a tag that merely looks like one is nobody's language.
    if (known(typed)) found.unshift({ tag: typed, name: languageName(typed), autonym: "", region: mainRegion(typed), varieties: [] });
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
