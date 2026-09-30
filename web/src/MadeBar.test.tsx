/**
 * The phone's foot bar, once a loop has played: it can be closed, and closing it stops the loop and
 * gives the bar back to the ways in — without deleting anything.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Loop, VocabularyGraph } from "./domain";
import * as playerModule from "./loops";
import MadeBar from "./MadeBar";

const loop: Loop = {
  id: "loop00000000001", language: "es", styleId: "gentle-game", seed: 104740,
  engineVersion: "1.4.0", bedFingerprint: "f35282aaf3c40245", format: "classic", switches: {}, fallbackFrom: null,
  audioRef: "loops/es/loop00000000001-6ad2f019.mp3", audioMime: "audio/mpeg",
  durationSeconds: 90, position: 1,
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1
};

const graph: VocabularyGraph = {
  vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [],
  imagePrompts: [], pronunciations: [], studyStates: [], loops: [loop], loopItems: [], loopCues: [],
  stories: [], storyParts: [], storyWords: [], beds: []
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("the phone's now-playing bar", () => {
  it("closes: the loop stops, and the bar is the way in again", () => {
    let loopId: string | null = loop.id;
    vi.spyOn(playerModule, "usePlayback").mockImplementation(() => ({
      loopId, at: 12, duration: 90, playing: false, loading: false, failed: null
    }));
    const stop = vi.spyOn(playerModule, "stop").mockImplementation(() => { loopId = null; });
    const bar = () => <MadeBar graph={graph} language="es" chip={false}
      onLoops={vi.fn()} onStories={vi.fn()} onMap={vi.fn()} />;
    const { rerender } = render(bar());

    expect(screen.queryByRole("button", { name: /Stories/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Stop and close" }));
    expect(stop).toHaveBeenCalledTimes(1);

    rerender(bar());
    expect(screen.queryByRole("button", { name: "Stop and close" })).toBeNull();
    expect(screen.getByRole("button", { name: /^Loops/ })).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: /Stories/ })).toBeInTheDocument();
  });

  it("is not offered on the desktop chip, whose place is still being designed", () => {
    vi.spyOn(playerModule, "usePlayback").mockReturnValue({
      loopId: loop.id, at: 12, duration: 90, playing: true, loading: false, failed: null
    });
    render(<MadeBar graph={graph} language="es" chip onLoops={vi.fn()} onStories={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Stop and close" })).toBeNull();
  });
});
