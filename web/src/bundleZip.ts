/**
 * A bundle as a zip: the archive's bytes in, its text files, pictures and clips out.
 *
 * Pure — no DOM, no transport — so the Settings panel and the laptop's installer for the starter
 * vocabularies (`web/scripts/install-bundle.ts`) read an archive the same way. What a bundle *is*
 * lives in `transfer.ts`; this is only the archive around it.
 */

import { strFromU8, unzipSync } from "fflate";
import { AUDIO_DIRECTORY, MEDIA_DIRECTORY, type BundleFile } from "./transfer";

/** Whatever the archiver on the other machine felt like adding. None of it is vocabulary. */
const NOISE = /(^|\/)(__MACOSX\/|\.DS_Store$|\._)/;

/** A directory anywhere in the path, so a bundle zipped inside a folder keeps its pictures. */
const under = (directory: string) => new RegExp(`(^|/)${directory}/`);
const MEDIA = under(MEDIA_DIRECTORY);
const AUDIO = under(AUDIO_DIRECTORY);

export interface BundleArchive {
  files: BundleFile[];
  pictures: Map<string, Uint8Array>;
  recordings: Map<string, Uint8Array>;
}

/**
 * The bundle's text files, and its pictures and clips kept as bytes.
 *
 * Split because `strFromU8` on a WebP or an MP3 produces mojibake — everything under `media/`, and
 * every recording under `audio/`, has to stay binary all the way to the route that stores it. A
 * clip's `clips.yaml` is text like any other. A single YAML file, not a zip, is one word document.
 */
export function bundleArchive(name: string, bytes: Uint8Array): BundleArchive {
  if (!/\.zip$/i.test(name)) {
    return { files: [{ path: name, text: strFromU8(bytes) }], pictures: new Map(), recordings: new Map() };
  }
  const files: BundleFile[] = [];
  const pictures = new Map<string, Uint8Array>();
  const recordings = new Map<string, Uint8Array>();
  Object.entries(unzipSync(bytes))
    .filter(([path, content]) => !path.endsWith("/") && !NOISE.test(path) && content.length > 0)
    .forEach(([path, content]) => {
      if (MEDIA.test(path)) pictures.set(path, content);
      else if (AUDIO.test(path) && !/\.ya?ml$/i.test(path)) recordings.set(path, content);
      else files.push({ path, text: strFromU8(content) });
    });
  return { files, pictures, recordings };
}
