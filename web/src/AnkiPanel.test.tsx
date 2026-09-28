import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type AnkiStatus, type Job } from "./api";
import AnkiPanel from "./AnkiPanel";

const job = (over: Partial<Job> = {}): Job => ({
  id: "job000000000001", ownerId: "owner0000000001", parentId: null, kind: "anki.push",
  subject: { kind: "anki", id: "push" }, input: {}, state: "done", trigger: "save",
  steps: [{ name: "anki.push", state: "done", detail: { created: 2, updated: 5 } },
          { name: "anki.pull", state: "done", detail: { written: 0, reviewsAdded: 0 } }],
  rerun: false, cancelRequested: false, dismissed: false, error: null, message: null,
  notBefore: null, createdAt: "2026-09-28T20:00:00.000Z", startedAt: "2026-09-28T20:01:00.000Z",
  finishedAt: "2026-09-28T20:01:10.000Z", ...over
});

const status = (over: Partial<AnkiStatus> = {}): AnkiStatus => ({
  configured: true, push: true, pull: false, lastPush: null, lastPull: null, ...over
});

afterEach(() => { vi.restoreAllMocks(); });

describe("Settings ▸ Anki", () => {
  it("shows the switches and saves one", async () => {
    vi.spyOn(backendSession, "ankiStatus").mockResolvedValue(status());
    const saved = vi.spyOn(backendSession, "saveAnkiSettings").mockResolvedValue(status({ pull: true }));
    render(<AnkiPanel onNotify={vi.fn()} />);

    expect(await screen.findByRole("checkbox", { name: /Send changes to Anki/ })).toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: /Read your reviews every hour/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ pull: true }));
  });

  it("says what the last push did, and a failure in its own words", async () => {
    vi.spyOn(backendSession, "ankiStatus").mockResolvedValue(status({
      lastPush: job(),
      lastPull: job({ kind: "anki.pull", state: "failed", steps: [],
                      message: "pre-mutation sync requires FULL_SYNC" })
    }));
    render(<AnkiPanel onNotify={vi.fn()} />);
    expect(await screen.findByText(/2 new, 5 changed/)).toBeInTheDocument();
    expect(screen.getByText(/Failed.*requires FULL_SYNC/)).toBeInTheDocument();
  });

  it("pushes now, and reads the state again afterwards", async () => {
    const reading = vi.spyOn(backendSession, "ankiStatus").mockResolvedValue(status());
    const pushed = vi.spyOn(backendSession, "ankiNow").mockResolvedValue(job({ state: "queued" }));
    render(<AnkiPanel onNotify={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Push now" }));
    await waitFor(() => expect(pushed).toHaveBeenCalledWith("push"));
    await waitFor(() => expect(reading).toHaveBeenCalledTimes(2));
  });

  it("offers nothing to switch on where the server has no Anki", async () => {
    vi.spyOn(backendSession, "ankiStatus").mockResolvedValue(status({ configured: false, push: false }));
    render(<AnkiPanel onNotify={vi.fn()} />);
    expect(await screen.findByText(/no Anki sync server behind it/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Send changes to Anki/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Push now" })).toBeDisabled();
  });

  it("says when the server could not be reached", async () => {
    vi.spyOn(backendSession, "ankiStatus").mockRejectedValue(new AcervoApiError("offline", 0, "offline"));
    render(<AnkiPanel onNotify={vi.fn()} />);
    expect(await screen.findByText("offline")).toBeInTheDocument();
  });
});
