/**
 * The IPA guide's recordings: static files shipped in the build, so every device has all of them
 * after one install and they play offline from the first tap (the service worker precaches them).
 *
 * They play through `pronunciation.playPreview`, the player every other sound uses, as a blob rather
 * than a URL: Safari asks for audio in byte ranges, which a precached response does not answer. The
 * player also primes iOS inside the press and silences a word, loop or story that is playing.
 */

import { playPreview } from "../pronunciation";

const FILES = import.meta.glob("./sounds/*.ogg", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

export const soundKey = (sound: string): string => `ipa:${sound}`;

export function soundUrl(sound: string): string | null {
  return FILES[`./sounds/${sound}`] ?? null;
}

/** Play a recording, or stop it when it is the one playing. */
export function playSound(sound: string): Promise<void> {
  const url = soundUrl(sound);
  if (!url) return Promise.reject(new Error("That recording is not in this version of the app."));
  return playPreview(soundKey(sound), async () => {
    const answer = await fetch(url);
    if (!answer.ok) throw new Error(`That recording could not be loaded (${answer.status}).`);
    return answer.blob();
  });
}
