/**
 * Spike variant 7: a plain scrolling strip, where scrolling only browses and a tap chooses.
 *
 * Every other row takes the picture in the middle as the choice, which is what makes a swipe that
 * stops in the wrong place choose the wrong thing. Here nothing is chosen by moving: the row scrolls
 * natively, with no snapping, and the chosen picture is outlined wherever it is. ‹ › scroll a page;
 * ← → from the keyboard step the choice and bring it into view. A mouse can drag the strip.
 */

import { useLayoutEffect, useRef, type KeyboardEvent } from "react";
import { BackIcon, ForwardIcon } from "../icons";
import { Caption, ChoiceButton, Frame, keyTarget, openingOf, useMouseDrag, type RowProps } from "./shared";

export function StripRow({ label, choices, value, onChange, idle }: RowProps) {
  const row = useRef<HTMLDivElement>(null);
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  const at = index >= 0 ? index : openingOf(choices, value);

  // Opens with the choice in the middle, without animating.
  useLayoutEffect(() => {
    const element = row.current;
    const item = element?.children[openingOf(choices, value)] as HTMLElement | undefined;
    if (element && item) element.scrollLeft = item.offsetLeft + item.offsetWidth / 2 - element.clientWidth / 2;
    // Only on opening: a choice made by a tap is already in view.
  }, []);
  useMouseDrag(row, {});

  const page = (direction: 1 | -1) => {
    const element = row.current;
    if (element) element.scrollBy({ left: direction * element.clientWidth * 0.7, behavior: "smooth" });
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const to = keyTarget(event, at, choices.length);
    if (to === null) return;
    onChange(choices[to].id);
    requestAnimationFrame(() => {
      const button = row.current?.children[to]?.querySelector("button");
      button?.focus({ preventScroll: true });
      button?.scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" });
    });
  };

  return <Frame caption={<Caption choices={choices} chosen={chosen} idle={idle} />}>
    <div className="carousel-row strip-row" ref={row} role="radiogroup" aria-label={label} onKeyDown={onKey}>
      {choices.map((choice, position) => <div key={choice.id} data-choice={choice.id} className={`carousel-item${position === index ? " on" : ""}`}>
        <ChoiceButton choice={choice} on={position === index} focusable={position === at} onClick={() => onChange(choice.id)} />
      </div>)}
    </div>
    <button type="button" className="carousel-step prev" aria-label={`Scroll back: ${label}`} onClick={() => page(-1)}><BackIcon /></button>
    <button type="button" className="carousel-step next" aria-label={`Scroll on: ${label}`} onClick={() => page(1)}><ForwardIcon /></button>
  </Frame>;
}
