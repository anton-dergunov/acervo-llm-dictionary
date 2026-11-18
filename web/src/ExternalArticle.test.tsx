import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ExternalArticle from "./ExternalArticle";
import type { LookupResult } from "./dictionaries";
import { externalEntryOf } from "./externalEntries";

vi.mock("./dictionaries", () => ({ lookup: vi.fn(async () => []) }));

const kaikki = (id: string, articles: NonNullable<LookupResult["entry"]>["articles"]): LookupResult => ({
  dictionaryId: id, name: id, attribution: "Wiktionary", licence: "CC BY-SA 4.0", origin: "device",
  sourceLang: "fr", entry: { dictionaryId: id, word: "livre", tier: "fields", articles }
});

describe("an external article's gender", () => {
  it("is said once in the masthead, and again only where a source says otherwise", () => {
    const entry = externalEntryOf("livre", [
      kaikki("kaikki-fr-en", [{ headword: "livre", posLabel: "noun", genders: ["masculine", "feminine"],
                                senses: [{ definition: "book" }] }]),
      kaikki("kaikki-fr-fr", [{ headword: "livre", posLabel: "noun", genders: ["masculine"],
                                senses: [{ definition: "Assemblage de feuilles." }] }])
    ]);
    const { container } = render(<ExternalArticle entry={entry} onAdd={() => undefined} />);
    const lines = [...container.querySelectorAll("p.gram")].map((line) => line.textContent);
    expect(lines[0]).toBe("noun·masculine / feminine·French·external dictionary");
    expect(lines.slice(1)).toEqual(["masculine"]);
  });
});
