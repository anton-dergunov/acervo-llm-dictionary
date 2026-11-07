/**
 * Choosing a loop's music: the make dialog's tiles and the player's menu.
 *
 * **Three kinds of choice, in the order a person reaches for them.** A favourite — a bed the owner
 * kept, asked for again by its style *and* seed, which is the pair that replays it. Surprise me —
 * the generator picks a style and a bed. A style — one of the generator's families, each with the
 * sentence the generator gives to choose it by. There is no "Auto" beside "Surprise me": they were
 * the same request under two names, and the list said both.
 *
 * **A favourite is not a style tile with a star**, because such a tile looks like the style it is a
 * piece of and goes unseen. The favourites are a row of their own above the styles, each saying in
 * plain view when it was kept and which loop it came from, with a button to hear it.
 *
 * The styles are the generator's catalogue, read from `GET /loops/schema` once per session and never
 * copied here, so a family added in a later version appears with nothing changing on this side.
 */

import { useEffect, useState } from "react";
import { backendSession, type LoopFamily, type LoopMusic, type LoopSchema } from "./api";
import type { Bed, Loop, VocabularyGraph } from "./domain";
import { Art } from "./art";
import type { StripChoice } from "./ChoiceStrip";
import { DiceIcon, PauseIcon, PlayIcon, StarIcon } from "./icons";
import * as player from "./loops";
import { loopIsReady, loopTitle, loopTrackOf, styleLabel } from "./selectors";

let asked: Promise<LoopSchema> | null = null;

/**
 * What the generator offers, asked once and shared; a failure is asked again next time.
 *
 * `fresh` asks again regardless, which is what the make dialog wants: whether the sample pack is
 * installed is a fact about the server that changes when the owner installs it, and a dialog that
 * went on refusing until a reload would be reporting a state that is no longer true.
 */
export function useLoopSchema(fresh = false): { schema: LoopSchema | null; trouble: string | null } {
  const [schema, setSchema] = useState<LoopSchema | null>(null);
  const [trouble, setTrouble] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    if (fresh) asked = null;
    asked ??= backendSession.loopSchema();
    asked.then((found) => {
      player.nameFormats(found.formats);
      if (live) setSchema(found);
    }).catch((error: unknown) => {
      asked = null;
      if (live) setTrouble(error instanceof Error && error.message ? error.message : "The loop generator could not be reached.");
    });
    return () => { live = false; };
  }, [fresh]);
  return { schema, trouble };
}

export function resetLoopSchemaForTests(): void { asked = null; }

export type MusicChoice =
  | { kind: "surprise" }
  | { kind: "style"; family: string }
  | { kind: "bed"; bed: Bed };

/** What a choice asks the server for. A favourite is its family and its seed, never one alone. */
export function musicOf(choice: MusicChoice): LoopMusic {
  if (choice.kind === "style") return { family: choice.family };
  if (choice.kind === "bed") return { family: choice.bed.styleId, seed: choice.bed.seed };
  return {};
}

function kept(bed: Bed): string {
  return new Date(bed.createdAt).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** The loop a favourite came from, if it is still there to be heard. */
function sourceOf(graph: VocabularyGraph, bed: Bed): Loop | undefined {
  const loop = graph.loops.find((one) => one.id === bed.sourceLoopId);
  return loop && !loop.deleted && loopIsReady(loop) ? loop : undefined;
}

/** How a favourite is described: when it was kept, and the loop it is the music of. */
export function bedAbout(graph: VocabularyGraph, bed: Bed): string {
  const loop = sourceOf(graph, bed);
  return loop ? `kept ${kept(bed)} · from “${loopTitle(graph, loop)}”` : `kept ${kept(bed)}`;
}

/** Hear a favourite before choosing it, by playing the loop it was kept from. */
function Preview({ graph, bed }: { graph: VocabularyGraph; bed: Bed }) {
  const playback = player.usePlayback();
  const loop = sourceOf(graph, bed);
  if (!loop) return null;
  const playing = playback.loopId === loop.id && playback.playing;
  return <button
    type="button" className="music-preview"
    aria-label={playing ? "Stop listening" : "Hear this music"}
    onClick={() => (playing ? player.pause() : void player.play(loopTrackOf(graph, loop)))}
  >{playing ? <PauseIcon /> : <PlayIcon />}</button>;
}

/** A choice as one string, which is what a strip of tiles is keyed by. */
export function musicKey(choice: MusicChoice): string {
  if (choice.kind === "style") return `style:${choice.family}`;
  if (choice.kind === "bed") return `bed:${choice.bed.id}`;
  return "surprise";
}

/**
 * The make dialog's music. The favourites, each with its star, what it came from and a button to hear
 * it; then the strip: Surprise me, and every style. Each picture is the style's (`art.tsx`), so a
 * favourite looks like the style it is a piece of. `of` reads a remembered key back, and anything it
 * no longer names — a favourite let go, a style the generator dropped — is Surprise me.
 */
export function musicChoices(graph: VocabularyGraph, families: LoopFamily[], favourites: Bed[]): {
  favourites: Bed[];
  styles: StripChoice[];
  of(key: string | null): MusicChoice;
} {
  const byKey = new Map<string, MusicChoice>();
  for (const bed of favourites) byKey.set(musicKey({ kind: "bed", bed }), { kind: "bed", bed });
  const tile = (choice: MusicChoice, entry: Omit<StripChoice, "id">): StripChoice => {
    byKey.set(musicKey(choice), choice);
    return { id: musicKey(choice), ...entry };
  };
  const styles = [
    tile({ kind: "surprise" }, {
      label: "Surprise me", about: "New music, in any style",
      art: <span className="choice-stand-in icon" aria-hidden="true"><DiceIcon /></span>
    }),
    ...families.map((family) => tile({ kind: "style", family: family.id }, {
      label: family.label, about: family.description,
      art: <Art group="music" id={family.id} label={family.label} />
    }))
  ];
  return { favourites, styles, of: (key) => (key && byKey.get(key)) || { kind: "surprise" } };
}

/** The favourites as a row of their own: the picture, the name with its star, where it came from. */
export function FavouriteMusic({ graph, families, favourites, value, onChange }: {
  graph: VocabularyGraph;
  families: LoopFamily[];
  favourites: Bed[];
  value: string;
  onChange(key: string): void;
}) {
  if (!favourites.length) return null;
  return <div className="music-favourites" role="radiogroup" aria-label="Favourite music">
    {favourites.map((bed) => {
      const key = musicKey({ kind: "bed", bed });
      const label = styleLabel(families, bed.styleId);
      return <div key={bed.id} className={`favourite${key === value ? " on" : ""}`}>
        <button type="button" role="radio" aria-checked={key === value} onClick={() => onChange(key)}
          aria-label={`${label}, ${bedAbout(graph, bed)}`}>
          <span className="favourite-art"><Art group="music" id={bed.styleId} label={label} /></span>
          <span className="favourite-text">
            <span className="favourite-name"><StarIcon filled />{label}</span>
            <span className="favourite-about">{bedAbout(graph, bed)}</span>
          </span>
        </button>
        <Preview graph={graph} bed={bed} />
      </div>;
    })}
  </div>;
}

/** The player's menu: new music for the loop that is open. Choosing is asking; there is no Apply. */
export function MusicMenu({ graph, loop, families, favourites, onChoose }: {
  graph: VocabularyGraph;
  loop: Loop;
  families: LoopFamily[];
  favourites: Bed[];
  onChoose(music: LoopMusic): void;
}) {
  const others = favourites.filter((bed) => !(bed.styleId === loop.styleId && bed.seed === loop.seed));
  return <div className="menu open music-menu" role="menu" aria-label="New music for this loop">
    <button role="menuitem" onClick={() => onChoose({})}>
      <span className="music-name">New music in this style</span>
      <span className="music-about">{styleLabel(families, loop.styleId)}, with a different bed</span>
    </button>
    {others.length > 0 && <div className="menu-label label">Favourites</div>}
    {others.map((bed) => <button key={bed.id} role="menuitem" onClick={() => onChoose(musicOf({ kind: "bed", bed }))}>
      <span className="music-name"><StarIcon filled />{styleLabel(families, bed.styleId)}</span>
      <span className="music-about">{bedAbout(graph, bed)}</span>
    </button>)}
    <div className="menu-label label">Styles</div>
    {families.map((family) => <button
      key={family.id} role="menuitemradio" aria-checked={family.id === loop.styleId}
      className={family.id === loop.styleId ? "on" : ""}
      onClick={() => onChoose({ family: family.id })}
    >
      <span className="music-name">{family.label}</span>
      <span className="music-about">{family.description}</span>
    </button>)}
  </div>;
}
