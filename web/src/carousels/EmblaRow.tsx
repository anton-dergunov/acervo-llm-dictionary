/**
 * Spike variants 1 and 2: the row as shipped on Embla, and the same row with `skipSnaps`.
 *
 * With Embla's default `skipSnaps: false`, a release fast enough to count as a flick goes to the
 * picture next to the one the drag *started* on (`DragHandler.allowedForce`), so dragging past three
 * pictures and letting go jumps back to the first one's neighbour. The wheel plugin fakes a drag, so
 * a turn of the wheel takes the same path. `skipSnaps: true` lets the release land where the finger
 * and its momentum say.
 */

import useEmblaCarousel from "embla-carousel-react";
import { WheelGesturesPlugin } from "embla-carousel-wheel-gestures";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Caption, ChoiceButton, Frame, Steps, keyTarget, openingOf, paint, type RowProps } from "./shared";

export function EmblaRow({ label, choices, value, onChange, idle, skipSnaps }: RowProps & { skipSnaps: boolean }) {
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  const [opening] = useState(() => openingOf(choices, value));
  const [viewport, api] = useEmblaCarousel(
    { align: "center", containScroll: false, startIndex: opening, duration: 22, skipSnaps, watchResize: typeof ResizeObserver === "function" },
    [WheelGesturesPlugin()]
  );
  const [middle, setMiddle] = useState(opening);
  const at = index >= 0 ? index : middle;
  const moved = useRef(false);
  const steering = useRef(false);
  const following = useRef(false);
  const latest = useRef({ index, choices, onChange });
  latest.current = { index, choices, onChange };

  const repaint = useCallback((): number => api ? paint(api.rootNode(), api.slideNodes()) : -1, [api]);

  useEffect(() => {
    if (!api) return;
    const follow = (found: number) => {
      const { index: now, choices: list, onChange: change } = latest.current;
      if (found < 0 || !list[found]) return;
      setMiddle(found);
      if (found !== now && (now >= 0 || moved.current)) {
        following.current = true;
        change(list[found].id);
      }
    };
    const scroll = () => {
      const nearest = repaint();
      if (!steering.current && moved.current) follow(nearest);
    };
    const settle = () => { steering.current = false; follow(api.selectedScrollSnap()); };
    const touched = () => { moved.current = true; steering.current = false; };
    const frame = api.rootNode();
    api.on("scroll", scroll).on("settle", settle).on("reInit", repaint).on("pointerDown", touched);
    frame.addEventListener("wheel", touched, { passive: true });
    repaint();
    return () => {
      api.off("scroll", scroll).off("settle", settle).off("reInit", repaint).off("pointerDown", touched);
      frame.removeEventListener("wheel", touched);
    };
  }, [api, repaint]);

  useEffect(() => {
    if (following.current) { following.current = false; return; }
    if (api && index >= 0 && api.selectedScrollSnap() !== index) {
      steering.current = true;
      api.scrollTo(index);
    }
  }, [api, index, choices.map((choice) => choice.id).join()]);

  const choose = (position: number, focus = false) => {
    const { choices: list, onChange: change } = latest.current;
    const next = Math.max(0, Math.min(list.length - 1, position));
    moved.current = true;
    change(list[next].id);
    if (focus) requestAnimationFrame(() => api?.slideNodes()[next]?.querySelector("button")?.focus({ preventScroll: true }));
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const to = keyTarget(event, at, choices.length);
    if (to !== null) choose(to, true);
  };

  return <Frame caption={<Caption choices={choices} chosen={chosen} idle={idle} />}>
    <div className="carousel-row" ref={viewport}>
      <div className="carousel-track" role="radiogroup" aria-label={label} onKeyDown={onKey}>
        {choices.map((choice, position) => <div key={choice.id} data-choice={choice.id} className={`carousel-item${position === index ? " on" : ""}`}>
          <ChoiceButton choice={choice} on={position === index} focusable={position === at} onClick={() => choose(position)} />
        </div>)}
      </div>
    </div>
    <Steps label={label} at={at} count={choices.length} onStep={(to) => choose(to)} />
  </Frame>;
}
