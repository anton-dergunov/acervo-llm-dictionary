/**
 * One character being written, stroke by stroke: what each drawn stroke did to it.
 *
 * Pure, so the rules the owner is taught by — which stroke is accepted, when a hint comes, when a
 * stroke is filled in so nobody is stuck — are tested without a screen. The pad draws a `Run` and
 * hands every finished stroke to `attempt`.
 */

import { gradeStroke } from "./grade";
import { judge, type Judgement } from "./match";
import type { Character, Point } from "./strokeData";

/** After this many refusals of one stroke, the stroke is shown being written. */
export const HINT_AFTER = 2;
/** After this many, it is written in for you and counted as missed. */
export const FILL_AFTER = 4;

export interface StrokeResult {
  /** Refusals of any kind before it was accepted or filled in. */
  misses: number;
  /** Of those, how many were another stroke in the order, and how many this one backwards. */
  outOfOrder: number;
  backwards: number;
  /** Shown being written — by a hint, by Peek, or because it was filled in. */
  hinted: boolean;
  filled: boolean;
  /** The precision grade, for a stroke that was written rather than filled in. */
  score: number | null;
  /** What the hand actually drew, for Compare. */
  drawn: Point[] | null;
}

export interface Run {
  /** The results of the strokes written so far, in order; the next stroke is `results.length`. */
  results: StrokeResult[];
  /** The stroke in progress: refusals so far, and whether it has been shown. */
  pending: Omit<StrokeResult, "filled" | "score" | "drawn">;
}

export type Outcome =
  | { kind: "accepted"; stroke: number; score: number }
  | { kind: "refused"; stroke: number; why: Exclude<Judgement, { kind: "match" }>; hint: boolean }
  | { kind: "filled"; stroke: number };

const fresh = (): Run["pending"] => ({ misses: 0, outOfOrder: 0, backwards: 0, hinted: false });

export function startRun(): Run {
  return { results: [], pending: fresh() };
}

export function nextStroke(run: Run): number {
  return run.results.length;
}

export function isDone(run: Run, character: Character): boolean {
  return run.results.length >= character.strokes.length;
}

/** The pending stroke was shown being written: a hint asked for, or Peek. */
export function markHinted(run: Run): Run {
  return { ...run, pending: { ...run.pending, hinted: true } };
}

export function attempt(run: Run, character: Character, drawn: Point[], options: { outline: boolean }):
  { run: Run; outcome: Outcome } {
  const stroke = nextStroke(run);
  if (stroke >= character.strokes.length) throw new Error("This character is already written.");
  const verdict = judge(drawn, character, stroke, { outline: options.outline });
  if (verdict.kind === "match") {
    const { score } = gradeStroke(drawn, character.strokes[stroke].median);
    const result: StrokeResult = { ...run.pending, filled: false, score, drawn };
    return { run: { results: [...run.results, result], pending: fresh() }, outcome: { kind: "accepted", stroke, score } };
  }
  const pending = {
    misses: run.pending.misses + 1,
    outOfOrder: run.pending.outOfOrder + (verdict.kind === "later" || verdict.kind === "earlier" ? 1 : 0),
    backwards: run.pending.backwards + (verdict.kind === "backwards" ? 1 : 0),
    hinted: run.pending.hinted
  };
  if (pending.misses >= FILL_AFTER) {
    const result: StrokeResult = { ...pending, hinted: true, filled: true, score: null, drawn: null };
    return { run: { results: [...run.results, result], pending: fresh() }, outcome: { kind: "filled", stroke } };
  }
  const hint = pending.misses >= HINT_AFTER;
  return {
    run: { ...run, pending: { ...pending, hinted: pending.hinted || hint } },
    outcome: { kind: "refused", stroke, why: verdict, hint }
  };
}

/** What the strip and the line under a finished character say. */
export interface Summary {
  strokes: number;
  /** Written right the first time, with no hint. */
  clean: number;
  outOfOrder: number;
  backwards: number;
  filled: number;
  /** The mean grade of the strokes that were written, or null when none were. */
  precision: number | null;
}

export function summarize(run: Run): Summary {
  const written = run.results.filter((one) => one.score !== null).map((one) => one.score as number);
  return {
    strokes: run.results.length,
    clean: run.results.filter((one) => one.misses === 0 && !one.hinted && !one.filled).length,
    outOfOrder: run.results.reduce((sum, one) => sum + one.outOfOrder, 0),
    backwards: run.results.reduce((sum, one) => sum + one.backwards, 0),
    filled: run.results.filter((one) => one.filled).length,
    precision: written.length ? Math.round(written.reduce((sum, one) => sum + one, 0) / written.length) : null
  };
}

/** How one stroke went, as a dot in the strip. */
export function strokeStanding(result: StrokeResult): "clean" | "helped" | "filled" {
  if (result.filled) return "filled";
  return result.misses === 0 && !result.hinted ? "clean" : "helped";
}

/** The sentence after a refused or filled stroke. Numbers are the owner's, counted from one. */
export function feedback(outcome: Outcome): string {
  const expected = outcome.stroke + 1;
  if (outcome.kind === "accepted") return "";
  if (outcome.kind === "filled") return `Stroke ${expected} is written in for you — watch how it goes.`;
  const { why, hint } = outcome;
  const watch = hint ? " Watch it once." : "";
  if (why.kind === "backwards") return `Right stroke, other way round — start at the dot.${watch}`;
  if (why.kind === "later") return `That's stroke ${why.drawn + 1} — stroke ${expected} comes first.${watch}`;
  if (why.kind === "earlier") return `Stroke ${why.drawn + 1} is already written — next is stroke ${expected}.${watch}`;
  return `Not quite — try stroke ${expected} again.${watch}`;
}
