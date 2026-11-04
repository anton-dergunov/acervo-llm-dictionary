import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ImagePanel from "./ImagePanel";
import { AcervoApiError, backendSession, type ImageSettings } from "../api";

const STYLES = [
  { id: "oil-painting", label: "Oil on canvas", mono: false, photographic: false },
  { id: "film-noir", label: "Film noir", mono: true, photographic: true },
  { id: "ukiyo-e", label: "Japanese woodblock", mono: false, photographic: false }
];

const settings = (overrides: Partial<ImageSettings> = {}): ImageSettings => ({
  drawEnabled: true, stylesOff: [], boostVariety: true, storyContinuity: "artwork", chosen: false,
  maxAttempts: 4, styles: STYLES, available: true, ...overrides
});

/** Never settles, so the assertion is about what the screen does *before* the server answers. */
const hangs = () => vi.spyOn(backendSession, "saveImageSettings")
  .mockImplementation(() => new Promise(() => undefined));

async function shown(initial = settings()) {
  vi.spyOn(backendSession, "imageSettings").mockResolvedValue(initial);
  const notify = vi.fn();
  render(<ImagePanel onNotify={notify} />);
  await waitFor(() => expect(screen.getByText("Oil on canvas")).toBeTruthy());
  return { notify };
}

/* A style is a chip that is pressed when it is on. */
const chip = (label: string) => screen.getByRole("button", { name: new RegExp(`^${label}`) }) as HTMLButtonElement;
const switchFor = (label: string) => {
  const node = chip(label);
  return { checked: node.getAttribute("aria-pressed") === "true", disabled: node.disabled };
};

afterEach(() => { vi.restoreAllMocks(); });

describe("switching a style off", () => {
  it("moves the switch at once rather than waiting for the server", async () => {
    await shown();
    hangs();
    fireEvent.click(chip("Oil on canvas"));
    // The switch is the feedback. It used to sit still until the answer came back, while a
    // "Saving…" line appeared and vanished — which resized the whole dialog and put it back.
    expect(switchFor("Oil on canvas").checked).toBe(false);
    expect(screen.queryByText("Saving…")).toBeNull();
  });

  it("says nothing at all while it saves", async () => {
    await shown();
    hangs();
    fireEvent.click(chip("Film noir"));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("composes several clicks in a row rather than each undoing the last", async () => {
    // Switching four styles off is one gesture. Each click has to add to the previous one rather
    // than to whatever the last render happened to hold.
    await shown();
    const save = vi.spyOn(backendSession, "saveImageSettings")
      .mockImplementation(() => new Promise(() => undefined));
    fireEvent.click(chip("Oil on canvas"));
    fireEvent.click(chip("Film noir"));

    expect(save.mock.calls.map((call) => call[0].stylesOff)).toEqual([
      ["oil-painting"],
      ["oil-painting", "film-noir"]
    ]);
    expect(switchFor("Oil on canvas").checked).toBe(false);
    expect(switchFor("Film noir").checked).toBe(false);
  });

  it("does not let switches be ticked while a save is in flight", async () => {
    await shown();
    hangs();
    fireEvent.click(chip("Oil on canvas"));
    // Nothing is disabled: waiting a round trip between clicks would make switching off five
    // styles feel broken.
    expect(switchFor("Film noir").disabled).toBe(false);
  });

  it("puts the switch back when the server refuses, and says why", async () => {
    const { notify } = await shown();
    vi.spyOn(backendSession, "saveImageSettings")
      .mockRejectedValue(new AcervoApiError("At least one style must stay switched on.", 400, "no_styles_left"));

    fireEvent.click(chip("Oil on canvas"));
    expect(switchFor("Oil on canvas").checked).toBe(false);
    await waitFor(() => expect(switchFor("Oil on canvas").checked).toBe(true));
    expect(notify).toHaveBeenCalledWith("At least one style must stay switched on.");
  });

  it("takes the server's answer as final, not this screen's optimism", async () => {
    await shown();
    // The server stored something other than what was asked — its answer wins.
    vi.spyOn(backendSession, "saveImageSettings")
      .mockResolvedValue(settings({ stylesOff: ["ukiyo-e"], chosen: true }));
    fireEvent.click(chip("Oil on canvas"));
    await waitFor(() => expect(switchFor("Japanese woodblock").checked).toBe(false));
    expect(switchFor("Oil on canvas").checked).toBe(true);
  });

  it("ignores an older answer that arrives after a newer one", async () => {
    await shown();
    let settle: ((value: ImageSettings) => void) | null = null;
    vi.spyOn(backendSession, "saveImageSettings")
      .mockImplementationOnce(() => new Promise((resolve) => { settle = resolve; }))
      .mockResolvedValueOnce(settings({ stylesOff: ["oil-painting", "film-noir"], chosen: true }));

    fireEvent.click(chip("Oil on canvas"));
    fireEvent.click(chip("Film noir"));
    await waitFor(() => expect(switchFor("Film noir").checked).toBe(false));

    // The first save now answers, with a list that predates the second click.
    settle!(settings({ stylesOff: ["oil-painting"], chosen: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(switchFor("Film noir").checked).toBe(false);
  });
});

describe("switching every style at once", () => {
  it("switches them all on by sending an empty off-list", async () => {
    await shown(settings({ stylesOff: ["oil-painting", "film-noir"], chosen: true }));
    const save = hangs();
    fireEvent.click(screen.getByText("Switch all on"));
    // Which is also what a fresh account holds, so this doubles as the way back to the default.
    expect(save).toHaveBeenCalledWith({ stylesOff: [] });
    expect(switchFor("Oil on canvas").checked).toBe(true);
  });

  it("leaves one on when switching them all off, and says which", async () => {
    await shown();
    const save = hangs();
    fireEvent.click(screen.getByText("Switch all off"));
    // With none there is nothing to draw with, and "draw nothing" is the switch at the top of the
    // page rather than an empty list here. The first style is kept: photorealism is the one
    // register the template says can carry any meaning at all.
    expect(save).toHaveBeenCalledWith({ stylesOff: ["film-noir", "ukiyo-e"] });
    // The first style in the table is the one kept.
    expect(switchFor("Oil on canvas").checked).toBe(true);
    expect(switchFor("Film noir").checked).toBe(false);
    expect(screen.getByText("1 of 3 on")).toBeTruthy();
  });

  it("greys out each bulk move once it would do nothing", async () => {
    await shown();
    expect((screen.getByText("Switch all on") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Switch all off") as HTMLButtonElement).disabled).toBe(false);
  });

  it("counts what is on, so the state is legible without reading every row", async () => {
    await shown(settings({ stylesOff: ["film-noir"], chosen: true }));
    expect(screen.getByText("2 of 3 on")).toBeTruthy();
  });
});

describe("what the panel says about the server", () => {
  it("says these settings are on the server when it cannot be reached", async () => {
    vi.spyOn(backendSession, "imageSettings")
      .mockRejectedValue(new Error("network"));
    render(<ImagePanel onNotify={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/on the server, which could not be reached/)).toBeTruthy());
  });

  it("says plainly when no provider can draw, rather than offering a switch that will refuse", async () => {
    await shown(settings({ available: false }));
    expect(screen.getByText(/No picture provider is set up/)).toBeTruthy();
  });

  it("says the deployment's own defaults are in force until something is chosen", async () => {
    await shown();
    expect(screen.getByText(/defaults are in force/)).toBeTruthy();
    hangs();
    fireEvent.click(chip("Oil on canvas"));
    // `chosen` flips optimistically with everything else, so the note goes at once.
    expect(screen.queryByText(/defaults are in force/)).toBeNull();
  });
});
