/**
 * Where the line thinks the track is, which is not always where the element says it is.
 *
 * An element does not move the instant it is told to: it reports the old `currentTime` until a seek
 * lands, and near zero while a `src` is being replaced. The clock reads it every frame, so both of
 * those used to reach the screen — tapping a word lit the word *before* it for as long as the blob
 * took to come back out of IndexedDB, which is why the flicker was longer on a desktop than on a
 * phone. These pin the two halves of the answer: a move within a track already held is not a
 * reload, and a seek asked for outranks the element until the element agrees.
 *
 * `LoopPlayer.test.tsx` mocks `usePlayback` outright, so nothing there can see this.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Loop, LoopItem } from "./domain";
import { MemoryMediaStore } from "./mediaStore";
import { drillCues } from "./testGraph";

const loop: Loop = {
  id: "loop00000000001", language: "es", styleId: "gentle-game", seed: 104740,
  engineVersion: "1.4.0", bedFingerprint: "f35282aaf3c40245", format: "classic", switches: {}, fallbackFrom: null,
  audioRef: "loops/es/loop00000000001-6ad2f019.mp3", audioMime: "audio/mpeg",
  durationSeconds: 90, position: 1,
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1
};

const word = (over: Partial<LoopItem>): LoopItem => ({
  id: "loopitem0000001", loopId: loop.id, lexemeId: "lexeme000000001", position: 0,
  sourceText: "asco", targetText: "disgust", emotion: "repulsed",
  startSeconds: 8.82, sourceRevealSeconds: 8.82, targetRevealSeconds: 17.65, endSeconds: 44.12,
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1, ...over
});

const items = [
  word({}),
  word({ id: "loopitem0000002", position: 1, sourceText: "la balsa", targetText: "raft",
         startSeconds: 44.12, sourceRevealSeconds: 44.12, targetRevealSeconds: 52.94, endSeconds: 79.41 })
];

const track = { loop, items, cues: drillCues(loop.id, items, 4.41) };

/* The element, as a browser behaves rather than as jsdom does: `currentTime` is written by the
   player and read back only once the seek has *landed*, which `land()` is. jsdom's own accessor
   answers the write immediately, which is precisely the behaviour that hides this bug. */
let reported = 0;
let asked: number | null = null;
let paused = true;
let made: HTMLAudioElement | null = null;
let frames: FrameRequestCallback[] = [];

function land(): void {
  if (asked !== null) reported = asked;
  asked = null;
  made?.dispatchEvent(new Event("seeked"));
}

/** One turn of the clock, as `requestAnimationFrame` would give it. */
function tick(): void {
  const due = frames;
  frames = [];
  due.forEach((run) => run(performance.now()));
}

type Player = typeof import("./loops");
let player: Player;

beforeEach(async () => {
  reported = 0; asked = null; paused = true; made = null; frames = [];

  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true, get: () => reported, set: (value: number) => { asked = value; }
  });
  Object.defineProperty(HTMLMediaElement.prototype, "paused", {
    configurable: true, get: () => paused
  });

  const Element = globalThis.Audio;
  vi.stubGlobal("Audio", class extends Element {
    constructor() { super(); made = this as unknown as HTMLAudioElement; }
  });
  vi.stubGlobal("requestAnimationFrame", (run: FrameRequestCallback) => { frames.push(run); return frames.length; });
  vi.stubGlobal("cancelAnimationFrame", () => { frames = []; });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, blob: async () => new Blob(["mp3"], { type: "audio/mpeg" })
  }));

  // A fresh module, so the element it holds is one this test made and can speak for.
  vi.resetModules();
  player = await import("./loops");
  player.replaceStoreForTests(new MemoryMediaStore());
  const api = await import("./api");
  vi.spyOn(api.backendSession, "mediaFileUrl").mockImplementation((reference) => `https://acervo.example.com/media/${reference}`);
  vi.spyOn(api.backendSession, "mediaHeaders").mockReturnValue({ Authorization: "Bearer token" });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(HTMLMediaElement.prototype, "currentTime");
  Reflect.deleteProperty(HTMLMediaElement.prototype, "paused");
});

describe("moving within a loop", () => {
  it("steps card by card: back to the top of this one, then to the one before", async () => {
    await player.play(track);
    player.seek(50);                            // six seconds into the second word
    player.stepCard(-1);
    expect(player.playback().at).toBe(44.12);
    player.stepCard(-1);
    expect(player.playback().at).toBe(8.82);
    player.stepCard(1);
    expect(player.playback().at).toBe(44.12);
  });

  it("does not reload the track to move within it", async () => {
    // Not just "does not fetch": the bytes are held for the session either way. What must not happen
    // is the `src` being replaced, which is what leaves the element playing the old position.
    const url = vi.spyOn(URL, "createObjectURL");
    await player.play(track);
    expect(url).toHaveBeenCalledTimes(1);

    await player.play(track, { at: items[1].startSeconds });

    expect(url).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(player.playback().at).toBe(items[1].startSeconds);
  });

  it("keeps the line on the word asked for while the element is still catching up", async () => {
    await player.play(track);
    paused = false;
    reported = 30;                              // somewhere in the first word
    made!.dispatchEvent(new Event("play"));     // the clock starts

    await player.play(track, { at: items[1].startSeconds });
    tick();

    // The element still says 30, which is the first word. Nothing may put the line back there.
    expect(made!.currentTime).toBe(30);
    expect(player.playback().at).toBe(items[1].startSeconds);
  });

  it("follows the element again once the seek has landed", async () => {
    await player.play(track);
    paused = false;
    reported = 30;
    made!.dispatchEvent(new Event("play"));
    player.seek(items[1].startSeconds);

    land();
    reported = items[1].startSeconds + 1.5;
    tick();

    expect(player.playback().at).toBe(items[1].startSeconds + 1.5);
  });
});

describe("stopping", () => {
  it("forgets the loop as the one playing, and takes it off the lock screen", async () => {
    const handlers = new Map<string, unknown>();
    const session = {
      metadata: null as unknown,
      setActionHandler: (action: string, run: unknown) => {
        if (run) handlers.set(action, run); else handlers.delete(action);
      }
    };
    vi.stubGlobal("navigator", { ...navigator, mediaSession: session });
    vi.stubGlobal("MediaMetadata", class { constructor(readonly init: unknown) {} });

    await player.play(track);
    expect(player.playback().loopId).toBe(loop.id);
    expect(session.metadata).not.toBeNull();
    expect(handlers.has("play")).toBe(true);

    player.stop();
    expect(player.playback().loopId).toBeNull();
    expect(player.nowPlaying()).toBeNull();
    expect(session.metadata).toBeNull();
    expect(handlers.size).toBe(0);
  });
});
