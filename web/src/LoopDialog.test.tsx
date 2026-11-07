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
import { selectedWords } from "./selectors";
import { testGraph } from "./testGraph";
import { resetRarityForTests } from "./WordPicker";

const SCHEMA: LoopSchema = {
  apiVersion: "2.0.0", engineVersion: "0.7.0", maxItems: 24,
  formats: [
    { id: "classic", label: "Classic drill", description: "Word, gap, answer.", switches: {}, requires: [], fallback: null },
    { id: "echo", label: "Say it back", description: "Hear it, say it, hear it again.", switches: {}, requires: [], fallback: null },
    { id: "radio-lesson", label: "Radio lesson", description: "Examples and remarks between the words.",
      switches: {
        repetitions: { label: "Times each word is said", default: "3", choices: ["2", "3", "4"] },
        remarks: { label: "Remarks about words", default: true }
      },
      requires: ["writer", "multilingual_voice"], fallback: "classic" },
    { id: "story", label: "Story", description: "A short story told between the words.", switches: {},
      requires: ["writer"], fallback: null },
    { id: "chant", label: "Chant", description: "Something the generator added later.", switches: {},
      requires: [], fallback: null }
  ],
  writerAvailable: true, mixesLanguages: true,
  productionBundle: true,
  families: [
    { id: "sunlit-acoustic", label: "Sunlit acoustic", description: "Guitar, harp or plucked strings." },
    { id: "meditative", label: "Meditative", description: "Slow and spacious." }
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

  it("draws again past every word showing, from a button that says so", async () => {
    open(wider(14));
    await screen.findByRole("radio", { name: "Drill" });
    const showing = () => screen.getAllByRole("button", { name: /^Remove / }).map((chip) => chip.getAttribute("aria-label"));
    const before = showing();
    fireEvent.click(screen.getByRole("button", { name: "Draw again" }));
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
  it("offers Surprise me once, chosen, and every style as a tile that says what it is", async () => {
    open();
    const music = await screen.findByRole("radiogroup", { name: "Music" });
    await within(music).findByRole("radio", { name: "Meditative" });
    expect(within(music).getAllByRole("radio", { name: /surprise me/i })).toHaveLength(1);
    expect(within(music).getByRole("radio", { name: /surprise me/i })).toHaveAttribute("aria-checked", "true");
    expect(within(music).getByRole("radio", { name: "Meditative" })).toHaveAttribute("title", "Slow and spacious.");
  });

  it("offers a kept bed in a row of its own, says where it came from, and asks for it by its family and its seed", async () => {
    const make = made();
    open();
    const favourites = await screen.findByRole("radiogroup", { name: "Favourite music" });
    const [kept] = within(favourites).getAllByRole("radio");
    expect(kept).toHaveTextContent("Sunlit acoustic");
    expect(kept).toHaveTextContent(/^Sunlit acoustickept /);
    expect(within(screen.getByRole("radiogroup", { name: "Music" })).queryByRole("radio", { name: /^Sunlit acoustic,/ })).toBeNull();
    fireEvent.click(kept);
    expect(kept).toHaveAttribute("aria-checked", "true");
    fireEvent.click(await go());
    await waitFor(() => expect(make).toHaveBeenCalled());
    expect(make.mock.calls[0][0]).toMatchObject({ family: "sunlit-acoustic", seed: 104740 });
  });

  it("opens on the music last asked for on this device", async () => {
    made();
    open();
    const music = await screen.findByRole("radiogroup", { name: "Music" });
    fireEvent.click(await within(music).findByRole("radio", { name: "Meditative" }));
    fireEvent.click(await go());
    await waitFor(() => expect(localStorage.getItem("acervo-loop-music")).toBe("style:meditative"));
    cleanup();
    open();
    const again = await screen.findByRole("radiogroup", { name: "Music" });
    expect(await within(again).findByRole("radio", { name: "Meditative" })).toHaveAttribute("aria-checked", "true");
  });

  it("shows every style in a grid, and choosing one returns with it chosen", async () => {
    const make = made();
    open();
    fireEvent.click(await screen.findByRole("button", { name: "All: Music" }));
    const grid = screen.getByRole("radiogroup", { name: "Music" });
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
