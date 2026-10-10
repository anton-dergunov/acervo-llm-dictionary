import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession, type ModelCatalogue, type ModelPair } from "./api";
import ModelPanel from "./ModelPanel";

const GEMINI = "gemini/gemini-3.1-flash-lite";
const GEMINI_SECOND = "gemini/gemini-3.5-flash-lite";
const CLOUDFLARE = "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const WAVENET = "wavenet";
const GEMINI_VOICE = "gemini-3.1-flash-tts-preview";

const pair = (provider: string, model: string): ModelPair => ({ provider, model });

function catalogue(overrides: Partial<ModelCatalogue> = {}): ModelCatalogue {
  return {
    providers: [
      {
        id: "gemini-free", label: "Gemini (free tier)", kinds: ["text"],
        models: { text: [GEMINI, GEMINI_SECOND] }, styles: {},
        available: true, reason: null,
        usageUrl: "https://aistudio.google.com/rate-limit", notes: "500 a day at no cost.",
        credential: {
          kind: "key", variable: "GEMINI_API_KEY", present: true, hint: "AIza…mnop"
        },
        settings: []
      },
      {
        id: "cloudflare", label: "Cloudflare Workers AI", kinds: ["text"],
        models: { text: [CLOUDFLARE] },
        available: false, reason: "CLOUDFLARE_API_TOKEN is not set",
        usageUrl: "https://dash.cloudflare.com/abc/ai/workers-ai", notes: null,
        credential: {
          kind: "key", variable: "CLOUDFLARE_API_TOKEN", present: false, hint: null
        },
        settings: [{ name: "CLOUDFLARE_ACCOUNT_ID", value: "abc" }]
      },
      {
        id: "google-tts", label: "Google Cloud Text-to-Speech", kinds: ["audio"],
        models: { audio: [WAVENET, GEMINI_VOICE] },
        styles: { [WAVENET]: "none", [GEMINI_VOICE]: "instruction" },
        available: true, reason: null, usageUrl: null, notes: null, settings: []
      }
    ],
    chains: {
      text: { source: "deployment", reason: null, pairs: [pair("gemini-free", GEMINI)] },
      image: { source: "deployment", reason: null, pairs: [] },
      audioPlain: { source: "deployment", reason: null, pairs: [] },
      audioExpressive: { source: "deployment", reason: null, pairs: [] }
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
    expect(within(row).getByText(/CLOUDFLARE_API_TOKEN is not set/)).toBeInTheDocument();
  });

  it("shows the server's own order as switched on, because it is what will actually be asked", async () => {
    /* The bug this replaces: under the deployment default every box rendered unticked, so unticking
       the last model looked like switching capture off while the server carried on building entries
       with the model at the head of its own order. */
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    expect(within(rowOf(await screen.findByText(GEMINI))).getByRole("checkbox")).toBeChecked();
    expect(screen.getByText(/own order is in force/i)).toBeInTheDocument();
  });

  it("lets an unavailable pair be switched on, because a rotated key must not lock the owner out", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(CLOUDFLARE));
    fireEvent.click(within(row).getByRole("checkbox"));
    // Adding to the inherited order, which is what was on screen — not replacing it.
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-free", GEMINI), pair("cloudflare", CLOUDFLARE)]
    }));
  });

  it("changing anything makes the inherited order yours, in one write naming one kind", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(catalogue());
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-free", GEMINI), pair("gemini-free", GEMINI_SECOND)]
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
        text: { source: "owner", reason: null, pairs: [pair("gemini-free", GEMINI)] },
        image: { source: "deployment", reason: null, pairs: [] },
        audioPlain: { source: "deployment", reason: null, pairs: [] },
        audioExpressive: { source: "deployment", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(chosen);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(chosen);
    panel();
    const row = rowOf(await screen.findByText(GEMINI));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ text: [] }));
  });

  it("says a switched-off kind is off, and that the rest of Acervo is not", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue({
      chains: {
        text: { source: "owner", reason: "no model is switched on for text", pairs: [] },
        image: { source: "deployment", reason: null, pairs: [] },
        audioPlain: { source: "deployment", reason: null, pairs: [] },
        audioExpressive: { source: "deployment", reason: null, pairs: [] }
      }
    }));
    panel();
    expect(await screen.findByText(/Switched off/i)).toBeInTheDocument();
    expect(screen.getByText(/rest of Acervo works as usual/i)).toBeInTheDocument();
  });

  it("offers a way back to the server's order, which no arrangement of tick boxes could mean", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue({
      chains: {
        text: { source: "owner", reason: null, pairs: [pair("gemini-free", GEMINI)] },
        image: { source: "deployment", reason: null, pairs: [] },
        audioPlain: { source: "deployment", reason: null, pairs: [] },
        audioExpressive: { source: "deployment", reason: null, pairs: [] }
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
          pairs: [pair("gemini-free", GEMINI), pair("gemini-free", GEMINI_SECOND)]
        },
        image: { source: "deployment", reason: null, pairs: [] },
        audioPlain: { source: "deployment", reason: null, pairs: [] },
        audioExpressive: { source: "deployment", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(chosen);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(chosen);
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("button", { name: /up$/i }));
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      text: [pair("gemini-free", GEMINI_SECOND), pair("gemini-free", GEMINI)]
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
        text: { source: "owner", reason: null, pairs: [pair("gemini-free", GEMINI_SECOND)] },
        image: { source: "deployment", reason: null, pairs: [] },
        audioPlain: { source: "deployment", reason: null, pairs: [] },
        audioExpressive: { source: "deployment", reason: null, pairs: [] }
      }
    });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(after);
    panel();
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() =>
      expect(within(rowOf(screen.getByText(GEMINI_SECOND))).getByRole("checkbox")).toBeChecked());
  });

  it("fails loudly and leaves the shown order alone when the server refuses", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "saveModelSelection").mockRejectedValue(new Error("That is not a model."));
    const notified = vi.fn();
    render(<ModelPanel onNotify={notified} />);
    const row = rowOf(await screen.findByText(GEMINI_SECOND));
    fireEvent.click(within(row).getByRole("checkbox"));
    await waitFor(() => expect(notified).toHaveBeenCalledWith("That is not a model."));
    expect(within(rowOf(screen.getByText(GEMINI_SECOND))).getByRole("checkbox")).not.toBeChecked();
  });

  it("says the picture and pronunciation orders are kept but not yet read", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    expect(await screen.findByText(/Nothing reads this order yet — the job that draws them/i))
      .toBeInTheDocument();
  });

  it("links out to each provider's own usage page", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();
    const link = await screen.findByRole("link", { name: /Gemini \(free tier\) usage/i });
    expect(link).toHaveAttribute("href", "https://aistudio.google.com/rate-limit");
  });

  it("says so plainly when the server cannot be reached", async () => {
    vi.spyOn(backendSession, "fetchModels").mockRejectedValue(new Error("offline"));
    panel();
    expect(await screen.findByText(/could not be reached/i)).toBeInTheDocument();
  });
});

/** The provider's row in the credentials table — its label also appears on every chain row. */
async function credentialLine(label: string): Promise<HTMLElement> {
  const table = await screen.findByTestId("provider-table");
  return within(table).getByText(label).closest(".provider-line") as HTMLElement;
}

describe("the credentials table", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows which key is deployed without showing the key", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();

    const line = await credentialLine("Gemini (free tier)");
    expect(within(line).getByText("GEMINI_API_KEY")).toBeTruthy();
    expect(within(line).getByText("AIza…mnop")).toBeTruthy();
  });

  it("names the variable a provider is waiting for rather than leaving a blank", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    panel();

    const line = await credentialLine("Cloudflare Workers AI");
    expect(within(line).getByText("CLOUDFLARE_API_TOKEN not set")).toBeTruthy();
    // The deployment fact stays visible: the account id is what the usage link is built from, and
    // it is how you tell one Cloudflare account from another.
    expect(within(line).getByText("abc")).toBeTruthy();
  });

  it("names the account for the one credential that is a file", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue({
      providers: [{
        id: "vertex", label: "Vertex AI", kinds: ["text"],
        models: { text: ["vertex_ai/gemini-3.8-flash"] },
        available: true, reason: null, usageUrl: null, notes: null,
        account: "acervo-vertex@PROJECT_ID.iam.gserviceaccount.com",
        credential: {
          kind: "file", variable: "GOOGLE_APPLICATION_CREDENTIALS", present: true, hint: null
        },
        settings: [{ name: "ACERVO_VERTEX_PROJECT", value: "a-project" }]
      }]
    }));
    panel();

    const shown = await credentialLine("Vertex AI");
    expect(within(shown).getByText("a credentials file")).toBeTruthy();
    expect(within(shown).getByText("acervo-vertex@PROJECT_ID.iam.gserviceaccount.com")).toBeTruthy();
    expect(within(shown).getByText("a-project")).toBeTruthy();
  });

  it("leaves a saved pair the catalogue has withdrawn out of the next save, which would be refused", async () => {
    const saved = catalogue({ chains: {
      ...catalogue().chains,
      audioPlain: { source: "owner", reason: null, pairs: [
        pair("gemini-free", "gemini/retired-tts"), pair("google-tts", WAVENET)
      ] }
    } });
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(saved);
    const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(saved);
    panel();
    const plain = (await screen.findByRole("heading", { name: /a clear, even voice/ }))
      .closest(".model-kind") as HTMLElement;
    expect(within(plain).queryByText("gemini/retired-tts")).toBeNull();
    fireEvent.click(within(rowOf(within(plain).getByText(GEMINI_VOICE))).getByRole("checkbox"));
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      audioPlain: [pair("google-tts", WAVENET), pair("google-tts", GEMINI_VOICE)]
    }));
  });

  describe("the voice that takes a direction", () => {
    const section = async (label: RegExp) =>
      (await screen.findByRole("heading", { name: label })).closest(".model-kind") as HTMLElement;

    it("offers only voices that take one, and says why", async () => {
      vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
      panel();
      const expressive = await section(/a voice that takes a direction/);
      expect(within(expressive).getByText(GEMINI_VOICE)).toBeInTheDocument();
      expect(within(expressive).queryByText(WAVENET)).toBeNull();
      expect(within(expressive).getByText(/Only voices that take a direction are listed/)).toBeInTheDocument();
      // The clear order is any voice: none of them is asked for a direction there.
      const plain = await section(/a clear, even voice/);
      expect(within(plain).getByText(WAVENET)).toBeInTheDocument();
      expect(within(plain).getByText(GEMINI_VOICE)).toBeInTheDocument();
    });

    it("keeps a saved voice that cannot take one out of sight, and out of the next save", async () => {
      const saved = catalogue({ chains: {
        ...catalogue().chains,
        audioExpressive: { source: "owner", reason: null, pairs: [pair("google-tts", WAVENET)] }
      } });
      vi.spyOn(backendSession, "fetchModels").mockResolvedValue(saved);
      const save = vi.spyOn(backendSession, "saveModelSelection").mockResolvedValue(saved);
      panel();
      const expressive = await section(/a voice that takes a direction/);
      expect(within(expressive).getByText(/Nothing you chose here takes a direction/)).toBeInTheDocument();
      fireEvent.click(within(rowOf(within(expressive).getByText(GEMINI_VOICE))).getByRole("checkbox"));
      await waitFor(() => expect(save).toHaveBeenCalledWith({
        audioExpressive: [pair("google-tts", GEMINI_VOICE)]
      }));
    });
  });
});
