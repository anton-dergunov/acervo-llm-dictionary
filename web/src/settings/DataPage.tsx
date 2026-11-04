/**
 * Settings ▸ Data: export, import, and deleting every word.
 *
 * Delete All Words is the one action here that re-syncing cannot undo, so it asks for the word
 * typed rather than a click, and the Mac menu's "Delete All Words…" opens straight onto that.
 */

import { useState } from "react";
import type { ReplicaSnapshot } from "../repository";
import { syncEngine } from "../sync";
import { Action, Group } from "./kit";
import { ExportPanel, ImportPanel } from "./TransferPanel";

const CONFIRMATION = "DELETE";

export default function DataPage({ snapshot, arm, onNotify, onChanged }: {
  snapshot: ReplicaSnapshot | null;
  arm?: "delete" | null;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  const [confirming, setConfirming] = useState(arm === "delete");
  const [typed, setTyped] = useState("");
  const [working, setWorking] = useState(false);
  const lexemes = snapshot?.lexemes.filter((lexeme) => !lexeme.deleted).length ?? 0;

  async function deleteEverything() {
    setWorking(true);
    try { await syncEngine.resetWords(); }
    catch (error) { onNotify(error instanceof Error ? error.message : "The words could not be deleted."); }
    finally { setWorking(false); setConfirming(false); setTyped(""); }
  }

  return <>
    {snapshot && <ExportPanel snapshot={snapshot} />}
    <ImportPanel onChanged={onChanged} />

    {!confirming && <Group foot="Removes every entry from the server and from all your devices.">
      <Action danger onClick={() => setConfirming(true)}>Delete all words…</Action>
    </Group>}
    {confirming && <section className="pref-group" aria-label="Delete all words">
      <div className="danger-zone">
        <h3>Delete all words</h3>
        <p role="alert">
          This deletes <strong>{lexemes.toLocaleString()} {lexemes === 1 ? "entry" : "entries"}</strong> and
          everything attached to them, on every device. Export first: syncing cannot bring them back.
        </p>
        <label htmlFor="delete-confirmation">Type {CONFIRMATION} to confirm</label>
        <input
          id="delete-confirmation" value={typed} autoComplete="off"
          onChange={(event) => setTyped(event.target.value)}
        />
        <div className="sync-actions">
          <button type="button" className="tb-btn" onClick={() => { setConfirming(false); setTyped(""); }}>Cancel</button>
          <button
            type="button" className="tb-btn danger" disabled={typed.trim() !== CONFIRMATION || working}
            onClick={() => void deleteEverything()}
          >Delete all words</button>
        </div>
      </div>
    </section>}
  </>;
}
