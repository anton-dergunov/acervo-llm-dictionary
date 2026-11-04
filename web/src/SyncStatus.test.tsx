import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SyncChip, SyncPanel } from "./SyncStatus";
import type { SyncStatus as Status } from "./sync";

const status = (changes: Partial<Status> = {}): Status => ({
  state: "idle", cursor: 41, lastPulledAt: new Date().toISOString(),
  lastWroteAt: null, persistent: true, message: null, ...changes
});

describe("the sync chip", () => {
  it("names the state it is in, so the icon is never the only signal", () => {
    render(<SyncChip status={status()} onOpen={() => {}} />);
    expect(screen.getByRole("button", { name: /Up to date/ })).toBeInTheDocument();
  });

  it("says offline rather than failed, because offline is normal here", () => {
    render(<SyncChip status={status({ state: "offline" })} onOpen={() => {}} />);
    expect(screen.getByRole("button", { name: /Offline/ })).toBeInTheDocument();
  });

  it("opens the panel when clicked", () => {
    const open = vi.fn();
    render(<SyncChip status={status()} onOpen={open} />);
    fireEvent.click(screen.getByRole("button"));
    expect(open).toHaveBeenCalledOnce();
  });
});

describe("the sync panel", () => {
  it("shows how current the copy is", () => {
    render(<SyncPanel status={status()} lexemeCount={12} onSyncNow={() => {}} onDownloadAgain={() => {}} />);
    expect(screen.getByText(/Received just now/)).toBeInTheDocument();
    expect(screen.getByText(/revision 41/)).toBeInTheDocument();
  });

  it("warns when the replica is only held in memory", () => {
    render(<SyncPanel status={status({ persistent: false })} lexemeCount={12} onSyncNow={() => {}} onDownloadAgain={() => {}} />);
    expect(screen.getByText(/held only until you reload/)).toBeInTheDocument();
  });

  it("does not offer a retry that cannot work while the app must be updated", () => {
    render(<SyncPanel status={status({ state: "blocked", message: "Update the app." })}
      lexemeCount={12} onSyncNow={() => {}} onDownloadAgain={() => {}} />);
    expect(screen.getByRole("button", { name: "Sync now" })).toBeDisabled();
  });

  it("explains a changed server database without offering to act blindly", () => {
    render(<SyncPanel status={status({ state: "datasetChanged" })} lexemeCount={12} onSyncNow={() => {}} onDownloadAgain={() => {}} />);
    expect(screen.getByRole("status")).toHaveTextContent(/may be the more complete one/);
    expect(screen.getByRole("button", { name: "Sync now" })).toBeDisabled();
  });

  it("replaces the local copy on a plain confirmation when nothing can be lost", () => {
    const download = vi.fn();
    render(<SyncPanel status={status()} lexemeCount={12} onSyncNow={() => {}} onDownloadAgain={download} />);
    fireEvent.click(screen.getByRole("button", { name: /Replace this device's copy with the server's/ }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Nothing is lost/);
    expect(screen.queryByLabelText(/Type REPLACE/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Replace this device's copy" }));
    expect(download).toHaveBeenCalledOnce();
  });

  it("makes the same action typed and explicit once the local copy may be the better one", () => {
    const download = vi.fn();
    render(<SyncPanel status={status({ state: "datasetChanged" })} lexemeCount={12}
      onSyncNow={() => {}} onDownloadAgain={download} />);
    fireEvent.click(screen.getByRole("button", { name: /Replace this device's copy with the server's/ }));
    expect(screen.getByText(/Nothing here can be recovered/)).toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: "Replace this device's copy" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Type REPLACE/), { target: { value: "replace please" } });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Type REPLACE/), { target: { value: "REPLACE" } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(download).toHaveBeenCalledOnce();
  });
});
