/**
 * The Loops surface: the loops you have, and the one you are playing.
 *
 * A player is a place you go to, so it takes the column rather than sitting over the list — and it
 * takes the whole height, so the controls are a footer that cannot scroll away.
 *
 * **One back arrow, and its meaning follows the level**: on an open loop it returns to the loops,
 * and on the loops it returns to your words. Modelled on the article's `.art-bar`, and present at
 * every width for the reason that one is — a surface that replaces the list has to carry the way
 * back out of itself, and a phone has no rail to fall back on.
 *
 * A loop's state is derived and there is no status column: an empty `audioRef` is the whole of what
 * "not rendered yet" means, and the job says how far along it is. So a loop whose render failed
 * simply reads as one that was asked for and not made, and Try again queues another.
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import type { LoopMusic } from "./api";
import { jobFor, jobStream, isOpen as jobIsOpen } from "./jobs";
import { stripOf } from "./ProgressStrip";
import type { Loop, VocabularyGraph } from "./domain";
import { BackIcon, HourglassIcon, PauseIcon, PlayIcon, PlusIcon } from "./icons";
import * as player from "./loops";
import { useLoopSchema } from "./LoopMusic";
import LoopPlayer from "./LoopPlayer";
import SwipeRow from "./SwipeRow";
import { formatLabel, loopIsReady, loopItemsOf, loopTitle, loopTrackOf, loopsIn } from "./selectors";

function clock(seconds: number | null): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function LoopView({ graph, language, onMake, onClose, onDelete, onChangeMusic, onToggleKeep }: {
  graph: VocabularyGraph;
  language: string;
  onMake(): void;
  /** Back to the words. The loop keeps playing; the bar and the chip are what it plays behind. */
  onClose(): void;
  /** Online-only and loud when it fails, like every other write. */
  onDelete(loopId: string): void;
  onChangeMusic(loopId: string, music: LoopMusic): void;
  /** Keep this loop's music as a favourite, or stop keeping it. */
  onToggleKeep(loop: Loop): void;
}) {
  const playback = player.usePlayback();
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const loops = loopsIn(graph, language);
  const [openId, setOpenId] = useState<string | null>(playback.loopId);
  const open = loops.find((loop) => loop.id === openId) ?? null;
  const { schema } = useLoopSchema();

  /* The queue the player moves through when Next, or Play the next one, asks for another. Kept in
     the player rather than here, so leaving this surface does not end it: a loop goes on playing
     while you read a word, which is most of the point of having one. */
  useEffect(() => {
    player.setQueue(loops.map((loop) => loopTrackOf(graph, loop)));
  }, [graph, loops.map((loop) => loop.id).join()]);

  if (open) {
    return <section className="loops">
      <div className="loops-back">
        <button className="icon-btn" onClick={() => setOpenId(null)} aria-label="Back to the loops"><BackIcon /></button>
        <span className="label">Loops</span>
        <span className="spacer" />
      </div>
      <LoopPlayer
        track={loopTrackOf(graph, open)} graph={graph}
        onChangeMusic={(music) => onChangeMusic(open.id, music)}
        onToggleKeep={() => onToggleKeep(open)}
      />
    </section>;
  }

  return <section className="loops">
    <div className="loops-back">
      <button className="icon-btn" onClick={onClose} aria-label="Back to the list"><BackIcon /></button>
      <span className="label">Your words</span>
      <span className="spacer" />
    </div>

    <div className="loops-head">
      <h2>Loops</h2>
      <span className="spacer" />
      <button className="tb-btn primary" onClick={onMake}><PlusIcon /><span>Make a loop</span></button>
    </div>

    {loops.length === 0 && <p className="empty">
      No loops yet. A loop takes a handful of your words and sets them to music, so they are learned
      while you are doing something else.
    </p>}

    <div className="loops-list">
      {loops.map((loop) => {
        const items = loopItemsOf(graph, loop.id);
        const ready = loopIsReady(loop);
        const job = jobFor(live, "loop", loop.id);
        const making = jobIsOpen(job);
        const failure = job?.state === "failed"
          ? job.message || stripOf(job)?.failure || job.error || ""
          : "";
        const here = playback.loopId === loop.id && playback.playing;
        /* Delete is the row's one action, by right-click or by swipe (`SwipeRow`). The row itself is
           not `disabled` even when there is nothing to play: a loop that was never made is the one
           you most want rid of, and a disabled button answers no gesture at all. */
        return <SwipeRow
          key={loop.id}
          actions={[{ label: "Delete", menuLabel: "Delete this loop", tone: "danger", run: () => onDelete(loop.id) }]}
        >
          <button
            className={`loop-row${playback.loopId === loop.id ? " on" : ""}`}
            aria-disabled={!ready}
            onClick={() => {
              if (!ready) return;
              setOpenId(loop.id);
              if (!here) void player.play(loopTrackOf(graph, loop));
            }}
          >
            <span className={`loop-go${ready ? "" : " pending"}`}>
              {ready ? (here ? <PauseIcon /> : <PlayIcon />) : <HourglassIcon />}
            </span>
            <span className="loop-main">
              <span className="loop-title">{loopTitle(graph, loop)}</span>
              <span className="loop-sub">
                {ready && making
                  /* New music being made for a loop that already plays: it goes on playing the
                     old track until this finishes, so the row says both. */
                  ? <span className="doing">New music · {stripOf(job)?.phases.map((phase) => phase.text).join(" · ") || "queued"}</span>
                  : ready
                  ? `${formatLabel(schema?.formats, loop.format)} · ${items.length} words · ${clock(loop.durationSeconds)}`
                  : making
                    /* What it is *doing*, in the generator's own words — this is a four-minute
                       operation and "being made" says nothing you could not already see. */
                    ? <span className="doing">{stripOf(job)?.phases.map((phase) => phase.text).join(" · ") || "Being made…"}</span>
                    /* Why, not only that. The reason is on the job the whole time; saying "never
                       made" and nothing else is what left a failure with no next step. */
                    : <span className="warn">{failure ? `Never made · ${failure}` : "Never made"}</span>}
              </span>
            </span>
          </button>
        </SwipeRow>;
      })}
    </div>

    {playback.failed && <p className="config-help warn">{playback.failed}</p>}
  </section>;
}
