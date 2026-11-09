/**
 * New music for a loop that is already made: the make dialog's picker, opening on the loop's own
 * style, and asking for exactly what was chosen — nothing for this style again, a family for
 * another, the pair that replays a saved piece, and for Surprise me some style other than this one.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type LoopSchema } from "./api";
import type { Bed, Loop, VocabularyGraph } from "./domain";
import { resetLoopSchemaForTests } from "./LoopMusic";
import LoopMusicDialog, { newMusicFor } from "./LoopMusicDialog";
import { MemoryMediaStore } from "./mediaStore";
import { replaceMusicStoreForTests } from "./music";
import { replaceStoreForTests as resetSpeechForTests } from "./pronunciation";

const SCHEMA: LoopSchema = {
  apiVersion: "2.0.0", engineVersion: "0.7.0", maxItems: 24,
  formats: [{ id: "classic", label: "Classic drill", description: "Word, gap, answer.", switches: {}, requires: [], fallback: null, barsPerItem: 8 }],
  writerAvailable: true, mixesLanguages: true, productionBundle: true,
  families: [
    { id: "gentle-game", label: "Gentle game", description: "Quick, cheerful arpeggios.", sample: null },
    { id: "meditative", label: "Meditative", description: "Slow and spacious.", sample: null },
    { id: "organic", label: "Organic", description: "Earthy mid-tempo pulse.", sample: null }
  ]
};

const record = {
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1
};

const loop: Loop = {
  id: "loop00000000001", language: "es", styleId: "gentle-game", seed: 104740,
  engineVersion: "1.4.0", bedFingerprint: "f35282aaf3c40245", format: "classic", switches: {}, fallbackFrom: null,
  audioRef: "loops/es/loop00000000001-6ad2f019.mp3", audioMime: "audio/mpeg", durationSeconds: 90, position: 1, ...record
};

const bed = (over: Partial<Bed>): Bed => ({
  id: "bedkept00000001", styleId: "gentle-game", seed: 104740, engineVersion: "1.4.0",
  bedFingerprint: "f35282aaf3c40245", sourceLoopId: loop.id, audioRef: null, audioMime: null, durationSeconds: null,
  ...record, ...over
});

/** The bed this loop is playing, and another kept from elsewhere. */
const playing = bed({});
const other = bed({ id: "bedkept00000002", styleId: "meditative", seed: 9, sourceLoopId: "loopgone0000001" });

function graphWith(beds: Bed[]): VocabularyGraph {
  return {
    vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [],
    imagePrompts: [], pronunciations: [], studyStates: [], loops: [loop], loopItems: [], loopCues: [],
    stories: [], storyParts: [], storyWords: [], beds
  };
}

const onChoose = vi.fn();
const onClose = vi.fn();
const onRemoveBed = vi.fn();

function open(beds: Bed[] = []) {
  const graph = graphWith(beds);
  render(<LoopMusicDialog graph={graph} loop={loop} onChoose={onChoose} onClose={onClose}
    onNotify={() => undefined} onRemoveBed={onRemoveBed} />);
  return graph;
}

const make = () => fireEvent.click(screen.getByRole("button", { name: "Make new music" }));

beforeEach(() => {
  resetLoopSchemaForTests();
  replaceMusicStoreForTests(new MemoryMediaStore());
  resetSpeechForTests(new MemoryMediaStore());
  vi.spyOn(backendSession, "loopSchema").mockResolvedValue(SCHEMA);
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); onChoose.mockReset(); onClose.mockReset(); onRemoveBed.mockReset(); });

describe("new music for a loop", () => {
  it("opens on the loop's own style, and asks for new music in it with nothing at all", async () => {
    open();
    const row = await screen.findByRole("radiogroup", { name: "Music style" });
    await within(row).findByRole("radio", { name: "Gentle game" });
    expect(within(row).getByRole("radio", { checked: true })).toHaveAccessibleName("Gentle game");
    expect(screen.getByRole("heading", { name: "New music" })).toBeInTheDocument();
    make();
    expect(onChoose).toHaveBeenCalledWith({});
    expect(onClose).toHaveBeenCalled();
  });

  it("asks for another style by its family", async () => {
    open();
    fireEvent.click(await screen.findByRole("button", { name: "All 4: Music style" }));
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Music style" })).getByRole("radio", { name: /Meditative/ }));
    make();
    expect(onChoose).toHaveBeenCalledWith({ family: "meditative" });
  });

  it("offers saved music but not the piece already playing, and asks for one by its family and seed", async () => {
    open([playing, other]);
    const saved = await screen.findByRole("radiogroup", { name: "Saved music" });
    const pieces = within(saved).getAllByRole("radio");
    expect(pieces).toHaveLength(1);
    fireEvent.click(pieces[0]);
    make();
    expect(onChoose).toHaveBeenCalledWith({ family: "meditative", seed: 9 });
  });

  it("lets a saved piece go from its corner", async () => {
    open([other]);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Meditative from saved music" }));
    expect(onRemoveBed).toHaveBeenCalledWith(other);
  });

  it("asks for some other style for Surprise me, since nothing at all would mean this one", () => {
    const graph = graphWith([]);
    for (const pick of [0, 1]) {
      const music = newMusicFor(loop, SCHEMA.families, "surprise", [], graph, () => pick);
      expect(music.family).toBeDefined();
      expect(music.family).not.toBe(loop.styleId);
    }
  });
});
