/**
 * Choosing a loop's music: the list the make dialog and the player's menu share.
 *
 * **Three kinds of choice, in the order a person reaches for them.** Surprise me — the generator
 * picks a style and a bed. A favourite — a bed the owner kept, asked for again by its style *and*
 * seed, which is the pair that replays it. A style — one of the generator's families, each with the
 * sentence the generator gives to choose it by. There is no "Auto" beside "Surprise me": they were
 * the same request under two names, and the list said both.
 *
 * The styles are the generator's catalogue, read from `GET /loops/schema` once per session and never
 * copied here, so a family added in a later version appears with nothing changing on this side.
 */

import { useEffect, useState, type ReactNode } from "react";
import { backendSession, type LoopFamily, type LoopMusic, type LoopSchema } from "./api";
import type { Bed, Loop, VocabularyGraph } from "./domain";
import { PauseIcon, PlayIcon, StarIcon } from "./icons";
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

function same(left: MusicChoice, right: MusicChoice): boolean {
  if (left.kind !== right.kind) return false;
  if (left.kind === "style" && right.kind === "style") return left.family === right.family;
  if (left.kind === "bed" && right.kind === "bed") return left.bed.id === right.bed.id;
  return true;
}

/** The make dialog's list: one choice, drawn as rows a finger can hit, each saying what it is. */
export function MusicChoices({ graph, families, favourites, value, onChange }: {
  graph: VocabularyGraph;
  families: LoopFamily[];
  favourites: Bed[];
  value: MusicChoice;
  onChange(choice: MusicChoice): void;
}) {
  const row = (choice: MusicChoice, name: string, about: string, extra?: ReactNode, star = false) => {
    const on = same(value, choice);
    return <div className={`music-choice${on ? " on" : ""}`}>
      <button type="button" role="radio" aria-checked={on} onClick={() => onChange(choice)}>
        <span className="music-name">{star && <StarIcon filled />}{name}</span>
        <span className="music-about">{about}</span>
      </button>
      {extra}
    </div>;
  };
  return <div className="music-choices" role="radiogroup" aria-label="Music">
    {row({ kind: "surprise" }, "Surprise me", "New music, in any style")}
    {favourites.length > 0 && <div className="music-group label">Favourites</div>}
    {favourites.map((bed) => <div key={bed.id}>
      {row({ kind: "bed", bed }, styleLabel(families, bed.styleId), bedAbout(graph, bed),
        <Preview graph={graph} bed={bed} />, true)}
    </div>)}
    {families.length > 0 && <div className="music-group label">Styles</div>}
    {families.map((family) => <div key={family.id}>
      {row({ kind: "style", family: family.id }, family.label, family.description)}
    </div>)}
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
