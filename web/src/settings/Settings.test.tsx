/** The Settings window: its list of pages, drilling in and out, and where it opens. */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession } from "../api";
import { repository } from "../repository";
import type { SyncStatus } from "../sync";
import Settings, { type Page } from "./Settings";

const status: SyncStatus = {
  state: "idle", lastPulledAt: null, lastWroteAt: null, cursor: 0, persistent: true, message: null
} as SyncStatus;

function open(page?: Page, onClose = vi.fn()) {
  /* Every server-backed page asks; none of them is what is under test here. */
  for (const method of ["fetchModels", "promptRules", "imageSettings", "pronunciationSettings",
    "scheduleSettings", "ankiStatus", "jobs", "clipSettings"] as const) {
    vi.spyOn(backendSession, method).mockImplementation((() => new Promise(() => undefined)) as never);
  }
  render(<Settings
    email="learner@account.example.com" status={status} snapshot={repository.snapshot()} language="es"
    page={page} onSignOut={vi.fn()} onClose={onClose} onNotify={vi.fn()} onChanged={vi.fn()}
  />);
  return screen.getByRole("dialog", { name: "Settings" });
}

const nav = () => within(screen.getByRole("navigation", { name: "Settings sections" }));

afterEach(() => { vi.restoreAllMocks(); });

describe("the Settings window", () => {
  it("lists every page in six groups", () => {
    open();
    expect(nav().getAllByRole("heading").map((heading) => heading.textContent))
      .toEqual(["General", "Vocabulary", "Media", "Server", "Data", "About"]);
    expect(nav().getAllByRole("button")).toHaveLength(17);
  });

  it("credits every recording the IPA guide plays on its About page", async () => {
    const dialog = open("about");
    expect(await within(dialog).findByText("Sounds in the IPA guide")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: /Sounds in the IPA guide/ }));
    const recordings = await within(dialog).findByRole("region", { name: "Recordings" });
    expect(within(recordings).getAllByText(/trimmed/)).toHaveLength(165);
    expect(within(recordings).getByText(/^tʰ · Pinyin t$/)).toBeTruthy();
  });

  it("opens on the list when nothing asked for a page, and drills in and back out", () => {
    const dialog = open();
    // A narrow window shows one level at a time; a wide one shows both, by stylesheet alone.
    expect(dialog).toHaveAttribute("data-level", "list");
    fireEvent.click(nav().getByRole("button", { name: "Anki" }));
    expect(dialog).toHaveAttribute("data-level", "page");
    expect(screen.getByRole("heading", { name: "Anki", level: 3 })).toBeInTheDocument();
    expect(nav().getByRole("button", { name: "Anki" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(dialog).toHaveAttribute("data-level", "list");
  });

  it("opens straight onto a page something asked for", () => {
    const dialog = open("sync");
    expect(dialog).toHaveAttribute("data-level", "page");
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
  });

  it("reopens on the page used last, on this device", () => {
    open();
    fireEvent.click(nav().getByRole("button", { name: "Reading" }));
    document.body.innerHTML = "";
    open();
    expect(screen.getByRole("heading", { name: "Reading", level: 3 })).toBeInTheDocument();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    open(undefined, onClose);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
