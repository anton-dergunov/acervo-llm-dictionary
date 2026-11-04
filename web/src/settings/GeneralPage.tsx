/**
 * Settings ▸ General: who is signed in, how this copy of Acervo is kept up to date, and — on the
 * Mac — the application's own settings, which used to be a second Settings window of its own.
 *
 * In a browser the app updates as a web app does. On the Mac the application updates itself and
 * knows its server, so this page shows its settings and asks it to change them (`host.ts`); it keeps
 * none of them itself.
 */

import { useEffect, useState } from "react";
import type { CaptureHealth } from "../api";
import { hostBridge, useHostState, type HostSetting, type HostState } from "../host";
import { fetchMacRelease, type MacRelease } from "../macRelease";
import { installUpdate, isNativeHost, shouldOfferMacApplication, type UpdateStage } from "../pwa";
import type { ReplicaSnapshot } from "../repository";
import { appVersionLabel } from "../version";
import { Action, Group, Notice, Placeholder, Row, Toggle, Value } from "./kit";

function count(n: number, one: string, many: string) {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

export default function GeneralPage({ update, email, snapshot, captureHealth, onSignOut, onNotify }: {
  update?: UpdateStage;
  email: string;
  snapshot: ReplicaSnapshot | null;
  captureHealth?: CaptureHealth;
  onSignOut(): void;
  onNotify(message: string): void;
}) {
  const native = isNativeHost();
  const lexemes = snapshot?.lexemes.filter((lexeme) => !lexeme.deleted).length ?? 0;
  const topics = snapshot?.topics.filter((topic) => !topic.deleted).length ?? 0;

  return <>
    <section className="pref-group" aria-label="Account">
      <div className="pref-card">
        <div className="pref-row">
          <span className="pref-avatar" aria-hidden="true">{email.charAt(0).toUpperCase()}</span>
          <span className="pref-text">
            <span className="pref-label">Signed in as {email}</span>
            <span className="pref-hint">
              {count(lexemes, "entry", "entries")} across {count(topics, "topic", "topics")} on this device
            </span>
          </span>
        </div>
      </div>
    </section>

    {captureHealth && !captureHealth.available && <Notice>
      This server cannot build entries: {captureHealth.reason}. Providers says what it can use.
    </Notice>}

    {native ? <MacApplication onNotify={onNotify} /> : <WebUpdates update={update} />}

    <Group>
      {/* Changing server is signing in again: a token belongs to the server that issued it, and the
          sign-in screen is where the address is asked for. */}
      {native && <Action onClick={onSignOut}>Change server…</Action>}
      <Action danger onClick={onSignOut}>Sign out</Action>
    </Group>
  </>;
}

function WebUpdates({ update }: { update?: UpdateStage }) {
  const offerMac = shouldOfferMacApplication();
  const [release, setRelease] = useState<MacRelease | null>();
  const [releaseFailed, setReleaseFailed] = useState(false);

  useEffect(() => {
    if (!offerMac) return;
    const controller = new AbortController();
    void fetchMacRelease(controller.signal)
      .then(setRelease)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setReleaseFailed(true);
      });
    return () => controller.abort();
  }, [offerMac]);

  return <Group title="Updates" foot={`Version ${appVersionLabel()}`}>
    {update === "ready" && <Row label="An update is ready" hint="Acervo reopens with the new version">
      <button type="button" className="tb-btn primary" onClick={() => void installUpdate()}>Update Acervo</button>
    </Row>}
    {update === "downloading" && <Row label="Downloading an update…" hint="You can keep using Acervo meanwhile" />}
    {!update && <Row label="Acervo is up to date" hint="The newest version this server offers" />}
    {offerMac && (release
      ? <Row label="Acervo for macOS" hint={`Version ${release.version}, build ${release.build}`}>
          <a className="tb-btn" href={release.url} download={release.file}>Download Acervo for macOS</a>
        </Row>
      : <Row label="Acervo for macOS" hint={releaseFailed ? "Could not be checked right now"
          : release === null ? "This server has not published one yet" : "Checking…"} />)}
  </Group>;
}

function MacApplication({ onNotify }: { onNotify(message: string): void }) {
  const [state, setState] = useHostState(onNotify);
  if (!state) return <Placeholder rows={5} />;

  /* Every change goes to the application and what it answers is what is shown: a login item can be
     refused by the system, and the switch must not claim otherwise. */
  const ask = (call: () => Promise<HostState>) => {
    void call().then(setState).catch((error: unknown) =>
      onNotify(error instanceof Error ? error.message : "The application did not answer."));
  };
  const set = (name: HostSetting) => (value: boolean) => ask(() => hostBridge.set(name, value));

  return <>
    <Group title="Updates" foot={`Version ${state.version}`}>
      <UpdateRow state={state} ask={ask} />
      <Toggle label="Check for updates automatically" checked={state.automaticChecks} onChange={set("automaticChecks")} />
      <Toggle
        label="Install updates automatically" hint="They start the next time Acervo opens"
        checked={state.automaticInstall} disabled={!state.automaticChecks} onChange={set("automaticInstall")}
      />
    </Group>
    <Group title="This Mac">
      <Row label="Server"><Value mono>{state.serverURL.replace(/^https?:\/\//, "") || "Not set"}</Value></Row>
      <Toggle label="Open Acervo at login" checked={state.openAtLogin} onChange={set("openAtLogin")} />
      <Toggle
        label="Show the window at login" hint="Off, Acervo starts in the menu bar"
        checked={state.showWindowAtLogin} disabled={!state.openAtLogin} onChange={set("showWindowAtLogin")}
      />
    </Group>
  </>;
}

function UpdateRow({ state, ask }: { state: HostState; ask(call: () => Promise<HostState>): void }) {
  const { update } = state;
  const button = (label: string, call: () => Promise<HostState>, primary = false) =>
    <button type="button" className={`tb-btn${primary ? " primary" : ""}`} onClick={() => ask(call)}>{label}</button>;

  switch (update.state) {
    case "checking": return <Row label="Checking for updates…" />;
    case "downloading": return <Row label={`Downloading the update… ${Math.round((update.progress ?? 0) * 100)}%`} />;
    case "installing": return <Row label="Installing the update…" />;
    case "failed": return <Row label="The update did not finish" hint={update.message}>
      {button("Try again", hostBridge.checkForUpdates)}
    </Row>;
    case "idle":
      if (update.pendingBuild) return <Row label={`Build ${update.pendingBuild} is installed`} hint="It starts when Acervo restarts">
        {button("Restart Now", hostBridge.restartNow, true)}
      </Row>;
      if (update.available) return <Row label={`Build ${update.available} is available`} hint={`This Mac runs ${state.version}`}>
        {/* The label names the restart, so nothing has to confirm it afterwards. */}
        {button("Update and Restart", hostBridge.installUpdate, true)}
      </Row>;
      return <Row
        label="Acervo is up to date"
        hint={update.message ?? (update.lastCheck ? `Last checked ${new Date(update.lastCheck).toLocaleString()}` : undefined)}
      >{button("Check Now", hostBridge.checkForUpdates)}</Row>;
  }
}
