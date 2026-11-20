import { useEffect, useState } from "react";

/**
 * The IPA panel's open layout choices, tried by hand before one is kept: how it opens on a phone,
 * and whether a mark is explained inside its letter's row or on a row of its own. Per device, in
 * local storage, like the editor's preferences: a trial, not a setting of the vocabulary. Set in
 * Settings ▸ Reading; removed once the owner has chosen (docs/plans/languages/ipa-guide.md).
 */

export type PhoneLayout = "sheet" | "full" | "inline";
export type MarksLayout = "inside" | "rows";
export interface IpaTrial { phone: PhoneLayout; marks: MarksLayout }

const KEYS = { phone: "acervo-ipa-trial-phone", marks: "acervo-ipa-trial-marks" } as const;
const CHOICES = { phone: ["sheet", "full", "inline"], marks: ["inside", "rows"] } as const;
const DEFAULTS: IpaTrial = { phone: "sheet", marks: "inside" };
const EVENT = "acervo-ipa-trial";

function read<K extends keyof IpaTrial>(name: K): IpaTrial[K] {
  try {
    const stored = localStorage.getItem(KEYS[name]);
    return (CHOICES[name] as readonly string[]).includes(stored ?? "") ? stored as IpaTrial[K] : DEFAULTS[name];
  } catch {
    return DEFAULTS[name];
  }
}

export function ipaTrial(): IpaTrial {
  return { phone: read("phone"), marks: read("marks") };
}

export function setIpaTrial<K extends keyof IpaTrial>(name: K, value: IpaTrial[K]): void {
  try { localStorage.setItem(KEYS[name], value); } catch { /* a trial, not data */ }
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function useIpaTrial(): IpaTrial {
  const [trial, setTrial] = useState(ipaTrial);
  useEffect(() => {
    const changed = () => setTrial(ipaTrial());
    window.addEventListener(EVENT, changed);
    return () => window.removeEventListener(EVENT, changed);
  }, []);
  return trial;
}
