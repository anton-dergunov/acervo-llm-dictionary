import { useEffect, useState } from "react";

/**
 * How the YAML surfaces present text, remembered per device.
 *
 * These describe this screen, not the vocabulary — a phone and a desktop want different answers —
 * so they live in local storage rather than the replicated graph, and they are set in Settings
 * rather than above the editor, where they were controls you had to step over on the way to work.
 *
 * Wrapping is the default: these documents are mostly prose, and a definition running off the right
 * edge is the common case. Scrolling stays available because YAML indentation is meaningful.
 */
export interface EditorPreferences {
  wrap: boolean;
  numbers: boolean;
}

const PREFERENCE_KEYS = { wrap: "acervo-editor-wrap", numbers: "acervo-editor-numbers" } as const;
const PREFERENCES_EVENT = "acervo-editor-preferences";

function readPreference(key: string, fallback: boolean): boolean {
  try {
    const stored = localStorage.getItem(key);
    return stored === null ? fallback : stored === "on";
  } catch {
    return fallback;
  }
}

export function editorPreferences(): EditorPreferences {
  return {
    wrap: readPreference(PREFERENCE_KEYS.wrap, true),
    numbers: readPreference(PREFERENCE_KEYS.numbers, false)
  };
}

export function setEditorPreference(name: keyof EditorPreferences, value: boolean): void {
  try { localStorage.setItem(PREFERENCE_KEYS[name], value ? "on" : "off"); } catch { /* a preference, not data */ }
  // Settings and the editor are different trees, so a change in one has to reach the other.
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function useEditorPreferences(): EditorPreferences {
  const [preferences, setPreferences] = useState(editorPreferences);
  useEffect(() => {
    const refresh = () => setPreferences(editorPreferences());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, []);
  return preferences;
}

/**
 * Which view an article opens in, remembered per device for the same reason as the editor's.
 *
 * `auto` is Cards where a word is glanced at — a touch screen, which cannot hover — and Page where
 * there is a pointer. The switch above an article changes the view for that sitting, not this.
 */
export type ArticleViewPreference = "auto" | "page" | "cards";
export type ArticleView = "page" | "cards";

const ARTICLE_VIEW_KEY = "acervo-article-view";

export function articleViewPreference(): ArticleViewPreference {
  try {
    const stored = localStorage.getItem(ARTICLE_VIEW_KEY);
    return stored === "page" || stored === "cards" ? stored : "auto";
  } catch {
    return "auto";
  }
}

export function setArticleViewPreference(value: ArticleViewPreference): void {
  try { localStorage.setItem(ARTICLE_VIEW_KEY, value); } catch { /* a preference, not data */ }
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function defaultArticleView(preference: ArticleViewPreference = articleViewPreference()): ArticleView {
  if (preference !== "auto") return preference;
  const touch = typeof window.matchMedia === "function" && window.matchMedia("(hover: none)").matches;
  return touch ? "cards" : "page";
}

export function useDefaultArticleView(): ArticleView {
  const [view, setView] = useState(() => defaultArticleView());
  useEffect(() => {
    const refresh = () => setView(defaultArticleView());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, []);
  return view;
}

/**
 * Whether pronunciations are kept on this device once heard, remembered per device.
 *
 * On by default: a spoken headword is a few kilobytes, and a clip kept is a clip that plays on a
 * plane. Off means every press asks the server — the choice for a device short on space — and
 * switching it off forgets what was kept (`pronunciation.ts`). A device fact, like wrapping, so it is
 * never replicated and never on the server.
 */
const PRONUNCIATION_CACHE_KEY = "acervo-pronunciation-cache";

export function pronunciationCacheEnabled(): boolean {
  return readPreference(PRONUNCIATION_CACHE_KEY, true);
}

export function setPronunciationCacheEnabled(value: boolean): void {
  try { localStorage.setItem(PRONUNCIATION_CACHE_KEY, value ? "on" : "off"); } catch { /* a preference, not data */ }
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function usePronunciationCache(): boolean {
  const [enabled, setEnabled] = useState(pronunciationCacheEnabled);
  useEffect(() => {
    const refresh = () => setEnabled(pronunciationCacheEnabled());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, []);
  return enabled;
}


/* ── the loop player ──
   Three device facts, for `usePronunciationCache`'s reason: which device is worth spending a
   hundred megabytes on is not a question the account can answer, and how you like a player to
   behave is not one either.

   Keeping loops is **off** by default where keeping clips is on, and that is the whole of what the
   difference in size buys: a vocabulary's clips cost about what its text does, and one loop costs
   more than both. A loop still plays with it off — the track is held for the session — it is simply
   not kept for the next time. */

const LOOP_CACHE_KEY = "acervo-loop-cache";
const LOOP_REPEAT_KEY = "acervo-loop-repeat";
const LOOP_AUTOPLAY_KEY = "acervo-loop-autoplay";

export function loopCacheEnabled(): boolean { return readPreference(LOOP_CACHE_KEY, false); }
export function loopRepeatEnabled(): boolean { return readPreference(LOOP_REPEAT_KEY, false); }
export function loopAutoplayEnabled(): boolean { return readPreference(LOOP_AUTOPLAY_KEY, false); }

function writePreference(key: string, value: boolean): void {
  try { localStorage.setItem(key, value ? "on" : "off"); } catch { /* a preference, not data */ }
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}

export function setLoopCacheEnabled(value: boolean): void { writePreference(LOOP_CACHE_KEY, value); }
export function setLoopRepeat(value: boolean): void { writePreference(LOOP_REPEAT_KEY, value); }
export function setLoopAutoplay(value: boolean): void { writePreference(LOOP_AUTOPLAY_KEY, value); }

function usePreference(read: () => boolean): boolean {
  const [value, setValue] = useState(read);
  useEffect(() => {
    const refresh = () => setValue(read());
    window.addEventListener(PREFERENCES_EVENT, refresh);
    return () => window.removeEventListener(PREFERENCES_EVENT, refresh);
  }, [read]);
  return value;
}

export function useLoopCache(): boolean { return usePreference(loopCacheEnabled); }
export function useLoopRepeat(): boolean { return usePreference(loopRepeatEnabled); }
export function useLoopAutoplay(): boolean { return usePreference(loopAutoplayEnabled); }

/* ── the make dialog ──
   The format last made on this device, and each format's switches as they were last set. A device
   fact for the loop player's reason: which kind of loop suits a morning walk is not the account's
   question. A format or switch the generator no longer offers is simply not found, and its default
   stands. */

const LOOP_FORMAT_KEY = "acervo-loop-format";
const LOOP_SWITCHES_KEY = "acervo-loop-switches";

export function lastLoopFormat(): string | null {
  try { return localStorage.getItem(LOOP_FORMAT_KEY); } catch { return null; }
}

export function loopSwitchesFor(format: string): Record<string, boolean | string> {
  try {
    const stored = JSON.parse(localStorage.getItem(LOOP_SWITCHES_KEY) || "{}") as Record<string, unknown>;
    const mine = stored[format];
    return mine && typeof mine === "object" && !Array.isArray(mine) ? mine as Record<string, boolean | string> : {};
  } catch { return {}; }
}

export function rememberLoopFormat(format: string, switches: Record<string, boolean | string>): void {
  try {
    const stored = JSON.parse(localStorage.getItem(LOOP_SWITCHES_KEY) || "{}") as Record<string, unknown>;
    localStorage.setItem(LOOP_SWITCHES_KEY, JSON.stringify({ ...stored, [format]: switches }));
    localStorage.setItem(LOOP_FORMAT_KEY, format);
  } catch { /* a preference, not data */ }
}
