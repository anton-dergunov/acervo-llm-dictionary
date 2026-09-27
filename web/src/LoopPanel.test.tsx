/**
 * Settings ▸ Loops: the three kinds of setting on one page, and which is which.
 *
 * The voices are the owner's and go to the server, stored beside the other two pronunciation uses —
 * the same record, chosen here because what they cost and what they do to a track are loop facts. Keeping a track is this device's and never leaves it. What the generator can do is the
 * deployment's and is read, not set.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type LoopSchema, type PronunciationSettings } from "./api";
import LoopPanel from "./LoopPanel";
import { replaceStoreForTests } from "./loops";
import { MemoryMediaStore } from "./mediaStore";

const GEMINI = {
  provider: "google-tts", providerLabel: "Google Cloud Text-to-Speech", model: "gemini-3.1-flash-tts-preview",
  available: true, style: "instruction" as const, voices: { es: ["Kore", "Charon"], en: ["Kore", "Charon"] }
};

const SCHEMA: LoopSchema = {
  apiVersion: "2.0.0", engineVersion: "0.7.0", maxItems: 24,
  formats: [], writerAvailable: true, mixesLanguages: true, productionBundle: true,
  families: [{ id: "gentle-game", label: "Gentle game", description: "Quick, cheerful arpeggios." }]
};

function settings(loops: "plain" | "expressive" = "expressive"): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false, stories: true },
    delivery: { words: "plain", examples: "expressive", loops, stories: "expressive" },
    voices: {}, guideVoices: {}, chosen: false, languages: ["es"], guideLanguages: ["en"],
    orders: { plain: [], expressive: [GEMINI] }
  };
}

async function panel(stored = settings()) {
  replaceStoreForTests(new MemoryMediaStore());
  vi.spyOn(backendSession, "loopSchema").mockResolvedValue(SCHEMA);
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(stored);
  const saved = vi.spyOn(backendSession, "savePronunciationSettings")
    .mockImplementation(async (changes) => ({
      ...stored,
      pregenerate: { ...stored.pregenerate, ...changes.pregenerate },
      delivery: { ...stored.delivery, ...changes.delivery },
      voices: changes.voices ?? stored.voices,
      guideVoices: changes.guideVoices ?? stored.guideVoices,
      chosen: true
    }));
  render(<LoopPanel onNotify={() => undefined} />);
  await screen.findByRole("heading", { name: "Loops" });
  return saved;
}

afterEach(() => vi.restoreAllMocks());

describe("Settings ▸ Loops", () => {
  it("chooses who says the guide lines, per model, in the language the translations are in", async () => {
    const saved = await panel();
    const guide = await screen.findByRole("combobox", { name: "English" });
    expect(guide).toHaveValue("");
    expect(screen.getByRole("option", { name: "The same voice" })).toBeInTheDocument();
    fireEvent.change(guide, { target: { value: "Charon" } });
    await waitFor(() => expect(saved).toHaveBeenCalledWith({
      guideVoices: { "google-tts": { "gemini-3.1-flash-tts-preview": { en: "Charon" } } }
    }));
  });

  it("offers only the models that read loops", async () => {
    await panel(settings("plain"));
    await screen.findByRole("radio", { name: /clear, even voice/ });
    expect(screen.queryByRole("combobox", { name: "English" })).toBeNull();
    expect(screen.getByText(/No model that reads loops has voices/)).toBeInTheDocument();
  });

  it("chooses the voice that speaks a loop, and stores it where the other two uses live", async () => {
    const saved = await panel();
    const directed = await screen.findByRole("radio", { name: /takes a direction/ });
    expect(directed).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: /clear, even voice/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ delivery: { loops: "plain" } }));
  });

  it("says what each order costs, because the two are not the same price", async () => {
    await panel();
    expect(await screen.findByText(/Three calls a line/)).toBeInTheDocument();
    expect(screen.getByText(/A third of the calls/)).toBeInTheDocument();
  });

  it("reads what the generator can do rather than offering to change it", async () => {
    await panel();
    expect(await screen.findByText(/Engine 0.7.0/)).toBeInTheDocument();
    expect(screen.getByText(/sample pack is installed/)).toBeInTheDocument();
  });
});
