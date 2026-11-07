import { useState } from "react";
import { asideOpen, setAsideOpen } from "./editorPreferences";
import { BookIcon, CaretIcon, CheckIcon, GlobeIcon } from "./icons";
import SwipeRow, { type RowAction } from "./SwipeRow";
import type { ExternalRow } from "./externalEntries";
import type { ListRow, SortKey, TopicSelection } from "./selectors";

const SORTS: [SortKey, string][] = [["recent", "Recent"], ["alpha", "A–Z"], ["hard", "Hardest"]];

function Strength({ row }: { row: ListRow }) {
  return <span className="strength" title={row.strengthLabel}>
    {[1, 2, 3, 4].map((bar) => <i key={bar} className={bar <= row.strength ? "f" : ""} />)}
  </span>;
}

/**
 * What the external section is doing right now.
 *
 * `online` is separate from the rest because it is the one tier that never runs on its own: §9 asks
 * for no prefetching, and a rate limit is not something to spend on a word someone was only passing
 * through on the way to another one.
 */
export interface ExternalSearch {
  rows: ExternalRow[];
  /** How many matched before the list was cut to what could be described. */
  total: number;
  /** Why a tier came back empty, when the reason is something other than "no such word". */
  trouble: string | null;
  /** True while the device and server tiers are still answering. */
  searching: boolean;
  /** Whether anything at all is switched on to search. */
  enabled: boolean;
  /** The server is unreachable, so only what this device holds can answer. */
  offline: boolean;
  online: "off" | "ready" | "searching" | "done";
  onOpen(row: ExternalRow): void;
  onSearchOnline(): void;
}

function sourceLabel(row: ExternalRow): string {
  if (row.sources.length > 2) return `${row.sources.length} sources`;
  return row.sources.map((source) => source.name).join(" · ");
}

/**
 * The external section: everything Acervo can find that is not yours.
 *
 * Below a rule and after every one of your own words, always — the ordering is the product. What is
 * here carries no emoji, no sense count and no strength bars, because it has none of those things:
 * an external row must be unmistakable at a glance, and the surest way to do that is to show only
 * what is true about it.
 */
function ExternalSection({ query, search }: { query: string; search: ExternalSearch }) {
  const { rows, online } = search;
  return <div className="ext-section">
    <div className="list-sep"><span className="label">Other dictionaries</span></div>

    {search.offline && <p className="ext-status">
      Your server is unreachable, so only the dictionaries stored on this device are being searched.
    </p>}

    <div className="rows">
      {rows.map((row) => <button
        key={`${row.word}:${row.sources[0].dictionaryId}`} className="row ext"
        onClick={() => search.onOpen(row)}
      >
        <span className="plate ext" aria-hidden="true">
          {row.origin === "online" ? <GlobeIcon /> : <BookIcon />}
        </span>
        {/* The source names are repeated as an attribute so a phone can put them under the gloss
            instead of squeezing a second column onto a screen that has no room for one. */}
        <span data-sources={sourceLabel(row)}>
          <span className="word">{row.word}</span>
          <span className="gloss">{row.gloss || "—"}</span>
        </span>
        <span className="meta"><span className="src">{sourceLabel(row)}</span></span>
      </button>)}
    </div>

    {search.total > rows.length && <p className="ext-status">
      The closest {rows.length} of {search.total}. Type more of the word to narrow them.
    </p>}
    {search.searching && <p className="ext-status">Looking through your dictionaries…</p>}
    {/* A reason beats an absence. Switched off, unreachable and genuinely-not-there are three
        different answers, and only the last one is about the word. */}
    {search.trouble && <p className="ext-status trouble" role="status">{search.trouble}</p>}
    {!search.searching && !search.trouble && !rows.length && online !== "searching"
      && <p className="ext-status">No dictionary here holds “{query}”.</p>}

    {online === "ready" && <button className="ext-online" onClick={search.onSearchOnline}>
      <GlobeIcon /><span>Press ⏎ to look “{query}” up online</span>
    </button>}
    {online === "searching" && <p className="ext-status" role="status">Asking the online dictionaries…</p>}
  </div>;
}

export default function LexemeList({
  rows, aside = [], languageName, topic, topicLabel, topicIcon, query, sort, onSort, onOpen, onFileAll, external, working,
  selected, onToggleSelected, onSetAside, onDelete
}: {
  rows: ListRow[];
  /** The words set aside, drawn faded under a folded rule after the rest. */
  aside?: ListRow[];
  languageName: string;
  topic: TopicSelection;
  topicLabel: string;
  topicIcon: string;
  query: string;
  sort: SortKey;
  onSort(sort: SortKey): void;
  onOpen(id: string): void;
  /** Empties the Inbox into the words' own topics. Only the Inbox has one. */
  onFileAll?(ids: string[]): void;
  /** Absent when nothing is being searched — an empty topic list has no external half. */
  external?: ExternalSearch;
  /** Whether the server is still filling a word in, so it can be found without opening it. */
  working?: (id: string) => boolean;
  /** Whether a word is in the selection, which its row then wears as a mark. */
  selected?: (id: string) => boolean;
  /* A word's row actions, by right-click or by swipe (`SwipeRow`). Delete asks nothing, exactly as
     the article's Delete asks nothing: it is a tombstone. */
  onToggleSelected?(id: string): void;
  onSetAside?(id: string, aside: boolean): void;
  onDelete?(id: string): void;
}) {
  const [open, setOpen] = useState(asideOpen);
  const trimmed = query.trim();
  let title = topicLabel;
  let icon = topicIcon;
  let sub: string;
  if (trimmed) {
    title = "Search";
    icon = "🔍";
    const found = rows.length + aside.length;
    sub = `${found} match${found === 1 ? "" : "es"} for “${trimmed}” in ${languageName}`;
  } else if (topic === "inbox") {
    sub = "Captured, processed, waiting for your review";
  } else if (topic === "all") {
    sub = `${rows.length} in ${languageName}`;
  } else {
    sub = `${rows.length} word${rows.length === 1 ? "" : "s"} in ${languageName}`;
  }

  const showExternal = Boolean(trimmed && external?.enabled);
  // Only the Inbox tab itself, never a search that happens to turn up unreviewed words: those rows
  // are an answer to a question, not a pile to be emptied.
  const fileable = !trimmed && topic === "inbox" ? rows : [];

  const shown = open || Boolean(trimmed);

  function wordRow(row: ListRow) {
    const on = selected?.(row.id) ?? false;
    const setAside = row.status === "aside";
    /* The mark is the plate's ring and a badge on its corner, drawn so nothing in the row moves —
       not the word, not the gloss, not the row's height. A word set aside is faded the same way. */
    const line = <button
      key={row.id}
      className={`row${row.status === "inbox" ? " inbox" : ""}${setAside ? " aside" : ""}${on ? " picked" : ""}`}
      onClick={() => onOpen(row.id)}
    >
      <span className="plate">
        {row.emoji || "📄"}
        {on && <span className="pick-badge" role="img" aria-label="Selected"><CheckIcon /></span>}
      </span>
      <span>
        <span className="word">{row.headword}{row.reading && <span className="rdg">{row.reading}</span>}</span>
        <span className="gloss">{row.shortGloss}</span>
      </span>
      <span className="meta">
        {working?.(row.id) && <span className="working-mark" role="img" aria-label="Still filling in" title="Still filling in" />}
        {row.senseCount > 1 && <span className="senses">{row.senseCount} senses</span>}
        {row.status === "inbox" ? <span className="prov">unreviewed</span> : <Strength row={row} />}
      </span>
    </button>;
    const actions: RowAction[] = [
      ...(onToggleSelected ? [{
        label: on ? "Unselect" : "Select", menuLabel: on ? "Remove from selection" : "Add to selection",
        tone: "pick" as const, run: () => onToggleSelected(row.id)
      }] : []),
      ...(onSetAside ? [setAside
        ? { label: "Bring back", menuLabel: "Bring it back", run: () => onSetAside(row.id, false) }
        : { label: "Set aside", menuLabel: "Set it aside", run: () => onSetAside(row.id, true) }] : []),
      ...(onDelete ? [{ label: "Delete", menuLabel: "Delete this word", tone: "danger" as const, run: () => onDelete(row.id) }] : [])
    ];
    if (!actions.length) return line;
    return <SwipeRow key={row.id} actions={actions}>{line}</SwipeRow>;
  }

  return <>
    <div className="list-head">
      <div>
        <h1><span className="ic">{icon}</span>{title}</h1>
        <p className="label sub">{sub}</p>
      </div>
      <div className="sortbar">
        {/* The count is in the label rather than behind a confirmation: a bulk press should be an
            informed one, and a dialog over a reversible field would be heavier than deleting a word,
            which asks nothing. */}
        {fileable.length > 0 && onFileAll
          && <button className="sort-btn" onClick={() => onFileAll(fileable.map((row) => row.id))}>
            File all {fileable.length}
          </button>}
        {SORTS.map(([key, text]) =>
          <button key={key} className={`sort-btn ${sort === key ? "on" : ""}`} onClick={() => onSort(key)}>{text}</button>)}
      </div>
    </div>
    <div className="rows">
      {rows.length ? rows.map(wordRow)
      // With a search running, the dictionaries below are the answer, so this shrinks to a line
      // saying which question it is answering rather than taking the whole page to say "nothing".
      : aside.length ? null
      : showExternal ? <p className="ext-status none-yours">No words of yours match “{trimmed}”.</p>
      : <p className="empty">Nothing here yet.</p>}
    </div>
    {/* Below your words and above everyone else's: they are still yours. A search draws them open,
        since a search is a question and a folded section would hide part of its answer. */}
    {aside.length > 0 && <div className="aside-section">
      {trimmed ? <div className="list-sep"><span className="label">Set aside · {aside.length}</span></div>
        : <button type="button" className="list-sep fold" aria-expanded={open}
            onClick={() => { setOpen(!open); setAsideOpen(!open); }}>
            <span className="caret"><CaretIcon /></span>
            <span className="label">Set aside · {aside.length}</span>
          </button>}
      {shown && <div className="rows">{aside.map(wordRow)}</div>}
    </div>}
    {showExternal && external && <ExternalSection query={trimmed} search={external} />}
  </>;
}
