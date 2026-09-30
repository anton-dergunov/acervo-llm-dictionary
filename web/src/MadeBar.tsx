/**
 * The ways in to what Acervo *made* from your words, and what is playing — in two shapes, because
 * the two widths want different things.
 *
 * Was `LoopBar.tsx`, and renamed when Stories arrived: it carries both now, and a file called
 * LoopBar that also owns the way in to stories would be a name that lies.
 *
 * **On a phone it is a bar at the foot of the window**, split in three — Loops, Stories and the Map — which is
 * where these belong on a device held in one hand. It is drawn over the list and nowhere else: the
 * article column already carries the view segments, the delete control, the progress strip and the
 * ask dock, and a second dock there is prohibited (`docs/features/loops.md` §2.13). There is
 * deliberately no mini-player over an article. The **+ is gone**: both surfaces carry their own
 * Make button in their own header, and a bar whose job is to be a way in should not also be a way
 * to start something.
 *
 * **On a desktop it is a chip in the top bar, and only while something is sounding.** The resting
 * button it used to draw has moved to the foot of the topic rail, beside Stories, because the top
 * bar was already carrying as much as it can and a third learning method would have made that
 * worse. So on a wide window this renders nothing at all until a loop plays.
 *
 * **The phone's bar can be closed.** Close stops the loop and forgets it as the one playing — it
 * deletes nothing — and the bar goes back to being the way in. Without it a loop heard once held the
 * foot of the list for the rest of the session.
 *
 * Both are the same component in two skins, so what they say can never disagree.
 */

import type { VocabularyGraph } from "./domain";
import { CloseIcon, MapIcon, NoteIcon, PauseIcon, PlayIcon } from "./icons";
import * as player from "./loops";
import { lexemesIn, loopCards, loopsIn, loopTitle, loopTrackOf, loopWordAt, storiesIn } from "./selectors";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function MadeBar({ graph, language, chip, playerOnly = false, onLoops, onStories, onMap }: {
  graph: VocabularyGraph;
  language: string;
  /** True in the top bar, false at the foot of the window. */
  chip: boolean;
  /* The foot bar with a selection over it: the selection bar has taken the ways in's place, so this
     draws only a loop that is playing, and nothing while none is. */
  playerOnly?: boolean;
  onLoops(): void;
  onStories(): void;
  /* The foot bar's third way in. The chip in the top bar has no use for it: the rail is beside it. */
  onMap?(): void;
}) {
  const playback = player.usePlayback();
  const loops = loopsIn(graph, language);
  const loop = playback.loopId ? loops.find((one) => one.id === playback.loopId) ?? null : null;
  const track = loop ? loopTrackOf(graph, loop) : null;
  // The word being taught, so the bar says what you are hearing rather than which file is open.
  const word = track ? loopWordAt(track.items, loopCards(track.cues), playback.at)?.sourceText : null;
  const fraction = loop && playback.duration ? playback.at / playback.duration : 0;

  const toggle = () => {
    if (!track) return;
    if (playback.playing) player.pause();
    else void player.play(track, { at: playback.at });
  };

  if (chip) {
    // Nothing sounding, nothing to say: the way in lives in the rail now.
    if (!loop) return null;
    return <span className="tb-btn loop-chip playing">
      <button className="loop-chip-play" onClick={toggle} aria-label={playback.playing ? "Pause" : "Play"}>
        {playback.playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <button className="loop-chip-what" onClick={onLoops}>
        <span className="loop-chip-word">{word ?? loopTitle(graph, loop, 1)}</span>
        <span className="loop-chip-at">{clock(playback.at)}</span>
      </button>
    </span>;
  }

  if (!loop && playerOnly) return null;
  if (!loop) return <div className="loopbar madebar">
    <button className="madebar-half" onClick={onLoops}>
      <span className="madebar-ic"><NoteIcon /></span>
      <span className="loopbar-title">Loops</span>
      <span className="loopbar-sub">{loops.length}</span>
    </button>
    <button className="madebar-half" onClick={onStories}>
      <span className="madebar-ic">📖</span>
      <span className="loopbar-title">Stories</span>
      <span className="loopbar-sub">{storiesIn(graph, language).length}</span>
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
    <span className="loopbar-line" style={{ width: `${Math.max(0, Math.min(1, fraction)) * 100}%` }} />
    <button className="loopbar-play" onClick={toggle} aria-label={playback.playing ? "Pause" : "Play"}>
      {playback.playing ? <PauseIcon /> : <PlayIcon />}
    </button>
    <button className="loopbar-main" onClick={onLoops}>
      <span className="loopbar-title">{word ?? loopTitle(graph, loop, 2)}</span>
      <span className="loopbar-sub">{clock(playback.at)} / {clock(playback.duration)}</span>
    </button>
    <button className="icon-btn loopbar-close" aria-label="Stop and close" title="Stop and close"
      onClick={() => player.stop()}><CloseIcon /></button>
  </div>;
}
