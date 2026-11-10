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
 * **The list is drawn as the word list is** (`MadeList.tsx`): its head carries the orders, and the
 * top bar's search, while this surface is open, searches the words in its loops — each row it keeps
 * says which matched. Make is the top bar's Add here. A row's badge is the kind of loop it is, the
 * make dialog's own icon, until it is the one loaded, when it is the transport.
 *
 * A loop's state is derived and there is no status column: an empty `audioRef` is the whole of what
 * "not rendered yet" means, and the job says how far along it is. So a loop whose render failed
 * simply reads as one that was asked for and not made, and Try again queues another.
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import { jobFor, jobStream, isOpen as jobIsOpen } from "./jobs";
import { stripOf } from "./ProgressStrip";
import type { Loop, VocabularyGraph } from "./domain";
import { BackIcon, HourglassIcon, PauseIcon, PlayIcon } from "./icons";
import { formatIcon } from "./LoopFormat";
import * as player from "./loops";
import { useLoopSchema } from "./LoopMusic";
import LoopPlayer from "./LoopPlayer";
import { MadeHead, MatchLine, useMadeList } from "./MadeList";
import SwipeRow from "./SwipeRow";
import { formatLabel, loopIsReady, loopItemsOf, loopTitle, loopTrackOf, loopsIn } from "./selectors";

function clock(seconds: number | null): string {
  const whole = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function LoopView({ graph, language, languageName, query = "", opening = null, onClose, onDelete, onChooseMusic, onToggleKeep }: {
  graph: VocabularyGraph;
  language: string;
  languageName: string;
  /** The top bar's search, which on this surface searches the words in its loops. */
  query?: string;
  /** The loop to open on: the one a word was opened from. Otherwise the one playing, if any. */
  opening?: string | null;
  /** Back to the words. The loop keeps playing; the bar and the chip are what it plays behind. */
  onClose(): void;
  /** Online-only and loud when it fails, like every other write. */
  onDelete(loopId: string): void;
  /** Open New music for this loop. */
  onChooseMusic(loopId: string): void;
  /** Keep this loop's music as a favourite, or stop keeping it. */
  onToggleKeep(loop: Loop): void;
}) {
  const playback = player.usePlayback();
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const order = useMadeList(graph, "loop", language, query);
  const loops = order.list.rows;
  const [openId, setOpenId] = useState<string | null>(opening ?? playback.loopId);
  const open = loopsIn(graph, language).find((loop) => loop.id === openId) ?? null;
  const { schema } = useLoopSchema();
  // A search is answered by the list, so an open player gives way to it.
  useEffect(() => { if (query.trim()) setOpenId(null); }, [query]);

  /* The queue the player moves through when Next, or Play the next one, asks for another: the list
     in the order it is shown. Kept in the player rather than here, so leaving this surface does not
     end it: a loop goes on playing while you read a word, which is most of the point of having one. */
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
        onChooseMusic={() => onChooseMusic(open.id)}
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

    <MadeHead kind="loop" icon="♪" title="Loops" count={loops.length} languageName={languageName} query={query} order={order} />

    {loops.length === 0 && (query.trim()
      ? <p className="ext-status none-yours">No loop of yours uses “{query.trim()}”.</p>
      : <p className="empty">
        No loops yet. A loop takes a handful of your words and sets them to music, so they are learned
        while you are doing something else. Make a loop, at the top, to start one.
      </p>)}

    <div className="loops-list">
      {loops.map((loop) => {
        const items = loopItemsOf(graph, loop.id);
        const ready = loopIsReady(loop);
        const job = jobFor(live, "loop", loop.id);
        const making = jobIsOpen(job);
        const failure = job?.state === "failed"
          ? job.message || stripOf(job)?.failure || job.error || ""
          : "";
        const loaded = playback.loopId === loop.id;
        const here = loaded && playback.playing;
        const Kind = formatIcon(loop.format);
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
            {/* The kind of loop, until it is the one loaded: then the transport. A plate rather than a
                disc, so a row that says what it is never looks like one that plays. */}
            <span className={`loop-go${ready ? "" : " pending"}${ready && !loaded ? " kind" : ""}`}
                  title={formatLabel(schema?.formats, loop.format)}>
              {!ready ? <HourglassIcon /> : loaded ? (here ? <PauseIcon /> : <PlayIcon />) : <Kind />}
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
              <MatchLine words={order.list.matches.get(loop.id)} query={query} language={language} />
            </span>
          </button>
        </SwipeRow>;
      })}
    </div>

    {playback.failed && <p className="config-help warn">{playback.failed}</p>}
  </section>;
}
