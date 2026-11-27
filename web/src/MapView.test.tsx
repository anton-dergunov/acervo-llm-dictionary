import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { forwardRef, useImperativeHandle } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type ServerMap } from "./api";
import type { Job } from "./api";
import { jobStream } from "./jobs";
import { MemoryMapStore } from "./mapStore";
import { MapView, replaceMapStoreForTests } from "./MapView";
import type { MapData, MapPoint } from "./meaningMap";
import { vocabularyOptions } from "./selectors";
import { ENGLISH, SPANISH, TEST_OWNER, testGraph } from "./testGraph";

/* jsdom has no canvas, so the drawing is stood in for by its points as buttons: everything around it
   — which map, the peek, Find, the way to an article — is what this checks. */
const handle = { select: vi.fn(), reveal: vi.fn(), setInsets: vi.fn(), fit: vi.fn(), zoomBy: vi.fn() };
let drawn: { data: MapData; highlighted?: Set<number> | null; chosen?: Set<number> | null; selected?: number } | null = null;
vi.mock("./meaningMap", () => ({
  MeaningMap: forwardRef(function Stub(props: {
    data: MapData; selected?: number; highlighted?: Set<number> | null;
    onSelect?: (point: MapPoint | null, index: number) => void;
  }, ref) {
    useImperativeHandle(ref, () => handle, []);
    drawn = props;
    return <div data-testid="map">{props.data.points.map((p, i) => <button key={p.id}
      onClick={() => props.onSelect?.(p, i)}>point {p.headword} {p.emoji}</button>)}</div>;
  })
}));
vi.mock("./picture", () => ({ usePicture: () => ({ url: "blob:picture", error: null }) }));

function serverMap(overrides: Partial<ServerMap> = {}): ServerMap {
  return {
    language: "es", fingerprint: "fp-1", version: "fp-1.none", model: "m", side: 1000, words: 2, senses: 3, names: "none",
    regions: [], contours: [],
    points: [
      { sense: "sensepicaritch0", lexeme: "lexemepicar0001", x: 100, y: 100, r: -1, h: -1, rank: 1, nb: [2] },
      { sense: "sensepicarchop0", lexeme: "lexemepicar0001", x: 800, y: 700, r: -1, h: -1, rank: 0.5, nb: [2] },
      { sense: "sensebalsaraft0", lexeme: "lexemebalsa0001", x: 300, y: 400, r: -1, h: -1, rank: 0.2, nb: [0] }
    ],
    ...overrides
  };
}

let store: MemoryMapStore;

function view(overrides: Partial<Parameters<typeof MapView>[0]> = {}) {
  const graph = testGraph();
  /* The map's row goes into the top bar, which the application hands it; here, a stand-in. */
  const bar = document.body.appendChild(document.createElement("div"));
  const props = {
    graph, owner: TEST_OWNER, vocabularyId: SPANISH, language: "es", vocabularies: vocabularyOptions(graph), camera: null, bar,
    onCamera: vi.fn(), selected: null as string | null, onSelect: vi.fn(), onVocabulary: vi.fn(),
    onOpen: vi.fn(), onClose: vi.fn(), ...overrides
  };
  const rendered = render(<MapView {...props} />);
  return { ...rendered, props, rerender: (next: Partial<typeof props>) => rendered.rerender(<MapView {...props} {...next} />) };
}

beforeEach(() => {
  store = new MemoryMapStore();
  replaceMapStoreForTests(store);
  drawn = null;
});
afterEach(() => vi.restoreAllMocks());

describe("the map surface", () => {
  it("asks the server for the map and draws it, joined to the replica", async () => {
    const read = vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    view();
    expect(await screen.findByRole("button", { name: /point la balsa/ })).toBeInTheDocument();
    expect(read).toHaveBeenCalledWith(SPANISH, undefined);
    expect(screen.getByText(/3 meanings · 2 words/)).toBeInTheDocument();
    expect((await store.read(TEST_OWNER, SPANISH))?.fingerprint).toBe("fp-1");
  });

  it("opens on the map this device holds, and sends its fingerprint to ask whether it is current", async () => {
    await store.save(TEST_OWNER, SPANISH, serverMap());
    const read = vi.spyOn(backendSession, "readMap").mockResolvedValue({ current: true, version: "fp-1.none" });
    view();
    expect(await screen.findByRole("button", { name: /point la balsa/ })).toBeInTheDocument();
    await waitFor(() => expect(read).toHaveBeenCalledWith(SPANISH, "fp-1.none"));
  });

  it("keeps a map it holds on screen when the server cannot be reached", async () => {
    await store.save(TEST_OWNER, SPANISH, serverMap());
    vi.spyOn(backendSession, "readMap").mockRejectedValue(new AcervoApiError("unreachable", 0, "offline"));
    view();
    expect(await screen.findByRole("button", { name: /point la balsa/ })).toBeInTheDocument();
    expect(screen.queryByText("No map yet")).not.toBeInTheDocument();
  });

  it("says plainly that there is no map when it has none and the server cannot be reached", async () => {
    vi.spyOn(backendSession, "readMap").mockRejectedValue(new AcervoApiError("unreachable", 0, "offline"));
    view();
    expect(await screen.findByText("No map yet")).toBeInTheDocument();
  });

  it("names a young vocabulary's map as words, without regions", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    view();
    expect(await screen.findByText(/Regions appear once a vocabulary has about 150 meanings/)).toBeInTheDocument();
  });

  it("peeks at a tapped sense and opens its article from there", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const { props, rerender } = view();
    fireEvent.click(await screen.findByRole("button", { name: /point picar 🔪/ }));
    expect(props.onSelect).toHaveBeenCalledWith("sensepicarchop0");
    rerender({ selected: "sensepicarchop0" });
    expect(screen.getByText("Cortar en trozos pequeños.")).toBeInTheDocument();
    expect(screen.getByText("to chop; to dice")).toBeInTheDocument();
    expect(screen.getByText("Meaning 2 of 2")).toBeInTheDocument();
    expect(drawn?.selected).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: /Open the article/ }));
    expect(props.onOpen).toHaveBeenCalledWith("lexemepicar0001", "sensepicarchop0");
  });

  it("marks every sense of a selected word, and selects a word from the peek", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const onToggleChosen = vi.fn();
    const { rerender } = view({ chosen: new Set(["lexemepicar0001"]), onToggleChosen });
    await screen.findByRole("button", { name: /point la balsa/ });
    expect([...(drawn?.chosen ?? [])]).toEqual([0, 1]);
    rerender({ selected: "sensebalsaraft0" });
    fireEvent.click(screen.getByRole("button", { name: /^Select$/ }));
    expect(onToggleChosen).toHaveBeenCalledWith("lexemebalsa0001");
    rerender({ selected: "sensepicaritch0" });
    expect(screen.getByRole("button", { name: /^Selected$/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("flies to the word's other sense from the peek", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const { props } = view({ selected: "sensepicarchop0" });
    fireEvent.click(await screen.findByRole("button", { name: "Meaning 1" }));
    expect(props.onSelect).toHaveBeenCalledWith("sensepicaritch0");
    expect(handle.select).toHaveBeenCalledWith(0, { fly: true });
  });

  it("finds a word, lights every match and flies to the one chosen", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const { props } = view();
    await screen.findByRole("button", { name: /point la balsa/ });
    fireEvent.change(screen.getByRole("searchbox", { name: "Find a word on the map" }), { target: { value: "pic" } });
    expect(drawn?.highlighted).toEqual(new Set([0, 1]));
    fireEvent.keyDown(screen.getByRole("searchbox", { name: "Find a word on the map" }), { key: "Enter" });
    expect(props.onSelect).toHaveBeenCalledWith("sensepicaritch0");
  });

  it("switches vocabulary from its own row, the top bar being hidden", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const { props } = view();
    fireEvent.click(await screen.findByRole("button", { name: "Vocabulary: Spanish" }));
    fireEvent.click(screen.getByRole("button", { name: /English/ }));
    expect(props.onVocabulary).toHaveBeenCalledWith(ENGLISH);
  });

  it("puts the peek away with Escape, and then leaves", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const { props, rerender } = view({ selected: "sensepicarchop0" });
    await screen.findByText("Cortar en trozos pequeños.");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(props.onSelect).toHaveBeenCalledWith(null);
    rerender({ selected: null });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(props.onClose).toHaveBeenCalled();
  });

  it("flies to the sense it was asked to show, as Find would, once the map holds it", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const onFlown = vi.fn();
    const { props } = view({ fly: "sensebalsaraft0", onFlown });
    await screen.findByRole("button", { name: /point la balsa/ });
    await waitFor(() => expect(handle.select).toHaveBeenCalledWith(2, { fly: true }));
    expect(props.onSelect).toHaveBeenCalledWith("sensebalsaraft0");
    expect(onFlown).toHaveBeenCalled();
  });

  it("draws its row in the bar it is given", async () => {
    vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap());
    const { props } = view();
    await screen.findByRole("button", { name: /point la balsa/ });
    expect((props.bar as HTMLElement).querySelector(".map-top input[aria-label='Find a word on the map']")).not.toBeNull();
  });

  it("asks again when the job naming its regions finishes", async () => {
    const read = vi.spyOn(backendSession, "readMap").mockResolvedValue(serverMap({ names: "pending", version: "fp-1.pending" }));
    view();
    await screen.findByRole("button", { name: /point la balsa/ });
    const job = (state: Job["state"]) => ({ id: "job1", kind: "map.name", state, subject: { kind: "vocabulary", id: SPANISH } }) as Job;
    act(() => jobStream.apply(job("running")));
    read.mockResolvedValue(serverMap({ names: "ready", version: "fp-1.ready" }));
    act(() => jobStream.apply(job("done")));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    // The unnamed map's version, which the server no longer calls current.
    expect(read).toHaveBeenLastCalledWith(SPANISH, "fp-1.pending");
  });
});
