import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type ScheduleSettings } from "./api";
import { describeJob } from "./ActivitySettings";

/**
 * Settings ▸ Schedule: one hour, and a switch per step of the nightly run.
 *
 * One timer rather than one per job, because steps in sequence can never compete for the same
 * allowance — so there is nothing here to stagger. Everything else the server does is started by
 * something happening, not by the clock.
 */

const STEP_LABELS: Record<string, { title: string; help: string }> = {
  "corpus.update": {
    title: "Update recorded speech",
    help: "Fetch what your enabled channels have published and rebuild the clip index. Words you "
      + "already have are never re-searched."
  }
};

function when(instant: string | null | undefined): string {
  if (!instant) return "";
  const at = new Date(instant);
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleString();
}

export default function SchedulePanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<ScheduleSettings | null>(null);
  const [failed, setFailed] = useState("");

  useEffect(() => {
    backendSession.scheduleSettings()
      .then(setSettings)
      .catch((error: unknown) => setFailed(error instanceof AcervoApiError
        ? error.message : "This setting lives on the server, which could not be reached."));
  }, []);

  const apply = async (changes: { hour?: number; steps?: Record<string, boolean> }) => {
    const before = settings;
    if (!before) return;
    setSettings({ ...before, ...changes, steps: { ...before.steps, ...(changes.steps ?? {}) } });
    try {
      setSettings(await backendSession.saveScheduleSettings(changes));
    } catch (error) {
      setSettings(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    }
  };

  if (failed) return <section className="config-section">
    <h3>Schedule</h3>
    <p className="config-help warn">{failed}</p>
  </section>;

  if (!settings) return <section className="config-section">
    <h3>Schedule</h3>
    <p className="config-help" role="status">Reading your schedule…</p>
  </section>;

  const last = settings.lastRun;
  return <section className="config-section">
    <h3>Schedule</h3>
    <p className="config-help">
      One run a night, for the work that really is time-based. Everything else — the clips, pictures
      and audio of a word you save — starts when you save it, not on a timer.
    </p>

    <label className="config-field">
      <span>Run at</span>
      <select
        value={String(settings.hour)}
        onChange={(event) => void apply({ hour: Number(event.target.value) })}
      >
        {Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>
          {`${String(hour).padStart(2, "0")}:00`}
        </option>)}
      </select>
    </label>
    <p className="config-help">
      Server time ({settings.timezone}). Next run {when(settings.nextRunAt)}. A night the server was
      down for runs once when it comes back; missed nights do not pile up.
    </p>

    {Object.entries(settings.steps).map(([name, on]) => {
      const label = STEP_LABELS[name] ?? { title: name, help: "" };
      return <label key={name} className="config-switch">
        <input
          type="checkbox" checked={on}
          onChange={(event) => void apply({ steps: { [name]: event.target.checked } })}
        />
        <span>
          <strong>{label.title}</strong>
          <span>{label.help}</span>
        </span>
      </label>;
    })}

    <h4 className="config-subhead">Last run</h4>
    {last ? <p className="config-help">
      {describeJob(last, null)} — {last.state === "done" ? "finished" : last.state}
      {last.finishedAt ? ` ${when(last.finishedAt)}` : ""}
      {last.message ? `. ${last.message}` : "."}
    </p> : <p className="config-help">It has not run yet.</p>}
  </section>;
}
