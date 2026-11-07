/**
 * The frame every make dialog sits in: a title, the choices, and one button that makes the thing.
 *
 * **The button never scrolls away.** It is in a footer outside the scrolling body, with whatever
 * stands in its way said beside it, so the dialog can be read top to bottom or not at all. The body
 * takes the height of what is in it and scrolls only when the window is smaller than that.
 *
 * **A long list opens over the body, not under it.** A dialog offering one of twenty-three styles
 * shows a strip of them, and the strip's last tile shows them all as a grid in place of the body,
 * with a way back in the header: the dialog does not grow to hold a list nobody is reading.
 *
 * Escape goes back from such a grid, and closes the dialog otherwise; so does a click outside it.
 * Focus is in the dialog from the moment it opens, so the key is the dialog's to answer.
 */

import { useEffect, useId, useRef, type ReactNode } from "react";
import { BackIcon } from "./icons";

export default function MakeDialog({ title, back, footer, onClose, children }: {
  title: string;
  /** Set while a grid is open in place of the body: its title, and how to return. */
  back?: { title: string; onBack(): void } | null;
  footer: ReactNode;
  onClose(): void;
  children: ReactNode;
}) {
  const id = useId();
  const frame = useRef<HTMLElement>(null);
  // Focus comes into the dialog when it opens and goes back where it was when it closes, as a modal
  // dialog's should: what is behind it is not what the keyboard is talking to.
  useEffect(() => {
    const before = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    frame.current?.focus({ preventScroll: true });
    return () => before?.focus({ preventScroll: true });
  }, []);
  // One listener for the dialog's life, reading the latest callbacks. Re-adding it whenever they
  // changed lost keys: a key that makes the application render again re-ran the effect while the key
  // was still on its way to the document, which removed the listener it was going to reach.
  const latest = useRef({ back, onClose });
  latest.current = { back, onClose };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      // Taken first, and marked as answered, so the surface behind the dialog does not also close.
      event.preventDefault();
      const { back: open, onClose: close } = latest.current;
      if (open) open.onBack();
      else close();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);

  return <div
    className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
  >
    <section ref={frame} tabIndex={-1} className="settings make-dialog" role="dialog" aria-modal="true" aria-labelledby={id}>
      <header>
        {back && <button type="button" className="make-back" onClick={back.onBack} aria-label={`Back to ${title}`}>
          <BackIcon />
        </button>}
        <h2 id={id}>{back ? back.title : title}</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <div className="make-body">{children}</div>
      <footer className="make-footer">{footer}</footer>
    </section>
  </div>;
}

/** One part of a make dialog: a small label over its controls. */
export function MakeSection({ label, children, aside }: { label: string; children: ReactNode; aside?: ReactNode }) {
  return <section className="make-section" aria-label={label}>
    <div className="make-label"><span>{label}</span>{aside}</div>
    {children}
  </section>;
}
