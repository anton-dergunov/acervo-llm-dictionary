/* Test helpers for the pages that choose voices: a voice as a row declares it, and the Settings
   window's sub-page slot, which those pages open into. Imported by tests only. */

import { useState, type ReactNode } from "react";
import type { VoiceMatch, VoiceOption, VoiceReader } from "../api";
import { SubPageContext, type SubPage } from "./kit";

export function voice(name: string, locale: string | null, match: VoiceMatch, extra: Partial<VoiceOption> = {}): VoiceOption {
  return { name, locale, gender: null, note: null, match, ...extra };
}

export function reader(provider: string, model: string, option: VoiceOption | null): VoiceReader {
  return { provider, providerLabel: "Google Cloud Text-to-Speech", model, voice: option };
}

/** The window's sub-page slot, as `Settings.tsx` provides it. */
export function SubPages({ children }: { children: ReactNode }) {
  const [sub, setSub] = useState<SubPage | null>(null);
  return <SubPageContext.Provider value={{ sub, open: setSub, close: () => setSub(null) }}>
    {sub && <h3>{sub.title}</h3>}
    {children}
  </SubPageContext.Provider>;
}
