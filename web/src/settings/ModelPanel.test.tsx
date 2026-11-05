import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type ModelCatalogue, type ModelPair } from "../api";
import ModelPanel from "./ModelPanel";
import { SubPageContext } from "./kit";

const GEMINI = "gemini/gemini-3.1-flash-lite";
const GEMINI_SECOND = "gemini/gemini-3.5-flash-lite";
const CLOUDFLARE = "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const WAVENET = "Wavenet";
const GEMINI_VOICE = "gemini-3.1-flash-tts-preview";

const pair = (provider: string, model: string): ModelPair => ({ provider, model });

const ids = (...models: string[]) => models.map((id) => ({ id }));

function catalogue(overrides: Partial<ModelCatalogue> = {}): ModelCatalogue {
  return {
    families: [],
    providers: [
      {
        id: "gemini-api", family: "gemini-api", label: "Gemini API", kinds: ["text"],
        models: { text: ids(GEMINI, GEMINI_SECOND) }, extra: {}, settings: {},
        available: true, reason: null, usageUrl: "https://aistudio.google.com/rate-limit",
        credential: { kind: "key", hint: "AIza…mnop", account: null },
        check: { ok: true, said: "Works · 52 models", at: "2026-11-05T14:02:00.000Z" }
      },
      {
        id: "cloudflare", family: "cloudflare", label: "Cloudflare", kinds: ["text"],
        models: { text: ids(CLOUDFLARE) }, extra: {}, settings: { accountId: "abc" },
        available: false, reason: "Cloudflare refused its key when it was last checked",
        usageUrl: "https://dash.cloudflare.com/abc/ai/workers-ai",
        credential: { kind: "key", hint: "Xb3d…k2Lm", account: null },
        check: { ok: false, said: "Cloudflare refused this key", at: "2026-11-05T09:15:00.000Z" }
      },
      {
        id: "google-cloud", family: "google-cloud", label: "Google Cloud", kinds: ["audio"],
        models: { audio: [{ id: WAVENET }, { id: GEMINI_VOICE, direction: true }] }, extra: {},
        settings: {}, available: true, reason: null, usageUrl: null,
        credential: { kind: "key", hint: "AIza…7tPe", account: null }, check: null
      }
    ],
    chains: {
      text: { source: "default", reason: null, pairs: [pair("gemini-api", GEMINI)] },
      image: { source: "default", reason: null, pairs: [] },
      audioPlain: { source: "default", reason: null, pairs: [] },
      audioExpressive: { source: "default", reason: null, pairs: [] }
    },
    ...overrides
  };
}

function panel() {
  return render(<ModelPanel onNotify={() => {}} />);
}

const rowOf = (element: HTMLElement): HTMLElement => element.closest(".model-row") as HTMLElement;

describe("the Providers pane", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists every model a provider offers, because the choice is a pair and not a provider", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    // Gemini's two free-tier models are separate 500-a-day buckets, so both must be selectable.
    expect(await screen.findByText(GEMINI)).toBeInTheDocument();
    expect(screen.getByText(GEMINI_SECOND)).toBeInTheDocument();
  });

  it("says the server's own order is in force until something is chosen", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    expect(await screen.findAllByText(/own order is in force/i)).not.toHaveLength(0);
  });

  it("renders an unavailable provider with its reason instead of hiding it", async () => {
    /* It keeps its place in a saved order and is skipped when the chain is walked, so hiding it
       would make the order the owner saved unexplainable. */
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    expect(row).toHaveClass("unavailable");
    expect(within(row).getByText(/Cloudflare refused its key when it was last checked/)).toBeInTheDocument();
  });

  it("shows the server's own order as switched on, because it is what will actually be asked", async () => {
    /* The bug this replaces: under the deployment default every box rendered unticked, so unticking
       the last model looked like switching capture off while the server carried on building entries
       with the model at the head of its own order. */
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    expect(within(rowOf(await screen.findByText(GEMINI))).getByRole("switch")).toBeChecked();
    expect(screen.getByText(/own order is in force/i)).toBeInTheDocument();
  });

  it("lets an unavailable pair be switched on, because a rotated key must not lock the owner out", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    fireEvent.click(within(row).getByRole("switch"));
    // Adding to the inherited order, which is what was on screen — not replacing it.
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-api", GEMINI), pair("cloudflare", CLOUDFLARE)]
    }));
  });

  it("changing anything makes the inherited order yours, in one write naming one kind", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("switch"));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-api", GEMINI), pair("gemini-api", GEMINI_SECOND)]
    });
  });

  it("marks an unavailable row with a badge and not only with dimmed text", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    expect(within(row).getByText(/unavailable/i)).toBeInTheDocument();
  });

  it("switching the last one off switches the kind off, rather than bouncing back", async () => {
    /* Most of Acervo works without a model, so "generate nothing" is a real answer. Refusing it
       made the server's own models reappear ticked, which read as the tick being ignored while
       entries carried on being built by them. */
    const chosen = catalogue({
      chains: {
        text: { source: "owner", reason: null, pairs: [pair("gemini-api", GEMINI)] },
        image: { source: "default", reason: null, pairs: [] },
        audioPlain: { source: "default", reason: null, pairs: [] },
        audioExpressive: { source: "default", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(chosen);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(chosen);
    panel();
    const row = rowOf(await screen.findByText(GEMINI));
    fireEvent.click(within(row).getByRole("switch"));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ text: [] }));
  });

  it("says a switched-off kind is off, and that the rest of Acervo is not", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue({
      chains: {
        text: { source: "owner", reason: "no model is switched on for text", pairs: [] },
        image: { source: "default", reason: null, pairs: [] },
        audioPlain: { source: "default", reason: null, pairs: [] },
        audioExpressive: { source: "default", reason: null, pairs: [] }
      }
    }));
    panel();
    expect(await screen.findByText(/Switched off/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing here is generated/i)).toBeInTheDocument();
  });

  it("offers a way back to the server's order, which no arrangement of tick boxes could mean", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue({
      chains: {
        text: { source: "owner", reason: null, pairs: [pair("gemini-api", GEMINI)] },
        image: { source: "default", reason: null, pairs: [] },
        audioPlain: { source: "default", reason: null, pairs: [] },
        audioExpressive: { source: "default", reason: null, pairs: [] }
      }
    }));
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    fireEvent.click((await screen.findAllByRole("button", { name: /Use this server/i }))[0]);
    await waitFor(() => expect(save).toHaveBeenCalledWith({ text: null }));
  });

  it("reorders a chosen pair with the arrows", async () => {
    const chosen = catalogue({
      chains: {
        text: {
          source: "owner", reason: null,
          pairs: [pair("gemini-api", GEMINI), pair("gemini-api", GEMINI_SECOND)]
        },
        image: { source: "default", reason: null, pairs: [] },
        audioPlain: { source: "default", reason: null, pairs: [] },
        audioExpressive: { source: "default", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(chosen);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(chosen);
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("button", { name: /up$/i }));
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-api", GEMINI_SECOND), pair("gemini-api", GEMINI)]
    }));
  });

  it("cannot move a pair that is switched off", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    // Cloudflare is not in the server's order, so it has no place to move within.
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    expect(within(row).getByRole("button", { name: /up$/i })).toBeDisabled();
    expect(within(row).getByRole("button", { name: /down$/i })).toBeDisabled();
  });

  it("shows what the server answered rather than what was clicked", async () => {
    const after = catalogue({
      chains: {
        text: { source: "owner", reason: null, pairs: [pair("gemini-api", GEMINI_SECOND)] },
        image: { source: "default", reason: null, pairs: [] },
        audioPlain: { source: "default", reason: null, pairs: [] },
        audioExpressive: { source: "default", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(after);
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("switch"));
    await waitFor(() =>
      expect(within(rowOf(screen.getByText(GEMINI_SECOND))).getByRole("switch")).toBeChecked());
  });

  it("fails loudly and leaves the shown order alone when the server refuses", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "saveModelSelection").mockRejectedValue(new Error("That is not a model."));
    const notified = vi.fn();
    render(<ModelPanel onNotify={notified} />);
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("switch"));
    await waitFor(() => expect(notified).toHaveBeenCalledWith("That is not a model."));
    expect(within(rowOf(screen.getByText(GEMINI_SECOND))).getByRole("switch")).not.toBeChecked();
  });

  it("says so plainly when the server cannot be reached", async () => {
    vi.spyOn(backendSession, "fetchModels").mockRejectedValue(new Error("offline"));
    panel();
    expect(await screen.findByText(/could not be reached/i)).toBeInTheDocument();
  });
});

describe("the provider list", () => {
  afterEach(() => vi.restoreAllMocks());

  const providerRow = async (label: string) =>
    (await within(await screen.findByRole("region", { name: "Providers" })).findByText(label)).closest("button") as HTMLElement;

  it("says what each provider offers and whether its key works", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    const gemini = await providerRow("Gemini API");
    expect(within(gemini).getByText("Text")).toBeInTheDocument();
    expect(within(gemini).getByText("Works")).toBeInTheDocument();
    const google = await providerRow("Google Cloud");
    expect(within(google).getByText("Voices")).toBeInTheDocument();
  });

  it("says a refused key was refused, at the top and on its row, with the way to fix it", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue({
      providers: catalogue().providers.map((one) => one.id === "cloudflare"
        ? { ...one, check: { ...one.check!, reason: "authentication" } } : one)
    }));
    const opened = vi.fn();
    render(<SubPageContext.Provider value={{ sub: null, open: opened, close() {} }}>
      <ModelPanel onNotify={() => {}} />
    </SubPageContext.Provider>);
    expect(await screen.findByText(/Cloudflare refused its key, so nothing is sent to it/)).toBeInTheDocument();
    expect(within(await providerRow("Cloudflare")).getByText("Key refused")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Replace the key" }));
    expect(opened).toHaveBeenCalledWith(expect.objectContaining({ title: "Cloudflare" }));
  });

  it("asks for a first provider when there is none, and every order says nothing offers it", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue({ providers: [] }));
    panel();
    expect(await screen.findByText(/This server has no provider yet/)).toBeInTheDocument();
    const text = await screen.findByRole("region", { name: "Text" });
    expect(within(text).getByText("Nothing offers this yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a provider…" })).toBeInTheDocument();
  });
});

describe("the orders", () => {
  afterEach(() => vi.restoreAllMocks());

  it("leaves a saved pair no provider offers out of the next save, which would be refused", async () => {
    const saved = catalogue({ chains: {
      ...catalogue().chains,
      audioPlain: { source: "owner", reason: null, pairs: [
        pair("gemini-api", "gemini/retired-tts"), pair("google-cloud", WAVENET)
      ] }
    } });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(saved);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(saved);
    panel();
    const plain = await screen.findByRole("region", { name: "Clear voice" });
    expect(within(plain).queryByText("gemini/retired-tts")).toBeNull();
    fireEvent.click(within(rowOf(within(plain).getByText(GEMINI_VOICE))).getByRole("switch"));
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      audioPlain: [pair("google-cloud", WAVENET), pair("google-cloud", GEMINI_VOICE)]
    }));
  });

  describe("the voice that takes a direction", () => {
    const section = (label: string) => screen.findByRole("region", { name: label });

    it("offers only voices that take one, and says why", async () => {
      vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
      panel();
      const expressive = await section("Expressive voice");
      expect(within(expressive).getByText(GEMINI_VOICE)).toBeInTheDocument();
      expect(within(expressive).queryByText(WAVENET)).toBeNull();
      expect(within(expressive).getByText(/Only voices that take a direction are listed/)).toBeInTheDocument();
      // The clear order is any voice: none of them is asked for a direction there.
      const plain = await section("Clear voice");
      expect(within(plain).getByText(WAVENET)).toBeInTheDocument();
      expect(within(plain).getByText(GEMINI_VOICE)).toBeInTheDocument();
    });

    it("keeps a saved voice that cannot take one out of sight, and out of the next save", async () => {
      const saved = catalogue({ chains: {
        ...catalogue().chains,
        audioExpressive: { source: "owner", reason: null, pairs: [pair("google-cloud", WAVENET)] }
      } });
      vi.spyOn(backendSession, "fetchModels").mockResolvedValue(saved);
      const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(saved);
      panel();
      const expressive = await section("Expressive voice");
      expect(within(expressive).getByText(/Nothing chosen takes a direction/)).toBeInTheDocument();
      fireEvent.click(within(rowOf(within(expressive).getByText(GEMINI_VOICE))).getByRole("switch"));
      await waitFor(() => expect(save).toHaveBeenCalledWith({
        audioExpressive: [pair("google-cloud", GEMINI_VOICE)]
      }));
    });
  });
});
