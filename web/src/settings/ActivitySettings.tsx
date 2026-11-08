/**
 * Settings ▸ Activity: when the nightly run happens, what the server is doing, and what it could not
 * finish.
 *
 * The schedule comes first because it is the only thing here that is a setting; the rest is a
 * record. One timer rather than one per job, because steps in sequence can never compete for the same
 * allowance — everything else the server does is started by something happening, not by the clock.
 * The server does the work whether or not anyone is looking, so the record is a window onto its jobs,
 * not a queue of this device's own. Cancel stops a job at its next check; Try again asks for a new
 * one; Dismiss hides a finished one.
 */

import { useSyncExternalStore } from "react";
import { AcervoApiError, backendSession, type Job } from "../api";
import { isOpen, jobStream } from "../jobs";
import type { ReplicaSnapshot } from "../repository";
import { stripOf } from "../ProgressStrip";
import { SETTINGS, useServerSetting } from "./cache";
import { Divider, Group, Notice, Placeholder, Row, Select, Toggle, Value } from "./kit";

const STEPS: Record<string, { title: string; hint: string }> = {
  "corpus.update": { title: "Update recorded speech", hint: "New videos from your clip channels" }
};

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
  music: "Saving music",
  "music.samples": "Preparing style samples",
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
const RETRYABLE = new Set(["enrich", "image.redraw", "image.rebrief", "loop", "music", "story"]);

function when(instant: string | null | undefined): string {
  if (!instant) return "";
  const at = new Date(instant);
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
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
  const held = useServerSetting(SETTINGS.jobs);
  const schedule = useServerSetting(SETTINGS.schedule);

  const failure = (error: unknown, fallback: string) =>
    onNotify(error instanceof AcervoApiError ? error.message : fallback);

  const plan = async (changes: { hour?: number; steps?: Record<string, boolean> }) => {
    const before = schedule.value;
    if (!before) return;
    schedule.set({ ...before, ...changes, steps: { ...before.steps, ...(changes.steps ?? {}) } });
    try { schedule.set(await backendSession.saveScheduleSettings(changes)); }
    catch (error) { schedule.set(before); failure(error, "That change was not saved."); }
  };

  const act = async (action: () => Promise<Job>, fallback: string) => {
    try {
      const job = await action();
      jobStream.apply(job);
      if (held.value) held.set(merged(held.value, [job]));
    } catch (error) {
      failure(error, fallback);
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

  const jobs = held.value ? merged(held.value, live.bySubject.values()) : [];
  const open = jobs.filter(isOpen);
  const failed = jobs.filter((job) => job.state === "failed");
  const finished = jobs.filter((job) => job.state === "done" || job.state === "cancelled").slice(0, 10);

  const row = (job: Job) => {
    const line = stripOf(job);
    const detail = line?.failure ?? line?.phases.map((phase) => phase.text).join(" · ") ?? "";
    return <Row key={job.id} label={describeJob(job, snapshot)} hint={detail || when(job.finishedAt ?? job.createdAt)}>
      {isOpen(job) && !job.cancelRequested
        && <button type="button" className="tb-btn" onClick={() => cancel(job)}>Cancel</button>}
      {job.state === "failed" && RETRYABLE.has(job.kind)
        && <button type="button" className="tb-btn" onClick={() => retry(job)}>Try again</button>}
      {!isOpen(job) && <button type="button" className="tb-btn" onClick={() => dismiss(job)}>Dismiss</button>}
    </Row>;
  };

  const nightly = schedule.value;
  const last = nightly?.lastRun;
  return <>
    {nightly ? <Group title="Nightly run">
      <Select
        label="Run at" hint={`${nightly.timezone} · next ${when(nightly.nextRunAt)}`}
        value={String(nightly.hour)}
        options={Array.from({ length: 24 }, (_, hour) => ({ value: String(hour), label: `${String(hour).padStart(2, "0")}:00` }))}
        onChange={(hour) => void plan({ hour: Number(hour) })}
      />
      {Object.entries(nightly.steps).map(([name, on]) => {
        const step = STEPS[name] ?? { title: name, hint: "" };
        return <Toggle
          key={name} label={step.title} hint={step.hint} checked={on}
          onChange={(next) => void plan({ steps: { [name]: next } })}
        />;
      })}
      {last
        ? <Row
            label="Last run"
            hint={`${when(last.finishedAt ?? last.createdAt)} · ${last.state === "done" ? "finished" : last.state}`
              + (last.message ? `: ${last.message}` : "")}
          />
        : <Row label="Last run"><Value>Not yet</Value></Row>}
    </Group> : schedule.error ? <Notice>{schedule.error}</Notice> : <Placeholder rows={3} />}

    <Divider>Recent activity</Divider>

    {held.value === undefined && (held.error ? <Notice>{held.error}</Notice> : <Placeholder rows={2} />)}
    {held.value !== undefined && <>
      <Group title="In progress">
        {open.length ? open.map(row) : <Row label="Nothing is running" />}
      </Group>
      {failed.length > 0 && <Group title="Could not finish">{failed.map(row)}</Group>}
      {finished.length > 0 && <Group title="Finished recently">{finished.map(row)}</Group>}
    </>}
  </>;
}
