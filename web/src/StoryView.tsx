/**
 * The Stories surface: the stories you have, and the one you are reading.
 *
 * Modelled on `LoopView.tsx` down to the row (`SwipeRow`), because it is the same shape of thing:
 * a list of made objects, each of which can be open, still being made, or asked for and never made.
 *
 * **One back arrow, and its meaning follows the level**: on an open story it returns to the
 * stories, and on the stories it returns to your words. Present at every width for the reason the
 * loops one is — a surface that replaces the list has to carry the way back out of itself.
 *
 * The list is the loops' list (`MadeList.tsx`): the orders in its head, the top bar's search
 * searching the words in its stories, and the top bar's Add making one.
 *
 * A story's state is derived and there is no status column: having no parts is the whole of what
 * "not written yet" means, and the job says how far along it is. So a story whose writing failed
 * simply reads as one that was asked for and not written, and Try again queues another.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { isRecording, jobFor, jobStream, isOpen as jobIsOpen } from "./jobs";
import { stripOf } from "./ProgressStrip";
import type { Story, VocabularyGraph } from "./domain";
import { BackIcon, HourglassIcon, PauseIcon, PlayIcon } from "./icons";
import { useListening } from "./listening";
import FitWords from "./FitWords";
import { ArchivedFold, MadeHead, MatchLine, StarMark, madeActions, useMadeList } from "./MadeList";
import StoryReader from "./StoryReader";
import { setStoryQueue, useStoryAudio } from "./storyAudio";
import SwipeRow from "./SwipeRow";
import {
  storiesIn, storyIsWritten, storyPartsOf, storyPictures, storyTitle, storyWordEntries, storyWordsOf
} from "./selectors";

function count(amount: number, noun: string): string {
  return `${amount} ${noun}${amount === 1 ? "" : "s"}`;
}

export default function StoryView({ graph, language, languageName, query = "", opening = null, onClose, onDelete, onMark }: {
  graph: VocabularyGraph;
  language: string;
  languageName: string;
  /** The top bar's search, which on this surface searches the words in its stories. */
  query?: string;
  /** The story and page to open on: where the owner was, coming back from a word opened from it. */
  opening?: { storyId: string; page: number } | null;
  /** Back to the words. */
  onClose(): void;
  /** Online-only and loud when it fails, like every other write. */
  onDelete(storyId: string): void;
  /** Star or archive a story, or take either back. Online-only and loud, like every write. */
  onMark(storyId: string, marks: Partial<Pick<Story, "starred" | "archived">>): void;
}) {
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const order = useMadeList(graph, "story", language, query);
  const stories = order.list.rows;
  const [openId, setOpenId] = useState<string | null>(opening?.storyId ?? null);
  const open = storiesIn(graph, language).find((story) => story.id === openId) ?? null;
  // Asked to open one — what is playing, from the bar or the rail — while already here.
  useEffect(() => { if (opening) setOpenId(opening.storyId); }, [opening]);
  // A search is answered by the list, so an open story gives way to it.
  useEffect(() => { if (query.trim()) setOpenId(null); }, [query]);
  /* "The next story" is the next in this list as it is shown, archived ones left out; the player
     keeps it, so leaving the list does not end it. Only written ones can be read aloud. */
  useEffect(() => {
    setStoryQueue(stories.filter((story) => storyIsWritten(graph, story.id)).map((story) => story.id));
  }, [graph, stories.map((story) => story.id).join()]);
  const playback = useStoryAudio();
  /* The reader goes on with the voice: when the story open here is read to its end and the next one
     begins, the next one opens. Only from the story that was sounding — opening another story while
     one plays elsewhere is not followed away from. */
  const sounded = useRef<string | null>(null);
  useEffect(() => {
    const before = sounded.current;
    sounded.current = playback.storyId;
    if (before && playback.storyId && before !== playback.storyId && openId === before) setOpenId(playback.storyId);
  }, [playback.storyId]);
  const listening = useListening();
  const sounding = (id: string) => listening === "story" && playback.storyId === id;

  function row(story: Story) {
        const written = storyIsWritten(graph, story.id);
        const pictures = storyPictures(graph, story.id);
        const words = storyWordsOf(graph, story.id);
        const job = jobFor(live, "story", story.id);
        const making = jobIsOpen(job);
        const failure = job?.state === "failed"
          ? job.message || stripOf(job)?.failure || job.error || ""
          : "";
        return <SwipeRow
          key={story.id} shellClassName="story-shell"
          actions={madeActions("story", story, { onMark: (marks) => onMark(story.id, marks), onDelete: () => onDelete(story.id) })}
        >
          <button
            className={`loop-row${sounding(story.id) ? " on" : ""}${story.archived ? " archived" : ""}`} aria-disabled={!written}
            onClick={() => { if (written) setOpenId(story.id); }}
          >
            {/* The story's own emoji, until it is the one being read aloud: then the transport, as a
                loop's badge is while it plays. */}
            <span className={`loop-go${sounding(story.id) ? "" : " story-go"}${written ? "" : " pending"}`}>
              {!written ? <HourglassIcon /> : sounding(story.id) ? (playback.status === "playing" ? <PauseIcon /> : <PlayIcon />) : (story.emoji || "📖")}
            </span>
            <span className="loop-main">
              <span className="loop-title">{storyTitle(graph, story)}<StarMark on={story.starred} /></span>
              <span className="loop-sub">
                {making
                  /* **One figure while it is being made**, whether or not it can be read yet. The
                     words it was made from are what tells two finished stories apart, but while
                     one is being built the question is how far along it is — and it used to be
                     answered only until the first part landed, after which the line reverted to
                     the word list and the recording went on invisibly for half an hour. */
                  ? <span className="doing">{stripOf(job)?.phases.map((phase) => phase.text).join(" · ") || "Being written…"}</span>
                  : written
                    ? <FitWords className="story-words" words={words.map((word) => word.sourceText)} />
                    /* Why, not only that: the reason is on the job the whole time. */
                    : <span className="warn">{failure ? `Never written · ${failure}` : "Never written"}</span>}
              </span>
              <MatchLine words={order.list.matches.get(story.id)} query={query} language={language} />
            </span>
            <span className="story-meta">
              {/* **Readable is worth saying while the rest is still being made**: a story has all
                  its words the moment it has parts, and the pictures and the recording only make
                  it better. Once it is finished this is ordinary again — what it is and how big. */}
              {making
                ? written && <span className="story-ready">Ready to read</span>
                : written && <>
                  <span className="story-counts">{count(pictures.total, "part")} · {count(words.length, "word")}</span>
                  {(order.plays.get(story.id) ?? 0) > 0 && <span className="story-plays">read {order.plays.get(story.id)}×</span>}
                  {pictures.drawn < pictures.total
                    && <span className="warn">{pictures.drawn} of {pictures.total} drawn</span>}
                </>}
            </span>
          </button>
        </SwipeRow>;
      }

  if (open) {
    /* `reading` widens the column: a story is read beside its picture where there is room, and that
       is wider than the list's measure. The reader owns its own header, where the counter lives. */
    /* `own-player` while the story being read aloud is this one: the bar at the foot and the rail's
       card step aside, as a music player's mini-player does while its own screen is open. */
    return <section className={`loops stories reading${sounding(open.id) ? " own-player" : ""}`}>
      <StoryReader
        story={open}
        title={storyTitle(graph, open)}
        parts={storyPartsOf(graph, open.id)}
        words={storyWordsOf(graph, open.id)}
        entries={storyWordEntries(graph, open.id)}
        recording={isRecording(jobFor(live, "story", open.id))}
        startAt={open.id === opening?.storyId ? opening.page : open.id === playback.storyId ? playback.partIndex : 0}
        onBack={() => setOpenId(null)}
        onStar={() => onMark(open.id, { starred: !open.starred })}
      />
    </section>;
  }

  return <section className="loops stories">
    <div className="loops-back">
      <button className="icon-btn" onClick={onClose} aria-label="Back to the list"><BackIcon /></button>
      <span className="label">Your words</span>
      <span className="spacer" />
    </div>

    <MadeHead kind="story" icon="📖" title="Stories" count={stories.length} archived={order.list.archived.length}
      languageName={languageName} query={query} order={order} />

    {stories.length === 0 && !order.list.archived.length && (query.trim()
      ? <p className="ext-status none-yours">No story of yours uses “{query.trim()}”.</p>
      : <p className="empty">
        No stories yet. A story takes a few of your words and tells them back to you as something
        worth reading, which is how they stick. Make a story, at the top, to start one.
      </p>)}

    <div className="loops-list">
      {stories.map(row)}
      <ArchivedFold count={order.list.archived.length} searching={Boolean(query.trim())}>
        {order.list.archived.map(row)}
      </ArchivedFold>
    </div>
  </section>;
}
