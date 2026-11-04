import { AcervoApiError, backendSession, type PushResponse } from "./api";
import type { VocabularyGraph } from "./domain";
import {
  repository, type ArticleWrite, type RemoteGraph, type RemoteWrite, type WriteOptions
} from "./repository";
import type { ArticleDraft } from "./yaml";
import { isNativeHost } from "./pwa";

/**
 * A word captured a minute ago does not need to arrive this second, and a pull that finds nothing
 * is one indexed range scan per collection. Sixty seconds is the balance; focus and network
 * recovery cover the cases where waiting would be noticed.
 */
const SYNC_INTERVAL = 60_000;
/** A sync that finishes quickly should not flash a spinner on its way past. */
const SYNCING_VISIBLE_AFTER = 600;

export type SyncState =
  "signedOut" | "idle" | "syncing" | "offline" | "serverError" | "blocked" | "datasetChanged";

export interface SyncStatus {
  state: SyncState;
  cursor: number;
  lastPulledAt: string | null;
  lastWroteAt: string | null;
  /** False when the replica could not be stored and lives only for this session. */
  persistent: boolean;
  message: string | null;
}

const IDLE_STATUS: SyncStatus = {
  state: "signedOut", cursor: 0, lastPulledAt: null, lastWroteAt: null, persistent: true, message: null
};

export function shouldSyncWhenTriggered(): boolean {
  return isNativeHost() || typeof document === "undefined" || document.visibilityState === "visible";
}

class SyncEngine implements RemoteGraph {
  private status: SyncStatus = IDLE_STATUS;
  private listeners = new Set<() => void>();
  private stops: (() => void)[] = [];
  private timer: number | undefined;
  private announce: number | undefined;
  private running: Promise<SyncStatus> | null = null;
  /** Asked for again while a pull was running, whose request may have left before the change. */
  private again = false;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getStatus = (): SyncStatus => this.status;

  start(): void {
    this.stop();
    repository.attachRemote(this);
    this.update({ state: "idle", message: null });
    // The engine owns the schedule; the caller owns "sync now that we are signed in". Tests get
    // no timers or listeners installed underneath them, and still drive `syncNow` explicitly.
    if (import.meta.env.MODE === "test") return;
    const trigger = () => { void this.syncNow(); };
    const whenVisible = () => { if (shouldSyncWhenTriggered()) trigger(); };

    this.timer = window.setInterval(whenVisible, SYNC_INTERVAL);
    window.addEventListener("focus", whenVisible);
    window.addEventListener("online", trigger);
    document.addEventListener("visibilitychange", whenVisible);
    this.stops.push(
      () => window.removeEventListener("focus", whenVisible),
      () => window.removeEventListener("online", trigger),
      () => document.removeEventListener("visibilitychange", whenVisible)
    );
  }

  stop(): void {
    window.clearInterval(this.timer);
    window.clearTimeout(this.announce);
    this.timer = undefined;
    this.announce = undefined;
    this.stops.forEach((remove) => remove());
    this.stops = [];
    repository.attachRemote(null);
    this.update({ state: "signedOut", message: null });
  }

  /**
   * Single-flight across pulls and writes alike. Serialising them is what stops a pull that was
   * already in flight from landing on top of a record a write has since replaced.
   *
   * Resolves with the status the sync ended in rather than rejecting, because most callers are
   * timers and listeners with nowhere to put a rejection. It has to resolve with *something*: a
   * bare promise meant "Sync now" could not tell success from failure and silently did nothing
   * visible, which is exactly how a broken server looked like a broken button.
   *
   * A call that arrives while a pull is running does not simply join it: that pull's request may
   * have left before the change the caller heard about, and joining it dropped a `revision` until
   * the minute timer came round. It asks for **one** more pull after the current one instead, so a
   * burst of revisions — an import sends several a word — costs two pulls rather than one each.
   */
  syncNow(immediate = false): Promise<SyncStatus> {
    if (this.running) {
      this.again = true;
      return this.running;
    }
    this.running = (async () => {
      do {
        this.again = false;
        await this.exchange(immediate);
      } while (this.again && this.status.state === "idle");
      return this.status;
    })().finally(() => { this.running = null; });
    return this.running;
  }

  private async exchange(immediate: boolean): Promise<void> {
    if (!backendSession.current()?.token) { this.update({ state: "signedOut" }); return; }
    if (this.status.state === "blocked" || this.status.state === "datasetChanged") return;
    if (immediate) this.update({ state: "syncing" });
    else this.announce = window.setTimeout(() => this.update({ state: "syncing" }), SYNCING_VISIBLE_AFTER);
    try {
      await this.pull();
      this.update({ state: "idle", message: null });
    } catch (error) {
      this.update(this.failure(error));
    } finally {
      // Each exchange cancels its own announcement. Clearing only when the loop ended let the first
      // of two back-to-back pulls — the launch pull and the event stream's — announce itself after
      // both were done, and "Checking the server for changes" stayed up until the next poll.
      window.clearTimeout(this.announce);
      this.announce = undefined;
    }
  }

  private async pull(): Promise<void> {
    const before = repository.state();
    const response = await backendSession.pullGraph(before.cursor);
    this.guardDataset(before.datasetId, response.datasetId);
    // A delta is not a whole graph and cannot be validated as one — half its relations point at
    // records the replica already holds. `applyRemote` validates the merged result instead.
    await repository.applyRemote(response.changes, response.cursor, response.datasetId);
  }

  /**
   * A cursor must never outlive the database that issued it. Calorie Logger resets and re-pushes
   * here, which is safe because its devices push. Acervo's do not, so this replica may hold more
   * than the server does — discarding it automatically could destroy the last complete copy.
   */
  private guardDataset(stored: string, incoming: string): void {
    if (!stored || stored === incoming) return;
    throw new DatasetChanged();
  }

  /** `RemoteGraph.push` — the repository's only route to the server. */
  async push(changes: Partial<VocabularyGraph>, options?: WriteOptions): Promise<RemoteWrite> {
    const snapshot = repository.state();
    try {
      const response = await backendSession.pushGraph(snapshot.deviceId, changes, options);
      this.guardDataset(snapshot.datasetId, response.datasetId);
      // The cursor deliberately does not move on a write: leaving it alone means the next pull
      // re-delivers these rows harmlessly rather than skipping anything written in between.
      return { records: response.records, cursor: snapshot.cursor, datasetId: response.datasetId };
    } catch (error) {
      this.update(this.failure(error));
      throw error;
    }
  }

  /** `RemoteGraph.saveArticle` — an article goes to the server as the document it is. */
  async saveArticle(
    draft: ArticleDraft, minted: ReadonlySet<string>, base: Record<string, number>, options?: WriteOptions
  ): Promise<ArticleWrite> {
    const snapshot = repository.state();
    try {
      const response = await backendSession.saveArticle(snapshot.deviceId, draft, [...minted], base, options);
      this.guardDataset(snapshot.datasetId, response.datasetId);
      return {
        records: response.records, cursor: snapshot.cursor, datasetId: response.datasetId,
        lexemeId: response.lexemeId, jobId: response.jobId
      };
    } catch (error) {
      this.update(this.failure(error));
      throw error;
    }
  }

  /** Tombstones every word and descendant, retaining languages and topics. */
  async resetWords(): Promise<void> {
    const snapshot = repository.state();
    try {
      const response = await backendSession.resetGraph(snapshot.deviceId);
      this.guardDataset(snapshot.datasetId, response.datasetId);
    } catch (error) {
      this.update(this.failure(error));
      throw error;
    }
    await this.syncNow(true);
  }

  /**
   * Discards the replica and downloads it again from the beginning. This is also the way out of
   * `datasetChanged`, which is why it clears the terminal state before syncing.
   */
  async downloadAgain(): Promise<void> {
    const ownerId = repository.state().ownerId;
    await repository.clear();
    await repository.load(ownerId);
    this.update({ state: "idle", message: null });
    await this.syncNow(true);
  }

  acknowledge(): void {
    this.update({ message: null });
  }

  private failure(error: unknown): Partial<SyncStatus> {
    if (error instanceof DatasetChanged) {
      return {
        state: "datasetChanged",
        message: "The server database was rebuilt or restored, so this device's copy can no longer be matched against it."
      };
    }
    if (!(error instanceof AcervoApiError)) {
      return { state: "offline", message: error instanceof Error ? error.message : String(error) };
    }
    if (error.code === "schema_version_mismatch") return { state: "blocked", message: error.message };
    if (error.status === 401) return { state: "signedOut", message: error.message };
    // A server that answers and fails is not an unreachable one. Calling it "offline" sent a whole
    // session looking at the network while PocketBase was refusing every request for a reason it
    // was willing to state. Reading still falls back to the replica either way.
    if (error.status >= 500) return { state: "serverError", message: error.message };
    return { state: "offline", message: error.message };
  }

  private update(changes: Partial<SyncStatus>) {
    const snapshot = repository.state();
    const next: SyncStatus = {
      ...this.status,
      cursor: snapshot.cursor,
      lastPulledAt: snapshot.lastPulledAt,
      lastWroteAt: snapshot.lastWroteAt,
      persistent: snapshot.persistent,
      ...changes
    };
    // Every listener repaints the whole interface, so a status that says nothing new is not sent.
    if ((Object.keys(next) as (keyof SyncStatus)[]).every((key) => next[key] === this.status[key])) return;
    this.status = next;
    this.listeners.forEach((listener) => listener());
  }
}

/** Not an API error: the request succeeded, and its answer is that the cursor is meaningless. */
export class DatasetChanged extends Error {
  constructor() { super("The server database changed identity."); }
}

export const syncEngine = new SyncEngine();
