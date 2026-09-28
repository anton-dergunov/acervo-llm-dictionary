import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { AcervoApiError, backendSession, type Job, type ScheduleSettings } from "./api";
import { isOpen, jobStream } from "./jobs";
import type { ReplicaSnapshot } from "./repository";
import { stripOf } from "./ProgressStrip";

/**
 * Settings ▸ Activity: what the server is doing and what it could not finish.
 *
 * The server does the work whether or not anyone is looking, so this is a window onto its job
 * record, not a queue of this device's own. Cancel stops a job at its next check; Try again asks for
 * a new one; Dismiss hides a finished one.
 */

const KIND_LABELS: Record<string, string> = {
  enrich: "Filling in",
  capture: "Capturing",
  "image.redraw": "Redrawing a picture",
  "image.rebrief": "Rewriting picture briefs",
  nightly: "Nightly run",
  "corpus.update": "Updating recorded speech",
  "anki.push": "Sending changes to Anki",
  "anki.pull": "Reading Anki's review state",
  loop: "Making a loop",
  story: "Making a story",
  "map.name": "Naming the map's regions"
};

export function describeJob(job: Job, snapshot: ReplicaSnapshot | null): string {
  const kind = KIND_LABELS[job.kind] ?? job.kind;
  if (job.subject?.kind !== "lexeme" || !snapshot) return kind;
  const word = snapshot.lexemes.find((lexeme) => lexeme.id === job.subject?.id);
  return word ? `${kind} “${word.headword}”` : kind;
}

/* The kinds a person can ask for again from here. A capture is resubmitted by its transport. */
const RETRYABLE = new Set(["enrich", "image.redraw", "image.rebrief", "loop", "story"]);

function when(instant: string | null): string {
  if (!instant) return "";
  const at = new Date(instant);
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleString();
}

function merged(held: Job[], heard: Iterable<Job>): Job[] {
  const byId = new Map(held.map((job) => [job.id, job]));
  for (const job of heard) byId.set(job.id, job);
  return [...byId.values()]
    .filter((job) => !job.dismissed)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

export default function ActivitySettings({ snapshot, onNotify }: {
  snapshot: ReplicaSnapshot | null;
  onNotify(message: string): void;
}) {
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const [held, setHeld] = useState<Job[] | null>(null);
  const [nightly, setNightly] = useState<ScheduleSettings | null>(null);
  const [problem, setProblem] = useState("");

  const load = useCallback(() => {
    backendSession.jobs(false)
      .then((jobs) => { setHeld(jobs); setProblem(""); })
      .catch((error: unknown) => setProblem(error instanceof AcervoApiError
        ? error.message : "The server's activity could not be read."));
  }, []);

  useEffect(() => { load(); }, [load]);

  /* The one thing here that is not started by something happening. Read beside the jobs so this
     page answers "is anything overdue" as well as "is anything running". */
  useEffect(() => {
    backendSession.scheduleSettings().then(setNightly).catch(() => undefined);
  }, []);

  const act = async (action: () => Promise<Job>, failure: string) => {
    try {
      const job = await action();
      jobStream.apply(job);
      setHeld((jobs) => jobs && merged(jobs, [job]));
    } catch (error) {
      onNotify(error instanceof AcervoApiError ? error.message : failure);
    }
  };

  const retry = (job: Job) => job.subject && void act(
    () => backendSession.enqueueJob({
      kind: job.kind, subject: job.subject!, input: job.input as Record<string, string>
    }),
    "That could not be asked for again."
  );
  const cancel = (job: Job) => void act(() => backendSession.cancelJob(job.id), "That could not be cancelled.");
  const dismiss = (job: Job) => void act(() => backendSession.dismissJob(job.id), "That could not be dismissed.");

  const jobs = held ? merged(held, live.bySubject.values()) : [];
  const open = jobs.filter(isOpen);
  const failed = jobs.filter((job) => job.state === "failed");
  const finished = jobs.filter((job) => job.state === "done" || job.state === "cancelled").slice(0, 10);

  const row = (job: Job) => {
    const line = stripOf(job);
    const detail = line?.failure ?? line?.phases.map((phase) => phase.text).join(" · ") ?? "";
    return <li key={job.id} className="activity-row">
      <span className="activity-what">
        <strong>{describeJob(job, snapshot)}</strong>
        <span className="hint">{detail || when(job.finishedAt ?? job.createdAt)}</span>
      </span>
      <span className="activity-actions">
        {isOpen(job) && !job.cancelRequested
          && <button type="button" className="tb-btn" onClick={() => cancel(job)}>Cancel</button>}
        {job.state === "failed" && RETRYABLE.has(job.kind)
          && <button type="button" className="tb-btn" onClick={() => retry(job)}>Try again</button>}
        {!isOpen(job) && <button type="button" className="tb-btn" onClick={() => dismiss(job)}>Dismiss</button>}
      </span>
    </li>;
  };

  return <section className="config-section activity-settings">
    <h3>Activity</h3>
    <p className="config-help">
      What the server is doing for you. It works whether or not this window is open: a word you save
      gets its clips, pictures and recordings in the background.
    </p>
    {problem && <p className="config-help warn">{problem}</p>}
    {held === null && !problem && <p className="config-help" role="status">Reading the server's activity…</p>}
    {held !== null && <>
      <h4 className="config-subhead">In progress</h4>
      {open.length ? <ul className="activity-list">{open.map(row)}</ul>
        : <p className="config-help">Nothing is running.</p>}
      {failed.length > 0 && <>
        <h4 className="config-subhead">Could not finish</h4>
        <ul className="activity-list">{failed.map(row)}</ul>
      </>}
      {finished.length > 0 && <>
        <h4 className="config-subhead">Finished recently</h4>
        <ul className="activity-list">{finished.map(row)}</ul>
      </>}
      {nightly && <>
        <h4 className="config-subhead">Nightly run</h4>
        <p className="config-help">
          {nightly.lastRun
            ? `Last run ${nightly.lastRun.state === "done" ? "finished" : nightly.lastRun.state} `
              + `${when(nightly.lastRun.finishedAt ?? nightly.lastRun.createdAt)}. `
            : "It has not run yet. "}
          Next {when(nightly.nextRunAt)}, in Settings ▸ Schedule.
        </p>
      </>}
    </>}
  </section>;
}
