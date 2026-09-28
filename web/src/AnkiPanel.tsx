import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type AnkiStatus, type Job } from "./api";

/**
 * Settings ▸ Anki: whether the server keeps Anki up to date, and how that last went.
 *
 * Two switches, because they are two directions (`docs/features/anki.md`): the vocabulary goes out a
 * minute after it changes, and review state comes back every hour. Both are the server's own work;
 * Anki on a device sees a push the next time it syncs.
 */

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
  const [status, setStatus] = useState<AnkiStatus | null>(null);
  const [failed, setFailed] = useState("");
  const [asking, setAsking] = useState<"push" | "pull" | null>(null);

  const read = () => backendSession.ankiStatus()
    .then(setStatus)
    .catch((error: unknown) => setFailed(error instanceof AcervoApiError
      ? error.message : "This setting lives on the server, which could not be reached."));

  useEffect(() => { void read(); }, []);

  const apply = async (changes: { push?: boolean; pull?: boolean }) => {
    const before = status;
    if (!before) return;
    setStatus({ ...before, ...changes });
    try {
      setStatus(await backendSession.saveAnkiSettings(changes));
    } catch (error) {
      setStatus(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    }
  };

  const now = async (what: "push" | "pull") => {
    setAsking(what);
    try {
      await backendSession.ankiNow(what);
      await read();
    } catch (error) {
      onNotify(error instanceof AcervoApiError ? error.message : "Anki could not be asked just now.");
    } finally {
      setAsking(null);
    }
  };

  if (failed) return <section className="config-section">
    <h3>Anki</h3>
    <p className="config-help warn">{failed}</p>
  </section>;

  if (!status) return <section className="config-section">
    <h3>Anki</h3>
    <p className="config-help" role="status">Reading how Anki is kept up to date…</p>
  </section>;

  return <section className="config-section">
    <h3>Anki</h3>
    <p className="config-help">
      Your words go to Anki as cards and your reviews come back as study state. Anki on your
      tablet picks up a change the next time it syncs.
    </p>
    {!status.configured && <p className="config-help warn">
      This server has no Anki sync server behind it, so there is nothing to keep up to date.
    </p>}

    <label className="config-switch">
      <input
        type="checkbox" checked={status.push} disabled={!status.configured}
        onChange={(event) => void apply({ push: event.target.checked })}
      />
      <span>
        <strong>Send changes to Anki</strong>
        <span>A minute after you stop editing, the words you changed are updated in Anki, new
          ones added, and their pictures and recordings with them. Your review progress is never
          touched.</span>
      </span>
    </label>
    <p className="config-help">Last push: {outcome(status.lastPush, "none yet.")}</p>
    <div className="sync-actions">
      <button className="tb-btn" disabled={!status.configured || asking !== null}
        onClick={() => void now("push")}>
        {asking === "push" ? "Pushing…" : "Push now"}
      </button>
    </div>

    <label className="config-switch">
      <input
        type="checkbox" checked={status.pull} disabled={!status.configured}
        onChange={(event) => void apply({ pull: event.target.checked })}
      />
      <span>
        <strong>Read your reviews every hour</strong>
        <span>Brings Anki's review state and history back into Acervo. Each push reads it
          too.</span>
      </span>
    </label>
    <p className="config-help">Last hourly read: {outcome(status.lastPull, "none yet.")}</p>
    <div className="sync-actions">
      <button className="tb-btn" disabled={!status.configured || asking !== null}
        onClick={() => void now("pull")}>
        {asking === "pull" ? "Reading…" : "Read now"}
      </button>
    </div>
  </section>;
}
