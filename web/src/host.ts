/**
 * The Mac application's own settings, as Settings ▸ General shows them.
 *
 * Whether Acervo opens at login, how it takes new versions of itself and which server it belongs to
 * are facts about this copy of the application, and the application keeps them. This page reads
 * them through the bridge and asks the application to change them; it stores none of them. The
 * application tells the page when they change — a download's progress, a build that arrived — by
 * calling `window.acervo.hostState`.
 */

import { useEffect, useState } from "react";
import { nativeCall } from "./session";

export interface HostUpdate {
  state: "idle" | "checking" | "downloading" | "installing" | "failed";
  /** 0–1 while downloading. */
  progress?: number;
  /** The failure's sentence, or a line about the last check. */
  message?: string | null;
  /** A newer build the server offers. */
  available?: string | null;
  /** A build already installed, which starts when Acervo restarts. */
  pendingBuild?: string | null;
  lastCheck?: string | null;
}

export interface HostState {
  serverURL: string;
  openAtLogin: boolean;
  showWindowAtLogin: boolean;
  automaticChecks: boolean;
  automaticInstall: boolean;
  version: string;
  update: HostUpdate;
}

export type HostSetting = "openAtLogin" | "showWindowAtLogin" | "automaticChecks" | "automaticInstall";

const EVENT = "acervo-host-state";

/** What the application calls, through `window.acervo.hostState`, whenever its state changes. */
export function receiveHostState(state: HostState) {
  window.dispatchEvent(new CustomEvent<HostState>(EVENT, { detail: state }));
}

export const hostBridge = {
  state: () => nativeCall<HostState>("hostSettings"),
  set: (name: HostSetting, value: boolean) => nativeCall<HostState>("setHostSetting", { name, value }),
  checkForUpdates: () => nativeCall<HostState>("checkForUpdates"),
  installUpdate: () => nativeCall<HostState>("installUpdate"),
  restartNow: () => nativeCall<HostState>("restartNow")
};

/** The application's settings, kept current; null until the first answer. */
export function useHostState(onFailure: (message: string) => void): [HostState | null, (state: HostState) => void] {
  const [state, setState] = useState<HostState | null>(null);
  useEffect(() => {
    let live = true;
    void hostBridge.state()
      .then((answer) => { if (live) setState(answer); })
      .catch((error: unknown) => onFailure(error instanceof Error ? error.message : "The application did not answer."));
    const changed = (event: Event) => setState((event as CustomEvent<HostState>).detail);
    window.addEventListener(EVENT, changed);
    return () => { live = false; window.removeEventListener(EVENT, changed); };
  }, []);
  return [state, setState];
}
