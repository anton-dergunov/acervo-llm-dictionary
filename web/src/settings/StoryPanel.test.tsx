/**
 * Settings ▸ Stories: which voice reads a story, whether it is recorded when the story is made, and
 * whether its later pictures are drawn from its earlier ones.
 *
 * The first two live in the pronunciation settings and the third in the picture settings the server
 * keeps for the owner, so what is pinned here is that the panel reads each from its own place,
 * writes only what it changed, and puts things back when the server refuses.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type ImageSettings, type PronunciationSettings } from "../api";
import StoryPanel from "./StoryPanel";

function settings(overrides: Partial<PronunciationSettings> = {}): PronunciationSettings {
  return {
    pregenerate: { headword: false, definitions: false, examples: false, stories: true },
    delivery: { words: "plain", examples: "expressive", loops: "expressive", stories: "expressive" },
    voices: {}, guideVoices: {}, first: {}, guideFirst: {}, chosen: false, languages: ["es"], guideLanguages: ["en"],
    accentChoices: {}, accents: { es: "es", en: "en" }, orders: { plain: [], expressive: [] },
    readers: { plain: {}, expressive: {} }, guideReaders: { plain: {}, expressive: {} },
    ...overrides
  };
}

function pictures(overrides: Partial<ImageSettings> = {}): ImageSettings {
  return {
    drawEnabled: true, stylesOff: [], boostVariety: true, storyContinuity: "all", chosen: false,
    maxAttempts: 4, available: true,
    styles: [
      { id: "cinematic-photoreal", label: "Cinematic photograph", mono: false, photographic: true },
      { id: "folk-naive", label: "Naïve folk painting", mono: false, photographic: false }
    ],
    ...overrides
  };
}

async function panel(stored = settings(), onNotify: (message: string) => void = () => undefined,
  drawn = pictures()) {
  vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue(stored);
  vi.spyOn(backendSession, "imageSettings").mockResolvedValue(drawn);
  const saved = vi.spyOn(backendSession, "savePronunciationSettings")
    .mockImplementation(async (changes) => ({
      ...stored,
      pregenerate: { ...stored.pregenerate, ...changes.pregenerate },
      delivery: { ...stored.delivery, ...changes.delivery },
      chosen: true
    }));
  render(<StoryPanel onNotify={onNotify} />);
  await screen.findByRole("radio", { name: "Expressive" });
  return saved;
}

afterEach(() => vi.restoreAllMocks());

describe("Settings ▸ Stories", () => {
  it("offers the directed voice as what is chosen until it is changed", async () => {
    await panel();
    expect(screen.getByRole("radio", { name: "Expressive" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Clear" })).not.toBeChecked();
  });

  it("chooses the voice that reads a story, and writes only that", async () => {
    const saved = await panel();

    fireEvent.click(screen.getByRole("radio", { name: "Clear" }));

    await waitFor(() => expect(saved).toHaveBeenCalledWith({ delivery: { stories: "plain" } }));
    expect(screen.getByRole("radio", { name: "Clear" })).toBeChecked();
  });

  it("says what each voice does to a story, because they are not the same price", async () => {
    await panel();
    expect(screen.getByText(/Each passage in its own manner/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Clear" }));
    expect(await screen.findByText(/one call a part/)).toBeInTheDocument();
  });

  it("records a story when it is made unless that is switched off", async () => {
    const saved = await panel();
    const recording = screen.getByRole("switch", { name: "Record narration when a story is made" });
    expect(recording).toBeChecked();

    fireEvent.click(recording);

    await waitFor(() => expect(saved).toHaveBeenCalledWith({ pregenerate: { stories: false } }));
    expect(recording).not.toBeChecked();
  });

  it("puts the choice back and says so when the server would not keep it", async () => {
    const notified = vi.fn();
    const saved = await panel(settings(), notified);
    saved.mockRejectedValueOnce(new AcervoApiError("The server cannot be reached.", 0, "offline"));

    fireEvent.click(screen.getByRole("radio", { name: "Clear" }));

    await waitFor(() => expect(notified).toHaveBeenCalledWith("The server cannot be reached."));
    expect(screen.getByRole("radio", { name: "Expressive" })).toBeChecked();
  });
  it("draws later pictures from earlier ones in every style until told otherwise", async () => {
    await panel();
    const every = await screen.findByRole("radio", { name: "Every style" });
    expect(every).toBeChecked();
    const choices = within(screen.getByRole("radiogroup", { name: "Keep characters and places consistent" })).getAllByRole("radio");
    expect(choices[0]).toBe(every);
    vi.spyOn(backendSession, "saveImageSettings").mockImplementation(() => new Promise(() => undefined));
    fireEvent.click(screen.getByRole("radio", { name: "Drawn only" }));
    expect(await screen.findByText(/photographic styles \(Cinematic photograph\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Naïve folk painting/)).not.toBeInTheDocument();
  });

  it("stores the picture choice with the picture settings and nothing else", async () => {
    await panel();
    const saved = vi.spyOn(backendSession, "saveImageSettings")
      .mockResolvedValue(pictures({ storyContinuity: "artwork", chosen: true }));
    fireEvent.click(await screen.findByRole("radio", { name: "Drawn only" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ storyContinuity: "artwork" }));
    expect(screen.getByRole("radio", { name: "Drawn only" })).toBeChecked();
  });

  it("puts the picture choice back when the server refuses it", async () => {
    const notices: string[] = [];
    await panel(settings(), (message) => notices.push(message));
    vi.spyOn(backendSession, "saveImageSettings")
      .mockRejectedValue(new AcervoApiError("That could not be saved here.", 400, "invalid_input"));
    fireEvent.click(await screen.findByRole("radio", { name: "Off" }));
    await waitFor(() => expect(notices).toEqual(["That could not be saved here."]));
    expect(screen.getByRole("radio", { name: "Every style" })).toBeChecked();
  });
});
