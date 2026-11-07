/**
 * One choice from a catalogue, as pictures: a carousel with the choice in the middle, and every
 * choice as a grid.
 *
 * The make dialogs choose a style of music, a kind of story and a style of picture this way. Each
 * catalogue is long — fourteen styles of music, thirteen kinds of story, twenty-three styles of
 * picture — so the dialog shows one row whatever its length.
 *
 * **The choice is the picture in the middle.** It is drawn larger than its neighbours, with its name
 * and the sentence that says what it is under the row, and the pictures either side shrink and fade
 * with their distance from it. A row whose ends simply stop does not say that it scrolls; one whose
 * middle is the point, with pictures fading off both sides, does. The choice a dialog opens on —
 * Surprise me, To suit the story — is the middle of its list (`centred`), so the row opens with
 * pictures on both sides rather than an empty half; the grid keeps it first. Moving the row is choosing:
 * - a swipe chooses as it goes: whichever picture is in the middle is the choice, while the finger
 *   is still moving, and the row is not pulled back to it;
 * - a sideways wheel steps one picture for each notch's worth of travel. It does not scroll the row
 *   itself: a wheel scrolling a snapping row that is also gliding to its choice pulled it back and
 *   forth on every small turn;
 * - tapping a picture brings it to the middle;
 * - the ‹ › buttons on the row's edges step one picture, for a desktop with no sideways wheel;
 * - the row is one stop for the keyboard, and ← → step, as in any radio group.
 *
 * The size of each picture is a transform written as the row scrolls, never its layout size, so the
 * row and the dialog keep their size while it moves. **All** (the dialog's link above the row) shows
 * the catalogue as a grid in place of the dialog's body (`MakeDialog`), with every sentence at once.
 */

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { BackIcon, ForwardIcon } from "./icons";

export interface CatalogueChoice {
  id: string;
  label: string;
  /** The sentence that says what it is: under the row when chosen, and in the grid. */
  about?: string;
  art: ReactNode;
}

/** How long after the last scroll event a row counts as at rest, where `scrollend` is missing. */
const SETTLE_MS = 120;
/** Sideways wheel travel that steps one picture, and how long a pause starts the count again. */
const WHEEL_STEP = 50;
const WHEEL_PAUSE_MS = 200;

/** A list with its default choice in the middle, so a carousel opening on it has both sides filled. */
export function centred<T>(first: T, rest: T[]): T[] {
  const half = Math.floor(rest.length / 2);
  return [...rest.slice(0, half), first, ...rest.slice(half)];
}

/** The size and opacity of a picture `distance` pictures from the middle. */
function look(distance: number): { scale: number; opacity: number } {
  if (distance <= 1) return { scale: 1.3 - 0.3 * distance, opacity: 1 };
  return { scale: Math.max(0.7, 1 - 0.18 * (distance - 1)), opacity: Math.max(0.35, 1 - 0.32 * (distance - 1)) };
}

function calm(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function ChoiceCarousel({ label, choices, value, onChange, idle }: {
  label: string;
  choices: CatalogueChoice[];
  /** The chosen id, or null when the choice was made elsewhere (a saved piece of music). */
  value: string | null;
  onChange(id: string): void;
  /** Said under the row while nothing in it is chosen. */
  idle?: string;
}) {
  const row = useRef<HTMLDivElement>(null);
  const settled = useRef<number | undefined>(undefined);
  const painting = useRef(0);
  /** Whether the row has been moved or chosen in since it appeared, as against only placed. */
  const placed = useRef(false);
  /** A finger is moving the row: what passes the middle is chosen, and the row is not steered. */
  const byHand = useRef(false);
  /** The choice came from the row's own position, so the row is already where it should be. */
  const following = useRef(false);
  /** Where the wheel has stepped to before the dialog has drawn it, and its unspent travel. */
  const wheel = useRef<{ travel: number; pause?: number; target: number | null }>({ travel: 0, target: null });
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  // Which picture is in the middle while nothing here is chosen, so the arrows step from it.
  const [middle, setMiddle] = useState(0);
  const at = index >= 0 ? index : middle;
  const latest = useRef({ at, index, choices, onChange });
  latest.current = { at, index, choices, onChange };

  const items = () => [...(row.current?.querySelectorAll<HTMLElement>("[data-choice]") ?? [])];

  /** Writes each picture's size from its distance to the middle of the row. */
  const paint = () => {
    const strip = row.current;
    if (!strip) return;
    const centre = strip.scrollLeft + strip.clientWidth / 2;
    for (const item of items()) {
      const step = item.offsetWidth + 28;
      const distance = Math.abs(item.offsetLeft + item.offsetWidth / 2 - centre) / (step || 1);
      const { scale, opacity } = look(distance);
      item.style.setProperty("--scale", scale.toFixed(3));
      item.style.setProperty("--fade", opacity.toFixed(3));
    }
  };

  /** The picture nearest the middle of the row as it is now. */
  const nearest = (): number => {
    const strip = row.current;
    if (!strip) return -1;
    const centre = strip.scrollLeft + strip.clientWidth / 2;
    let best = -1;
    let gap = Infinity;
    items().forEach((item, position) => {
      const away = Math.abs(item.offsetLeft + item.offsetWidth / 2 - centre);
      if (away < gap) { gap = away; best = position; }
    });
    return best;
  };

  /** Chooses what a finger has brought to the middle, without steering the row to it. */
  const follow = () => {
    const found = nearest();
    const { index: now, choices: list, onChange: change } = latest.current;
    if (found < 0) return;
    setMiddle(found);
    if (found !== now) {
      following.current = true;
      change(list[found].id);
    }
  };

  // Brings the choice to the middle: at once when the row first appears, smoothly afterwards, and
  // not at all when the row's own movement made the choice.
  useEffect(() => {
    wheel.current.target = null;
    if (following.current) { following.current = false; paint(); return; }
    const strip = row.current;
    const item = index >= 0 ? items()[index] : null;
    if (strip && item) {
      const left = item.offsetLeft + item.offsetWidth / 2 - strip.clientWidth / 2;
      if (Math.abs(strip.scrollLeft - left) > 1) {
        strip.scrollTo({ left, behavior: placed.current && !calm() ? "smooth" : "auto" });
      }
    }
    paint();
  }, [value, choices.map((choice) => choice.id).join()]);

  const choose = (position: number, focus = false) => {
    const { choices: list, onChange: change } = latest.current;
    const next = Math.max(0, Math.min(list.length - 1, position));
    placed.current = true;
    // A choice made by a tap, a key, an arrow or the wheel owns the movement that follows it.
    byHand.current = false;
    wheel.current.target = next;
    change(list[next].id);
    if (focus) requestAnimationFrame(() => items()[next]?.querySelector("button")?.focus({ preventScroll: true }));
  };

  useEffect(() => {
    const strip = row.current;
    if (!strip) return;
    const onScroll = () => {
      cancelAnimationFrame(painting.current);
      painting.current = requestAnimationFrame(() => {
        paint();
        if (byHand.current) follow();
      });
      window.clearTimeout(settled.current);
      settled.current = window.setTimeout(onEnd, SETTLE_MS);
    };
    const onEnd = () => {
      window.clearTimeout(settled.current);
      if (byHand.current) follow();
      byHand.current = false;
    };
    const onTouch = () => { placed.current = true; byHand.current = true; };
    const onPointer = (event: PointerEvent) => { if (event.pointerType !== "mouse") onTouch(); };
    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
      event.preventDefault();
      const state = wheel.current;
      // Lines (Firefox) or pages, as pixels.
      const scale = event.deltaMode === 1 ? 40 : event.deltaMode === 2 ? strip.clientWidth : 1;
      state.travel += event.deltaX * scale;
      window.clearTimeout(state.pause);
      state.pause = window.setTimeout(() => { state.travel = 0; }, WHEEL_PAUSE_MS);
      let steps = 0;
      while (Math.abs(state.travel) >= WHEEL_STEP) {
        const sign = Math.sign(state.travel);
        steps += sign;
        state.travel -= sign * WHEEL_STEP;
      }
      if (steps) choose((state.target ?? latest.current.at) + steps);
    };
    strip.addEventListener("scroll", onScroll, { passive: true });
    strip.addEventListener("scrollend", onEnd);
    strip.addEventListener("touchstart", onTouch, { passive: true });
    strip.addEventListener("pointerdown", onPointer);
    strip.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("resize", paint);
    return () => {
      strip.removeEventListener("scroll", onScroll);
      strip.removeEventListener("scrollend", onEnd);
      strip.removeEventListener("touchstart", onTouch);
      strip.removeEventListener("pointerdown", onPointer);
      strip.removeEventListener("wheel", onWheel);
      window.removeEventListener("resize", paint);
      window.clearTimeout(settled.current);
      window.clearTimeout(wheel.current.pause);
      cancelAnimationFrame(painting.current);
    };
  }, []);

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = { ArrowRight: at + 1, ArrowDown: at + 1, ArrowLeft: at - 1, ArrowUp: at - 1, Home: 0, End: choices.length - 1 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    choose(moves[event.key], true);
  };

  const about = choices.some((choice) => choice.about);
  return <div className="carousel">
    <div className="carousel-frame">
      <div className="carousel-row" ref={row} role="radiogroup" aria-label={label} onKeyDown={onKey}>
        {choices.map((choice, position) => <div
          key={choice.id} data-choice={choice.id} className={`carousel-item${position === index ? " on" : ""}`}
        >
          <button
            type="button" role="radio" aria-checked={position === index} tabIndex={position === at ? 0 : -1}
            aria-label={choice.label} aria-description={choice.about} title={position === index ? undefined : choice.label}
            onClick={() => choose(position)}
          ><span className="choice-art">{choice.art}</span></button>
        </div>)}
      </div>
      <button type="button" className="carousel-step prev" aria-label={`Previous: ${label}`}
        hidden={at <= 0} onClick={() => choose(at - 1)}><BackIcon /></button>
      <button type="button" className="carousel-step next" aria-label={`Next: ${label}`}
        hidden={at >= choices.length - 1} onClick={() => choose(at + 1)}><ForwardIcon /></button>
    </div>
    <div className={`carousel-caption${about ? " described" : ""}`} aria-hidden="true">
      {chosen
        ? <><strong>{chosen.label}</strong>{chosen.about && <span>{chosen.about}</span>}</>
        : <span>{idle}</span>}
    </div>
  </div>;
}

/** Every choice at once, with what each one is. Choosing one is the whole of what the grid is for. */
export function ChoiceGrid({ label, choices, value, onChange }: {
  label: string;
  choices: CatalogueChoice[];
  value: string | null;
  onChange(id: string): void;
}) {
  return <div className="choice-grid" role="radiogroup" aria-label={label}>
    {choices.map((choice) => {
      const on = choice.id === value;
      return <div key={choice.id} className={`choice${on ? " on" : ""}`}>
        <button type="button" role="radio" aria-checked={on} onClick={() => onChange(choice.id)}>
          <span className="choice-art">{choice.art}</span>
          <span className="choice-name">{choice.label}</span>
          {choice.about && <span className="choice-about">{choice.about}</span>}
        </button>
      </div>;
    })}
  </div>;
}

/** The link above a carousel that shows its whole catalogue. */
export function AllChoices({ count, label, onOpen }: { count: number; label: string; onOpen(): void }) {
  return <button type="button" className="make-more" onClick={onOpen} aria-label={`All ${count}: ${label}`}>
    All {count} ›
  </button>;
}
