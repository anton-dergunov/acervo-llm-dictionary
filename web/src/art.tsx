/**
 * The make dialogs' pictures: a sample of each picture style, a vignette for each kind of story and
 * each kind of music. Generated once by `scripts/draw_dialog_art.py` and kept under `art/`, named by
 * the catalogue id they picture (`art/README.md` says how they were made and under what licence).
 *
 * **An id with no picture still gets a tile**: its emoji when it has one, else its initial. Styles,
 * kinds and music are catalogues read from the server and from LexiBeat, so one added there appears
 * here at once, and its picture follows when the script is run again.
 */

const FILES = import.meta.glob("./art/*/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

export type ArtGroup = "styles" | "kinds" | "music";

export function artFor(group: ArtGroup, id: string): string | null {
  return FILES[`./art/${group}/${id}.webp`] ?? null;
}

/** A catalogue entry's picture, or the stand-in that keeps the tile the same shape without one. */
export function Art({ group, id, label, emoji }: { group: ArtGroup; id: string; label: string; emoji?: string | null }) {
  const url = artFor(group, id);
  if (url) return <img className="choice-img" src={url} alt="" loading="lazy" decoding="async" draggable={false} />;
  return <span className={`choice-stand-in${emoji ? " emoji" : ""}`} aria-hidden="true">
    {emoji || label.trim().charAt(0).toUpperCase()}
  </span>;
}
