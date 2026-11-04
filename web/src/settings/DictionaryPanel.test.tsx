import { IDBFactory } from "fake-indexeddb";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendSession, type RemoteDictionary } from "../api";
import DictionaryPanel from "./DictionaryPanel";
import { install, isEnabled, uninstall } from "../dictionaries";
import * as store from "../dictionaryStore";
import sample from "../testFixtures/sampleDictionary.json";

const remote = (id: string, overrides: Partial<RemoteDictionary> = {}): RemoteDictionary => ({
  id, name: id, sourceLang: "es", targetLang: "en", tier: "fields", licence: "CC BY-SA 4.0",
  attribution: "Wiktionary contributors.", entryCount: 834245, keyCount: 865202,
  blobBytes: 20 * 2 ** 20, indexBytes: 8 * 2 ** 20, schemaVersion: 1, ...overrides
});

function panel() {
  return render(<DictionaryPanel onNotify={() => {}} />);
}

/** `closest` is typed as `Element`, and `within` wants an `HTMLElement`. */
const rowOf = (element: HTMLElement): HTMLElement =>
  element.closest(".pref-row") as HTMLElement;

describe("the Dictionaries pane", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(store, "storageReport").mockResolvedValue({
      usedBytes: 30 * 2 ** 20, quotaBytes: 4 * 2 ** 30, persisted: true
    });
    vi.spyOn(backendSession, "listDictionaries").mockResolvedValue({ dictionaries: [] });
  });

  afterEach(() => vi.restoreAllMocks());

  it("says each dictionary comes from its publisher", async () => {
    panel();
    expect(await screen.findByText(/downloads from its publisher/i)).toBeInTheDocument();
  });

  it("groups by language and shows a licence on every row", async () => {
    panel();
    const spanish = await screen.findByRole("heading", { name: /Spanish/i });
    const group = spanish.parentElement!;
    expect(within(group).getAllByText(/CC BY-SA 4\.0/).length).toBeGreaterThan(0);
  });

  it("shows what this device holds and whether that storage is safe", async () => {
    panel();
    expect(await screen.findByText(/Nothing stored on this device/i)).toBeInTheDocument();
    expect(screen.getByText(/protected from being cleared/i)).toBeInTheDocument();
  });

  it("reports headroom rather than a usage figure the browser has not caught up with", async () => {
    // Measured on WebKit: estimate().usage stays at zero right after a 40 MiB write, so quoting it
    // back would tell someone holding dictionaries that they are holding nothing.
    vi.spyOn(store, "storageReport").mockResolvedValue({
      usedBytes: 0, quotaBytes: 78 * 2 ** 30, persisted: true
    });
    panel();
    expect(await screen.findByText(/About 78\.0 GB available/i)).toBeInTheDocument();
    expect(screen.queryByText(/of about .* used/i)).toBeNull();
  });

  it("quotes the browser's usage when it is believable", async () => {
    vi.spyOn(store, "storageReport").mockResolvedValue({
      usedBytes: 30 * 2 ** 20, quotaBytes: 4 * 2 ** 30, persisted: true
    });
    panel();
    expect(await screen.findByText(/30 MB of about 4\.0 GB used/i)).toBeInTheDocument();
  });

  it("warns when the browser may clear the storage again", async () => {
    vi.spyOn(store, "storageReport").mockResolvedValue({
      usedBytes: null, quotaBytes: null, persisted: false
    });
    panel();
    expect(await screen.findByText(/may clear its storage/i)).toBeInTheDocument();
    expect(screen.getByText(/does not say how much room/i)).toBeInTheDocument();
  });

  it("remembers switching a dictionary off for this device", async () => {
    panel();
    await screen.findByRole("heading", { name: /Spanish/i });
    const row = rowOf(screen.getByText("CC-CEDICT"));
    // Everything usable is on to begin with, so the switch that means anything is the one off.
    expect(isEnabled("cc-cedict")).toBe(true);
    fireEvent.click(within(row).getByRole("switch"));
    await waitFor(() => expect(isEnabled("cc-cedict")).toBe(false));
    fireEvent.click(within(row).getByRole("switch"));
    await waitFor(() => expect(isEnabled("cc-cedict")).toBe(true));
  });

  it("cannot offer to store a dictionary the server has not compiled", async () => {
    panel();
    await screen.findByRole("heading", { name: /Spanish/i });
    const row = rowOf(screen.getByText("CC-CEDICT"));
    const button = within(row).getByRole("button", { name: /^store$/i });
    expect(button).toBeDisabled();
    expect(await screen.findByText(/has not compiled any dictionaries/i)).toBeInTheDocument();
  });

  it("offers to store one the server does have", async () => {
    vi.spyOn(backendSession, "listDictionaries")
      .mockResolvedValue({ dictionaries: [remote("cc-cedict")] });
    panel();
    const row = rowOf(await screen.findByText("CC-CEDICT"));
    await waitFor(() =>
      expect(within(row).getByRole("button", { name: /^store$/i })).toBeEnabled());
    expect(within(row).getByText(/on your server/i)).toBeInTheDocument();
  });

  it("says a dictionary is stored here, with its size, and offers to remove it", async () => {
    // Installed for real through the service, because the pane reads the store the service writes;
    // mocking the store after import would only prove the mock works.
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: new IDBFactory() });
    vi.spyOn(backendSession, "dictionaryFileUrl")
      .mockImplementation((id, extension) => `https://acervo.example.com/${id}.${extension}`);
    vi.spyOn(backendSession, "dictionaryHeaders").mockReturnValue({});
    vi.spyOn(globalThis, "fetch").mockImplementation((async (url: string) => {
      const name = String(url).split("/").pop()!;
      const extension = name.split(".").pop()!;
      const body = extension === "json"
        ? new TextEncoder().encode(JSON.stringify({ ...sample.metadata, id: "cc-cedict", name: "CC-CEDICT" }))
        : Uint8Array.from(atob(sample[extension as "dict" | "idx"]), (c) => c.charCodeAt(0));
      return {
        ok: true, status: 200, headers: new Headers(),
        blob: async () => new Blob([body]),
        text: async () => new TextDecoder().decode(body)
      } as unknown as Response;
    }) as typeof fetch);

    await install("cc-cedict");
    try {
      panel();
      const row = rowOf(await screen.findByText("CC-CEDICT"));
      await waitFor(() => expect(within(row).getByText(/Stored ·/)).toBeInTheDocument());
      expect(within(row).getByRole("button", { name: /^remove$/i })).toBeInTheDocument();
      expect(within(row).queryByRole("button", { name: /^store$/i })).toBeNull();
    } finally {
      await uninstall("cc-cedict");
    }
  });

  it("gives a link-out an address and nothing to switch on", async () => {
    panel();
    const row = rowOf(await screen.findByText(/Diccionario de la lengua española/i));
    expect(within(row).queryByRole("switch")).toBeNull();
    expect(within(row).getByRole("link", { name: /open/i }))
      .toHaveAttribute("href", "https://dle.rae.es/");
  });

  it("says an online source needs no download", async () => {
    panel();
    const row = rowOf(await screen.findByText(/Free Dictionary API/i));
    expect(within(row).getByText(/Looked up as you need it/i)).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /^store$/i })).toBeNull();
  });
});
