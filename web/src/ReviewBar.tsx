/* ── the bar over a proposal under review ────────────────────────────────
   Its own component rather than more of `App`, because it owns three things `App` has no use for:
   which change you are looking at, how tall the bar is, and how to bring a change into view.

   It knows nothing about record ids or the edit language. `order` is a list of opaque keys in the
   order the article draws them, and the only thing this does with one is find the element carrying
   it — which is why `diffDrafts` builds that list rather than letting this file walk a draft. */

import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { ChevronIcon } from "./icons";

/* The fallback for the bar's height, before it has been measured, is the `66px` in `styles.css`'s
   `scroll-margin-top` — the same kind of static default `.ext-sec` carries. */
function elementFor(key: string, scroller: HTMLElement | null): Element | null {
  // A note has no id of its own, so it is addressed by position. Quoted attribute values, so a
  // draft's `draft:sense:0` placeholder needs no escaping.
  const selector = key.startsWith("note:")
    ? `[data-note="${key.slice(5)}"]`
    : `[data-record="${key}"]`;
  return (scroller ?? document).querySelector(selector);
}

export default function ReviewBar({
  count, order, saving, scroller, onDiscard, onSave, primary = { short: "Save", long: " changes" }
}: {
  count: number;
  /** Every change, in the order the article draws them, so next and previous move down the page. */
  order: readonly string[];
  saving: boolean;
  /** An element the marks live inside: `App`'s `main`, or the Add view's preview. */
  scroller: RefObject<HTMLElement | null>;
  onDiscard(): void;
  onSave(): void;
  /**
   * What the primary button says. On a stored entry it writes; on the Add view it only takes the
   * change into the unsaved document, and calling that "Save" would claim a write that never happens.
   * `long` is dropped first on a narrow screen.
   */
  primary?: { short: string; long?: string };
}) {
  const [at, setAt] = useState(0);
  const bar = useRef<HTMLDivElement>(null);

  /* The bar is sticky at the top of the pane, so a jump has to clear it or the change lands
     underneath. Measured rather than assumed because the bar's height genuinely changes with width —
     the same argument `ExternalArticle` makes for its own sticky nav — and written to the scroller
     as a custom property because there are many jump targets and one bar. */
  useLayoutEffect(() => {
    const element = bar.current;
    const host = scroller.current;
    if (!element || !host) return;
    const measure = () =>
      host.style.setProperty("--review-h", `${Math.round(element.getBoundingClientRect().height)}px`);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
      host.style.removeProperty("--review-h");
    };
  }, [scroller]);

  const show = (index: number) => {
    const key = order[index];
    if (!key) return;
    const target = elementFor(key, scroller.current);
    if (!target) return;
    /* Which mark you are on, set on the element rather than threaded back through `App` and the
       mark slot: it is a transient pointer owned by this bar, it changes on every press, and the
       bar already holds the element. Nothing else needs to know. */
    for (const marked of (scroller.current ?? document).querySelectorAll(".mark-current")) {
      marked.classList.remove("mark-current");
    }
    target.classList.add("mark-current");
    const still = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // One frame, because Safari drops a smooth scroll issued in the same frame as a layout change.
    requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
    });
  };

  /* Land on the first change rather than at the top of the pane. A proposal that edits the third
     sense of a long entry was previously invisible until you went looking for it. */
  useEffect(() => {
    setAt(0);
    show(0);
    // `order` identity changes with the proposal, which is exactly when to jump again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order]);

  const step = (way: 1 | -1) => {
    const next = Math.min(Math.max(at + way, 0), order.length - 1);
    setAt(next);
    show(next);
  };

  return <div className="review-bar" ref={bar}>
    <span className="review-mark">✎</span>
    <span className="label">
      {count} {count === 1 ? "change" : "changes"}<span className="review-long"> proposed</span>
    </span>
    {order.length > 1 && <div className="review-nav">
      <button onClick={() => step(-1)} disabled={at === 0} aria-label="Previous change">
        <ChevronIcon />
      </button>
      <span className="review-at">{at + 1}/{order.length}</span>
      <button onClick={() => step(1)} disabled={at >= order.length - 1} aria-label="Next change">
        <span className="review-down"><ChevronIcon /></span>
      </button>
    </div>}
    <span className="spacer" />
    <button className="tb-btn" onClick={onDiscard}>Discard</button>
    <button className="tb-btn primary" disabled={saving} onClick={onSave}>
      {saving ? "Saving…" : <>{primary.short}{primary.long && <span className="review-long">{primary.long}</span>}</>}
    </button>
  </div>;
}
