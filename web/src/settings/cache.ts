/**
 * What the server last said about each setting, kept while the app is open.
 *
 * A page of Settings used to fetch its settings every time it was shown and render a line of
 * "Reading your settings…" until they came — so every switch between two pages went old page,
 * placeholder, new page, and coming back to a page did it again. Here a page shows the last answer
 * at once and asks again quietly; the answer replaces it when it lands.
 *
 * It is a cache of route answers and nothing more: the replica and its rules are untouched, a write
 * still goes to the server and fails loudly, and what is shown after a save is the server's reply
 * (`set` takes it), never this client's optimism alone.
 */

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { AcervoApiError, backendSession } from "../api";
import { listOnServer } from "../dictionaries";

/** One setting the server holds: where it is read from, and what to say when it cannot be. */
export interface Resource<T> {
  key: string;
  fetch(): Promise<T>;
  failure: string;
}

const resource = <T,>(key: string, fetch: () => Promise<T>, failure: string): Resource<T> =>
  ({ key, fetch, failure });

const UNREACHABLE = "These settings are on the server, which could not be reached.";

export const SETTINGS = {
  models: resource("models", () => backendSession.fetchModels(), "Your server could not be reached."),
  rules: resource("rules", () => backendSession.promptRules(), UNREACHABLE),
  images: resource("images", () => backendSession.imageSettings(), UNREACHABLE),
  pronunciations: resource("pronunciations", () => backendSession.pronunciationSettings(), UNREACHABLE),
  languages: resource("languages", () => backendSession.languages(), "The list of languages is on the server, which could not be reached."),
  schedule: resource("schedule", () => backendSession.scheduleSettings(), UNREACHABLE),
  anki: resource("anki", () => backendSession.ankiStatus(), UNREACHABLE),
  jobs: resource("jobs", () => backendSession.jobs(false), "The server’s activity could not be read."),
  clips: resource("clips", () => backendSession.clipSettings(), UNREACHABLE),
  corpus: resource("corpus", () => backendSession.clipCorpus(), "The clip corpus could not be asked."),
  loopSchema: resource("loopSchema", () => backendSession.loopSchema(), "The loop generator could not be reached."),
  dictionaries: resource("dictionaries", () => listOnServer(), "Your server’s dictionaries could not be listed.")
};

/**
 * Read in the background when Settings opens, so the first visit to a page is usually as quick as
 * the second. Each is one indexed read on the server. The corpus is not among them: it is a call to
 * another service, made only by the page that shows it.
 */
const PREFETCHED = [
  SETTINGS.models, SETTINGS.rules, SETTINGS.images, SETTINGS.pronunciations,
  SETTINGS.schedule, SETTINGS.anki, SETTINGS.jobs, SETTINGS.clips
];

export interface Reading<T> {
  value: T | undefined;
  /** Set only when there is nothing to show: a failed refresh behind a value keeps the value. */
  error: string | null;
}

interface Entry {
  reading: Reading<unknown>;
  inflight: Promise<unknown> | null;
  /** Bumped by every `set`, so an answer to a read that began before a save cannot undo it. */
  version: number;
  listeners: Set<() => void>;
}

const entries = new Map<string, Entry>();
/** Bumped by `forgetServerSettings`, so an answer for the account just signed out of is dropped. */
let generation = 0;

function entryFor(key: string): Entry {
  let entry = entries.get(key);
  if (!entry) {
    entry = { reading: { value: undefined, error: null }, inflight: null, version: 0, listeners: new Set() };
    entries.set(key, entry);
  }
  return entry;
}

function publish(entry: Entry, reading: Reading<unknown>) {
  entry.reading = reading;
  entry.listeners.forEach((listener) => listener());
}

function message(error: unknown, failure: string): string {
  return error instanceof AcervoApiError ? error.message : failure;
}

/** Ask the server again. Two pages asking at once share one request. */
export function refresh<T>(source: Resource<T>): Promise<T> {
  const entry = entryFor(source.key);
  if (entry.inflight) return entry.inflight as Promise<T>;
  const started = { version: entry.version, generation };
  const request = source.fetch().then(
    (value) => {
      if (started.generation === generation && started.version === entry.version) {
        publish(entry, { value, error: null });
      }
      return value;
    },
    (error: unknown) => {
      if (started.generation === generation && entry.reading.value === undefined) {
        publish(entry, { value: undefined, error: message(error, source.failure) });
      }
      throw error;
    }
  ).finally(() => {
    if (entry.inflight === request) entry.inflight = null;
  });
  entry.inflight = request;
  return request;
}

/** What a save returned, which is now what the server holds. */
export function store<T>(source: Resource<T>, value: T) {
  const entry = entryFor(source.key);
  entry.version += 1;
  publish(entry, { value, error: null });
}

export function prefetchSettings() {
  PREFETCHED.forEach((source) => { void refresh(source as Resource<unknown>).catch(() => undefined); });
}

/** On signing out: nothing one account was told may be shown to the next. */
export function forgetServerSettings() {
  generation += 1;
  for (const entry of entries.values()) {
    entry.inflight = null;
    entry.version += 1;
    publish(entry, { value: undefined, error: null });
  }
}

/**
 * A setting as a page sees it: the last answer at once, refreshed once per visit.
 *
 * `set` is for what a save returned, or for the optimistic value a switch shows while its save is
 * in flight — the page puts the old one back if the save is refused.
 */
export function useServerSetting<T>(source: Resource<T>): Reading<T> & { set(value: T): void } {
  const entry = entryFor(source.key);
  const subscribe = useCallback((listener: () => void) => {
    entry.listeners.add(listener);
    return () => { entry.listeners.delete(listener); };
  }, [entry]);
  const reading = useSyncExternalStore(subscribe, () => entry.reading) as Reading<T>;
  useEffect(() => { void refresh(source).catch(() => undefined); }, [source]);
  const set = useCallback((value: T) => store(source, value), [source]);
  return { ...reading, set };
}
