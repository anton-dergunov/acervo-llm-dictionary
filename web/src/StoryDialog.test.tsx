/**
 * Make a story: the owner's own note to the writer travels with the request, trimmed, and only when
 * something was written in it; the words are the ones shown; and the kinds and the styles are tiles,
 * the styles a kind suggests first.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type Job, type StoryTypes } from "./api";
import type { Story } from "./domain";
import StoryDialog from "./StoryDialog";
import { selectedWords } from "./selectors";
import { testGraph } from "./testGraph";

const TYPES = {
  types: [
    { id: "funny", label: "Funny", emoji: "😂", styles: ["comic-book"] },
    { id: "mystery", label: "Mystery", emoji: "🕵️", styles: ["film-noir", "watercolour-storybook"] }
  ],
  styles: [{ id: "comic-book", label: "Comic book" }, { id: "watercolour-storybook", label: "Watercolour" },
    { id: "film-noir", label: "Film noir" }],
  minWords: 1, maxWords: 8, minParts: 2, maxParts: 6, defaultParts: 4
} as unknown as StoryTypes;

function open() {
  render(<StoryDialog
    graph={testGraph()} query={{ language: "es", topic: "all", query: "", sort: "recent" }}
    deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
    onNotify={() => undefined}
  />);
}

let made: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.spyOn(backendSession, "storyTypes").mockResolvedValue(TYPES);
  made = vi.spyOn(backendSession, "makeStory").mockResolvedValue(
    { story: { id: "storynew0000001" } as Story, job: {} as Job });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });

describe("the owner's guidance", () => {
  it("is sent, trimmed, when something is written in it", async () => {
    open();
    const box = await screen.findByRole("textbox", { name: /anything else/i });
    fireEvent.change(box, { target: { value: "  Tell it from the dog’s side.  " } });
    const make = screen.getByRole("button", { name: /^Make the story/ });
    await waitFor(() => expect(make).toBeEnabled());
    fireEvent.click(make);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0]).toMatchObject({ guidance: "Tell it from the dog’s side." });
  });

  it("is left out of the request when the box is empty", async () => {
    open();
    const make = await screen.findByRole("button", { name: /^Make the story/ });
    await waitFor(() => expect(make).toBeEnabled());
    fireEvent.click(make);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0]).not.toHaveProperty("guidance");
  });

  it("stops where the server would refuse", async () => {
    open();
    const box = await screen.findByRole("textbox", { name: /anything else/i });
    expect(box).toHaveAttribute("maxLength", "1000");
  });
});

describe("the words", () => {
  it("draws from the words a story can use, not only the ones a loop can", async () => {
    // The Inbox holds one word, espolvorear, which has no single term to say: a loop can use none of
    // it, a story can. Drawing from a loop's words sent a story no words at all.
    render(<StoryDialog
      graph={testGraph()} query={{ language: "es", topic: "inbox", query: "", sort: "recent" }}
      deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
      onNotify={() => undefined}
    />);
    await waitFor(() => expect(screen.getByRole("button", { name: /^Make the story/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^Make the story/ }));
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0].lexemeIds).toEqual(["lexemeespolv001"]);
  });

  it("sends the selection as chosen when opened from it", async () => {
    const graph = testGraph();
    render(<StoryDialog
      graph={graph} query={{ language: "es", topic: "all", query: "", sort: "recent" }}
      selection={selectedWords(graph, "es", ["lexemeespolv001", "lexemepicar0001"])} from="selection"
      deviceId="device000000001" onClose={() => undefined} onMade={() => undefined}
      onNotify={() => undefined}
    />);
    const go = await screen.findByRole("button", { name: "Make the story · 2 words" });
    await waitFor(() => expect(go).toBeEnabled());
    fireEvent.click(go);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0].lexemeIds).toEqual(["lexemeespolv001", "lexemepicar0001"]);
  });
});

describe("the kind and the pictures", () => {
  it("counts the words as segments, three by default, and sends the kind and style chosen", async () => {
    open();
    const make = await screen.findByRole("button", { name: /^Make the story/ });
    await waitFor(() => expect(make).toBeEnabled());
    // The fixture's scope has two words a story can use, so three cannot be asked for.
    const counts = within(screen.getByRole("radiogroup", { name: "How many words" })).getAllByRole("radio");
    expect(counts.map((one) => one.textContent)).toEqual(["1", "2"]);
    expect(counts[1]).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "Mystery" }));
    fireEvent.click(make);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0]).toMatchObject({ typeId: "mystery" });
    expect(made.mock.calls[0][0]).not.toHaveProperty("styleId");
  });

  it("puts the styles a kind suggests first, in its order", async () => {
    open();
    fireEvent.click(await screen.findByRole("radio", { name: "Mystery" }));
    const styles = within(screen.getByRole("radiogroup", { name: "Pictures" })).getAllByRole("radio")
      .map((one) => one.querySelector(".choice-name")?.textContent);
    expect(styles).toEqual(["To suit the story", "Film noir", "Watercolour", "Comic book"]);
  });

  it("shows every style in a grid, and choosing one returns with it chosen", async () => {
    open();
    fireEvent.click(await screen.findByRole("button", { name: "All: Pictures" }));
    expect(screen.getByRole("heading", { name: "Pictures" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Film noir" }));
    expect(screen.getByRole("heading", { name: "Make a story" })).toBeInTheDocument();
    const make = screen.getByRole("button", { name: /^Make the story/ });
    await waitFor(() => expect(make).toBeEnabled());
    fireEvent.click(make);
    await waitFor(() => expect(made).toHaveBeenCalled());
    expect(made.mock.calls[0][0]).toMatchObject({ styleId: "film-noir" });
  });
});
