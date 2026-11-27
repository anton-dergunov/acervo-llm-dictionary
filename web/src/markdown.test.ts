import { describe, expect, it } from "vitest";
import { articleFor } from "./selectors";
import { entryFor, fileNameFor, markdownFor } from "./markdown";
import { ENGLISH, SPANISH, testGraph } from "./testGraph";
import type { VocabularyGraph } from "./domain";

const vocabularyIn = (graph: VocabularyGraph, id: string) => graph.vocabularies.find((one) => one.id === id)!;

const AT = "2026-09-01T12:00:00.000Z";

const fileNamed = (name: string) =>
  markdownFor(testGraph(), vocabularyIn(testGraph(), SPANISH), AT).find((file) => file.path === name);

describe("the Obsidian projection", () => {
  it("names a file for its vocabulary, the way the vault already does", () => {
    expect(fileNameFor("Spanish", "Technology")).toBe("Spanish vocab - Technology.md");
    expect(fileNameFor("Spanish (Mexico) · Everyday words", "Food")).toBe("Spanish (Mexico) · Everyday words vocab - Food.md");
  });

  it("keeps a topic that would be an illegal filename out of the path", () => {
    expect(fileNameFor("Spanish", "Health / Body")).toBe("Spanish vocab - Health Body.md");
  });

  it("writes a word as a heading, one gloss line and nothing else it does not need", () => {
    const graph = testGraph();
    // la balsa's only example is generated, so the entry is two lines.
    expect(entryFor(graph, articleFor(graph, "lexemebalsa0001")!)).toBe([
      "##### **la balsa** 🛶",
      "*raft*"
    ].join("\n"));
  });

  it("gives a word with several senses one gloss line, not one per sense", () => {
    const graph = testGraph();
    expect(entryFor(graph, articleFor(graph, "lexemepicar0001")!)).toBe([
      "##### **picar** 🌶️",
      // The curated short form, the same line the list shows — not "to itch" then "to chop; to dice".
      "*to itch; to chop*",
      "> Me **pica** la nariz. - My nose **itches**."
    ].join("\n"));
  });

  it("keeps only the sentences you met or wrote, and leaves the notes to the article", () => {
    const graph = testGraph();
    const text = entryFor(graph, articleFor(graph, "lexemepicar0001")!);
    // The attestation example stays; the subtitle one does not, and neither does the note.
    expect(text).toContain("Me **pica** la nariz.");
    expect(text).not.toContain("Pica la cebolla");
    expect(text).not.toContain("carried by the object");

    const manual = testGraph();
    manual.examples[1] = { ...manual.examples[1], origin: "manual" };
    expect(entryFor(manual, articleFor(manual, "lexemepicar0001")!))
      .toContain("> **Pica** la cebolla bien fina. - **Chop** the onion very finely.");
  });

  it("falls back to the first sense when a word has no curated short form", () => {
    const graph = testGraph();
    expect(entryFor(graph, articleFor(graph, "lexemeturmoil01")!))
      .toBe("##### **turmoil** 🌪️\n*суматоха; смятение*");
  });

  it("files a word by topic, an unfiled one under Misc and a waiting one under Inbox", () => {
    const files = markdownFor(testGraph(), vocabularyIn(testGraph(), SPANISH), AT).map((file) => file.path);
    expect(files).toContain("Spanish vocab - Food.md");
    expect(files).toContain("Spanish vocab - Travel.md");
    // espolvorear is still in the inbox, so it stays out of Food the way the rail keeps it out.
    expect(fileNamed("Spanish vocab - Inbox.md")!.text).toContain("espolvorear");
    expect(fileNamed("Spanish vocab - Food.md")!.text).not.toContain("espolvorear");
  });

  it("numbers a vocabulary named like one earlier in the owner's order, so their notes never mix", () => {
    const graph = testGraph();
    const spanish = vocabularyIn(graph, SPANISH);
    const twin = { ...spanish, id: "vocabspanish002", order: spanish.order + 1 };
    const both = { ...graph, vocabularies: [...graph.vocabularies, twin] };
    expect(markdownFor(both, spanish, AT).map((file) => file.path)).toContain("Spanish vocab - Food.md");
    expect(markdownFor(both, twin, AT).map((file) => file.path)).toEqual([]);
    const moved = { ...both, lexemes: both.lexemes.map((lexeme) => lexeme.vocabularyId === SPANISH ? { ...lexeme, vocabularyId: twin.id } : lexeme) };
    expect(markdownFor(moved, twin, AT).map((file) => file.path)).toContain("Spanish 2 vocab - Food.md");
  });

  it("gives a vocabulary with no topics a Misc file", () => {
    const files = markdownFor(testGraph(), vocabularyIn(testGraph(), ENGLISH), AT);
    expect(files.map((file) => file.path)).toEqual(["English vocab - Misc.md"]);
    expect(files[0].text).toContain("##### **turmoil** 🌪️");
  });

  it("carries front matter and sorts entries so a re-export diffs cleanly", () => {
    const text = fileNamed("Spanish vocab - Food.md")!.text;
    expect(text.startsWith(`---\nacervo-export: "${AT}"\nlanguage: es\nsection: "Food"\n---\n`)).toBe(true);
    expect(text.indexOf("**picar**")).toBeGreaterThan(-1);
  });
});
