/** Real characters from the pinned dataset, and ways of drawing their strokes, for the tests. */

import ren from "../testFixtures/strokes/人.json";
import kou from "../testFixtures/strokes/口.json";
import ma from "../testFixtures/strokes/妈.json";
import shui from "../testFixtures/strokes/水.json";
import { character, type Character, type CharacterStrokes, type Point } from "./strokeData";

export const FIXTURES: Record<string, CharacterStrokes> = {
  人: ren as CharacterStrokes, 口: kou as CharacterStrokes, 妈: ma as CharacterStrokes, 水: shui as CharacterStrokes
};

export function fixture(symbol: keyof typeof FIXTURES & string): Character {
  return character(symbol, FIXTURES[symbol]);
}

/** A median, as a hand would draw it: every few units along it, not only at its vertices. */
export function traced(points: Point[], step = 12): Point[] {
  const result: Point[] = [points[0]];
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    const pieces = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / step));
    for (let piece = 1; piece <= pieces; piece += 1) {
      result.push({ x: a.x + ((b.x - a.x) * piece) / pieces, y: a.y + ((b.y - a.y) * piece) / pieces });
    }
  }
  return result;
}

/** The same, wobbling: a deterministic sideways shake of up to `amplitude` units. */
export function shaky(points: Point[], amplitude: number): Point[] {
  return traced(points).map((point, index) => ({
    x: point.x + amplitude * Math.sin(index * 1.7),
    y: point.y + amplitude * Math.cos(index * 2.3)
  }));
}

export function shifted(points: Point[], dx: number, dy: number): Point[] {
  return traced(points).map((point) => ({ x: point.x + dx, y: point.y + dy }));
}
