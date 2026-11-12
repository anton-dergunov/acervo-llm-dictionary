/**
 * How one character is written, as the pinned dataset describes it (`docs/features/writing.md`).
 *
 * Make Me a Hanzi's data, as packaged by hanzi-writer-data (Arphic Public License): for each stroke,
 * in the standard order, its **outline** — an SVG path, the shape a brush leaves — and its
 * **median**, the centre line in the direction the stroke is written. Everything is in one box,
 * 1024 units wide, with y pointing *up* from a baseline: x runs 0…1024 and y −124…900. The page
 * draws in that space through one transform, and a pointer is brought into it by `toCharacter`, so
 * nothing that checks a stroke ever sees a pixel.
 */

export interface Point { x: number; y: number }

/** What the server answers for one character, as the dataset ships it. */
export interface CharacterStrokes {
  strokes: string[];
  medians: [number, number][][];
  /** The strokes that make up the radical, where the dataset names one. */
  radStrokes?: number[];
}

/** One stroke, ready to be drawn and matched against. */
export interface Stroke {
  index: number;
  outline: string;
  median: Point[];
  inRadical: boolean;
}

export interface Character {
  symbol: string;
  strokes: Stroke[];
}

export const BOX = 1024;
/** The top of the box in the dataset's own coordinates; its foot is `TOP - BOX`. */
export const TOP = 900;
/** Room around the box, in the same units, so a stroke that starts at an edge can still be drawn. */
export const MARGIN = 40;
/** The SVG transform that takes the dataset's y-up space into the page's y-down one. */
export const FLIP = `translate(0 ${TOP}) scale(1 -1)`;

export function character(symbol: string, data: CharacterStrokes): Character {
  const radical = new Set(data.radStrokes ?? []);
  return {
    symbol,
    strokes: data.strokes.map((outline, index) => ({
      index,
      outline,
      median: (data.medians[index] ?? []).map(([x, y]) => ({ x, y })),
      inRadical: radical.has(index)
    }))
  };
}

/** A point on the drawn square, given as a fraction of its width and height, in dataset units. */
export function toCharacter(fractionX: number, fractionY: number): Point {
  const span = BOX + 2 * MARGIN;
  return { x: fractionX * span - MARGIN, y: TOP - (fractionY * span - MARGIN) };
}

/** A dataset point in the page's y-down space, for whatever is drawn outside the flipped group. */
export function toPage(point: Point): Point {
  return { x: point.x, y: TOP - point.y };
}

/** The characters of a text that have strokes: the Han script, which is what the dataset covers. */
const HAN = /\p{Script=Han}/u;
export function isHan(symbol: string): boolean {
  return HAN.test(symbol);
}

export function hanCharacters(text: string): string[] {
  return Array.from(text).filter(isHan);
}
