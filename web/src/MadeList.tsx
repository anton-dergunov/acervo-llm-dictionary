/**
 * What the Loops and the Stories lists share: their head, drawn as the word list's is — the title and
 * a count on the left, the orders on the right over the rule — and the line that says which of a
 * row's words a search matched.
 *
 * Make is not in the head. While one of these surfaces is open the top bar's Add makes what it holds,
 * as the top bar's search searches it (`App.tsx`), so the head has room for the orders.
 */

import { useMemo, useState } from "react";
import type { VocabularyGraph } from "./domain";
import { madeSortFor, rememberMadeSort } from "./editorPreferences";
import { useRarity } from "./rarity";
import { MADE_SORTS, madeLoops, madeStories, type MadeKind, type MadeList, type MadeSort, type MadeWord } from "./selectors";
import type { Loop, Story } from "./domain";

const LABELS: Record<MadeSort, string> = { recent: "Recent", hard: "Hardest", rare: "Rarest" };

function storedSort(kind: MadeKind): MadeSort {
  const stored = madeSortFor(kind);
  return MADE_SORTS.find((sort) => sort === stored) ?? "recent";
}

export interface MadeOrder<T> {
  list: MadeList<T>;
  sort: MadeSort;
  setSort(sort: MadeSort): void;
  /** Said under the orders when the one chosen has nothing to go by, rather than a list that looks unsorted. */
  note: string;
}

/** A made list in the order chosen, remembered per list on this device, and filtered by the surface's search. */
export function useMadeList(graph: VocabularyGraph, kind: "loop", language: string, query: string): MadeOrder<Loop>;
export function useMadeList(graph: VocabularyGraph, kind: "story", language: string, query: string): MadeOrder<Story>;
export function useMadeList(graph: VocabularyGraph, kind: MadeKind, language: string, query: string): MadeOrder<Loop | Story> {
  const [sort, setSortState] = useState<MadeSort>(() => storedSort(kind));
  const rarity = useRarity(language, sort === "rare");
  const zipf = rarity.state === "ready" ? rarity.zipf : null;
  const list = useMemo(() => {
    const made = { language, query, sort, rarity: zipf };
    return kind === "loop" ? madeLoops(graph, made) : madeStories(graph, made);
  }, [graph, kind, language, query, sort, zipf]);
  const reviewed = useMemo(() => graph.studyStates.some((state) => !state.deleted && state.reps > 0), [graph]);
  const note = sort === "hard" && !reviewed ? "Hardest needs Anki’s review history, and none has come back yet."
    : sort === "rare" && rarity.state === "refused" ? rarity.why
    : "";
  const setSort = (next: MadeSort) => { setSortState(next); rememberMadeSort(kind, next); };
  return { list, sort, setSort, note };
}

export function MadeHead({ kind, icon, title, count, archived = 0, languageName, query, order }: {
  kind: MadeKind;
  icon: string;
  title: string;
  /** How many rows are shown. */
  count: number;
  archived?: number;
  languageName: string;
  query: string;
  order: Pick<MadeOrder<unknown>, "sort" | "setSort" | "note">;
}) {
  const trimmed = query.trim();
  const noun = kind === "loop" ? (count === 1 ? "loop" : "loops") : (count === 1 ? "story" : "stories");
  const sub = trimmed ? `${count} ${noun} with “${trimmed}”`
    : `${count} in ${languageName}${archived ? ` · ${archived} archived` : ""}`;
  return <>
    <div className="list-head made-head">
      <div>
        <h1><span className="ic" aria-hidden="true">{icon}</span>{title}</h1>
        <p className="label sub">{sub}</p>
      </div>
      <div className="sortbar">
        {MADE_SORTS.map((sort) =>
          <button key={sort} className={`sort-btn ${order.sort === sort ? "on" : ""}`} onClick={() => order.setSort(sort)}>{LABELS[sort]}</button>)}
      </div>
    </div>
    {order.note && <p className="made-note">{order.note}</p>}
  </>;
}

/** The letters a search matched, marked by a background and nothing else, so nothing moves. */
function Marked({ text, query }: { text: string; query: string }) {
  const at = text.toLowerCase().indexOf(query);
  if (!query || at < 0) return <>{text}</>;
  return <>{text.slice(0, at)}<mark>{text.slice(at, at + query.length)}</mark>{text.slice(at + query.length)}</>;
}

/** Which of a row's words matched: the word as it was used and what it means, three at most. */
export function MatchLine({ words, query, language }: { words: readonly MadeWord[] | undefined; query: string; language: string }) {
  if (!words?.length) return null;
  const search = query.trim().toLowerCase();
  return <span className="made-match">
    {words.slice(0, 3).map((word, index) => <span key={`${word.lexemeId}-${index}`} className="made-hit">
      <span lang={language}><Marked text={word.source} query={search} /></span>
      {word.target && <> · <Marked text={word.target} query={search} /></>}
    </span>)}
    {words.length > 3 && <span className="made-hit more">+{words.length - 3}</span>}
  </span>;
}
