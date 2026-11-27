import type { VocabularyGraph } from "./domain";
import { vocabularyFor, type TopicSelection } from "./selectors";

/**
 * Where you were, remembered per device, so a cold start reopens it.
 *
 * iOS evicts an installed web app it has not shown for a while, and reopening one used to land on
 * the first vocabulary's list whatever you had been reading. This is a convenience of this screen
 * rather than a fact about the vocabulary, so it lives in local storage beside the editor
 * preferences and never in the replica — and anything it names that is no longer there is dropped
 * rather than trusted.
 */
export interface Place {
  vocabularyId: string;
  topic: TopicSelection;
  openId: string | null;
}

const KEY = "acervo-last-place";

export function rememberPlace(place: Place): void {
  try { localStorage.setItem(KEY, JSON.stringify(place)); } catch { /* a convenience, not data */ }
}

/** Signing out forgets it with everything else the session left on this device. */
export function forgetPlace(): void {
  try { localStorage.removeItem(KEY); } catch { /* nothing to forget */ }
}

export function lastPlace(): Place | null {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<Place> | null;
    if (!stored || typeof stored.vocabularyId !== "string" || typeof stored.topic !== "string") return null;
    return {
      vocabularyId: stored.vocabularyId,
      topic: stored.topic,
      openId: typeof stored.openId === "string" ? stored.openId : null
    };
  } catch {
    return null;
  }
}

/**
 * The remembered place, as far as this graph still holds it: a vocabulary it no longer has means no
 * place at all, a topic that has gone falls back to all words, and a word that has gone, or is in
 * another vocabulary, is simply not reopened.
 */
export function placeIn(graph: VocabularyGraph, place: Place | null): Place | null {
  if (!place || !vocabularyFor(graph, place.vocabularyId)) return null;
  const topic = place.topic === "all" || place.topic === "inbox"
    || graph.topics.some((one) => one.id === place.topic && !one.deleted) ? place.topic : "all";
  const word = place.openId
    ? graph.lexemes.find((one) => one.id === place.openId && !one.deleted && one.vocabularyId === place.vocabularyId)
    : undefined;
  return { vocabularyId: place.vocabularyId, topic, openId: word ? word.id : null };
}
