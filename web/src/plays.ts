import { useSyncExternalStore } from "react";
import type { Play } from "./domain";
import { newId, nowInstant } from "./ids";
import { repository } from "./repository";

/**
 * Plays waiting to reach the server: **the one write this application queues**.
 *
 * Every other write is a round trip that fails loudly offline and changes nothing
 * (`docs/architecture/sync.md`). A play is the exception because of what it is: a record made once, on
 * the device it happened on, and never edited — so it has no version it was edited *from*, and there
 * is nothing it could be stale against or conflict with. Sending it late is the same write as sending
 * it at once. And it happens where the other writes do not: on a phone in a pocket, with no server in
 * reach, which is exactly when Least played most needs to have heard about it.
 *
 * So a play is kept here, in local storage under the account it was made in, until the sync engine
 * has sent it (`sync.ts`, after each pull) and the server's copy is in the replica. Counts read the
 * replica's plays and these together (`playCounts` in `selectors.ts`), so a play counts the moment it
 * happens, online or not. A play the server refuses — its loop belongs to another account, or it was
 * already stored — is dropped rather than tried forever: it can never succeed, and the server has
 * written the refusal down in its activity log.
 */

const KEY = "acervo-play-outbox";

interface Stored {
  ownerId: string;
  plays: readonly Play[];
}

const NONE: readonly Play[] = Object.freeze([]);
let state: Stored = read();
const listeners = new Set<() => void>();
const recorded = new Set<() => void>();

function read(): Stored {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || "null") as Partial<Stored> | null;
    if (!parsed || typeof parsed.ownerId !== "string" || !Array.isArray(parsed.plays)) return { ownerId: "", plays: NONE };
    return { ownerId: parsed.ownerId, plays: Object.freeze(parsed.plays.filter((play) => play && typeof play.id === "string")) };
  } catch {
    return { ownerId: "", plays: NONE };
  }
}

function write(next: Stored): void {
  state = next;
  try { localStorage.setItem(KEY, JSON.stringify(next)); }
  catch { /* storage refused: the play waits only as long as this session */ }
  listeners.forEach((listener) => listener());
}

/** The plays this account has made on this device that the replica does not hold yet. */
export function pendingPlays(ownerId: string = repository.state().ownerId): readonly Play[] {
  return state.ownerId === ownerId ? state.plays : NONE;
}

/**
 * One play of a loop, or one read of a story, now. Counted at once, and sent with the next sync —
 * which this asks for, so online it reaches the server within a moment.
 */
export function recordPlay(kind: "loop" | "story", id: string): void {
  const replica = repository.state();
  if (!replica.ready || !replica.ownerId) return;
  const at = nowInstant();
  const play: Play = {
    id: newId(), loopId: kind === "loop" ? id : null, storyId: kind === "story" ? id : null,
    ownerId: replica.ownerId, deleted: false, createdAt: at, editedAt: at, editedBy: replica.deviceId, revision: 0
  };
  write({ ownerId: replica.ownerId, plays: Object.freeze([...pendingPlays(replica.ownerId), play]) });
  recorded.forEach((listener) => listener());
}

/** Forget plays that have arrived, or that can never arrive. */
export function dropPlays(ids: readonly string[]): void {
  if (!ids.length) return;
  const gone = new Set(ids);
  write({ ownerId: state.ownerId, plays: Object.freeze(state.plays.filter((play) => !gone.has(play.id))) });
}

/** Told when a play is recorded: how the sync engine knows to send it without importing this the other way. */
export function onPlayRecorded(listener: () => void): () => void {
  recorded.add(listener);
  return () => { recorded.delete(listener); };
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function usePendingPlays(): readonly Play[] {
  const stored = useSyncExternalStore(subscribe, () => state);
  return stored.ownerId === repository.state().ownerId ? stored.plays : NONE;
}

export function resetPlaysForTests(): void {
  state = { ownerId: "", plays: NONE };
  try { localStorage.removeItem(KEY); } catch { /* nothing to remove */ }
}
