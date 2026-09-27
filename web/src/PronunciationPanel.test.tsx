/**
 * Settings ▸ Pronunciation: the two kinds of setting on one page, and which is which.
 *
 * What is recorded, how it is delivered and which voice reads are the owner's and go to the server.
 * Keeping clips is this device's, so it never does — and switching it off forgets what was kept.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type PronunciationSettings } from "./api";
import { pronunciationCacheEnabled, setPronunciationCacheEnabled } from "./editorPreferences";
import { MemoryMediaStore } from "./mediaStore";
import PronunciationPanel from "./PronunciationPanel";
import { replaceStoreForTests } from "./pronunciation";

const WAVENET = {
  provider: "google-tts", providerLabel: "Google Cloud Text-to-Speech", model: "wavenet",
  available: true, style: "none" as const, voices: { es: ["es-ES-Wavenet-F", "es-ES-Wavenet-E"] }
};

function settings(overrides: Partial<PronunciationSettings> = {}): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false, stories: true },
    delivery: { words: "plain", examples: "expressive", loops: "expressive", stories: "expressive" },
    voices: {}, guideVoices: {}, chosen: false, languages: ["es"], guideLanguages: ["en"],
    orders: { plain: [WAVENET], expressive: [{ ...WAVENET, model: "gemini-3.1-flash-tts-preview", style: "instruction", voices: { es: ["Kore"] } }] },
    ...overrides
  };
}

async function panel(stored = settings()) {
  replaceStoreForTests(new MemoryMediaStore());
  setPronunciationCacheEnabled(true);
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(stored);
  const saved = vi.spyOn(backendSession, "savePronunciationSettings")
    .mockImplementation(async (changes) => ({
      ...stored, ...changes,
      pregenerate: { ...stored.pregenerate, ...changes.pregenerate },
      delivery: { ...stored.delivery, ...changes.delivery },
      chosen: true,
    }));
  render(<PronunciationPanel onNotify={() => undefined} />);
  await screen.findByRole("heading", { name: "Pronunciation" });
  return saved;
}

afterEach(() => { vi.restoreAllMocks(); setPronunciationCacheEnabled(true); });

describe("Settings ▸ Pronunciation", () => {
  it("stores what to record in advance on the server, where the recording happens", async () => {
    const saved = await panel();
    fireEvent.click(await screen.findByRole("checkbox", { name: /The word itself/ }));
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
      .toEqual(["A clear, even voice", "A voice that takes a direction"]);
  });

  it("offers each model's voices for each vocabulary language, the default first", async () => {
    await panel();
    const select = screen.getAllByRole("combobox", { name: /Spanish/ })[0];
    expect([...select.querySelectorAll("option")].map((option) => option.textContent))
      .toEqual(["Default · es-ES-Wavenet-F", "es-ES-Wavenet-F", "es-ES-Wavenet-E"]);
  });

  it("stores a chosen voice under its model and language", async () => {
    const saved = await panel();
    fireEvent.change(screen.getAllByRole("combobox", { name: /Spanish/ })[0], { target: { value: "es-ES-Wavenet-E" } });
    await waitFor(() => expect(saved).toHaveBeenCalledWith({
      voices: { "google-tts": { wavenet: { es: "es-ES-Wavenet-E" } } }
    }));
  });

  it("keeps clips as a device preference, which the server is never told about", async () => {
    const saved = await panel();
    fireEvent.click(screen.getByRole("checkbox", { name: /Keep pronunciations on this device/ }));
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
