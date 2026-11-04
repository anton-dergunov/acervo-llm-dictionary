/**
 * Hearing a word: every pronunciation call, the one audio element, and the clips kept on this device.
 *
 * **Reads are offline-first here too.** A clip the replica names and this device holds plays with no
 * request at all. Otherwise the server is asked, and it answers with the stored clip while it still
 * says what the record says, or records a new one — which is a write, so it needs the server and
 * fails loudly without one. Nothing is queued: a press that could not be answered says so.
 *
 * A clip is a row in the replica (`pronunciations`) naming a file in the server's media directory,
 * the way a picture is. The bytes are kept in `mediaStore.ts`'s `pronunciations` store — a store of
 * its own, so switching this off forgets clips and never pictures — keyed by the reference the row
 * carries. Recording again gives the row a new reference, so a stale key is simply never asked for.
 *
 * A **selection** is the one thing spoken and not kept, anywhere: it names no record, so there is no
 * row to put it in and nothing to tell when it is stale. `selectionSpeech.ts` decides what the runs
 * are; this module says them.
 */

import { useSyncExternalStore } from "react";
import { AcervoApiError, backendSession } from "./api";
import type { Pronunciation, PronunciationTarget, VocabularyGraph } from "./domain";
import { pronunciationCacheEnabled } from "./editorPreferences";
import { pronunciationId } from "./ids";
import { createMediaStore, type MediaStore } from "./mediaStore";
import { repository } from "./repository";
import { syncEngine } from "./sync";

/** What a play button says. `id` is null in an unsaved proposal, which has nothing to store against. */
export interface SayTarget {
  kind: PronunciationTarget;
  id: string | null;
  text: string;
  lang: string;
}

/** One stretch of a selection in one language, and the record it is the whole text of, if any. */
export interface SpokenRun {
  text: string;
  lang: string;
  target: SayTarget | null;
}

export interface Played {
  /** The voice that read it, for the toast. */
  voice: string | null;
  /** True when a stored clip played, which is what can be recorded again. */
  stored: boolean;
}

export const COLLECTIONS: Record<PronunciationTarget, string> = {
  lexeme: "lexemes", sense: "senses", example: "examples", attestation: "attestations"
};

let store: MediaStore = createMediaStore("pronunciations");
/** Clips heard this session while keeping is off, so a second press does not fetch again. Bounded. */
const session = new Map<string, Blob>();
const SESSION_LIMIT = 40;

/* ── what is playing ─────────────────────────────────────────────────── */

export interface SpeechState {
  /** The key being fetched or recorded. */
  busy: string | null;
  /** The key being heard. */
  playing: string | null;
}

let state: SpeechState = { busy: null, playing: null };
const listeners = new Set<() => void>();

function update(next: Partial<SpeechState>): void {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

export function keyOf(target: Pick<SayTarget, "kind" | "id" | "text">): string {
  return `${target.kind}:${target.id ?? target.text}`;
}

export function useSpeechState(): SpeechState {
  return useSyncExternalStore(
    (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    () => state
  );
}

/* ── the audio element ───────────────────────────────────────────────── */

let element: HTMLAudioElement | null = null;
let finish: (() => void) | null = null;

/* A few milliseconds of silence. iOS lets an element play only from inside the gesture that asked,
   and the clip arrives after a fetch — so the element is started on silence first, synchronously,
   and the clip is swapped in once it arrives. */
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

function audio(): HTMLAudioElement {
  element ??= new Audio();
  return element;
}

/** Called synchronously from the press, before anything is awaited. */
function prime(): void {
  const player = audio();
  if (!player.paused) return;
  try {
    player.src = SILENCE;
    void player.play()?.catch(() => undefined);
  } catch { /* jsdom, or a browser with no audio at all */ }
}

/* What else on this page makes sound. Two audio elements racing for one output is a bug with no
   good failure mode, so every other player registers its own pause here, and each of them — this
   module included — calls `silencePlayers` before it plays. Registration runs this way round so the
   dependency does too: `loops.ts` and `storyAudio.ts` import this module and nothing imports them
   back. It was one slot while a loop was the only other player; a story's recording is the second,
   and a slot that the second overwrote would have left the first unsilenced. */
const players = new Set<() => void>();

/** Register a player's pause. Returns the way to take it out again. */
export function registerPlayer(pause: () => void): () => void {
  players.add(pause);
  return () => { players.delete(pause); };
}

/** Pause every other player. A player passes its own pause to be left alone. */
export function silencePlayers(except?: () => void): void {
  players.forEach((pause) => { if (pause !== except) pause(); });
}

/** Stop whatever is being heard. */
export function stop(): void {
  const player = element;
  if (player) {
    try { player.pause(); } catch { /* nothing to stop */ }
  }
  finish?.();
  finish = null;
  update({ playing: null });
}

async function sound(blob: Blob, key: string): Promise<void> {
  stop();
  silencePlayers();
  const player = audio();
  const url = URL.createObjectURL(blob);
  update({ playing: key });
  try {
    await new Promise<void>((resolve, reject) => {
      finish = resolve;
      // Only this clip's own end: the silence `prime` started may finish after the clip was swapped in.
      player.onended = () => { if (player.src === url) resolve(); };
      player.onerror = () => { if (player.src === url) reject(new Error("This device could not play that recording.")); };
      player.src = url;
      player.play().catch((error: unknown) => {
        const name = error instanceof DOMException ? error.name : "";
        reject(new Error(name === "NotAllowedError"
          ? "This device would not start the audio. Press play again."
          : "This device could not play that recording."));
      });
    });
  } catch (error) {
    console.warn("Acervo: a pronunciation could not be played", { key, type: blob.type, size: blob.size, error });
    throw error;
  } finally {
    finish = null;
    player.onended = null;
    player.onerror = null;
    URL.revokeObjectURL(url);
    if (state.playing === key) update({ playing: null });
  }
}

/* ── the clips ───────────────────────────────────────────────────────── */

/** The stored clip for a target, while it still says what the record says. */
export function currentClip(graph: Pick<VocabularyGraph, "pronunciations">, target: SayTarget): Pronunciation | null {
  if (!target.id) return null;
  const id = pronunciationId(target.kind, target.id);
  const clip = graph.pronunciations.find((record) => record.id === id);
  return clip && !clip.deleted && clip.text === target.text && clip.lang === target.lang ? clip : null;
}

async function download(reference: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(backendSession.mediaFileUrl(reference), { headers: backendSession.mediaHeaders(), cache: "no-store" });
  } catch {
    throw new Error("This pronunciation is not on this device yet, and the server cannot be reached.");
  }
  if (!response.ok) {
    console.warn("Acervo: a pronunciation could not be read from the server", { reference, status: response.status });
    throw new Error(response.status === 404
      ? "That recording is not on the server any more. Record it again."
      : `That recording could not be read from the server (${response.status}).`);
  }
  return response.blob();
}

/** The clip's bytes: this device first, then the server — kept on the device when keeping is on. */
export async function clipBlob(reference: string): Promise<Blob> {
  const kept = await store.read(reference).catch(() => null);
  if (kept) return kept.blob;
  const remembered = session.get(reference);
  if (remembered) return remembered;
  const blob = await download(reference);
  if (pronunciationCacheEnabled()) {
    await store.save(reference, blob).catch(() => undefined);
  } else {
    session.set(reference, blob);
    if (session.size > SESSION_LIMIT) session.delete(session.keys().next().value as string);
  }
  return blob;
}

/** For the export, which writes clips into a zip rather than playing them. */
export async function clipBytes(reference: string): Promise<Uint8Array> {
  return new Uint8Array(await (await clipBlob(reference)).arrayBuffer());
}

function failure(error: unknown): Error {
  if (error instanceof AcervoApiError && error.code === "offline") {
    return new Error("Recording a pronunciation needs the server, and it cannot be reached.");
  }
  return error instanceof Error ? error : new Error("That could not be pronounced.");
}

/**
 * Say one target. Pressing the button that is playing stops it instead.
 *
 * `again` asks the server for a fresh recording even when the stored one is current — "Record again"
 * after hearing a bad one. The previous clip is dropped from this device as the new one arrives.
 */
export async function play(target: SayTarget, options: { again?: boolean } = {}): Promise<Played | null> {
  const key = keyOf(target);
  if (!options.again && (state.playing === key || state.busy === key)) {
    stop();
    return null;
  }
  prime();
  update({ busy: key });
  try {
    if (!target.id) {
      const spoken = await backendSession.utterance(target.text, target.lang).catch((error) => { throw failure(error); });
      update({ busy: null });
      await sound(spoken.audio, key);
      return { voice: spoken.voice, stored: false };
    }
    const graph = repository.snapshot();
    const previous = graph.pronunciations.find((record) => record.id === pronunciationId(target.kind, target.id!));
    let clip = options.again ? null : currentClip(graph, target);
    if (!clip) {
      clip = await backendSession.pronounce(COLLECTIONS[target.kind], target.id, graph.deviceId, options.again === true)
        .catch((error) => { throw failure(error); });
      // The row reaches the replica the way every server-written row does; the clip plays meanwhile.
      void syncEngine.syncNow();
      if (previous && previous.audioRef !== clip.audioRef) void forget(previous.audioRef);
    }
    const blob = await clipBlob(clip.audioRef);
    update({ busy: null });
    await sound(blob, key);
    return { voice: clip.voice, stored: true };
  } finally {
    if (state.busy === key) update({ busy: null });
  }
}

/** Say a selection, one run after another. Nothing is stored unless a run is a whole stored record. */
export async function playRuns(runs: SpokenRun[]): Promise<void> {
  for (const run of runs) {
    if (run.target?.id) {
      await play(run.target);
      continue;
    }
    const key = `selection:${run.lang}:${run.text}`;
    prime();
    update({ busy: key });
    let spoken;
    try {
      spoken = await backendSession.utterance(run.text, run.lang).catch((error) => { throw failure(error); });
    } finally {
      update({ busy: null });
    }
    await sound(spoken.audio, key);
  }
}

/* What a voice sounded like, held for the session: comparing voices means pressing play on the same
   one again, and that should cost nothing. Never kept on the device — it is not a recording of any
   record, only a sample. */
const previews = new Map<string, Blob>();

/**
 * Hear a voice before choosing it, through this player like every other sound here. `key` names the
 * voice; pressing the one that is playing stops it.
 */
export async function playPreview(key: string, fetch: () => Promise<Blob>): Promise<void> {
  if (state.playing === key) { stop(); return; }
  prime();
  let blob = previews.get(key);
  if (!blob) {
    update({ busy: key });
    try {
      blob = await fetch().catch((error) => { throw failure(error); });
    } finally {
      if (state.busy === key) update({ busy: null });
    }
    previews.set(key, blob);
  }
  await sound(blob, key);
}

/* ── keeping clips ───────────────────────────────────────────────────── */

async function forget(reference: string): Promise<void> {
  session.delete(reference);
  await store.remove(reference).catch(() => undefined);
}

let filling: Promise<number> | null = null;

/**
 * Bring every clip the replica names onto this device — and every recording of a story part — so a
 * word recorded elsewhere, or in advance, plays offline. One at a time and stopping at the first failure, because the usual failure is
 * "offline" and the next sync will try again. Only while keeping is on.
 */
export function fill(graph: Pick<VocabularyGraph, "pronunciations" | "storyParts"> = repository.snapshot()): Promise<number> {
  if (filling || !pronunciationCacheEnabled()) return filling ?? Promise.resolve(0);
  filling = (async () => {
    let fetched = 0;
    // A part of a story read aloud is kept with the clips: it is spoken audio of the same order of
    // size, and it is what lets a story be heard on a plane. Same store, same key — the reference.
    const references = [
      ...graph.pronunciations.filter((clip) => !clip.deleted).map((clip) => clip.audioRef),
      ...graph.storyParts.filter((part) => !part.deleted)
        .flatMap((part) => part.audioSegments.map((passage) => passage.audioRef))
    ];
    for (const reference of references) {
      if (!reference) continue;
      if (await store.read(reference).catch(() => null)) continue;
      try {
        await store.save(reference, await download(reference));
        fetched += 1;
      } catch {
        break;
      }
    }
    return fetched;
  })().finally(() => { filling = null; });
  return filling;
}

/** Forget every clip kept on this device. The rows stay; a press fetches the clip again. */
export async function forgetPronunciations(): Promise<void> {
  session.clear();
  await store.clear().catch(() => undefined);
}

export function keptPronunciationBytes(): Promise<number> {
  return store.bytes().catch(() => 0);
}

/** For tests: a store that does not need IndexedDB. */
export function replaceStoreForTests(replacement: MediaStore): void {
  store = replacement;
  session.clear();
  state = { busy: null, playing: null };
  element = null;
}
