/**
 * Settings ▸ Pronunciation: the two kinds of setting on one page, and which is which.
 *
 * What is recorded, how it is delivered and which voice reads are the owner's and go to the server.
 * Keeping clips is this device's, so it never does — and switching it off forgets what was kept.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type PronunciationSettings } from "../api";
import { pronunciationCacheEnabled, setPronunciationCacheEnabled } from "../editorPreferences";
import { MemoryMediaStore } from "../mediaStore";
import PronunciationPanel, { offeredVoices } from "./PronunciationPanel";
import { replaceStoreForTests } from "../pronunciation";
import { SubPages, reader, voice } from "./testVoices";
import { repository } from "../repository";
import { testGraph } from "../testGraph";
import { offeredFirst, shortName } from "./voices";

/* Spanish heard as in Argentina: no clear voice is made for it, so a US one is nearest and Spain's is
   the language's main one; a voice that takes an instruction speaks any accent. */
const US = voice("es-US-Wavenet-A", "es-US", "near", { gender: "female" });
const SPAIN = voice("es-ES-Wavenet-F", "es-ES", "main", { gender: "female" });
const KORE = voice("Kore", null, "any", { gender: "female", note: "firm" });
const PUCK = voice("Puck", null, "any", { gender: "male", note: "upbeat" });

const WAVENET = {
  provider: "google-tts", providerLabel: "Google Cloud Text-to-Speech", model: "wavenet",
  available: true, style: "none" as const, voices: { es: [US, SPAIN] }
};
const STANDARD = { ...WAVENET, model: "standard", voices: { es: [voice("es-ES-Standard-F", "es-ES", "main")] } };
const GEMINI = { ...WAVENET, model: "gemini-3.1-flash-tts-preview", style: "instruction" as const, voices: { es: [KORE, PUCK] } };

function settings(overrides: Partial<PronunciationSettings> = {}): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false, stories: true },
    delivery: { words: "plain", examples: "expressive", loops: "expressive", stories: "expressive" },
    voices: {}, guideVoices: {}, first: {}, guideFirst: {}, chosen: false, languages: ["es"], guideLanguages: ["en"],
    accents: { es: "es-AR", en: "en" },
    orders: { plain: [WAVENET, STANDARD], expressive: [GEMINI] },
    readers: {
      plain: { es: [reader("google-tts", "wavenet", US), reader("google-tts", "standard", STANDARD.voices.es[0])] },
      expressive: { es: [reader("google-tts", GEMINI.model, KORE)] }
    },
    guideReaders: { plain: {}, expressive: {} },
    ...overrides
  };
}

async function panel(stored = settings()) {
  replaceStoreForTests(new MemoryMediaStore());
  vi.spyOn(repository, "snapshot").mockReturnValue(testGraph() as never);
  setPronunciationCacheEnabled(true);
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(stored);
  const saved = vi.spyOn(backendSession, "savePronunciationSettings")
    .mockImplementation(async (changes) => ({
      ...stored, ...changes,
      pregenerate: { ...stored.pregenerate, ...changes.pregenerate },
      delivery: { ...stored.delivery, ...changes.delivery },
      chosen: true,
    }));
  render(<SubPages><PronunciationPanel onNotify={() => undefined} /></SubPages>);
  await screen.findByRole("region", { name: "Record in advance" });
  return saved;
}

afterEach(() => { vi.restoreAllMocks(); setPronunciationCacheEnabled(true); });

describe("Settings ▸ Pronunciation", () => {
  it("stores what to record in advance on the server, where the recording happens", async () => {
    const saved = await panel();
    fireEvent.click(await screen.findByRole("switch", { name: /The word itself/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ pregenerate: { headword: true } }));
  });

  it("gives what it reads its own choice of order, and leaves loops to their own page", async () => {
    const saved = await panel();
    const chooser = (name: RegExp) => screen.getByRole("combobox", { name });
    expect((chooser(/Words and definitions/) as HTMLSelectElement).value).toBe("plain");
    expect((chooser(/Example sentences/) as HTMLSelectElement).value).toBe("expressive");
    // The third use is the same stored value, chosen in Settings ▸ Loops: what it costs and what it
    // does to a track are loop facts and belong beside them.
    expect(screen.queryByRole("combobox", { name: /Loops/ })).toBeNull();

    // Choosing the clear order for examples *is* switching emotion off — one mechanism, not two —
    // and it moves the whole order, so the cheap voice reads them rather than the expensive one
    // reading them without a direction.
    fireEvent.change(chooser(/Example sentences/), { target: { value: "plain" } });
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ delivery: { examples: "plain" } }));
  });

  it("names the orders for what they can do rather than for what reads them", async () => {
    await panel();
    const options = [...screen.getByRole("combobox", { name: /Example sentences/ }).querySelectorAll("option")];
    expect(options.map((option) => option.textContent))
      .toEqual(["Clear voice", "Expressive voice"]);
  });

  it("shows each language once, with its accent and the voice that reads it clearly and with feeling", async () => {
    await panel();
    const spanish = screen.getByRole("region", { name: "🇪🇸 Spanish · Argentina" });
    expect(spanish).toHaveTextContent("Clear voice");
    expect(spanish).toHaveTextContent("Wavenet-A · United States");
    expect(spanish).toHaveTextContent("1 backup");
    expect(spanish).toHaveTextContent("Expressive voice");
    expect(spanish).toHaveTextContent("Kore · Argentina");
    // Said once, under the language, rather than as a row per model.
    expect(screen.getAllByRole("region", { name: /Spanish/ })).toHaveLength(1);
    expect(spanish).toHaveTextContent("No clear voice has an accent from Argentina yet; the nearest reads.");
  });

  it("says what to do when there is nothing in the language to read yet", async () => {
    const told = vi.fn();
    replaceStoreForTests(new MemoryMediaStore());
    vi.spyOn(repository, "snapshot").mockReturnValue({ ...testGraph(), lexemes: [], senses: [], examples: [] } as never);
    vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(settings());
    const heard = vi.spyOn(backendSession, "previewVoice");
    render(<SubPages><PronunciationPanel onNotify={told} /></SubPages>);
    fireEvent.click(await screen.findByRole("button", { name: "Hear Kore" }));
    expect(told).toHaveBeenCalledWith("Add a word in Spanish to hear its voices.");
    expect(heard).not.toHaveBeenCalled();
  });

  it("plays a voice through the preview route before it is chosen", async () => {
    await panel();
    const heard = vi.spyOn(backendSession, "previewVoice").mockResolvedValue(new Blob(["x"], { type: "audio/ogg" }));
    // Something of the owner's own: the newest Spanish example in the replica, and its emotion.
    fireEvent.click(screen.getByRole("button", { name: "Hear Kore" }));
    await waitFor(() => expect(heard).toHaveBeenCalledWith(expect.objectContaining({
      order: "expressive", language: "es", provider: "google-tts", model: GEMINI.model, voice: "Kore",
      text: expect.any(String)
    })));
  });

  it("lists a language's voices by accent, nearest first, and makes the one chosen read first", async () => {
    const saved = await panel();
    fireEvent.click(screen.getByRole("button", { name: /Clear voice/ }));
    expect(await screen.findByRole("heading", { name: "Spanish · Clear voice" })).toBeInTheDocument();
    const titles = screen.getAllByRole("region").map((region) => region.getAttribute("aria-label"));
    expect(titles.slice(0, 2)).toEqual(["United States", "Spain"]);
    expect(screen.getByRole("radio", { name: /Wavenet-A · female/ })).toHaveAttribute("aria-checked", "true");

    fireEvent.click(screen.getByRole("radio", { name: /Wavenet-F · female/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({
      voices: { "google-tts": { wavenet: { es: "es-ES-Wavenet-F" } } },
      first: { plain: { es: ["google-tts", "wavenet"] } }
    }));
  });

  it("shows who reads when the chosen voice cannot, and lets each say it in a voice of its own", async () => {
    const saved = await panel();
    fireEvent.click(screen.getByRole("button", { name: /Clear voice/ }));
    const backups = await screen.findByRole("region", { name: "If it can’t answer" });
    expect(backups).toHaveTextContent("Google Cloud Text-to-Speech · standard");
    fireEvent.change(screen.getByRole("combobox", { name: /standard/ }), { target: { value: "es-ES-Standard-F" } });
    await waitFor(() => expect(saved).toHaveBeenCalledWith({
      voices: { "google-tts": { standard: { es: "es-ES-Standard-F" } } }, first: {}
    }));
  });

  it("offers the expressive voices that speak any accent, telling them which", async () => {
    await panel();
    fireEvent.click(screen.getByRole("button", { name: /Expressive voice/ }));
    const any = await screen.findByRole("region", { name: "Speaks any accent" });
    expect(any).toHaveTextContent("Kore · female · firm");
    expect(any).toHaveTextContent("Puck · male · upbeat");
    expect(screen.getByText("Told to speak as in Argentina.")).toBeInTheDocument();
  });

  it("keeps clips as a device preference, which the server is never told about", async () => {
    const saved = await panel();
    fireEvent.click(screen.getByRole("switch", { name: "Keep pronunciations" }));
    await waitFor(() => expect(pronunciationCacheEnabled()).toBe(false));
    expect(saved).not.toHaveBeenCalled();
  });

  it("still offers to forget what is kept when the server cannot be reached", async () => {
    replaceStoreForTests(new MemoryMediaStore());
    vi.spyOn(backendSession, "pronunciationSettings").mockRejectedValue(new Error("away"));
    render(<PronunciationPanel onNotify={() => undefined} />);
    expect(await screen.findByRole("button", { name: /Forget pronunciations/ })).toBeInTheDocument();
  });
});

describe("a voice's name", () => {
  it("drops a locale it repeats, whoever names voices that way, and keeps any other", () => {
    expect(shortName("es-ES-Wavenet-F")).toBe("Wavenet-F");
    expect(shortName("cmn-CN-Standard-A")).toBe("Standard-A");
    expect(shortName("Kore")).toBe("Kore");
  });
});

describe("the voice document a change sends", () => {
  it("lets go of a first voice its order no longer holds", () => {
    expect(offeredFirst({
      plain: { es: ["google-tts", "wavenet"], ru: ["gone", "model"] },
      expressive: { es: ["google-tts", "wavenet"] }
    }, settings())).toEqual({ plain: { es: ["google-tts", "wavenet"] } });
  });

  it("lets go of a voice chosen for a model no order offers any more, and keeps the rest", () => {
    const stored = {
      "google-tts": { wavenet: { es: "es-ES-Wavenet-E" }, "gemini-3.1-flash-tts-preview": { es: "Kore" } },
      // Retired from speech: the whole document would otherwise be refused on every later change.
      "gemini-free": { "gemini/gemini-3.1-flash-tts-preview": { es: "Kore" } }
    };
    expect(offeredVoices(stored, settings())).toEqual({
      "google-tts": { wavenet: { es: "es-ES-Wavenet-E" }, "gemini-3.1-flash-tts-preview": { es: "Kore" } }
    });
  });
});
