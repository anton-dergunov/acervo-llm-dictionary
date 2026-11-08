/**
 * The make dialog for a loop. Its words: drawn and shown before they are sent, the words in no loop
 * yet first, swapped one at a time, or the selection exactly as shown. Its kinds: three tiles, the
 * drill's variants and each kind's switches under Options, what a kind needs said before it is
 * chosen, and the last one made on this device. Its music: one Surprise me, the styles as tiles, a
 * kept bed asked for by the pair that replays it, and every choice in a grid.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type LoopSchema } from "./api";
import type { VocabularyGraph } from "./domain";
import LoopDialog from "./LoopDialog";
import { resetLoopSchemaForTests } from "./LoopMusic";
import { MemoryMediaStore } from "./mediaStore";
import { replaceMusicStoreForTests } from "./music";
import { replaceStoreForTests as resetSpeechForTests } from "./pronunciation";
import { selectedWords } from "./selectors";
import { testGraph } from "./testGraph";
import { resetRarityForTests } from "./WordPicker";

const SCHEMA: LoopSchema = {
  apiVersion: "2.0.0", engineVersion: "0.7.0", maxItems: 24,
  formats: [
    { id: "classic", label: "Classic drill", description: "Word, gap, answer.", switches: {}, requires: [], fallback: null, barsPerItem: 8 },
    { id: "echo", label: "Say it back", description: "Hear it, say it, hear it again.", switches: {}, requires: [], fallback: null, barsPerItem: 8 },
    { id: "radio-lesson", label: "Radio lesson", description: "Examples and remarks between the words.",
      switches: {
        repetitions: { label: "Times each word is said", default: "3", choices: ["2", "3", "4"] },
        remarks: { label: "Remarks about words", default: true }
      },
      requires: ["writer", "multilingual_voice"], fallback: "classic", barsPerItem: 8 },
    { id: "story", label: "Story", description: "A short story told between the words.", switches: {},
      requires: ["writer"], fallback: null, barsPerItem: 8 },
    { id: "chant", label: "Chant", description: "Something the generator added later.", switches: {},
      requires: [], fallback: null, barsPerItem: 8 }
  ],
  writerAvailable: true, mixesLanguages: true,
  productionBundle: true,
  families: [
    { id: "sunlit-acoustic", label: "Sunlit acoustic", description: "Guitar, harp or plucked strings.", sample: "k1/sunlit-acoustic-1a2b3c4d.mp3" },
    { id: "meditative", label: "Meditative", description: "Slow and spacious.", sample: null }
  ]
};

const query = { language: "es", topic: "all" as const, query: "", sort: "recent" as const };

function open(graph: VocabularyGraph = testGraph(), extra: Partial<Parameters<typeof LoopDialog>[0]> = {}) {
  render(<LoopDialog
    graph={graph} query={query}
    deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
    onNotify={() => undefined} {...extra}
  />);
  return graph;
}

/** The fixture with `count` more words a loop can say. */
function wider(count: number): VocabularyGraph {
  const graph = testGraph();
  const template = graph.lexemes.find((one) => one.id === "lexemebalsa0001")!;
  for (let index = 0; index < count; index += 1) {
    graph.lexemes.push({ ...template, id: `lexemeextra${String(index).padStart(4, "0")}`, headword: `palabra${index}`, lemma: `palabra${index}` });
  }
  return graph;
}

const made = () => vi.spyOn(backendSession, "makeLoop").mockResolvedValue({ loop: { id: "x" } as never, job: {} as never });
const go = () => screen.findByRole("button", { name: /^Make the loop/ });

beforeEach(() => {
  resetLoopSchemaForTests();
  replaceMusicStoreForTests(new MemoryMediaStore());
  resetSpeechForTests(new MemoryMediaStore());
  resetRarityForTests();
  vi.spyOn(backendSession, "loopSchema").mockResolvedValue(SCHEMA);
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });

describe("the words", () => {
  it("sends exactly the words it shows, and puts the next word in place of one removed", async () => {
    const make = made();
    open(wider(14));
    await screen.findByRole("radio", { name: "Drill" });
    const chips = () => screen.getAllByRole("button", { name: /^Remove / });
    expect(chips()).toHaveLength(12);
    const before = chips().map((chip) => chip.getAttribute("aria-label"));
    fireEvent.click(chips()[0]);
    const after = chips().map((chip) => chip.getAttribute("aria-label"));
    expect(after).not.toContain(before[0]);
    expect(after.slice(0, 11)).toEqual(before.slice(1));
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    const sent = make.mock.calls[0][0].lexemeIds;
    expect(sent).toHaveLength(12);
    expect(after.map((label) => label!.replace(/^Remove /, "")))
      .toEqual(sent.map((id: string) => testOrWider(id)));
  });

  it("offers other words past every word showing, from a button that says so", async () => {
    open(wider(14));
    await screen.findByRole("radio", { name: "Drill" });
    const showing = () => screen.getAllByRole("button", { name: /^Remove / }).map((chip) => chip.getAttribute("aria-label"));
    const before = showing();
    fireEvent.click(screen.getByRole("button", { name: "Other words" }));
    const after = showing();
    expect(after).toHaveLength(12);
    // Sixteen words and twelve showing: the four not shown come first, then the least passed over.
    expect(after.slice(0, 4).every((label) => !before.includes(label))).toBe(true);
  });

  it("draws the words in no loop yet before the ones that have been", async () => {
    // picar and la balsa are in the morning loop; three new words fill a draw of four first.
    open(wider(3));
    await screen.findByRole("radio", { name: "Drill" });
    const shown = screen.getAllByRole("button", { name: /^Remove / }).map((chip) => chip.textContent);
    expect(shown.slice(0, 3).every((text) => /palabra/.test(text ?? ""))).toBe(true);
    expect(screen.getByText("3 not in a loop yet, then the least used")).toBeInTheDocument();
  });

  it("says Hard needs Anki until there is something to order by", async () => {
    open({ ...testGraph(), studyStates: [] });
    fireEvent.click(await screen.findByRole("radio", { name: "Hard" }));
    expect(screen.getByText(/Needs your review history from Anki/)).toBeInTheDocument();
  });

  it("asks how rare the words are once, and says by name when the language has no list", async () => {
    const asked = vi.spyOn(backendSession, "wordRarity").mockRejectedValue(
      new AcervoApiError("There is no word-frequency list for Spanish, so its words cannot be ordered by how rare they are.", 422, "rarity_unavailable"));
    open();
    fireEvent.click(await screen.findByRole("radio", { name: "Rare" }));
    expect(await screen.findByText(/There is no word-frequency list for Spanish/)).toBeInTheDocument();
    expect(asked).toHaveBeenCalledTimes(1);
  });

  it("orders by rarity once the figures arrive, rarest first among the unused", async () => {
    vi.spyOn(backendSession, "wordRarity").mockResolvedValue({ language: "es", zipf: { lexemeextra0001: 1.1, lexemeextra0000: 3.2 } });
    const make = made();
    open(wider(2));
    fireEvent.click(await screen.findByRole("radio", { name: "Rare" }));
    expect(await screen.findByText("Words least common in everyday Spanish.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("button", { name: /^Remove / })[0]).toHaveTextContent("palabra1"));
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0].lexemeIds.slice(0, 2)).toEqual(["lexemeextra0001", "lexemeextra0000"]);
  });
});

/** A chip's headword for an id in `wider`'s graph. */
function testOrWider(id: string): string {
  return id.startsWith("lexemeextra") ? `palabra${Number(id.slice(-4))}` : id === "lexemepicar0001" ? "picar" : "la balsa";
}

describe("choosing the kind of loop", () => {
  it("offers three kinds and a tile for a format it does not know, and opens on the drill", async () => {
    const make = made();
    open();
    const kinds = within(await screen.findByRole("radiogroup", { name: "Kind of loop" })).getAllByRole("radio");
    expect(kinds.map((kind) => kind.textContent)).toEqual(["Drill", "Radio lesson", "Story", "Chant"]);
    expect(screen.getByRole("radio", { name: "Drill" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({ format: "classic", switches: {} });
  });

  it("sends the drill's variant as its own format", async () => {
    const make = made();
    open();
    await screen.findByRole("radio", { name: "Drill" });
    fireEvent.click(screen.getByRole("radio", { name: "Say it back" }));
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0].format).toBe("echo");
  });

  it("offers a kind's switches, reads them out folded, and sends what was set", async () => {
    const make = made();
    open();
    fireEvent.click(await screen.findByRole("radio", { name: "Radio lesson" }));
    expect(screen.getByText("3× · Remarks about words")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "4" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Remarks about words" }));
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({
      format: "radio-lesson", switches: { repetitions: "4", remarks: false }
    });
  });

  it("opens next time on the format last made here, with its switches as they were set", async () => {
    made();
    open();
    fireEvent.click(await screen.findByRole("radio", { name: "Radio lesson" }));
    fireEvent.click(screen.getByRole("radio", { name: "2" }));
    fireEvent.click(await go());
    await waitFor(() => expect(backendSession.makeLoop).toHaveBeenCalled());
    cleanup();
    open();
    expect(await screen.findByRole("radio", { name: "Radio lesson" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "2" })).toHaveAttribute("aria-checked", "true");
  });

  it("says before it is chosen what a kind needs, and what it becomes without it", async () => {
    vi.spyOn(backendSession, "loopSchema").mockResolvedValue({ ...SCHEMA, writerAvailable: false, mixesLanguages: false });
    open();
    const radio = await screen.findByRole("radio", { name: "Radio lesson" });
    expect(radio).toBeEnabled();
    fireEvent.click(radio);
    expect(screen.getByText(/Falls back to Classic drill here: it needs a writing model and a loop voice that can mix languages/)).toBeInTheDocument();
    // A story has nothing to become, so it cannot be asked for.
    const story = screen.getByRole("radio", { name: /^Story/ });
    expect(story).toBeDisabled();
    expect(story).toHaveTextContent("Needs a writing model");
  });
});

describe("choosing the music", () => {
  it("offers Surprise me once, chosen, and every style as a picture that says what it is", async () => {
    open();
    const music = await screen.findByRole("radiogroup", { name: "Music style" });
    await within(music).findByRole("radio", { name: "Meditative" });
    expect(within(music).getAllByRole("radio", { name: /surprise me/i })).toHaveLength(1);
    expect(within(music).getByRole("radio", { name: /surprise me/i })).toHaveAttribute("aria-checked", "true");
    expect(within(music).getByRole("radio", { name: "Meditative" })).toHaveAttribute("aria-description", "Slow and spacious.");
    // The chosen one is named and described under the row.
    expect(document.querySelector(".carousel-caption")).toHaveTextContent("Surprise meNew music, in any style");
  });

  it("opens with Surprise me in the middle of the row, and first in the grid", async () => {
    open();
    const music = await screen.findByRole("radiogroup", { name: "Music style" });
    await within(music).findByRole("radio", { name: "Meditative" });
    expect(within(music).getAllByRole("radio").map((one) => one.getAttribute("aria-label")))
      .toEqual(["Sunlit acoustic", "Surprise me", "Meditative"]);
    fireEvent.click(screen.getByRole("button", { name: "All 3: Music style" }));
    expect(within(screen.getByRole("radiogroup", { name: "Music style" })).getAllByRole("radio")[0])
      .toHaveTextContent("Surprise me");
  });

  it("steps through the styles with the arrows and the keyboard", async () => {
    open();
    const music = await screen.findByRole("radiogroup", { name: "Music style" });
    await within(music).findByRole("radio", { name: "Meditative" });
    fireEvent.click(screen.getByRole("button", { name: "Next: Music style" }));
    expect(within(music).getByRole("radio", { name: "Meditative" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("button", { name: "Next: Music style" })).toBeNull();
    fireEvent.keyDown(music, { key: "Home" });
    expect(within(music).getByRole("radio", { name: "Sunlit acoustic" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("button", { name: "Previous: Music style" })).toBeNull();
    fireEvent.keyDown(music, { key: "ArrowRight" });
    expect(within(music).getByRole("radio", { name: /surprise me/i })).toHaveAttribute("aria-checked", "true");
  });

  it("offers a kept bed as saved music, says where it came from, and asks for it by its family and its seed", async () => {
    const make = made();
    open();
    const favourites = await screen.findByRole("radiogroup", { name: "Saved music" });
    const [kept] = within(favourites).getAllByRole("radio");
    expect(kept).toHaveTextContent("Sunlit acoustic");
    expect(kept).toHaveTextContent(/^Sunlit acoustickept /);
    expect(within(screen.getByRole("radiogroup", { name: "Music style" })).queryByRole("radio", { name: /^Sunlit acoustic,/ })).toBeNull();
    fireEvent.click(kept);
    expect(kept).toHaveAttribute("aria-checked", "true");
    // No style is chosen while saved music is, and the row says so.
    expect(within(screen.getByRole("radiogroup", { name: "Music style" })).queryByRole("radio", { checked: true })).toBeNull();
    expect(document.querySelector(".carousel-caption")).toHaveTextContent("Saved music chosen above");
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({ family: "sunlit-acoustic", seed: 104740 });
  });

  it("shows the two most recent saved pieces, and every one in place of the dialog's body", async () => {
    const graph = testGraph();
    const [bed] = graph.beds;
    graph.beds = [
      { ...bed, id: "bedlatest000001", createdAt: "2026-11-02T10:00:00.000Z", seed: 1 },
      { ...bed, id: "bedmiddle000001", createdAt: "2026-10-20T10:00:00.000Z", seed: 2 },
      bed
    ];
    const make = made();
    open(graph);
    const saved = await screen.findByRole("radiogroup", { name: "Saved music" });
    expect(within(saved).getAllByRole("radio")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "All 3: Saved music" }));
    expect(screen.getByRole("heading", { name: "Saved music" })).toBeInTheDocument();
    const every = within(screen.getByRole("radiogroup", { name: "Saved music" })).getAllByRole("radio");
    expect(every).toHaveLength(3);
    fireEvent.click(every[2]);
    // Back in the dialog, the oldest piece is chosen and takes the second place, so it is in sight.
    expect(screen.getByRole("heading", { name: "Make a loop" })).toBeInTheDocument();
    const shown = within(screen.getByRole("radiogroup", { name: "Saved music" })).getAllByRole("radio");
    expect(shown).toHaveLength(2);
    expect(shown[1]).toHaveAttribute("aria-checked", "true");
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({ family: "sunlit-acoustic", seed: 104740 });
  });

  it("opens on the music last asked for on this device", async () => {
    made();
    open();
    const music = await screen.findByRole("radiogroup", { name: "Music style" });
    fireEvent.click(await within(music).findByRole("radio", { name: "Meditative" }));
    fireEvent.click(await go());
    await waitFor(() => expect(localStorage.getItem("acervo-loop-music")).toBe("style:meditative"));
    cleanup();
    open();
    const again = await screen.findByRole("radiogroup", { name: "Music style" });
    expect(await within(again).findByRole("radio", { name: "Meditative" })).toHaveAttribute("aria-checked", "true");
  });

  it("shows every style in a grid, and choosing one returns with it chosen", async () => {
    const make = made();
    open();
    fireEvent.click(await screen.findByRole("button", { name: "All 3: Music style" }));
    const grid = screen.getByRole("radiogroup", { name: "Music style" });
    expect(within(grid).getByText("Slow and spacious.")).toBeInTheDocument();
    fireEvent.click(within(grid).getByRole("radio", { name: /Meditative/ }));
    expect(screen.getByRole("heading", { name: "Make a loop" })).toBeInTheDocument();
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    const asked = make.mock.calls[0][0];
    expect(asked.family).toBe("meditative");
    expect(asked.seed).toBeUndefined();
  });
});

describe("making a loop from the selection", () => {
  function openWith(ids: string[], from: "selection" | "scope" = "selection") {
    const graph = testGraph();
    open(graph, { selection: selectedWords(graph, "es", ids), from });
  }

  it("sends exactly the selected words, in the order chosen, leaving out one a loop cannot say", async () => {
    const make = made();
    openWith(["lexemebalsa0001", "lexemeespolv001", "lexemepicar0001"]);
    expect(await screen.findByText(/Left out, no single term to say/)).toHaveTextContent("espolvorear");
    fireEvent.click(await screen.findByRole("button", { name: "Make the loop · 2 words" }));
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0].lexemeIds).toEqual(["lexemebalsa0001", "lexemepicar0001"]);
  });

  it("starts on the draw from a surface's own Make button, and can switch", async () => {
    openWith(["lexemepicar0001"], "scope");
    expect(await screen.findByRole("radio", { name: "Random" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("slider", { name: "How many words" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Selection · 1/ }));
    expect(screen.queryByRole("slider", { name: "How many words" })).toBeNull();
    expect(screen.getByRole("button", { name: "Make the loop · 1 word" })).toBeInTheDocument();
  });

  it("cannot be made from a selection a loop can use none of", async () => {
    openWith(["lexemeespolv001"]);
    expect(await screen.findByRole("button", { name: "Make the loop · 0 words" })).toBeDisabled();
  });
});

describe("hearing the music on its own", () => {
  const MP3 = () => new Blob(["ID3-music"], { type: "audio/mpeg" });
  /** Playback that goes on until something stops it, as a 24-second sample does. */
  const lasting = () => vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  const row = () => screen.getByRole("radiogroup", { name: "Music style" });

  it("puts ▶ on the middle style only, and never on Surprise me", async () => {
    open();
    await within(await screen.findByRole("radiogroup", { name: "Music style" })).findByRole("radio", { name: "Meditative" });
    expect(document.querySelectorAll(".carousel-action")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Next: Music style" }));
    const actions = document.querySelectorAll(".carousel-action");
    expect(actions).toHaveLength(1);
    expect(actions[0].closest(".carousel-item")).toHaveAttribute("data-choice", "style:meditative");
    expect(within(row()).getByRole("button", { name: "Hear Meditative" })).toBeInTheDocument();
  });

  it("plays a sample the server has by its name, and has one the server has not made yet made", async () => {
    lasting();
    const audio = vi.spyOn(backendSession, "sampleAudio").mockResolvedValue(MP3());
    const make = vi.spyOn(backendSession, "makeSample").mockResolvedValue({ family: "meditative", sample: "k1/meditative-9f8e7d6c.mp3" });
    open();
    await within(await screen.findByRole("radiogroup", { name: "Music style" })).findByRole("radio", { name: "Meditative" });
    fireEvent.keyDown(row(), { key: "Home" });
    fireEvent.click(within(row()).getByRole("button", { name: "Hear Sunlit acoustic" }));
    expect(await within(row()).findByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(audio).toHaveBeenCalledWith("k1/sunlit-acoustic-1a2b3c4d.mp3");
    expect(make).not.toHaveBeenCalled();
    fireEvent.click(within(row()).getByRole("button", { name: "Stop" }));
    fireEvent.keyDown(row(), { key: "End" });
    fireEvent.click(within(row()).getByRole("button", { name: "Hear Meditative" }));
    await waitFor(() => expect(make).toHaveBeenCalledWith("meditative"));
    await waitFor(() => expect(audio).toHaveBeenCalledWith("k1/meditative-9f8e7d6c.mp3"));
  });

  it("says why a sample could not be made, and goes back to ▶", async () => {
    const notify = vi.fn();
    vi.spyOn(backendSession, "makeSample").mockRejectedValue(new AcervoApiError("The loop generator is busy making a loop.", 503, "loops_busy"));
    open(testGraph(), { onNotify: notify });
    await within(await screen.findByRole("radiogroup", { name: "Music style" })).findByRole("radio", { name: "Meditative" });
    fireEvent.keyDown(row(), { key: "End" });
    fireEvent.click(within(row()).getByRole("button", { name: "Hear Meditative" }));
    await waitFor(() => expect(notify).toHaveBeenCalledWith("The loop generator is busy making a loop."));
    expect(within(row()).getByRole("button", { name: "Hear Meditative" })).toBeInTheDocument();
  });

  it("plays a kept bed's own music when it has some, from this device once fetched", async () => {
    lasting();
    const graph = testGraph();
    graph.beds = [{ ...graph.beds[0], audioRef: "music/bedmorning00001-0a0b0c0d.mp3", audioMime: "audio/mpeg", durationSeconds: 61 }];
    vi.spyOn(backendSession, "mediaFileUrl").mockImplementation((reference) => `https://acervo.example.com/media/${reference}`);
    vi.spyOn(backendSession, "mediaHeaders").mockReturnValue({ Authorization: "Bearer token" });
    const fetched = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => MP3() });
    vi.stubGlobal("fetch", fetched);
    open(graph);
    const saved = await screen.findByRole("radiogroup", { name: "Saved music" });
    // Fetched as the dialog opens, so ▶ does not wait on the network.
    await waitFor(() => expect(fetched).toHaveBeenCalledWith("https://acervo.example.com/media/music/bedmorning00001-0a0b0c0d.mp3", expect.anything()));
    fireEvent.click(within(saved).getByRole("button", { name: "Hear Sunlit acoustic" }));
    expect(await within(saved).findByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(fetched).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("removes a saved piece from its corner, even one whose loop is gone", async () => {
    const graph = testGraph();
    graph.loops = graph.loops.map((one) => (one.id === graph.beds[0].sourceLoopId ? { ...one, deleted: true } : one));
    const remove = vi.fn();
    open(graph, { onRemoveBed: remove });
    const saved = await screen.findByRole("radiogroup", { name: "Saved music" });
    // Nothing left to hear it by, and still a way to let it go.
    expect(within(saved).queryByRole("button", { name: /^Hear / })).toBeNull();
    fireEvent.click(within(saved).getByRole("button", { name: "Remove Sunlit acoustic from saved music" }));
    expect(remove).toHaveBeenCalledWith(expect.objectContaining({ id: "bedmorning00001" }));
  });

  it("stops a sample when saved music is chosen, and when the dialog closes", async () => {
    lasting();
    vi.spyOn(backendSession, "sampleAudio").mockResolvedValue(MP3());
    open();
    await within(await screen.findByRole("radiogroup", { name: "Music style" })).findByRole("radio", { name: "Meditative" });
    fireEvent.keyDown(row(), { key: "Home" });
    fireEvent.click(within(row()).getByRole("button", { name: "Hear Sunlit acoustic" }));
    await within(row()).findByRole("button", { name: "Stop" });
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Saved music" })).getAllByRole("radio")[0]);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Stop" })).toBeNull());
  });
});
