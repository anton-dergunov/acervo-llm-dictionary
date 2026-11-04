/**
 * Settings ▸ Vocabularies: a language is found by its name and shown by its name and flag, and a
 * vocabulary's variety, level and note are saved with it, through the repository like every other
 * edit of the vocabulary.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type LanguageEntry } from "../api";
import { repository } from "../repository";
import { testGraph } from "../testGraph";
import { VocabularyEditor } from "./Configuration";
import { search } from "./LanguageSearch";
import { SubPages } from "./testVoices";

const LANGUAGES: LanguageEntry[] = [
  { tag: "en", name: "English", autonym: "English", region: "US", varieties: ["US", "GB"] },
  { tag: "zh-Hans", name: "Chinese (Simplified)", autonym: "中文 (简体)", region: "CN", varieties: ["CN", "SG"] },
  { tag: "zh-Hant", name: "Chinese (Traditional)", autonym: "中文 (繁體)", region: "TW", varieties: ["TW", "HK"] },
  { tag: "es", name: "Spanish", autonym: "español", region: "ES", varieties: ["MX", "AR", "ES", "419"] },
  { tag: "fr", name: "French", autonym: "français", region: "FR", varieties: ["FR", "CA", "BE"] },
  { tag: "ru", name: "Russian", autonym: "русский", region: "RU", varieties: ["RU"] }
];

let saved: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.spyOn(backendSession, "languages").mockResolvedValue({ languages: LANGUAGES });
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue({ orders: { plain: [], expressive: [] } } as never);
  saved = vi.spyOn(repository, "saveVocabulary").mockResolvedValue(undefined as never);
});
afterEach(() => vi.restoreAllMocks());

function editor(snapshot = testGraph()) {
  render(<SubPages><VocabularyEditor snapshot={snapshot as never} onNotify={() => undefined} onChanged={() => undefined} /></SubPages>);
}

function withSpanish(changes: object) {
  const graph = testGraph();
  return { ...graph, vocabularies: graph.vocabularies.map((entry) => entry.language === "es" ? { ...entry, ...changes } : entry) };
}

describe("Settings ▸ Vocabularies", () => {
  it("shows each vocabulary by name and flag, and its languages by name", () => {
    const graph = testGraph();
    editor({ ...graph, vocabularies: graph.vocabularies.map((entry) =>
      entry.language === "en" ? { ...entry, region: "GB", level: "C1" } : entry) } as never);
    const english = screen.getByRole("button", { name: /🇬🇧\s+English/ });
    expect(english).toHaveTextContent("🇬🇧 English");
    expect(english).toHaveTextContent("United Kingdom · C1 · translated into Russian");
    expect(screen.getByRole("button", { name: /🇪🇸\s+Spanish/ })).toHaveTextContent("translated into English");
  });

  it("offers the language's varieties with their flags, and the flag follows the one chosen", async () => {
    editor();
    fireEvent.click(screen.getByRole("button", { name: /Spanish/ }));
    const variety = await screen.findByRole("combobox", { name: "Variety" });
    // What the server derived from CLDR, in its order: nothing about Spanish is written here.
    await waitFor(() => expect([...variety.querySelectorAll("option")].map((option) => option.textContent))
      .toEqual(["None", "🇲🇽 Mexico", "🇦🇷 Argentina", "🇪🇸 Spain", "🌐 Latin America"]));
    expect(screen.getByRole("textbox", { name: "Flag" })).toHaveAttribute("placeholder", "🇪🇸");
    fireEvent.change(variety, { target: { value: "AR" } });
    expect(screen.getByRole("textbox", { name: "Flag" })).toHaveAttribute("placeholder", "🇦🇷");
    // Names, never tags, for the languages it is written in.
    expect(screen.getByRole("button", { name: /Senses defined in/ })).toHaveTextContent("🇪🇸 Spanish");
    expect(screen.getByRole("button", { name: /Translated into/ })).toHaveTextContent("🇺🇸 English");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(
      expect.objectContaining({ language: "es", region: "AR", flag: null }), "vocabes00000001"));
  });

  it("keeps a flag pasted over the automatic one, until the variety changes", async () => {
    editor(withSpanish({ flag: "🏴" }) as never);
    fireEvent.click(screen.getByRole("button", { name: /Spanish/ }));
    const flag = await screen.findByRole("textbox", { name: "Flag" });
    expect(flag).toHaveValue("🏴");
    fireEvent.change(flag, { target: { value: "🇨🇴" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveBeenLastCalledWith(expect.objectContaining({ flag: "🇨🇴", region: null }), expect.any(String)));

    fireEvent.click(screen.getByRole("button", { name: /Spanish/ }));
    fireEvent.change(await screen.findByRole("combobox", { name: "Variety" }), { target: { value: "MX" } });
    expect(screen.getByRole("textbox", { name: "Flag" })).toHaveValue("");
  });

  it("saves a level and what the learner says about themselves", async () => {
    editor();
    fireEvent.click(screen.getByRole("button", { name: /Spanish/ }));
    fireEvent.change(await screen.findByRole("combobox", { name: "Level" }), { target: { value: "B1" } });
    fireEvent.change(screen.getByRole("textbox", { name: "About you" }), { target: { value: "  Off to Argentina in March.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(
      expect.objectContaining({ level: "B1", learnerNote: "Off to Argentina in March." }), "vocabes00000001"));
  });

  it("chooses the gloss languages by name, in order, never leaving none", async () => {
    editor();
    fireEvent.click(screen.getByRole("button", { name: /Spanish/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Translated into/ }));
    expect(screen.getByRole("button", { name: "Remove English" })).toBeDisabled();
    fireEvent.change(screen.getByRole("searchbox", { name: /Add a language/ }), { target: { value: "русс" } });
    fireEvent.click(await screen.findByRole("button", { name: /Russian/ }));
    fireEvent.click(screen.getByRole("button", { name: "Move Russian up" }));
    expect(screen.getByRole("button", { name: "Remove English" })).toBeEnabled();
  });

  it("adds a language found by its name, opening it filled in rather than saving it at once", async () => {
    editor();
    fireEvent.click(screen.getByRole("button", { name: "Add a language…" }));
    const box = await screen.findByRole("searchbox", { name: "Find a language" });
    fireEvent.change(box, { target: { value: "span" } });
    const spanish = await screen.findByRole("button", { name: /Spanish/ });
    expect(spanish).toBeDisabled();
    expect(spanish).toHaveTextContent("Already kept");

    fireEvent.change(box, { target: { value: "fran" } });
    fireEvent.click(await screen.findByRole("button", { name: /French/ }));
    expect(await screen.findByRole("heading", { name: "French" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Flag" })).toHaveAttribute("placeholder", "🇫🇷");
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("French");
    expect(saved).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Add vocabulary" }));
    // Translated into what the owner's other vocabularies are, and defined in the language itself.
    await waitFor(() => expect(saved).toHaveBeenCalledWith(expect.objectContaining({
      language: "fr", definitionLang: "fr", glossLangs: ["en", "ru"], notesLang: "en", flag: null,
      region: null, level: null, learnerNote: null, displayName: "French", order: 2
    }), undefined));
  });

  it("finds a language by a word of either of its names, and takes a tag it does not list", () => {
    expect(search(LANGUAGES, "trad")[0].tag).toBe("zh-Hant");
    expect(search(LANGUAGES, "Espa")[0].tag).toBe("es");
    expect(search(LANGUAGES, "fr")[0].tag).toBe("fr");
    expect(search(LANGUAGES, "gsw")[0]).toEqual(expect.objectContaining({ tag: "gsw", name: "Swiss German" }));
    expect(search(LANGUAGES, "xx-nothing")).toEqual([]);
  });

  it("names the window's page after the language while it is being added", async () => {
    editor();
    fireEvent.click(screen.getByRole("button", { name: "Add a language…" }));
    fireEvent.change(await screen.findByRole("searchbox"), { target: { value: "russ" } });
    const list = (await screen.findByRole("button", { name: /Russian/ })).closest("section")!;
    expect(within(list).getAllByRole("button")).toHaveLength(1);
  });
});
