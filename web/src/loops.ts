/**
 * Playing a loop: the one place a track is heard, and the only audio element besides the one
 * `pronunciation.ts` owns.
 *
 * **The whole track is held in memory before a note of it plays.** The media route is behind bearer
 * auth, so its URL cannot go in an `<audio src>` — the same reason a picture is fetched as a blob —
 * and the constraint is the better design anyway: nothing touches the network during playback, which
 * is what a locked screen, a lift and a train need.
 *
 * **Keeping a track on the device is off by default**, unlike clips. A vocabulary's clips cost about
 * what its text does; one loop costs more than both. With it off a track is still held for the
 * session — pressing play twice does not download twice — it is simply not kept for tomorrow. The
 * cache is keyed on `audioRef`, which carries a digest of the bytes, so a re-render is a new
 * reference and a device holding the old one simply misses. There is no invalidation here and there
 * must not be.
 *
 * **One sound at a time.** This module stops `pronunciation.ts` and pauses every other registered
 * player before it plays, and registers its own pause with it, so a word read aloud, or a story,
 * silences the loop. The dependency runs one way: this imports that, and nothing imports this back.
 *
 * Which card is showing, which of its lines was last said and which may be drawn yet are all
 * `selectors.ts`'s, derived from the clock every frame. Nothing about the reveal is decided here, and
 * nothing about it is remembered — which is what makes dragging backwards put an answer away again.
 */

import { useSyncExternalStore } from "react";
import { AcervoApiError, backendSession } from "./api";
import { loopAutoplayEnabled, loopCacheEnabled, loopRepeatEnabled } from "./editorPreferences";
import { createMediaStore, type MediaStore } from "./mediaStore";
import { registerPlayer, silencePlayers, stop as stopSpeech } from "./pronunciation";
import { formatLabel, loopCards, type LoopTrack } from "./selectors";

let store: MediaStore = createMediaStore("loops");

/* Held for this session when the device is not keeping loops. One track, not many: they are
   megabytes each, and the case this exists for is pressing play again on what you just heard. */
let session: { reference: string; blob: Blob } | null = null;

export interface Playback {
  loopId: string | null;
  /** Where the track has got to, in seconds. Read from the element, never counted up. */
  at: number;
  duration: number;
  playing: boolean;
  loading: boolean;
  failed: string | null;
}

const EMPTY: Playback = { loopId: null, at: 0, duration: 0, playing: false, loading: false, failed: null };

let state: Playback = EMPTY;
const listeners = new Set<() => void>();

function update(partial: Partial<Playback>): void {
  state = { ...state, ...partial };
  listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };

/** Where the track is, for a caller that is not a component. `nowPlaying`'s opposite number. */
export const playback = (): Playback => state;

export function usePlayback(): Playback {
  return useSyncExternalStore(subscribe, playback);
}

/* ── the element ─────────────────────────────────────────────────────── */

let element: HTMLAudioElement | null = null;
let frame = 0;
/** The object URL the element is holding, revoked when it is replaced. */
let held: string | null = null;

/* Where the track has been asked to go and has not got to yet.
   An element does not move the instant it is told to: it reports the old `currentTime` until the
   seek lands, and for a track being loaded it reports zero. The clock below would read that back
   every frame and overwrite what was asked for — which is how tapping a word used to light the word
   before it, for as long as the blob took to arrive. While this is set it *is* the position; the
   element's own clock resumes the moment it agrees. */
let wanted: number | null = null;

/** Close enough to call a seek landed, for an element that never fires `seeked`. */
const SETTLED = 0.25;

function audio(): HTMLAudioElement {
  if (element) return element;
  element = new Audio();
  element.preload = "auto";
  element.addEventListener("ended", ended);
  element.addEventListener("pause", () => { update({ playing: false }); stopClock(); });
  element.addEventListener("play", () => { update({ playing: true }); startClock(); });
  element.addEventListener("seeked", () => { wanted = null; });
  return element;
}

/* iOS lets an element play only from inside the gesture that asked, and a track arrives after a
   fetch — so the element is started on silence first, synchronously, and the track is swapped in
   once it is in hand. `pronunciation.ts` does the same for the same reason. */
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

function prime(): void {
  const player = audio();
  if (!player.paused) return;
  try { player.src = SILENCE; void player.play()?.catch(() => undefined); }
  catch { /* jsdom, or a browser with no audio at all */ }
}

/* `timeupdate` fires about four times a second, which is enough for a clock and not enough for a
   line that has to move under a finger or a mark that follows an utterance. So the position is read
   every frame while playing, and not at all while paused. */
function startClock(): void {
  if (frame) return;
  const tick = () => {
    const player = element;
    if (!player || player.paused) { frame = 0; return; }
    if (wanted !== null && Math.abs(player.currentTime - wanted) < SETTLED) wanted = null;
    update({
      at: wanted ?? player.currentTime,
      duration: Number.isFinite(player.duration) ? player.duration : state.duration
    });
    frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
}

function stopClock(): void {
  if (frame) cancelAnimationFrame(frame);
  frame = 0;
}

/* ── what is queued ──
   The list the player moves through when Next, or Play the next one, asks for another. Set by
   whoever is showing the loops; the player keeps it so that leaving the surface does not end the
   queue — a loop goes on playing while you read a word, which is the point of it. */
let queue: LoopTrack[] = [];
let current: LoopTrack | null = null;

export function setQueue(entries: LoopTrack[]): void {
  queue = entries.filter((entry) => Boolean(entry.loop.audioRef));
}

export function queued(): LoopTrack[] { return queue; }

export function nowPlaying(): LoopTrack | null { return current; }

/* The formats' names, for the lock screen, as the generator gave them. Told by whoever asked for
   the schema; until then a format is named from its id. */
let formatNames: { id: string; label: string }[] = [];

export function nameFormats(formats: { id: string; label: string }[]): void { formatNames = formats; }

function neighbour(by: 1 | -1): LoopTrack | null {
  if (!current) return null;
  const at = queue.findIndex((entry) => entry.loop.id === current!.loop.id);
  if (at < 0) return null;
  return queue[at + by] ?? null;
}

export function hasNeighbour(by: 1 | -1): boolean { return Boolean(neighbour(by)); }

/* ── the bytes ───────────────────────────────────────────────────────── */

async function download(reference: string): Promise<Blob> {
  const answer = await fetch(backendSession.mediaFileUrl(reference), {
    headers: backendSession.mediaHeaders(), cache: "no-store"
  });
  if (!answer.ok) throw new AcervoApiError("That loop's track could not be fetched.", answer.status, "not_found");
  return answer.blob();
}

async function trackFor(reference: string): Promise<Blob> {
  if (session?.reference === reference) return session.blob;
  if (loopCacheEnabled()) {
    const kept = await store.read(reference).catch(() => null);
    if (kept) return kept.blob;
  }
  const blob = await download(reference);
  session = { reference, blob };
  if (loopCacheEnabled()) await store.save(reference, blob).catch(() => undefined);
  return blob;
}

/* ── playing ─────────────────────────────────────────────────────────── */

export async function play(track: LoopTrack, { at }: { at?: number } = {}): Promise<void> {
  const { loop } = track;
  if (!loop.audioRef) return;
  stopSpeech();
  silencePlayers(pause);
  // Read before `prime()`, which replaces `src` with silence when the element is paused: a word
  // tapped while the loop is paused is still a move within a track this device already holds.
  const resuming = current?.loop.id === loop.id && element?.src === held && held !== null;
  current = track;
  if (resuming) {
    /* Nothing to fetch and no `src` to replace, so moving is one assignment to `currentTime` and the
       store moves with it in the same tick. Fetching the blob again — which is what this used to do
       whenever `at` was given — left the element playing the old position for as long as IndexedDB
       took to answer, and the line followed the element. */
    update({ failed: null });
    if (at !== undefined) seek(at);
    await audio().play().catch(failWith);
    return;
  }
  // Before any await, so the browser still counts this as the gesture that asked.
  prime();
  wanted = at ?? 0;
  update({ loopId: loop.id, at: at ?? 0, duration: loop.durationSeconds ?? 0, loading: true, failed: null });
  try {
    const blob = await trackFor(loop.audioRef);
    const player = audio();
    if (held) URL.revokeObjectURL(held);
    held = URL.createObjectURL(blob);
    player.src = held;
    player.currentTime = at ?? 0;
    update({ loading: false });
    describe(track);
    await player.play().catch(failWith);
  } catch (error) {
    // Nothing is going to arrive at that position now, so the clock stops being overruled by it.
    wanted = null;
    update({ loading: false });
    failWith(error);
  }
}

function failWith(error: unknown): void {
  update({
    playing: false,
    failed: error instanceof AcervoApiError ? error.message : "That loop could not be played on this device."
  });
}

export function pause(): void {
  try { element?.pause(); } catch { /* nothing to stop */ }
  update({ playing: false });
  stopClock();
}

export function stop(): void {
  pause();
  current = null;
  wanted = null;
  if (held) { URL.revokeObjectURL(held); held = null; }
  if (element) element.removeAttribute("src");
  update(EMPTY);
  forgetLockScreen();
}

export function seek(seconds: number): void {
  const player = element;
  if (!player || !current) return;
  const bound = Math.max(0, Math.min(state.duration || player.duration || 0, seconds));
  wanted = bound;
  try { player.currentTime = bound; } catch { /* not seekable yet */ }
  update({ at: bound });
}

/** Back to the top of this card, unless it only just started — then to the one before. */
export function stepCard(by: 1 | -1): void {
  if (!current) return;
  const starts = loopCards(current.cues).map((card) => card.start);
  let index = -1;
  starts.forEach((start, position) => { if (state.at >= start) index = position; });
  if (by < 0 && index >= 0 && state.at - starts[index] > 3) { seek(starts[index]); return; }
  const want = index + by;
  if (want < 0) { seek(0); return; }
  if (want >= starts.length) { seek(state.duration); return; }
  seek(starts[want]);
}

export function stepLoop(by: 1 | -1): void {
  const next = neighbour(by);
  if (next) void play(next);
}

/* What happens at the end is the owner's two switches, in this order: play it again, else play the
   next one, else stop. Both are off by default — a loop that ends is a loop that ends. */
function ended(): void {
  const repeat = loopRepeatEnabled();
  if (repeat && current) { seek(0); void audio().play().catch(failWith); return; }
  if (loopAutoplayEnabled()) {
    const next = neighbour(1);
    if (next) { void play(next); return; }
  }
  update({ playing: false, at: state.duration });
  stopClock();
}

/* ── the lock screen ──
   What the phone shows, and the buttons on the headphones. The first use of MediaSession here, and
   worth it: this is the one surface in Acervo you are meant to leave running. */
function describe(track: LoopTrack): void {
  const media = navigator.mediaSession;
  if (!media) return;
  const title = track.items.slice(0, 3).map((item) => item.sourceText).join(", ");
  try {
    media.metadata = new MediaMetadata({
      title: title || "Loop",
      artist: `${formatLabel(formatNames, track.loop.format)} · ${track.items.length} words`,
      album: "Acervo"
    });
    media.setActionHandler("play", () => { void play(track); });
    media.setActionHandler("pause", () => pause());
    media.setActionHandler("previoustrack", () => stepCard(-1));
    media.setActionHandler("nexttrack", () => stepCard(1));
    media.setActionHandler("seekto", (event) => { if (event.seekTime !== undefined) seek(event.seekTime); });
  } catch { /* an older browser, or one that refuses a handler it does not implement */ }
}

/* A stopped loop leaves nothing on the lock screen: its play button would start the track again. */
function forgetLockScreen(): void {
  const media = navigator.mediaSession;
  if (!media) return;
  try {
    media.metadata = null;
    for (const action of ["play", "pause", "previoustrack", "nexttrack", "seekto"] as const) {
      media.setActionHandler(action, null);
    }
  } catch { /* an older browser, or one that refuses a handler it does not implement */ }
}

/* ── the device ──────────────────────────────────────────────────────── */

export async function forgetLoops(): Promise<void> {
  session = null;
  await store.clear().catch(() => undefined);
}

/** One track, when the loop naming it is gone. `pronunciation.ts` forgets a clip the same way. */
export async function forget(reference: string): Promise<void> {
  if (session?.reference === reference) session = null;
  await store.remove(reference).catch(() => undefined);
}

export function keptLoopBytes(): Promise<number> {
  return store.bytes().catch(() => 0);
}

export function replaceStoreForTests(replacement: MediaStore): void {
  store = replacement;
  session = null;
  state = EMPTY;
  current = null;
  wanted = null;
  queue = [];
}

registerPlayer(pause);
