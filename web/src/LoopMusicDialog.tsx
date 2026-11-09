/**
 * New music for a loop that is already made: the make dialog's music, on its own.
 *
 * **The same picker as the make dialog's** (`MusicSections`): Saved music as cards with ▶, then the
 * styles' carousel with each style's sample — so music is chosen the same way wherever it is
 * chosen, rather than as pictures in one place and a list of names in another. It opens on the
 * loop's own style, which is what "new music in this style" was; the saved piece the loop is already
 * playing is not offered, since asking for it again would make the same music.
 *
 * **Choosing is not asking**: a swipe chooses as the row moves, so the request is the footer's
 * button, and the dialog closes on it. What it asks `POST /loops/{id}/music` for:
 *
 * - the loop's own style — nothing at all, which the server reads as this style with a new bed;
 * - another style — its family, and the server mints the seed;
 * - a saved piece — its family *and* seed, the pair that replays it (`musicOf`);
 * - Surprise me — a style picked here from the others offered. For a loop that exists, an empty
 *   request already means *this* style, so "any style" is a choice made before asking.
 *
 * The music last made on this device is the make dialog's memory and is not touched here.
 */

import { useEffect, useState } from "react";
import type { LoopFamily, LoopMusic } from "./api";
import type { Bed, Loop, VocabularyGraph } from "./domain";
import { MusicBrowse, MusicSections, musicChoices, musicKey, musicOf, useLoopSchema, type MusicBrowsing } from "./LoopMusic";
import MakeDialog from "./MakeDialog";
import { stopPreview } from "./pronunciation";
import { favouriteBeds } from "./selectors";

/** What a choice asks for, for a loop that already has music. */
export function newMusicFor(loop: Loop, families: LoopFamily[], key: string, favourites: Bed[], graph: VocabularyGraph,
  pick: (count: number) => number = (count) => Math.floor(Math.random() * count)): LoopMusic {
  const choice = musicChoices(graph, families, favourites).of(key);
  if (choice.kind === "bed") return musicOf(choice);
  if (choice.kind === "style") return choice.family === loop.styleId ? {} : { family: choice.family };
  const others = families.filter((family) => family.id !== loop.styleId);
  return others.length ? { family: others[pick(others.length)].id } : {};
}

export default function LoopMusicDialog({ graph, loop, onChoose, onClose, onNotify, onRemoveBed }: {
  graph: VocabularyGraph;
  loop: Loop;
  /** Online-only and loud when it fails, like every other write. */
  onChoose(music: LoopMusic): void;
  onClose(): void;
  onNotify(message: string): void;
  onRemoveBed?(bed: Bed): void;
}) {
  const { schema, trouble } = useLoopSchema();
  const families = schema?.families ?? [];
  const favourites = favouriteBeds(graph).filter((bed) => !(bed.styleId === loop.styleId && bed.seed === loop.seed));
  const [picked, setPicked] = useState<string | null>(loop.styleId ? `style:${loop.styleId}` : null);
  const [browsing, setBrowsing] = useState<MusicBrowsing>(null);
  const value = musicKey(musicChoices(graph, families, favourites).of(picked));
  // Closing the dialog, by its button or otherwise, ends what it was playing with it.
  useEffect(() => () => stopPreview(), []);

  const footer = <>
    {trouble && <p className="make-blocked warn">{trouble}</p>}
    <button
      className="tb-btn primary make-go" disabled={!schema}
      onClick={() => {
        stopPreview();
        onChoose(newMusicFor(loop, families, value, favourites, graph));
        onClose();
      }}
    >Make new music</button>
  </>;
  const shared = { graph, families, favourites, value, onNotify, onRemove: onRemoveBed };

  if (browsing) {
    return <MakeDialog title="New music" footer={footer} onClose={onClose}
      back={{ title: browsing === "styles" ? "Music style" : "Saved music", onBack: () => setBrowsing(null) }}>
      <MusicBrowse {...shared} browsing={browsing} onChange={(key) => { setPicked(key); setBrowsing(null); }} />
    </MakeDialog>;
  }
  return <MakeDialog title="New music" footer={footer} onClose={onClose}>
    <MusicSections {...shared} onChange={setPicked} onBrowse={setBrowsing} />
  </MakeDialog>;
}
