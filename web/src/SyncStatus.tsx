import { useState } from "react";
import { AlertIcon, CloudIcon, CloudOffIcon, SyncIcon } from "./icons";
import { relativeTime } from "./format";
import { describeStartup, startupTimings } from "./startup";
import { Action, Group, Notice, Row } from "./settings/kit";
import type { SyncStatus } from "./sync";

/** Typed, not clicked, when the copy being discarded may be the only complete one left. */
const CONFIRMATION = "REPLACE";

type Tone = "synced" | "syncing" | "offline" | "blocked";

const TONES: Record<SyncStatus["state"], Tone> = {
  idle: "synced", syncing: "syncing", offline: "offline", serverError: "blocked",
  blocked: "blocked", datasetChanged: "blocked", signedOut: "offline"
};

const LABELS: Record<SyncStatus["state"], string> = {
  idle: "Up to date with the server",
  syncing: "Checking the server for changes",
  offline: "Offline — showing the copy stored on this device",
  // Distinct from offline on purpose. The server answering and failing is a fault someone has to
  // go and fix; calling it "offline" points the owner at their network instead of at the server.
  serverError: "The server is reachable but returned an error",
  blocked: "Synchronisation stopped: this app needs updating",
  datasetChanged: "Synchronisation stopped: the server database changed",
  signedOut: "Not signed in"
};

/** The topbar indicator. Deliberately quiet: offline is a normal state here, not a failure. */
export function SyncChip({ status, onOpen }: { status: SyncStatus; onOpen(): void }) {
  const tone = TONES[status.state];
  return <button className={`tb-btn sync-chip ${tone}`} onClick={onOpen} aria-label={LABELS[status.state]} title={LABELS[status.state]}>
    {tone === "syncing" ? <SyncIcon /> : tone === "blocked" ? <AlertIcon /> : tone === "offline" ? <CloudOffIcon /> : <CloudIcon />}
  </button>;
}

/** The detail, shown inside Settings — where someone goes to find out why a device stopped. */
export function SyncPanel({ status, lexemeCount, onSyncNow, onDownloadAgain }: {
  status: SyncStatus;
  lexemeCount: number;
  onSyncNow(): void;
  onDownloadAgain(): void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const timings = startupTimings();
  const stopped = status.state === "blocked" || status.state === "datasetChanged";
  // Normally this discards a cache the server can rebuild. After the server database changed
  // identity it may instead discard the most complete surviving copy, so the gate is raised.
  const irreversible = status.state === "datasetChanged";
  const ready = !irreversible || typed.trim() === CONFIRMATION;

  function download() {
    setConfirming(false);
    setTyped("");
    onDownloadAgain();
  }
  return <>
    <Group foot={timings ? describeStartup(timings) : undefined}>
      <Row
        label={LABELS[status.state]}
        hint={`Received ${relativeTime(status.lastPulledAt)}`
          + (status.lastWroteAt ? ` · last change saved ${relativeTime(status.lastWroteAt)}` : "")
          + (status.cursor > 0 ? ` · revision ${status.cursor}` : "")}
      />
      <Action onClick={onSyncNow} disabled={status.state === "syncing" || stopped}>Sync now</Action>
    </Group>
    {!status.persistent && <Notice>
      This device could not open its local storage, so your words are held only until you reload.
    </Notice>}
    {status.state === "datasetChanged" && <Notice>
      The server’s database changed. Nothing here has been touched, and this copy may be the more
      complete one: replace it with the server’s, or rebuild the server from this device first.
    </Notice>}
    {status.message && status.state !== "idle" && <p className="pref-foot sync-message">{status.message}</p>}

    {!confirming && <Group foot="Downloads everything again from the server.">
      <Action danger onClick={() => setConfirming(true)}>Replace this device's copy with the server's…</Action>
    </Group>}
    {confirming && <section className="pref-group" aria-label="Replace this device's copy">
      <div className="danger-zone">
        <p role="alert">
          This deletes the {lexemeCount} {lexemeCount === 1 ? "entry" : "entries"} held here and
          downloads the server's copy in their place.
          {irreversible
            ? " The server database was rebuilt, so it may hold fewer than this device does. Nothing here can be recovered afterwards."
            : " Nothing is lost: the server has everything this device does."}
        </p>
        {irreversible && <>
          <label htmlFor="replace-confirmation">Type {CONFIRMATION} to confirm</label>
          <input
            id="replace-confirmation" value={typed} autoComplete="off"
            onChange={(event) => setTyped(event.target.value)}
          />
        </>}
        <div className="sync-actions">
          <button type="button" className="tb-btn" onClick={() => { setConfirming(false); setTyped(""); }}>Cancel</button>
          <button type="button" className="tb-btn danger" disabled={!ready} onClick={download}>Replace this device's copy</button>
        </div>
      </div>
    </section>}
  </>;
}
