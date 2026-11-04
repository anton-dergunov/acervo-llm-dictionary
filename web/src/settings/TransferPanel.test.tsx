import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { strToU8, zipSync } from "fflate";
import { backendSession } from "../api";
import { MemoryDatabase } from "../localDatabase";
import { LocalAcervoRepository, repository, type ReplicaSnapshot } from "../repository";
import { testGraph, TEST_OWNER } from "../testGraph";
import { fakeRemote } from "../testRemote";
import { syncEngine } from "../sync";
import { exportBundle } from "../transfer";
import { ExportPanel, ImportPanel } from "./TransferPanel";

const AT = "2026-09-01T12:00:00.000Z";

const snapshotOf = (): ReplicaSnapshot => ({
  ...testGraph(), ready: true, ownerId: TEST_OWNER, deviceId: "device000000001",
  datasetId: "dataset00000001", cursor: 9, lastPulledAt: null, lastWroteAt: null, persistent: true
});

/** jsdom's File has no `arrayBuffer`, which every browser and the WKWebView host do have. */
function fileOf(bytes: Uint8Array, name: string): File {
  const file = new File([bytes as unknown as BlobPart], name);
  Object.defineProperty(file, "arrayBuffer", {
    value: () => Promise.resolve(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength))
  });
  return file;
}

function bundleFile(name = "acervo-all-2026-09-01.zip"): File {
  const archive: Record<string, Uint8Array> = {};
  exportBundle(testGraph(), { language: "all", markdown: false, images: false, pronunciations: false }, AT)
    .forEach((file) => { archive[file.path] = strToU8(file.text); });
  return fileOf(zipSync(archive), name);
}

/** The same bundle with a picture beside a word file, the way an export with pictures writes it. */
function bundleWithPicture(): File {
  const archive: Record<string, Uint8Array> = {};
  exportBundle(testGraph(), { language: "all", markdown: false, images: false, pronunciations: false }, AT)
    .forEach((file) => { archive[file.path] = strToU8(file.text); });
  archive["media/es/picar-1.webp"] = new Uint8Array([1, 2, 3]);
  return fileOf(zipSync(archive), "acervo-all-2026-09-01.zip");
}

/* jsdom has neither of these, and the export path is exactly the code that needs them. */
let saved: { name: string; blob: Blob } | null = null;
beforeEach(() => {
  saved = null;
  URL.createObjectURL = vi.fn(() => "blob:acervo");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    saved = { name: this.download, blob: new Blob() };
  });
});
afterEach(() => vi.restoreAllMocks());

describe("the export panel", () => {
  it("offers every language the replica holds, and all of them together", () => {
    render(<ExportPanel snapshot={snapshotOf()} />);
    const options = within(screen.getByRole("combobox")).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      "All languages", "Spanish · 3 entries", "English · 1 entry"
    ]);
  });

  it("writes a file named after what is in it", async () => {
    render(<ExportPanel snapshot={snapshotOf()} />);
    fireEvent.click(screen.getByRole("button", { name: "Export…" }));
    // Not synchronous any more: the clips this device does not hold are fetched before it is zipped.
    await waitFor(() => expect(saved!.name).toMatch(/^acervo-all-\d{4}-\d{2}-\d{2}\.zip$/));

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "es" } });
    fireEvent.click(screen.getByRole("button", { name: "Export…" }));
    await waitFor(() => expect(saved!.name).toMatch(/^acervo-es-\d{4}-\d{2}-\d{2}\.zip$/));
  });
});

describe("the import panel", () => {
  beforeEach(async () => {
    // The panel writes through the shared repository, the way every other surface does.
    Object.assign(repository, new LocalAcervoRepository(new MemoryDatabase()));
    await repository.load(TEST_OWNER);
    repository.attachRemote(fakeRemote());
  });

  const choose = async (file: File) => {
    const input = document.querySelector<HTMLInputElement>("input[type=file]")!;
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    fireEvent.change(input);
    await screen.findByText(file.name);
  };

  it("says what a bundle holds before writing any of it", async () => {
    render(<ImportPanel onChanged={() => {}} />);
    await choose(bundleFile());
    expect(screen.getByText("4 entries, 2 topics, 2 languages")).toBeInTheDocument();
    expect(repository.snapshot().lexemes).toEqual([]);
  });

  it("imports the bundle and reports what it did", async () => {
    const changed = vi.fn();
    render(<ImportPanel onChanged={changed} />);
    await choose(bundleFile());
    fireEvent.click(screen.getByRole("button", { name: "Import 4 entries" }));

    expect(await screen.findByText("Import finished")).toBeInTheDocument();
    expect(screen.getByText("4 added, 2 new topics, 2 new languages")).toBeInTheDocument();
    expect(repository.snapshot().lexemes.filter((lexeme) => !lexeme.deleted)).toHaveLength(4);
    expect(changed).toHaveBeenCalled();
  });

  it("pulls after restoring pictures, so a finished import has them", async () => {
    /* A word arrives in the replica by itself: `saveArticle` merges what the server answers. A
       picture does not — it is written by the image route — so without this the article showed
       empty frames and a "waiting" count until the next scheduled sync came round a minute later. */
    const attach = vi.spyOn(backendSession, "attachImage")
      .mockResolvedValue({} as never);
    const pull = vi.spyOn(syncEngine, "syncNow")
      .mockResolvedValue(syncEngine.getStatus());

    render(<ImportPanel onChanged={() => {}} />);
    await choose(bundleWithPicture());
    fireEvent.click(screen.getByRole("button", { name: "Import 4 entries" }));

    expect(await screen.findByText("Import finished")).toBeInTheDocument();
    expect(attach).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/1 pictures put back/)).toBeInTheDocument();
    expect(pull).toHaveBeenCalled();
  });

  it("does not pull when the bundle carried no pictures", async () => {
    const pull = vi.spyOn(syncEngine, "syncNow").mockResolvedValue(syncEngine.getStatus());
    render(<ImportPanel onChanged={() => {}} />);
    await choose(bundleFile());
    fireEvent.click(screen.getByRole("button", { name: "Import 4 entries" }));

    expect(await screen.findByText("Import finished")).toBeInTheDocument();
    expect(pull).not.toHaveBeenCalled();
  });

  it("lists the words it left alone on a second import", async () => {
    const { unmount } = render(<ImportPanel onChanged={() => {}} />);
    await choose(bundleFile());
    fireEvent.click(screen.getByRole("button", { name: "Import 4 entries" }));
    await screen.findByText("Import finished");
    unmount();

    render(<ImportPanel onChanged={() => {}} />);
    await choose(bundleFile());
    fireEvent.click(screen.getByRole("button", { name: "Import 4 entries" }));
    await screen.findByText("Import finished");

    expect(screen.getByText("0 added, 4 already present")).toBeInTheDocument();
    const skipped = within(screen.getByText("Already in your vocabulary").parentElement!);
    expect(skipped.getByText("picar")).toBeInTheDocument();
    expect(repository.snapshot().lexemes.filter((lexeme) => !lexeme.deleted)).toHaveLength(4);
  });

  it("refuses a file that is not an export, and says so", async () => {
    render(<ImportPanel onChanged={() => {}} />);
    const input = document.querySelector<HTMLInputElement>("input[type=file]")!;
    Object.defineProperty(input, "files", {
      value: [fileOf(strToU8("hello"), "notes.txt")], configurable: true
    });
    fireEvent.change(input);
    expect(await screen.findByRole("alert")).toHaveTextContent(/does not look like an Acervo export/);
  });
});
