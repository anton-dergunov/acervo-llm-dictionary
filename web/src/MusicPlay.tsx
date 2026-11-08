/**
 * ▶ for music heard on its own: a style's sample on the carousel, a kept bed's music in Saved music.
 *
 * One round, frosted button for both, so a sample and a saved piece look like the same act. Idle it
 * is ▶; while the bytes are on their way a thin arc turns round it (a slow pulse instead, for a
 * device that asks for less motion); playing it is ❚❚ with a ring that fills as the music plays.
 * A failure is the toast's, with the sentence that says why — the button only returns to ▶.
 *
 * The sound is `pronunciation.playPreview`'s, so it silences a loop or a word and they silence it.
 */

import { PauseIcon, PlayIcon } from "./icons";
import { playPreview, stopPreview, usePreviewProgress, useSpeechState } from "./pronunciation";

/** The key a piece of music is heard under, from the key its choice goes by (`musicKey`). */
export const previewKey = (choice: string): string => `music:${choice}`;

const RADIUS = 16;
const ROUND = 2 * Math.PI * RADIUS;

/** Start a piece, reporting a failure the way the button does. */
export function hear(choice: string, fetch: () => Promise<Blob>, onError: (message: string) => void): void {
  playPreview(previewKey(choice), fetch).catch((error: unknown) => {
    onError(error instanceof Error && error.message ? error.message : "That music could not be played.");
  });
}

/** The button itself, for music this module does not play: a saved piece heard through its loop. */
export function MusicButton({ label, size, loading = false, playing, share, onClick }: {
  label: string;
  size: "large" | "small";
  loading?: boolean;
  playing: boolean;
  /** How much of it has played, from 0 to 1. */
  share: number;
  onClick(): void;
}) {
  return <button
    type="button"
    className={`music-play ${size}${loading ? " loading" : ""}${playing ? " playing" : ""}`}
    aria-label={playing || loading ? "Stop" : `Hear ${label}`}
    onClick={onClick}
  >
    <svg className="music-play-ring" viewBox="0 0 36 36" aria-hidden="true">
      {loading && <circle className="arc" cx="18" cy="18" r={RADIUS} strokeDasharray={`${ROUND * 0.28} ${ROUND}`} />}
      {playing && <circle className="fill" cx="18" cy="18" r={RADIUS} strokeDasharray={`${ROUND * share} ${ROUND}`} />}
    </svg>
    {playing ? <PauseIcon /> : <PlayIcon />}
  </button>;
}

export function MusicPlay({ choice, label, size = "large", fetch, onError }: {
  /** The key of the choice it plays, as `musicKey` writes it. */
  choice: string;
  /** What it plays, for "Hear Organic". */
  label: string;
  size?: "large" | "small";
  fetch(): Promise<Blob>;
  onError(message: string): void;
}) {
  const key = previewKey(choice);
  const speech = useSpeechState();
  const progress = usePreviewProgress(key);
  const playing = speech.playing === key;
  const loading = speech.busy === key;
  const share = playing && progress.duration > 0 ? Math.min(1, progress.at / progress.duration) : 0;
  return <MusicButton label={label} size={size} loading={loading} playing={playing} share={share}
    onClick={() => (loading ? stopPreview() : hear(choice, fetch, onError))} />;
}
