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
 * A story's state is derived and there is no status column: having no parts is the whole of what
 * "not written yet" means, and the job says how far along it is. So a story whose writing failed
 * simply reads as one that was asked for and not written, and Try again queues another.
 */

import { useState, useSyncExternalStore } from "react";
import { isRecording, jobFor, jobStream, isOpen as jobIsOpen } from "./jobs";
import { stripOf } from "./ProgressStrip";
import type { VocabularyGraph } from "./domain";
import { BackIcon, HourglassIcon, PlusIcon } from "./icons";
import FitWords from "./FitWords";
import StoryReader from "./StoryReader";
import SwipeRow from "./SwipeRow";
import {
  storiesIn, storyIsWritten, storyPartsOf, storyPictures, storyTitle, storyWordEntries, storyWordsOf
} from "./selectors";

function count(amount: number, noun: string): string {
  return `${amount} ${noun}${amount === 1 ? "" : "s"}`;
}

export default function StoryView({ graph, language, opening = null, onMake, onClose, onDelete }: {
  graph: VocabularyGraph;
  language: string;
  /** The story and page to open on: where the owner was, coming back from a word opened from it. */
  opening?: { storyId: string; page: number } | null;
  onMake(): void;
  /** Back to the words. */
  onClose(): void;
  /** Online-only and loud when it fails, like every other write. */
  onDelete(storyId: string): void;
}) {
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const stories = storiesIn(graph, language);
  const [openId, setOpenId] = useState<string | null>(opening?.storyId ?? null);
  const open = stories.find((story) => story.id === openId) ?? null;

  if (open) {
    /* `reading` widens the column: a story is read beside its picture where there is room, and that
       is wider than the list's measure. The reader owns its own header, where the counter lives. */
    return <section className="loops stories reading">
      <StoryReader
        story={open}
        title={storyTitle(graph, open)}
        parts={storyPartsOf(graph, open.id)}
        words={storyWordsOf(graph, open.id)}
        entries={storyWordEntries(graph, open.id)}
        recording={isRecording(jobFor(live, "story", open.id))}
        startAt={open.id === opening?.storyId ? opening.page : 0}
        onBack={() => setOpenId(null)}
      />
    </section>;
  }

  return <section className="loops stories">
    <div className="loops-back">
      <button className="icon-btn" onClick={onClose} aria-label="Back to the list"><BackIcon /></button>
      <span className="label">Your words</span>
      <span className="spacer" />
    </div>

    <div className="loops-head">
      <h2>Stories</h2>
      <span className="spacer" />
      <button className="tb-btn primary" onClick={onMake}><PlusIcon /><span>Make a story</span></button>
    </div>

    {stories.length === 0 && <p className="empty">
      No stories yet. A story takes a few of your words and tells them back to you as something
      worth reading, which is how they stick.
    </p>}

    <div className="loops-list">
      {stories.map((story) => {
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
          actions={[{ label: "Delete", menuLabel: "Delete this story", tone: "danger", run: () => onDelete(story.id) }]}
        >
          <button
            className="loop-row" aria-disabled={!written}
            onClick={() => { if (written) setOpenId(story.id); }}
          >
            <span className={`loop-go story-go${written ? "" : " pending"}`}>
              {written ? (story.emoji || "📖") : <HourglassIcon />}
            </span>
            <span className="loop-main">
              <span className="loop-title">{storyTitle(graph, story)}</span>
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
            </span>
            <span className="story-meta">
              {/* **Readable is worth saying while the rest is still being made**: a story has all
                  its words the moment it has parts, and the pictures and the recording only make
                  it better. Once it is finished this is ordinary again — what it is and how big. */}
              {making
                ? written && <span className="story-ready">Ready to read</span>
                : written && <>
                  <span className="story-counts">{count(pictures.total, "part")} · {count(words.length, "word")}</span>
                  {pictures.drawn < pictures.total
                    && <span className="warn">{pictures.drawn} of {pictures.total} drawn</span>}
                </>}
            </span>
          </button>
        </SwipeRow>;
      })}
    </div>
  </section>;
}
