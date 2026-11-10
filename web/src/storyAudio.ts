/**
 * Hearing a story: the third place in Acervo where anything is heard, after `pronunciation.ts` (a word
 * or a sentence) and `loops.ts` (a track), and modelled on the second.
 *
 * **A story plays part after part, and goes on to the next story when asked to.** The use is a phone
 * in a pocket: one tap, and it reads to the end. Each part's passages play in turn, then the next
 * part's; at the end, the owner's two switches decide, in the loop player's order — read it again,
 * else the next story in the list it was started from, else stop. **Pause is pause, and leaving is not
 * stop**: the reader closing, a word opened, the screen locked — none of them is a reason to stop
 * reading, any more than they are for a loop. The bar, the rail's card and the lock screen are what it
 * reads behind (`listening.ts`).
 *
 * **A passage is its own file, and nothing is ever seeked.** Playing one is playing it from its first
 * sample. The alternative was tried and does not work: join the passages, remember where each begins,
 * and set `currentTime`. A browser seeks a compressed stream to a page boundary — one second, in the
 * Ogg the server writes — so a passage started a word or two late, or into the sentence before, and
 * the element reports the position that was asked for rather than the one it gave.
 *
 * **What it will need next is read before it is needed.** A part's passages are all in hand before its
 * first one sounds, so the swap between two is an assignment rather than a fetch, and while a part
 * plays the next part's are read too — so a locked phone with no signal goes on to the next part
 * without asking the network for anything. Recordings are kept on the device with the other clips.
 *
 * **A passage is a place to start.** Touching one while nothing of this story is sounding plays that
 * passage alone — "what was that sentence?"; touching one while it is sounding goes there and reads
 * on — "go back to there".
 *
 * **On demand is the same route the job takes.** A part with no passages asks the server for them,
 * which is one call to the same function `story.audio` runs, and plays when they arrive. The element
 * is started on silence in the press itself, before that wait, for `pronunciation.ts`'s reason: iOS
 * lets an element play only from inside the gesture that asked.
 *
 * One sound at a time: this stops `pronunciation.ts`, pauses every other registered player before it
 * plays, and registers its own pause with them. The dependency runs one way, as it does for loops.
 */

import { useSyncExternalStore } from "react";
import { AcervoApiError, backendSession } from "./api";
import type { AudioSegment, Story, StoryPart } from "./domain";
import { storyAutoplayEnabled, storyRepeatEnabled } from "./editorPreferences";
import { claim, release as releaseLockScreen } from "./listening";
import { recordPlay } from "./plays";
import { clipBlob, registerPlayer, silencePlayers, stop as stopSpeech } from "./pronunciation";
import { repository } from "./repository";
import { storyPartsOf, storyTitle } from "./selectors";
import { syncEngine } from "./sync";

export type StoryAudioStatus = "idle" | "busy" | "playing" | "paused";

export interface StoryPlayback {
  /** The story loaded: being read, paused, or read to its end and waiting to be read again. */
  storyId: string | null;
  /** The part being fetched, recorded, heard or paused. Kept while `failed`, so the reader can say why. */
  partId: string | null;
  /** Its place in the story, which is the page the reader follows to. */
  partIndex: number;
  status: StoryAudioStatus;
  /** Index of the passage that is sounding, or null when nothing of this part is. */
  segment: number | null;
  /** How many passages the part has, so a footer can say how far into it the voice is. */
  passages: number;
  failed: string | null;
}

const EMPTY: StoryPlayback = { storyId: null, partId: null, partIndex: 0, status: "idle", segment: null, passages: 0, failed: null };

let state: StoryPlayback = EMPTY;
const listeners = new Set<() => void>();

function update(partial: Partial<StoryPlayback>): void {
  state = { ...state, ...partial };
  listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };

export const storyPlayback = (): StoryPlayback => state;

export function useStoryAudio(): StoryPlayback {
  return useSyncExternalStore(subscribe, storyPlayback);
}

/* ── what is loaded ──────────────────────────────────────────────────── */

interface Reading {
  story: Story;
  /** The parts as they were when it started, with any recorded on demand since filled in. */
  parts: StoryPart[];
  index: number;
  passages: AudioSegment[];
  at: number;
  /** One passage asked for on its own: it stops after that passage, and is not a read. */
  alone: boolean;
}

let reading: Reading | null = null;
/** The bytes of the loaded story's passages, by reference: this part's, and the next one's. */
const blobs = new Map<string, Blob>();
/** The stories in the order the list showed them, which is what "the next story" means. */
let order: string[] = [];
/** The story whose read has been counted in this opening (`noteRead`). */
let counted: string | null = null;

let element: HTMLAudioElement | null = null;
/** The object URL the element is holding, revoked when it is let go. */
let held: string | null = null;
/** Bumped by every press that starts something, so an answer that arrives late knows it is stale. */
let run = 0;

/** The list a story was started from, in the order shown; set by whoever shows it, kept here. */
export function setStoryQueue(ids: readonly string[]): void { order = [...ids]; }

function neighbour(by: 1 | -1): string | null {
  if (!reading) return null;
  const at = order.indexOf(reading.story.id);
  return at < 0 ? null : order[at + by] ?? null;
}

export function hasNextStory(): boolean { return Boolean(neighbour(1)); }

/**
 * A read is an opening that reaches the second part — by the page turned or by the voice — counted
 * once per opening. `beginReading` is an opening of the reader; the voice reaching another story is
 * one too.
 */
export function noteRead(storyId: string): void {
  if (counted === storyId) return;
  counted = storyId;
  recordPlay("story", storyId);
}

export function beginReading(storyId: string): void {
  if (state.storyId !== storyId && counted === storyId) counted = null;
}

/* ── the element ─────────────────────────────────────────────────────── */

function audio(): HTMLAudioElement {
  if (element) return element;
  element = new Audio();
  element.preload = "auto";
  // The passage's own end only: the silence `prime` starts ends too, long before one has arrived.
  element.addEventListener("ended", () => { if (held && element?.src === held) void advance(); });
  element.addEventListener("pause", () => {
    if (state.status === "playing" && held && element?.src === held) update({ status: "paused" });
  });
  element.addEventListener("play", () => {
    if (held && element?.src === held) update({ status: "playing" });
  });
  return element;
}

/* A few milliseconds of silence, for the reason `pronunciation.ts` and `loops.ts` give. */
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

function prime(): void {
  const player = audio();
  if (!player.paused) return;
  try { player.src = SILENCE; void player.play()?.catch(() => undefined); }
  catch { /* jsdom, or a browser with no audio at all */ }
}

/** Let go of the element: nothing is sounding and nothing is held. What is loaded stays loaded. */
function silence(): void {
  if (element) {
    try { element.pause(); } catch { /* nothing to stop */ }
    element.removeAttribute("src");
  }
  if (held) { URL.revokeObjectURL(held); held = null; }
}

/** Play the passage the reading is on. */
async function sound(): Promise<void> {
  if (!reading) return;
  const passage = reading.passages[reading.at];
  const blob = blobs.get(passage.audioRef);
  if (!blob) throw new Error("That passage's recording is not on this device.");
  const player = audio();
  if (held) URL.revokeObjectURL(held);
  held = URL.createObjectURL(blob);
  player.src = held;
  update({ status: "playing", segment: reading.at });
  await player.play();
}

/** Every passage of a part, read into `blobs` unless already there. */
async function fetchPassages(passages: AudioSegment[], mine: number): Promise<boolean> {
  for (const passage of passages) {
    if (blobs.has(passage.audioRef)) continue;
    const blob = await clipBlob(passage.audioRef);
    if (mine !== run) return false;
    blobs.set(passage.audioRef, blob);
  }
  return true;
}

/** The next part's passages, while this one plays, so going on to it needs no network. */
function readAhead(index: number, mine: number): void {
  const part = reading?.parts[index];
  if (!part?.audioSegments.length) return;
  void fetchPassages(part.audioSegments, mine).catch(() => undefined);
}

/** Begin part `index` of what is loaded, from passage `from`: recorded first if it has no passages. */
async function enter(index: number, from: number, mine: number): Promise<void> {
  if (!reading) return;
  let part = reading.parts[index];
  update({ partId: part.id, partIndex: index, status: "busy", segment: null, failed: null, passages: part.audioSegments.length });
  if (!part.audioSegments.length) {
    const row = await backendSession.recordStoryPart(part.storyId, part.id, repository.state().deviceId);
    if (mine !== run || !reading) return;
    // The row reaches the replica the way every server-written row does; it plays meanwhile.
    void syncEngine.syncNow();
    part = { ...part, audioSegments: row.audioSegments };
    reading.parts[index] = part;
    from = 0;
  }
  if (!part.audioSegments.length) throw new Error("That part has no recording.");
  if (!await fetchPassages(part.audioSegments, mine)) return;
  // Only the bytes of this part and the next stay held: a long story is not kept whole in memory.
  const keep = new Set([...part.audioSegments, ...(reading.parts[index + 1]?.audioSegments ?? [])].map((one) => one.audioRef));
  [...blobs.keys()].forEach((reference) => { if (!keep.has(reference)) blobs.delete(reference); });
  reading.index = index;
  reading.passages = part.audioSegments;
  reading.at = Math.min(from, part.audioSegments.length - 1);
  update({ passages: part.audioSegments.length });
  if (index >= 1 && !reading.alone) noteRead(reading.story.id);
  describe();
  await sound();
  if (!reading.alone) readAhead(index + 1, mine);
}

function failure(error: unknown): string {
  if (error instanceof AcervoApiError && error.code === "offline") {
    return "Reading a story aloud needs the server, and it cannot be reached.";
  }
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "This device would not start the audio. Press play again.";
  }
  return error instanceof Error ? error.message : "That part could not be read aloud.";
}

function failed(error: unknown, partId: string | null): void {
  console.warn("Acervo: a story could not be read aloud", { part: partId, error });
  silence();
  update({ status: "idle", segment: null, failed: failure(error) });
}

/** Load `story` and read it from part `index`, passage `from` — or that one passage, `alone`. */
async function start(story: Story, parts: StoryPart[], index: number, from: number, alone: boolean): Promise<void> {
  if (!parts[index]) return;
  const mine = ++run;
  if (reading?.story.id !== story.id) blobs.clear();
  silence();
  stopSpeech();
  silencePlayers(pause);
  // Before any await, so the browser still counts this as the gesture that asked.
  prime();
  reading = { story, parts: [...parts], index, passages: [], at: from, alone };
  update({ ...EMPTY, storyId: story.id });
  try {
    await enter(index, from, mine);
  } catch (error) {
    if (mine === run) failed(error, parts[index].id);
  }
}

/** This passage ended: the next passage, the next part, or the end of the story. */
async function advance(): Promise<void> {
  if (!reading) return;
  const mine = run;
  if (reading.alone) { atRest(); return; }
  try {
    if (reading.at + 1 < reading.passages.length) {
      reading.at += 1;
      await sound();
    } else if (reading.index + 1 < reading.parts.length) {
      await enter(reading.index + 1, 0, mine);
    } else {
      ended();
    }
  } catch (error) {
    if (mine === run) failed(error, state.partId);
  }
}

/** Read to its end: read it again, else the next story, else rest with it still loaded. */
function ended(): void {
  if (!reading) return;
  const { story, parts } = reading;
  if (storyRepeatEnabled()) {
    counted = null;
    void start(story, parts, 0, 0, false);
    return;
  }
  const next = storyAutoplayEnabled() ? neighbour(1) : null;
  if (next && startById(next)) return;
  atRest();
}

/** Nothing sounding, and what was loaded still loaded, so play reads it again from the top. */
function atRest(): void {
  run += 1;
  silence();
  if (reading) reading.alone = false;
  update({ status: "idle", segment: null, partIndex: 0, partId: reading?.parts[0]?.id ?? null });
}

function startById(storyId: string, index = 0): boolean {
  const graph = repository.snapshot();
  const story = graph.stories.find((one) => one.id === storyId && !one.deleted);
  const parts = story ? storyPartsOf(graph, story.id) : [];
  if (!story || !parts.length) return false;
  void start(story, parts, index, 0, false);
  return true;
}

/* ── the lock screen ── */

function describe(): void {
  if (!reading) return;
  const graph = repository.snapshot();
  const part = reading.parts[reading.index];
  claim("story", {
    title: storyTitle(graph, reading.story),
    artist: `Part ${reading.index + 1} of ${reading.parts.length}`,
    picture: part.imageRef,
    play: () => resume(),
    pause: () => pause(),
    // A part is a chapter: Previous goes back to the top of this one, or the one before; Next goes
    // on to the next part, and from the last to the next story.
    previous: () => stepPart(-1),
    next: () => { if (reading && reading.index + 1 < reading.parts.length) stepPart(1); else nextStory(); }
  });
}

/* ── pressing ────────────────────────────────────────────────────────── */

/**
 * The reader's play button, on the part `index` it is showing: play, pause or carry on; on a story
 * that is not the one loaded, read it from that part. Pressing it while a part is being recorded
 * stops that.
 */
export function toggleStory(story: Story, parts: StoryPart[], index: number): void {
  if (state.storyId === story.id && reading) {
    if (state.status === "playing") { pause(); return; }
    if (state.status === "paused") { resume(); return; }
    if (state.status === "busy") { stop(); return; }
  }
  void start(story, parts, index, 0, false);
}

/** Read `story` from part `index`: the page swiped to while it reads, or a footer's part tapped. */
export function readFrom(story: Story, parts: StoryPart[], index: number): void {
  void start(story, parts, index, 0, false);
}

/**
 * A touch on a passage. While this story is sounding it goes there and reads on; otherwise it plays
 * that passage alone.
 */
export function playSegment(story: Story, parts: StoryPart[], index: number, passage: number): void {
  if (!parts[index]?.audioSegments[passage]) return;
  const sounding = state.storyId === story.id && (state.status === "playing" || state.status === "paused") && !reading?.alone;
  void start(story, parts, index, passage, !sounding);
}

/** Previous goes to the top of this part unless it has only just begun; Next to the next part. */
export function stepPart(by: 1 | -1): void {
  if (!reading) return;
  const fresh = reading.at === 0 && (audio().currentTime || 0) < 3;
  const want = by < 0 ? (fresh ? reading.index - 1 : reading.index) : reading.index + 1;
  if (want < 0 || want >= reading.parts.length) return;
  void start(reading.story, reading.parts, want, 0, false);
}

/** The next story in the list it was started from. */
export function nextStory(): void {
  const next = neighbour(1);
  if (next) startById(next);
}

export function pause(): void {
  if (state.status !== "playing") return;
  try { element?.pause(); } catch { /* nothing to stop */ }
  update({ status: "paused" });
}

export function resume(): void {
  if (!reading) return;
  if (state.status === "idle") { void start(reading.story, reading.parts, state.partIndex, 0, false); return; }
  silencePlayers(pause);
  describe();
  void audio().play().catch((error: unknown) => failed(error, state.partId));
}

/** Stop and forget the story: what the bar's close does. */
export function stop(): void {
  run += 1;
  silence();
  reading = null;
  blobs.clear();
  update(EMPTY);
  releaseLockScreen("story");
}

export function replaceForTests(): void {
  run += 1;
  silence();
  element = null;
  reading = null;
  blobs.clear();
  order = [];
  counted = null;
  state = EMPTY;
}

registerPlayer(pause);
