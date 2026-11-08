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
 * **Which row is on trial.** The row below is a spike of eight variants (`carousels/`,
 * `docs/plans/carousel-spike.md`), chosen per device from the top of any make dialog; what follows
 * describes the one shipped before it.
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

import { type ReactNode } from "react";
import { EmblaRow } from "./carousels/EmblaRow";
import { NativeRow } from "./carousels/NativeRow";
import { StripRow } from "./carousels/StripRow";
import { SwiperRow } from "./carousels/SwiperRow";
import { TileChoice } from "./carousels/TileChoice";
import type { RowProps } from "./carousels/shared";
import { useCarouselVariant, type CarouselVariant } from "./carousels/variants";
import "./carousels/spike.css";

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

const ROWS: Record<CarouselVariant, (props: RowProps) => ReactNode> = {
  "embla": (props) => <EmblaRow {...props} skipSnaps={false} />,
  "embla-fixed": (props) => <EmblaRow {...props} skipSnaps />,
  "native": (props) => <NativeRow {...props} one={false} />,
  "native-one": (props) => <NativeRow {...props} one />,
  "swiper": (props) => <SwiperRow {...props} mode="free" />,
  "swiper-step": (props) => <SwiperRow {...props} mode="step" />,
  "strip": (props) => <StripRow {...props} />,
  "tile": (props) => <TileChoice {...props} />
};

/**
 * The carousel, in whichever of the spike's variants this device chose (`carousels/variants.ts`).
 * A change of variant mounts a fresh row.
 */
export function ChoiceCarousel(props: RowProps) {
  const variant = useCarouselVariant();
  return <ChoiceRow key={variant} variant={variant} {...props} />;
}

function ChoiceRow({ variant, ...props }: RowProps & { variant: CarouselVariant }) {
  return <>{ROWS[variant](props)}</>;
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
