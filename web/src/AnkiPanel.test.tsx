import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type AnkiStatus, type Job } from "./api";
import AnkiPanel from "./AnkiPanel";
import { jobStream } from "./jobs";

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

afterEach(() => { vi.restoreAllMocks(); jobStream.stop(); });

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

  it("pushes now, and follows the push to its outcome without being opened again", async () => {
    vi.spyOn(backendSession, "ankiStatus").mockResolvedValue(status({ lastPush: job({ id: "job000000000000",
      createdAt: "2026-09-27T20:00:00.000Z", steps: [{ name: "anki.push", state: "done",
        detail: { created: 9, updated: 9 } }] }) }));
    const queued = job({ id: "job000000000002", state: "queued", steps: [], finishedAt: null,
                         createdAt: "2026-09-28T21:00:00.000Z" });
    const pushed = vi.spyOn(backendSession, "ankiNow").mockResolvedValue(queued);
    render(<AnkiPanel onNotify={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Push now" }));
    await waitFor(() => expect(pushed).toHaveBeenCalledWith("push"));
    expect(await screen.findByText(/Last push: Waiting to start/)).toBeInTheDocument();

    act(() => { jobStream.apply({ ...queued, state: "running" }); });
    expect(screen.getByText(/Last push: Running now/)).toBeInTheDocument();
    act(() => { jobStream.apply({ ...job(), id: queued.id, createdAt: queued.createdAt }); });
    expect(screen.getByText(/Last push: Finished.*2 new, 5 changed/)).toBeInTheDocument();
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
