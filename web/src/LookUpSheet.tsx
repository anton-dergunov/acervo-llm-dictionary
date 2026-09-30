/**
 * Looking up a word tapped while reading — in a story, on a loop's card, in an article
 * (`docs/features/look-up.md`).
 *
 * **The tap moves nothing.** A story does not start reading and a loop does not seek: the owner
 * tapped a word to understand it, so whatever the tap used to do is a button on this sheet instead
 * (`play`). A word you hold is answered from the replica, at once and offline, with the way to its
 * article; any other is asked of the quick look-up a photographed word uses (`POST
 * /capture/resolve`), and **Add files it in the Inbox** through the headless capture job, so the owner
 * goes on reading. Nothing here writes the graph: that job does, through the ordinary save.
 *
 * The state is one hook per surface, `useLookUp`, and the sheet is one component placed at the foot
 * of that surface: over a story's page, between a loop's cards and its controls, inside an article's
 * ask dock. The tapped word is painted with a CSS highlight, which colours text where it already is
 * and so cannot move it; where the highlight API is missing the sheet still names the word.
 */

import { createContext, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { InboxCapture, QuickLookUp, QuickLookUpRequest } from "./api";
import type { VocabularyGraph } from "./domain";
import { CheckIcon, CloseIcon, OpenIcon, PlayIcon, PlusIcon } from "./icons";
import { heldWord, type HeldWord } from "./selectors";
import type { TappedWord } from "./tapWord";

/** Where the owner was reading, so Back from an article opened here comes back to it. */
export type ReadingPlace =
  | { kind: "story"; storyId: string; page: number }
  | { kind: "loop"; loopId: string };

/** What a look-up needs from the application, which the surfaces that read are given by context. */
export interface LookUpServices {
  graph: VocabularyGraph | null;
  lookUp(request: QuickLookUpRequest, signal: AbortSignal): Promise<QuickLookUp>;
  /** Online-only and loud when it fails, like every other write. */
  queue(request: InboxCapture): Promise<unknown>;
  open(lexemeId: string, from: ReadingPlace | null): void;
  notify(message: string): void;
}

export const LookUpContext = createContext<LookUpServices | null>(null);

/** The job the tap used to have, on the sheet instead. */
export interface LookUpAction {
  label: string;
  run(): void;
}

export interface LookUpRequest {
  tapped: TappedWord;
  /** The language being learned on this surface. */
  language: string;
  /** What the owner is reading, which the word's attestation will name. */
  sourceTitle: string | null;
  play?: LookUpAction | null;
  from?: ReadingPlace | null;
  /** The word whose article this is, which is "this word" rather than one to open. */
  self?: string | null;
}

type Answer =
  | { state: "held"; held: HeldWord }
  | { state: "asking" }
  | { state: "done"; found: QuickLookUp }
  | { state: "failed"; message: string };

interface Look extends LookUpRequest {
  answer: Answer;
  added: "no" | "adding" | "added";
}

const HIGHLIGHT = "look-up";

type Highlights = { set(name: string, value: unknown): void; delete(name: string): void };

function highlights(): { registry: Highlights; make(range: Range): unknown } | null {
  const css = (globalThis as { CSS?: { highlights?: Highlights } }).CSS;
  const Make = (globalThis as { Highlight?: new (range: Range) => unknown }).Highlight;
  return css?.highlights && typeof Make === "function"
    ? { registry: css.highlights, make: (range) => new Make(range) }
    : null;
}

const keyOf = (request: QuickLookUpRequest) =>
  `${request.selection.start}:${request.selection.end}\u0000${request.text}`;

export function useLookUp(services: LookUpServices | null) {
  const [look, setLook] = useState<Look | null>(null);
  const asking = useRef<AbortController | null>(null);
  // Tapping back to a word already asked about is free.
  const answered = useRef(new Map<string, QuickLookUp>());

  const close = useCallback(() => {
    asking.current?.abort();
    asking.current = null;
    setLook(null);
  }, []);

  const ask = useCallback((request: LookUpRequest) => {
    if (!services) return;
    asking.current?.abort();
    const question: QuickLookUpRequest = { ...request.tapped.sentence, source: "reading" };
    const key = keyOf(question);
    const known = answered.current.get(key);
    if (known) {
      setLook({ ...request, answer: { state: "done", found: known }, added: "no" });
      return;
    }
    const controller = new AbortController();
    asking.current = controller;
    setLook({ ...request, answer: { state: "asking" }, added: "no" });
    services.lookUp(question, controller.signal).then((found) => {
      answered.current.set(key, found);
      if (asking.current === controller) setLook((now) => now && { ...now, answer: { state: "done", found } });
    }, (error: unknown) => {
      if (controller.signal.aborted) return;
      const message = error instanceof Error ? error.message : "That word could not be looked up.";
      setLook((now) => now && { ...now, answer: { state: "failed", message } });
    });
  }, [services]);

  const open = useCallback((request: LookUpRequest) => {
    const held = services?.graph
      ? heldWord(services.graph, request.language, request.tapped.word, request.tapped.lexemeId)
      : null;
    if (held) {
      asking.current?.abort();
      setLook({ ...request, answer: { state: "held", held }, added: "no" });
    } else ask(request);
  }, [services, ask]);

  const retry = useCallback(() => { if (look) ask(look); }, [look, ask]);

  const add = useCallback(() => {
    if (!services || !look || look.answer.state !== "done" || look.added !== "no") return;
    const { resolution } = look.answer.found;
    setLook({ ...look, added: "adding" });
    services.queue({ text: look.tapped.sentence.text, resolution, sourceTitle: look.sourceTitle }).then(
      () => setLook((now) => now && now.tapped === look.tapped ? { ...now, added: "added" } : now),
      (error: unknown) => {
        setLook((now) => now && now.tapped === look.tapped ? { ...now, added: "no" } : now);
        services.notify(error instanceof Error ? error.message : "That word could not be added.");
      });
  }, [services, look]);

  const openHeld = useCallback((id: string) => {
    if (!services || !look) return;
    const from = look.from ?? null;
    close();
    services.open(id, from);
  }, [services, look, close]);

  // The word is painted while its sheet is open, and only then.
  useEffect(() => {
    const paint = highlights();
    if (!look || !paint) return;
    paint.registry.set(HIGHLIGHT, paint.make(look.tapped.range));
    return () => paint.registry.delete(HIGHLIGHT);
  }, [look?.tapped]);

  // Escape puts the sheet away before it leaves the surface, which the application's own handler does.
  useEffect(() => {
    if (!look) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      close();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [look, close]);

  useEffect(() => () => asking.current?.abort(), []);

  return { look, open, close, retry, add, openHeld };
}

export type LookUpState = ReturnType<typeof useLookUp>;

/** The word the owner holds, whether the replica said so or the server did. */
function heldOf(look: Look): HeldWord | null {
  if (look.answer.state === "held") return look.answer.held;
  if (look.answer.state !== "done" || !look.answer.found.duplicates.length) return null;
  const [first] = look.answer.found.duplicates;
  return {
    id: first.id, headword: first.headword,
    gloss: look.answer.found.resolution.gloss || first.shortGloss || ""
  };
}

/**
 * The sheet. `over` sits over the foot of a story's page, and moves to its top when the tapped word
 * would be under it; `flow` is a row of a column that owns its height (a loop's player); `docked` is
 * the top of the article's ask dock, and `stuck` the foot of a column that scrolls.
 */
export function LookUpSheet({ state, placement }: {
  state: LookUpState;
  placement: "over" | "flow" | "docked" | "stuck";
}) {
  const { look, close, retry, add, openHeld } = state;
  const sheet = useRef<HTMLElement | null>(null);
  const [top, setTop] = useState(false);
  useLayoutEffect(() => {
    if (!look || placement !== "over" || !sheet.current) return;
    // Measured against where the sheet sits at the foot, wherever it sits now.
    const word = look.tapped.range.getBoundingClientRect?.();
    const box = sheet.current.getBoundingClientRect();
    const frame = (sheet.current.offsetParent ?? sheet.current.parentElement)?.getBoundingClientRect();
    setTop(Boolean(word && frame && box.height && word.bottom > frame.bottom - box.height - 20));
  }, [look?.tapped, placement]);
  if (!look) return null;

  const held = heldOf(look);
  const self = Boolean(held && look.self && held.id === look.self);
  const { answer } = look;
  const { text, selection } = look.tapped.sentence;
  return <aside
    ref={sheet} className={`look-sheet ${placement}${top ? " top" : ""}`}
    role="dialog" aria-label="Look up a word"
  >
    <div className="look-head">
      <div className="photo-meaning look-meaning" aria-live="polite">
        {held ? <>
          <strong lang={look.language}>{held.headword}</strong>
          {held.gloss && <span> — {held.gloss}</span>}
          <span className="photo-held"> · {self ? "this word" : "in your words"}</span>
        </> : answer.state === "failed" ? <span className="photo-meaning-failed">{answer.message}</span>
          : answer.state === "done" ? <>
            <strong lang={look.language}>{answer.found.resolution.headword}</strong>
            {answer.found.resolution.gloss && <span> — {answer.found.resolution.gloss}</span>}
          </> : <span className="photo-meaning-pending">
            <strong lang={look.language}>{look.tapped.word}</strong> — looking it up…
          </span>}
      </div>
      <button type="button" className="icon-btn look-close" onClick={close} aria-label="Close"><CloseIcon /></button>
    </div>
    {/* What Add keeps, for a word you do not have: the sentence, with the word in it. */}
    {!held && <p className="look-sentence" lang={look.language}>
      {text.slice(0, selection.start)}<mark>{text.slice(selection.start, selection.end)}</mark>{text.slice(selection.end)}
    </p>}
    <div className="look-actions">
      {held ? !self && <button type="button" className="tb-btn primary" onClick={() => openHeld(held.id)}>
        <OpenIcon /><span>Open {held.headword}</span>
      </button>
        : look.added === "added" ? <span className="look-added" role="status"><CheckIcon /><span>Added to your Inbox</span></span>
          : answer.state === "failed" ? <button type="button" className="tb-btn" onClick={retry}>Try again</button>
            : <button type="button" className="tb-btn primary" onClick={add}
              disabled={answer.state !== "done" || look.added === "adding"}><PlusIcon /><span>Add</span></button>}
      {look.play && <button type="button" className="tb-btn" onClick={look.play.run}>
        <PlayIcon /><span>{look.play.label}</span>
      </button>}
    </div>
  </aside>;
}
