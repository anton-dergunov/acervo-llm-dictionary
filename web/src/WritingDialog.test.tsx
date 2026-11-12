import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StrokeAnswer } from "./api";
import { WritingDialog } from "./WritingDialog";
import { MARGIN, TOP, type Point } from "./writing/strokeData";
import { createShelf, STROKE_DATASET, StrokeStore } from "./writing/strokeStore";
import { FIXTURES, traced } from "./writing/testStrokes";

const SPAN = 1024 + 2 * MARGIN;

/* jsdom has no PointerEvent, and a MouseEvent standing in for one loses what the pad decides by —
   which pointer, of what kind, how hard. */
if (!("PointerEvent" in window)) {
  class TestPointerEvent extends MouseEvent {
    pointerId: number; pointerType: string; pressure: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
      this.pointerType = init.pointerType ?? "mouse";
      this.pressure = init.pressure ?? 0.5;
    }
  }
  Object.defineProperty(window, "PointerEvent", { value: TestPointerEvent, configurable: true });
}

function serving(): StrokeStore {
  return new StrokeStore(createShelf(), async (characters): Promise<StrokeAnswer> => ({
    dataset: STROKE_DATASET,
    characters: Object.fromEntries(Array.from(characters).filter((one) => one in FIXTURES).map((one) => [one, FIXTURES[one]])),
    missing: Array.from(characters).filter((one) => !(one in FIXTURES))
  }));
}

async function open(word: string, mode: "watch" | "trace" | "write", store = serving()) {
  localStorage.setItem("acervo-writing-mode", mode);
  render(<WritingDialog headword={word} reading="kǒu" language="zh-Hans" gloss="mouth" store={store} onClose={() => undefined} />);
  return pad();
}

async function pad(): Promise<SVGSVGElement> {
  const found = await screen.findByRole("img", { name: /Writing pad/ });
  // jsdom lays nothing out: the pad is a square exactly as wide as the dataset's box with its margin,
  // so a client coordinate is a dataset coordinate shifted by the margin.
  found.getBoundingClientRect = () => ({ left: 0, top: 0, width: SPAN, height: SPAN, right: SPAN, bottom: SPAN, x: 0, y: 0, toJSON: () => ({}) });
  return found as unknown as SVGSVGElement;
}

function draw(target: Element, points: Point[], pointerType = "mouse", pointerId = 1) {
  const at = (point: Point) => ({ clientX: point.x + MARGIN, clientY: TOP - point.y + MARGIN, pointerId, pointerType, pressure: 0.5, button: 0 });
  act(() => {
    fireEvent.pointerDown(target, at(points[0]));
    for (const point of points.slice(1)) fireEvent.pointerMove(target, at(point));
    fireEvent.pointerUp(target, at(points[points.length - 1]));
  });
}

const kou = FIXTURES["口"].medians.map((median) => median.map(([x, y]) => ({ x, y })));
const said = () => document.querySelector(".writing-said")?.textContent ?? "";

describe("the Write sheet", () => {
  beforeEach(() => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => { callback(0); return 0; });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    localStorage.clear();
  });

  it("checks each stroke in order and sums the character up", async () => {
    const target = await open("口", "trace");
    for (const median of kou) draw(target, traced(median));
    expect(said()).toBe("3 strokes · 3 right first time · precision 100, clean");
    expect([...document.querySelectorAll(".writing-dots li")].map((one) => one.className)).toEqual(["clean", "clean", "clean"]);
    expect(screen.getByRole("button", { name: "Compare" })).toBeInTheDocument();
  });

  it("says which stroke comes first when one is drawn out of order", async () => {
    const target = await open("口", "trace");
    draw(target, traced(kou[2]));
    expect(said()).toBe("That's stroke 3 — stroke 1 comes first.");
    expect(document.querySelectorAll(".writing-strokes path")).toHaveLength(0);
  });

  it("shows the stroke after two misses and writes it in after four", async () => {
    const target = await open("口", "write");
    const scribble = traced([{ x: 100, y: 100 }, { x: 900, y: 120 }, { x: 120, y: 700 }]);
    draw(target, scribble);
    expect(document.querySelector(".writing-anim.hint")).toBeNull();
    draw(target, scribble);
    expect(document.querySelector(".writing-anim.hint")).not.toBeNull();
    expect(said()).toMatch(/Watch it once\.$/);
    draw(target, scribble);
    draw(target, scribble);
    expect(said()).toBe("Stroke 1 is written in for you — watch how it goes.");
    expect(document.querySelector(".writing-dots li")?.className).toBe("filled");
  });

  it("stops taking a finger once a pen has drawn on it — the palm", async () => {
    const target = await open("口", "trace");
    draw(target, traced(kou[0]), "pen", 1);
    draw(target, traced(kou[1]), "touch", 2);
    expect(said()).toBe("Stroke 2 of 3");
    draw(target, traced(kou[1]), "pen", 3);
    expect(said()).toBe("Stroke 3 of 3");
  });

  it("takes nothing while watching", async () => {
    const target = await open("口", "watch");
    draw(target, traced(kou[0]));
    expect(screen.getByRole("button", { name: /Pause/ })).toBeInTheDocument();
    expect(document.querySelector(".writing-dots")).toBeNull();
  });

  it("hides the characters while writing from memory, and says which syllable is next", async () => {
    await open("口口", "write");
    expect(screen.getByRole("heading", { name: "Write from memory" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Character \d$/ })).toHaveLength(2);
    expect(screen.queryByText("口")).toBeNull();
  });

  it("says in one line when the strokes are not on this device and the server cannot be reached", async () => {
    localStorage.setItem("acervo-writing-mode", "trace");
    const offline = new StrokeStore(createShelf(), async () => { throw new Error("offline"); });
    render(<WritingDialog headword="口" reading="kǒu" language="zh-Hans" gloss="mouth" store={offline} onClose={() => undefined} />);
    expect(await screen.findByText(/not on this device yet/)).toBeInTheDocument();
  });

  it("says so for a character the dataset does not have", async () => {
    localStorage.setItem("acervo-writing-mode", "trace");
    render(<WritingDialog headword="𠮷" reading="jí" language="zh-Hans" gloss={null} store={serving()} onClose={() => undefined} />);
    expect(await screen.findByText("There is no stroke data for 𠮷.")).toBeInTheDocument();
  });

  it("remembers the way of practising on this device", async () => {
    await open("口", "watch");
    fireEvent.click(screen.getByRole("button", { name: "Write" }));
    expect(localStorage.getItem("acervo-writing-mode")).toBe("write");
  });
});
