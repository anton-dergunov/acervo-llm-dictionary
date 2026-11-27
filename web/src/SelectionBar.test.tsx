/**
 * The selection bar says how many words are selected and which, opens the list of them, and is the
 * way to a loop or a story made from them.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SelectionBar from "./SelectionBar";
import { selectedWords } from "./selectors";
import { SPANISH, testGraph } from "./testGraph";

afterEach(cleanup);

function bar() {
  const graph = testGraph();
  const handlers = { onOpen: vi.fn(), onRemove: vi.fn(), onClear: vi.fn(), onLoop: vi.fn(), onStory: vi.fn() };
  render(<SelectionBar
    words={selectedWords(graph, SPANISH, ["lexemebalsa0001", "lexemepicar0001"])} language="es" name="Spanish" {...handlers}
  />);
  return handlers;
}

describe("the selection bar", () => {
  it("says how many are selected and which, in the order they were chosen", () => {
    bar();
    expect(screen.getByText("2 words selected")).toBeInTheDocument();
    expect(screen.getByText(/la balsa · picar/)).toBeInTheDocument();
  });

  it("opens the list of every selected word, where one can be opened or taken out", () => {
    const { onOpen, onRemove } = bar();
    fireEvent.click(screen.getByRole("button", { name: /Your selection: 2 words/ }));
    fireEvent.click(screen.getByRole("button", { name: "Remove picar from the selection" }));
    expect(onRemove).toHaveBeenCalledWith("lexemepicar0001");
    fireEvent.click(screen.getByRole("menuitem", { name: /la balsa/ }));
    expect(onOpen).toHaveBeenCalledWith("lexemebalsa0001");
  });

  it("makes a loop or a story from the selection, and forgets it", () => {
    const { onLoop, onStory, onClear } = bar();
    fireEvent.click(screen.getByRole("button", { name: "Make a loop from these words" }));
    fireEvent.click(screen.getByRole("button", { name: "Make a story from these words" }));
    fireEvent.click(screen.getByRole("button", { name: "Forget the selection" }));
    expect(onLoop).toHaveBeenCalledOnce();
    expect(onStory).toHaveBeenCalledOnce();
    expect(onClear).toHaveBeenCalledOnce();
  });
});
