/**
 * What is playing, in each of its skins: the phone's foot bar, which can be closed — stopping it and
 * giving the bar back to the ways in, deleting nothing — and the rail's card; for a loop or a story,
 * whichever was started last.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Loop, VocabularyGraph } from "./domain";
import * as listeningModule from "./listening";
import * as playerModule from "./loops";
import * as readerModule from "./storyAudio";
import { testGraph } from "./testGraph";
import MadeBar from "./MadeBar";

const loop: Loop = {
  id: "loop00000000001", language: "es", styleId: "gentle-game", seed: 104740,
  engineVersion: "1.4.0", bedFingerprint: "f35282aaf3c40245", format: "classic", switches: {}, fallbackFrom: null,
  audioRef: "loops/es/loop00000000001-6ad2f019.mp3", audioMime: "audio/mpeg",
  durationSeconds: 90, position: 1, starred: false, archived: false,
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1
};

const graph: VocabularyGraph = {
  vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [],
  imagePrompts: [], pronunciations: [], studyStates: [], loops: [loop], loopItems: [], loopCues: [],
  stories: [], storyParts: [], storyWords: [], beds: [], plays: []
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("the phone's now-playing bar", () => {
  it("closes: the loop stops, and the bar is the way in again", () => {
    vi.spyOn(listeningModule, "useListening").mockReturnValue("loop");
    let loopId: string | null = loop.id;
    vi.spyOn(playerModule, "usePlayback").mockImplementation(() => ({
      loopId, at: 12, duration: 90, playing: false, loading: false, failed: null
    }));
    const stop = vi.spyOn(playerModule, "stop").mockImplementation(() => { loopId = null; });
    const bar = () => <MadeBar graph={graph} language="es" skin="bar"
      onLoops={vi.fn()} onStories={vi.fn()} onMap={vi.fn()} onOpenStory={vi.fn()} />;
    const { rerender } = render(bar());

    expect(screen.queryByRole("button", { name: /Stories/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Stop and close" }));
    expect(stop).toHaveBeenCalledTimes(1);

    rerender(bar());
    expect(screen.queryByRole("button", { name: "Stop and close" })).toBeNull();
    expect(screen.getByRole("button", { name: /^Loops/ })).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: /Stories/ })).toBeInTheDocument();
  });

  it("says which story is being read and which part, and opens it there", () => {
    vi.spyOn(listeningModule, "useListening").mockReturnValue("story");
    vi.spyOn(readerModule, "useStoryAudio").mockReturnValue({
      storyId: "storypicada0001", partId: "storypart000002", partIndex: 1, status: "playing", segment: 0, passages: 2, failed: null
    });
    const onOpenStory = vi.fn();
    render(<MadeBar graph={testGraph()} language="es" skin="bar"
      onLoops={vi.fn()} onStories={vi.fn()} onOpenStory={onOpenStory} />);

    expect(screen.getByText("La balsa que picaba")).toBeInTheDocument();
    expect(screen.getByText("Story · part 2 of 2")).toBeInTheDocument();
    fireEvent.click(screen.getByText("La balsa que picaba"));
    expect(onOpenStory).toHaveBeenCalledWith("storypicada0001", 1);
  });

  /* The one started last is the one shown: a paused loop does not take the bar back from a story. */
  it("shows the story when it was started after the loop", () => {
    vi.spyOn(listeningModule, "useListening").mockReturnValue("story");
    vi.spyOn(playerModule, "usePlayback").mockReturnValue({
      loopId: "loopmorning0001", at: 12, duration: 90, playing: false, loading: false, failed: null
    });
    vi.spyOn(readerModule, "useStoryAudio").mockReturnValue({
      storyId: "storypicada0001", partId: "storypart000001", partIndex: 0, status: "paused", segment: 0, passages: 2, failed: null
    });
    render(<MadeBar graph={testGraph()} language="es" skin="bar"
      onLoops={vi.fn()} onStories={vi.fn()} onOpenStory={vi.fn()} />);
    expect(screen.getByText("Story · part 1 of 2")).toBeInTheDocument();
  });

  it("draws nothing at all on the lists while nothing plays", () => {
    vi.spyOn(listeningModule, "useListening").mockReturnValue(null);
    const { container } = render(<MadeBar graph={graph} language="es" skin="bar" playerOnly
      onLoops={vi.fn()} onStories={vi.fn()} onOpenStory={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("the rail's card", () => {
  it("plays, pauses and goes on to the next loop, and has no close", () => {
    vi.spyOn(listeningModule, "useListening").mockReturnValue("loop");
    vi.spyOn(playerModule, "usePlayback").mockReturnValue({
      loopId: loop.id, at: 12, duration: 90, playing: true, loading: false, failed: null
    });
    vi.spyOn(playerModule, "hasNeighbour").mockReturnValue(true);
    const pause = vi.spyOn(playerModule, "pause").mockImplementation(() => undefined);
    const step = vi.spyOn(playerModule, "stepLoop").mockImplementation(() => undefined);
    render(<MadeBar graph={graph} language="es" skin="rail" onLoops={vi.fn()} onStories={vi.fn()} onOpenStory={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(pause).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "The next loop" }));
    expect(step).toHaveBeenCalledWith(1);
    expect(screen.queryByRole("button", { name: "Stop and close" })).toBeNull();
  });
});
