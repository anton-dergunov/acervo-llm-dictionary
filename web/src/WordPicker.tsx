/**
 * Which words a make dialog sends, shown before it sends them.
 *
 * **What is drawn is what is sent.** The words are chips, and the button counts exactly them. Each
 * chip carries its ×, because a chip that is quietly a button goes unnoticed: removing a word puts
 * the next one in the order in its place, so the count stays what was asked for. **Draw again**, a
 * labelled button under the chips, passes over every word showing. Turned-down words come back only
 * once nothing else in scope is left.
 *
 * **Words not used yet come first** (`drawOrder` in `selectors.ts`), and the order chosen here
 * decides among them: at random, the hardest by Anki, the rarest in the language, or the newest.
 * The selection, when there is one, is a fifth choice, sent as chosen less what the kind cannot use.
 * Hard needs Anki's review history and says so until there is some; Rare asks the server once a
 * session, and a language with no frequency list is said by name.
 *
 * The order and the count are remembered per kind on this device (`editorPreferences.ts`); the
 * dialog opens on the selection when it was opened from the selection bar.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AcervoApiError, backendSession } from "./api";
import type { Lexeme, VocabularyGraph } from "./domain";
import { lastDraw, rememberDraw } from "./editorPreferences";
import { CloseIcon, GemIcon, PeakIcon, SelectIcon, ShuffleIcon, SparkleIcon, SyncIcon } from "./icons";
import { languageOf } from "./languages";
import {
  chosenFor, drawOrder, drawWords, hasReviewState, usageCounts,
  type ChosenWord, type DrawOrder, type ListQuery, type MadeKind, type SelectedWord
} from "./selectors";

export type WordSource = "selection" | "scope";
type Choice = DrawOrder | "selection";

const ORDERS: { id: DrawOrder; label: string; icon: () => ReactNode }[] = [
  { id: "random", label: "Random", icon: ShuffleIcon },
  { id: "hard", label: "Hard", icon: PeakIcon },
  { id: "rare", label: "Rare", icon: GemIcon },
  { id: "newest", label: "Newest", icon: SparkleIcon }
];

/** How many chips are drawn before the rest fold into "+N". */
const SHOWN = 12;

export function wordsCount(count: number): string {
  return `${count} word${count === 1 ? "" : "s"}`;
}

/* Rarity is a figure about the language, so it is asked for once a session per language. */
const rarities = new Map<string, Promise<Record<string, number>>>();

export function resetRarityForTests(): void { rarities.clear(); }

type Rarity = { state: "idle" | "asking" } | { state: "ready"; zipf: Record<string, number> } | { state: "refused"; why: string };

function useRarity(language: string, wanted: boolean): Rarity {
  const [rarity, setRarity] = useState<Rarity>({ state: "idle" });
  useEffect(() => {
    if (!wanted) return;
    let live = true;
    if (!rarities.has(language)) {
      const asked = backendSession.wordRarity(language).then((answer) => answer.zipf);
      asked.catch(() => rarities.delete(language));
      rarities.set(language, asked);
    }
    setRarity((now) => (now.state === "ready" ? now : { state: "asking" }));
    rarities.get(language)!.then(
      (zipf) => { if (live) setRarity({ state: "ready", zipf }); },
      (error: unknown) => {
        if (live) setRarity({ state: "refused", why: error instanceof AcervoApiError ? error.message : "How rare each word is could not be read." });
      }
    );
    return () => { live = false; };
  }, [language, wanted]);
  return rarity;
}

export interface WordDraw {
  source: WordSource;
  choice: Choice;
  choose(choice: Choice): void;
  /** Words from the scope, drawn; or the selection, each used or left out with a reason. */
  chips: ChosenWord[];
  /** Exactly what will be sent. */
  ids: string[];
  count: number;
  setCount(count: number): void;
  least: number;
  most: number;
  /** How many words in scope this kind could use. */
  pool: number;
  /** How many of them are in no loop (or story) yet. */
  unused: number;
  swap(id: string): void;
  redraw(): void;
  canHard: boolean;
  rarity: Rarity;
  selected: number;
  /** Remember the order and count for next time; called when something is made. */
  remember(): void;
}

export function useWordDraw({ graph, query, kind, candidatesOf, eligible, why, max, least, initial, selection, from }: {
  graph: VocabularyGraph;
  query: ListQuery;
  kind: MadeKind;
  /** The words in scope this kind can use. */
  candidatesOf(graph: VocabularyGraph, query: ListQuery): Lexeme[];
  eligible(graph: VocabularyGraph, lexeme: Lexeme): boolean;
  /** Why a selected word this kind cannot use is left out. */
  why: string;
  max: number;
  least: number;
  initial: number;
  selection: SelectedWord[];
  from: WordSource;
}): WordDraw {
  const remembered = useMemo(() => lastDraw(kind), [kind]);
  const [source, setSource] = useState<WordSource>(selection.length && from === "selection" ? "selection" : "scope");
  const [order, setOrder] = useState<DrawOrder>(
    ORDERS.some((one) => one.id === remembered.order) ? remembered.order as DrawOrder : "random");
  const [wanted, setWanted] = useState(remembered.count ?? initial);
  const [seed] = useState(() => Date.now());
  const [passed, setPassed] = useState<ReadonlySet<string>>(new Set());

  const candidates = useMemo(() => candidatesOf(graph, query), [candidatesOf, graph, query]);
  const usage = useMemo(() => usageCounts(graph, kind), [graph, kind]);
  const canHard = useMemo(() => hasReviewState(graph, candidates), [graph, candidates]);
  const rarity = useRarity(query.language, order === "rare");
  const ordered = useMemo(() => drawOrder(graph, candidates, {
    order: order === "hard" && !canHard ? "random" : order, usage, seed,
    rarity: rarity.state === "ready" ? rarity.zipf : null
  }), [graph, candidates, order, canHard, usage, seed, rarity]);

  const most = Math.max(Math.min(max, candidates.length), Math.min(least, candidates.length));
  const lowest = Math.min(least, most);
  const count = Math.min(Math.max(wanted, lowest), most);
  const drawn = useMemo(() => drawWords(ordered, count, passed), [ordered, count, passed]);
  const chosen = chosenFor(graph, selection, { eligible, why, max, noun: kind });

  const fromSelection = source === "selection" && selection.length > 0;
  const chips: ChosenWord[] = fromSelection ? chosen : drawn.map((lexeme) => ({
    id: lexeme.id, headword: lexeme.headword, emoji: lexeme.emoji, shortGloss: "", lexeme, skip: ""
  }));
  const ids = chips.filter((chip) => !chip.skip).map((chip) => chip.id);

  return {
    source: fromSelection ? "selection" : "scope",
    choice: fromSelection ? "selection" : order,
    choose(next) {
      if (next === "selection") { setSource("selection"); return; }
      setSource("scope");
      setOrder(next);
      setPassed(new Set());
    },
    chips, ids, count, least: lowest, most,
    setCount(next) { setWanted(next); },
    pool: candidates.length,
    unused: candidates.filter((lexeme) => !usage.get(lexeme.id)).length,
    swap(id) { setPassed(new Set([...passed, id])); },
    redraw() {
      const all = new Set([...passed, ...drawn.map((lexeme) => lexeme.id)]);
      // Once every word has been passed over, start again rather than offering the same ones.
      setPassed(all.size >= candidates.length ? new Set(drawn.map((lexeme) => lexeme.id)) : all);
    },
    canHard, rarity, selected: selection.length,
    remember() { rememberDraw(kind, { order, count: wanted }); }
  };
}

/** The line under the count: where the words come from, and how much a loop of them lasts. */
function poolNote(draw: WordDraw, kind: MadeKind, choice: Choice): string {
  if (choice === "hard") return `Hardest first, from ${draw.pool}`;
  if (draw.unused >= draw.count) return `From ${draw.unused} not in a ${kind} yet`;
  if (draw.unused > 0) return `${draw.unused} not in a ${kind} yet, then the least used`;
  return `Every word has been in a ${kind}: the least used first`;
}

export function WordPicker({ draw, kind, language, counter, secondsPerWord }: {
  draw: WordDraw;
  kind: MadeKind;
  language: string;
  /** A slider for a loop's dozens; segments for a story's handful. */
  counter: "slider" | "segments";
  /** Seconds a word takes in this kind of loop, when there is anything to go on. */
  secondsPerWord?: number | null;
}) {
  const [open, setOpen] = useState(false);
  const fromSelection = draw.source === "selection";
  const caption = draw.choice === "hard"
    ? draw.canHard ? "Words Anki says you find hardest." : "Needs your review history from Anki, which has none yet."
    : draw.choice === "rare"
      ? draw.rarity.state === "refused" ? draw.rarity.why : `Words least common in everyday ${languageOf(language).name}.`
      : null;
  const warn = (draw.choice === "hard" && !draw.canHard) || (draw.choice === "rare" && draw.rarity.state === "refused");
  const shown = open ? draw.chips : draw.chips.slice(0, SHOWN);
  const hidden = draw.chips.length - shown.length;
  const reasons = fromSelection ? [...new Set(draw.chips.filter((chip) => chip.skip).map((chip) => chip.skip))] : [];
  const estimate = secondsPerWord && draw.ids.length ? Math.max(1, Math.round((secondsPerWord * draw.ids.length) / 60)) : null;

  return <div className="word-picker">
    <div className="word-orders" role="radiogroup" aria-label="Which words">
      {ORDERS.map(({ id, label, icon: Icon }) => <button
        key={id} type="button" role="radio" aria-checked={draw.choice === id}
        className={`word-order${draw.choice === id ? " on" : ""}`} onClick={() => draw.choose(id)}
      ><Icon />{label}</button>)}
      {draw.selected > 0 && <button
        type="button" role="radio" aria-checked={fromSelection}
        className={`word-order${fromSelection ? " on" : ""}`} onClick={() => draw.choose("selection")}
      ><SelectIcon on />Selection · {draw.selected}</button>}
    </div>
    {caption && <p className={`word-caption${warn ? " warn" : ""}`}>{caption}</p>}

    {!fromSelection && <div className="word-count">
      {counter === "slider"
        ? <input
          type="range" min={draw.least} max={draw.most} value={draw.count} aria-label="How many words"
          disabled={draw.pool === 0} onChange={(event) => draw.setCount(Number(event.target.value))}
        />
        : <span className="seg word-count-seg" role="radiogroup" aria-label="How many words">
          {Array.from({ length: draw.most - draw.least + 1 }, (_, index) => draw.least + index).map((value) => <button
            key={value} type="button" role="radio" aria-checked={value === draw.count}
            className={value === draw.count ? "on" : ""} onClick={() => draw.setCount(value)}
          >{value}</button>)}
        </span>}
      <output>{wordsCount(draw.count)}{estimate ? <small> · about {estimate} min</small> : null}</output>
    </div>}

    <div className="make-words" aria-live="polite">
      {shown.map((chip) => fromSelection || chip.skip
        ? <span key={chip.id} className={`make-chip${chip.skip ? " skip" : ""}`} lang={language}
          title={chip.skip ? `Left out: ${chip.skip}` : undefined}>
          <span aria-hidden="true">{chip.emoji || "📄"}</span>{chip.headword}
        </span>
        : <button key={chip.id} type="button" className="make-chip" lang={language}
          aria-label={`Remove ${chip.headword}`} title="Remove — the next word takes its place"
          onClick={() => draw.swap(chip.id)}>
          <span aria-hidden="true">{chip.emoji || "📄"}</span>{chip.headword}<span className="make-chip-x"><CloseIcon /></span>
        </button>)}
      {hidden > 0 && <button type="button" className="make-chip more" onClick={() => setOpen(true)}>+{hidden}</button>}
    </div>
    {!fromSelection && draw.pool > 0 && <div className="word-foot">
      <p className="word-note">{poolNote(draw, kind, draw.choice)}</p>
      {draw.pool > draw.count && <button type="button" className="word-redraw" onClick={draw.redraw}>
        <SyncIcon />Draw again
      </button>}
    </div>}
    {!fromSelection && draw.pool === 0 && <p className="word-note warn">No word here can be in a {kind} yet.</p>}
    {reasons.length > 0 && <p className="word-note">
      {reasons.map((reason) => <span key={reason}>
        Left out, {reason}: {draw.chips.filter((chip) => chip.skip === reason).map((chip, index) => <span key={chip.id}>
          {index > 0 && ", "}<i lang={language}>{chip.headword}</i>
        </span>)}.{" "}
      </span>)}
    </p>}
  </div>;
}
