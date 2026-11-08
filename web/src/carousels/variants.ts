/**
 * The carousel spike: eight ways of choosing one picture from a catalogue, tried side by side on the
 * desktop and the iPad before one is kept (`docs/plans/carousel-spike.md`).
 *
 * Which one the make dialogs use is a device-local choice, picked from the top of any make dialog or
 * from `?spike=carousel`. It is kept in local storage because Safari and the installed app on an iPad
 * keep separate storage, so each has to be able to choose for itself.
 */

import { useSyncExternalStore } from "react";

export const VARIANTS = [
  { id: "embla", label: "1 · Embla (as shipped)", about: "Today's row, unchanged: the baseline." },
  { id: "embla-fixed", label: "2 · Embla, fixed release", about: "Today's row, but letting go lands where your finger or the momentum says, not next to where you started." },
  { id: "native", label: "3 · Native snapping row", about: "The browser's own scrolling and momentum; it stops on the nearest picture." },
  { id: "native-one", label: "4 · Native, one per swipe", about: "The browser's own scrolling, stopping on the next picture at most, however fast the swipe." },
  { id: "swiper", label: "5 · Swiper, free with snap", about: "Swiper's physics: momentum as far as you throw it, then it settles on a picture." },
  { id: "swiper-step", label: "6 · Swiper, paged", about: "Swiper moving one picture per swipe or per turn of the wheel." },
  { id: "strip", label: "7 · Plain strip, tap to choose", about: "A row that only scrolls; nothing is chosen until you tap a picture." },
  { id: "tile", label: "8 · Chosen picture + Change", about: "No row: the choice, ‹ › to step, and Change… for every picture at once." }
] as const;

export type CarouselVariant = (typeof VARIANTS)[number]["id"];

const KEY = "acervo.spike.carousel";
const DEFAULT: CarouselVariant = "embla-fixed";
const listeners = new Set<() => void>();

function isVariant(value: unknown): value is CarouselVariant {
  return VARIANTS.some((variant) => variant.id === value);
}

export function carouselVariant(): CarouselVariant {
  try {
    const stored = localStorage.getItem(KEY);
    return isVariant(stored) ? stored : DEFAULT;
  } catch { return DEFAULT; }
}

export function setCarouselVariant(value: CarouselVariant): void {
  try { localStorage.setItem(KEY, value); } catch { /* a preference, not data */ }
  listeners.forEach((listener) => listener());
}

export function useCarouselVariant(): CarouselVariant {
  return useSyncExternalStore(
    (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    carouselVariant,
    () => DEFAULT
  );
}
