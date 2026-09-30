import { describe, expect, it } from "vitest";
import type { SayTarget } from "./pronunciation";
import { runsOf, sentenceAt, sentencesAround, wordAt } from "./selectionSpeech";

/**
 * A selection crosses languages, and the markup says which is which. These build the same shapes the
 * article renders — a Spanish sentence, an English translation, a gloss — and select across them.
 */

function page(): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = `
    <h1 lang="es" data-say="lexeme:lexemepicar0001">picar</h1>
    <div class="ex">
      <p class="t" lang="es" data-say="example:examplepicar010">Me pica la nariz. Creo que voy a estornudar.</p>
      <p class="tr" lang="en">My nose itches.</p>
    </div>
    <p class="note" lang="ru">Не путать с «picante».</p>
  `;
  document.body.replaceChildren(root);
  return root;
}

const targets = new Map<string, SayTarget>([
  ["lexeme:lexemepicar0001", { kind: "lexeme", id: "lexemepicar0001", text: "picar", lang: "es" }],
  ["example:examplepicar010", {
    kind: "example", id: "examplepicar010", lang: "es",
    text: "Me pica la nariz. Creo que voy a estornudar."
  }]
]);

function select(root: HTMLElement, from: string, to: string, fromOffset = 0, toOffset?: number): Range {
  const start = root.querySelector(from)!.firstChild!;
  const end = root.querySelector(to)!.firstChild!;
  const range = document.createRange();
  range.setStart(start, fromOffset);
  range.setEnd(end, toOffset ?? (end.textContent?.length ?? 0));
  return range;
}

describe("reading a selection aloud", () => {
  it("splits it into one run per language, in the order they are on the page", () => {
    const root = page();
    const runs = runsOf(select(root, ".t", ".tr"), root, targets, "es");
    expect(runs.map((run) => [run.lang, run.text])).toEqual([
      ["es", "Me pica la nariz. Creo que voy a estornudar."],
      ["en", "My nose itches."]
    ]);
  });

  it("extends half a sentence to the whole one, and no further", () => {
    const root = page();
    // "pica la" — inside the first sentence of two.
    const runs = runsOf(select(root, ".t", ".t", 3, 10), root, targets, "es");
    expect(runs).toHaveLength(1);
    expect(runs[0].text).toBe("Me pica la nariz.");
  });

  it("plays a whole stored block as its own record, so the kept clip is what is heard", () => {
    const root = page();
    const whole = runsOf(select(root, ".t", ".t"), root, targets, "es");
    expect(whole[0].target?.id).toBe("examplepicar010");
    // Half of it is not that record, so it is read as a selection and nothing is stored.
    expect(runsOf(select(root, ".t", ".t", 3, 10), root, targets, "es")[0].target).toBeNull();
  });

  it("reads a note in the language notes are written in, never the word's", () => {
    const root = page();
    const runs = runsOf(select(root, ".note", ".note"), root, targets, "es");
    expect(runs).toEqual([{ text: "Не путать с «picante».", lang: "ru", target: null }]);
  });

  it("falls back to the article's language for text in no block of its own", () => {
    const root = document.createElement("div");
    root.innerHTML = "<p>suelto</p>";
    document.body.replaceChildren(root);
    const range = document.createRange();
    range.selectNodeContents(root.querySelector("p")!);
    expect(runsOf(range, root, targets, "es")).toEqual([{ text: "suelto", lang: "es", target: null }]);
  });

  it("keeps the whole sentence a span touches, at either end", () => {
    const text = "Uno. Dos. Tres.";
    expect(sentencesAround(text, 6, 8, "es")).toBe("Dos.");
    expect(sentencesAround(text, 2, 7, "es")).toBe("Uno. Dos.");
  });
});

describe("the word and sentence a tap asks about", () => {
  it("measures the tapped word from the start of its own sentence", () => {
    const text = "No viene a buscar migajas. Camina con paso firme.";
    const at = text.indexOf("paso");
    expect(sentenceAt(text, at, at + 4, "es")).toEqual({
      text: "Camina con paso firme.", selection: { start: 11, end: 15 }
    });
  });

  it("takes the word under a character, and a caret just after its last letter", () => {
    const text = "Camina con paso firme.";
    expect(wordAt(text, 12, "es")).toEqual({ start: 11, end: 15 });
    expect(wordAt(text, 15, "es")).toEqual({ start: 11, end: 15 });
    expect(wordAt(text, 11, "es")).toEqual({ start: 11, end: 15 });
  });

  it("finds no word on punctuation or a gap", () => {
    expect(wordAt("firme.  Y", 6, "es")).toBeNull();
  });

  it("chooses a unit around a character in a language written without spaces", () => {
    const text = "我在图书馆看书";
    const found = wordAt(text, text.indexOf("书"), "zh");
    expect(found).not.toBeNull();
    expect(found!.start).toBeLessThanOrEqual(text.indexOf("书"));
    expect(found!.end).toBeGreaterThan(text.indexOf("书"));
  });
});
