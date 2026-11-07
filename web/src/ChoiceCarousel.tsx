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
 * middle is the point, with pictures fading off both sides, does. Moving the row is choosing:
 * - a swipe, or a sideways wheel, chooses whichever picture comes to rest in the middle;
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
  const placed = useRef(false);
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  // Which picture is in the middle while nothing here is chosen, so the arrows step from it.
  const [middle, setMiddle] = useState(0);
  const at = index >= 0 ? index : middle;

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

  /** The picture nearest the middle once the row has come to rest. */
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

  const rest = () => {
    const found = nearest();
    if (found < 0) return;
    setMiddle(found);
    // A row at rest on the choice it already has says nothing; one moved by hand chooses. A row
    // with nothing chosen and never moved stays unchosen.
    if (found !== index && (index >= 0 || placed.current)) onChange(choices[found].id);
  };

  // Brings the choice to the middle: at once when the row first appears, smoothly afterwards.
  useEffect(() => {
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

  useEffect(() => {
    const strip = row.current;
    if (!strip) return;
    const onScroll = () => {
      cancelAnimationFrame(painting.current);
      painting.current = requestAnimationFrame(paint);
      window.clearTimeout(settled.current);
      settled.current = window.setTimeout(rest, SETTLE_MS);
    };
    const onEnd = () => { window.clearTimeout(settled.current); rest(); };
    // Anything that scrolls the row after it first appears is a person moving it, or the row
    // following a choice; before that it is only the row being placed.
    const onUser = () => { placed.current = true; };
    strip.addEventListener("scroll", onScroll, { passive: true });
    strip.addEventListener("scrollend", onEnd);
    strip.addEventListener("pointerdown", onUser);
    strip.addEventListener("wheel", onUser, { passive: true });
    strip.addEventListener("touchstart", onUser, { passive: true });
    window.addEventListener("resize", paint);
    return () => {
      strip.removeEventListener("scroll", onScroll);
      strip.removeEventListener("scrollend", onEnd);
      strip.removeEventListener("pointerdown", onUser);
      strip.removeEventListener("wheel", onUser);
      strip.removeEventListener("touchstart", onUser);
      window.removeEventListener("resize", paint);
      window.clearTimeout(settled.current);
      cancelAnimationFrame(painting.current);
    };
  });

  const choose = (position: number, focus = false) => {
    const next = Math.max(0, Math.min(choices.length - 1, position));
    placed.current = true;
    onChange(choices[next].id);
    if (focus) requestAnimationFrame(() => items()[next]?.querySelector("button")?.focus({ preventScroll: true }));
  };

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
