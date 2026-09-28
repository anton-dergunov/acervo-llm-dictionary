import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type ScheduleSettings } from "./api";
import SchedulePanel from "./SchedulePanel";

const settings = (over: Partial<ScheduleSettings> = {}): ScheduleSettings => ({
  hour: 2, steps: { "corpus.update": true }, chosen: false,
  timezone: "Europe/Madrid", nextRunAt: "2026-09-18T00:00:00.000Z",
  lastRun: null, ...over
});

afterEach(() => { vi.restoreAllMocks(); });

describe("Settings ▸ Schedule", () => {
  it("shows the hour in the server's zone, and saves a new one", async () => {
    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue(settings());
    const saved = vi.spyOn(backendSession, "saveScheduleSettings")
      .mockResolvedValue(settings({ hour: 5, chosen: true }));
    render(<SchedulePanel onNotify={vi.fn()} />);

    expect(await screen.findByDisplayValue("02:00")).toBeInTheDocument();
    expect(screen.getByText(/Europe\/Madrid/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Run at"), { target: { value: "5" } });
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ hour: 5 }));
  });

  it("switches a step", async () => {
    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue(settings());
    const saved = vi.spyOn(backendSession, "saveScheduleSettings").mockResolvedValue(settings());
    render(<SchedulePanel onNotify={vi.fn()} />);

    fireEvent.click(await screen.findByRole("checkbox", { name: /Update recorded speech/ }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith({ steps: { "corpus.update": false } }));
  });

  it("says how the last run went, and when nothing has run", async () => {
    vi.spyOn(backendSession, "scheduleSettings").mockResolvedValue(settings());
    const { rerender } = render(<SchedulePanel onNotify={vi.fn()} />);
    expect(await screen.findByText("It has not run yet.")).toBeInTheDocument();

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
    rerender(<SchedulePanel key="again" onNotify={vi.fn()} />);
    expect(await screen.findByText(/Nightly run — failed/)).toBeInTheDocument();
    expect(screen.getByText(/The corpus refused\./)).toBeInTheDocument();
  });

  it("says when the server could not be reached", async () => {
    vi.spyOn(backendSession, "scheduleSettings")
      .mockRejectedValue(new AcervoApiError("offline", 0, "offline"));
    render(<SchedulePanel onNotify={vi.fn()} />);
    expect(await screen.findByText("offline")).toBeInTheDocument();
  });
});
