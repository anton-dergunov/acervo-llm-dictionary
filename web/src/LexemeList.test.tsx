/**
 * A word's row offers the selection and Delete by right-click or by swipe, and a selected word wears
 * its mark in the list.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LexemeList from "./LexemeList";
import { visibleRows } from "./selectors";
import { testGraph } from "./testGraph";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function list(selected: string[] = [], { aside = [] as string[], query = "" } = {}) {
  const graph = testGraph();
  for (const lexeme of graph.lexemes) if (aside.includes(lexeme.id)) lexeme.status = "aside";
  const view = visibleRows(graph, { language: "es", topic: "all", query, sort: "alpha" });
  const handlers = { onOpen: vi.fn(), onToggleSelected: vi.fn(), onSetAside: vi.fn(), onDelete: vi.fn() };
  render(<LexemeList
    rows={view.rows} aside={view.aside} languageName="Spanish" topic="all" topicLabel="All words" topicIcon="📖"
    query={query} sort="alpha" onSort={() => undefined} selected={(id) => selected.includes(id)} {...handlers}
  />);
  return handlers;
}

describe("a word's row", () => {
  it("puts the word in the selection from its right-click menu", () => {
    const { onToggleSelected } = list();
    fireEvent.contextMenu(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Add to selection" }));
    expect(onToggleSelected).toHaveBeenCalledWith("lexemepicar0001");
  });

  it("offers Unselect and Delete behind a selected row, and wears the selection's mark", () => {
    const { onToggleSelected, onDelete } = list(["lexemepicar0001"]);
    expect(screen.getAllByRole("img", { name: "Selected" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /picar/ })).toHaveClass("picked");
    fireEvent.click(screen.getByRole("button", { name: "Unselect" }));
    expect(onToggleSelected).toHaveBeenCalledWith("lexemepicar0001");
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    expect(onDelete).toHaveBeenCalledWith("lexemebalsa0001");
  });
});

describe("words set aside", () => {
  it("wait folded under a rule at the foot of the list, and unfold on a tap that is remembered", () => {
    list([], { aside: ["lexemebalsa0001"] });
    const rule = screen.getByRole("button", { name: /Set aside · 1/ });
    expect(rule).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /la balsa/ })).toBeNull();
    fireEvent.click(rule);
    expect(screen.getByRole("button", { name: /la balsa/ })).toHaveClass("aside");
    cleanup();
    list([], { aside: ["lexemebalsa0001"] });
    expect(screen.getByRole("button", { name: /Set aside · 1/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("are shown open in a search, since they are part of its answer", () => {
    list([], { aside: ["lexemebalsa0001"], query: "embarcación" });
    expect(screen.queryByRole("button", { name: /Set aside/ })).toBeNull();
    expect(screen.getByText("Set aside · 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /la balsa/ })).toHaveClass("aside");
    expect(screen.queryByText(/No words of yours match/)).toBeNull();
  });

  it("are set aside from a row, and brought back from one", () => {
    const { onSetAside } = list([], { aside: ["lexemebalsa0001"] });
    fireEvent.contextMenu(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Set it aside" }));
    expect(onSetAside).toHaveBeenCalledWith("lexemepicar0001", true);
    fireEvent.click(screen.getByRole("button", { name: /Set aside · 1/ }));
    fireEvent.contextMenu(screen.getByRole("button", { name: /la balsa/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Bring it back" }));
    expect(onSetAside).toHaveBeenCalledWith("lexemebalsa0001", false);
  });
});
