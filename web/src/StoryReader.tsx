/**
 * Reading a story: a deck of pages, one part to a page, and a last page that lists the words.
 *
 * **A deck rather than a scroller**, and that is the whole layout decision. A part is two to four
 * sentences under a picture, which is about one screen — so a column of them is a page you scroll to
 * see what a swipe would show whole. It is the same deck a word's cards are (`deck.tsx`), and so it
 * moves the same way: a swipe that follows the finger, a horizontal scroll, the arrow keys, and two
 * arrows that sit beside the column when there is margin for them and under it when there is not.
 * There are no dots and no footer — where you are is the counter in the header, and a control that
 * needs its own row is a row the story does not get. The ivy leaves are for the wide layout only,
 * where they fill the space the picture leaves the words; narrow, the picture opens the page.
 *
 * **The translation is never drawn before it is asked for**, which is `LoopPlayer`'s rule about an
 * answer arriving before the recall gap has passed, in the one other place Acervo has one. The
 * space it will take is held open, so revealing it does not move the story under the reader's eye.
 *
 * Marks are found rather than stored: `storySpans` locates the forms the writer reported, and a
 * form it cannot find is simply not marked. The translation is marked the same way from the words
 * the translator reported, and a story translated before that was asked for simply has none.
 * See `selectors.ts`.
 *
 * **A part can be read aloud**, by the button beside its heading. Pressing it while it plays pauses it
 * and pressing it again carries on; there is no scrubber, because swiping to another part and back is
 * the way to begin again — a page that stops being the one on screen stops its audio and forgets the
 * position. A part read by a directed voice also knows where its passages are, and each is then a
 * place to start: started while nothing plays it plays that passage alone, started while it plays it
 * moves there. The passage that is sounding is tinted, and **nothing about it moves the text** — the
 * tint is a background, never padding, weight or size. See `storyAudio.ts`.
 *
 * **A tap on a word looks it up and plays nothing** (`LookUpSheet.tsx`): the passage it is in is the
 * sheet's button instead, and a tap on anything else in a passage — its punctuation, a gap — starts
 * it as a tap always did.
 *
 * Only a page and its neighbours fetch their picture. Every page is mounted — that is what lets a
 * swipe show the next one under the finger — but a picture is a blob behind bearer auth, and a
 * story of six should not ask for six at once to read the first.
 */

import { useContext, useEffect, useLayoutEffect, useMemo, useState, type MouseEvent } from "react";
import { DeckEdges, Hedera, useDeck } from "./deck";
import type { Story, StoryPart, StoryWord } from "./domain";
import { BackIcon, PauseIcon, PlayIcon } from "./icons";
import { LookUpContext, LookUpSheet, useLookUp, type LookUpAction } from "./LookUpSheet";
import { usePicture } from "./picture";
import { playRuns } from "./pronunciation";
import { SelectionPill } from "./SelectionPill";
import { runsOf } from "./selectionSpeech";
import { segmentSpans, storySpans, type StorySpan, type StoryWordEntry } from "./selectors";
import { playSegment, stopPart, toggle, useStoryAudio } from "./storyAudio";
import { wordAtPoint, wordInSelection, type TappedWord } from "./tapWord";

function Picture({ part, title, near }: { part: StoryPart; title: string; near: boolean }) {
  const { url, error } = usePicture(near ? part.imageRef : null);
  // The frame is always here, drawn or not: a picture that arrives into space already reserved
  // does not move the words under it.
  return <div className={`story-pic${url ? " is-ready" : ""}`}>
    {url
      ? <img src={url} alt={part.imagePrompt || `Picture for ${title}`} />
      : <span className="story-pic-note">
        {error ? "That picture could not be read."
          : part.failureReason ? "No picture for this part."
            // A picture that exists and has not arrived yet is not one being drawn.
            : part.imageRef ? "" : "Drawing…"}
      </span>}
  </div>;
}

/** One run of a part's text: the word marked, or plain. A mark says which word it is, so a tap on
    it is answered from the words you hold. */
function Runs({ spans }: { spans: StorySpan[] }) {
  return <>{spans.map((span, position) => (
    span.lexemeId
      ? <b key={position} className="story-mark" data-lexeme={span.lexemeId}>{span.text}</b>
      : <span key={position}>{span.text}</span>
  ))}</>;
}

function PartPage({ story, part, number, words, near, active, recording, revealed, onReveal, onHide, onLook, onLookAway }: {
  story: Story;
  part: StoryPart;
  number: number;
  words: StoryWord[];
  near: boolean;
  /** Whether this is the page on screen. The audio of any other page is stopped. */
  active: boolean;
  /** The story is still being made and this part's recording is one of the things it will do. */
  recording: boolean;
  revealed: boolean;
  onReveal(): void;
  onHide(): void;
  /** A word was tapped, with what the tap would otherwise have played. */
  onLook(tapped: TappedWord, play: LookUpAction | null): void;
  /** Something that is not a word was tapped. */
  onLookAway(): void;
}) {
  const runs = useMemo(
    () => segmentSpans(part.text, words, part.audioSegments), [part.text, words, part.audioSegments]);
  const tappable = runs.some((run) => run.segment !== null);
  const audio = useStoryAudio();
  const mine = audio.partId === part.id;
  const status = mine ? audio.status : "idle";
  // The page that is no longer on screen stops, and so does one that is unmounted. A stopped part
  // forgets its position, so coming back to it starts from the top.
  useEffect(() => { if (!active) stopPart(part.id); }, [active, part.id]);
  useEffect(() => () => stopPart(part.id), [part.id]);
  /* **Never disabled while the story's job has it in hand.** It was, and that was wrong in the one
     case it mattered: a job resting out a daily quota holds the part for twenty-five minutes, and a
     dead button with no explanation is all you get. Pressing it records the part now, through the
     same function the job would have used; the job then finds it done and moves on. */
  const queued = recording && !part.audioSegments.length && status === "idle";
  const label = status === "busy" ? (part.audioSegments.length ? "Loading the recording" : "Recording this part — press to cancel")
    : status === "playing" ? "Pause" : status === "paused" ? "Carry on"
      : queued ? "Waiting to be recorded — press to record it now" : "Read this part aloud";
  /* A tap on a word looks it up and plays nothing; the passage it is in is the sheet's button. A tap
     on anything else in a passage — its punctuation, a gap — plays it, as a tap always did. */
  const touch = (event: MouseEvent<HTMLParagraphElement>) => {
    // A drag that selected text is a selection, not a touch on a passage.
    if (window.getSelection()?.toString()) return;
    const tapped = wordAtPoint(event, event.currentTarget, story.language);
    const from = tapped ? tapped.range.startContainer.parentElement : event.target instanceof Element ? event.target : null;
    const passage = tappable ? from?.closest("[data-segment]") : null;
    const index = passage ? Number(passage.getAttribute("data-segment")) : null;
    if (tapped) {
      const sounding = status === "playing" || status === "paused";
      onLook(tapped, index === null ? null
        : { label: sounding ? "From here" : "This passage", run: () => playSegment(part, index) });
      return;
    }
    onLookAway();
    if (index !== null) playSegment(part, index);
  };
  // The same word in the reader's own language, where the translator said what it became.
  const translated = useMemo(
    () => storySpans(part.translation, words, "translationForms"), [part.translation, words]);
  return <article className="card story-card" aria-label={`Part ${number}`}>
    <div className="story-body">
      <Picture part={part} title={story.title || "this story"} near={near} />
      <div className="story-copy">
        <Hedera side="above" />
        <h3 className="story-head">
          {part.heading && <><span className="story-no">{number}</span> · {part.heading}</>}
          <button
            type="button" className={`say head always story-listen${status === "playing" || status === "paused" ? " playing" : ""}${status === "busy" || queued ? " busy" : ""}`}
            aria-label={label} aria-busy={status === "busy"} title={label}
            onClick={() => toggle(part)}
          >{status === "playing" ? <PauseIcon /> : <PlayIcon />}</button>
        </h3>
        {mine && audio.failed && <p className="story-audio-note" role="status">{audio.failed}</p>}
        <p className={`story-text${tappable ? " tappable" : ""}`} lang={story.language} onClick={touch}>
          {runs.map((run, position) => run.segment === null
            ? <Runs key={position} spans={run.spans} />
            : <span
              key={position} data-segment={run.segment}
              className={`story-seg${mine && status !== "idle" && audio.segment === run.segment ? " on" : ""}`}
            ><Runs spans={run.spans} /></span>)}
        </p>

        {/* The space is held whether or not it has been asked for, so revealing moves nothing. */}
        <div className="story-tr-slot">
          {revealed
            ? <>
              <p className="story-tr">
                {part.headingTranslation && <span className="story-tr-head">{part.headingTranslation}. </span>}
                {translated.map((span, position) => (
                  span.lexemeId
                    ? <b key={position} className="story-mark">{span.text}</b>
                    : <span key={position}>{span.text}</span>
                ))}
              </p>
              {/* A way back to the withheld state: reading it again is the point of the app, and a
                  translation that could only ever be revealed would be there for the rest of the
                  visit. A button and not a tap on the text, so the text can still be selected. */}
              <button className="story-hide" onClick={onHide} aria-label="Hide the translation">Hide</button>
            </>
            : <button className="story-reveal" onClick={onReveal} disabled={!part.translation}>
              {part.translation ? "Tap to read it in your own language" : "Not translated yet"}
            </button>}
        </div>
        <Hedera side="below" />
      </div>
    </div>
  </article>;
}

/**
 * The last page: the words the story was made from, each as it looks in the word list. It is the
 * one place a story says what it was for, and a word it could not work in is shown, dimmed, rather
 * than left out — asked for and not used is a fact about the story.
 */
function WordsPage({ entries }: { entries: StoryWordEntry[] }) {
  return <article className="card story-card story-words-page" aria-label="Words in this story">
    <div className="story-body">
      <div className="story-copy">
        <Hedera side="above" />
        <h3 className="story-head">Words</h3>
        <div className="rows">
          {entries.map((entry) => <div key={entry.lexemeId} className={`row${entry.used ? "" : " unused"}`}>
            <span className="plate" aria-hidden="true">{entry.emoji}</span>
            <span>
              <span className="word">{entry.headword}</span>
              {entry.gloss && <span className="gloss">{entry.gloss}</span>}
            </span>
          </div>)}
        </div>
        <Hedera side="below" />
      </div>
    </div>
  </article>;
}

export default function StoryReader({ story, title, parts, words, entries, recording = false, startAt = 0, onBack }: {
  story: Story;
  /** What the header calls it: its own title, or the words it was asked to teach. */
  title: string;
  parts: StoryPart[];
  words: StoryWord[];
  entries: StoryWordEntry[];
  /** The story's job is still going and has its recording still to do. */
  recording?: boolean;
  /** The page to open on: where the owner was, coming back from a word opened from this story. */
  startAt?: number;
  onBack(): void;
}) {
  const pages = parts.length ? parts.length + 1 : 0;
  const { root, track, at, go, jump, beside, onScroll } = useDeck(story.id);
  useLayoutEffect(() => { if (startAt) jump(startAt); }, [story.id]);
  const services = useContext(LookUpContext);
  const lookUp = useLookUp(services);
  const { open: look, close: lookAway } = lookUp;
  // The sheet belongs to the page it was opened on.
  useEffect(() => lookAway(), [at, lookAway]);
  const lookAt = (tapped: TappedWord, play: LookUpAction | null) => look({
    tapped, play, language: story.language, sourceTitle: `Story · ${title}`,
    from: { kind: "story", storyId: story.id, page: at }
  });
  const listenToSelection = (range: Range) => {
    if (!root.current) return;
    void playRuns(runsOf(range, root.current, new Map(), story.language)).catch((error: unknown) =>
      services?.notify(error instanceof Error ? error.message : "That selection could not be read aloud."));
  };
  const lookUpSelection = (range: Range) => {
    const tapped = root.current ? wordInSelection(range, root.current, story.language) : null;
    if (tapped) lookAt(tapped, null);
  };
  /* Which parts have been turned over. Per part rather than one switch for the story, because
     revealing one answer must not reveal the next — and it is deliberately *not* remembered
     between visits: coming back to a story you have read is reading it again. */
  const [shown, setShown] = useState<Set<string>>(() => new Set());
  const reveal = (id: string) => setShown((current) => new Set(current).add(id));
  const hide = (id: string) => setShown((current) => {
    const next = new Set(current);
    next.delete(id);
    return next;
  });

  return <div className={`cards story-read${beside ? " edges-beside" : ""}`} ref={root}>
    {/* Where you are, and what it is, in the line the back arrow already owns: the way back on the
        left, the title in the middle of the view, the counter on the right. The title gives way (it
        is cut short) before either side does. */}
    <div className="loops-back story-bar">
      <span className="story-bar-side">
        <button className="icon-btn" onClick={onBack} aria-label="Back to the stories"><BackIcon /></button>
        <span className="label">Stories</span>
      </span>
      <span className="story-bar-title">{title}</span>
      {/* An empty cell when there is no counter, so the title stays in the middle column. */}
      {pages > 0
        ? <span className="story-bar-count">{Math.min(at + 1, pages)} / {pages}</span>
        : <span />}
    </div>

    {parts.length === 0
      ? <p className="empty">This story has not been written yet.</p>
      : <div className="cards-stage">
        <div className="cards-track" ref={track} onScroll={onScroll}>
          {parts.map((part, index) => <PartPage
            key={part.id} story={story} part={part} number={index + 1} words={words}
            near={Math.abs(index - at) <= 1} active={index === at} recording={recording}
            revealed={shown.has(part.id)} onReveal={() => reveal(part.id)} onHide={() => hide(part.id)}
            onLook={lookAt}
            onLookAway={lookAway}
          />)}
          <WordsPage entries={entries} />
        </div>
      </div>}

    {parts.length > 0
      && <DeckEdges at={at} count={pages} go={go} previous="The part before" next="The next part" />}
    <SelectionPill root={root} onListen={listenToSelection} onLookUp={lookUpSelection} />
    <LookUpSheet state={lookUp} placement="over" />
  </div>;
}
