/**
 * Writing a Mandarin word's characters, stroke by stroke (`docs/features/writing.md`).
 *
 * Three ways to practise one word, one character at a time:
 *
 * - **Watch** — the strokes are written in order and direction, numbered, the radical in its own
 *   colour;
 * - **Trace** — over the faint outline, each stroke you draw checked against the next one;
 * - **Write** — no outline, from the reading, the meaning and the sound.
 *
 * What a drawn stroke did is `writing/practice.ts`: only the next stroke in the standard order is
 * accepted, in the direction it is written, and a refusal says why — which stroke that was, or that
 * it went the other way round. Two refusals show the stroke; four write it in. Nothing is stored:
 * this is practice, and a run is forgotten when the sheet closes.
 *
 * The dialog shell is the clip dialog's, and so is where it lives: in the article, which only shows it.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { BackIcon, ForwardIcon, PauseIcon, PlayIcon, RepeatIcon } from "./icons";
import { hanziColumns, ReadingText } from "./Reading";
import { precisionWord } from "./writing/grade";
import {
  attempt, feedback, isDone, markHinted, nextStroke, startRun, strokeStanding, summarize, type Run
} from "./writing/practice";
import { character as characterOf, hanCharacters, type Character } from "./writing/strokeData";
import { strokeStore, type StrokeStore } from "./writing/strokeStore";
import { animationTime, HINT_FADE, WritingPad, type Animated, type InkPoint } from "./writing/WritingPad";

export type WritingMode = "watch" | "trace" | "write";
const MODES: { mode: WritingMode; label: string }[] = [
  { mode: "watch", label: "Watch" }, { mode: "trace", label: "Trace" }, { mode: "write", label: "Write" }
];
const MODE_KEY = "acervo-writing-mode";
/** The pause between one stroke and the next while watching. */
const BETWEEN = 320;
const PEEK = 1400;

/** Which way of practising this device used last: a preference of the screen, not of the vocabulary. */
function rememberedMode(): WritingMode {
  try {
    const stored = localStorage.getItem(MODE_KEY);
    return stored === "watch" || stored === "trace" || stored === "write" ? stored : "watch";
  } catch { return "watch"; }
}
function rememberMode(mode: WritingMode) {
  try { localStorage.setItem(MODE_KEY, mode); } catch { /* a preference, not data */ }
}

type Loaded =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "ready"; characters: Map<string, Character | null>; unreachable: Set<string> };

export function WritingDialog({ headword, reading, language, gloss, listen, onClose, store = strokeStore() }: {
  headword: string;
  reading: string | null;
  language: string;
  gloss: string | null;
  /** The article's own listen button for the word, so the sheet plays what the article plays. */
  listen?: ReactNode;
  onClose(): void;
  /** Where the strokes come from: this device's store, unless a test hands it another. */
  store?: StrokeStore;
}) {
  const symbols = useMemo(() => hanCharacters(headword), [headword]);
  const [mode, setModeState] = useState<WritingMode>(rememberedMode);
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [at, setAt] = useState(0);
  const [runs, setRuns] = useState<Run[]>(() => symbols.map(startRun));
  const [said, setSaid] = useState("");
  const [animate, setAnimate] = useState<Animated | null>(null);
  const [pulse, setPulse] = useState<{ stroke: number; key: number } | null>(null);
  const [peek, setPeek] = useState(false);
  const [compare, setCompare] = useState(false);
  const [watch, setWatch] = useState({ shown: 0, playing: true });
  const keys = useRef(0);
  const timers = useRef<number[]>([]);

  const later = useCallback((ms: number, then: () => void) => {
    timers.current.push(window.setTimeout(then, ms));
  }, []);
  const stopTimers = useCallback(() => {
    timers.current.forEach((timer) => window.clearTimeout(timer));
    timers.current = [];
  }, []);
  useEffect(() => stopTimers, [stopTimers]);

  useEffect(() => {
    let current = true;
    store.strokesOf(symbols).then(({ found, unreachable }) => {
      if (!current) return;
      const characters = new Map<string, Character | null>();
      for (const symbol of symbols) {
        const data = found.get(symbol);
        characters.set(symbol, data ? characterOf(symbol, data) : null);
      }
      setLoaded({ state: "ready", characters, unreachable: new Set(unreachable) });
    }, (error: unknown) => {
      if (current) setLoaded({ state: "failed", message: error instanceof Error ? error.message : "The strokes could not be read." });
    });
    return () => { current = false; };
  }, [symbols, store]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const symbol = symbols[at] ?? "";
  const character = loaded.state === "ready" ? loaded.characters.get(symbol) ?? null : null;
  const run = runs[at] ?? startRun();
  const done = character ? isDone(run, character) : false;

  /** A clean slate for the character in view: nothing animating, nothing said. */
  const settle = useCallback(() => {
    stopTimers();
    setAnimate(null);
    setPulse(null);
    setPeek(false);
    setCompare(false);
    setSaid("");
  }, [stopTimers]);

  const chooseMode = (next: WritingMode) => {
    settle();
    setModeState(next);
    rememberMode(next);
    setRuns(symbols.map(startRun));
    setWatch({ shown: 0, playing: true });
  };

  const choose = (index: number) => {
    settle();
    setAt(index);
    setWatch({ shown: 0, playing: true });
  };

  /* Watching: one stroke written, a pause, the next, until the character is whole. */
  useEffect(() => {
    if (mode !== "watch" || !character || !watch.playing) return;
    if (watch.shown >= character.strokes.length) {
      setWatch((current) => ({ ...current, playing: false }));
      return;
    }
    const stroke = character.strokes[watch.shown];
    setAnimate({ stroke: stroke.index, tone: "ink", key: (keys.current += 1) });
    const timer = window.setTimeout(() => {
      setAnimate(null);
      setWatch((current) => ({ ...current, shown: current.shown + 1 }));
    }, animationTime(stroke) + BETWEEN);
    return () => window.clearTimeout(timer);
  }, [mode, character, watch.playing, watch.shown]);

  const showStroke = useCallback((stroke: number, tone: Animated["tone"]) => {
    if (!character) return;
    setAnimate({ stroke, tone, key: (keys.current += 1) });
    const time = animationTime(character.strokes[stroke]) + (tone === "hint" ? 250 + HINT_FADE : 0);
    later(time, () => setAnimate((current) => (current?.stroke === stroke ? null : current)));
  }, [character, later]);

  const onStroke = useCallback((points: InkPoint[]): boolean => {
    if (!character || done) return false;
    const { run: next, outcome } = attempt(run, character, points, { outline: mode === "trace" });
    setRuns((current) => current.map((one, index) => (index === at ? next : one)));
    setPulse(null);
    if (outcome.kind === "accepted") {
      setSaid("");
      return true;
    }
    setSaid(feedback(outcome));
    if (outcome.kind === "filled") {
      showStroke(outcome.stroke, "ink");
    } else {
      if (outcome.why.kind === "backwards") setPulse({ stroke: outcome.stroke, key: (keys.current += 1) });
      if (outcome.hint) showStroke(outcome.stroke, "hint");
    }
    return false;
  }, [character, done, run, mode, at, showStroke]);

  const hint = () => {
    if (!character || done) return;
    setRuns((current) => current.map((one, index) => (index === at ? markHinted(one) : one)));
    showStroke(nextStroke(run), "hint");
  };

  const peekNow = () => {
    if (!character || done) return;
    setRuns((current) => current.map((one, index) => (index === at ? markHinted(one) : one)));
    setPeek(true);
    later(PEEK, () => setPeek(false));
  };

  const again = () => {
    settle();
    setRuns((current) => current.map((one, index) => (index === at ? startRun() : one)));
  };

  const wholeWordAgain = (next: WritingMode) => {
    settle();
    if (next !== mode) { setModeState(next); rememberMode(next); }
    setRuns(symbols.map(startRun));
    setAt(0);
    setWatch({ shown: 0, playing: true });
  };

  const columns = useMemo(() => {
    const found = hanziColumns({ language, headword, reading });
    return found && found.length === symbols.length && found.every((column) => Array.from(column.characters).length === 1)
      ? found : null;
  }, [language, headword, reading, symbols.length]);

  const finishedAll = loaded.state === "ready" && symbols.every((one, index) => {
    const known = loaded.characters.get(one);
    return !known || isDone(runs[index], known);
  });
  const last = at === symbols.length - 1;
  const summary = character && done ? summarize(run) : null;
  const unavailable = loaded.state === "ready" && !character
    ? loaded.unreachable.has(symbol)
      ? `The strokes for ${symbol} are not on this device yet; they come with the next connection to the server.`
      : `There is no stroke data for ${symbol}.`
    : null;
  const hidden = mode === "write";

  const title = hidden ? "Write from memory" : `Write ${headword}`;
  const strokeCount = character?.strokes.length ?? 0;

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings writing-dialog" role="dialog" aria-modal="true" aria-labelledby="writing-title">
      <header>
        <h2 id="writing-title" lang={hidden ? undefined : language}>{title}</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>

      <div className="settings-body writing-body">
        <div className="writing-top">
          <div className="writing-prompt">
            {reading && <span className="writing-reading">{columns
              ? columns.map((column, index) => <span key={index}
                  className={`tone-${column.syllable.tone}${index === at ? " now" : ""}`}>{column.syllable.text}</span>)
              : <ReadingText reading={reading} language={language} />}</span>}
            {listen}
            {gloss && <span className="writing-gloss">{gloss}</span>}
          </div>
          <div className="seg writing-modes" role="group" aria-label="How to practise">
            {MODES.map((one) => <button key={one.mode} type="button" className={mode === one.mode ? "on" : ""}
              aria-pressed={mode === one.mode} onClick={() => chooseMode(one.mode)}>{one.label}</button>)}
          </div>
        </div>

        {symbols.length > 1 && <div className="writing-chars" role="group" aria-label="Characters">
          {symbols.map((one, index) => {
            const known = loaded.state === "ready" ? loaded.characters.get(one) : null;
            const finished = known ? isDone(runs[index], known) : false;
            const precision = finished ? summarize(runs[index]).precision : null;
            return <button key={index} type="button" lang={language}
              className={`writing-char${index === at ? " on" : ""}${finished ? " done" : ""}`}
              aria-current={index === at} aria-label={hidden && !finished ? `Character ${index + 1}` : `Character ${index + 1}, ${one}`}
              onClick={() => choose(index)}>
              <span className="glyph">{hidden && !finished ? "?" : one}</span>
              {precision !== null && <span className="score">{precision}</span>}
            </button>;
          })}
        </div>}

        <div className="writing-stage">
          {loaded.state === "loading" && <p className="hint">Fetching the strokes…</p>}
          {loaded.state === "failed" && <p className="hint">{loaded.message}</p>}
          {unavailable && <p className="hint">{unavailable}</p>}
          {character && <WritingPad
            character={character}
            outline={mode === "trace" || mode === "watch" || peek || compare}
            written={mode === "watch" ? watch.shown : run.results.length}
            animate={animate}
            numbers={mode === "watch"}
            radical={mode === "watch"}
            pulse={pulse}
            compare={compare ? run.results.flatMap((one) => (one.drawn ? [one.drawn as InkPoint[]] : [])) : null}
            drawing={mode !== "watch" && !done && animate?.tone !== "ink"}
            onStroke={onStroke}
            label={hidden && !done ? "Writing pad" : `Writing pad for ${symbol}`}
          />}
        </div>

        {character && mode !== "watch" && <ol className="writing-dots" aria-label="Strokes">
          {character.strokes.map((stroke) => {
            const result = run.results[stroke.index];
            const standing = result ? strokeStanding(result) : stroke.index === nextStroke(run) ? "next" : "ahead";
            return <li key={stroke.index} className={standing}
              aria-label={`Stroke ${stroke.index + 1}: ${{ clean: "right first time", helped: "written after a miss",
                filled: "written in for you", next: "next", ahead: "to come" }[standing]}`} />;
          })}
        </ol>}

        <p className="writing-said" role="status" aria-live="polite">{said
          || (summary ? summaryLine(summary)
            : character && mode !== "watch" ? `Stroke ${Math.min(nextStroke(run) + 1, strokeCount)} of ${strokeCount}` : "")}</p>

        {character && mode === "watch" && <div className="writing-controls">
          <button type="button" className="icon-btn" aria-label="Previous stroke" disabled={watch.shown === 0}
            onClick={() => { setAnimate(null); setWatch((current) => ({ shown: Math.max(0, current.shown - 1), playing: false })); }}>
            <BackIcon /></button>
          <button type="button" className="tb-btn primary" onClick={() => {
            if (watch.playing) { setAnimate(null); setWatch((current) => ({ ...current, playing: false })); }
            else setWatch((current) => ({ shown: current.shown >= strokeCount ? 0 : current.shown, playing: true }));
          }}>{watch.playing ? <><PauseIcon />Pause</> : <><PlayIcon />Play</>}</button>
          <button type="button" className="icon-btn" aria-label="Next stroke" disabled={watch.shown >= strokeCount}
            onClick={() => { setAnimate(null); setWatch((current) => ({ shown: Math.min(strokeCount, current.shown + 1), playing: false })); }}>
            <ForwardIcon /></button>
          <span className="writing-count">Stroke {Math.min(watch.shown + (animate ? 1 : 0), strokeCount)} of {strokeCount}</span>
          <button type="button" className="tb-btn" onClick={() => setWatch({ shown: 0, playing: true })}><RepeatIcon />Again</button>
          {last ? <button type="button" className="tb-btn" onClick={() => chooseMode("trace")}>Trace it</button>
            : <button type="button" className="tb-btn" onClick={() => choose(at + 1)}>Next character</button>}
        </div>}

        {character && mode !== "watch" && !done && <div className="writing-controls">
          <button type="button" className="tb-btn" onClick={hint}>Show the next stroke</button>
          {mode === "write" && <button type="button" className="tb-btn" onClick={peekNow}>Peek</button>}
          <button type="button" className="tb-btn" onClick={again}><RepeatIcon />Start over</button>
        </div>}

        {character && mode !== "watch" && done && <div className="writing-controls">
          <button type="button" className={`tb-btn${compare ? " on" : ""}`} aria-pressed={compare}
            onClick={() => setCompare((current) => !current)}>Compare</button>
          <button type="button" className="tb-btn" onClick={again}><RepeatIcon />Again</button>
          {!last && <button type="button" className="tb-btn primary" onClick={() => choose(at + 1)}>Next character<ForwardIcon /></button>}
          {last && finishedAll && mode === "trace" && <button type="button" className="tb-btn primary"
            onClick={() => wholeWordAgain("write")}>Write it from memory</button>}
          {last && finishedAll && mode === "write" && <button type="button" className="tb-btn primary"
            onClick={() => wholeWordAgain("write")}>Write the word again</button>}
        </div>}
      </div>
    </section>
  </div>;
}

function summaryLine(summary: ReturnType<typeof summarize>): string {
  const parts = [`${summary.strokes} ${summary.strokes === 1 ? "stroke" : "strokes"}`,
    `${summary.clean} right first time`];
  if (summary.outOfOrder) parts.push(`${summary.outOfOrder} out of order`);
  if (summary.backwards) parts.push(`${summary.backwards} backwards`);
  if (summary.filled) parts.push(`${summary.filled} written in`);
  if (summary.precision !== null) parts.push(`precision ${summary.precision}, ${precisionWord(summary.precision)}`);
  return parts.join(" · ");
}
