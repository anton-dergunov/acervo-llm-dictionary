import { useEffect, useState } from "react";
import type { CaptureHealth } from "./api";
import ActivitySettings from "./ActivitySettings";
import SchedulePanel from "./SchedulePanel";
import AnkiPanel from "./AnkiPanel";
import { TopicEditor, VocabularyEditor } from "./Configuration";
import DictionaryPanel from "./DictionaryPanel";
import ClipPanel from "./ClipPanel";
import LoopPanel from "./LoopPanel";
import StoryPanel from "./StoryPanel";
import ImagePanel from "./ImagePanel";
import ModelPanel from "./ModelPanel";
import PronunciationPanel from "./PronunciationPanel";
import RulesPanel from "./RulesPanel";
import { fetchMacRelease, type MacRelease } from "./macRelease";
import { installUpdate, isNativeHost, shouldOfferMacApplication, type UpdateStage } from "./pwa";
import type { ReplicaSnapshot } from "./repository";
import { syncEngine, type SyncStatus } from "./sync";
import { SyncPanel } from "./SyncStatus";
import { ExportPanel, ImportPanel } from "./TransferPanel";
import { appVersionLabel } from "./version";
import {
  articleViewPreference, editorPreferences, setArticleViewPreference, setEditorPreference,
  type ArticleViewPreference, type EditorPreferences
} from "./editorPreferences";

/** Typing the word is the point: this is the one action that cannot be undone by re-syncing. */
const CONFIRMATION = "DELETE";

export type Page =
  | "general" | "vocabularies" | "topics" | "models" | "rules" | "images" | "pronunciation" | "loops" | "stories" | "clips" | "dictionaries" | "editor"
  | "activity" | "schedule" | "anki" | "sync" | "data";

export default function Settings({ update, email, status, snapshot, language, captureHealth, page: opensOn, arm, onSignOut, onClose, onNotify, onChanged }: {
  update?: UpdateStage;
  email: string;
  /**
   * What this server builds entries with, or `undefined` while that is unknown.
   *
   * Still read here because the Capture control is gated on it before anything is chosen, but no
   * longer *shown* here: Settings ▸ Models is where a provider is named now, and it reads the
   * owner's own chain rather than the deployment's. Two readouts would have drifted.
   */
  captureHealth?: CaptureHealth;
  status: SyncStatus;
  snapshot: ReplicaSnapshot | null;
  /** Which vocabulary the topic counts are shown for — the one the list is currently filtered to. */
  language: string;
  /** Which section to open on, so the Mac menu can point straight at the one it names. */
  page?: Page;
  /** A menu item ending in "…" promises a dialog, so Delete All Words opens its own. */
  arm?: "delete" | null;
  onSignOut(): void;
  onClose(): void;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  /* On the Mac the app updates itself and remembers its own server address, so repeating either
     here would offer a second, conflicting control for something this window does not own. What
     stays is everything about the vocabulary, which the native host deliberately does not own. */
  const native = isNativeHost();
  const offerMacApplication = shouldOfferMacApplication();
  const [macRelease, setMacRelease] = useState<MacRelease | null>();
  const [releaseError, setReleaseError] = useState(false);
  const [page, setPage] = useState<Page>(opensOn ?? "general");
  const [editor, setEditor] = useState(editorPreferences);
  const [articleView, setArticleView] = useState(articleViewPreference);

  function changeEditor(name: keyof EditorPreferences, value: boolean) {
    setEditorPreference(name, value);
    setEditor(editorPreferences());
  }

  const [confirming, setConfirming] = useState(arm === "delete");
  const [typed, setTyped] = useState("");
  const [working, setWorking] = useState(false);

  const liveLexemes = snapshot?.lexemes.filter((lexeme) => !lexeme.deleted).length ?? 0;
  const liveTopics = snapshot?.topics.filter((topic) => !topic.deleted).length ?? 0;

  async function run(action: () => Promise<void>, failure: string) {
    setWorking(true);
    try { await action(); }
    catch (error) { onNotify(error instanceof Error ? error.message : failure); }
    finally { setWorking(false); }
  }

  /**
   * `syncNow` reports by resolving, not by throwing, so `run` would show nothing either way. On a
   * server that fails every request the panel's text never changes, and the button looked broken.
   */
  async function refresh() {
    setWorking(true);
    try {
      const result = await syncEngine.syncNow(true);
      onNotify(result.state === "idle"
        ? "Up to date with the server."
        : result.message ?? "The vocabulary could not be refreshed.");
    } finally { setWorking(false); }
  }

  async function deleteEverything() {
    await run(() => syncEngine.resetWords(), "The words could not be deleted.");
    setConfirming(false);
    setTyped("");
  }

  useEffect(() => {
    if (!offerMacApplication) return;
    const controller = new AbortController();
    void fetchMacRelease(controller.signal)
      .then(setMacRelease)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setReleaseError(true);
      });
    return () => controller.abort();
  }, [offerMacApplication]);

  const pages: { id: Page; label: string }[] = [
    { id: "general", label: "General" },
    { id: "vocabularies", label: "Vocabularies" },
    { id: "topics", label: "Topics" },
    { id: "models", label: "Providers" },
    { id: "rules", label: "Rules" },
    { id: "images", label: "Pictures" },
    { id: "pronunciation", label: "Pronunciation" },
    { id: "loops", label: "Loops" },
    { id: "stories", label: "Stories" },
  { id: "clips", label: "Clips" },
    { id: "dictionaries", label: "Dictionaries" },
    { id: "editor", label: "Reading" },
    { id: "activity", label: "Activity" },
    { id: "schedule", label: "Schedule" },
    { id: "anki", label: "Anki" },
    { id: "sync", label: "Sync" },
    { id: "data", label: "Data" }
  ];

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header><h2 id="settings-title">Settings</h2><button className="close" onClick={onClose} aria-label="Close settings">×</button></header>

      {/* One page at a time. Everything here used to be one column, which grew past the window the
          moment topics and vocabularies became editable — and the dialog could not scroll, so the
          controls at the bottom were simply unreachable. */}
      <nav className="settings-nav" role="tablist" aria-label="Settings sections">
        {pages.map((entry) => <button
          key={entry.id} role="tab" id={`settings-tab-${entry.id}`}
          aria-selected={page === entry.id} aria-controls="settings-panel"
          className={page === entry.id ? "on" : ""}
          onClick={() => setPage(entry.id)}
        >{entry.label}</button>)}
      </nav>

      <div className="settings-body" id="settings-panel" role="tabpanel" aria-labelledby={`settings-tab-${page}`}>
        {page === "general" && <>
          <div className="update-status">
            <strong>Signed in as {email}</strong>
            <span>{liveLexemes} {liveLexemes === 1 ? "entry" : "entries"} across {liveTopics} {liveTopics === 1 ? "topic" : "topics"} on this device.</span>
          </div>
          {!native && update === "ready" && <button className="update-action" onClick={() => void installUpdate()}><strong>Update Acervo</strong><span>The update is ready. Acervo will reopen with the new version.</span></button>}
          {!native && update === "downloading" && <div className="update-status"><strong>Downloading an update…</strong><span>You can keep using Acervo while it finishes.</span></div>}
          {!native && !update && <div className="update-status"><strong>Acervo is up to date</strong><span>This is the newest version available from this server.</span></div>}
          {offerMacApplication && macRelease && <a className="download-action" href={macRelease.url} download={macRelease.file}>
            <strong>Download Acervo for macOS</strong>
            <span>Version {macRelease.version}, build {macRelease.build}</span>
          </a>}
          {offerMacApplication && macRelease === null && <div className="update-status"><strong>macOS application</strong><span>No native release has been published by this server yet.</span></div>}
          {offerMacApplication && macRelease === undefined && !releaseError && <div className="update-status"><strong>macOS application</strong><span>Checking for a native release…</span></div>}
          {offerMacApplication && releaseError && <div className="update-status"><strong>macOS application</strong><span>The native release could not be checked right now.</span></div>}
          {captureHealth && !captureHealth.available && <div className="update-status">
            <strong>This server cannot build entries</strong>
            <span>{captureHealth.reason}. Settings {"\u25B8"} Providers says what it can use.</span>
          </div>}
          {native && <div className="update-status">
            <strong>Updates and server address</strong>
            <span>Acervo ▸ Settings, in the menu bar.</span>
          </div>}
          <button className="tb-btn" onClick={onSignOut}>Sign out</button>
          <p className="version">Version {appVersionLabel()}</p>
        </>}

        {page === "editor" && <section className="config-section">
          <h3>Articles</h3>
          <p className="config-help">
            How a word opens. Page is the whole entry, scrolled, and is where you can ask about it and
            edit it. Cards shows one meaning and one sentence at a time, swiped left and right. This
            describes this device, not your vocabulary.
          </p>
          <div className="config-choices" role="radiogroup" aria-label="Open articles in">
            {([
              ["auto", "Depends on the device", "Cards on a touch screen, Page with a mouse or trackpad."],
              ["page", "Page", "Always the whole entry."],
              ["cards", "Cards", "Always one thing at a time."]
            ] as [ArticleViewPreference, string, string][]).map(([value, title, help]) =>
              <label key={value} className="config-switch">
                <input
                  type="radio" name="article-view" value={value} checked={articleView === value}
                  onChange={() => { setArticleViewPreference(value); setArticleView(value); }}
                />
                <span><strong>{title}</strong><span>{help}</span></span>
              </label>)}
          </div>

          <h3>YAML editor</h3>
          <p className="config-help">
            How entries are shown when you read or edit them as YAML. These describe this device,
            not your vocabulary, so they are not shared with your other devices.
          </p>
          <label className="config-switch">
            <input
              type="checkbox" checked={editor.wrap}
              onChange={(event) => changeEditor("wrap", event.target.checked)}
            />
            <span>
              <strong>Wrap long lines</strong>
              <span>Off, a long definition runs past the edge and the editor scrolls sideways to it.</span>
            </span>
          </label>
          <label className="config-switch">
            <input
              type="checkbox" checked={editor.numbers}
              onChange={(event) => changeEditor("numbers", event.target.checked)}
            />
            <span>
              <strong>Show line numbers</strong>
              <span>Useful when a document is refused: the reason names the line it is on.</span>
            </span>
          </label>
        </section>}

        {page === "models" && <ModelPanel onNotify={onNotify} />}

        {page === "rules" && <RulesPanel onNotify={onNotify} />}

        {page === "images" && <ImagePanel onNotify={onNotify} />}

        {page === "pronunciation" && <PronunciationPanel onNotify={onNotify} />}

        {page === "loops" && <LoopPanel onNotify={onNotify} />}
        {page === "stories" && <StoryPanel onNotify={onNotify} />}
      {page === "clips" && <ClipPanel onNotify={onNotify} />}

        {page === "dictionaries" && <DictionaryPanel onNotify={onNotify} />}

        {page === "activity" && <ActivitySettings snapshot={snapshot} onNotify={onNotify} />}

        {page === "schedule" && <SchedulePanel onNotify={onNotify} />}

        {page === "anki" && <AnkiPanel onNotify={onNotify} />}

        {page === "vocabularies" && snapshot && <VocabularyEditor snapshot={snapshot} onNotify={onNotify} onChanged={onChanged} />}
        {page === "topics" && snapshot && <TopicEditor snapshot={snapshot} language={language} onNotify={onNotify} onChanged={onChanged} />}

        {page === "sync" && <SyncPanel
          status={status}
          lexemeCount={liveLexemes}
          onSyncNow={() => void refresh()}
          onDownloadAgain={() => void run(() => syncEngine.downloadAgain(), "The vocabulary could not be downloaded again.")}
        />}

        {page === "data" && <>
          {snapshot && <ExportPanel snapshot={snapshot} />}
          <ImportPanel onChanged={onChanged} />
          <div className="danger-zone">
          <h3>Delete all words</h3>
          {!confirming && <>
            <p>Removes every entry from the server and from every device you use. This needs a
              connection to the server, like any other change.</p>
            <button className="tb-btn danger" onClick={() => setConfirming(true)}>Delete all words…</button>
          </>}
          {confirming && <>
            <p role="alert">
              This deletes <strong>{liveLexemes} {liveLexemes === 1 ? "entry" : "entries"}</strong> and
              everything attached to them — senses, examples, the sentences you captured, and study
              history. Your other devices are emptied the next time they sync.
            </p>
            <p role="alert">
              Export first if you have not already. Syncing again cannot bring any of this back.
            </p>
            <label htmlFor="delete-confirmation">Type {CONFIRMATION} to confirm</label>
            <input
              id="delete-confirmation" value={typed} autoComplete="off"
              onChange={(event) => setTyped(event.target.value)}
            />
            <div className="sync-actions">
              <button className="tb-btn" onClick={() => { setConfirming(false); setTyped(""); }}>Cancel</button>
              <button
                className="tb-btn danger" disabled={typed.trim() !== CONFIRMATION || working}
                onClick={() => void deleteEverything()}
              >Delete all words</button>
            </div>
          </>}
          </div>
        </>}

        {(page === "vocabularies" || page === "topics") && !snapshot
          && <p className="config-help">Opening your vocabulary…</p>}
      </div>
    </section>
  </div>;
}
