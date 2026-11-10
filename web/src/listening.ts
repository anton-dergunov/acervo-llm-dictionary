import { useSyncExternalStore } from "react";
import { acquire, release as releasePicture } from "./media";

/**
 * Which of the two players is the one that is playing — a loop or a story — and the lock screen,
 * which speaks for it.
 *
 * Both players stop each other (`pronunciation.registerPlayer`), but stopping is pausing: a paused
 * loop is still loaded, its bar still says what it is. What decides which one the bar, the rail's
 * card, the chip and the lock screen describe is **the one started last**, and this is where that is
 * kept. It is also why the lock screen lives here rather than in either player: each claims it when it
 * starts, and lets go only of its own claim. A loop's handlers used to stay on the lock screen while a
 * story played, so its play button there started the loop again.
 */

export type Listening = "loop" | "story";

let owner: Listening | null = null;
const listeners = new Set<() => void>();
/** The picture on the lock screen, held as a blob URL until it is replaced. */
let artwork: string | null = null;

function announce(): void { listeners.forEach((listener) => listener()); }

export function listening(): Listening | null { return owner; }

export function useListening(): Listening | null {
  return useSyncExternalStore((listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; }, listening);
}

export interface LockScreen {
  title: string;
  artist: string;
  /** A stored picture's reference, shown as the artwork once it has been read. */
  picture?: string | null;
  play(): void;
  pause(): void;
  previous(): void;
  next(): void;
  seek?(seconds: number): void;
}

/** Become the one playing, and say so on the lock screen. Called by a player whenever it starts. */
export function claim(kind: Listening, screen: LockScreen): void {
  if (owner !== kind) { owner = kind; announce(); }
  const media = typeof navigator !== "undefined" ? navigator.mediaSession : undefined;
  if (!media) return;
  const metadata = (art: string | null) => new MediaMetadata({
    title: screen.title, artist: screen.artist, album: "Acervo",
    ...(art ? { artwork: [{ src: art, sizes: "512x512" }] } : {})
  });
  try {
    media.metadata = metadata(null);
    media.setActionHandler("play", () => screen.play());
    media.setActionHandler("pause", () => screen.pause());
    media.setActionHandler("previoustrack", () => screen.previous());
    media.setActionHandler("nexttrack", () => screen.next());
    media.setActionHandler("seekto", screen.seek
      ? (event) => { if (event.seekTime !== undefined) screen.seek!(event.seekTime); }
      : null);
  } catch { /* an older browser, or one that refuses a handler it does not implement */ }
  showPicture(screen.picture ?? null, () => metadata);
}

function showPicture(reference: string | null, metadata: () => (art: string | null) => MediaMetadata): void {
  if (artwork) { releasePicture(artwork); artwork = null; }
  if (!reference) return;
  artwork = reference;
  void acquire(reference).then((url) => {
    if (artwork !== reference) { releasePicture(reference); return; }
    try { navigator.mediaSession.metadata = metadata()(url); } catch { /* as above */ }
  }).catch(() => { if (artwork === reference) artwork = null; });
}

/**
 * Let go — but only if this player is still the one playing. A loop stopped after a story started
 * must not take the story's lock screen with it.
 */
export function release(kind: Listening): void {
  if (owner !== kind) return;
  owner = null;
  announce();
  if (artwork) { releasePicture(artwork); artwork = null; }
  const media = typeof navigator !== "undefined" ? navigator.mediaSession : undefined;
  if (!media) return;
  try {
    media.metadata = null;
    for (const action of ["play", "pause", "previoustrack", "nexttrack", "seekto"] as const) {
      media.setActionHandler(action, null);
    }
  } catch { /* as above */ }
}

export function resetListeningForTests(): void { owner = null; artwork = null; announce(); }
