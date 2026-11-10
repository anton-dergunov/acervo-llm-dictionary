/**
 * The loops list, and the two ways out of it.
 *
 * A pointer right-clicks a row; a finger pushes it aside and finds Delete behind it, which is CSS
 * and therefore invisible to jsdom — so what is pinned here is that the button exists on every row
 * and that both routes call the same thing. The row a loop was never made for matters most: that is
 * the one you most want rid of, and while it was a `disabled` button it answered no gesture at all.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Loop, LoopItem, VocabularyGraph } from "./domain";
import LoopView from "./LoopView";

const stamp = {
  ownerId: "owner0000000001", deleted: false, createdAt: "2026-09-16T00:00:00.000Z",
  editedAt: "2026-09-16T00:00:00.000Z", editedBy: "device000000001", revision: 1
};

const loop = (over: Partial<Loop>): Loop => ({
  id: "loop00000000001", language: "es", styleId: "gentle-game", seed: 104740,
  engineVersion: "1.4.0", bedFingerprint: "f35282aaf3c40245", format: "classic", switches: {}, fallbackFrom: null,
  audioRef: "loops/es/loop00000000001-6ad2f019.mp3", audioMime: "audio/mpeg",
  durationSeconds: 90, position: 1, starred: false, archived: false, ...stamp, ...over
});

const item = (loopId: string): LoopItem => ({
  id: `loopitem${loopId.slice(-5)}`, loopId, lexemeId: "lexeme000000001", position: 0,
  sourceText: "asco", targetText: "disgust", emotion: "repulsed",
  startSeconds: 0, sourceRevealSeconds: 0, targetRevealSeconds: 8, endSeconds: 20, ...stamp
});

function view(loops: Loop[], query = "", onMark: (id: string, marks: object) => void = () => undefined) {
  const graph: VocabularyGraph = {
    vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [],
    imagePrompts: [], pronunciations: [], studyStates: [],
    loops, loopItems: loops.map((one) => item(one.id)), loopCues: [],
    stories: [], storyParts: [], storyWords: [], beds: [], plays: []
  };
  const onDelete = vi.fn();
  render(<LoopView
    graph={graph} language="es" languageName="Spanish" query={query} onClose={() => undefined} onMark={onMark}
    onDelete={onDelete} onChooseMusic={() => undefined} onToggleKeep={() => undefined}
  />);
  return onDelete;
}

afterEach(() => vi.restoreAllMocks());

describe("the loops list", () => {
  /* Star, Archive and Delete on every row, and each says what it would do to this one. */
  it("stars and archives from the row, and offers to take either back", () => {
    const onMark = vi.fn();
    view([loop({ starred: true })], "", onMark);
    fireEvent.click(screen.getByRole("button", { name: "Unstar" }));
    expect(onMark).toHaveBeenCalledWith("loop00000000001", { starred: false });
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    expect(onMark).toHaveBeenCalledWith("loop00000000001", { archived: true });
    expect(screen.getByRole("img", { name: "Starred" })).toBeInTheDocument();
  });

  /* Archived rows fold away at the foot, as set-aside words do, and a search opens the fold. */
  it("folds the archived loops under a rule at the foot", () => {
    view([loop({}), loop({ id: "loop00000000002", position: 2, archived: true })]);
    const fold = screen.getByRole("button", { name: /Archived · 1/ });
    expect(fold).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelectorAll(".loop-row")).toHaveLength(1);
    fireEvent.click(fold);
    expect(document.querySelectorAll(".loop-row.archived")).toHaveLength(1);
    expect(screen.getByText("1 in Spanish · 1 archived")).toBeInTheDocument();
  });

  /* The badge says what kind of loop a row is, as the make dialog's tile does, until it is loaded. */
  it("marks each loop with its kind", () => {
    view([loop({}), loop({ id: "loop00000000002", position: 2, format: "radio-lesson" })]);
    const kinds = [...document.querySelectorAll(".loop-go.kind")].map((badge) => badge.getAttribute("title"));
    expect(kinds).toHaveLength(2);
    expect(new Set(kinds).size).toBe(2);
  });

  it("keeps only the loops whose words match the search, and marks the letters that did", () => {
    view([loop({})], "disg");
    expect(screen.getByText("1 loop with “disg”")).toBeInTheDocument();
    expect(document.querySelector(".made-match mark")?.textContent).toBe("disg");
  });

  it("says so when no loop uses the word searched for", () => {
    view([loop({})], "zzz");
    expect(screen.getByText("No loop of yours uses “zzz”.")).toBeInTheDocument();
  });

  it("offers Delete on every row, including one that was never made", () => {
    view([loop({}), loop({ id: "loop00000000002", position: 2, audioRef: null, durationSeconds: null })]);
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(2);
  });

  it("deletes the loop the swipe belongs to", () => {
    const onDelete = view([loop({}), loop({ id: "loop00000000002", position: 2 })]);
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[1]);
    expect(onDelete).toHaveBeenCalledWith("loop00000000002");
  });

  it("opens a menu on a right-click, and deletes from it", () => {
    const onDelete = view([loop({ audioRef: null, durationSeconds: null })]);
    expect(screen.queryByRole("menuitem")).toBeNull();

    fireEvent.contextMenu(screen.getByText("asco"));
    const choice = screen.getByRole("menuitem", { name: "Delete this loop" });
    /* A mouse presses before it clicks, and the press is what used to close the menu: a bare click
       reached the button, a real one found it already gone. */
    fireEvent.pointerDown(choice);
    fireEvent.click(choice);
    expect(onDelete).toHaveBeenCalledWith("loop00000000001");
  });

  it("closes the menu on a press anywhere else, and on Escape", () => {
    const onDelete = view([loop({})]);

    fireEvent.contextMenu(screen.getByText("asco"));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("menuitem")).toBeNull();

    fireEvent.contextMenu(screen.getByText("asco"));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("menuitem")).toBeNull();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("opens the menu at the pointer", () => {
    view([loop({})]);
    fireEvent.contextMenu(screen.getByText("asco"), { clientX: 240, clientY: 36 });

    /* jsdom has no layout, so the row's box is at the origin and the offsets are the client point. */
    const menu = screen.getByRole("menu");
    expect(menu.style.getPropertyValue("--menu-x")).toBe("240px");
    expect(menu.style.getPropertyValue("--menu-y")).toBe("36px");
  });

  it("does not open a loop that was never made, but still lets it be right-clicked", () => {
    const onDelete = view([loop({ audioRef: null, durationSeconds: null })]);
    fireEvent.click(screen.getByText("asco"));
    expect(screen.getByText(/Never made/)).toBeInTheDocument();

    fireEvent.contextMenu(screen.getByText("asco"));
    expect(screen.getByRole("menuitem", { name: "Delete this loop" })).toBeInTheDocument();
    expect(onDelete).not.toHaveBeenCalled();
  });
});
