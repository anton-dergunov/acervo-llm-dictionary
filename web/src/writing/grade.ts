/**
 * How precisely an accepted stroke was written: 0–100.
 *
 * Acceptance (`match.ts`) is deliberately forgiving: a stroke may start a quarter of the box away from
 * where it should and still count, because refusing a rough-but-right stroke teaches nothing. The
 * grade is where closeness is told back, from the same points:
 *
 * - **path**: how far the drawn line runs from the median (root mean square), measured both ways (every
 *   drawn point to the median, and every point along the median to the drawn line), so a stroke that
 *   is close but stops halfway is not graded as close;
 * - **ends**: how far it starts from the median's start and ends from its end — where a brush is set
 *   down and lifted, which is most of what makes a stroke look right.
 *
 * A dataset stroke is roughly a hundred units wide, so a path within a few units of the centre line
 * is as good as a hand gets, and one seventy away has left the stroke's body.
 * **These bounds are a first guess**, set from drawing the fixtures; they are to be tuned by hand on
 * the iPad, which is the only place "that felt like an 80" can be measured (`docs/features/writing.md`).
 */

import { distance, length } from "./match";
import type { Point } from "./strokeData";

export const PATH_PERFECT = 6;
export const PATH_NONE = 70;
export const ENDS_PERFECT = 15;
export const ENDS_NONE = 120;
const PATH_WEIGHT = 0.65;

export interface StrokeGrade {
  score: number;
  /** Root-mean-square distance between the drawn line and the median, in dataset units. */
  path: number;
  /** Mean of the start and end offsets, in dataset units. */
  ends: number;
}

function toSegment(point: Point, a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const span = dx * dx + dy * dy;
  if (span === 0) return distance(point, a);
  const t = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / span));
  return distance(point, { x: a.x + t * dx, y: a.y + t * dy });
}

function toLine(point: Point, line: Point[]): number {
  if (line.length === 1) return distance(point, line[0]);
  let best = Infinity;
  for (let index = 1; index < line.length; index += 1) best = Math.min(best, toSegment(point, line[index - 1], line[index]));
  return best;
}

/** Points every `step` units along a line, ends included. */
function along(line: Point[], step = 16): Point[] {
  const result = [line[0]];
  let carried = 0;
  for (let index = 1; index < line.length; index += 1) {
    const a = line[index - 1];
    const b = line[index];
    const span = distance(a, b);
    let at = step - carried;
    while (at <= span) {
      result.push({ x: a.x + (b.x - a.x) * (at / span), y: a.y + (b.y - a.y) * (at / span) });
      at += step;
    }
    carried = span - (at - step);
  }
  result.push(line[line.length - 1]);
  return result;
}

const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;
const fall = (value: number, perfect: number, none: number) =>
  Math.max(0, Math.min(1, 1 - (value - perfect) / (none - perfect)));

export function gradeStroke(drawn: Point[], median: Point[]): StrokeGrade {
  if (drawn.length === 0 || median.length === 0 || length(median) === 0) return { score: 0, path: Infinity, ends: Infinity };
  // Root mean square rather than the mean, so a stroke that is mostly right and wanders once is
  // told so: the wander is what the eye sees.
  const rms = (values: number[]) => Math.sqrt(mean(values.map((value) => value * value)));
  const outward = rms(along(drawn).map((point) => toLine(point, median)));
  const inward = rms(along(median).map((point) => toLine(point, drawn)));
  const path = (outward + inward) / 2;
  const ends = (distance(drawn[0], median[0]) + distance(drawn[drawn.length - 1], median[median.length - 1])) / 2;
  const score = Math.round(100 * (PATH_WEIGHT * fall(path, PATH_PERFECT, PATH_NONE)
    + (1 - PATH_WEIGHT) * fall(ends, ENDS_PERFECT, ENDS_NONE)));
  return { score, path, ends };
}

/** A word for a score, for the line under a finished character. */
export function precisionWord(score: number): string {
  if (score >= 85) return "clean";
  if (score >= 65) return "good";
  return "loose";
}
