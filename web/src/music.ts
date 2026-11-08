/**
 * Music heard on its own: a kept bed's music and a style's sample, kept on this device.
 *
 * Both are short, both are asked for again and again while choosing, and both must start the moment
 * ▶ is pressed, so both are kept in `mediaStore.ts`'s `music` store once fetched — a store of their
 * own, so forgetting loops forgets neither. **Each is keyed by a name that carries a digest of its
 * bytes**, a bed's by its `audioRef` and a sample's by the name `GET /loops/schema` gave it, so this
 * is a cache with no invalidation: a re-rendered sample is a new name the device has never held.
 *
 * A sample the server has not made yet (the schema's `sample` is null) is asked for with
 * `makeSample`, which renders it there and then. That waits on the generator, so it is the slow path;
 * the server warms every sample after a deploy so that a tap rarely takes it.
 *
 * Playing is `pronunciation.playPreview`'s — this module only fetches. There is no fourth player.
 */

import { AcervoApiError, backendSession, type LoopFamily } from "./api";
import type { Bed } from "./domain";
import { createMediaStore, type MediaStore } from "./mediaStore";

let store: MediaStore = createMediaStore("music");

/** One fetch per name at a time, so a prefetch and a tap on the same thing share one request. */
const inFlight = new Map<string, Promise<Blob>>();
/** Samples made on a tap this session, by family, for a schema that was read before they existed. */
const made = new Map<string, string>();

async function kept(name: string, fetchBlob: () => Promise<Blob>): Promise<Blob> {
  const stored = await store.read(name).catch(() => null);
  if (stored) return stored.blob;
  const running = inFlight.get(name);
  if (running) return running;
  const fetching = (async () => {
    const blob = await fetchBlob();
    // Best-effort, as a picture's is: a full disk costs a fetch next time, not this playback.
    await store.save(name, blob).catch(() => undefined);
    return blob;
  })().finally(() => { inFlight.delete(name); });
  inFlight.set(name, fetching);
  return fetching;
}

function offline(error: unknown, what: string): Error {
  if (error instanceof AcervoApiError && error.code === "offline") {
    return new Error(`${what} is not on this device yet, and the server cannot be reached.`);
  }
  return error instanceof Error ? error : new Error(`${what} could not be fetched.`);
}

async function download(reference: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(backendSession.mediaFileUrl(reference), { headers: backendSession.mediaHeaders(), cache: "no-store" });
  } catch {
    throw new Error("This music is not on this device yet, and the server cannot be reached.");
  }
  if (!response.ok) {
    throw new Error(response.status === 404
      ? "That music is not on the server any more."
      : `That music could not be read from the server (${response.status}).`);
  }
  return response.blob();
}

/** A kept bed's own music. Only for a bed whose `audioRef` is set. */
export function bedMusic(bed: Pick<Bed, "audioRef">): Promise<Blob> {
  const reference = bed.audioRef;
  if (!reference) return Promise.reject(new Error("That music has not been made yet."));
  return kept(reference, () => download(reference));
}

/** The name a family's sample goes by, if the server has one: from the schema, or made this session. */
function sampleName(family: LoopFamily): string | null {
  return family.sample ?? made.get(family.id) ?? null;
}

/** A style's sample: from this device, else the server's cache, else made by the server now. */
export async function sampleMusic(family: LoopFamily): Promise<Blob> {
  let name = sampleName(family);
  if (!name) {
    try {
      name = (await backendSession.makeSample(family.id)).sample;
    } catch (error) {
      throw offline(error, `The ${family.label} sample`);
    }
    made.set(family.id, name);
  }
  const found = name;
  return kept(found, () => backendSession.sampleAudio(found).catch((error) => { throw offline(error, `The ${family.label} sample`); }));
}

/**
 * Fetch what is about to be asked for: the shown beds' music and the samples near the middle of the
 * row. Only what the server already has — a missing sample is not made by looking at it — and one at
 * a time, quietly, since the usual failure is "offline" and a tap will say so itself.
 */
export async function prefetch(beds: Pick<Bed, "audioRef">[], families: LoopFamily[]): Promise<void> {
  for (const bed of beds) {
    if (!bed.audioRef) continue;
    try { await bedMusic(bed); } catch { return; }
  }
  for (const family of families) {
    const name = sampleName(family);
    if (!name) continue;
    try { await kept(name, () => backendSession.sampleAudio(name)); } catch { return; }
  }
}

/** A kept bed's music is gone from the server; the device lets its copy go too. */
export async function forgetBedMusic(reference: string): Promise<void> {
  await store.remove(reference).catch(() => undefined);
}

/** Forget every piece of music kept on this device, for a sign-out. */
export async function forgetMusic(): Promise<void> {
  made.clear();
  await store.clear().catch(() => undefined);
}

/** For tests: a store that does not need IndexedDB. */
export function replaceMusicStoreForTests(replacement: MediaStore): void {
  store = replacement;
  inFlight.clear();
  made.clear();
}
