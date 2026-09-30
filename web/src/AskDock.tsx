/* ── the ask dock ────────────────────────────────────────────────────────
   One surface at every width: a bar pinned to the bottom of the article pane, which grows upward
   into a sheet. No side pane, ever (`docs/features/article-chat.md` §7.1). The article column is
   780 px and a tablet in portrait is about 834 px, so a docked side pane would cut the article to
   roughly 400 px to make room for a conversation that is usually two turns long. The dock costs the
   article nothing horizontally at any width, and on a phone it *is* the mobile design rather than a
   degraded version of a desktop one.

   The component is a launcher and a reading surface for prose, and deliberately not the place a
   proposal lives: **the answer to an editing turn is not a chat message, it is the article.** When a
   proposal is accepted the dock hands it up and collapses, and `App` puts the article into review.

   It knows nothing about the graph, the replica or the projection. `ask()` is handed down already
   knowing how to assemble a request, so the document is re-serialised on every turn and the model
   sees the saved article after a save rather than the one it was asked about. */

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { ChatCapture, ChatProposal, ChatResult, ChatTurn } from "./api";
import { AskIcon, ChevronIcon, CloseIcon, PlusIcon, SendIcon } from "./icons";
import { useKeyboardInset } from "./visualViewport";

/**
 * How far the sheet is open. Three stops, no drag library and no intermediate state.
 *
 * `open` rather than `half`: the name was the bug. It described a fixed fraction of the screen, so
 * focusing the composer reserved a large empty box before there was anything to put in it. It is
 * now content-sized with a cap.
 */
export type Detent = "dock" | "open" | "full";

type Phase =
  | { at: "idle" }
  | { at: "thinking" }
  | { at: "failed"; message: string };

/** The one card the latest answer may carry. Cleared by the next turn. */
type Card =
  | { kind: "proposal"; proposal: ChatProposal; modelId: string }
  | { kind: "capture"; capture: ChatCapture };

export interface AskDockProps {
  /** What is being discussed, for the context strip at the `full` detent. */
  headword: string;
  emoji?: string | null;
  /** Held by `App` so it survives the dock unmounting, and lost on reload, on purpose (`§3.3`). */
  turns: ChatTurn[];
  onTurns(next: ChatTurn[]): void;
  /** Assembled by the caller on every turn — subject, reference and neighbours, freshly read. */
  ask(turns: ChatTurn[]): Promise<ChatResult>;
  /** From `syncStatus`, never `navigator.onLine`. Reading never depends on the server; this does. */
  offline: boolean;
  /** The block that was tapped, when one was. Both prefixes the turn and bounds the edit. */
  focus?: { label: string } | null;
  onClearFocus?(): void;
  /** Article subjects only: the reader pressed *Review*. */
  onPropose?(proposal: ChatProposal, modelId: string): void;
  /** Reference subjects only: the reader pressed *Add to my words*. */
  onCapture?(capture: ChatCapture): void;
  /**
   * A turn to send on mount without a press — the capture fold-in (`§8.3`).
   *
   * Sent rather than merely typed, following `AddView`'s own precedent: the decision was taken on
   * the duplicate panel, and asking for it a second time would be a form standing between someone
   * and the thing they already asked for.
   */
  seeded?: string | null;
  /** Said once, when the seeded turn has been sent, so it cannot be sent again on a later visit. */
  onSeedUsed?(): void;
  /**
   * How far open the sheet now is.
   *
   * Reported rather than controlled: the detent is this component's business, but at `full` the
   * article must not be drawn at all, and only the surface holding both can arrange that.
   */
  onDetent?(detent: Detent): void;
  /** Whether `full` is offered. False on the Add view, whose own composer already owns the height. */
  expandable?: boolean;
  /**
   * Sit in the flow rather than pinned to the bottom of a pane.
   *
   * The Add view has no `.pane`: its preview scrolls inside a `Composer`, so a sticky bottom edge
   * resolves against *that* scroller and the sheet floats over the article instead of below it.
   */
  inline?: boolean;
  /**
   * What sits on top of the dock: the article's look-up sheet (`LookUpSheet.tsx`). The dock already
   * owns the foot of the column, so a sheet of its own there would be under it.
   */
  above?: ReactNode;
}

const OFFLINE = "Chat needs the server. Your words are all still here.";

export default function AskDock({
  headword, emoji = null, turns, onTurns, ask, offline,
  focus = null, onClearFocus, onPropose, onCapture, seeded = null, onSeedUsed,
  onDetent, expandable = true, inline = false, above = null
}: AskDockProps) {
  const [detent, setDetent] = useState<Detent>("dock");
  const [draft, setDraft] = useState("");
  const [phase, setPhase] = useState<Phase>({ at: "idle" });
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [card, setCard] = useState<Card | null>(null);
  const thread = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  /* A ref rather than state: a second send must be impossible *during* the first, and state set in
     an async handler is a render behind. */
  const busy = useRef(false);
  const started = useRef(false);
  /* 0 everywhere the layout viewport already shrinks for the keyboard; the keyboard's height on
     iOS Safari, which does not. Without it the composer lands under the keyboard on exactly the
     device this feature is for. */
  const keyboard = useKeyboardInset();

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy.current || offline) return;
    busy.current = true;
    // The focus chip prefixes the turn as well as bounding the edit, so the transcript reads back
    // as what was actually asked rather than losing which block it was about.
    const asked = focus ? `About ${focus.label}: ${question}` : question;
    const next: ChatTurn[] = [...turns, { role: "you", text: asked }];
    onTurns(next);
    setDraft("");
    setFollowUps([]);
    setCard(null);
    setPhase({ at: "thinking" });
    setDetent((now) => (now === "dock" ? "open" : now));
    try {
      const answer = await ask(next);
      onTurns([...next, { role: "acervo", text: answer.reply }]);
      setFollowUps(answer.followUps);
      setPhase({ at: "idle" });
      if (answer.proposal && onPropose) setCard({ kind: "proposal", proposal: answer.proposal, modelId: answer.modelId });
      else if (answer.capture && onCapture) setCard({ kind: "capture", capture: answer.capture });
      onClearFocus?.();
    } catch (error) {
      // The turn stays in the thread. It is what they asked, and losing it would mean typing it
      // again to retry — on the device where typing is the whole cost.
      setPhase({ at: "failed", message: error instanceof Error ? error.message : "That did not work." });
    } finally {
      busy.current = false;
    }
  };

  useEffect(() => {
    if (started.current || !seeded) return;
    started.current = true;
    onSeedUsed?.();
    void send(seeded);
    // Mount only: `send` closes over state that changes every turn, and re-running this would
    // re-ask the seeded question after every answer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seeded]);

  useEffect(() => {
    const list = thread.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [turns, phase, card, followUps]);

  const open = (to: Detent) => {
    setDetent(to);
    if (to !== "dock") requestAnimationFrame(() => composer.current?.focus());
  };

  const step = (way: 1 | -1) => {
    const order: Detent[] = expandable ? ["dock", "open", "full"] : ["dock", "open"];
    const at = order.indexOf(detent) + way;
    if (at >= 0 && at < order.length) setDetent(order[at]);
  };

  useEffect(() => { onDetent?.(detent); }, [detent, onDetent]);

  /* `field-sizing: content` is Chromium-only, and the device this is for runs Safari — so the
     composer is grown by hand. Height to `auto` first, or it can only ever get taller. The cap is
     in CSS, which then scrolls. */
  const grow = (field: HTMLTextAreaElement | null) => {
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${field.scrollHeight}px`;
  };
  useEffect(() => { grow(composer.current); }, [draft]);

  const thinking = phase.at === "thinking";
  const exchanges = Math.max(1, Math.round(turns.length / 2));

  return <section
    className={`ask ask-${detent} ${inline ? "ask-inline" : ""} ${offline ? "ask-off" : ""}`}
    style={{ "--kb": `${keyboard}px` } as CSSProperties}
    aria-label={`Conversation about ${headword}`}
  >
    {above}
    {detent !== "dock" && <header className="ask-head">
      <button
        className="ask-grab" onClick={() => step(detent === "full" ? -1 : 1)}
        aria-label={detent === "full" ? "Shrink the conversation" : "Expand the conversation"}
      ><ChevronIcon /></button>
      {/* At `full` the article is hidden but the word is not (`§7.3`): the masthead becomes a
          one-line strip so what is being discussed is never off screen. */}
      {detent === "full" && <span className="ask-subject">
        <span className="ask-emoji">{emoji || "📄"}</span>{headword}
      </span>}
      <span className="spacer" />
      {turns.length > 0 && <button className="link-btn" onClick={() => {
        onTurns([]); setFollowUps([]); setCard(null); setPhase({ at: "idle" });
      }}>Clear</button>}
      <button className="icon-btn" aria-label="Close the conversation" onClick={() => setDetent("dock")}>
        <CloseIcon />
      </button>
    </header>}

    {detent !== "dock" && <div className="ask-thread" ref={thread}>
      {turns.length === 0 && !thinking && <p className="ask-empty">
        Ask what this word means, how it differs from another, or for one more example.
      </p>}
      {turns.map((turn, index) => <div key={index} className={`ask-turn ${turn.role}`}>
        <span className="ask-who">{turn.role === "you" ? "you" : <AskIcon />}</span>
        <p>{turn.text}</p>
      </div>)}

      {/* A quiet line in the thread, not a spinner over the article: the article stays readable and
          scrollable throughout, and nothing about a pending turn locks it (`§7.4`). */}
      {thinking && <div className="ask-turn acervo ask-thinking">
        <span className="ask-who"><AskIcon /></span><p>Thinking…</p>
      </div>}

      {phase.at === "failed" && <p className="ask-failed">{offline ? OFFLINE : phase.message}</p>}

      {card?.kind === "proposal" && <div className="ask-card">
        <div className="ask-card-head"><span className="ask-card-mark">✎</span>{card.proposal.summary}</div>
        <div className="ask-card-foot">
          <span className="label">
            {card.proposal.ops.length} {card.proposal.ops.length === 1 ? "change" : "changes"}
          </span>
          <span className="spacer" />
          {/* Nothing is applied without this press, and nothing is written without a second. */}
          <button className="tb-btn primary" onClick={() => {
            onPropose?.(card.proposal, card.modelId);
            setCard(null);
            setDetent("dock");
          }}>Review</button>
        </div>
      </div>}

      {card?.kind === "capture" && <div className="ask-card">
        <div className="ask-card-head"><span className="ask-card-mark"><PlusIcon /></span>Add to my words</div>
        <div className="ask-card-foot">
          <span className="label">with what you asked for</span>
          <span className="spacer" />
          <button className="tb-btn primary" onClick={() => onCapture?.(card.capture)}>Add</button>
        </div>
      </div>}

      {/* Two taps replace two sentences of typing. On a phone that is the difference between a
          feature used on a train and one used at a desk.

          Held back while a card is waiting: there is one thing to decide at that moment, and
          "How do I remember it?" beside an un-reviewed edit is an invitation to forget the edit.
          They come back the moment the card is answered, which is when they read as next steps. */}
      {followUps.length > 0 && !thinking && !card && <div className="ask-followups">
        {followUps.map((text) => <button key={text} className="ask-followup" onClick={() => void send(text)}>
          {text}
        </button>)}
      </div>}
    </div>}

    {/* Its own row, so the field keeps the full width. Inline, a chip reading "example 1 of sense 3"
        took more of a phone than the thing you were typing into. */}
    {focus && <div className="ask-chips">
      <button
        type="button" className="ask-chip" onClick={() => onClearFocus?.()}
        aria-label={`Stop asking about ${focus.label}`}
      >{focus.label}<CloseIcon /></button>
    </div>}

    <form
      className="ask-bar"
      onSubmit={(event) => { event.preventDefault(); void send(draft); }}
    >
      <span className="ask-mark"><AskIcon /></span>
      <textarea
        ref={composer}
        className="ask-input"
        rows={1}
        value={draft}
        disabled={offline}
        placeholder={offline ? OFFLINE : `Ask about ${headword}…`}
        aria-label={`Ask about ${headword}`}
        onFocus={() => { if (detent === "dock") setDetent("open"); }}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void send(draft);
          }
          if (event.key === "Escape" && detent !== "dock") {
            event.stopPropagation();
            setDetent("dock");
            composer.current?.blur();
          }
        }}
      />
      <button
        type="submit" className="ask-send" aria-label="Ask"
        disabled={offline || thinking || !draft.trim()}
      ><SendIcon /></button>
      {detent === "dock" && turns.length > 0 && <button
        type="button" className="link-btn ask-resume" onClick={() => open("open")}
      >{exchanges === 1 ? "1 turn" : `${exchanges} turns`}</button>}
    </form>
  </section>;
}
