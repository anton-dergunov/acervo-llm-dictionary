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
 * pictures on both sides rather than an empty half; the grid keeps it first.
 *
 * **The row is Embla** (`embla-carousel-react`, MIT), with its wheel plugin
 * (`embla-carousel-wheel-gestures`, MIT): a swipe, a drag, a sideways wheel or a trackpad moves it
 * smoothly, with momentum, and it settles with a picture in the middle. **Whatever passes the middle
 * is the choice, as it passes**, so the row and the choice never disagree. A wheel stepping one
 * picture per notch, and a native scrolling row steered to its choice, were both tried before this:
 * the first needed a precise hand, and the second could stop with one picture in the middle and
 * another chosen. A tap, ← → from the keyboard, or the ‹ › buttons on the row's edges (for a mouse
 * with no sideways wheel) choose a picture, and the row glides to it.
 *
 * The size of each picture is a transform written as the row moves, never its layout size, and the
 * caption under it has a fixed height, so the dialog keeps its size while the row moves. **All** (the
 * dialog's link above the row) shows the catalogue as a grid in place of the dialog's body
 * (`MakeDialog`), with every sentence at once.
 */

import useEmblaCarousel from "embla-carousel-react";
import { WheelGesturesPlugin } from "embla-carousel-wheel-gestures";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { BackIcon, ForwardIcon } from "./icons";

export interface CatalogueChoice {
  id: string;
  label: string;
  /** The sentence that says what it is: under the row when chosen, and in the grid. */
  about?: string;
  art: ReactNode;
}

/** A list with its default choice in the middle, so a carousel opening on it has both sides filled. */
export function centred<T>(first: T, rest: T[]): T[] {
  const half = Math.floor(rest.length / 2);
  return [...rest.slice(0, half), first, ...rest.slice(half)];
}

/** The size and opacity of a picture `distance` pictures from the middle. */
function look(distance: number): { scale: number; opacity: number } {
  if (distance <= 1) return { scale: 1.2 - 0.2 * distance, opacity: 1 };
  return { scale: Math.max(0.72, 1 - 0.16 * (distance - 1)), opacity: Math.max(0.35, 1 - 0.32 * (distance - 1)) };
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
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  // Where the row opens: on the choice, else on the middle of the list, where its default sits.
  const [opening] = useState(() => (index >= 0 ? index : Math.floor((choices.length - 1) / 2)));
  const [viewport, api] = useEmblaCarousel(
    // `watchResize` as the components that measure text do: where there is no ResizeObserver there
    // is no layout to follow (jsdom).
    { align: "center", containScroll: false, startIndex: opening, duration: 22, watchResize: typeof ResizeObserver === "function" },
    [WheelGesturesPlugin()]
  );
  // The picture in the middle, which is what the arrows and keys step from while nothing is chosen.
  const [middle, setMiddle] = useState(opening);
  const at = index >= 0 ? index : middle;
  /** Whether the row has been moved by hand; until then, a row with nothing chosen chooses nothing. */
  const moved = useRef(false);
  /** The row is gliding to a choice made elsewhere: what it passes on the way is not chosen. */
  const steering = useRef(false);
  /** The choice came from the row's own movement, so the row is already where it should be. */
  const following = useRef(false);
  const latest = useRef({ index, choices, onChange });
  latest.current = { index, choices, onChange };

  /** Writes each picture's size from its distance to the middle of the row; returns the nearest. */
  const paint = useCallback((): number => {
    const frame = api?.rootNode();
    if (!api || !frame) return -1;
    const box = frame.getBoundingClientRect();
    const centre = box.left + box.width / 2;
    let nearest = -1;
    let least = Infinity;
    api.slideNodes().forEach((slide, position) => {
      const rect = slide.getBoundingClientRect();
      const distance = Math.abs(rect.left + rect.width / 2 - centre) / (rect.width || 1);
      if (distance < least) { least = distance; nearest = position; }
      const { scale, opacity } = look(distance);
      slide.style.setProperty("--scale", scale.toFixed(3));
      slide.style.setProperty("--fade", opacity.toFixed(3));
    });
    return nearest;
  }, [api]);

  useEffect(() => {
    if (!api) return;
    /** Chooses what the row's own movement has brought to the middle, without steering the row. */
    const follow = (found: number) => {
      const { index: now, choices: list, onChange: change } = latest.current;
      if (found < 0 || !list[found]) return;
      setMiddle(found);
      if (found !== now && (now >= 0 || moved.current)) {
        following.current = true;
        change(list[found].id);
      }
    };
    // While a finger, a wheel or the momentum after them moves the row, the picture passing the
    // middle is chosen as it passes; while the row glides to a tapped choice, nothing on the way is.
    const scroll = () => {
      const nearest = paint();
      if (!steering.current && moved.current) follow(nearest);
    };
    const settle = () => {
      steering.current = false;
      follow(api.selectedScrollSnap());
    };
    const touched = () => { moved.current = true; steering.current = false; };
    const frame = api.rootNode();
    api.on("scroll", scroll).on("settle", settle).on("reInit", paint).on("pointerDown", touched);
    frame.addEventListener("wheel", touched, { passive: true });
    paint();
    return () => {
      api.off("scroll", scroll).off("settle", settle).off("reInit", paint).off("pointerDown", touched);
      frame.removeEventListener("wheel", touched);
    };
  }, [api, paint]);

  // A choice made by a tap, a key, an arrow or the grid: the row glides to it.
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
    const moves: Record<string, number> = { ArrowRight: at + 1, ArrowDown: at + 1, ArrowLeft: at - 1, ArrowUp: at - 1, Home: 0, End: choices.length - 1 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    choose(moves[event.key], true);
  };

  const about = choices.some((choice) => choice.about);
  return <div className="carousel">
    <div className="carousel-frame">
      <div className="carousel-row" ref={viewport}>
        <div className="carousel-track" role="radiogroup" aria-label={label} onKeyDown={onKey}>
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
