import { useState, useSyncExternalStore } from "react";
import { AcervoApiError, backendSession, type Job } from "../api";
import { jobFor, jobStream } from "../jobs";
import { SETTINGS, useServerSetting } from "./cache";
import { Group, Notice, Placeholder, Row, Toggle } from "./kit";

/**
 * Settings ▸ Anki: whether the server keeps Anki up to date, and how that last went.
 *
 * Two switches, because they are two directions (`docs/features/anki.md`): the vocabulary goes out a
 * minute after it changes, and review state comes back every hour. Both are the server's own work;
 * Anki on a device sees a push the next time it syncs.
 *
 * What the panel says follows the job stream, so "Running now" becomes the outcome when it lands,
 * without the panel being opened again.
 */

/** The newer of what the panel was told when it opened and what the stream has heard since. */
function newest(read: Job | null, heard: Job | undefined): Job | null {
  if (!heard) return read;
  if (!read || heard.id === read.id || heard.createdAt >= read.createdAt) return heard;
  return read;
}

function when(instant: string | null | undefined): string {
  if (!instant) return "";
  const at = new Date(instant);
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleString();
}

/** What a finished or waiting job says, in a line. A failure carries its own sentence. */
function outcome(job: Job | null, never: string): string {
  if (!job) return never;
  if (job.state === "queued") {
    return job.notBefore ? `Waiting until ${when(job.notBefore)}.` : "Waiting to start.";
  }
  if (job.state === "running") return "Running now.";
  const finished = job.finishedAt ? ` ${when(job.finishedAt)}` : "";
  if (job.state === "done") {
    const pushed = job.steps.find((step) => step.name === "anki.push")?.detail;
    const read = job.steps.find((step) => step.name === "anki.pull")?.detail;
    const counts = pushed && "created" in pushed
      ? ` ${pushed.created} new, ${pushed.updated} changed.`
      : read && "written" in read ? ` ${read.written} study states changed, ${read.reviewsAdded} reviews added.` : "";
    return `Finished${finished}.${counts}`;
  }
  return `${job.state === "failed" ? "Failed" : "Cancelled"}${finished}${job.message ? `: ${job.message}` : "."}`;
}

export default function AnkiPanel({ onNotify }: { onNotify(message: string): void }) {
  const { value: status, error, set } = useServerSetting(SETTINGS.anki);
  const [asking, setAsking] = useState<"push" | "pull" | null>(null);
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);

  const apply = async (changes: { push?: boolean; pull?: boolean }) => {
    const before = status;
    if (!before) return;
    set({ ...before, ...changes });
    try {
      set(await backendSession.saveAnkiSettings(changes));
    } catch (error) {
      set(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    }
  };

  const now = async (what: "push" | "pull") => {
    setAsking(what);
    try {
      jobStream.apply(await backendSession.ankiNow(what));
    } catch (error) {
      onNotify(error instanceof AcervoApiError ? error.message : "Anki could not be asked just now.");
    } finally {
      setAsking(null);
    }
  };

  if (!status) return error ? <Notice>{error}</Notice> : <Placeholder rows={2} />;

  const lastPush = newest(status.lastPush, jobFor(live, "anki.push", "push"));
  const lastPull = newest(status.lastPull, jobFor(live, "anki.pull", "pull"));
  const off = !status.configured;
  return <>
    {off && <Notice>This server has no Anki sync server behind it, so there is nothing to keep up to date.</Notice>}
    <Group title="Your words, out to Anki" foot="Your review progress in Anki is never touched.">
      <Toggle
        label="Send changes to Anki" hint="A minute after you stop editing"
        checked={status.push} disabled={off} onChange={(on) => void apply({ push: on })}
      />
      <Row label="Last push" hint={outcome(lastPush, "None yet.")}>
        <button type="button" className="tb-btn" disabled={off || asking !== null} onClick={() => void now("push")}>
          {asking === "push" ? "Pushing…" : "Push now"}
        </button>
      </Row>
    </Group>
    <Group title="Your reviews, back from Anki">
      <Toggle
        label="Read your reviews every hour" hint="Each push reads them too"
        checked={status.pull} disabled={off} onChange={(on) => void apply({ pull: on })}
      />
      <Row label="Last read" hint={outcome(lastPull, "None yet.")}>
        <button type="button" className="tb-btn" disabled={off || asking !== null} onClick={() => void now("pull")}>
          {asking === "pull" ? "Reading…" : "Read now"}
        </button>
      </Row>
    </Group>
  </>;
}
