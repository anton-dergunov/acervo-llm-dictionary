import { useSyncExternalStore } from "react";

/**
 * The selection: words picked by hand to make something from — a loop or a story today.
 *
 * **This device's, and never synced.** It is a working pile rather than part of the vocabulary, so it
 * lives in local storage beside the other per-device state, not in the replicated graph, and it
 * touches no schema version. It survives changing topic, searching, opening an article or the map,
 * and reloading, which is the whole of what a selection has to do that a checkbox in one view could
 * not.
 *
 * **One selection per language, in the order the words were chosen**, because a loop and a story
 * are each in one language, and the first chosen are the ones a dialog uses when it cannot take them
 * all. The record carries the account it was made in: another account on this device reads an empty
 * selection and its first write replaces the record, the rule the replica already follows.
 *
 * An entry is a lexeme id and nothing else. What it is — its headword, whether it still exists — is
 * read from the replica when it is drawn (`selectedWords` in `selectors.ts`), so a word deleted
 * since simply stops appearing and nothing here ever needs repairing.
 */

const KEY = "acervo-word-selection";
const NONE: readonly string[] = Object.freeze([]);

interface Stored {
  ownerId: string;
  languages: Record<string, readonly string[]>;
}

let state: Stored = read();
const listeners = new Set<() => void>();

function read(): Stored {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ownerId: "", languages: {} };
    const parsed = JSON.parse(raw) as Partial<Stored>;
    const languages: Record<string, readonly string[]> = {};
    for (const [language, ids] of Object.entries(parsed.languages ?? {})) {
      if (Array.isArray(ids)) languages[language] = Object.freeze(ids.filter((id): id is string => typeof id === "string"));
    }
    return { ownerId: typeof parsed.ownerId === "string" ? parsed.ownerId : "", languages };
  } catch {
    // Unreadable is the same as empty: the selection is a convenience, never the only copy of anything.
    return { ownerId: "", languages: {} };
  }
}

function write(next: Stored): void {
  state = next;
  try { localStorage.setItem(KEY, JSON.stringify(next)); }
  catch { /* storage refused: the selection lasts this session instead */ }
  listeners.forEach((listener) => listener());
}

function set(ownerId: string, language: string, ids: readonly string[]): void {
  const languages = state.ownerId === ownerId ? { ...state.languages } : {};
  if (ids.length) languages[language] = Object.freeze([...ids]);
  else delete languages[language];
  write({ ownerId, languages });
}

/** The ids selected in one language, for one account, in the order they were chosen. */
export function selectedIds(ownerId: string, language: string): readonly string[] {
  if (!ownerId || state.ownerId !== ownerId) return NONE;
  return state.languages[language] ?? NONE;
}

/** Select a word, or unselect it if it is selected. Returns whether it is selected now. */
export function toggleSelected(ownerId: string, language: string, id: string): boolean {
  const ids = selectedIds(ownerId, language);
  const on = !ids.includes(id);
  set(ownerId, language, on ? [...ids, id] : ids.filter((one) => one !== id));
  return on;
}

/** Forget a language's selection, returning what it held so the toast can put it back. */
export function clearSelected(ownerId: string, language: string): readonly string[] {
  const before = selectedIds(ownerId, language);
  set(ownerId, language, []);
  return before;
}

/** Put a cleared selection back — Undo. */
export function restoreSelected(ownerId: string, language: string, ids: readonly string[]): void {
  set(ownerId, language, ids);
}

const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };

/* Another tab or window of this device changing the selection is this device changing it. */
if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key !== KEY) return;
    state = read();
    listeners.forEach((listener) => listener());
  });
}

export function useSelectedIds(ownerId: string, language: string): readonly string[] {
  return useSyncExternalStore(subscribe, () => selectedIds(ownerId, language));
}

/** For tests: start from what storage holds now. */
export function reloadSelectionForTests(): void {
  state = read();
  listeners.forEach((listener) => listener());
}
