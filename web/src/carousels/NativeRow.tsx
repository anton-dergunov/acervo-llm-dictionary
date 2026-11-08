/**
 * Spike variants 3 and 4: a native scrolling row with CSS scroll snapping, the middle picture chosen.
 *
 * The browser does all the moving — the finger, the momentum, the wheel, the snap — and the code only
 * reads where the row is: whatever is nearest the middle is the choice, as it passes. **Nothing here
 * scrolls the row in answer to a scroll.** Only a tap, a key, an arrow or a choice made in the grid
 * glides it, and a finger or a wheel that arrives during the glide takes over at once. The native row
 * tried before this one also steered the row back to its choice after the user had moved it, and
 * the two then fought.
 *
 * `one` adds `scroll-snap-stop: always`: a swipe or a turn of the wheel stops at the next picture,
 * however fast it was.
 *
 * A mouse cannot drag a native scroller, so `useMouseDrag` lets it; snapping is off during the drag
 * and the row glides to the nearest picture when the button is let go.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { Caption, ChoiceButton, Frame, Steps, keyTarget, openingOf, paint, useMouseDrag, type RowProps } from "./shared";

const SETTLE_MS = 160;

function calm(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function NativeRow({ label, choices, value, onChange, idle, one }: RowProps & { one: boolean }) {
  const row = useRef<HTMLDivElement>(null);
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  const [opening] = useState(() => openingOf(choices, value));
  const [middle, setMiddle] = useState(opening);
  const centre = useRef(opening);
  const at = index >= 0 ? index : middle;
  const moved = useRef(false);
  const steering = useRef(false);
  const following = useRef(false);
  const settleTimer = useRef<number | undefined>(undefined);
  const latest = useRef({ index, choices, onChange });
  latest.current = { index, choices, onChange };

  const slides = useCallback(() => row.current?.querySelectorAll<HTMLElement>(":scope > .carousel-item") ?? [], []);
  const leftFor = useCallback((position: number): number | null => {
    const element = row.current;
    const item = slides()[position];
    if (!element || !item) return null;
    return item.offsetLeft + item.offsetWidth / 2 - element.clientWidth / 2;
  }, [slides]);
  const glide = useCallback((position: number) => {
    const left = leftFor(position);
    if (left === null || !row.current) return;
    steering.current = true;
    row.current.scrollTo({ left, behavior: calm() ? "auto" : "smooth" });
  }, [leftFor]);

  useLayoutEffect(() => {
    const left = leftFor(opening);
    if (left !== null && row.current) row.current.scrollLeft = left;
    paint(row.current, slides());
  }, [leftFor, opening, slides]);

  useEffect(() => {
    const element = row.current;
    if (!element) return;
    let frame = 0;
    const settled = () => { steering.current = false; };
    const scroll = () => {
      window.clearTimeout(settleTimer.current);
      settleTimer.current = window.setTimeout(settled, SETTLE_MS);
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const nearest = paint(element, slides());
        if (nearest < 0) return;
        centre.current = nearest;
        setMiddle(nearest);
        const { index: now, choices: list, onChange: change } = latest.current;
        if (!steering.current && moved.current && nearest !== now && list[nearest]) {
          following.current = true;
          change(list[nearest].id);
        }
      });
    };
    const touched = () => { moved.current = true; steering.current = false; };
    element.addEventListener("scroll", scroll, { passive: true });
    element.addEventListener("scrollend", settled);
    element.addEventListener("touchstart", touched, { passive: true });
    element.addEventListener("wheel", touched, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer.current);
      element.removeEventListener("scroll", scroll);
      element.removeEventListener("scrollend", settled);
      element.removeEventListener("touchstart", touched);
      element.removeEventListener("wheel", touched);
    };
  }, [slides]);

  useMouseDrag(row, {
    onStart: () => { moved.current = true; steering.current = false; },
    onEnd: () => {
      const element = row.current;
      if (!element) return;
      const nearest = paint(element, slides());
      const left = leftFor(nearest);
      if (left !== null) element.scrollTo({ left, behavior: calm() ? "auto" : "smooth" });
    }
  });

  // A choice made by a tap, a key, an arrow or the grid: the row glides to it. One the row's own
  // movement made is already where the row is.
  useEffect(() => {
    if (following.current) { following.current = false; return; }
    if (index >= 0 && centre.current !== index) glide(index);
  }, [glide, index, choices.map((choice) => choice.id).join()]);

  const choose = (position: number, focus = false) => {
    const { choices: list, onChange: change } = latest.current;
    const next = Math.max(0, Math.min(list.length - 1, position));
    moved.current = true;
    if (list[next].id === value) glide(next);
    change(list[next].id);
    if (focus) requestAnimationFrame(() => slides()[next]?.querySelector("button")?.focus({ preventScroll: true }));
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const to = keyTarget(event, at, choices.length);
    if (to !== null) choose(to, true);
  };

  return <Frame caption={<Caption choices={choices} chosen={chosen} idle={idle} />}>
    <div className={`carousel-row native-row${one ? " one" : ""}`} ref={row} role="radiogroup" aria-label={label} onKeyDown={onKey}>
      {choices.map((choice, position) => <div key={choice.id} data-choice={choice.id} className={`carousel-item${position === index ? " on" : ""}`}>
        <ChoiceButton choice={choice} on={position === index} focusable={position === at} onClick={() => choose(position)} />
      </div>)}
    </div>
    <Steps label={label} at={at} count={choices.length} onStep={(to) => choose(to)} />
  </Frame>;
}
