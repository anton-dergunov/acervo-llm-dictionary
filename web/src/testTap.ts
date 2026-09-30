/**
 * A tap on a word, for jsdom, which does no layout: the caret the browser would report under the
 * finger, and the boxes the word would be drawn in. `tapWord.ts` asks for exactly these two things.
 */

type Caret = { caretRangeFromPoint?: (x: number, y: number) => Range | null };

const originalRects = Range.prototype.getClientRects;

/** The caret lands `into` characters into the first text node under `block` that holds `word`. */
export function caretOn(block: Element, word: string, into = 1): void {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const at = node.data.indexOf(word);
    if (at < 0) continue;
    (document as unknown as Caret).caretRangeFromPoint = () => {
      const range = document.createRange();
      range.setStart(node, at + into);
      return range;
    };
    return;
  }
  throw new Error(`no “${word}” under ${block.tagName}`);
}

/** Every word is drawn in one box around (x, y). */
export function boxesAt(x: number, y: number): void {
  Range.prototype.getClientRects = function getClientRects() {
    return [{ left: x - 20, right: x + 20, top: y - 10, bottom: y + 10, width: 40, height: 20 }] as unknown as DOMRectList;
  };
}

/** Where a test taps, which `boxesAt(TAP.clientX, TAP.clientY)` puts every word under. */
export const TAP = { clientX: 100, clientY: 50 };

/** Aim at `word` in `block`, with the word drawn under the tap. */
export function aimAt(block: Element, word: string, into = 1): void {
  caretOn(block, word, into);
  boxesAt(TAP.clientX, TAP.clientY);
}

export function forgetTaps(): void {
  delete (document as unknown as Caret).caretRangeFromPoint;
  Range.prototype.getClientRects = originalRects;
}
