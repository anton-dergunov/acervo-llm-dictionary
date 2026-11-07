/**
 * One choice from a catalogue, as pictures: a strip to swipe through, and every choice as a grid.
 *
 * The make dialogs choose music, a kind of story and a style of picture this way. Each catalogue is
 * long — fourteen kinds of music, thirteen of story, twenty-three styles — and a list of it was the
 * longest thing in either dialog. The strip shows a picture and a name per choice in one row that
 * keeps its height whatever the catalogue's length; its last tile, **All**, shows the grid in place
 * of the dialog's body (`MakeDialog`), where each choice also has the sentence that says what it is.
 *
 * Whatever is chosen is scrolled into view when the strip is drawn, so a choice remembered or made
 * in the grid is never off at the end of a row. A choice may carry a control of its own beside it,
 * which is how a favourite piece of music is heard before it is chosen.
 */

import { useEffect, useRef, type ReactNode } from "react";
import { GridIcon } from "./icons";

export interface StripChoice {
  id: string;
  label: string;
  /** The sentence that says what it is: the grid shows it, the strip offers it on hover. */
  about?: string;
  art: ReactNode;
  /** A mark over the picture: a favourite's star. */
  badge?: ReactNode;
  /** A control beside the choice, never inside it: a button may not hold a button. */
  extra?: ReactNode;
}

function Tile({ choice, on, onChange, wide }: {
  choice: StripChoice; on: boolean; onChange(id: string): void; wide?: boolean;
}) {
  return <div className={`choice${on ? " on" : ""}`} data-choice={choice.id}>
    <button
      type="button" role="radio" aria-checked={on} onClick={() => onChange(choice.id)}
      title={wide ? undefined : choice.about} aria-description={wide ? undefined : choice.about}
    >
      <span className="choice-art">{choice.art}{choice.badge && <span className="choice-badge">{choice.badge}</span>}</span>
      <span className="choice-name">{choice.label}</span>
      {wide && choice.about && <span className="choice-about">{choice.about}</span>}
    </button>
    {choice.extra}
  </div>;
}

export function ChoiceStrip({ label, choices, value, onChange, onAll }: {
  label: string;
  choices: StripChoice[];
  value: string;
  onChange(id: string): void;
  /** Show every choice as a grid. Left out when the strip already shows them all at a glance. */
  onAll?: () => void;
}) {
  const strip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const chosen = [...(strip.current?.querySelectorAll<HTMLElement>("[data-choice]") ?? [])]
      .find((tile) => tile.dataset.choice === value);
    if (chosen && strip.current) {
      // Scrolls the strip only: `scrollIntoView` would move the dialog and the page with it.
      const row = strip.current;
      const left = chosen.offsetLeft - row.offsetLeft;
      if (left < row.scrollLeft || left + chosen.offsetWidth > row.scrollLeft + row.clientWidth) {
        row.scrollLeft = Math.max(0, left - 12);
      }
    }
  }, [value]);
  return <div className="choice-strip" ref={strip} role="radiogroup" aria-label={label}>
    {choices.map((choice) => <Tile key={choice.id} choice={choice} on={choice.id === value} onChange={onChange} />)}
    {onAll && <div className="choice choice-all">
      <button type="button" onClick={onAll} aria-label={`All: ${label}`}>
        <span className="choice-art"><GridIcon /></span>
        <span className="choice-name">All</span>
      </button>
    </div>}
  </div>;
}

/** Every choice at once, with what each one is. Choosing one is the whole of what the grid is for. */
export function ChoiceGrid({ label, choices, value, onChange, children }: {
  label: string;
  choices: StripChoice[];
  value: string;
  onChange(id: string): void;
  /** Group headings or a note, drawn above the grid. */
  children?: ReactNode;
}) {
  return <div className="choice-grid-view">
    {children}
    <div className="choice-grid" role="radiogroup" aria-label={label}>
      {choices.map((choice) => <Tile key={choice.id} choice={choice} on={choice.id === value} onChange={onChange} wide />)}
    </div>
  </div>;
}
