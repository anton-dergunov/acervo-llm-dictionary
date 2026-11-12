/**
 * The square a character is written on: its grid, its outline, the strokes written so far, the ink
 * being drawn, and the strokes shown being written.
 *
 * **Input is Pointer Events and nothing else**, like the map and the photo (`touch-action: none`, a
 * captured pointer), for what a pen needs:
 *
 * - **palm rejection**: once a pen has touched this pad, a finger no longer draws on it — the hand
 *   resting on the glass is a touch too. A pen landing while a touch stroke is under way replaces it,
 *   since that touch was almost certainly the palm arriving first. A device with no pen draws with a
 *   finger as ever;
 * - **the pen's own points**: `getCoalescedEvents`, so a Pencil's 240 a second are all kept rather
 *   than the 60 a frame delivers, and its pressure, which shapes the ink.
 *
 * The ink is drawn by perfect-freehand (MIT) as a filled outline rather than a fixed-width line, so
 * it looks like ink; a mouse or a finger has no pressure, and it is simulated from speed.
 *
 * Everything is drawn in the dataset's own box (`strokeData.ts`), so nothing here converts a stroke
 * twice: the pointer is brought into that space once, by `toCharacter`.
 */

import { getStroke } from "perfect-freehand";
import { useCallback, useEffect, useId, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { length } from "./match";
import { BOX, FLIP, MARGIN, toCharacter, toPage, type Character, type Point, type Stroke } from "./strokeData";

export interface InkPoint extends Point { pressure: number }

/** A stroke shown being written: in ink as part of the character, or as a hint that fades. */
export interface Animated {
  stroke: number;
  tone: "ink" | "hint";
  /** A new value replays the same stroke. */
  key: number;
}

/** How long a stroke takes to be shown, by its length: slow enough to follow the direction. */
export function animationTime(stroke: Stroke): number {
  return Math.round((length(stroke.median) + 600) / 1.8);
}
export const HINT_FADE = 700;

/** The ink's width, in dataset units: a little under a printed stroke, so a traced outline shows. */
const INK = 58;

function inkOutline(points: InkPoint[], simulated: boolean, last: boolean): string {
  // A simulated pressure swells a slow stroke, so a mouse or a finger thins less from a slimmer start.
  const outline = getStroke(points.map((p) => [p.x, p.y, p.pressure]), {
    size: simulated ? INK * 0.85 : INK, thinning: simulated ? 0.35 : 0.6, smoothing: 0.5, streamline: 0.35,
    simulatePressure: simulated, last,
    start: { taper: 0, cap: true }, end: { taper: simulated ? 0 : 18, cap: true }
  });
  if (outline.length < 2) return "";
  const [first, ...rest] = outline;
  return `M ${first[0].toFixed(1)} ${first[1].toFixed(1)} ${rest.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ")} Z`;
}

/** The median, its start pulled back by half a brush so the round start is covered too. */
function animationPath(stroke: Stroke): { d: string; span: number } {
  const median = stroke.median;
  if (median.length < 2) return { d: "", span: 0 };
  const [a, b] = median;
  const span = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const start = { x: a.x - ((b.x - a.x) / span) * 100, y: a.y - ((b.y - a.y) / span) * 100 };
  const points = [start, ...median.slice(1)];
  return {
    d: `M ${points.map((p) => `${p.x} ${p.y}`).join(" L ")}`,
    span: Math.ceil(length(points) + 100)
  };
}

interface Fading { id: number; d: string; accepted: boolean }

export function WritingPad({ character, outline, written, animate = null, numbers = false, radical = false,
                             pulse = null, compare = null, drawing, onStroke, label }: {
  character: Character;
  /** The faint shape of the whole character, to write over. */
  outline: boolean;
  /** How many strokes are written: drawn solid, in order. */
  written: number;
  animate?: Animated | null;
  /** Each written stroke's number at its start, and the radical in its own colour: Watch. */
  numbers?: boolean;
  radical?: boolean;
  /** A dot where the expected stroke starts, for a stroke drawn backwards; a new key replays it. */
  pulse?: { stroke: number; key: number } | null;
  /** What the hand drew, laid over the strokes. */
  compare?: InkPoint[][] | null;
  /** Whether a drawn stroke is taken. */
  drawing: boolean;
  /** A finished stroke, in dataset units. Answers whether it was accepted, which colours its ink. */
  onStroke?(points: InkPoint[]): boolean;
  label: string;
}) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const svg = useRef<SVGSVGElement | null>(null);
  const active = useRef<{ pointer: number; type: string; points: InkPoint[] } | null>(null);
  const penSeen = useRef(false);
  const frame = useRef<number | null>(null);
  const fadeId = useRef(0);
  const [live, setLive] = useState<{ points: InkPoint[]; simulated: boolean } | null>(null);
  const [fading, setFading] = useState<Fading[]>([]);

  useEffect(() => () => { if (frame.current !== null) cancelAnimationFrame(frame.current); }, []);

  const paint = useCallback(() => {
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      const stroke = active.current;
      setLive(stroke ? { points: [...stroke.points], simulated: stroke.type !== "pen" } : null);
    });
  }, []);

  const pointOf = (event: { clientX: number; clientY: number; pressure: number }, type: string): InkPoint => {
    const box = svg.current!.getBoundingClientRect();
    const at = toCharacter((event.clientX - box.left) / box.width, (event.clientY - box.top) / box.height);
    return { ...at, pressure: type === "pen" ? Math.max(0.05, event.pressure || 0.5) : 0.5 };
  };

  const begin = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!drawing || !svg.current) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (event.pointerType === "pen") {
      penSeen.current = true;
      // The palm got there first: the pen's stroke is the one meant.
      if (active.current && active.current.type === "touch") active.current = null;
    } else if (event.pointerType === "touch" && penSeen.current) {
      return;
    }
    if (active.current) return;
    event.preventDefault();
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* jsdom, or a pointer already gone */ }
    active.current = { pointer: event.pointerId, type: event.pointerType || "mouse", points: [pointOf(event, event.pointerType)] };
    paint();
  };

  const move = (event: ReactPointerEvent<SVGSVGElement>) => {
    const stroke = active.current;
    if (!stroke || event.pointerId !== stroke.pointer) return;
    const native = event.nativeEvent;
    const all = typeof native.getCoalescedEvents === "function" ? native.getCoalescedEvents() : [];
    for (const one of all.length ? all : [native]) stroke.points.push(pointOf(one, stroke.type));
    paint();
  };

  const finish = (event: ReactPointerEvent<SVGSVGElement>, kept: boolean) => {
    const stroke = active.current;
    if (!stroke || event.pointerId !== stroke.pointer) return;
    active.current = null;
    setLive(null);
    if (!kept || stroke.points.length < 2) return;
    const accepted = onStroke ? onStroke(stroke.points) : false;
    const fade = { id: (fadeId.current += 1), d: inkOutline(stroke.points, stroke.type !== "pen", true), accepted };
    setFading((current) => [...current, fade]);
    window.setTimeout(() => setFading((current) => current.filter((one) => one.id !== fade.id)), accepted ? 320 : 650);
  };

  const strokes = character.strokes;
  const animating = animate ? strokes[animate.stroke] : null;
  const solid = strokes.filter((stroke) => stroke.index < written
    && !(animate?.tone === "ink" && animate.stroke === stroke.index));
  const shownNumbers = numbers ? strokes.filter((stroke) => stroke.index < written
    || (animate?.tone === "ink" && animate.stroke === stroke.index)) : [];
  const path = animating ? animationPath(animating) : null;
  const pulseAt = pulse && strokes[pulse.stroke]?.median[0] ? toPage(strokes[pulse.stroke].median[0]) : null;
  const span = BOX + 2 * MARGIN;

  return <svg
    ref={svg}
    className={`writing-pad${drawing ? " drawing" : ""}${compare ? " comparing" : ""}`}
    viewBox={`${-MARGIN} ${-MARGIN} ${span} ${span}`}
    role="img" aria-label={label}
    onPointerDown={begin} onPointerMove={move}
    onPointerUp={(event) => finish(event, true)} onPointerCancel={(event) => finish(event, false)}
    onContextMenu={(event) => event.preventDefault()}
  >
    {/* 米字格: the square, its centre lines and its diagonals, which is how a learner places a stroke. */}
    <g className="writing-grid" aria-hidden="true">
      <rect x="0" y="0" width={BOX} height={BOX} />
      <path className="guide" d={`M ${BOX / 2} 0 V ${BOX} M 0 ${BOX / 2} H ${BOX} M 0 0 L ${BOX} ${BOX} M ${BOX} 0 L 0 ${BOX}`} />
    </g>
    <defs>
      {/* In the user space of the path it clips, which is already flipped: no transform of its own. */}
      {animating && <clipPath id={`${id}-clip`}><path d={animating.outline} /></clipPath>}
    </defs>
    <g transform={FLIP}>
      {outline && <g className="writing-outline">{strokes.map((stroke) =>
        <path key={stroke.index} d={stroke.outline} />)}</g>}
      <g className="writing-strokes">{solid.map((stroke) =>
        <path key={stroke.index} d={stroke.outline} className={radical && stroke.inRadical ? "radical" : undefined} />)}</g>
    </g>
    {animating && path && <path
      key={`${animate!.key}-${animate!.stroke}`}
      className={`writing-anim ${animate!.tone}${radical && animating.inRadical ? " radical" : ""}`}
      transform={FLIP} clipPath={`url(#${id}-clip)`} d={path.d}
      strokeDasharray={`${path.span} ${path.span}`} strokeDashoffset={path.span}
      style={{
        animationDuration: animate!.tone === "hint"
          ? `${animationTime(animating)}ms, ${HINT_FADE}ms`
          : `${animationTime(animating)}ms`,
        animationDelay: animate!.tone === "hint" ? `0ms, ${animationTime(animating) + 250}ms` : undefined
      }}
    />}
    {/* The hand's line as a thin centre line, which is what can be read against the model's shape. */}
    {compare && <g transform={FLIP} className="writing-compare">{compare.map((points, index) =>
      <path key={index} d={`M ${points.map((p) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" L ")}`} />)}</g>}
    <g transform={FLIP} className="writing-ink">
      {fading.map((one) => <path key={one.id} d={one.d} className={one.accepted ? "accepted" : "refused"} />)}
      {live && <path d={inkOutline(live.points, live.simulated, false)} />}
    </g>
    {shownNumbers.map((stroke) => {
      const at = stroke.median[0] ? toPage(stroke.median[0]) : null;
      return at && <g key={stroke.index} className="writing-number" transform={`translate(${at.x} ${at.y})`} aria-hidden="true">
        <circle r="34" /><text dy="12">{stroke.index + 1}</text>
      </g>;
    })}
    {pulseAt && <circle key={`pulse-${pulse!.key}`} className="writing-pulse" cx={pulseAt.x} cy={pulseAt.y} r="30" />}
  </svg>;
}
