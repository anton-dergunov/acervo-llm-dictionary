/**
 * Choosing a loop's music, the same in the make dialog and in the player's New music.
 *
 * **Three kinds of choice, in the order a person reaches for them.** A favourite — a bed the owner
 * kept, asked for again by its style *and* seed, which is the pair that replays it. Surprise me —
 * the generator picks a style and a bed. A style — one of the generator's families, each with the
 * sentence the generator gives to choose it by. There is no "Auto" beside "Surprise me": they were
 * the same request under two names, and the list said both.
 *
 * **A favourite is not a style tile with a star**, because such a tile looks like the style it is a
 * piece of and goes unseen. Saved music is a section of its own above the styles, each piece saying
 * in plain view when it was kept and which loop it came from, with a button to hear it. The two most
 * recent show; the rest unfold in place, so the section is two cards high however many are kept.
 *
 * The styles are the generator's catalogue, read from `GET /loops/schema` once per session and never
 * copied here, so a family added in a later version appears with nothing changing on this side.
 */

import { useEffect, useState } from "react";
import { backendSession, type LoopFamily, type LoopMusic, type LoopSchema } from "./api";
import type { Bed, Loop, VocabularyGraph } from "./domain";
import { Art } from "./art";
import { AllChoices, ChoiceCarousel, ChoiceGrid, centred, type CatalogueChoice } from "./ChoiceCarousel";
import { MakeSection } from "./MakeDialog";
import { CloseIcon, DiceIcon, StarIcon } from "./icons";
import * as player from "./loops";
import { bedMusic, prefetch, sampleMusic } from "./music";
import { MusicButton, MusicPlay, hear, previewKey } from "./MusicPlay";
import { stopPreview, useSpeechState } from "./pronunciation";
import { loopIsReady, loopTitle, loopTrackOf, styleLabel } from "./selectors";

let asked: Promise<LoopSchema> | null = null;
/** The last answer, so a surface opening again starts from it rather than from nothing. */
let known: LoopSchema | null = null;

/**
 * What the generator offers, asked once and shared; a failure is asked again next time.
 *
 * `fresh` asks again regardless, which is what the make dialog wants: whether the sample pack is
 * installed is a fact about the server that changes when the owner installs it, and a dialog that
 * went on refusing until a reload would be reporting a state that is no longer true. It still starts
 * from the last answer while it asks, so the dialog opens at its full size instead of growing a
 * moment later, and the fresh answer replaces it when it comes.
 */
export function useLoopSchema(fresh = false): { schema: LoopSchema | null; trouble: string | null } {
  const [schema, setSchema] = useState<LoopSchema | null>(known);
  const [trouble, setTrouble] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    if (fresh) asked = null;
    asked ??= backendSession.loopSchema();
    asked.then((found) => {
      known = found;
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

export function resetLoopSchemaForTests(): void { asked = null; known = null; }

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

/**
 * Hear a favourite before choosing it: its own music, rendered once by the server after it was kept
 * and kept on this device. Until that has arrived, the loop it was kept from, voice and all.
 */
function Preview({ graph, families, bed, onNotify }: {
  graph: VocabularyGraph;
  families: LoopFamily[];
  bed: Bed;
  onNotify(message: string): void;
}) {
  const playback = player.usePlayback();
  const label = styleLabel(families, bed.styleId);
  if (bed.audioRef) {
    return <MusicPlay choice={musicKey({ kind: "bed", bed })} label={label} size="small"
      fetch={() => bedMusic(bed)} onError={onNotify} />;
  }
  const loop = sourceOf(graph, bed);
  if (!loop) return null;
  const playing = playback.loopId === loop.id && playback.playing;
  return <MusicButton
    label={label} size="small" playing={playing} loading={playback.loopId === loop.id && playback.loading}
    share={playing && playback.duration > 0 ? Math.min(1, playback.at / playback.duration) : 0}
    onClick={() => (playing ? player.pause() : void player.play(loopTrackOf(graph, loop)))}
  />;
}

/** A choice as one string, which is what a strip of tiles is keyed by. */
export function musicKey(choice: MusicChoice): string {
  if (choice.kind === "style") return `style:${choice.family}`;
  if (choice.kind === "bed") return `bed:${choice.bed.id}`;
  return "surprise";
}

/**
 * The make dialog's music. The favourites, each with its star, what it came from and a button to hear
 * it; then the styles' carousel: Surprise me, and every style. Each picture is the style's (`art.tsx`), so a
 * favourite looks like the style it is a piece of. `of` reads a remembered key back, and anything it
 * no longer names — a favourite let go, a style the generator dropped — is Surprise me.
 */
export function musicChoices(graph: VocabularyGraph, families: LoopFamily[], favourites: Bed[]): {
  favourites: Bed[];
  styles: CatalogueChoice[];
  of(key: string | null): MusicChoice;
} {
  const byKey = new Map<string, MusicChoice>();
  for (const bed of favourites) byKey.set(musicKey({ kind: "bed", bed }), { kind: "bed", bed });
  const tile = (choice: MusicChoice, entry: Omit<CatalogueChoice, "id">): CatalogueChoice => {
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

/** How many saved pieces the section shows; All shows the rest in place of the dialog's body. */
const SAVED_SHOWN = 2;

/** Saved pieces as cards: the picture, the name with its star, where it came from, and ▶. */
export function SavedCards({ graph, families, favourites, value, onChange, onNotify, onRemove }: {
  graph: VocabularyGraph;
  families: LoopFamily[];
  favourites: Bed[];
  value: string;
  onChange(key: string): void;
  onNotify(message: string): void;
  /** Stop keeping a piece. Its corner ×, the one way to let go of a piece whose loop is gone. */
  onRemove?(bed: Bed): void;
}) {
  // What is shown is what ▶ will be pressed on, so its music is fetched before it is.
  const shown = favourites.map((bed) => bed.audioRef ?? "").join();
  useEffect(() => { void prefetch(favourites, []); }, [shown]);
  return <div className="music-favourites" role="radiogroup" aria-label="Saved music">
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
        <Preview graph={graph} families={families} bed={bed} onNotify={onNotify} />
        {onRemove && <button type="button" className="favourite-remove" onClick={() => onRemove(bed)}
          aria-label={`Remove ${label} from saved music`} title="Remove from saved music">
          <span aria-hidden="true"><CloseIcon /></span>
        </button>}
      </div>;
    })}
  </div>;
}

/**
 * Saved music, as a section of its own: the two most recent pieces, and All for every one, shown in
 * place of the dialog's body as the styles' grid is — so the dialog is the same height however many
 * are kept. A chosen piece that is not among the two takes the second place, so what is chosen is
 * always in sight.
 */
export function SavedMusic({ graph, families, favourites, value, onChange, onAll, onNotify, onRemove }: {
  graph: VocabularyGraph;
  families: LoopFamily[];
  favourites: Bed[];
  value: string;
  onChange(key: string): void;
  onAll(): void;
  onNotify(message: string): void;
  onRemove?(bed: Bed): void;
}) {
  if (!favourites.length) return null;
  const chosen = favourites.find((bed) => musicKey({ kind: "bed", bed }) === value);
  const shown = chosen && favourites.indexOf(chosen) >= SAVED_SHOWN
    ? [favourites[0], chosen]
    : favourites.slice(0, SAVED_SHOWN);
  const all = favourites.length > SAVED_SHOWN
    ? <AllChoices count={favourites.length} label="Saved music" onOpen={onAll} />
    : null;
  return <MakeSection label="Saved music" aside={all}>
    <SavedCards graph={graph} families={families} favourites={shown} value={value} onChange={onChange}
      onNotify={onNotify} onRemove={onRemove} />
  </MakeSection>;
}

/** Which catalogue is shown whole in place of a dialog's body, if one is. */
export type MusicBrowsing = null | "styles" | "saved";

/** What a style's sample is heard under; a saved piece's key starts differently. */
const SAMPLE = previewKey("style:");

/**
 * The music half of a dialog: Saved music, then the styles' carousel — the same in the make dialog
 * and in the player's New music, so choosing music looks and sounds the same wherever it is chosen.
 *
 * Hearing a style: ▶ on the middle picture plays its sample; while one is playing — or on its way —
 * the row coming to rest on another style plays that one instead, and resting on Surprise me stops
 * it, so swiping through the styles is listening through them. Choosing saved music stops a sample;
 * closing the dialog — the dialog's own unmount, not this one's, since All replaces these sections
 * while the music plays on — ends whatever it was playing.
 */
export function MusicSections({ graph, families, favourites, value, onChange, onBrowse, onNotify, onRemove }: {
  graph: VocabularyGraph;
  families: LoopFamily[];
  favourites: Bed[];
  /** The chosen key, as `musicKey` writes it. */
  value: string;
  onChange(key: string): void;
  /** Show a whole catalogue in place of the dialog's body. */
  onBrowse(browsing: Exclude<MusicBrowsing, null>): void;
  onNotify(message: string): void;
  onRemove?(bed: Bed): void;
}) {
  const tiles = musicChoices(graph, families, favourites);
  const row = centred(tiles.styles[0], tiles.styles.slice(1));
  const familyOf = (key: string): LoopFamily | undefined => families.find((family) => `style:${family.id}` === key);

  const speech = useSpeechState();
  const auditioning = [speech.playing, speech.busy].some((key) => key?.startsWith(SAMPLE));
  const [resting, setResting] = useState<string | null>(null);
  const settled = (key: string) => {
    setResting(key);
    if (!auditioning || speech.playing === previewKey(key) || speech.busy === previewKey(key)) return;
    const family = familyOf(key);
    if (family) hear(key, () => sampleMusic(family), onNotify);
    else stopPreview();
  };
  // The middle sample and its neighbours are what ▶ and a swipe will reach for next.
  const found = row.findIndex((choice) => choice.id === (resting ?? value));
  const middle = found >= 0 ? found : Math.floor((row.length - 1) / 2);
  const near = [row[middle], row[middle - 1], row[middle + 1]].map((choice) => choice && familyOf(choice.id))
    .filter((family): family is LoopFamily => Boolean(family?.sample));
  const nearKey = near.map((family) => family.sample).join();
  useEffect(() => { void prefetch([], near); }, [nearKey]);
  // A piece being heard stops as it is removed; a chosen one falls back by itself.
  const remove = onRemove && ((bed: Bed) => {
    const heard = previewKey(musicKey({ kind: "bed", bed }));
    if (speech.playing === heard || speech.busy === heard) stopPreview();
    onRemove(bed);
  });

  return <>
    <SavedMusic graph={graph} families={families} favourites={favourites} onNotify={onNotify} onRemove={remove}
      value={value} onChange={(key) => { if (auditioning) stopPreview(); onChange(key); }} onAll={() => onBrowse("saved")} />

    <MakeSection label="Music style" note="composed new for each loop"
      aside={<AllChoices count={tiles.styles.length} label="Music style" onOpen={() => onBrowse("styles")} />}>
      <ChoiceCarousel
        label="Music style" choices={row} onChange={onChange}
        idle="Saved music chosen above"
        value={value.startsWith("bed:") ? null : value}
        action={(choice) => {
          const family = familyOf(choice.id);
          return family && <MusicPlay choice={choice.id} label={family.label}
            fetch={() => sampleMusic(family)} onError={onNotify} />;
        }}
        onSettle={(choice) => settled(choice.id)}
      />
    </MakeSection>
  </>;
}

/** A whole catalogue in place of the dialog's body: every style as a grid, or every saved piece. */
export function MusicBrowse({ browsing, graph, families, favourites, value, onChange, onNotify, onRemove }: {
  browsing: Exclude<MusicBrowsing, null>;
  graph: VocabularyGraph;
  families: LoopFamily[];
  favourites: Bed[];
  value: string;
  /** A choice made here also closes the catalogue; that is the dialog's to do. */
  onChange(key: string): void;
  onNotify(message: string): void;
  onRemove?(bed: Bed): void;
}) {
  const speech = useSpeechState();
  if (browsing === "styles") {
    return <ChoiceGrid label="Music style" choices={musicChoices(graph, families, favourites).styles}
      value={value} onChange={onChange} />;
  }
  const remove = onRemove && ((bed: Bed) => {
    const heard = previewKey(musicKey({ kind: "bed", bed }));
    if (speech.playing === heard || speech.busy === heard) stopPreview();
    onRemove(bed);
  });
  return <SavedCards graph={graph} families={families} favourites={favourites} onNotify={onNotify}
    onRemove={remove} value={value}
    onChange={(key) => { if ([speech.playing, speech.busy].some((one) => one?.startsWith(SAMPLE))) stopPreview(); onChange(key); }} />;
}
