import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ActivitySettings from "./ActivitySettings";
import { AcervoApiError, backendSession, type Job, type ScheduleSettings } from "../api";
import { jobStream } from "../jobs";
import { repository } from "../repository";

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
    expect(await screen.findByText("Nothing is running")).toBeInTheDocument();
    expect(await screen.findByText("Not yet")).toBeInTheDocument();
  });
});

/* The nightly run's settings, which were a Schedule page of their own until Activity took them in. */
describe("Settings ▸ Activity ▸ Nightly run", () => {
  const settings = (over: Partial<ScheduleSettings> = {}): ScheduleSettings => ({
    hour: 2, steps: { "corpus.update": true }, chosen: false,
    timezone: "Europe/Madrid", nextRunAt: "2026-09-18T00:00:00.000Z",
    lastRun: null, ...over
  });

  beforeEach(() => { vi.spyOn(backendSession, "jobs").mockResolvedValue([]); });

  it("shows the hour in the server's zone, and saves a new one", async () => {
    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue(settings());
    const saved = vi.spyOn(backendSession, "saveScheduleSettings")
      .mockResolvedValue(settings({ hour: 5, chosen: true }));
    render(<ActivitySettings snapshot={null} onNotify={vi.fn()} />);

    expect(await screen.findByDisplayValue("02:00")).toBeInTheDocument();
    expect(screen.getByText(/Europe\/Madrid/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Run at"), { target: { value: "5" } });
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ hour: 5 }));
  });

  it("switches a step", async () => {
    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue(settings());
    const saved = vi.spyOn(backendSession, "saveScheduleSettings").mockResolvedValue(settings());
    render(<ActivitySettings snapshot={null} onNotify={vi.fn()} />);

    fireEvent.click(await screen.findByRole("switch", { name: /Update recorded speech/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ steps: { "corpus.update": false } }));
  });

  it("says how the last run went, and when nothing has run", async () => {
    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue(settings());
    const { unmount } = render(<ActivitySettings snapshot={null} onNotify={vi.fn()} />);
    expect(await screen.findByText("Not yet")).toBeInTheDocument();
    unmount();

    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue(settings({
      lastRun: {
        id: "job000000000001", ownerId: "owner0000000001", parentId: null, kind: "nightly",
        subject: { kind: "schedule", id: "nightly" }, input: {}, state: "failed",
        trigger: "schedule", steps: [], rerun: false, cancelRequested: false, dismissed: false,
        error: "corpus_failed", message: "The corpus refused.", notBefore: null,
        createdAt: "2026-09-17T00:00:00.000Z", startedAt: null,
        finishedAt: "2026-09-17T00:05:00.000Z"
      }
    }));
    render(<ActivitySettings snapshot={null} onNotify={vi.fn()} />);
    expect(await screen.findByText(/· failed: The corpus refused\./)).toBeInTheDocument();
  });

  it("says when the server could not be reached", async () => {
    vi.spyOn(backendSession, "scheduleSettings")
      .mockRejectedValue(new AcervoApiError("offline", 0, "offline"));
    render(<ActivitySettings snapshot={null} onNotify={vi.fn()} />);
    expect(await screen.findByText("offline")).toBeInTheDocument();
  });
});
