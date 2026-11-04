/**
 * Settings ▸ Clips: the owner's switches at once, the corpus when it answers, and the channel list
 * — a sub-page — only when it is opened.
 *
 * The catalogue is the corpus service's, so what is tested here is Acervo's presentation of it —
 * the grouping, the link, and the fact that switching a channel on is a request to that service
 * rather than anything Acervo stores.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SubPageContext, type SubPage } from "./kit";

const channels = vi.fn();
const setChannelEnabled = vi.fn(async (_language: string, _id: string, _on: boolean) => undefined);
const addChannel = vi.fn();
const clipSettings = vi.fn();
const clipCorpus = vi.fn();
const saveClipSettings = vi.fn();
const enqueueJob = vi.fn();

vi.mock("../clips", async () => {
  const actual = await vi.importActual<typeof import("../clips")>("../clips");
  return {
    ...actual, channels: () => channels(),
    setChannelEnabled: (...a: [string, string, boolean]) => setChannelEnabled(...a),
    addChannel: (channel: unknown) => addChannel(channel)
  };
});
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    backendSession: {
      ...actual.backendSession, clipSettings: () => clipSettings(),
      clipCorpus: () => clipCorpus(),
      saveClipSettings: () => saveClipSettings(),
      enqueueJob: (request: unknown) => enqueueJob(request)
    }
  };
});

const { default: ClipPanel } = await import("./ClipPanel");
const { jobStream } = await import("../jobs");

const channel = (over: Partial<Record<string, unknown>> = {}) => ({
  source_language: "es", section_id: "learning", section_name: "Language learning",
  id: "easy-spanish", name: "Easy Spanish", url: "https://www.youtube.com/@EasySpanish/videos",
  enabled: true, varieties: ["Spain", "Mexico"], speech_style: ["conversation"], description: null,
  ...over
});

/** The window's part: which sub-page is open. */
function Harness({ opened = null }: { opened?: SubPage | null }) {
  const [sub, setSub] = useState<SubPage | null>(opened);
  return <SubPageContext.Provider value={{ sub, open: setSub, close: () => setSub(null) }}>
    <ClipPanel onNotify={() => undefined} />
  </SubPageContext.Provider>;
}

function serve(corpus: Record<string, unknown> = {}) {
  clipSettings.mockResolvedValue({ searchEnabled: true, selfContainedOnly: false, chosen: false });
  clipCorpus.mockResolvedValue({
    configured: true, reachable: true, ready: true, indexedLanguages: ["es"],
    videos: 251, segments: 60704, ...corpus
  });
}

function panel(corpus: Record<string, unknown> = {}) {
  serve(corpus);
  render(<Harness />);
}

function channelPage() {
  serve();
  render(<Harness opened={{ id: "channels", title: "Channels" }} />);
}

afterEach(() => { vi.clearAllMocks(); });

describe("the page", () => {
  it("shows the switches without waiting for the corpus, which is another service", async () => {
    clipSettings.mockResolvedValue({ searchEnabled: true, selfContainedOnly: false, chosen: false });
    clipCorpus.mockImplementation(() => new Promise(() => undefined));
    render(<Harness />);
    expect(await screen.findByRole("switch", { name: "Look for clips" })).toBeChecked();
  });

  it("says plainly when the corpus does not answer, and keeps the switches", async () => {
    serve({ reachable: false, error: "timeout" });
    render(<Harness />);
    expect(await screen.findByText(/not answering \(timeout\)/)).toBeTruthy();
    expect(screen.getByRole("switch", { name: "Look for clips" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Channels/ })).toBeNull();
  });

  it("reads the channel list only when Channels is opened", async () => {
    channels.mockResolvedValue([channel()]);
    panel();
    const open = await screen.findByRole("button", { name: /Channels/ });
    expect(channels).not.toHaveBeenCalled();
    fireEvent.click(open);
    expect(await screen.findByRole("switch", { name: "Easy Spanish" })).toBeChecked();
    expect(channels).toHaveBeenCalledTimes(1);
  });
});

describe("the channel catalogue", () => {
  it("groups by language and section, and does not repeat the language on every row", async () => {
    channels.mockResolvedValue([
      channel(),
      channel({ id: "linguriosa", name: "Linguriosa", enabled: false }),
      channel({ source_language: "en", id: "bbc", name: "BBC", section_name: "News", enabled: false })
    ]);
    channelPage();

    const group = await screen.findByRole("region", { name: "Spanish · Language learning" });
    expect(screen.getByRole("region", { name: "English · News" })).toBeTruthy();
    expect(within(group).getByText("1 of 2 on")).toBeTruthy();
    // The row says the variety and the style, and nothing about the language.
    expect(within(group).getAllByText("Spain · Mexico · conversation")).toHaveLength(2);
    expect(within(group).queryByText(/\bes\b/)).toBeNull();
  });

  it("counts what is on", async () => {
    channels.mockResolvedValue([
      channel(), channel({ id: "b", name: "B", enabled: false }), channel({ id: "c", name: "C", enabled: false })
    ]);
    channelPage();
    expect(await screen.findByText("1 of 3 on")).toBeTruthy();
  });

  it("names each of the corpus's own sections", async () => {
    channels.mockResolvedValue([
      channel(),
      channel({ id: "ruina", name: "La Ruina", section_name: "Live comedy", enabled: false })
    ]);
    channelPage();
    expect(await screen.findByRole("region", { name: /Language learning/ })).toBeTruthy();
    expect(screen.getByRole("region", { name: /Live comedy/ })).toBeTruthy();
  });

  it("opens the channel itself, to watch some of it", async () => {
    channels.mockResolvedValue([channel()]);
    channelPage();
    const link = await screen.findByRole("link", { name: "Watch Easy Spanish" }) as HTMLAnchorElement;
    expect(link.href).toBe("https://www.youtube.com/@EasySpanish/videos");
    expect(link.target).toBe("_blank");
    expect(link.rel).toContain("noreferrer");
  });

  it("switches a channel through the corpus service rather than storing anything", async () => {
    channels.mockResolvedValue([channel()]);
    channelPage();
    fireEvent.click(await screen.findByRole("switch", { name: "Easy Spanish" }));
    await waitFor(() => expect(setChannelEnabled).toHaveBeenCalledWith("es", "easy-spanish", false));
  });

  it("says that a change waits for the next update, and that saved clips stay", async () => {
    channels.mockResolvedValue([channel()]);
    channelPage();
    expect(await screen.findByText(/next update\. Clips you already saved stay/)).toBeTruthy();
  });

  it("asks for one update however often Update is pressed", async () => {
    channels.mockResolvedValue([channel()]);
    const queued = {
      id: "job000000000001", ownerId: "owner0000000001", parentId: null, kind: "corpus.update",
      subject: { kind: "corpus", id: "corpus" }, input: {}, state: "running", trigger: "manual",
      steps: [], rerun: false, cancelRequested: false, dismissed: false, error: null,
      message: null, notBefore: null, createdAt: "2026-09-17T10:00:00.000Z", startedAt: null,
      finishedAt: null
    };
    enqueueJob.mockResolvedValue(queued);
    channelPage();

    fireEvent.click(await screen.findByRole("button", { name: "Update" }));
    await waitFor(() => expect(enqueueJob).toHaveBeenCalledWith({
      kind: "corpus.update", subject: { kind: "corpus", id: "corpus" }
    }));
    // While the server is updating, the button says so and cannot start a second one.
    expect(await screen.findByRole("button", { name: "Updating…" })).toBeDisabled();
    jobStream.stop();
  });

  it("adds a channel to the corpus's own catalogue", async () => {
    channels.mockResolvedValue([channel()]);
    addChannel.mockResolvedValue(channel({ id: "linguriosa", name: "Linguriosa" }));
    channelPage();

    fireEvent.click(await screen.findByRole("button", { name: "Add a channel…" }));
    const fields: [string, string][] = [
      ["Language", "es"], ["Section", "learning"], ["Identifier", "linguriosa"],
      ["Name", "Linguriosa"], ["URL", "https://www.youtube.com/@Linguriosa/videos"]
    ];
    fields.forEach(([label, value]) =>
      fireEvent.change(screen.getByLabelText(label), { target: { value } }));
    fireEvent.click(screen.getByRole("button", { name: "Add channel" }));

    await waitFor(() => expect(addChannel).toHaveBeenCalledWith({
      source_language: "es", section_id: "learning", id: "linguriosa", name: "Linguriosa",
      url: "https://www.youtube.com/@Linguriosa/videos", enabled: true
    }));
    expect(await screen.findByRole("link", { name: "Watch Linguriosa" })).toBeTruthy();
  });
});


describe("whether the player translates a clip", () => {
  /* The one part of this deployment that can go quiet without complaining. The player renders the
     same grey sentence whether no provider is credentialed, the chain names rows that container
     lacks, or a model answered badly — and there was nowhere at all to read which. */

  it("names what would answer, which is the chain rather than the row that did", async () => {
    panel({ translation: { available: true, provider: "acervo-chain", model: "gemini-free" } });
    expect(await screen.findByText("Translated in the player")).toBeTruthy();
    expect(screen.getByText("gemini-free")).toBeTruthy();
  });

  it("says so plainly when nothing is credentialed", async () => {
    panel({ translation: { available: false, provider: null, model: null } });
    expect(await screen.findByText(/Off: no model for the corpus/)).toBeTruthy();
  });

  it("says nothing at all when the corpus is too old to report it", async () => {
    panel();
    await waitFor(() => expect(screen.getByText(/251 videos/)).toBeTruthy());
    expect(screen.queryByText("Translated in the player")).toBeNull();
  });
});
