import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type ModelCatalogue, type ModelProvider, type ProviderFamily } from "../api";
import { refresh, SETTINGS } from "./cache";
import { SubPageContext, type SubPage } from "./kit";
import ModelPanel from "./ModelPanel";

const family = (overrides: Partial<ProviderFamily> & Pick<ProviderFamily, "id" | "label" | "group">): ProviderFamily => ({
  hint: "", kinds: ["text"], fileOnly: [], credential: "key", keyLabel: "API key", keyUrl: null, voicesUrl: null,
  fields: [], ...overrides
});

const FAMILIES: ProviderFamily[] = [
  family({ id: "gemini-api", label: "Gemini API", group: "Free to start", hint: "Text, with a daily free allowance",
           keyUrl: "https://aistudio.google.com/apikey" }),
  family({ id: "cloudflare", label: "Cloudflare", group: "Free to start", kinds: ["text", "image", "audio"],
           keyLabel: "API token", keyUrl: "https://dash.cloudflare.com/profile/api-tokens",
           voicesUrl: "https://developers.cloudflare.com/workers-ai/models/?tasks=Text-to-Speech",
           fields: [{ name: "accountId", label: "Account ID", needed: "always", default: null, hint: "On the Workers AI page", choices: [] }] }),
  family({ id: "google-cloud", label: "Google Cloud", group: "Popular", kinds: ["text", "image", "audio", "ocr"],
           fileOnly: ["text", "image"], credential: "key-or-file",
           ready: [{ kind: "text", id: "gemini-3.8-flash", fileOnly: true }, { kind: "image", id: "gemini-3.1-flash-lite-image", fileOnly: true },
                   { kind: "audio", id: "Wavenet", fileOnly: false }, { kind: "audio", id: "gemini-2.5-flash-tts", fileOnly: true },
                   { kind: "ocr", id: "document-text-detection", fileOnly: false }],
           fields: [
             { name: "project", label: "Project", needed: "file", default: null, hint: null, choices: [] },
             { name: "location", label: "Location", needed: "file", default: "global", hint: null, choices: ["global", "europe-west1"] }
           ] }),
  family({ id: "openai-compatible", label: "Any compatible service", group: "Any compatible service", credential: "optional" })
];

const GEMINI: ModelProvider = {
  id: "gemini-api", family: "gemini-api", label: "Gemini API", kinds: ["text"],
  models: { text: [{ id: "gemini-3.5-flash-lite", allowance: { amount: 500, unit: "calls", per: "day" } }] },
  extra: {}, settings: {}, available: true, reason: null, usageUrl: "https://aistudio.google.com/rate-limit",
  credential: { kind: "key", hint: "AIza…mnop", account: null },
  check: { ok: true, said: "Works · 52 models", reason: null, at: "2026-11-05T14:02:00.000Z" }
};
const GOOGLE: ModelProvider = {
  id: "google-cloud", family: "google-cloud", label: "Google Cloud", kinds: ["audio", "ocr"],
  models: { audio: [{ id: "Wavenet" }, { id: "gemini-2.5-flash-tts", direction: true }], ocr: [{ id: "document-text-detection" }] },
  extra: {}, settings: {}, available: true, reason: null, usageUrl: null,
  credential: { kind: "key", hint: "AIza…7tPe", account: null },
  check: { ok: true, said: "Works · Text-to-Speech answers", reason: null, at: null }
};

function catalogue(providers: ModelProvider[] = [GEMINI, GOOGLE]): ModelCatalogue {
  return {
    families: FAMILIES, providers,
    chains: Object.fromEntries(["text", "quick", "image", "audioPlain", "audioExpressive", "ocr"]
      .map((kind) => [kind, { source: "default" as const, reason: null, pairs: [] }]))
  };
}

const answer = (providers: ModelProvider[], provider: string) => ({ ...catalogue(providers), provider });

/** The window's part of a sub-page: it holds which one is open, as Settings does. */
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

async function openProvider(label: string) {
  render(<Window />);
  fireEvent.click(await within(await screen.findByRole("region", { name: "Providers" })).findByText(label));
}

describe("adding a provider", () => {
  afterEach(() => { vi.restoreAllMocks(); notified.mockReset(); });

  it("offers the server's families, grouped as the server groups them", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    render(<Window />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a provider…" }));
    expect(title()).toBe("Add a provider");
    const free = screen.getByRole("region", { name: "Free to start" });
    expect(within(free).getByText("Gemini API")).toBeInTheDocument();
    expect(within(free).getByText("Text, with a daily free allowance")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Popular" })).getByText("Google Cloud")).toBeInTheDocument();
    // A group of one named after its member needs no title of its own.
    expect(screen.queryByRole("region", { name: "Any compatible service" })).toBeNull();
    expect(screen.getByText("Any compatible service")).toBeInTheDocument();
  });

  it("checks and adds what the form says, then opens the new provider's page", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const added: ModelProvider = { ...GEMINI, id: "cloudflare", family: "cloudflare", label: "Cloudflare", kinds: [],
      models: {}, settings: { accountId: "abc" }, credential: { kind: "key", hint: "cf-t…cdef", account: null } };
    const add = vi.spyOn(backendSession, "addProvider").mockResolvedValue(answer([GEMINI, GOOGLE, added], "cloudflare"));
    const pronunciations = vi.spyOn(SETTINGS.pronunciations, "fetch").mockResolvedValue({} as never);
    render(<Window />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a provider…" }));
    fireEvent.click(screen.getByText("Cloudflare"));
    expect(screen.getByText("dash.cloudflare.com")).toHaveAttribute("href", "https://dash.cloudflare.com/profile/api-tokens");
    fireEvent.change(screen.getByLabelText("Account ID"), { target: { value: "abc" } });
    const key = screen.getByLabelText("API token");
    expect(key).toHaveAttribute("type", "password");
    fireEvent.change(key, { target: { value: "  cf-test-token-0123456789abcdef " } });
    fireEvent.click(screen.getByRole("button", { name: "Check and add" }));

    await waitFor(() => expect(title()).toBe("Cloudflare"));
    expect(add).toHaveBeenCalledWith({
      family: "cloudflare", label: "Cloudflare", settings: { accountId: "abc" }, key: "cf-test-token-0123456789abcdef"
    });
    // The new provider's page, empty: a group per kind, each with only the way to add a model.
    expect(screen.getByText("cf-t…cdef")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add a model…" })).toHaveLength(3);
    // Voices and orders on Pronunciation can change with a provider, so they are asked again.
    expect(pronunciations).toHaveBeenCalled();
  });

  it("shows a refused key on the form in the provider's words, and adds nothing", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "addProvider").mockRejectedValue(
      new AcervoApiError("Gemini API refused this key: API key not valid. Nothing was saved.", 400, "key_refused"));
    render(<Window />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a provider…" }));
    fireEvent.click(screen.getByText("Gemini API"));
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "AIza-wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Check and add" }));
    expect(await screen.findByText(/refused this key: API key not valid/)).toBeInTheDocument();
    expect(title()).toBe("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(title()).toBe("Add a provider");
  });

  it("asks Google Cloud's project and location only with a credentials file", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const add = vi.spyOn(backendSession, "addProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "google-cloud"));
    render(<Window />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a provider…" }));
    fireEvent.click(screen.getByText("Google Cloud"));
    expect(screen.queryByLabelText("Project")).toBeNull();
    expect(screen.getByText("Reaches voices and reading photos")).toBeInTheDocument();
    // The usual models a key reaches, and with the file everything.
    expect(screen.getByText("Voices and reading photos, ready to use")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Credentials file" }));
    expect(screen.getByText("Reaches text, pictures, voices and reading photos")).toBeInTheDocument();
    expect(screen.getByText("Text, pictures, voices and reading photos, ready to use")).toBeInTheDocument();
    expect(screen.queryByLabelText("API key")).toBeNull();
    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "example-project" } });
    const file = new File([JSON.stringify({ type: "service_account" })], "acervo.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("Credentials file"), { target: { files: [file] } });
    await screen.findByText("acervo.json");
    fireEvent.click(screen.getByRole("button", { name: "Check and add" }));
    await waitFor(() => expect(add).toHaveBeenCalledWith({
      family: "google-cloud", label: "Google Cloud", settings: { project: "example-project", location: "global" },
      credentials: JSON.stringify({ type: "service_account" }), ready: true
    }));
  });

  it("adds the usual models unless the switch is turned off, and offers none where a family has none", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const add = vi.spyOn(backendSession, "addProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "google-cloud"));
    render(<Window />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a provider…" }));
    fireEvent.click(screen.getByText("Gemini API"));
    expect(screen.queryByText(/Add the usual models/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(await screen.findByText("Google Cloud"));
    fireEvent.click(screen.getByRole("switch", { name: /Add the usual models/ }));
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "test-google-cloud-key-qrstuvwx" } });
    fireEvent.click(screen.getByRole("button", { name: "Check and add" }));
    await waitFor(() => expect(add).toHaveBeenCalledWith(expect.objectContaining({ ready: false })));
  });
});

describe("a credentials file the dialog cannot reach", () => {
  afterEach(() => { vi.restoreAllMocks(); notified.mockReset(); });

  async function googleFileForm() {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    render(<Window />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a provider…" }));
    fireEvent.click(screen.getByText("Google Cloud"));
    fireEvent.click(screen.getByRole("radio", { name: "Credentials file" }));
    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "example-project" } });
  }

  it("says where your own sign-in usually is", async () => {
    await googleFileForm();
    expect(screen.getByText("~/.config/gcloud/application_default_credentials.json")).toBeInTheDocument();
  });

  it("takes the file pasted, and sends it as its text", async () => {
    await googleFileForm();
    const add = vi.spyOn(backendSession, "addProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "google-cloud"));
    const file = JSON.stringify({ type: "authorized_user", client_id: "x" });
    fireEvent.click(screen.getByRole("button", { name: "Paste…" }));
    fireEvent.change(screen.getByLabelText("The credentials file’s contents"), { target: { value: file } });
    fireEvent.click(screen.getByRole("button", { name: "Use it" }));
    expect(screen.getByText("Pasted")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check and add" }));
    await waitFor(() => expect(add).toHaveBeenCalledWith(expect.objectContaining({ credentials: file })));
  });

  it("says a half-copied file is not whole, and sends nothing", async () => {
    await googleFileForm();
    const add = vi.spyOn(backendSession, "addProvider");
    fireEvent.click(screen.getByRole("button", { name: "Paste…" }));
    fireEvent.change(screen.getByLabelText("The credentials file’s contents"), { target: { value: '{ "type": "authorized_user", "cli' } });
    fireEvent.click(screen.getByRole("button", { name: "Use it" }));
    expect(screen.getByText(/That is not the whole file/)).toBeInTheDocument();
    expect(screen.queryByText("Pasted")).toBeNull();
    expect(add).not.toHaveBeenCalled();
  });

  it("replaces a stored provider's file by pasting, checked at once", async () => {
    const vertex: ModelProvider = { ...GOOGLE, credential: { kind: "file", hint: null, account: "acervo@project.example.com" },
      settings: { project: "example-project" } };
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue([vertex]));
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([vertex], "google-cloud"));
    await openProvider("Google Cloud");
    const file = JSON.stringify({ type: "service_account", client_email: "acervo@project.example.com" });
    fireEvent.click(screen.getByRole("button", { name: "Paste…" }));
    fireEvent.change(screen.getByLabelText("The credentials file’s contents"), { target: { value: file } });
    fireEvent.click(screen.getByRole("button", { name: "Use it" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("google-cloud", { credentials: file }));
  });

  it("sends a project typed but not yet saved with the replacement file, so both are checked together", async () => {
    const vertex: ModelProvider = { ...GOOGLE, credential: { kind: "file", hint: null, account: "acervo@project.example.com" },
      settings: { project: "old-project" } };
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue([vertex]));
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([vertex], "google-cloud"));
    await openProvider("Google Cloud");
    fireEvent.change(screen.getByDisplayValue("old-project"), { target: { value: "new-project" } });
    const file = JSON.stringify({ type: "authorized_user", client_id: "x", client_secret: "y", refresh_token: "z" });
    fireEvent.click(screen.getByRole("button", { name: "Paste…" }));
    fireEvent.change(screen.getByLabelText("The credentials file’s contents"), { target: { value: file } });
    fireEvent.click(screen.getByRole("button", { name: "Use it" }));
    await waitFor(() => expect(change).toHaveBeenCalledTimes(1));
    expect(change).toHaveBeenCalledWith("google-cloud",
      { credentials: file, settings: expect.objectContaining({ project: "new-project" }) });
  });
});

describe("a provider's page", () => {
  afterEach(() => { vi.restoreAllMocks(); notified.mockReset(); });

  it("shows which key is set, never the key, and what its check said", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    await openProvider("Gemini API");
    expect(title()).toBe("Gemini API");
    expect(screen.getByText("AIza…mnop")).toBeInTheDocument();
    expect(screen.getByText("Works · 52 models")).toBeInTheDocument();
    expect(screen.getByText(/Checked .*, \d\d:\d\d/)).toBeInTheDocument();
    expect(screen.getByText("500 a day free")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Gemini API’s own page/ })).toHaveAttribute("href", "https://aistudio.google.com/rate-limit");
  });

  it("checks a replacement key before it is kept, and says a refusal on the page", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const change = vi.spyOn(backendSession, "changeProvider")
      .mockRejectedValueOnce(new AcervoApiError("Gemini API refused this key. Nothing was saved.", 400, "key_refused"))
      .mockResolvedValueOnce(answer([{ ...GEMINI, credential: { kind: "key", hint: "AIzb…zzzz", account: null } }, GOOGLE], "gemini-api"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "AIzb-new-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Check and save" }));
    expect(await screen.findByText("Gemini API refused this key. Nothing was saved.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check and save" }));
    expect(await screen.findByText("AIzb…zzzz")).toBeInTheDocument();
    expect(change).toHaveBeenLastCalledWith("gemini-api", { key: "AIzb-new-key" });
  });

  it("checks again on asking, and shows what the server answered", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "checkProvider").mockResolvedValue(answer([{
      ...GEMINI, check: { ok: false, said: "Gemini API did not answer", reason: "unreachable", at: null }
    }, GOOGLE], "gemini-api"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByText("Gemini API did not answer")).toBeInTheDocument();
  });

  it("removes a model with its cross, in one write of the provider's models", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([{ ...GEMINI, models: { text: [] } }, GOOGLE], "gemini-api"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Remove gemini-3.5-flash-lite" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("gemini-api", { models: { text: [] } }));
    await waitFor(() => expect(screen.queryByText("gemini-3.5-flash-lite")).toBeNull());
  });

  it("hides what only a credentials file reaches while it signs in with a key", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    await openProvider("Google Cloud");
    expect(screen.getByRole("region", { name: "Voices" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Reading photos" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Text" })).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: "Credentials file" }));
    expect(screen.getByLabelText("Project")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose…" })).toBeInTheDocument();
  });

  it("removes a provider on the second press, and goes back to the list", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    const remove = vi.spyOn(backendSession, "removeProvider").mockResolvedValue(answer([GOOGLE], "gemini-api"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Remove this provider" }));
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove Gemini API and its key" }));
    await waitFor(() => expect(title()).toBe("Providers"));
    expect(remove).toHaveBeenCalledWith("gemini-api");
    expect(within(screen.getByRole("region", { name: "Providers" })).queryByText("Gemini API")).toBeNull();
  });
});

describe("adding a model", () => {
  afterEach(() => { vi.restoreAllMocks(); notified.mockReset(); });

  it("picks from what the provider lists, and marks what is already there", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerModels").mockResolvedValue({
      kind: "text", listed: true, models: ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.8-pro"]
    });
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "gemini-api"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Add a model…" }));
    expect(title()).toBe("Add a text model");
    const offered = await screen.findByRole("region", { name: "Gemini API offers" });
    expect(within(offered).getByText("Added")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search Gemini API’s models"), { target: { value: "pro" } });
    expect(within(offered).queryByText("gemini-3.8-flash")).toBeNull();
    fireEvent.click(within(offered).getByText("gemini-3.8-pro"));
    await waitFor(() => expect(change).toHaveBeenCalledWith("gemini-api", { models: {
      text: [GEMINI.models.text[0], { id: "gemini-3.8-pro" }]
    } }));
    expect(notified).toHaveBeenCalledWith("gemini-3.8-pro added.");
  });

  it("adds a name the list does not hold from the same box, and says the list lacks it", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerModels").mockResolvedValue({ kind: "text", listed: true, models: ["gemini-3.8-flash"] });
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "gemini-api"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Add a model…" }));
    const search = await screen.findByLabelText("Search Gemini API’s models");
    expect(screen.queryByLabelText("Model name")).toBeNull();

    fireEvent.change(search, { target: { value: "gemini-3.9-flash" } });
    // Enter does not turn a name the list lacks into a model: a half-typed search would.
    fireEvent.keyDown(search, { key: "Enter" });
    expect(change).not.toHaveBeenCalled();
    expect(screen.getByText(/Gemini API does not list it/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add “gemini-3.9-flash”" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("gemini-api", { models: {
      text: [GEMINI.models.text[0], { id: "gemini-3.9-flash" }]
    } }));
  });

  it("offers no unlisted name when what is typed is in the list, and Enter adds it", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerModels").mockResolvedValue({ kind: "text", listed: true, models: ["gemini-3.8-flash"] });
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "gemini-api"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Add a model…" }));
    const search = await screen.findByLabelText("Search Gemini API’s models");
    fireEvent.change(search, { target: { value: "gemini-3.8-flash" } });
    expect(screen.queryByRole("button", { name: /^Add “/ })).toBeNull();
    fireEvent.keyDown(search, { key: "Enter" });
    await waitFor(() => expect(change).toHaveBeenCalledWith("gemini-api", { models: {
      text: [GEMINI.models.text[0], { id: "gemini-3.8-flash" }]
    } }));
  });

  it("takes the name in the same box where the provider lists nothing", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerModels").mockResolvedValue({ kind: "audio", listed: false, models: [] });
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "google-cloud"));
    await openProvider("Google Cloud");
    fireEvent.click(within(screen.getByRole("region", { name: "Voices" })).getByRole("button", { name: "Add a model…" }));
    expect(await screen.findByText(/does not list these/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("The model’s name"), { target: { value: "gemini-3.1-flash-tts-preview" } });
    fireEvent.click(screen.getByRole("button", { name: "Add “gemini-3.1-flash-tts-preview”" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("google-cloud", { models: expect.objectContaining({
      audio: [...GOOGLE.models.audio, { id: "gemini-3.1-flash-tts-preview" }]
    }) }));
  });

  it("says in the provider's words when it cannot be asked, and still takes a name", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerModels").mockRejectedValue(
      new AcervoApiError("Gemini API did not answer: connection refused.", 502, "provider_listing_failed"));
    await openProvider("Gemini API");
    fireEvent.click(screen.getByRole("button", { name: "Add a model…" }));
    expect(await screen.findByText("Gemini API did not answer: connection refused.")).toBeInTheDocument();
    expect(screen.getByLabelText("The model’s name")).toBeInTheDocument();
  });
});

describe("a voice model's page", () => {
  afterEach(() => { vi.restoreAllMocks(); notified.mockReset(); });

  async function openVoice(model: string) {
    await openProvider("Google Cloud");
    fireEvent.click(screen.getByText(model));
  }

  it("lists the voices the provider has for it, a few first", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerVoices").mockResolvedValue({ listed: true, voices: Array.from({ length: 30 },
      (_, index) => ({ name: `Voice${index}`, gender: index % 2 ? "male" : "female" })) });
    await openVoice("gemini-2.5-flash-tts");
    expect(title()).toBe("gemini-2.5-flash-tts");
    expect(await screen.findByText("30 listed by Google Cloud")).toBeInTheDocument();
    expect(screen.queryByText("Voice10")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all 30" }));
    expect(screen.getByText("Voice29")).toBeInTheDocument();
  });

  it("says whether it takes a direction, in one write of the provider's models", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerVoices").mockResolvedValue({ listed: true, voices: [] });
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "google-cloud"));
    await openVoice("Wavenet");
    fireEvent.click(screen.getByRole("switch", { name: "Takes a direction" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("google-cloud", { models: {
      ...GOOGLE.models, audio: [{ id: "Wavenet", direction: true }, GOOGLE.models.audio[1]]
    } }));
  });

  it("keeps a free allowance only once it is saved", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerVoices").mockResolvedValue({ listed: true, voices: [] });
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "google-cloud"));
    await openVoice("Wavenet");
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "4000000" } });
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("google-cloud", { models: {
      ...GOOGLE.models,
      audio: [{ id: "Wavenet", allowance: { amount: 4000000, unit: "characters", per: "month" } }, GOOGLE.models.audio[1]]
    } }));
  });

  it("chooses the languages it speaks on their own page", async () => {
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue());
    vi.spyOn(backendSession, "providerVoices").mockResolvedValue({ listed: true, voices: [] });
    vi.spyOn(SETTINGS.languages, "fetch").mockResolvedValue({ languages: [
      { tag: "es", name: "Spanish", autonym: "español", region: "ES", varieties: [] }
    ] } as never);
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([GEMINI, GOOGLE], "google-cloud"));
    await openVoice("Wavenet");
    fireEvent.change(screen.getByLabelText("Languages"), { target: { value: "some" } });
    expect(title()).toBe("Languages");
    void refresh(SETTINGS.languages);
    fireEvent.click(await screen.findByText("Spanish"));
    await waitFor(() => expect(change).toHaveBeenCalledWith("google-cloud", { models: {
      ...GOOGLE.models, audio: [{ id: "Wavenet", languages: ["es"] }, GOOGLE.models.audio[1]]
    } }));
  });

  it("types the voices a provider cannot list, with where to find them", async () => {
    const cloudflare: ModelProvider = { ...GEMINI, id: "cloudflare", family: "cloudflare", label: "Cloudflare", kinds: ["audio"],
      models: { audio: [{ id: "@cf/deepgram/aura-1" }] }, usageUrl: null };
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue(catalogue([cloudflare]));
    vi.spyOn(backendSession, "providerVoices").mockResolvedValue({ listed: false, voices: [] });
    const change = vi.spyOn(backendSession, "changeProvider").mockResolvedValue(answer([cloudflare], "cloudflare"));
    await openProvider("Cloudflare");
    fireEvent.click(screen.getByText("@cf/deepgram/aura-1"));
    expect(await screen.findByText("developers.cloudflare.com")).toHaveAttribute(
      "href", "https://developers.cloudflare.com/workers-ai/models/?tasks=Text-to-Speech");
    fireEvent.change(screen.getByLabelText("Voice name"), { target: { value: "angus" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith("cloudflare", { models: {
      audio: [{ id: "@cf/deepgram/aura-1", voices: [{ name: "angus" }] }]
    } }));
  });
});
