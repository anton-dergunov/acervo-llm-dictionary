/**
 * Whether a drawn stroke is the stroke that comes next — and if not, what it was instead.
 *
 * The matching is Hanzi Writer's (`strokeMatches` and its geometry, v3.7.3), ported rather than
 * depended on: its runtime reads input through mouse and first-touch events, which knows nothing of
 * a pen and a resting palm, and its quiz only ever says "mistake". The sentence that teaches the
 * order is the one it cannot say — *that was stroke 5; stroke 3 comes first* — so `judge` below
 * extends it to name which stroke was drawn, and in which direction.
 *
 * Hanzi Writer — MIT License, Copyright (c) 2014 David Chanin. https://github.com/chanind/hanzi-writer
 *
 * A drawn stroke matches the expected stroke's median when all of these hold, in the dataset's
 * 1024-unit box (`strokeData.ts`):
 *
 * - it lies near the median on average;
 * - it starts near the median's start and ends near its end;
 * - it runs the same way (the mean best cosine between its segments and the median's);
 * - it has the same shape, by the Fréchet distance between the two after each is resampled, centred
 *   and scaled, tried at five small rotations;
 * - it is not much shorter.
 *
 * Only the next stroke can be accepted, so the order is enforced by construction; a stroke drawn
 * backwards matches only when reversed, and is refused.
 */

import type { Character, Point, Stroke } from "./strokeData";

const COSINE_SIMILARITY_THRESHOLD = 0;
const START_AND_END_DIST_THRESHOLD = 250;
const FRECHET_THRESHOLD = 0.4;
const MIN_LEN_THRESHOLD = 0.35;
const AVERAGE_DISTANCE_THRESHOLD = 350;
const SHAPE_FIT_ROTATIONS = [Math.PI / 16, Math.PI / 32, 0, -Math.PI / 32, -Math.PI / 16];

export interface MatchOptions {
  /** Below 1 is stricter, above it more lenient. */
  leniency?: number;
  /** A drawing over a visible outline is held closer to it. */
  outline?: boolean;
}

/* ── geometry ─────────────────────────────────────────────────────────── */

const subtract = (a: Point, b: Point): Point => ({ x: a.x - b.x, y: a.y - b.y });
const magnitude = (p: Point) => Math.sqrt(p.x * p.x + p.y * p.y);
export const distance = (a: Point, b: Point) => magnitude(subtract(a, b));
const average = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;

export function length(points: Point[]): number {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) total += distance(points[index], points[index - 1]);
  return total;
}

function cosineSimilarity(a: Point, b: Point): number {
  return (a.x * b.x + a.y * b.y) / magnitude(a) / magnitude(b);
}

/** A point on the line through `a` and `b`, `by` beyond `b`. */
function extendPointOnLine(a: Point, b: Point, by: number): Point {
  const vector = subtract(b, a);
  const norm = by / magnitude(vector);
  return { x: b.x + norm * vector.x, y: b.y + norm * vector.y };
}

/** The discrete Fréchet distance (Eiter and Mannila), one column at a time. */
function frechetDistance(first: Point[], second: Point[]): number {
  const long = first.length >= second.length ? first : second;
  const short = first.length >= second.length ? second : first;
  let previous: number[] = [];
  for (let i = 0; i < long.length; i += 1) {
    const current: number[] = [];
    for (let j = 0; j < short.length; j += 1) {
      const here = distance(long[i], short[j]);
      if (i === 0 && j === 0) current.push(here);
      else if (i > 0 && j === 0) current.push(Math.max(previous[0], here));
      else if (i === 0) current.push(Math.max(current[j - 1], here));
      else current.push(Math.max(Math.min(previous[j], previous[j - 1], current[j - 1]), here));
    }
    previous = current;
  }
  return previous[short.length - 1];
}

/** No segment longer than `most`. */
function subdivide(curve: Point[], most = 0.05): Point[] {
  const result = curve.slice(0, 1);
  for (const point of curve.slice(1)) {
    const last = result[result.length - 1];
    const span = distance(point, last);
    if (span > most) {
      const pieces = Math.ceil(span / most);
      const step = span / pieces;
      for (let index = 0; index < pieces; index += 1) result.push(extendPointOnLine(point, last, -step * (index + 1)));
    } else {
      result.push(point);
    }
  }
  return result;
}

/** The curve redrawn as `count` points spaced evenly along it. */
function resample(curve: Point[], count = 30): Point[] {
  const step = length(curve) / (count - 1);
  const result = [curve[0]];
  const remaining = curve.slice(1);
  for (let index = 0; index < count - 2; index += 1) {
    let last = result[result.length - 1];
    let left = step;
    for (;;) {
      const next = remaining[0];
      const span = distance(last, next);
      if (span < left && remaining.length > 1) {
        left -= span;
        last = remaining.shift()!;
      } else {
        result.push(extendPointOnLine(last, next, left - span));
        break;
      }
    }
  }
  result.push(curve[curve.length - 1]);
  return result;
}

/** Translated to its mean and scaled by its ends (Procrustes), then finely subdivided. */
function normalize(curve: Point[]): Point[] {
  const outlined = resample(curve);
  const mean = { x: average(outlined.map((p) => p.x)), y: average(outlined.map((p) => p.y)) };
  const translated = outlined.map((p) => subtract(p, mean));
  const first = translated[0];
  const last = translated[translated.length - 1];
  const scale = Math.sqrt(average([first.x ** 2 + first.y ** 2, last.x ** 2 + last.y ** 2]));
  return subdivide(translated.map((p) => ({ x: p.x / scale, y: p.y / scale })));
}

function rotate(curve: Point[], theta: number): Point[] {
  return curve.map((p) => ({
    x: Math.cos(theta) * p.x - Math.sin(theta) * p.y,
    y: Math.sin(theta) * p.x + Math.cos(theta) * p.y
  }));
}

export function stripDuplicates(points: Point[]): Point[] {
  const result: Point[] = [];
  for (const point of points) {
    const last = result[result.length - 1];
    if (!last || last.x !== point.x || last.y !== point.y) result.push(point);
  }
  return result;
}

function vectors(points: Point[]): Point[] {
  const result: Point[] = [];
  for (let index = 1; index < points.length; index += 1) result.push(subtract(points[index], points[index - 1]));
  return result;
}

/** The nearest vertex of the median, as Hanzi Writer measures it. */
function nearest(stroke: Stroke, point: Point): number {
  return Math.min(...stroke.median.map((one) => distance(one, point)));
}

/* ── one stroke against one stroke ────────────────────────────────────── */

interface MatchData { isMatch: boolean; averageDistance: number; backwards: boolean }

function matchData(points: Point[], stroke: Stroke, options: Required<MatchOptions>, checkBackwards: boolean): MatchData {
  const { leniency, outline } = options;
  const averageDistance = average(points.map((point) => nearest(stroke, point)));
  const distanceModifier = outline || stroke.index > 0 ? 0.5 : 1;
  if (averageDistance > AVERAGE_DISTANCE_THRESHOLD * distanceModifier * leniency) {
    return { isMatch: false, averageDistance, backwards: false };
  }
  const median = stroke.median;
  const startAndEnd = distance(median[0], points[0]) <= START_AND_END_DIST_THRESHOLD * leniency
    && distance(median[median.length - 1], points[points.length - 1]) <= START_AND_END_DIST_THRESHOLD * leniency;
  const medianVectors = vectors(median);
  const direction = average(vectors(points).map((edge) =>
    Math.max(...medianVectors.map((one) => cosineSimilarity(one, edge))))) > COSINE_SIMILARITY_THRESHOLD;
  const drawn = normalize(points);
  const model = normalize(median);
  const shape = Math.min(...SHAPE_FIT_ROTATIONS.map((theta) => frechetDistance(drawn, rotate(model, theta))))
    <= FRECHET_THRESHOLD * leniency;
  const long = leniency * (length(points) + 25) / (length(median) + 25) >= MIN_LEN_THRESHOLD;
  const isMatch = startAndEnd && direction && shape && long;
  if (checkBackwards && !isMatch) {
    const reversed = matchData([...points].reverse(), stroke, options, false);
    if (reversed.isMatch) return { isMatch: false, averageDistance, backwards: true };
  }
  return { isMatch, averageDistance, backwards: false };
}

function settled(options: MatchOptions): Required<MatchOptions> {
  return { leniency: options.leniency ?? 1, outline: options.outline ?? false };
}

/** Whether `points` is stroke `index` of the character — Hanzi Writer's `strokeMatches`. */
export function strokeMatches(points: Point[], character: Character, index: number, options: MatchOptions = {}):
  { isMatch: boolean; backwards: boolean } {
  const drawn = stripDuplicates(points);
  if (drawn.length < 2) return { isMatch: false, backwards: false };
  const chosen = settled(options);
  const expected = character.strokes[index];
  const found = matchData(drawn, expected, chosen, true);
  if (!found.isMatch) return { isMatch: false, backwards: found.backwards };

  // A later stroke that fits better means this was probably that one. Rather than refusing outright,
  // the expected stroke is asked again, more strictly, by how much better the other fitted.
  let closest = found.averageDistance;
  for (const later of character.strokes.slice(index + 1)) {
    const other = matchData(drawn, later, chosen, false);
    if (other.isMatch && other.averageDistance < closest) closest = other.averageDistance;
  }
  if (closest < found.averageDistance) {
    const adjustment = 0.6 * (closest + found.averageDistance) / (2 * found.averageDistance);
    const again = matchData(drawn, expected, { ...chosen, leniency: chosen.leniency * adjustment }, true);
    return { isMatch: again.isMatch, backwards: again.backwards };
  }
  return { isMatch: true, backwards: false };
}

/* ── what the stroke was, for the sentence that teaches ───────────────── */

export type Judgement =
  | { kind: "match" }
  /** The expected stroke, drawn from its end to its start. */
  | { kind: "backwards" }
  /** A stroke that comes later in the order. */
  | { kind: "later"; drawn: number }
  /** A stroke already written. */
  | { kind: "earlier"; drawn: number }
  | { kind: "miss" };

/**
 * The verdict on one drawn stroke when stroke `index` is the one expected.
 *
 * Acceptance is `strokeMatches` and nothing else. Only a refusal is looked at further: the stroke is
 * then matched against every other stroke, and the closest one it fits names what was drawn.
 */
export function judge(points: Point[], character: Character, index: number, options: MatchOptions = {}): Judgement {
  const verdict = strokeMatches(points, character, index, options);
  if (verdict.isMatch) return { kind: "match" };
  if (verdict.backwards) return { kind: "backwards" };
  const drawn = stripDuplicates(points);
  if (drawn.length < 2) return { kind: "miss" };
  const chosen = settled(options);
  let best: { index: number; averageDistance: number } | null = null;
  for (const stroke of character.strokes) {
    if (stroke.index === index) continue;
    const other = matchData(drawn, stroke, chosen, false);
    if (other.isMatch && (!best || other.averageDistance < best.averageDistance)) {
      best = { index: stroke.index, averageDistance: other.averageDistance };
    }
  }
  if (!best) return { kind: "miss" };
  return best.index > index ? { kind: "later", drawn: best.index } : { kind: "earlier", drawn: best.index };
}
