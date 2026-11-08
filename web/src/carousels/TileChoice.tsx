/**
 * Spike variant 8: no row at all. The chosen picture with its name and sentence, ‹ › either side to
 * step through the catalogue, and a press on the picture (or **Change…**) to see every choice at once
 * in the grid the dialog already has. Nothing moves under a finger, so nothing can land in the wrong
 * place; the price is that the other choices are one tap away rather than in view.
 */

import { BackIcon, ForwardIcon } from "../icons";
import { openingOf, type RowProps } from "./shared";

export function TileChoice({ label, choices, value, onChange, idle, onAll }: RowProps) {
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  const at = index >= 0 ? index : openingOf(choices, value);
  const step = (to: number) => onChange(choices[Math.max(0, Math.min(choices.length - 1, to))].id);

  return <div className="tile-choice" role="group" aria-label={label}>
    <button type="button" className="carousel-step tile-step" aria-label={`Previous: ${label}`}
      disabled={index >= 0 && at <= 0} onClick={() => step(index >= 0 ? at - 1 : at)}><BackIcon /></button>
    <button type="button" className="tile-main" onClick={onAll} aria-label={`Change ${label}`}>
      <span className="choice-art">{chosen ? chosen.art : null}</span>
      <span className="tile-text">
        <strong>{chosen ? chosen.label : idle ?? "Nothing chosen"}</strong>
        {chosen?.about && <span>{chosen.about}</span>}
        <em>{`Change… · ${index >= 0 ? index + 1 : "–"} of ${choices.length}`}</em>
      </span>
    </button>
    <button type="button" className="carousel-step tile-step" aria-label={`Next: ${label}`}
      disabled={index >= 0 && at >= choices.length - 1} onClick={() => step(index >= 0 ? at + 1 : at)}><ForwardIcon /></button>
  </div>;
}
