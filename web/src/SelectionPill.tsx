import { useEffect, useState } from "react";
import { PlayIcon, SearchIcon } from "./icons";

/**
 * Whatever is selected, in the text you are reading: listen to it, or look it up.
 *
 * One pill with two halves, floating above the selection, because a play button on every phrase
 * would be noise and a selection is already the gesture for "this bit". Look up is how a phrase the
 * tap did not widen to is looked up (`LookUpSheet.tsx`); it is absent where nothing can be.
 */
export function SelectionPill({ root, onListen, onLookUp = null }: {
  root: React.RefObject<HTMLElement | null>;
  onListen(range: Range): void;
  onLookUp?: ((range: Range) => void) | null;
}) {
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  useEffect(() => {
    const onChange = () => {
      const selection = window.getSelection();
      const text = selection && !selection.isCollapsed ? selection.toString().trim() : "";
      if (!text || !root.current || !selection?.anchorNode || !root.current.contains(selection.anchorNode)
          || selection.rangeCount === 0) {
        setAt(null);
        return;
      }
      const box = selection.getRangeAt(0).getBoundingClientRect?.();
      if (!box) { setAt(null); return; }
      const half = onLookUp ? 100 : 60;
      setAt({
        left: Math.min(Math.max(box.left + box.width / 2, half), window.innerWidth - half),
        top: Math.max(box.top, 70)
      });
    };
    document.addEventListener("selectionchange", onChange);
    return () => document.removeEventListener("selectionchange", onChange);
  }, [root, onLookUp]);
  if (!at) return null;
  const withRange = (use: (range: Range) => void) => () => {
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) use(selection.getRangeAt(0));
  };
  return <div
    className="sel-say" role="toolbar" aria-label="The selection" style={{ left: at.left, top: at.top }}
    // Pressing it must not collapse the selection it is about to read.
    onMouseDown={(event) => event.preventDefault()}
  >
    <button type="button" className="sel-act" onClick={withRange(onListen)}><PlayIcon /><span>Listen</span></button>
    {onLookUp && <button type="button" className="sel-act" onClick={withRange((range) => {
      onLookUp(range);
      window.getSelection()?.removeAllRanges();
      setAt(null);
    })}><SearchIcon /><span>Look up</span></button>}
  </div>;
}
