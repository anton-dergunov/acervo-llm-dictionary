import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EditorView } from "@codemirror/view";
import App from "./App";
import { AcervoApiError, backendSession, SCHEMA_VERSION, type CaptureHealth, type Job } from "./api";
import { hydrateGlosses, lookup as lookupDictionaries, searchDictionaries } from "./dictionaries";
import { jobStream } from "./jobs";
import { INSTALLED_EVENT, UPDATE_EVENT } from "./pwa";
import { LocalAcervoRepository, repository } from "./repository";
import type { LocalDatabase } from "./localDatabase";
import { articleChanges } from "./testArticles";
import { TEST_OWNER, testGraph } from "./testGraph";
import { reloadSelectionForTests } from "./wordSelection";

vi.mock("virtual:pwa-register", () => ({ registerSW: vi.fn() }));

// A photo is read without a canvas: the Photo tab needs only the blobs these return.
vi.mock("./photoImage", () => ({
  encodePhoto: vi.fn(async () => new Blob(["jpeg"], { type: "image/jpeg" })),
  still: vi.fn(() => document.createElement("canvas")),
  cropSquare: vi.fn(async () => new Blob(["square"], { type: "image/jpeg" }))
}));
/* jsdom has no canvas: the map's drawing is stood in for by its points as buttons. */
vi.mock("./meaningMap", async () => {
  const { forwardRef, useImperativeHandle } = await import("react");
  return {
    MeaningMap: forwardRef(function Stub(props: {
      data: { points: { id: string; headword: string; emoji: string }[] };
      onSelect?: (point: unknown, index: number) => void;
    }, ref) {
      useImperativeHandle(ref, () => ({ select: vi.fn(), reveal: vi.fn(), setInsets: vi.fn(), fit: vi.fn(), zoomBy: vi.fn() }), []);
      return <div>{props.data.points.map((p, i) => <button key={p.id} onClick={() => props.onSelect?.(p, i)}>
        point {p.headword} {p.emoji}</button>)}</div>;
    })
  };
});

/* The dictionary transports are the network and the device store; the tests below are about what
   the interface does with their answers, so they are spied rather than reimplemented. Everything
   else in the module — the merging, the ranking, the resolution order — stays real. */
vi.mock("./dictionaries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./dictionaries")>();
  return {
    ...actual,
    searchDictionaries: vi.fn(actual.searchDictionaries),
    hydrateGlosses: vi.fn(actual.hydrateGlosses),
    lookup: vi.fn(actual.lookup)
  };
});

/* The mocks above are module-level `vi.fn`s, so their call history and any implementation a test
   installs outlive `restoreAllMocks`. Each test starts from the real behaviour again. */
const realDictionaries = await vi.importActual<typeof import("./dictionaries")>("./dictionaries");

const SESSION = {
  baseUrl: "https://acervo.example.com", email: "learner@account.example.com",
  token: "token", userId: TEST_OWNER
};

const DATASET = "dataset00000001";

/** The server numbers every row it hands back; the cursor is the highest of them. */
/**
 * A sentence, found by its whole paragraph. Its last word shares a no-wrap span with the listen button
 * so the button cannot wrap alone, which splits the text across two elements `getByText` reads
 * separately.
 */
const sentence = (text: string) => (_: string, element: Element | null) =>
  element?.tagName === "P" && element.textContent === text;

function numberedGraph() {
  const graph = testGraph();
  let revision = 0;
  (Object.keys(graph) as (keyof typeof graph)[]).forEach((kind) => {
    (graph[kind] as { revision: number }[]).forEach((record) => { record.revision = ++revision; });
  });
  return { graph, cursor: revision };
}

/** A server that can build entries, which is the ordinary case every other test assumes. */
function serverHealth(capture: Partial<CaptureHealth> = {}) {
  vi.spyOn(backendSession, "health").mockResolvedValue({
    name: "Acervo", version: "0.1.0", build: "1", schemaVersion: SCHEMA_VERSION,
    capture: { available: true, provider: "gemini", model: "gemini-3.1-flash-lite", reason: null, ...capture },
  });
}

function signedIn() {
  const { graph, cursor } = numberedGraph();
  serverHealth();
  vi.spyOn(backendSession, "restore").mockResolvedValue(SESSION);
  vi.spyOn(backendSession, "current").mockReturnValue(SESSION);
  vi.spyOn(backendSession, "refresh").mockResolvedValue(SESSION);
  vi.spyOn(backendSession, "pullGraph").mockResolvedValue({
    schemaVersion: SCHEMA_VERSION, datasetId: DATASET, cursor,
    serverTime: "2026-08-29T12:00:00.000Z", changes: graph
  });
}

/* One counter for the whole file, never reset. A revision is only ever allocated upward, so a write
   always beats whatever the fixture pulled — and a second write in the same test always beats the
   first. Resetting it per test reintroduced exactly the collision it exists to avoid. */
let allocated = 1000;

/** A server that accepts every write and numbers the rows it hands back, as the real one does. */
function acceptWrites() {
  /* One ever-increasing counter per owner, which is what the server actually keeps — deliberately
     not derived from the cursor. A pull can move the cursor back to what the fixture hands out, and
     a write numbered from it would then collide with a revision already stored, so the merge would
     drop it as stale. Seeded above anything the fixture pulls, so a write always wins. */
  vi.spyOn(backendSession, "pushGraph").mockImplementation(async (_device, changes) => {
    const records = Object.fromEntries(Object.entries(changes).map(([kind, list]) =>
      [kind, (list ?? []).map((record) => ({ ...record, revision: ++allocated }))]));
    // The cursor is the highest revision allocated, exactly as the server reports it.
    return {
      schemaVersion: SCHEMA_VERSION, datasetId: DATASET, cursor: allocated,
      serverTime: "2026-08-29T12:00:01.000Z", records
    };
  });
  /* An article is diffed by the server. The replica mirrors it here, so it stands in for what the
     server holds. */
  vi.spyOn(backendSession, "saveArticle").mockImplementation(async (deviceId, draft, minted) => {
    const snapshot = repository.snapshot();
    const { lexemeId, changes } = articleChanges(
      snapshot, draft, new Set(minted), { ownerId: snapshot.ownerId, deviceId },
      new Date(Date.parse("2026-08-29T12:00:01.000Z") + allocated).toISOString()
    );
    const records = Object.fromEntries(Object.entries(changes).map(([kind, list]) =>
      [kind, (list ?? []).map((record) => ({ ...record, revision: ++allocated }))]));
    return {
      schemaVersion: SCHEMA_VERSION, datasetId: DATASET, cursor: allocated,
      serverTime: "2026-08-29T12:00:01.000Z", records, lexemeId, jobId: null
    };
  });
}

/**
 * The editing surface is CodeMirror, so a test drives the real editor rather than a textarea:
 * `findFromDOM` hands back the live view and a dispatch is exactly what typing does.
 */
function editorView(): EditorView {
  const dom = document.querySelector(".code-scroll .cm-editor") as HTMLElement;
  const view = EditorView.findFromDOM(dom);
  if (!view) throw new Error("no editor is mounted");
  return view;
}

const editorText = () => editorView().state.doc.toString();

function replaceInEditor(find: string, replacement: string) {
  const view = editorView();
  act(() => {
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: view.state.doc.toString().replace(find, replacement) } });
  });
}

/** CodeMirror is loaded on demand, so a mount that follows a tab/mode switch takes an extra tick. */
async function waitForEditor() {
  await waitFor(() => expect(document.querySelector(".cm-editor")).not.toBeNull());
}

/**
 * A capture the server answered with a full proposal: one sense, the learner's own sentence kept as
 * an attestation, and the example that draws on it naming that attestation.
 */
function mockGarfioCapture() {
  vi.spyOn(backendSession, "captureText").mockResolvedValue({
    resolution: {
      language: "es", headword: "el garfio", lemma: "garfio", pos: "noun",
      sentences: [{ text: "El disfraz de pirata viene con un garfio.", translation: null }],
      note: null, consumedLines: 1, consumedText: null
    },
    duplicates: [],
    draft: {
      id: null, language: "es", headword: "el garfio", lemma: "garfio", reading: null,
      ipa: null, pos: "noun", gender: "masculine", register: "neutral", dialect: null, emoji: "🪝",
      topics: ["Travel"], status: "active", shortGloss: "hook",
      primaryGloss: "hook", emotion: "sharp and piratical", notes: [],
      senses: [{
        id: "sense0000000091", order: 0, definition: "Gancho de metal curvo y puntiagudo.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["hook", "grappling hook"] }],
        domain: null, emoji: null, images: [],
        examples: [{
          id: "example00000091", text: "El disfraz de pirata viene con un garfio.", textLang: "es",
          translation: "The pirate costume comes with a hook.", translationLang: "en",
          // The learner's own sentence, linked to the attestation created by the same save.
          origin: "attestation", sourceAttestationId: "attest000000091", modelId: null,
          videoRef: null, videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null,
          clipRef: null, imageRef: null, emotion: null,
          note: null, matchedForm: "un garfio", matchedTranslationForm: "hook"
        }]
      }],
      attestations: [{
        id: "attest000000091", text: "El disfraz de pirata viene con un garfio.", translation: null,
        sourceUrl: null, sourceTitle: null, sourceKind: "unknown",
        capturedAt: "2026-08-29T12:00:00.000Z", photoRef: null, photoRegion: null
      }],
      images: []
    }
  });
}

/** Renders the app and waits for the pulled replica to reach the word list. */
async function openList() {
  render(<App />);
  await screen.findByRole("heading", { name: /All words/ });
  await screen.findByRole("button", { name: /picar/ });
}

describe("Acervo application", () => {
  beforeEach(async () => {
    delete window.webkit;
    localStorage.clear();
    sessionStorage.clear();
    await repository.clear();
    vi.mocked(searchDictionaries).mockReset().mockImplementation(realDictionaries.searchDictionaries);
    vi.mocked(hydrateGlosses).mockReset().mockImplementation(realDictionaries.hydrateGlosses);
    vi.mocked(lookupDictionaries).mockReset().mockImplementation(realDictionaries.lookup);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: null }) }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("uses the web page origin when signing in from a browser", async () => {
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    const login = vi.spyOn(backendSession, "login").mockResolvedValue({
      baseUrl: window.location.origin, email: "learner@account.example.com", token: "token", userId: TEST_OWNER
    });
    render(<App />);
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(screen.queryByLabelText("Server")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "learner@account.example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith(
      window.location.origin, "learner@account.example.com", "secret-password"
    ));
  });

  it("keeps explicit server selection in the native macOS host", async () => {
    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);
    expect(await screen.findByLabelText("Server")).toBeInTheDocument();
  });

  it("reports why a sign in failed without leaving the form", async () => {
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    vi.spyOn(backendSession, "login")
      .mockRejectedValue(new AcervoApiError("The email or password is incorrect.", 401, "invalid_credentials"));
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "learner@account.example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("The email or password is incorrect.")).toBeInTheDocument();
  });

  it("offers Android installation before sign in", async () => {
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Linux; Android 15)", platform: "Linux armv8l", maxTouchPoints: 5
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Install the app" })).toBeInTheDocument();
    expect(screen.getByText(/offers Install app when Acervo is not installed yet/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue in browser" }));
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });

  it("stays on the install screen once installed, rather than falling through to signing in", async () => {
    // Landing on the browser's sign-in form the moment the app is installed reads as though the
    // installation went nowhere, and signs you in somewhere other than the app you just added.
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Linux; Android 15)", platform: "Linux armv8l", maxTouchPoints: 5
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Install the app" })).toBeInTheDocument();

    act(() => { window.dispatchEvent(new CustomEvent(INSTALLED_EVENT)); });

    expect(await screen.findByRole("heading", { name: "Acervo is installed" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    // Continuing in the browser stays available, as the deliberate choice it already was.
    fireEvent.click(screen.getByRole("button", { name: "Continue in browser" }));
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });

  it("shows the Safari home-screen steps on iPhone and iPad", async () => {
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
      platform: "iPhone", maxTouchPoints: 5
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    vi.spyOn(backendSession, "restore").mockResolvedValue(null);
    render(<App />);

    expect(await screen.findByText("Open this page in ", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Share")).toBeInTheDocument();
    expect(screen.getByText("Add to Home Screen")).toBeInTheDocument();
  });

  it("lists the owner's words pulled from the server", async () => {
    signedIn();
    await openList();
    expect(screen.getByRole("button", { name: /picar/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /la balsa/ })).toBeInTheDocument();
    // The inbox word is filed separately, not among the filed collections.
    expect(screen.queryByRole("button", { name: /espolvorear/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Inbox/ })).toBeInTheDocument();
  });

  it("still opens on the stored replica when the server is unreachable", async () => {
    signedIn();
    await openList();
    vi.spyOn(backendSession, "pullGraph")
      .mockRejectedValue(new AcervoApiError("The Acervo server could not be reached. Local vocabulary remains available.", 0, "offline"));
    render(<App />);
    expect((await screen.findAllByRole("button", { name: /Offline/ })).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /picar/ }).length).toBeGreaterThan(0);
  });

  it("shows the wordmark, not an empty vocabulary, until the stored replica has been read", async () => {
    // A cold start on a tablet reads the whole replica back before there is anything to show, and
    // the interface used to be drawn during that read saying "All 0 · Loops 0 · Stories 0".
    signedIn();
    // A cold start: the words are already on this device from an earlier opening, and no place was
    // remembered — the first opening after an update, or after signing out.
    await openList();
    cleanup();
    localStorage.clear();
    // A new process on the same device: the stored replica stays, nothing is in memory any more.
    Object.assign(repository, new LocalAcervoRepository(Reflect.get(repository, "database") as LocalDatabase));
    const load = repository.load.bind(repository);
    let release!: () => void;
    const reading = new Promise<void>((resolve) => { release = resolve; });
    vi.spyOn(repository, "load").mockImplementation(async (ownerId) => { await reading; return load(ownerId); });
    render(<App />);

    expect(await screen.findByText("Acervo")).toBeInTheDocument();
    expect(screen.getByText("Opening your vocabulary…")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /All words/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Loops/ })).not.toBeInTheDocument();

    // Every state the DOM passes through, not only where it settles: the interface must never exist
    // without its words. A first frame with no language chosen yet drew every count as 0, and the
    // tablet showed it for as long as the real list then took to render.
    let emptyShell = false;
    const watch = new MutationObserver(() => {
      if (document.querySelector(".viewport") && !screen.queryByRole("button", { name: /picar/ })) emptyShell = true;
    });
    watch.observe(document.body, { childList: true, subtree: true });
    release();
    await screen.findByRole("button", { name: /picar/ });
    watch.disconnect();
    expect(emptyShell).toBe(false);
    expect(screen.queryByText("Opening your vocabulary…")).not.toBeInTheDocument();
  });

  it("waits for the first sync rather than showing zero words when nothing is stored yet", async () => {
    // A first sign-in, or a stored copy being downloaded again: the words come from the pull.
    signedIn();
    const answer = await backendSession.pullGraph(0);
    let release!: () => void;
    const answering = new Promise<void>((resolve) => { release = resolve; });
    vi.spyOn(backendSession, "pullGraph").mockImplementation(async () => { await answering; return answer; });
    render(<App />);
    expect(await screen.findByText("Opening your vocabulary…")).toBeInTheDocument();

    let emptyShell = false;
    const watch = new MutationObserver(() => {
      if (document.querySelector(".viewport") && !screen.queryByRole("button", { name: /picar/ })) emptyShell = true;
    });
    watch.observe(document.body, { childList: true, subtree: true });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(document.querySelector(".viewport")).toBeNull();
    release();
    await screen.findByRole("button", { name: /picar/ });
    watch.disconnect();
    expect(emptyShell).toBe(false);
  });

  it("reopens the word you were reading after a cold start", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    expect(await screen.findByRole("heading", { name: "picar" })).toBeInTheDocument();
    cleanup();

    render(<App />);
    expect(await screen.findByRole("heading", { name: "picar" })).toBeInTheDocument();
  });

  it("opens on the list when the word you were reading has gone", async () => {
    signedIn();
    localStorage.setItem("acervo-last-place", JSON.stringify({ language: "es", topic: "all", openId: "lexeme000000999" }));
    await openList();
    expect(screen.queryByRole("heading", { name: "picar" })).not.toBeInTheDocument();
  });

  it("narrows the list by topic and by search", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /Travel/ }));
    expect(await screen.findByRole("heading", { name: /Travel/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /picar/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "itch" } });
    expect(await screen.findByRole("heading", { name: /Search/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /picar/ })).toBeInTheDocument();
  });

  /* ── external dictionaries ─────────────────────────────────────────
     Your words answer first and always; anything else is below a rule and says whose it is. */

  const DEVICE_HIT = {
    word: "picadura", dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)",
    origin: "device" as const, gloss: "mordedura de un insecto"
  };
  const ONLINE_HIT = {
    word: "picar", dictionaryId: "freedictionaryapi", name: "Free Dictionary API",
    origin: "online" as const, gloss: "to itch"
  };

  /** Answers each tier separately, the way the real transports do. */
  function dictionariesAnswer(byTier: Partial<Record<"device" | "server" | "online", unknown[]>>) {
    vi.mocked(hydrateGlosses).mockImplementation(async (rows) => rows);
    vi.mocked(searchDictionaries).mockImplementation(async (_word, { tiers }) => {
      const hits = (byTier[tiers[0] as "device"] ?? []) as never[];
      // `asked` is what stops the section claiming a word is missing when nothing was switched on.
      return { hits, asked: 1, failed: [] };
    });
  }

  it("searches your words first and the dictionaries below a rule", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT] });
    await openList();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pica" } });

    // Yours answers immediately; the dictionaries follow, under their own heading.
    expect(await screen.findByRole("button", { name: /picar/ })).toBeInTheDocument();
    expect(await screen.findByText("Other dictionaries")).toBeInTheDocument();
    const external = await screen.findByRole("button", { name: /picadura/ });
    expect(within(external).getByText("mordedura de un insecto")).toBeInTheDocument();
    expect(within(external).getByText("Wiktionary (es→es)")).toBeInTheDocument();
    // No study statistics: nothing here is being studied.
    expect(external.querySelector(".strength")).toBeNull();
  });

  it("never asks an online source until ⏎ is pressed", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT], online: [ONLINE_HIT] });
    await openList();
    const box = screen.getByPlaceholderText("Search your words…");
    fireEvent.change(box, { target: { value: "picar" } });
    await screen.findByText("Other dictionaries");

    await waitFor(() => expect(vi.mocked(searchDictionaries).mock.calls.length).toBeGreaterThan(0));
    expect(vi.mocked(searchDictionaries).mock.calls.every(([, options]) => options.tiers[0] !== "online"))
      .toBe(true);
    expect(screen.getByText(/Press ⏎ to look/)).toBeInTheDocument();

    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(
      vi.mocked(searchDictionaries).mock.calls.some(([, options]) => options.tiers[0] === "online")
    ).toBe(true));
    expect(await screen.findByRole("button", { name: /Free Dictionary API/ })).toBeInTheDocument();
  });

  it("says the server is unreachable rather than pretending the list is complete", async () => {
    signedIn();
    vi.spyOn(backendSession, "pullGraph").mockRejectedValue(
      new AcervoApiError("offline", 0, "offline"));
    dictionariesAnswer({ device: [] });
    render(<App />);
    await screen.findByRole("heading", { name: /All words/ });
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pic" } });
    expect(await screen.findByText(/only the dictionaries stored on this device/)).toBeInTheDocument();
  });

  it("opens a dictionary entry as an article, and offers to add it", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT] });
    vi.mocked(lookupDictionaries).mockResolvedValue([{
      dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device",
      attribution: "Wiktionary contributors. CC BY-SA 4.0.", licence: "CC BY-SA 4.0", sourceLang: "es",
      entry: { dictionaryId: "kaikki-es-es", word: "picadura", tier: "fields", articles: [{
        headword: "picadura", posLabel: "noun", ipa: "[pikaˈðuɾa]",
        senses: [{ definition: "Mordedura de un insecto." }]
      }] }
    }]);
    await openList();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pica" } });
    fireEvent.click(await screen.findByRole("button", { name: /picadura/ }));

    expect(await screen.findByRole("heading", { name: "picadura" })).toBeInTheDocument();
    expect(screen.getByText("Mordedura de un insecto.")).toBeInTheDocument();
    // Said where it came from, because CC BY-SA asks that of whoever displays it.
    expect(screen.getByText(/Wiktionary contributors/)).toBeInTheDocument();
    expect(screen.getByText("not in your words")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add to my words" })).toBeInTheDocument();
  });

  it("adds a dictionary entry through capture, carrying it as reference and not as your sentence", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT] });
    vi.mocked(lookupDictionaries).mockResolvedValue([{
      dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device",
      attribution: "Wiktionary contributors.", licence: "CC BY-SA 4.0", sourceLang: "es",
      entry: { dictionaryId: "kaikki-es-es", word: "picadura", tier: "fields", articles: [{
        headword: "picadura", posLabel: "noun",
        senses: [{ definition: "Mordedura de un insecto.",
                   examples: [{ text: "Una picadura de mosquito." }] }]
      }] }
    }]);
    const capture = vi.spyOn(backendSession, "captureText")
      .mockRejectedValue(new AcervoApiError("nothing to build", 502, "llm_unusable"));

    await openList();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pica" } });
    fireEvent.click(await screen.findByRole("button", { name: /picadura/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Add to my words" }));
    fireEvent.click(screen.getByRole("button", { name: "Build entry" }));

    await waitFor(() => expect(capture).toHaveBeenCalled());
    const [, request] = capture.mock.calls[0];
    expect(request.headword).toBe("picadura");
    expect(request.referenceMode).toBe("expand");
    expect(request.reference).toContain("Mordedura de un insecto.");
    // The dictionary's own example is reference, never the text a capture turns into attestations.
    expect(request.text).toBe("picadura");
    expect(request.text).not.toContain("mosquito");
  });

  it("forgets an abandoned composition rather than reopening it", async () => {
    signedIn();
    dictionariesAnswer({ device: [DEVICE_HIT] });
    vi.mocked(lookupDictionaries).mockResolvedValue([{
      dictionaryId: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device",
      attribution: "Wiktionary contributors.", licence: "CC BY-SA 4.0", sourceLang: "es",
      entry: { dictionaryId: "kaikki-es-es", word: "picadura", tier: "fields", articles: [{
        headword: "picadura", posLabel: "noun",
        senses: [{ definition: "Mordedura de un insecto." }]
      }] }
    }]);
    const capture = vi.spyOn(backendSession, "captureText")
      .mockRejectedValue(new AcervoApiError("nothing to build", 502, "llm_unusable"));

    await openList();
    fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "pica" } });
    fireEvent.click(await screen.findByRole("button", { name: /picadura/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Add to my words" }));
    fireEvent.click(screen.getByRole("button", { name: "Build entry" }));
    await waitFor(() => expect(capture).toHaveBeenCalled());
    const spent = capture.mock.calls.length;

    // Escape leaves the composition, and must take its seed with it. It used to clear the tab and
    // leave the seed behind, so the next press of Add reopened the dictionary word you had walked
    // away from — and, because a seeded composition processes itself on arrival, spent a capture
    // building it a second time.
    fireEvent.keyDown(document, { key: "Escape" });
    await screen.findByRole("button", { name: /picar/ });

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByLabelText(/Paste a word/)).toHaveValue("");
    expect(screen.getByLabelText(/Which word/)).toHaveValue("");
    expect(screen.queryByText(/What is being sent as reference/)).not.toBeInTheDocument();
    expect(capture).toHaveBeenCalledTimes(spent);
  });

  it("looks the dictionary form up too, not only the headword you read", async () => {
    signedIn();
    vi.mocked(lookupDictionaries).mockResolvedValue([]);
    await openList();
    // `la balsa` is how a Spanish learner needs to see the word; `balsa` is how a dictionary is
    // keyed. Only the first was ever asked for, so every gendered noun missed.
    fireEvent.click(await screen.findByRole("button", { name: /la balsa/ }));
    fireEvent.click((await screen.findByText("Other dictionaries")).closest("button")!);
    await waitFor(() => expect(lookupDictionaries)
      .toHaveBeenCalledWith("la balsa", "es", ["device", "server"], ["balsa"]));
    expect(await screen.findByText(/“la balsa” or “balsa”/)).toBeInTheDocument();
  });

  it("looks a word up in the dictionaries only when their section is opened", async () => {
    signedIn();
    vi.mocked(lookupDictionaries).mockResolvedValue([]);
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));

    const fold = await screen.findByText("Other dictionaries");
    // Reading your own article must not quietly issue byte-range reads on the chance you are curious.
    expect(lookupDictionaries).not.toHaveBeenCalled();

    fireEvent.click(fold.closest("button")!);
    await waitFor(() => expect(lookupDictionaries)
      .toHaveBeenCalledWith("picar", "es", ["device", "server"], ["picar"]));
    expect(await screen.findByText(/No dictionary on this device or your server holds/))
      .toBeInTheDocument();
  });

  it("opens the article with its senses, where you met it, and details folded away", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    expect(await screen.findByRole("heading", { name: "picar" })).toBeInTheDocument();
    expect(screen.getByText("/piˈkaɾ/")).toBeInTheDocument();
    // Plain words, not "v." — and no language code, because the vocabulary is already chosen.
    expect(screen.getByText("verb")).toBeInTheDocument();
    expect(screen.getByText(sentence("Producir comezón."))).toBeInTheDocument();
    expect(screen.getByText(sentence("Cortar en trozos pequeños."))).toBeInTheDocument();
    // Nothing on the reading surface about approval, models or where a clip starts.
    expect(screen.queryByText("unapproved")).toBeNull();
    expect(screen.queryByText(/starts at/)).toBeNull();
    // A clip's title is made quiet by rule, and it is removed from its dialog rather than the page.
    expect(screen.getByText(/comiendo en un mercado/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove this clip" })).toBeNull();
    // Study state is a fact about the record, so it waits in Details until asked for.
    expect(screen.queryByText("18.3")).toBeNull();
    fireEvent.click(screen.getByText("Details").closest("button")!);
    expect(screen.getByText("18.3")).toBeInTheDocument();
  });

  it("shows a sentence you supplied once, in its sense, rather than again under where you met it", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await screen.findByRole("heading", { name: "picar" });
    const graph = repository.snapshot();
    const linked = graph.examples.find((example) => example.sourceAttestationId && !example.deleted);
    const attestation = graph.attestations.find((record) => record.id === linked?.sourceAttestationId);
    expect(attestation).toBeTruthy();
    expect(document.querySelector(`[data-record="${attestation!.id}"]`)).toBeNull();
    expect(within(document.querySelector(`[data-record="${linked!.id}"]`) as HTMLElement)
      .getByText("your sentence")).toBeInTheDocument();
  });

  it("projects the open record as YAML", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "YAML" }));
    expect(await screen.findByText("picar.yaml")).toBeInTheDocument();
    expect(editorText()).toContain("id: lexemepicar0001");
  });

  it("reaches sync, sign-out and delete on the native host, without its update controls", async () => {
    // The Mac window owns the server address and the app's own updates. Everything about the
    // vocabulary is here — and hiding the whole pane to keep the update controls out left none of
    // it reachable on macOS at all.
    window.webkit = { messageHandlers: { acervo: { postMessage: vi.fn() } } };
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /Open settings/ }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    expect(settings.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    // A second update control here would conflict with the one the host already owns.
    expect(settings.queryByText("Acervo is up to date")).not.toBeInTheDocument();
    expect(settings.queryByText(/Download Acervo for macOS/)).not.toBeInTheDocument();
    expect(settings.getByText("Updates and server address")).toBeInTheDocument();

    fireEvent.click(settings.getByRole("tab", { name: "Sync" }));
    expect(settings.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    fireEvent.click(settings.getByRole("tab", { name: "Data" }));
    expect(settings.getByRole("button", { name: /Delete all words/ })).toBeInTheDocument();
  });

  it("puts export, import and deletion together on the Data page", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Data" }));
    expect(settings.getByRole("button", { name: "Export…" })).toBeInTheDocument();
    expect(settings.getByRole("combobox")).toHaveValue("all");
    expect(settings.getByRole("heading", { name: "Import" })).toBeInTheDocument();
    expect(settings.getByRole("button", { name: /Delete all words/ })).toBeInTheDocument();
  });

  it("opens the Data page armed for deletion when the Mac menu asks", async () => {
    signedIn();
    await openList();
    window.acervo!.command("delete");

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    // The menu item ends in an ellipsis, so it owes the reader a confirmation rather than a page.
    expect(settings.getByLabelText(/Type DELETE to confirm/)).toBeInTheDocument();
    expect(settings.getByRole("button", { name: "Export…" })).toBeInTheDocument();
  });

  it("adds a topic from settings and files it into the rail", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Topics" }));
    fireEvent.click(settings.getByRole("button", { name: "Add a topic…" }));
    fireEvent.change(settings.getByLabelText("Name"), { target: { value: "Slang" } });
    fireEvent.change(settings.getByLabelText("Icon"), { target: { value: "💬" } });
    fireEvent.click(settings.getByRole("button", { name: "Add topic" }));

    // Generated entries can only be filed under topics that exist, so this is what unblocks capture
    // on an account that was not seeded.
    expect(await settings.findByText("Slang")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));
    expect(await screen.findByRole("button", { name: /Slang/ })).toBeInTheDocument();
  });

  it("refuses to remove a vocabulary that still holds words", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Vocabularies" }));
    const spanish = settings.getByText(/^es · defined in es/).closest(".config-row")!;
    fireEvent.click(within(spanish as HTMLElement).getByRole("button", { name: "Remove" }));
    // Nothing is deleted, but the words would lose the gloss preference they are rendered with.
    expect(await screen.findByText(/still has 3 words/)).toBeInTheDocument();
    expect(repository.snapshot().vocabularies.filter((entry) => !entry.deleted)).toHaveLength(2);
  });

  it("offers editing only from the YAML view, and switches views from the article menu", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await screen.findByRole("heading", { name: "picar" });
    expect(screen.queryByRole("button", { name: "Edit as YAML" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Article menu" }));
    fireEvent.click(await screen.findByRole("menuitemradio", { name: "YAML" }));
    expect(await screen.findByRole("button", { name: "Edit as YAML" })).toBeInTheDocument();
  });

  it("plays a word's stored pronunciation, and records it again from the toast", async () => {
    signedIn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({ data: null }), blob: async () => new Blob(["ID3"], { type: "audio/mpeg" })
    }));
    const pronounce = vi.spyOn(backendSession, "pronounce");
    // The session is restored by a spy in these tests, so the media address is too.
    vi.spyOn(backendSession, "mediaFileUrl").mockImplementation((reference) => `${SESSION.baseUrl}/api/acervo/media/${reference}`);
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Listen to picar" }));

    // The replica already names a current clip, so the first press asks the server for nothing.
    expect(await screen.findByText("Playing · es-ES-Wavenet-F")).toBeInTheDocument();
    expect(pronounce).not.toHaveBeenCalled();

    const stored = repository.snapshot().pronunciations[0];
    pronounce.mockResolvedValue({ ...stored, audioRef: "audio/lexemepicar0001/hl08nur0wl9h0n1-99999999.mp3", voice: "es-ES-Wavenet-E" });
    fireEvent.click(screen.getByRole("button", { name: "Record again" }));
    expect(await screen.findByText("Recorded again · es-ES-Wavenet-E")).toBeInTheDocument();
    expect(pronounce).toHaveBeenCalledWith("lexemes", "lexemepicar0001", expect.any(String), true);
  });

  it("refuses to build a second entry for a word already in the vocabulary", async () => {
    signedIn();
    await openList();
    const capture = vi.spyOn(backendSession, "captureText").mockResolvedValue({
      resolution: {
        language: "es", headword: "picar", lemma: "picar", pos: "verb",
        sentences: [], note: null, consumedLines: 1, consumedText: null
      },
      duplicates: [{ id: "lexemepicar0001", headword: "picar", shortGloss: "to itch; to chop" }],
      draft: null
    });

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "¿Te pica mucho la salsa?" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));

    expect(await screen.findByText("You already have this word.")).toBeInTheDocument();
    // Nothing was generated and nothing was written; the entry it already has is one tap away.
    expect(capture).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "picar" }));
    expect(await screen.findByRole("heading", { name: "picar" })).toBeInTheDocument();
  });

  it("captures a sentence, reviews the generated entry as an article and saves it", async () => {
    signedIn();
    await openList();
    acceptWrites();
    mockGarfioCapture();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "El disfraz de pirata viene con un garfio." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));

    // The proposal arrives rendered, not serialized: reviewing a generated entry is reading the
    // thing you are about to get, in the component a stored entry uses.
    expect(await screen.findByRole("heading", { name: "el garfio" })).toBeInTheDocument();
    expect(screen.getByText(sentence("Gancho de metal curvo y puntiagudo."))).toBeInTheDocument();
    expect(screen.getByText("grappling hook")).toBeInTheDocument();
    // The one provenance worth reading while reviewing: which sentence is yours.
    expect(screen.getByText("your sentence")).toBeInTheDocument();
    // Nothing is stored, so there is no id, revision or date to claim there is.
    expect(document.querySelector(".meta-foot")).toBeNull();

    // Going back to the capture keeps what was submitted, so the text can be adjusted and re-run
    // rather than retyped.
    fireEvent.click(screen.getByRole("button", { name: "Text" }));
    expect(await screen.findByLabelText(/Paste a word/))
      .toHaveValue("El disfraz de pirata viene con un garfio.");

    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    await screen.findByText("new-entry.yaml");
    await waitForEditor();
    expect(editorText()).toContain("headword: el garfio");
    expect(editorText()).toContain("origin: attestation");

    fireEvent.click(screen.getByRole("button", { name: "Validate & save" }));
    expect(await screen.findByRole("heading", { name: /garfio/ })).toBeInTheDocument();

    const saved = repository.snapshot();
    const lexeme = saved.lexemes.find((record) => record.headword === "el garfio");
    // Reviewed before it was saved, so it is an ordinary word rather than an Inbox one.
    expect(lexeme?.status).toBe("active");
    const attestation = saved.attestations.find((record) => record.lexemeId === lexeme?.id);
    const example = saved.examples.find((record) => record.text.startsWith("El disfraz"));
    // Provenance is the point: the sentence survives as its own record, and the example says so.
    expect(example?.origin).toBe("attestation");
    expect(example?.sourceAttestationId).toBe(attestation?.id);
  });

  it("takes Add back to the capture box mid-composition rather than starting over", async () => {
    signedIn();
    await openList();
    mockGarfioCapture();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "El disfraz de pirata viene con un garfio." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));
    await screen.findByRole("heading", { name: "el garfio" });

    // The toolbar stays up while you compose, so Add is reachable from the article you are
    // reviewing. It means "back to the box", not "throw this away and start again" — correcting the
    // word and processing it once more is the ordinary way to use this screen.
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByLabelText(/Paste a word/))
      .toHaveValue("El disfraz de pirata viene con un garfio.");
  });

  it("renders the proposal from the document, so a YAML edit shows in the article", async () => {
    signedIn();
    await openList();
    mockGarfioCapture();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "El disfraz de pirata viene con un garfio." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));
    await screen.findByRole("heading", { name: "el garfio" });

    // The preview is derived from the editor text rather than kept beside it, so the two cannot
    // disagree about what is being approved.
    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    await screen.findByText("new-entry.yaml");
    await waitForEditor();
    replaceInEditor("headword: el garfio", "headword: el gancho");
    fireEvent.click(screen.getByRole("button", { name: "Article" }));
    expect(await screen.findByRole("heading", { name: "el gancho" })).toBeInTheDocument();

    // A document that cannot be read has nothing to show and nothing to approve.
    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    await waitForEditor();
    replaceInEditor("pos: noun", "pos: preposition");
    fireEvent.click(screen.getByRole("button", { name: "Article" }));
    expect(await screen.findByText(/must be one of/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("takes the word on its own, and says which one it is when the sentence does not", async () => {
    signedIn();
    await openList();
    const capture = vi.spyOn(backendSession, "captureText").mockResolvedValue({
      resolution: {
        language: "es", headword: "picar", lemma: "picar", pos: "verb",
        sentences: [], note: null, consumedLines: 1, consumedText: null
      },
      duplicates: [{ id: "lexemepicar0001", headword: "picar", shortGloss: "to itch; to chop" }],
      draft: null
    });

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Which word/), { target: { value: "  picar  " } });
    // The sentence is empty, so the word is the whole capture — one request shape, not two.
    fireEvent.click(screen.getByRole("button", { name: "Process" }));

    await screen.findByText("You already have this word.");
    expect(capture).toHaveBeenCalledWith(
      expect.any(String), expect.objectContaining({ text: "picar", headword: "picar" }));
  });

  it("saves an article edited as YAML and shows the change", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await editAsYaml();
    await waitForEditor();

    replaceInEditor("emoji: 🌶️", "emoji: 🫠");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved to the server")).toBeInTheDocument();
    await waitFor(() =>
      expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.emoji).toBe("🫠"));
  });

  it("keeps the draft and says what is wrong when the document does not parse", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await editAsYaml();
    await waitForEditor();

    replaceInEditor("pos: verb", "pos: preposition");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/must be one of/)).toBeInTheDocument();
    // Still in the editor, with the rejected text intact rather than reverted.
    expect(editorText())
      .toContain("pos: preposition");
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.pos).toBe("verb");
  });

  it("replaces the word list while composing, and puts it back on cancel", async () => {
    signedIn();
    await openList();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await screen.findByRole("region", { name: "Add a word" });
    // The list is gone rather than covered, so the composer owns the height and can pin its own
    // header and buttons — which is the whole reason it is a view and not a dialog.
    expect(screen.queryByRole("button", { name: /picar/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(await screen.findByRole("button", { name: /picar/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Add a word" })).not.toBeInTheDocument();
  });

  /* A surface that replaces the list has to carry the way back out of itself. Loops shipped with
     two accidental exits — the Add button, which starts a composition you did not want, and changing
     language — and every obvious one was a dead end: the search box updated a list that was not
     drawn, and Escape did nothing. These are the three that should work. */
  describe("the map", () => {
    const spanishMap = {
      language: "es", fingerprint: "fp", version: "fp.none", model: "m", side: 1000, words: 2, senses: 2,
      names: "none" as const, regions: [], contours: [],
      points: [
        { sense: "sensepicarchop0", lexeme: "lexemepicar0001", x: 1, y: 1, r: -1, h: -1, rank: 1, nb: [1] },
        { sense: "sensebalsaraft0", lexeme: "lexemebalsa0001", x: 9, y: 9, r: -1, h: -1, rank: 0.5, nb: [0] }
      ]
    };
    const openMap = async () => {
      vi.spyOn(backendSession, "readMap").mockResolvedValue(spanishMap);
      fireEvent.click(screen.getByRole("button", { name: "Map" }));
      await screen.findByRole("heading", { name: "Map" });
    };

    it("replaces the list, and its own row replaces the top bar", async () => {
      signedIn();
      await openList();
      await openMap();
      expect(screen.queryByRole("heading", { name: /All words/ })).not.toBeInTheDocument();
      // `styles.css` hides the top bar on `map-open`; jsdom applies no stylesheet, so this asserts the
      // class the rule keys on.
      expect(document.querySelector(".app.map-open")).not.toBeNull();
    });

    it("comes back from an article opened on it, with the peek still open", async () => {
      signedIn();
      await openList();
      await openMap();
      fireEvent.click(await screen.findByRole("button", { name: /point picar/ }));
      fireEvent.click(await screen.findByRole("button", { name: /Open the article/ }));
      expect(await screen.findByRole("button", { name: "Back to the list" })).toBeInTheDocument();
      expect(document.querySelector(".app.map-open")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Back to the list" }));
      expect(await screen.findByRole("heading", { name: "Map" })).toBeInTheDocument();
      expect(await screen.findByText("Cortar en trozos pequeños.")).toBeInTheDocument();
    });

    it("lights only its own tab in the rail, not the topic behind it", async () => {
      signedIn();
      await openList();
      await openMap();
      expect(screen.getByRole("button", { name: "Map" })).toHaveClass("on");
      expect(document.querySelectorAll(".rail .tab.on")).toHaveLength(1);
    });

    it("draws its row in the top bar itself, in place of search", async () => {
      signedIn();
      await openList();
      await openMap();
      expect(document.querySelector(".topbar .map-top")).not.toBeNull();
      expect(screen.queryByPlaceholderText("Search your words…")).not.toBeInTheDocument();
    });

    it("shows a sense from its article, and Back returns to the article", async () => {
      signedIn();
      await openList();
      vi.spyOn(backendSession, "readMap").mockResolvedValue(spanishMap);
      fireEvent.click(await screen.findByRole("button", { name: /picar/ }));
      const shows = await screen.findAllByRole("button", { name: "Show on the map" });
      fireEvent.click(shows[shows.length > 1 ? 1 : 0]);
      expect(await screen.findByRole("heading", { name: "Map" })).toBeInTheDocument();
      expect(await screen.findByText("Cortar en trozos pequeños.")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Back to your words" }));
      expect(await screen.findByRole("button", { name: "Back to the list" })).toBeInTheDocument();
    });

    it("leaves for search on ⌘K, the search box being in the bar it hides", async () => {
      signedIn();
      await openList();
      await openMap();
      fireEvent.keyDown(document, { key: "k", metaKey: true });
      expect(await screen.findByRole("heading", { name: /All words/ })).toBeInTheDocument();
      expect(document.activeElement).toBe(screen.getByPlaceholderText("Search your words…"));
    });

    it("leaves on Escape when nothing is peeked at", async () => {
      signedIn();
      await openList();
      await openMap();
      fireEvent.keyDown(document, { key: "Escape" });
      expect(await screen.findByRole("heading", { name: /All words/ })).toBeInTheDocument();
    });
  });

  describe("getting back out of Loops", () => {
    const openLoops = async () => {
      fireEvent.click(screen.getByRole("button", { name: "Loops" }));
      await screen.findByRole("heading", { name: "Loops" });
      // The list is gone rather than covered — the surface owns the height so its controls cannot
      // scroll away. Keyed on the list's own heading, because a loop row names words too.
      expect(screen.queryByRole("heading", { name: /All words/ })).not.toBeInTheDocument();
    };

    it("goes back to the words with the back arrow", async () => {
      signedIn();
      await openList();
      await openLoops();
      fireEvent.click(screen.getByRole("button", { name: "Back to the list" }));
      expect(await screen.findByRole("heading", { name: /All words/ })).toBeInTheDocument();
    });

    it("leaves when you type in the search box, because that is asking for the list", async () => {
      signedIn();
      await openList();
      await openLoops();
      fireEvent.change(screen.getByPlaceholderText("Search your words…"), { target: { value: "itch" } });
      expect(await screen.findByRole("heading", { name: /Search/ })).toBeInTheDocument();
    });

    it("leaves on Escape, like every other surface that replaces the list", async () => {
      signedIn();
      await openList();
      await openLoops();
      fireEvent.keyDown(document, { key: "Escape" });
      expect(await screen.findByRole("heading", { name: /All words/ })).toBeInTheDocument();
    });

    it("keeps the topic rail, which an open article does not", async () => {
      signedIn();
      await openList();
      await openLoops();
      // A topic files a *word*, so it has nothing to say here — but there is room for it wherever
      // there is room at all, and only a phone drops it. `styles.css` is what drops it there, and
      // jsdom applies no stylesheet, so this asserts the class the rule keys on.
      expect(document.querySelector(".app.loops-open")).not.toBeNull();
      expect(document.querySelector(".app.article-open")).toBeNull();
    });
  });

  it("edits an article in the same composer, not inside the scrolling pane", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await editAsYaml();

    // Same shell as Add, so the Save button cannot scroll away on a long entry.
    const editor = within(await screen.findByRole("region", { name: /Edit picar/ }));
    expect(editor.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(document.querySelector(".main.composing")).not.toBeNull();

    fireEvent.click(editor.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("heading", { name: /picar/ })).toBeInTheDocument();
    expect(document.querySelector(".main.composing")).toBeNull();
  });

  it("wraps long lines by default, and keeps line numbers off", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await editAsYaml();
    await waitForEditor();

    // Wrapping is the default: these documents are prose, and a clipped definition was unreadable
    // and unscrollable both. The class is what the editor actually applies to wrap its lines.
    expect(document.querySelector(".cm-content")!.classList.contains("cm-lineWrapping")).toBe(true);
    // Numbers are off by default, and the gutter is absent rather than empty.
    expect(document.querySelector(".cm-lineNumbers")).toBeNull();
  });

  it("turns on line numbers from settings, and the editor picks them up", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    // Wrap and numbers describe this screen, not the vocabulary, so they live in settings rather
    // than as controls you step over on the way to the editor.
    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));
    fireEvent.click(settings.getByRole("tab", { name: "Reading" }));
    fireEvent.click(settings.getByRole("checkbox", { name: /Show line numbers/ }));
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));

    fireEvent.click(await screen.findByRole("button", { name: /picar/ }));
    await editAsYaml();
    await waitForEditor();
    // The editor draws a number per line and keeps it beside a line that wraps — which is the
    // reason numbers are worth offering at all.
    expect(document.querySelector(".cm-lineNumbers")).not.toBeNull();
    expect(localStorage.getItem("acervo-editor-numbers")).toBe("on");
  });

  it("creates an entry from the YAML template and opens it", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    // A region, not a dialog: composing replaces the list rather than covering it.
    const sheet = within(screen.getByRole("region", { name: "Add a word" }));
    fireEvent.click(sheet.getByRole("button", { name: "YAML" }));
    await waitForEditor();

    const view = editorView();
    act(() => {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: view.state.doc.toString()
        .replace('headword: ""', "headword: sobremesa")
        .replace('definition: ""', "definition: Charla tras la comida.")
        .replace('terms: [""]', "terms: [after-dinner talk]")
        .replace('- text: ""', "- text: La sobremesa duró dos horas.")
        .replace('translation: ""', "translation: The talk lasted two hours.") } });
    });
    fireEvent.click(sheet.getByRole("button", { name: "Validate & save" }));

    expect(await screen.findByText("Added to your vocabulary")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /sobremesa/ })).toBeInTheDocument();
  });

  it("saves a new word without asking for any enrichment, and opens it on the page", async () => {
    /* The server enriches what a save creates. A device that also asked would spend every call
       twice, so nothing model-shaped may leave from here — and Cards, the touch default, would
       re-flow under the reader as results land. */
    localStorage.setItem("acervo-article-view", "cards");
    signedIn();
    await openList();
    acceptWrites();
    const asked = [vi.spyOn(backendSession, "enqueueJob"), vi.spyOn(backendSession, "pronounce")];
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    const sheet = within(screen.getByRole("region", { name: "Add a word" }));
    fireEvent.click(sheet.getByRole("button", { name: "YAML" }));
    await waitForEditor();
    const view = editorView();
    act(() => {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: view.state.doc.toString()
        .replace('headword: ""', "headword: sobremesa")
        .replace('definition: ""', "definition: Charla tras la comida.")
        .replace('terms: [""]', "terms: [after-dinner talk]")
        .replace('- text: ""', "- text: La sobremesa duró dos horas.")
        .replace('translation: ""', "translation: The talk lasted two hours.") } });
    });
    fireEvent.click(sheet.getByRole("button", { name: "Validate & save" }));

    expect(await screen.findByRole("heading", { name: /sobremesa/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Page" })).toHaveClass("on");
    asked.forEach((spy) => expect(spy).not.toHaveBeenCalled());
  });

  it("keeps Cards closed while the server fills a word in, and shows how far it has got", async () => {
    const working: Job = {
      id: "job000000000001", ownerId: TEST_OWNER, parentId: null, kind: "enrich",
      subject: { kind: "lexeme", id: "lexemepicar0001" }, input: {}, state: "running",
      trigger: "save", rerun: false, cancelRequested: false, dismissed: false, error: null,
      message: null, notBefore: null, createdAt: "2026-09-17T10:00:00.000Z",
      startedAt: "2026-09-17T10:00:01.000Z", finishedAt: null,
      steps: [
        { name: "clips", state: "done", detail: { found: 0 } },
        { name: "pictures", state: "running", done: 1, total: 2 },
        { name: "pronunciations", state: "pending" }
      ]
    };
    signedIn();
    await openList();
    act(() => jobStream.apply(working));
    expect(await screen.findByRole("img", { name: "Still filling in" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await screen.findByRole("heading", { name: "picar" });
    const cards = screen.getByRole("button", { name: "Cards" });
    expect(cards).toBeDisabled();
    expect(cards).toHaveAttribute("title", "Cards open when pictures and clips are ready");
    expect(screen.getByText("Drawing 2 of 2")).toHaveClass("now");
    expect(screen.getByText("Recording audio")).not.toHaveClass("now");

    act(() => jobStream.apply({
      ...working, state: "done", steps: working.steps.map((step) => ({ ...step, state: "done" }))
    }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Cards" })).toBeEnabled());
    expect(screen.queryByText(/Drawing/)).toBeNull();
    act(() => jobStream.stop());
  });

  it("redraws a picture as a server job, and pulls the new one when it is done", async () => {
    signedIn();
    await openList();
    vi.spyOn(backendSession, "imageSettings").mockResolvedValue({
      drawEnabled: true, stylesOff: [], boostVariety: true, storyContinuity: "artwork",
      chosen: false, maxAttempts: 4, available: true,
      styles: [{ id: "flat-vector", label: "Flat vector", mono: false, photographic: false }]
    });
    vi.spyOn(backendSession, "imagePrompt").mockRejectedValue(new Error("offline"));
    const redraw: Job = {
      id: "job000000000007", ownerId: TEST_OWNER, parentId: null, kind: "image.redraw",
      subject: { kind: "imagePrompt", id: "imagepicar00010" }, input: {}, state: "queued",
      trigger: "manual", steps: [], rerun: false, cancelRequested: false, dismissed: false,
      error: null, message: null, notBefore: null, createdAt: "2026-09-17T10:00:00.000Z",
      startedAt: null, finishedAt: null
    };
    const enqueue = vi.spyOn(backendSession, "enqueueJob").mockResolvedValue(redraw);
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: /^Picture for picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Draw" }));

    await waitFor(() => expect(enqueue).toHaveBeenCalledWith({
      kind: "image.redraw", subject: { kind: "imagePrompt", id: "imagepicar00010" },
      input: { prompt: "A hand hovering near an itchy nose, flat vector, no text.", styleId: "flat-vector" }
    }));
    // Leaving the dialog loses nothing: the picture says it is being redrawn for as long as the job is open.
    expect(await screen.findByText(/Redrawing…|Drawing…/)).toBeInTheDocument();

    // The finished job clears the mark. Bringing the new picture down is the *revision* frame's
    // job, which every write publishes and `jobs.test.ts` pins — this page does nothing special for
    // a redraw, which is the point: the new picture has a new reference and is fetched like any one.
    act(() => jobStream.apply({ ...redraw, state: "done", finishedAt: "2026-09-17T10:01:00.000Z" }));
    await waitFor(() => expect(screen.queryByText(/Redrawing…|Drawing…/)).toBeNull());
    act(() => jobStream.stop());
  });

  it("leaves one line and a Try again when the server could not finish a word", async () => {
    signedIn();
    await openList();
    const failed: Job = {
      id: "job000000000002", ownerId: TEST_OWNER, parentId: null, kind: "enrich",
      subject: { kind: "lexeme", id: "lexemepicar0001" }, input: {}, state: "failed",
      trigger: "save", rerun: false, cancelRequested: false, dismissed: false, error: "image_refused",
      message: null, notBefore: null, createdAt: "2026-09-17T10:00:00.000Z",
      startedAt: null, finishedAt: "2026-09-17T10:02:00.000Z",
      steps: [
        { name: "clips", state: "skipped" },
        { name: "pictures", state: "failed", done: 2, total: 2, error: "image_refused", detail: { refused: 1 } },
        { name: "pronunciations", state: "skipped" }
      ]
    };
    act(() => jobStream.apply(failed));
    const again = vi.spyOn(backendSession, "enqueueJob").mockResolvedValue({
      ...failed, id: "job000000000003", state: "queued", steps: [], createdAt: "2026-09-17T10:03:00.000Z"
    });
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    expect(await screen.findByText("1 of 2 pictures drawn")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(again).toHaveBeenCalledWith({
      kind: "enrich", subject: { kind: "lexeme", id: "lexemepicar0001" }
    }));
    expect(await screen.findByText("Waiting to start")).toBeInTheDocument();
    act(() => jobStream.stop());
  });

  it("reports a refused save without changing anything locally", async () => {
    signedIn();
    await openList();
    vi.spyOn(backendSession, "saveArticle")
      .mockRejectedValue(new AcervoApiError("This entry was changed somewhere else.", 409, "stale_record"));
    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    await editAsYaml();
    await waitForEditor();

    replaceInEditor("headword: picar", "headword: picarse");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/changed somewhere else/)).toBeInTheDocument();
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemepicar0001")!.headword).toBe("picar");
  });

  it("deletes a word once the server has accepted the tombstone", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /la balsa/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByText(/tombstone/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: /la balsa/ })).not.toBeInTheDocument());
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemebalsa0001")?.deleted).toBe(true);
  });

  it("gathers words into the selection from the list and an article, and makes a loop from them", async () => {
    localStorage.removeItem("acervo-word-selection");
    reloadSelectionForTests();
    vi.spyOn(backendSession, "loopSchema").mockResolvedValue({
      apiVersion: "2.0.0", engineVersion: "0.7.0", maxItems: 24, formats: [], writerAvailable: true,
      mixesLanguages: true, productionBundle: true, families: []
    });
    signedIn();
    await openList();
    fireEvent.contextMenu(screen.getByRole("button", { name: /la balsa/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Add to selection" }));
    expect(await screen.findByText("1 word selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /picar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Add to selection" }));
    expect(await screen.findByText("2 words selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove from selection" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Make a loop from these words" }));
    expect(await screen.findByRole("radio", { name: /Your selection · 2/ })).toHaveAttribute("aria-checked", "true");
    expect(await screen.findByRole("button", { name: "Make the loop from 2 words" })).toBeInTheDocument();
    localStorage.removeItem("acervo-word-selection");
    reloadSelectionForTests();
  });

  it("files a word out of the Inbox from its article, into its own topics", async () => {
    signedIn();
    await openList();
    acceptWrites();
    fireEvent.click(screen.getByRole("button", { name: /Inbox/ }));
    fireEvent.click(await screen.findByRole("button", { name: /espolvorear/ }));

    fireEvent.click(await screen.findByRole("button", { name: "File it" }));
    expect(await screen.findByText(/in its topics now/)).toBeInTheDocument();
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemeespolv001")!.status).toBe("active");

    // The word stays open — you have just read it, which is what filing it means — and the button
    // is gone, because there is nothing left to file.
    expect(screen.getByRole("heading", { name: "espolvorear" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "File it" })).not.toBeInTheDocument();
    // The Inbox is empty, so the rail drops its tab and stands on All words instead of a list with
    // no way back to itself. The word is now in Food, which it always named.
    await waitFor(() => expect(screen.queryByRole("button", { name: /Inbox/ })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Food/ }));
    expect(await screen.findByRole("button", { name: /espolvorear/ })).toBeInTheDocument();
  });

  it("offers File all only on the Inbox, and says how many it would move", async () => {
    signedIn();
    await openList();
    acceptWrites();
    // Not on a topic: those rows are filed already.
    expect(screen.queryByRole("button", { name: /File all/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Inbox/ }));
    fireEvent.click(await screen.findByRole("button", { name: "File all 1" }));

    expect(await screen.findByText(/in its topics now/)).toBeInTheDocument();
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemeespolv001")!.status).toBe("active");
    await screen.findByRole("heading", { name: /All words/ });
  });

  it("refuses to delete while offline, and changes nothing", async () => {
    signedIn();
    await openList();
    vi.spyOn(backendSession, "pushGraph")
      .mockRejectedValue(new AcervoApiError("The Acervo server could not be reached. Local vocabulary remains available.", 0, "offline"));
    fireEvent.click(screen.getByRole("button", { name: /la balsa/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByText(/could not be reached/)).toBeInTheDocument();
    // The entry is still open, still undeleted, and nothing was queued for later.
    expect(screen.getByRole("heading", { name: /la balsa/ })).toBeInTheDocument();
    expect(repository.snapshot().lexemes.find((lexeme) => lexeme.id === "lexemebalsa0001")?.deleted).toBe(false);
  });

  it("switches between the languages the replica holds", async () => {
    signedIn();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Vocabulary language" }));
    fireEvent.click(await screen.findByRole("button", { name: /English/ }));
    expect(await screen.findByRole("button", { name: /turmoil/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /picar/ })).not.toBeInTheDocument();
  });

  it("announces and installs a waiting update explicitly", async () => {
    signedIn();
    await openList();
    act(() => { window.dispatchEvent(new CustomEvent(UPDATE_EVENT, { detail: "ready" })); });
    const gear = screen.getByRole("button", { name: "Open settings; an update is ready" });
    expect(gear).toHaveClass("has-update");
    fireEvent.click(gear);
    expect(await screen.findByRole("button", { name: /Update Acervo/ })).toBeInTheDocument();
  });

  it("offers the native macOS release from browser settings", async () => {
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", platform: "MacIntel", maxTouchPoints: 0
    });
    signedIn();
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: {
        version: "0.1.0", build: "202608270001", file: "Acervo.zip", size: 42, sha256: "abc",
        url: "/api/acervo/downloads/Acervo.zip"
      } })
    } as Response);
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    const link = await screen.findByRole("link", { name: /Download Acervo for macOS/ });
    expect(link).toHaveAttribute("href", "/api/acervo/downloads/Acervo.zip");
    expect(link).toHaveAttribute("download", "Acervo.zip");
  });

  /* The failure this guards against is a configured provider whose key is absent: the button looked
     live, and the only way to learn otherwise was to press it and read a 503. */
  it("turns Capture off with a reason when the server cannot build entries", async () => {
    signedIn();
    serverHealth({ available: false, provider: null, model: null, reason: "GEMINI_API_KEY is not set" });
    const capture = vi.spyOn(backendSession, "captureText");
    await openList();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    const refusal = await screen.findByRole("alert");
    expect(refusal).toHaveTextContent("This server cannot build entries right now.");
    expect(refusal).toHaveTextContent("GEMINI_API_KEY is not set");

    fireEvent.change(screen.getByLabelText(/Paste a word/), { target: { value: "el garfio" } });
    expect(screen.getByRole("button", { name: "Process" })).toBeDisabled();
    expect(capture).not.toHaveBeenCalled();
    // Writing the entry by hand needs no model, so that way out stays open.
    expect(screen.getByRole("button", { name: "Write YAML instead" })).toBeEnabled();
  });

  it("leaves Capture live when the server never answered about it", async () => {
    signedIn();
    vi.spyOn(backendSession, "health").mockRejectedValue(new Error("offline"));
    await openList();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), { target: { value: "el garfio" } });
    // Unknown is not unavailable: a write is allowed to try, and to fail loudly if it must.
    expect(screen.getByRole("button", { name: "Process" })).toBeEnabled();
  });

  it("names the provider and model that build entries, in Settings \u25B8 Providers", async () => {
    /* Moved out of General, not duplicated: General read the *deployment's* provider from health,
       and Models reads the owner's own chain. Two readouts of "what builds an entry" would drift
       the moment a chain was chosen. */
    signedIn();
    vi.spyOn(backendSession, "fetchModels").mockResolvedValue({
      providers: [{
        id: "gemini-free", label: "Gemini (free tier)", kinds: ["text"],
        models: { text: ["gemini/gemini-3.1-flash-lite"] },
        available: true, reason: null, usageUrl: null, notes: null
      }],
      chains: {
        text: { source: "deployment", reason: null, pairs: [] },
        image: { source: "deployment", reason: null, pairs: [] },
        audio: { source: "deployment", reason: null, pairs: [] }
      }
    });
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    const settings = within(await screen.findByRole("dialog", { name: /Settings/ }));

    expect(settings.queryByText(/Entries are built by/)).not.toBeInTheDocument();
    fireEvent.click(settings.getByRole("tab", { name: "Providers" }));
    // Twice on purpose: once as a row in the text chain, once in the credentials table below it.
    expect(await settings.findAllByText("Gemini (free tier)")).toHaveLength(2);
    expect(settings.getByText("gemini/gemini-3.1-flash-lite")).toBeInTheDocument();
  });
});

/* ── the article conversation (`docs/features/article-chat.md`) ──────────────────────────────
   Chat is a consumer of the core: no storage, no second writer, and every change goes through
   `repository.saveArticle` at the entry's own revision. What is asserted here is that shape — that
   a proposal reaches the article as marks and nothing else, that saving is one ordinary write, and
   that undo is the previous document saved again. */

/** A turn that answers in prose and proposes one small edit. */
function mockChat(reply: string, proposal: unknown = null) {
  const chat = vi.spyOn(backendSession, "chat");
  // Reset rather than only re-implement: a spy on a method that was already spied keeps the call
  // history, and "asks nothing" would then be asserting against the previous test's turn.
  chat.mockReset();
  chat.mockResolvedValue({
    reply, followUps: ["One more example"],
    proposal: proposal as never, capture: null, modelId: "gemini-3.1-flash-lite"
  });
  return chat;
}

/** Editing is offered from the YAML view, where the document is. */
async function editAsYaml() {
  fireEvent.click(await screen.findByRole("button", { name: "YAML" }));
  fireEvent.click(await screen.findByRole("button", { name: "Edit as YAML" }));
}

async function openPicar() {
  await openList();
  fireEvent.click(screen.getByRole("button", { name: /picar/ }));
  await screen.findByRole("heading", { name: "picar" });
}

async function ask(question: string) {
  const composer = screen.getByLabelText("Ask about picar");
  fireEvent.change(composer, { target: { value: question } });
  fireEvent.submit(composer.closest("form")!);
}

describe("asking about an article", () => {
  it("offers the dock on a stored article and answers in the thread", async () => {
    signedIn();
    const chat = mockChat("«picar» is to itch, and also to chop.");
    await openPicar();
    await ask("what does this mean?");
    expect(await screen.findByText("«picar» is to itch, and also to chop.")).toBeInTheDocument();
    expect(chat).toHaveBeenCalledTimes(1);
    // The document goes with the question: `yaml.ts` is the only place the projection is understood,
    // so the device serialises it rather than the server.
    const [, request] = chat.mock.calls[0];
    expect(request.subject.kind).toBe("article");
    expect((request.subject as { document: string }).document).toContain("headword: picar");
    // Chosen from the replica before the request left, which is why there is no tool loop.
    expect(request.neighbours?.length).toBeGreaterThan(0);
    // A follow-up is one tap instead of a sentence of typing.
    expect(screen.getByRole("button", { name: "One more example" })).toBeInTheDocument();
  });

  it("says the server is needed when it is unreachable, and asks nothing", async () => {
    signedIn();
    const chat = mockChat("never reached");
    await openList();
    vi.spyOn(backendSession, "pullGraph")
      .mockRejectedValue(new AcervoApiError("unreachable", 0, "offline"));
    render(<App />);
    fireEvent.click((await screen.findAllByRole("button", { name: /picar/ }))[0]);
    await screen.findAllByRole("heading", { name: "picar" });
    // Reading never depends on the server; this is the only part of the article view that does.
    // The second render is the reload; the first is still mounted, so take the latest.
    await waitFor(() => {
      const composers = screen.getAllByLabelText("Ask about picar");
      expect(composers[composers.length - 1]).toBeDisabled();
    });
    expect(chat).not.toHaveBeenCalled();
  });

  it("hides the dock entirely when the server has no model configured", async () => {
    signedIn();
    serverHealth({ available: false, reason: "no key" });
    await openPicar();
    await waitFor(() =>
      expect(screen.queryByLabelText("Ask about picar")).not.toBeInTheDocument());
  });

  it("shows a proposal as marks on the article, writing nothing until asked", async () => {
    signedIn();
    acceptWrites();
    mockChat("Worth noting the contrast.", {
      summary: "Adds a note.",
      ops: [{ op: "set", target: "lexeme", field: "notes", value: ["Not «rascar»."] }]
    });
    await openPicar();
    await ask("add a note about rascar");

    // The proposal arrives as a card in the thread, not as an applied change.
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(await screen.findByText("Not «rascar».")).toBeInTheDocument();
    /* `set notes` takes the whole list, so replacing it is one note added and one removed — and
       both are marked. The removed line is still drawn, struck through: nothing vanishes without
       being seen going. */
    expect(document.querySelector(".review-bar")!.textContent).toContain("2 changes");
    expect(document.querySelector(".mark-add")).not.toBeNull();
    expect(document.querySelector(".mark-cut")).not.toBeNull();
    expect(screen.getByText("The sense is carried by the object, not the verb."))
      .toHaveClass("mark-cut");
    // Nothing is written until a second press.
    expect(backendSession.pushGraph).not.toHaveBeenCalled();
    expect(backendSession.saveArticle).not.toHaveBeenCalled();
  });

  it("saves a reviewed proposal as one ordinary write, and undoes it as another", async () => {
    signedIn();
    acceptWrites();
    mockChat("Worth noting.", {
      summary: "Adds a note.",
      ops: [{ op: "set", target: "lexeme", field: "notes", value: ["Not «rascar»."] }]
    });
    await openPicar();
    await ask("add a note");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: /^Save/ }));

    await waitFor(() => expect(backendSession.saveArticle).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(repository.snapshot().lexemes.find((one) => one.id === "lexemepicar0001")!.notes)
        .toContain("Not «rascar»."));

    // Undo is the previous document, saved again — an ordinary online write like everything else.
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(backendSession.saveArticle).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(repository.snapshot().lexemes.find((one) => one.id === "lexemepicar0001")!.notes)
        .not.toContain("Not «rascar»."));
  });

  it("brings a removed example back with its own id when the save is undone", async () => {
    signedIn();
    acceptWrites();
    mockChat("That one duplicates the other.", {
      summary: "Removes an example.",
      ops: [{ op: "remove", target: "example:examplepicar010", reason: "duplicate" }]
    });
    await openPicar();
    await ask("drop the first example");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: /^Save/ }));
    await waitFor(() => expect(
      repository.snapshot().examples.find((one) => one.id === "examplepicar010")!.deleted).toBe(true));

    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    // A tombstone, not an erasure, and `stamp` sets `deleted: false` — so naming the id again
    // brings the record back rather than creating a second one under a new id.
    await waitFor(() => expect(
      repository.snapshot().examples.find((one) => one.id === "examplepicar010")!.deleted).toBe(false));
  });

  it("drops a proposal rather than applying it when the model names something that is not there", async () => {
    signedIn();
    mockChat("Here you go.", {
      summary: "Edits a sense that does not exist.",
      ops: [{ op: "set", target: "sense:nosuchsense001", field: "domain", value: "cooking" }]
    });
    await openPicar();
    await ask("fix sense three");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(await screen.findByText(/not there, so nothing was changed/)).toBeInTheDocument();
    expect(document.querySelector(".review-bar")).toBeNull();
  });

  it("keeps the dock out of the Add view's own preview", async () => {
    signedIn();
    mockGarfioCapture();
    await openList();
    fireEvent.click(screen.getByRole("button", { name: /Add/ }));
    fireEvent.change(await screen.findByLabelText(/Paste a word/), {
      target: { value: "El disfraz de pirata viene con un garfio." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process" }));
    await screen.findByRole("heading", { name: "el garfio" });
    // The Add view replaces the pane rather than sharing it, so the stored article's dock is gone…
    expect(screen.queryByLabelText("Ask about picar")).not.toBeInTheDocument();
    // …and the one over the unsaved proposal is about the word being added (§8.4).
    expect(screen.getByLabelText("Ask about el garfio")).toBeInTheDocument();
  });
});

/* ── reviewing a proposal: what it marks, and how you get to it ──────────
   Round two. The complaints these pin: a proposal below the fold was invisible, a reworded sentence
   never said which words moved, and a reorder reported "0 changes proposed" over an article that
   had silently renumbered itself. */

describe("stepping through a proposal", () => {
  it("brings the first change into view rather than scrolling to the top", async () => {
    signedIn();
    acceptWrites();
    const seen = vi.spyOn(Element.prototype, "scrollIntoView");
    mockChat("Fixed.", {
      summary: "Sharpens the second sense.",
      ops: [{ op: "set", target: "sense:sensepicarchop0", field: "domain", value: "culinary" }]
    });
    await openPicar();
    await ask("tighten the second sense");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));

    await waitFor(() => expect(seen).toHaveBeenCalled());
    const target = seen.mock.instances[seen.mock.instances.length - 1] as Element;
    expect(target.getAttribute("data-record")).toBe("sensepicarchop0");
  });

  it("walks the changes with next and previous, and clamps at both ends", async () => {
    signedIn();
    acceptWrites();
    mockChat("Two things.", {
      summary: "Two changes.",
      ops: [
        { op: "set", target: "sense:sensepicaritch0", field: "domain", value: "medicine" },
        { op: "set", target: "sense:sensepicarchop0", field: "domain", value: "culinary" }
      ]
    });
    await openPicar();
    await ask("tidy both senses");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));

    expect(await screen.findByText("1/2")).toBeInTheDocument();
    // Previous is unavailable on the first change.
    expect(screen.getByRole("button", { name: "Previous change" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next change" }));
    expect(await screen.findByText("2/2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next change" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous change" }));
    expect(await screen.findByText("1/2")).toBeInTheDocument();
  });

  it("counts and marks a sense that only moved", async () => {
    signedIn();
    acceptWrites();
    mockChat("Reordered.", {
      summary: "Puts the cooking sense first.",
      ops: [{ op: "reorder", target: "senses", ids: ["sensepicarchop0", "sensepicaritch0"] }]
    });
    await openPicar();
    await ask("put the cooking sense first");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));

    // It used to say "0 changes proposed" over an article that had renumbered itself.
    const bar = await screen.findByText(/1 change/);
    expect(bar).toBeInTheDocument();
    expect(document.querySelector(".mark-moved")).not.toBeNull();
    // A move gets no tint, because none of its content changed.
    expect(document.querySelector(".mark-moved .field-change")).toBeNull();
  });

  it("shows which words moved when a sentence is reworded", async () => {
    signedIn();
    acceptWrites();
    mockChat("Tidied.", {
      summary: "Rewords the first example.",
      ops: [{
        op: "set", target: "example:examplepicar010", field: "text",
        value: "Me pica mucho la nariz."
      }]
    });
    await openPicar();
    await ask("make the first example stronger");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));

    const block = await waitFor(() => {
      const found = document.querySelector('[data-record="examplepicar010"]');
      expect(found).not.toBeNull();
      return found!;
    });
    // The inserted word is marked, and the sentence still reads as one sentence.
    expect(block.querySelector(".wd-ins")!.textContent).toContain("mucho");
    expect(block.querySelector(".t")!.textContent).toBe("Me pica mucho la nariz.");
  });

  it("reads a reworded note as one change with a word diff, not a delete and an add", async () => {
    signedIn();
    acceptWrites();
    mockChat("Tidied the note.", {
      summary: "Rewords the note.",
      ops: [{
        op: "set", target: "lexeme", field: "notes",
        value: ["The sense is carried by the object, not by the verb."]
      }]
    });
    await openPicar();
    await ask("tidy the note");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));

    expect(await screen.findByText(/1 change/)).toBeInTheDocument();
    const note = document.querySelector('[data-note="0"]')!;
    expect(note.className).toContain("mark-change");
    expect(note.querySelector(".wd-ins")!.textContent).toContain("by");
  });
});

describe("the conversation at its largest", () => {
  it("takes the pane and hands the height to the sheet", async () => {
    signedIn();
    mockChat("…");
    await openPicar();
    // Focusing opens it to the content-sized detent; the grabber then takes it to full.
    fireEvent.focus(screen.getByLabelText("Ask about picar"));
    fireEvent.click(await screen.findByRole("button", { name: "Expand the conversation" }));

    // `display: none` is CSS, which jsdom does not load — the contract is the class, and the class
    // is what stops the region scrolling and hands the height to the sheet.
    await waitFor(() => expect(document.querySelector(".pane.ask-only")).not.toBeNull());
    expect(document.querySelector(".main.composing")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Shrink the conversation" }));
    await waitFor(() => expect(document.querySelector(".pane.ask-only")).toBeNull());
    expect(document.querySelector(".main.composing")).toBeNull();
  });
});

describe("a conversation that edits what it just proposed", () => {
  it("keeps the follow-ups out of the way until the card is answered", async () => {
    signedIn();
    acceptWrites();
    mockChat("Added it.", {
      summary: "Adds an example.",
      ops: [{ op: "add", target: "example", in: "sensepicaritch0", value: { text: "Me pica todo." } }]
    });
    await openPicar();
    await ask("add an example");

    // One decision at a time: the card is the thing to answer, and a follow-up beside it is an
    // invitation to forget the edit.
    expect(await screen.findByRole("button", { name: "Review" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "One more example" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    /* Review collapses the sheet, because the answer to an editing turn is the article. The
       follow-ups are waiting when the conversation is reopened — which is the point: they are next
       steps, and there is no next step until the edit has been looked at. */
    fireEvent.focus(screen.getByLabelText("Ask about picar"));
    expect(await screen.findByRole("button", { name: "One more example" })).toBeInTheDocument();
  });

  it("builds a second turn on the first, and never on the ghosts drawn for the reader", async () => {
    signedIn();
    acceptWrites();
    const chat = mockChat("Removed it.", {
      summary: "Removes the first example.",
      ops: [{ op: "remove", target: "example:examplepicar010", reason: "duplicate" }]
    });
    await openPicar();
    await ask("drop the first example");
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    await screen.findByText(/1 change/);

    await ask("and tidy the note");
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(2));
    /* `diff.shown` puts the removed example back so it can be drawn struck through. Sending that
       would show the model a record the proposal has already taken away — and applying the next
       turn to it would quietly resurrect it. */
    const [, second] = chat.mock.calls[1];
    const document_ = (second.subject as { document: string }).document;
    expect(document_).not.toContain("Me pica la nariz");
    // Its id does survive, as the anchor of the picture that illustrates it — which is a fact about
    // the picture, not a resurrection of the sentence.
    expect(document_).toContain("exampleId: examplepicar010");
  });
});

/* ── a photographed sentence folded into a word already held (`docs/features/photo-capture.md`) ──
   The conversation carries text and a model may not name a photo, so the device attaches it. */
describe("folding a photographed sentence into a word already held", () => {
  const PHOTO = "photos/owner0000000001/0123456789abcdef.jpg";
  const box = (x: number): [number, number][] => [[x, 0.1], [x + 0.1, 0.1], [x + 0.1, 0.14], [x, 0.14]];

  it("keeps the photo with the sentence the conversation adds", async () => {
    signedIn();
    acceptWrites();
    // A spy made again keeps the earlier tests' calls; only this test's save is asserted on.
    vi.mocked(backendSession.saveArticle).mockClear();
    if (!("PointerEvent" in window)) Object.defineProperty(window, "PointerEvent", { value: MouseEvent, configurable: true });
    URL.createObjectURL = vi.fn(() => "blob:photo");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(backendSession, "warmPhoto").mockResolvedValue({});
    vi.spyOn(backendSession, "readPhoto").mockResolvedValue({
      photoRef: PHOTO, width: 1000, height: 500, language: "es", vocabulary: true,
      readBy: { provider: "google-vision", model: "document-text-detection" },
      text: "Me pica mucho.",
      words: [
        { id: "w0", text: "Me", polygons: [box(0.1)], confidence: 0.95, lineId: "l0", start: 0, end: 2 },
        { id: "w1", text: "pica", polygons: [box(0.25)], confidence: 0.95, lineId: "l0", start: 3, end: 7 },
        { id: "w2", text: "mucho.", polygons: [box(0.4)], confidence: 0.95, lineId: "l0", start: 8, end: 14 }
      ],
      lines: [{ id: "l0", polygon: [[0.1, 0.1], [0.5, 0.1], [0.5, 0.14], [0.1, 0.14]], wordIds: ["w0", "w1", "w2"] }],
      sentences: [{ id: "s0", text: "Me pica mucho.", wordIds: ["w0", "w1", "w2"], start: 0, end: 14,
        truncatedStart: false, truncatedEnd: false }]
    });
    vi.spyOn(backendSession, "resolveCapture").mockResolvedValue({
      resolution: {
        language: "es", headword: "picar", lemma: "picar", pos: "verb",
        sentences: [{ text: "Me pica mucho.", translation: null }], note: null, consumedLines: 1,
        consumedText: null, gloss: "to itch"
      },
      duplicates: [{ id: "lexemepicar0001", headword: "picar", shortGloss: "to itch; to chop" }],
      foldable: { sentences: [{ text: "Me pica mucho.", translation: null }], reference: false, note: null }
    });
    mockChat("Worth keeping.", {
      summary: "Adds the sentence.",
      ops: [{ op: "add", target: "attestation", ref: "a1", value: { text: "Me pica mucho." } }]
    });
    await openList();

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("button", { name: "Photo" }));
    const input = document.querySelector<HTMLInputElement>("input[type=file]")!;
    fireEvent.change(input, { target: { files: [new File(["x"], "page.png", { type: "image/png" })] } });
    await screen.findByAltText("The photo being read");
    const frame = document.querySelector<HTMLElement>(".photo-frame")!;
    frame.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.pointerDown(frame, { clientX: 290, clientY: 60, pointerId: 1 });
    fireEvent.pointerUp(frame, { clientX: 290, clientY: 60, pointerId: 1 });
    fireEvent.click(await screen.findByRole("button", { name: "Fold this sentence in" }));

    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: /^Save/ }));
    await waitFor(() => expect(backendSession.saveArticle).toHaveBeenCalledTimes(1));
    const [, draft] = vi.mocked(backendSession.saveArticle).mock.calls[0];
    const kept = draft.attestations.find((one) => one.text === "Me pica mucho.")!;
    expect(kept.photoRef).toBe(PHOTO);
    expect(kept.photoRegion).not.toBeNull();
  });
});
