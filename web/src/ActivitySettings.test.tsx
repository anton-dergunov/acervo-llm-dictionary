import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ActivitySettings from "./ActivitySettings";
import { backendSession, type Job } from "./api";
import { jobStream } from "./jobs";
import { repository } from "./repository";

function job(id: string, state: Job["state"], overrides: Partial<Job> = {}): Job {
  return {
    id, ownerId: "owner0000000001", parentId: null, kind: "enrich",
    subject: { kind: "lexeme", id: "lexemepicar0001" }, input: {}, state, trigger: "save",
    steps: [], rerun: false, cancelRequested: false, dismissed: false, error: null, message: null,
    notBefore: null, createdAt: `2026-09-17T10:00:0${id.slice(-1)}.000Z`, startedAt: null,
    finishedAt: state === "queued" || state === "running" ? null : "2026-09-17T10:05:00.000Z",
    ...overrides
  };
}

afterEach(() => { vi.restoreAllMocks(); jobStream.stop(); });

describe("Settings ▸ Activity", () => {
  beforeEach(() => {
    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue({
      hour: 2, steps: { "corpus.update": true }, chosen: false, timezone: "UTC",
      nextRunAt: "2026-09-18T02:00:00.000Z", lastRun: null
    });
  });

  it("lists what is running, what failed and what finished, with what can be done about each", async () => {
    vi.spyOn(backendSession, "jobs").mockResolvedValue([
      job("job000000000001", "running"),
      job("job000000000002", "failed", {
        subject: { kind: "lexeme", id: "lexemeother0001" },
        steps: [{ name: "clips", state: "failed" }]
      }),
      job("job000000000003", "done", { subject: { kind: "lexeme", id: "lexemeother0002" } })
    ]);
    const cancel = vi.spyOn(backendSession, "cancelJob")
      .mockResolvedValue(job("job000000000001", "running", { cancelRequested: true }));
    const again = vi.spyOn(backendSession, "enqueueJob").mockResolvedValue(job("job000000000004", "queued"));
    const snapshot = { ...repository.snapshot(), lexemes: [] };

    render(<ActivitySettings snapshot={snapshot} onNotify={vi.fn()} />);

    expect(await screen.findByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("Could not finish")).toBeInTheDocument();
    expect(screen.getByText("Couldn't search recorded speech")).toBeInTheDocument();
    expect(screen.getByText("Finished recently")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Dismiss" })).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("job000000000001"));

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(again).toHaveBeenCalledWith({
      kind: "enrich", subject: { kind: "lexeme", id: "lexemeother0001" }, input: {}
    }));
  });

  it("says when nothing is running", async () => {
    vi.spyOn(backendSession, "jobs").mockResolvedValue([]);
    render(<ActivitySettings snapshot={null} onNotify={vi.fn()} />);
    expect(await screen.findByText("Nothing is running.")).toBeInTheDocument();
    expect(await screen.findByText(/It has not run yet\./)).toBeInTheDocument();
  });
});
