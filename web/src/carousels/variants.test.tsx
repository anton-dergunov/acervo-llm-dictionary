import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChoiceCarousel, type CatalogueChoice } from "../ChoiceCarousel";
import { CarouselPicker } from "./CarouselPicker";
import { VARIANTS, carouselVariant, setCarouselVariant } from "./variants";

const choices: CatalogueChoice[] = ["a", "b", "c", "d", "e"].map((id) => ({ id, label: `Choice ${id}`, art: <span>{id}</span> }));
const rows = VARIANTS.filter((variant) => variant.id !== "tile");

describe("the carousel spike", () => {
  it.each(rows.map((variant) => variant.id))("%s offers every choice and reports a tap", (id) => {
    setCarouselVariant(id);
    const onChange = vi.fn();
    render(<ChoiceCarousel label="Style" choices={choices} value="c" onChange={onChange} />);
    const group = screen.getByRole("radiogroup", { name: "Style" });
    expect(group.querySelectorAll('[role="radio"]')).toHaveLength(5);
    expect(screen.getByRole("radio", { name: "Choice c" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "Choice e" }));
    expect(onChange).toHaveBeenCalledWith("e");
  });

  it("tile shows the choice, steps, and opens the grid", () => {
    setCarouselVariant("tile");
    const onChange = vi.fn();
    const onAll = vi.fn();
    render(<ChoiceCarousel label="Style" choices={choices} value="c" onChange={onChange} onAll={onAll} />);
    expect(screen.getByText("Choice c")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next: Style" }));
    expect(onChange).toHaveBeenCalledWith("d");
    fireEvent.click(screen.getByRole("button", { name: "Change Style" }));
    expect(onAll).toHaveBeenCalled();
  });

  it("the picker switches the row on this device", () => {
    setCarouselVariant("embla-fixed");
    render(<><CarouselPicker /><ChoiceCarousel label="Style" choices={choices} value="c" onChange={() => undefined} /></>);
    act(() => { fireEvent.change(screen.getByRole("combobox"), { target: { value: "tile" } }); });
    expect(carouselVariant()).toBe("tile");
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Style" })).toBeInTheDocument();
  });
});
