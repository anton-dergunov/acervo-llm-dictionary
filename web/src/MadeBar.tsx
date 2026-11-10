/**
 * The ways in to what Acervo *made* from your words, and what is playing — a loop or a story, whichever
 * was started last (`listening.ts`) — in three skins, one per device shape, so what they say can never
 * disagree.
 *
 * **On a phone, a bar at the foot of the window.** Resting, it is split in three — Loops, Stories and
 * the Map — which is where these belong on a device held in one hand. Playing, it is one row: the
 * transport, what it is and how far it has got, the next one in the list it was started from, and
 * close, which stops it and forgets it as the one playing (it deletes nothing) and gives the bar back
 * to the ways in. It is drawn over the list, and on the Loops and Stories lists while something
 * plays; never over an article, whose column already carries the view segments, the delete control,
 * the progress strip and the ask dock (`docs/features/loops.md` §2.13). There is no **+**: on those
 * surfaces the top bar's Add makes what they hold.
 *
 * **On a tablet or a desktop, a card at the foot of the rail**, which is where the ways in already
 * are and is on screen at every width a list is, so the top bar no longer has to make room. The rail
 * is 88 px across, so the card is a column: the transport ringed by how far it has got, what is
 * playing in two lines, and Next.
 *
 * **A chip in the top bar only where neither is drawn**: a tablet-sized window whose rail an article
 * has hidden. `styles.css` decides where each skin shows; each steps aside while the thing playing is
 * open in its own player (`.own-player`), which carries every control already.
 */

import type { VocabularyGraph } from "./domain";
import { CloseIcon, MapIcon, NextIcon, NoteIcon, PauseIcon, PlayIcon } from "./icons";
import { useListening } from "./listening";
import * as player from "./loops";
import { lexemesIn, loopCards, loopsIn, loopTitle, loopTrackOf, loopWordAt, storiesIn, storyPartsOf, storyTitle } from "./selectors";
import * as reader from "./storyAudio";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

interface Playing {
  kind: "loop" | "story";
  playing: boolean;
  busy: boolean;
  /** What it is: the word being taught, or the story's title. */
  title: string;
  /** How far it has got, in full and in one figure. */
  sub: string;
  short: string;
  fraction: number;
  toggle(): void;
  next: (() => void) | null;
  close(): void;
  open(): void;
}

export default function MadeBar({ graph, language, skin, playerOnly = false, onLoops, onStories, onMap, onOpenStory }: {
  graph: VocabularyGraph;
  language: string;
  skin: "bar" | "rail" | "chip";
  /* The foot bar with a selection over it, or on the Loops and Stories lists: only what is playing,
     and nothing while nothing is. */
  playerOnly?: boolean;
  onLoops(): void;
  onStories(): void;
  /* The foot bar's third way in. The rail has its own. */
  onMap?(): void;
  /** Open the story being read, at the part being read. */
  onOpenStory(storyId: string, page: number): void;
}) {
  const listening = useListening();
  const playback = player.usePlayback();
  const heard = reader.useStoryAudio();
  const now = nowPlaying();

  function nowPlaying(): Playing | null {
    if (listening === "story" && heard.storyId) {
      const story = graph.stories.find((one) => one.id === heard.storyId);
      const parts = story ? storyPartsOf(graph, story.id) : [];
      if (!story || !parts.length) return null;
      const part = Math.min(heard.partIndex, parts.length - 1);
      const within = heard.passages ? (heard.segment ?? 0) / heard.passages : 0;
      return {
        kind: "story", playing: heard.status === "playing", busy: heard.status === "busy",
        title: storyTitle(graph, story),
        sub: `Story · part ${part + 1} of ${parts.length}`, short: `${part + 1} / ${parts.length}`,
        fraction: heard.status === "idle" ? 0 : (part + within) / parts.length,
        toggle: () => { if (heard.status === "playing") reader.pause(); else reader.resume(); },
        next: reader.hasNextStory() ? () => reader.nextStory() : null,
        close: () => reader.stop(),
        open: () => onOpenStory(story.id, part)
      };
    }
    if (listening === "loop" && playback.loopId) {
      const loop = loopsIn(graph, language).find((one) => one.id === playback.loopId)
        ?? graph.loops.find((one) => one.id === playback.loopId && !one.deleted);
      if (!loop) return null;
      const track = loopTrackOf(graph, loop);
      // The word being taught, so it says what you are hearing rather than which file is open.
      const word = loopWordAt(track.items, loopCards(track.cues), playback.at)?.sourceText;
      return {
        kind: "loop", playing: playback.playing, busy: playback.loading,
        title: word ?? loopTitle(graph, loop, 2),
        sub: `${clock(playback.at)} / ${clock(playback.duration)}`, short: clock(playback.at),
        fraction: playback.duration ? playback.at / playback.duration : 0,
        toggle: () => { if (playback.playing) player.pause(); else void player.play(track, { at: playback.at }); },
        next: player.hasNeighbour(1) ? () => player.stepLoop(1) : null,
        close: () => player.stop(),
        open: onLoops
      };
    }
    return null;
  }

  const percent = `${Math.max(0, Math.min(1, now?.fraction ?? 0)) * 100}%`;
  const noun = now?.kind === "story" ? "story" : "loop";

  if (skin === "chip") {
    if (!now) return null;
    return <span className="tb-btn loop-chip playing">
      <button className="loop-chip-play" onClick={now.toggle} aria-label={now.playing ? "Pause" : "Play"}>
        {now.playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <button className="loop-chip-what" onClick={now.open}>
        <span className="loop-chip-word">{now.title}</span>
        <span className="loop-chip-at">{now.short}</span>
      </button>
    </span>;
  }

  if (skin === "rail") {
    if (!now) return null;
    return <div className="rail-now" role="group" aria-label="Now playing">
      <button className="rail-now-play" style={{ ["--at" as string]: percent }} onClick={now.toggle}
        aria-label={now.playing ? "Pause" : "Play"}>
        <span className="glyph">{now.playing ? <PauseIcon /> : <PlayIcon />}</span>
      </button>
      <button className="rail-now-what" onClick={now.open} title="Open it">
        <span className="rail-now-title">{now.title}</span>
        <span className="rail-now-sub">{now.short}</span>
      </button>
      <button className="rail-now-next" onClick={() => now.next?.()} disabled={!now.next}
        aria-label={`The next ${noun}`} title={`The next ${noun}`}><NextIcon /></button>
    </div>;
  }

  if (!now && playerOnly) return null;
  if (!now) return <div className="loopbar madebar">
    <button className="madebar-half" onClick={onLoops}>
      <span className="madebar-ic"><NoteIcon /></span>
      <span className="loopbar-title">Loops</span>
      <span className="loopbar-sub">{loopsIn(graph, language).filter((one) => !one.archived).length}</span>
    </button>
    <button className="madebar-half" onClick={onStories}>
      <span className="madebar-ic">📖</span>
      <span className="loopbar-title">Stories</span>
      <span className="loopbar-sub">{storiesIn(graph, language).filter((one) => !one.archived).length}</span>
    </button>
    {onMap && <button className="madebar-half" onClick={onMap}>
      <span className="madebar-ic"><MapIcon /></span>
      <span className="loopbar-title">Map</span>
      <span className="loopbar-sub">{lexemesIn(graph, language).length}</span>
    </button>}
  </div>;

  return <div className="loopbar">
    {/* The hairline sits on the bar's own top rule, so a bar that is playing reads as a progress
        line rather than as a bar with a widget in it. */}
    <span className="loopbar-line" style={{ width: percent }} />
    <button className="loopbar-play" onClick={now.toggle} aria-label={now.playing ? "Pause" : "Play"}>
      {now.playing ? <PauseIcon /> : <PlayIcon />}
    </button>
    <button className="loopbar-main" onClick={now.open}>
      <span className="loopbar-title">{now.title}</span>
      <span className="loopbar-sub">{now.sub}</span>
    </button>
    <button className="icon-btn loopbar-next" onClick={() => now.next?.()} disabled={!now.next}
      aria-label={`The next ${noun}`} title={`The next ${noun}`}><NextIcon /></button>
    <button className="icon-btn loopbar-close" aria-label="Stop and close" title="Stop and close"
      onClick={now.close}><CloseIcon /></button>
  </div>;
}
