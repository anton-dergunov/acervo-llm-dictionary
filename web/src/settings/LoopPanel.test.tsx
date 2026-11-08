/**
 * Settings ▸ Loops: the three kinds of setting on one page, and which is which.
 *
 * The voices are the owner's and go to the server, stored beside the other two pronunciation uses —
 * the same record, chosen here because what they cost and what they do to a track are loop facts. Keeping a track is this device's and never leaves it. What the generator can do is the
 * deployment's and is read, not set.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type LoopSchema, type PronunciationSettings } from "../api";
import LoopPanel from "./LoopPanel";
import { replaceStoreForTests } from "../loops";
import { MemoryMediaStore } from "../mediaStore";
import { SubPages, reader, voice } from "./testVoices";

const KORE = voice("Kore", null, "any", { gender: "female", note: "firm" });
const CHARON = voice("Charon", null, "any", { gender: "male", note: "informative" });
const GEMINI = {
  provider: "google-tts", providerLabel: "Google Cloud Text-to-Speech", model: "gemini-3.1-flash-tts-preview",
  available: true, style: "instruction" as const, voices: { es: [KORE, CHARON], en: [KORE, CHARON] }
};

const SCHEMA: LoopSchema = {
  apiVersion: "2.0.0", engineVersion: "0.7.0", maxItems: 24,
  formats: [], writerAvailable: true, mixesLanguages: true, productionBundle: true,
  families: [{ id: "gentle-game", label: "Gentle game", description: "Quick, cheerful arpeggios.", sample: null }]
};

function settings(loops: "plain" | "expressive" = "expressive"): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false, stories: true },
    delivery: { words: "plain", examples: "expressive", loops, stories: "expressive" },
    voices: {}, guideVoices: {}, first: {}, guideFirst: {}, chosen: false, languages: ["es"], guideLanguages: ["en"],
    accents: { es: "es", en: "en" }, orders: { plain: [], expressive: [GEMINI] },
    readers: { plain: {}, expressive: { es: [reader("google-tts", GEMINI.model, KORE)] } },
    guideReaders: { plain: {}, expressive: { en: [reader("google-tts", GEMINI.model, KORE)] } }
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
      guideFirst: changes.guideFirst ?? stored.guideFirst,
      chosen: true
    }));
  render(<SubPages><LoopPanel onNotify={() => undefined} /></SubPages>);
  await screen.findByRole("radiogroup", { name: "Repetitions are" });
  return saved;
}

afterEach(() => vi.restoreAllMocks());

describe("Settings ▸ Loops", () => {
  it("chooses who says the guide lines, in the language the translations are in", async () => {
    const saved = await panel();
    const guide = await screen.findByRole("region", { name: "Guide’s voice" });
    expect(guide).toHaveTextContent("English");
    expect(guide).toHaveTextContent("Kore · Any accent");
    fireEvent.click(screen.getByRole("button", { name: /English/ }));
    fireEvent.click(await screen.findByRole("radio", { name: /Charon/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({
      guideVoices: { "google-tts": { "gemini-3.1-flash-tts-preview": { en: "Charon" } } },
      guideFirst: { expressive: { en: ["google-tts", "gemini-3.1-flash-tts-preview"] } }
    }));
  });

  it("offers a guide voice only where the order that reads loops has one", async () => {
    await panel(settings("plain"));
    await screen.findByRole("radio", { name: "Recorded once, varied" });
    expect(screen.queryByRole("region", { name: "Guide’s voice" })).toBeNull();
  });

  it("chooses the voice that speaks a loop, and stores it where the other two uses live", async () => {
    const saved = await panel();
    const directed = await screen.findByRole("radio", { name: "Read again each time" });
    expect(directed).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: "Recorded once, varied" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ delivery: { loops: "plain" } }));
  });

  it("says what each order costs, because the two are not the same price", async () => {
    await panel();
    expect(await screen.findByText(/three calls a line/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Recorded once, varied" }));
    expect(await screen.findByText(/a third of the calls/)).toBeInTheDocument();
  });

  it("reads what the generator can do rather than offering to change it", async () => {
    await panel();
    expect(await screen.findByText(/Engine 0.7.0/)).toBeInTheDocument();
    expect(screen.queryByText(/Loops cannot be made/)).toBeNull();
  });
});
