/**
 * Spike variants 5 and 6: the row on Swiper (`swiper`, MIT), a second, independent physics engine.
 *
 * `free` is Swiper's free mode with sticky snapping: a throw carries as far as its momentum, then the
 * row settles on a picture, and the wheel moves it one to one before settling the same way. `step` is
 * Swiper's paged mode: a swipe lands on the nearest picture, a short flick moves one, and a turn of the
 * wheel moves one per gesture. In both, the picture nearest the middle is chosen as it passes, as in
 * every row of the spike, and a tap, a key or an arrow glides the row without choosing what it passes.
 *
 * Swiper animates with CSS transitions, so while one runs the pictures are painted every frame from
 * where they really are, not from where the transition is going.
 */

import Swiper from "swiper";
import { FreeMode, Mousewheel } from "swiper/modules";
import "swiper/css";
import "swiper/css/free-mode";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Caption, ChoiceButton, Frame, Steps, keyTarget, openingOf, paint, type RowProps } from "./shared";

export function SwiperRow({ label, choices, value, onChange, idle, mode }: RowProps & { mode: "free" | "step" }) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Swiper | null>(null);
  const index = choices.findIndex((choice) => choice.id === value);
  const chosen = index >= 0 ? choices[index] : null;
  const [opening] = useState(() => openingOf(choices, value));
  const [middle, setMiddle] = useState(opening);
  const centre = useRef(opening);
  const at = index >= 0 ? index : middle;
  const moved = useRef(false);
  const steering = useRef(false);
  const following = useRef(false);
  const latest = useRef({ index, choices, onChange });
  latest.current = { index, choices, onChange };

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    let frame = 0;
    let animating = false;
    const update = () => {
      const nearest = paint(element, element.querySelectorAll<HTMLElement>(".carousel-item"));
      if (nearest < 0) return;
      centre.current = nearest;
      setMiddle(nearest);
      const { index: now, choices: list, onChange: change } = latest.current;
      if (!steering.current && moved.current && nearest !== now && list[nearest]) {
        following.current = true;
        change(list[nearest].id);
      }
    };
    const loop = () => { update(); if (animating) frame = requestAnimationFrame(loop); };
    const touched = () => { moved.current = true; steering.current = false; };
    const swiper = new Swiper(element, {
      modules: [FreeMode, Mousewheel],
      slidesPerView: "auto",
      centeredSlides: true,
      initialSlide: opening,
      speed: 320,
      threshold: 5,
      grabCursor: true,
      freeMode: mode === "free" ? { enabled: true, sticky: true, momentumRatio: 0.6, momentumVelocityRatio: 0.7 } : { enabled: false },
      mousewheel: { enabled: true, forceToAxis: true, thresholdDelta: mode === "step" ? 6 : null },
      on: {
        setTranslate: () => update(),
        transitionStart: () => { animating = true; cancelAnimationFrame(frame); frame = requestAnimationFrame(loop); },
        transitionEnd: () => { animating = false; steering.current = false; update(); },
        touchStart: touched,
        scroll: touched
      }
    });
    instance.current = swiper;
    update();
    return () => {
      cancelAnimationFrame(frame);
      instance.current = null;
      swiper.destroy(true, true);
    };
  }, [mode, opening]);

  useEffect(() => {
    if (following.current) { following.current = false; return; }
    const swiper = instance.current;
    if (swiper && index >= 0 && centre.current !== index) {
      steering.current = true;
      swiper.slideTo(index);
    }
  }, [index, choices.map((choice) => choice.id).join()]);

  const choose = (position: number, focus = false) => {
    const { choices: list, onChange: change } = latest.current;
    const next = Math.max(0, Math.min(list.length - 1, position));
    moved.current = true;
    if (list[next].id === value && centre.current !== next) { steering.current = true; instance.current?.slideTo(next); }
    change(list[next].id);
    if (focus) requestAnimationFrame(() => container.current?.querySelectorAll(".carousel-item")[next]?.querySelector("button")?.focus({ preventScroll: true }));
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const to = keyTarget(event, at, choices.length);
    if (to !== null) choose(to, true);
  };

  return <Frame caption={<Caption choices={choices} chosen={chosen} idle={idle} />}>
    <div className="carousel-row swiper swiper-row" ref={container}>
      <div className="swiper-wrapper" role="radiogroup" aria-label={label} onKeyDown={onKey}>
        {choices.map((choice, position) => <div key={choice.id} data-choice={choice.id} className={`swiper-slide carousel-item${position === index ? " on" : ""}`}>
          <ChoiceButton choice={choice} on={position === index} focusable={position === at} onClick={() => choose(position)} />
        </div>)}
      </div>
    </div>
    <Steps label={label} at={at} count={choices.length} onStep={(to) => choose(to)} />
  </Frame>;
}
