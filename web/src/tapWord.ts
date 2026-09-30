/**
 * The word under a tap, in text the owner is reading (`docs/features/look-up.md`).
 *
 * **The DOM is not changed to make words tappable.** No word is wrapped in an element of its own:
 * the browser is asked where the caret would land under the finger (`caretPositionFromPoint`, or
 * WebKit's `caretRangeFromPoint`), and the word around it is chosen by `Intl.Segmenter`. So a story,
 * a loop's line and an article are hit-tested as they are already drawn, and nothing about looking a
 * word up can move a line of text.
 *
 * **A tap near nothing selects nothing.** The caret lands on the nearest letter wherever the finger
 * is — in a margin, past the end of a line — so the point must also fall on the word's own boxes,
 * give or take a fifth of a line: the rule photo capture's tap keeps (`photoText.ts`).
 *
 * Which text counts is the innermost block carrying a `lang` attribute, which every rendered block
 * already has (`selectionSpeech.ts`), in the language being learned. A translation, a gloss or a
 * note in the reader's own language is not looked up.
 */

import { sentenceAt, wordAt } from "./selectionSpeech";

export interface TappedWord {
  word: string;
  /** The sentence the word is in, and where the word sits in it: what the quick look-up is asked. */
  sentence: { text: string; selection: { start: number; end: number } };
  /** The word in the document, which the sheet's highlight paints. */
  range: Range;
  /** The block the word was read from. */
  block: Element;
  /** The word the text itself says this is, where it says so: a story's mark. */
  lexemeId: string | null;
}

/** Whether a block may be looked up in, beyond being in the right language. */
export type Accept = (block: Element) => boolean;

const everything: Accept = () => true;

/** `es` matches `es-MX`: a block's tag may be more precise than the vocabulary's. */
export function sameLanguage(left: string, right: string): boolean {
  const base = (tag: string) => tag.trim().toLowerCase().split("-")[0];
  return Boolean(left) && base(left) === base(right);
}

interface Caret { node: Node; offset: number }

function caretAt(x: number, y: number): Caret | null {
  const doc = document as Document & {
    caretPositionFromPoint?(x: number, y: number): { offsetNode: Node; offset: number } | null;
    caretRangeFromPoint?(x: number, y: number): Range | null;
  };
  if (typeof doc.caretPositionFromPoint === "function") {
    const at = doc.caretPositionFromPoint(x, y);
    return at ? { node: at.offsetNode, offset: at.offset } : null;
  }
  if (typeof doc.caretRangeFromPoint === "function") {
    const at = doc.caretRangeFromPoint(x, y);
    return at ? { node: at.startContainer, offset: at.startOffset } : null;
  }
  return null;
}

/** The block a node's text belongs to, if it may be looked up in. */
function blockOf(node: Node, root: Element, language: string, accept: Accept): Element | null {
  const element = node.nodeType === Node.TEXT_NODE ? node.parentElement : node as Element;
  const block = element?.closest("[lang]") ?? null;
  if (!block || !root.contains(block)) return null;
  if (!sameLanguage(block.getAttribute("lang") ?? "", language) || !accept(block)) return null;
  return block;
}

/** The text of a block as it is read: not a button inside it, nor anything hidden from a reader. */
function readNodes(block: Element): Text[] {
  const nodes: Text[] = [];
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const skip = node.parentElement?.closest("button, [aria-hidden='true']");
    if (skip && skip !== block && block.contains(skip)) continue;
    nodes.push(node);
  }
  return nodes;
}

function offsetIn(nodes: Text[], node: Node, offset: number): number {
  let seen = 0;
  for (const one of nodes) {
    if (one === node) return seen + offset;
    seen += one.data.length;
  }
  return -1;
}

function rangeOver(nodes: Text[], start: number, end: number): Range {
  const range = document.createRange();
  let seen = 0;
  for (const node of nodes) {
    const length = node.data.length;
    if (start >= seen && start <= seen + length) range.setStart(node, start - seen);
    if (end >= seen && end <= seen + length) { range.setEnd(node, end - seen); break; }
    seen += length;
  }
  return range;
}

function onBoxes(range: Range, x: number, y: number): boolean {
  if (typeof range.getClientRects !== "function") return false;
  return Array.from(range.getClientRects()).some((box) => {
    const give = box.height * 0.2;
    return x >= box.left - give && x <= box.right + give && y >= box.top - give && y <= box.bottom + give;
  });
}

function tapped(block: Element, nodes: Text[], start: number, end: number, language: string,
                 lexemeId: string | null): TappedWord {
  const text = nodes.map((node) => node.data).join("");
  return {
    word: text.slice(start, end),
    sentence: sentenceAt(text, start, end, language),
    range: rangeOver(nodes, start, end),
    block,
    lexemeId
  };
}

/** The word under a pointer inside `root`, in `language`, or null for a tap on anything else. */
export function wordAtPoint(
  point: { clientX: number; clientY: number }, root: Element, language: string, accept: Accept = everything
): TappedWord | null {
  const caret = caretAt(point.clientX, point.clientY);
  if (!caret || caret.node.nodeType !== Node.TEXT_NODE) return null;
  const block = blockOf(caret.node, root, language, accept);
  if (!block) return null;
  const nodes = readNodes(block);
  const offset = offsetIn(nodes, caret.node, caret.offset);
  if (offset < 0) return null;
  const text = nodes.map((node) => node.data).join("");
  const word = wordAt(text, offset, language);
  if (!word) return null;
  const found = tapped(block, nodes, word.start, word.end, language,
    caret.node.parentElement?.closest("[data-lexeme]")?.getAttribute("data-lexeme") || null);
  return onBoxes(found.range, point.clientX, point.clientY) ? found : null;
}

/**
 * What a selection inside `root` asks to be looked up: the selected text within the block it begins
 * in, trimmed. This is how a phrase the tap did not widen to is looked up.
 */
export function wordInSelection(range: Range, root: Element, language: string, accept: Accept = everything): TappedWord | null {
  const block = blockOf(range.startContainer, root, language, accept);
  if (!block) return null;
  const nodes = readNodes(block);
  const text = nodes.map((node) => node.data).join("");
  const from = range.startContainer.nodeType === Node.TEXT_NODE ? offsetIn(nodes, range.startContainer, range.startOffset) : 0;
  const to = block.contains(range.endContainer) && range.endContainer.nodeType === Node.TEXT_NODE
    ? offsetIn(nodes, range.endContainer, range.endOffset) : text.length;
  if (from < 0 || to <= from) return null;
  const picked = text.slice(from, to);
  const start = from + (picked.length - picked.trimStart().length);
  const end = to - (picked.length - picked.trimEnd().length);
  return end > start ? tapped(block, nodes, start, end, language, null) : null;
}
