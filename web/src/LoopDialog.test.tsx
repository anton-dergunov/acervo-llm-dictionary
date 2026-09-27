/**
 * The make dialog's music: one "Surprise me" rather than two names for it, the styles in words, and
 * a kept bed asked for by the pair that replays it. Its words: from the selection, exactly as shown,
 * or a draw from the scope. And its formats: what each needs, said before it is chosen, its switches,
 * and the last one made on this device.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type LoopSchema } from "./api";
import LoopDialog from "./LoopDialog";
import { resetLoopSchemaForTests } from "./LoopMusic";
import { selectedWords } from "./selectors";
import { testGraph } from "./testGraph";

const SCHEMA: LoopSchema = {
  apiVersion: "2.0.0", engineVersion: "0.7.0", maxItems: 24,
  formats: [
    { id: "classic", label: "Classic drill", description: "Word, gap, answer.", switches: {}, requires: [], fallback: null },
    { id: "radio-lesson", label: "Radio lesson", description: "Examples and remarks between the words.",
      switches: {
        repetitions: { label: "Times each word is said", default: "3", choices: ["2", "3", "4"] },
        remarks: { label: "Remarks about words", default: true }
      },
      requires: ["writer", "multilingual_voice"], fallback: "classic" },
    { id: "story", label: "Story", description: "A short story told between the words.", switches: {},
      requires: ["writer"], fallback: null }
  ],
  writerAvailable: true, mixesLanguages: true,
  productionBundle: true,
  families: [
    { id: "sunlit-acoustic", label: "Sunlit acoustic", description: "Guitar, harp or plucked strings." },
    { id: "meditative", label: "Meditative", description: "Slow and spacious." }
  ]
};

function open() {
  const graph = testGraph();
  render(<LoopDialog
    graph={graph} query={{ language: "es", topic: "all", query: "", sort: "recent" }}
    deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
    onNotify={() => undefined}
  />);
  return graph;
}

beforeEach(() => {
  resetLoopSchemaForTests();
  vi.spyOn(backendSession, "loopSchema").mockResolvedValue(SCHEMA);
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });

describe("choosing the kind of loop", () => {
  const made = () => vi.spyOn(backendSession, "makeLoop").mockResolvedValue({ loop: { id: "x" } as never, job: {} as never });

  it("opens on the drill, and asks for it with no switches", async () => {
    const make = made();
    open();
    expect(await screen.findByRole("radio", { name: /classic drill/i })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Make the loop" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({ format: "classic", switches: {} });
  });

  it("offers a format's switches, and sends what was set", async () => {
    const make = made();
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /radio lesson/i }));
    fireEvent.click(screen.getByRole("radio", { name: "4" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Remarks about words" }));
    fireEvent.click(screen.getByRole("button", { name: "Make the loop" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({
      format: "radio-lesson", switches: { repetitions: "4", remarks: false }
    });
  });

  it("opens next time on the format last made here, with its switches as they were set", async () => {
    made();
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /radio lesson/i }));
    fireEvent.click(screen.getByRole("radio", { name: "2" }));
    fireEvent.click(screen.getByRole("button", { name: "Make the loop" }));
    await waitFor(() => expect(backendSession.makeLoop).toHaveBeenCalled());
    cleanup();
    open();
    expect(await screen.findByRole("radio", { name: /radio lesson/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: "2" })).toHaveAttribute("aria-checked", "true");
  });

  it("says before it is chosen what a format needs, and what it becomes without it", async () => {
    vi.spyOn(backendSession, "loopSchema").mockResolvedValue({ ...SCHEMA, writerAvailable: false, mixesLanguages: false });
    open();
    const radio = await screen.findByRole("radio", { name: /radio lesson/i });
    expect(radio).toBeEnabled();
    expect(radio.closest("label")).toHaveTextContent(
      "Falls back to Classic drill here: it needs a writing model and a loop voice that can mix languages"
    );
    // A story has nothing to become, so it cannot be asked for.
    const story = screen.getByRole("radio", { name: /story/i });
    expect(story).toBeDisabled();
    expect(story.closest("label")).toHaveTextContent("Needs a writing model — set one up in Settings ▸ Providers.");
  });
});

describe("choosing the music", () => {
  it("offers Surprise me once, and every style with its description", async () => {
    open();
    await screen.findByRole("radio", { name: /meditative/i });
    expect(screen.getAllByRole("radio", { name: /surprise me/i })).toHaveLength(1);
    expect(screen.queryByRole("radio", { name: /^auto/i })).toBeNull();
    expect(screen.getByRole("radio", { name: /meditative/i })).toHaveTextContent("Slow and spacious.");
    expect(screen.getByRole("radio", { name: /surprise me/i })).toHaveAttribute("aria-checked", "true");
  });

  it("lists a kept bed first, and asks for it by its family and its seed", async () => {
    const make = vi.spyOn(backendSession, "makeLoop").mockResolvedValue({ loop: { id: "x" } as never, job: {} as never });
    open();
    const kept = await screen.findByRole("radio", { name: /sunlit acoustic.*kept/i });
    fireEvent.click(kept);
    fireEvent.click(screen.getByRole("button", { name: "Make the loop" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({ family: "sunlit-acoustic", seed: 104740 });
  });

  it("asks for a style by its family alone, and for nothing when surprised", async () => {
    const make = vi.spyOn(backendSession, "makeLoop").mockResolvedValue({ loop: { id: "x" } as never, job: {} as never });
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /meditative/i }));
    fireEvent.click(screen.getByRole("button", { name: "Make the loop" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    const asked = make.mock.calls[0][0];
    expect(asked.family).toBe("meditative");
    expect(asked.seed).toBeUndefined();
  });
});

describe("making a loop from the selection", () => {
  function openWith(ids: string[], from: "selection" | "scope" = "selection") {
    const graph = testGraph();
    render(<LoopDialog
      graph={graph} query={{ language: "es", topic: "all", query: "", sort: "recent" }}
      selection={selectedWords(graph, "es", ids)} from={from}
      deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
      onNotify={() => undefined}
    />);
  }

  it("sends exactly the selected words, in the order chosen, leaving out one a loop cannot say", async () => {
    const make = vi.spyOn(backendSession, "makeLoop").mockResolvedValue({ loop: { id: "x" } as never, job: {} as never });
    openWith(["lexemebalsa0001", "lexemeespolv001", "lexemepicar0001"]);
    expect(await screen.findByText(/Left out, no single term to say/)).toHaveTextContent("espolvorear");
    fireEvent.click(await screen.findByRole("button", { name: "Make the loop from 2 words" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0].lexemeIds).toEqual(["lexemebalsa0001", "lexemepicar0001"]);
  });

  it("starts on the random draw from a surface's own Make button, and can switch", async () => {
    openWith(["lexemepicar0001"], "scope");
    expect(await screen.findByRole("radio", { name: /Random from Spanish/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("How many words")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Your selection · 1/ }));
    expect(screen.queryByText("How many words")).toBeNull();
    expect(screen.getByRole("button", { name: "Make the loop from 1 word" })).toBeInTheDocument();
  });

  it("cannot be made from a selection a loop can use none of", async () => {
    openWith(["lexemeespolv001"]);
    expect(await screen.findByRole("button", { name: "Make the loop from 0 words" })).toBeDisabled();
  });
});
