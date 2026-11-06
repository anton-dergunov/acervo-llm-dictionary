import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  backendSession, type ModelCatalogue, type ModelProvider, type UsageCounts, type UsageModel, type UsageReadout
} from "../api";
import { SubPageContext, type SubPage } from "./kit";
import ModelPanel from "./ModelPanel";

const GEMINI: ModelProvider = {
  id: "gemini-api", family: "gemini-api", label: "Gemini API", kinds: ["text", "audio"],
  models: {
    text: [{ id: "gemini-3.5-flash-lite", allowance: { amount: 500, unit: "calls", per: "day" } }, { id: "gemini-3.1-flash-lite" }],
    audio: [{ id: "gemini-3.8-flash-tts", direction: true, allowance: { amount: 10, unit: "calls", per: "day" } }]
  },
  extra: {}, settings: {}, available: true, reason: null, usageUrl: "https://aistudio.google.com/rate-limit",
  credential: { kind: "key", hint: "AIza…mnop", account: null },
  check: { ok: true, said: "Works", reason: null, at: null }
};
const CLOUDFLARE: ModelProvider = {
  ...GEMINI, id: "cloudflare", family: "cloudflare", label: "Cloudflare", kinds: ["image"], usageUrl: null,
  models: { image: [{ id: "flux-2-klein-4b" }] }
};

function catalogue(providers: ModelProvider[] = [GEMINI, CLOUDFLARE]): ModelCatalogue {
  return {
    families: [], providers,
    chains: Object.fromEntries(["text", "quick", "image", "audioPlain", "audioExpressive", "ocr"]
      .map((kind) => [kind, { source: "default" as const, reason: null, pairs: [] }]))
  };
}

const counts = (overrides: Partial<UsageCounts> = {}): UsageCounts => ({
  calls: 0, failed: 0, inputTokens: 0, outputTokens: 0, characters: 0, pictures: 0, photos: 0, costUsd: null, ...overrides
});

const DAYS = Array.from({ length: 30 }, (_, index) => {
  const day = new Date(Date.UTC(2026, 10, 6 - (29 - index))).toISOString().slice(0, 10);
  return { day, succeeded: index === 29 ? 7 : index % 3, failed: index === 29 ? 2 : 0 };
});

const model = (overrides: Partial<UsageModel> & Pick<UsageModel, "model" | "kind">): UsageModel => ({
  offered: true, allowance: null, gauge: null, today: counts(), month: counts(), all: counts(), window: counts(),
  days: DAYS, failures: {}, seconds: null, lastFailure: null, ...overrides
});

const TTS = model({
  model: "gemini-3.8-flash-tts", kind: "audio",
  allowance: { amount: 10, unit: "calls", per: "day" }, gauge: { amount: 10, unit: "calls", per: "day", used: 9 },
  today: counts({ calls: 9, failed: 2, characters: 1400 }), month: counts({ calls: 40, failed: 3, characters: 6000 }),
  all: counts({ calls: 214, failed: 19, characters: 31000 }), window: counts({ calls: 214, failed: 19, characters: 31000 }),
  failures: { rate_limited: 17, unreachable: 2 }, seconds: 2.4,
  lastFailure: { said: "Quota exceeded for today, retry after 00:00 UTC", reason: "rate_limited", at: "2026-11-06T11:42:00.000Z" }
});

const READOUT: UsageReadout = {
  day: "2026-11-06",
  totals: {
    today: counts({ calls: 142, failed: 3, inputTokens: 1_000_000, outputTokens: 200_000, pictures: 18, characters: 1400 }),
    month: counts({ calls: 900 }), all: counts({ calls: 4000 })
  },
  providers: [
    { id: "gemini-api", label: "Gemini API", present: true, models: [
      model({ model: "gemini-3.5-flash-lite", kind: "text",
        allowance: { amount: 500, unit: "calls", per: "day" }, gauge: { amount: 500, unit: "calls", per: "day", used: 96 },
        today: counts({ calls: 96, inputTokens: 900_000, outputTokens: 80_000 }), month: counts({ calls: 800 }) }),
      TTS
    ] },
    { id: "cloudflare", label: "Cloudflare", present: true, models: [
      model({ model: "flux-2-klein-4b", kind: "image", today: counts({ calls: 19, failed: 1, pictures: 18 }) })
    ] },
    { id: "groq", label: "groq", present: false, models: [
      model({ model: "llama-3.3-70b-versatile", kind: "text", offered: false, all: counts({ calls: 12 }) })
    ] }
  ]
};

function Window({ start = null }: { start?: SubPage | null }) {
  const [sub, setSub] = useState<SubPage | null>(start);
  return <SubPageContext.Provider value={{ sub, open: setSub, close: () => setSub(null) }}>
    <h3 data-testid="title">{sub?.title ?? "Providers"}</h3>
    {sub && <button type="button" onClick={() => setSub(sub.parent ?? null)}>Back</button>}
    <ModelPanel onNotify={notified} />
  </SubPageContext.Provider>;
}

const notified = vi.fn();
const title = () => screen.getByTestId("title").textContent;

function serve(readout: UsageReadout = READOUT, providers?: ModelProvider[]) {
  vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue(providers));
  return vi.spyOn(backendSession, "usage").mockResolvedValue(readout);
}

async function openUsage() {
  render(<Window />);
  fireEvent.click(await screen.findByText("Today: 142 calls · 3 failed"));
  expect(title()).toBe("Usage");
}

describe("Usage", () => {
  afterEach(() => { vi.restoreAllMocks(); notified.mockReset(); });

  it("says today's calls on Providers, and how much of each pair's allowance is gone", async () => {
    serve();
    render(<Window />);
    expect(await screen.findByText("Today: 142 calls · 3 failed")).toBeInTheDocument();
    const text = screen.getByRole("region", { name: "Text" });
    expect(await within(text).findByText("96 of 500 today")).toBeInTheDocument();
  });

  it("lists every provider's models with their counts and gauges, for the period chosen", async () => {
    serve();
    await openUsage();
    expect(screen.getByText("142")).toBeInTheDocument();
    expect(screen.getByText("1.2M")).toBeInTheDocument();
    const gemini = screen.getByRole("region", { name: "Gemini API" });
    expect(within(gemini).getByText("96 calls · 980k tokens")).toBeInTheDocument();
    expect(within(gemini).getByText("9 calls · 2 failed · 1.4k characters")).toBeInTheDocument();
    const near = within(gemini).getByRole("meter", { name: "9 of 10 today" });
    expect(near.closest(".pref-gauge")).toHaveClass("near");
    expect(within(screen.getByRole("region", { name: "Cloudflare" })).getByText("18 pictures · 1 failed")).toBeInTheDocument();
    // Nothing from a removed provider today; all time, it is still there, under its id.
    expect(screen.queryByText("llama-3.3-70b-versatile")).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: "All time" }));
    expect(screen.getByText("4k")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "groq · no longer on this server" }))
      .getByText("llama-3.3-70b-versatile")).toBeInTheDocument();
  });

  it("shows one model's thirty days, why its calls failed and the last failure's sentence", async () => {
    serve();
    await openUsage();
    fireEvent.click(screen.getByText("gemini-3.8-flash-tts"));
    expect(title()).toBe("gemini-3.8-flash-tts");
    expect(screen.getByText("Gemini API · Voices")).toBeInTheDocument();
    expect(screen.getByText("Free allowance 10 a day · answers in 2.4 s on average")).toBeInTheDocument();
    expect(screen.getByText("failed · 9%")).toBeInTheDocument();
    expect(screen.getByText("31k")).toBeInTheDocument();
    const why = screen.getByRole("region", { name: "Why calls failed" });
    expect(within(why).getByText("Allowance spent")).toBeInTheDocument();
    expect(within(why).getByText("17")).toBeInTheDocument();
    expect(within(why).getByText("Gemini API said no more for now")).toBeInTheDocument();
    expect(screen.getByText("Quota exceeded for today, retry after 00:00 UTC")).toBeInTheDocument();
    // A bar says its day in words, on focus as on hover.
    const today = screen.getByRole("generic", { name: "Today: 7 answered, 2 failed" });
    fireEvent.focus(today);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Today: 7 answered, 2 failed");
  });

  it("changes a voice's allowance on its own page", async () => {
    serve();
    vi.spyOn(backendSession, "providerVoices").mockResolvedValue({ listed: true, voices: [] });
    await openUsage();
    fireEvent.click(screen.getByText("gemini-3.8-flash-tts"));
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    expect(title()).toBe("gemini-3.8-flash-tts");
    expect(screen.getByRole("switch", { name: "Takes a direction" })).toBeChecked();
    expect(screen.getByLabelText("Amount")).toHaveValue("10");
  });

  it("sets a text model's allowance from its Usage page, and asks for the gauges again", async () => {
    const usage = serve();
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue({ ...catalogue(), provider: "gemini-api" });
    vi.spyOn(backendSession, "pronunciationSettings").mockResolvedValue({} as never);
    await openUsage();
    fireEvent.click(screen.getByText("gemini-3.5-flash-lite"));
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    expect(screen.getByRole("region", { name: "Free allowance" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Counted in"), { target: { value: "tokens" } });
    const asked = usage.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("gemini-api", { models: {
      ...GEMINI.models,
      text: [{ id: "gemini-3.5-flash-lite", allowance: { amount: 1000, unit: "tokens", per: "day" } }, GEMINI.models.text[1]]
    } }));
    // Back to the model's Usage, whose gauge is measured against the new allowance.
    await waitFor(() => expect(title()).toBe("gemini-3.5-flash-lite"));
    expect(usage.mock.calls.length).toBeGreaterThan(asked);
  });

  it("offers a picture model's allowance in pictures only", async () => {
    serve();
    await openUsage();
    fireEvent.click(screen.getByText("flux-2-klein-4b"));
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    expect(screen.queryByLabelText("Counted in")).toBeNull();
    expect(screen.getByLabelText("Each")).toHaveValue("day");
  });

  it("opens a provider's own usage from its page", async () => {
    serve();
    render(<Window />);
    fireEvent.click(await within(await screen.findByRole("region", { name: "Providers" })).findByText("Cloudflare"));
    fireEvent.click(await screen.findByText("Today: 19 calls · 1 failed"));
    expect(title()).toBe("Usage");
    expect(screen.queryByRole("region", { name: "Gemini API" })).toBeNull();
    expect(screen.getByRole("region", { name: "Cloudflare" })).toBeInTheDocument();
  });

  it("offers no Change for a model the server no longer has", async () => {
    serve();
    await openUsage();
    fireEvent.click(screen.getByRole("radio", { name: "All time" }));
    fireEvent.click(screen.getByText("llama-3.3-70b-versatile"));
    expect(screen.getByText("groq · Text")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change" })).toBeNull();
  });

  it("says when nothing has been asked", async () => {
    serve({ ...READOUT, totals: { today: counts({ calls: 0 }), month: counts(), all: counts() }, providers: [] });
    render(<Window />);
    fireEvent.click(await screen.findByText("Nothing asked today"));
    expect(screen.getByText("Nothing asked in this period")).toBeInTheDocument();
  });
});
