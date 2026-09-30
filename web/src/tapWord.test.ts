import { afterEach, describe, expect, it } from "vitest";
import { sameLanguage, wordAtPoint, wordInSelection } from "./tapWord";
import { boxesAt, caretOn, forgetTaps, TAP } from "./testTap";

/**
 * jsdom does no layout, so where the caret lands and where a word's boxes are is stubbed: the caret
 * at a given text node and offset, and every word drawn in one box around the point unless a test
 * moves it away. What is tested is everything after that — which block, which word, which sentence.
 */

function page(): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = `
    <h1 lang="es" data-say="lexeme:lexemeperro0001">el perro</h1>
    <p class="story" lang="es">Cada martes, un <b data-lexeme="lexemeperro0001">perro</b> entra.<button>▶</button> Camina con paso firme.</p>
    <p class="tr" lang="en">Every Tuesday, a dog walks in.</p>
  `;
  document.body.replaceChildren(root);
  return root;
}

const caretIn = (root: HTMLElement, selector: string, word: string, into = 1) =>
  caretOn(root.querySelector(selector)!, word, into);
const tap = TAP;

afterEach(forgetTaps);

describe("the word under a tap", () => {
  it("is the word, its sentence, and the word the text marks it as", () => {
    const root = page();
    caretIn(root, ".story", "perro", 2);
    boxesAt(100, 50);
    const found = wordAtPoint(tap, root, "es");
    expect(found?.word).toBe("perro");
    expect(found?.lexemeId).toBe("lexemeperro0001");
    expect(found?.sentence).toEqual({ text: "Cada martes, un perro entra.", selection: { start: 16, end: 21 } });
  });

  it("reads past a button inside the text without miscounting", () => {
    const root = page();
    caretIn(root, ".story", "paso");
    boxesAt(100, 50);
    const found = wordAtPoint(tap, root, "es");
    expect(found?.word).toBe("paso");
    expect(found?.lexemeId).toBeNull();
    expect(found?.sentence.text).toBe("Camina con paso firme.");
    expect(found?.sentence.selection).toEqual({ start: 11, end: 15 });
  });

  it("selects nothing when the finger is near the word but not on it", () => {
    const root = page();
    caretIn(root, ".story", "paso");
    boxesAt(400, 50);
    expect(wordAtPoint(tap, root, "es")).toBeNull();
  });

  it("does not look up text in another language, nor what a surface refuses", () => {
    const root = page();
    caretIn(root, ".tr", "dog");
    boxesAt(100, 50);
    expect(wordAtPoint(tap, root, "es")).toBeNull();

    caretIn(root, "h1", "perro");
    expect(wordAtPoint(tap, root, "es")?.word).toBe("perro");
    expect(wordAtPoint(tap, root, "es", (block) => !block.closest('[data-say^="lexeme:"]'))).toBeNull();
  });

  it("finds nothing without a caret to ask", () => {
    const root = page();
    boxesAt(100, 50);
    expect(wordAtPoint(tap, root, "es")).toBeNull();
  });
});

describe("a selection looked up", () => {
  it("is the selected phrase, trimmed, in the sentence it sits in", () => {
    const root = page();
    const text = root.querySelector(".story")!.lastChild as Text;
    const range = document.createRange();
    const at = text.data.indexOf("con paso firme");
    range.setStart(text, at - 1);
    range.setEnd(text, at + "con paso firme".length);
    const found = wordInSelection(range, root, "es");
    expect(found?.word).toBe("con paso firme");
    expect(found?.sentence).toEqual({ text: "Camina con paso firme.", selection: { start: 7, end: 21 } });
  });
});

describe("the language a block is in", () => {
  it("matches a more precise tag", () => {
    expect(sameLanguage("es-MX", "es")).toBe(true);
    expect(sameLanguage("en", "es")).toBe(false);
    expect(sameLanguage("", "es")).toBe(false);
  });
});
