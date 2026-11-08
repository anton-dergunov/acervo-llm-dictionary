/**
 * What every row in the carousel spike shares: the props, the look of a picture by its distance from
 * the middle, the caption under the row, the ‹ › buttons and the keys.
 */

import { useEffect, useRef, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import type { CatalogueChoice } from "../ChoiceCarousel";
import { BackIcon, ForwardIcon } from "../icons";

export interface RowProps {
  label: string;
  choices: CatalogueChoice[];
  /** The chosen id, or null when the choice was made elsewhere (a saved piece of music). */
  value: string | null;
  onChange(id: string): void;
  /** Said under the row while nothing in it is chosen. */
  idle?: string;
  /** Shows the whole catalogue as a grid, as the dialog's All link does. */
  onAll?(): void;
}

/** Where a row opens: on the choice, else on the middle of the list, where its default sits. */
export function openingOf(choices: CatalogueChoice[], value: string | null): number {
  const index = choices.findIndex((choice) => choice.id === value);
  return index >= 0 ? index : Math.floor((choices.length - 1) / 2);
}

/** The size and opacity of a picture `distance` pictures from the middle. */
export function look(distance: number): { scale: number; opacity: number } {
  if (distance <= 1) return { scale: 1.2 - 0.2 * distance, opacity: 1 };
  return { scale: Math.max(0.72, 1 - 0.16 * (distance - 1)), opacity: Math.max(0.35, 1 - 0.32 * (distance - 1)) };
}

/** Writes each slide's size from its distance to the middle of `frame`; returns the nearest one. */
export function paint(frame: HTMLElement | null, slides: ArrayLike<HTMLElement>): number {
  if (!frame) return -1;
  const box = frame.getBoundingClientRect();
  const centre = box.left + box.width / 2;
  let nearest = -1;
  let least = Infinity;
  Array.from(slides).forEach((slide, position) => {
    const rect = slide.getBoundingClientRect();
    const distance = Math.abs(rect.left + rect.width / 2 - centre) / (rect.width || 1);
    if (distance < least) { least = distance; nearest = position; }
    const { scale, opacity } = look(distance);
    slide.style.setProperty("--scale", scale.toFixed(3));
    slide.style.setProperty("--fade", opacity.toFixed(3));
  });
  return nearest;
}

/** The position a key moves to from `at`, or null when the key is not one of the row's. */
export function keyTarget(event: KeyboardEvent, at: number, count: number): number | null {
  const moves: Record<string, number> = { ArrowRight: at + 1, ArrowDown: at + 1, ArrowLeft: at - 1, ArrowUp: at - 1, Home: 0, End: count - 1 };
  if (!(event.key in moves)) return null;
  event.preventDefault();
  return Math.max(0, Math.min(count - 1, moves[event.key]));
}

export function ChoiceButton({ choice, on, focusable, onClick }: {
  choice: CatalogueChoice; on: boolean; focusable: boolean; onClick(): void;
}) {
  return <button
    type="button" role="radio" aria-checked={on} tabIndex={focusable ? 0 : -1}
    aria-label={choice.label} aria-description={choice.about} title={on ? undefined : choice.label}
    onClick={onClick}
  ><span className="choice-art">{choice.art}</span></button>;
}

export function Steps({ label, at, count, onStep }: { label: string; at: number; count: number; onStep(to: number): void }) {
  return <>
    <button type="button" className="carousel-step prev" aria-label={`Previous: ${label}`}
      hidden={at <= 0} onClick={() => onStep(at - 1)}><BackIcon /></button>
    <button type="button" className="carousel-step next" aria-label={`Next: ${label}`}
      hidden={at >= count - 1} onClick={() => onStep(at + 1)}><ForwardIcon /></button>
  </>;
}

export function Caption({ choices, chosen, idle }: { choices: CatalogueChoice[]; chosen: CatalogueChoice | null; idle?: string }) {
  const about = choices.some((choice) => choice.about);
  return <div className={`carousel-caption${about ? " described" : ""}`} aria-hidden="true">
    {chosen
      ? <><strong>{chosen.label}</strong>{chosen.about && <span>{chosen.about}</span>}</>
      : <span>{idle}</span>}
  </div>;
}

export function Frame({ children, caption }: { children: ReactNode; caption: ReactNode }) {
  return <div className="carousel"><div className="carousel-frame">{children}</div>{caption}</div>;
}

/**
 * Lets a mouse drag a native scrolling row, which a browser does not do by itself: the row follows
 * the pointer, and a click after a drag is swallowed so letting go does not also choose. Touch and
 * pens are left to the browser. `onEnd` is told when a drag ends.
 */
export function useMouseDrag(row: RefObject<HTMLElement | null>, handlers: { onStart?(): void; onEnd?(): void }) {
  const latest = useRef(handlers);
  latest.current = handlers;
  useEffect(() => {
    const element = row.current;
    if (!element) return;
    let start: { x: number; left: number } | null = null;
    let dragged = false;
    const down = (event: PointerEvent) => {
      if (event.pointerType !== "mouse" || event.button !== 0) return;
      start = { x: event.clientX, left: element.scrollLeft };
      dragged = false;
    };
    const move = (event: PointerEvent) => {
      if (!start) return;
      const dx = event.clientX - start.x;
      if (!dragged && Math.abs(dx) < 5) return;
      if (!dragged) {
        dragged = true;
        element.classList.add("dragging");
        latest.current.onStart?.();
      }
      element.scrollLeft = start.left - dx;
    };
    const up = () => {
      if (!start) return;
      start = null;
      if (dragged) {
        element.classList.remove("dragging");
        latest.current.onEnd?.();
      }
    };
    const click = (event: MouseEvent) => {
      if (dragged) { event.stopPropagation(); event.preventDefault(); dragged = false; }
    };
    element.addEventListener("pointerdown", down);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    element.addEventListener("click", click, true);
    return () => {
      element.removeEventListener("pointerdown", down);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      element.removeEventListener("click", click, true);
    };
  }, [row]);
}
