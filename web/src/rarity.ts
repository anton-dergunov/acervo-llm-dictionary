/**
 * How rare each word is in its language: wordfreq's Zipf figure, asked of the server once a session
 * per language (`GET /words/rarity`). It is a fact about the language rather than about a record, so
 * it is not replicated, and the make dialogs' Rare and the lists' Rarest share one answer.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession } from "./api";

const rarities = new Map<string, Promise<Record<string, number>>>();

export function resetRarityForTests(): void { rarities.clear(); }

export type Rarity =
  | { state: "idle" | "asking" }
  | { state: "ready"; zipf: Record<string, number> }
  | { state: "refused"; why: string };

/** The figures for one language, asked for only once `wanted`; a failed answer is asked again next time. */
export function useRarity(language: string, wanted: boolean): Rarity {
  const [rarity, setRarity] = useState<Rarity>({ state: "idle" });
  useEffect(() => {
    if (!wanted) return;
    let live = true;
    if (!rarities.has(language)) {
      const asked = backendSession.wordRarity(language).then((answer) => answer.zipf);
      asked.catch(() => rarities.delete(language));
      rarities.set(language, asked);
    }
    setRarity((now) => (now.state === "ready" ? now : { state: "asking" }));
    rarities.get(language)!.then(
      (zipf) => { if (live) setRarity({ state: "ready", zipf }); },
      (error: unknown) => {
        if (live) setRarity({ state: "refused", why: error instanceof AcervoApiError ? error.message : "How rare each word is could not be read." });
      }
    );
    return () => { live = false; };
  }, [language, wanted]);
  return rarity;
}
