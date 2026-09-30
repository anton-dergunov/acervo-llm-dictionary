import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PhotoPoint, PhotoReading, QuickLookUp } from "./api";
import PhotoCapture from "./PhotoCapture";

vi.mock("./photoImage", () => ({
  encodePhoto: vi.fn(async () => new Blob(["jpeg"], { type: "image/jpeg" })),
  still: vi.fn(() => document.createElement("canvas")),
  cropSquare: vi.fn(async () => new Blob(["square"], { type: "image/jpeg" }))
}));

const box = (x: number, y: number): PhotoPoint[] => [[x, y], [x + 0.1, y], [x + 0.1, y + 0.04], [x, y + 0.04]];

const READING: PhotoReading = {
  photoRef: "photos/owner0000000001/0123456789abcdef.jpg",
  width: 1000, height: 500, language: "es", vocabulary: true,
  readBy: { provider: "google-vision", model: "document-text-detection" },
  text: "Lo llevó a cabo.",
  words: [
    { id: "w0", text: "Lo", polygons: [box(0.1, 0.1)], confidence: 0.95, lineId: "l0", start: 0, end: 2 },
    { id: "w1", text: "llevó", polygons: [box(0.25, 0.1)], confidence: 0.95, lineId: "l0", start: 3, end: 8 },
    { id: "w2", text: "a", polygons: [box(0.4, 0.1)], confidence: 0.95, lineId: "l0", start: 9, end: 10 },
    { id: "w3", text: "cabo.", polygons: [box(0.55, 0.1)], confidence: 0.95, lineId: "l0", start: 11, end: 16 }
  ],
  lines: [{ id: "l0", polygon: [[0.1, 0.1], [0.65, 0.1], [0.65, 0.14], [0.1, 0.14]], wordIds: ["w0", "w1", "w2", "w3"] }],
  sentences: [{ id: "s0", text: "Lo llevó a cabo.", wordIds: ["w0", "w1", "w2", "w3"], start: 0, end: 16, truncatedStart: false, truncatedEnd: false }]
};

const FOUND: QuickLookUp = {
  resolution: {
    language: "es", headword: "llevar a cabo", lemma: "llevar a cabo", pos: "idiom",
    sentences: [{ text: "Lo llevó a cabo.", translation: null }], note: null, consumedLines: 1, consumedText: null,
    gloss: "to carry out"
  },
  duplicates: [],
  foldable: null
};

function setUp(overrides: Partial<Parameters<typeof PhotoCapture>[0]> = {}) {
  const props = {
    head: <h2>Add a word</h2>,
    notices: null,
    offline: false,
    unavailable: null,
    working: false,
    onRead: vi.fn(async () => READING),
    onStore: vi.fn(async () => ({ photoRef: "photos/owner0000000001/fedcba9876543210.jpg" })),
    onLookUp: vi.fn(async () => FOUND),
    onAdd: vi.fn(),
    onOpenLexeme: vi.fn(),
    onFoldIn: vi.fn(),
    onWarm: vi.fn(),
    ...overrides
  };
  const view = render(<PhotoCapture {...props} />);
  return { props, view };
}

async function choose(view: ReturnType<typeof render>) {
  const input = view.container.querySelector<HTMLInputElement>("input[type=file]")!;
  fireEvent.change(input, { target: { files: [new File(["x"], "page.png", { type: "image/png" })] } });
  await screen.findByAltText("The photo being read");
  const frame = view.container.querySelector<HTMLElement>(".photo-frame")!;
  frame.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, x: 0, y: 0, toJSON: () => ({}) });
  return frame;
}

/** Makes the square scroll: the image inside it is three squares tall, scrolled down by one. */
function tall(view: ReturnType<typeof render>, scrollTop: number) {
  const square = view.container.querySelector<HTMLElement>(".photo-square")!;
  Object.defineProperty(square, "scrollHeight", { value: 1500, configurable: true });
  Object.defineProperty(square, "clientHeight", { value: 500, configurable: true });
  square.scrollTop = scrollTop;
  fireEvent.scroll(square);
}

function tap(frame: HTMLElement, x: number, y: number) {
  fireEvent.pointerDown(frame, { clientX: x, clientY: y, pointerId: 1 });
  fireEvent.pointerUp(frame, { clientX: x, clientY: y, pointerId: 1 });
}

const getUserMedia = vi.fn();

beforeEach(() => {
  // jsdom has neither; the component needs only what these return.
  if (!("PointerEvent" in window)) Object.defineProperty(window, "PointerEvent", { value: MouseEvent, configurable: true });
  URL.createObjectURL = vi.fn(() => "blob:photo");
  URL.revokeObjectURL = vi.fn();
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
});

afterEach(() => { getUserMedia.mockReset(); });

describe("the Photo tab", () => {
  it("never turns the camera on by itself, and warms the server's reader", () => {
    const { props } = setUp();
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Take a photo" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Choose an image" })).toBeEnabled();
    expect(props.onWarm).toHaveBeenCalledTimes(1);
  });

  it("turns the camera on only when asked, and says plainly when it is not allowed", async () => {
    getUserMedia.mockRejectedValue(new DOMException("denied", "NotAllowedError"));
    setUp();
    fireEvent.click(screen.getByRole("button", { name: "Take a photo" }));
    expect(await screen.findByText(/not allowed to use the camera/)).toBeInTheDocument();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(getUserMedia.mock.calls[0][0].video.facingMode).toEqual({ ideal: "environment" });
  });

  it("says it needs the server when offline, and lets nothing be sent", () => {
    setUp({ offline: true });
    expect(screen.getByText("Photo capture needs the server.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take a photo" })).toBeDisabled();
  });

  it("reads a chosen image, looks up a tapped word in its sentence, and adds it with the photo", async () => {
    const { props, view } = setUp();
    const frame = await choose(view);
    expect(props.onRead).toHaveBeenCalledTimes(1);

    tap(frame, 290, 60);
    await waitFor(() => expect(props.onLookUp).toHaveBeenCalledTimes(1));
    expect(vi.mocked(props.onLookUp).mock.calls[0][0]).toEqual({ text: "Lo llevó a cabo.", selection: { start: 3, end: 8 }, source: "photo" });
    expect(await screen.findByText("llevar a cabo")).toBeInTheDocument();
    expect(screen.getByText(/to carry out/)).toBeInTheDocument();
    expect(screen.getByLabelText("The sentence, as it will be kept")).toHaveValue("Lo llevó a cabo.");

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    const added = vi.mocked(props.onAdd).mock.calls[0][0];
    expect(added.text).toBe("Lo llevó a cabo.");
    expect(added.resolution).toEqual(FOUND.resolution);
    expect(added.photoRef).toBe(READING.photoRef);
    expect(added.photoRegion.words).toEqual([box(0.25, 0.1)]);
    expect(added.sourceKind).toBe("web");
    expect(added.photo).toBeInstanceOf(Blob);
  });

  it("asks nothing for a tap that lands on no word", async () => {
    const { props, view } = setUp();
    const frame = await choose(view);
    tap(frame, 900, 450);
    await act(async () => { await Promise.resolve(); });
    expect(props.onLookUp).not.toHaveBeenCalled();
    expect(screen.getByText(/Tap a word to see what it means here/)).toBeInTheDocument();
  });

  it("adds without the photo when keeping it is switched off", async () => {
    const { props, view } = setUp();
    const frame = await choose(view);
    tap(frame, 290, 60);
    await screen.findByText("llevar a cabo");
    fireEvent.click(screen.getByLabelText(/Keep the photo/));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(vi.mocked(props.onAdd).mock.calls[0][0]).toMatchObject({ photoRef: null, photoRegion: null, photo: null });
  });

  it("offers to open a word already held and fold this sentence into it", async () => {
    const foldable = { sentences: [{ text: "Lo llevó a cabo.", translation: null }], reference: false, note: null };
    const { props, view } = setUp({
      onLookUp: vi.fn(async () => ({
        ...FOUND, duplicates: [{ id: "lexeme000000001", headword: "llevar a cabo", shortGloss: "to carry out" }], foldable
      }))
    });
    const frame = await choose(view);
    tap(frame, 290, 60);
    fireEvent.click(await screen.findByRole("button", { name: "Fold this sentence in" }));
    // The photo goes with it, as Add would keep it: the device attaches it, not the conversation.
    await waitFor(() => expect(props.onFoldIn).toHaveBeenCalledWith(
      "lexeme000000001", foldable,
      expect.objectContaining({ photoRef: READING.photoRef, photo: expect.anything() })
    ));
    expect(vi.mocked(props.onFoldIn).mock.calls[0][2]!.photoRegion).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open llevar a cabo" }));
    expect(props.onOpenLexeme).toHaveBeenCalledWith("lexeme000000001");
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
  });

  it("folds in without the photo when it is not to be kept", async () => {
    const foldable = { sentences: [{ text: "Lo llevó a cabo.", translation: null }], reference: false, note: null };
    const { props, view } = setUp({
      onLookUp: vi.fn(async () => ({
        ...FOUND, duplicates: [{ id: "lexeme000000001", headword: "llevar a cabo", shortGloss: "to carry out" }], foldable
      }))
    });
    const frame = await choose(view);
    tap(frame, 290, 60);
    fireEvent.click(screen.getByLabelText(/Keep the photo/));
    fireEvent.click(await screen.findByRole("button", { name: "Fold this sentence in" }));
    await waitFor(() => expect(props.onFoldIn).toHaveBeenCalledWith("lexeme000000001", foldable, null));
  });

  it("says so when the photo could not be read, and can try again", async () => {
    const onRead = vi.fn().mockRejectedValueOnce(new Error("The photo reader is temporarily rate limited, so the photo was not read."))
      .mockResolvedValueOnce(READING);
    const { view } = setUp({ onRead });
    const input = view.container.querySelector<HTMLInputElement>("input[type=file]")!;
    fireEvent.change(input, { target: { files: [new File(["x"], "page.png", { type: "image/png" })] } });
    expect(await screen.findByText(/temporarily rate limited/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(onRead).toHaveBeenCalledTimes(2));
  });

  it("hides the action bar while the camera is live, so nothing covers the shutter", async () => {
    getUserMedia.mockResolvedValue({ getTracks: () => [], getVideoTracks: () => [] });
    const { view } = setUp();
    fireEvent.click(screen.getByRole("button", { name: "Take a photo" }));
    expect(await screen.findByRole("button", { name: "Take the photo" })).toBeInTheDocument();
    expect(view.container.querySelector(".composer-actions")).toBeNull();
    expect(view.container.querySelector(".photo-square.fixed video")).not.toBeNull();
  });

  it("selects a phrase with a sideways drag along the line", async () => {
    const { props, view } = setUp();
    const frame = await choose(view);
    fireEvent.pointerDown(frame, { clientX: 290, clientY: 60, pointerId: 1 });
    fireEvent.pointerMove(frame, { clientX: 590, clientY: 62, pointerId: 1 });
    fireEvent.pointerUp(frame, { clientX: 590, clientY: 62, pointerId: 1 });
    await waitFor(() => expect(props.onLookUp).toHaveBeenCalled());
    expect(vi.mocked(props.onLookUp).mock.calls.at(-1)![0].selection).toEqual({ start: 3, end: 16 });
  });

  it("treats a finger moving up or down as scrolling, not as a tap", async () => {
    const { props, view } = setUp();
    const frame = await choose(view);
    fireEvent.pointerDown(frame, { clientX: 290, clientY: 60, pointerId: 1 });
    fireEvent.pointerUp(frame, { clientX: 291, clientY: 120, pointerId: 1 });
    await act(async () => { await Promise.resolve(); });
    expect(props.onLookUp).not.toHaveBeenCalled();
  });

  it("keeps a scrolled image as the square that was on screen", async () => {
    const { cropSquare } = await import("./photoImage");
    const { props, view } = setUp();
    const frame = await choose(view);
    tall(view, 0);
    expect(screen.getByText(/Swipe up or down/)).toBeInTheDocument();
    expect(view.container.querySelector(".photo-window.more-below")).not.toBeNull();
    tall(view, 500);
    expect(screen.queryByText(/Swipe up or down/)).toBeNull();
    tap(frame, 290, 60);
    await screen.findByText("llevar a cabo");
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(props.onAdd).toHaveBeenCalled());
    expect(vi.mocked(cropSquare).mock.calls.at(-1)!.slice(1)).toEqual([1 / 3, 1 / 3]);
    expect(props.onStore).toHaveBeenCalledTimes(1);
    const added = vi.mocked(props.onAdd).mock.calls[0][0];
    expect(added.photoRef).toBe("photos/owner0000000001/fedcba9876543210.jpg");
    expect(await added.photo!.text()).toBe("square");
    // The word sat at 0.10–0.14 of the whole image, which is above the square that was kept.
    expect(added.photoRegion!.words).toEqual([]);
  });

  it("keeps a photo that fits the square whole, with no second upload", async () => {
    const { props, view } = setUp();
    const frame = await choose(view);
    tap(frame, 290, 60);
    await screen.findByText("llevar a cabo");
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(props.onAdd).toHaveBeenCalled());
    expect(props.onStore).not.toHaveBeenCalled();
    expect(vi.mocked(props.onAdd).mock.calls[0][0].photoRef).toBe(READING.photoRef);
  });
});
