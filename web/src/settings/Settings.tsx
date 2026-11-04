/**
 * Settings: one window of a fixed size, its pages listed in five groups.
 *
 * The design is `docs/features/settings.md`, and the prototype is `design/ui-prototype/settings.html`.
 * Three things here are load-bearing:
 *
 * - **The size is the screen's, not the page's.** Full screen on a phone, nearly on a tablet, a
 *   generous resizable window with a mouse. A page switch must never move or resize anything, which
 *   the old dialog — sized by whatever page was in it — did on every click.
 * - **One DOM at every width.** Wide, the list is a sidebar beside the page; narrow, it is a page of
 *   its own and a page drills in from it. `data-level` says which a narrow window shows, and only
 *   the stylesheet knows the width.
 * - **Pages show what they last knew.** The server-backed ones read through `cache.ts`, so leaving
 *   a page and coming back costs nothing and nothing flashes.
 */

import { useEffect, useLayoutEffect, useRef, useState, type ComponentType, type RefObject } from "react";
import type { CaptureHealth } from "../api";
import {
  ArchiveIcon, BackIcon, BookIcon, CardsIcon, ChipIcon, CloseIcon, FlagIcon, ForwardIcon, GlobeIcon,
  OpenBookIcon, PencilIcon, PictureIcon, PulseIcon, RepeatIcon, SpeakerIcon, SunIcon, SyncIcon, TagIcon,
  VideoIcon
} from "../icons";
import type { UpdateStage } from "../pwa";
import type { ReplicaSnapshot } from "../repository";
import { syncEngine, type SyncStatus } from "../sync";
import { SyncPanel } from "../SyncStatus";
import ActivitySettings from "./ActivitySettings";
import AnkiPanel from "./AnkiPanel";
import { prefetchSettings } from "./cache";
import ClipPanel from "./ClipPanel";
import { TopicEditor, VocabularyEditor } from "./Configuration";
import DataPage from "./DataPage";
import DictionaryPanel from "./DictionaryPanel";
import GeneralPage from "./GeneralPage";
import ImagePanel from "./ImagePanel";
import { Placeholder, SubPageContext, type SubPage } from "./kit";
import LoopPanel from "./LoopPanel";
import ModelPanel from "./ModelPanel";
import PronunciationPanel from "./PronunciationPanel";
import ReadingPage from "./ReadingPage";
import RulesPanel from "./RulesPanel";
import StoryPanel from "./StoryPanel";

export type Page =
  | "general" | "reading" | "dictionaries"
  | "vocabularies" | "topics" | "rules"
  | "pictures" | "pronunciation" | "clips" | "loops" | "stories"
  | "providers" | "activity" | "anki"
  | "sync" | "data";

const GROUPS: { title: string; pages: { id: Page; label: string; icon: ComponentType }[] }[] = [
  { title: "General", pages: [
    { id: "general", label: "General", icon: SunIcon },
    { id: "reading", label: "Reading", icon: BookIcon },
    { id: "dictionaries", label: "Dictionaries", icon: GlobeIcon }
  ] },
  { title: "Vocabulary", pages: [
    { id: "vocabularies", label: "Vocabularies", icon: FlagIcon },
    { id: "topics", label: "Topics", icon: TagIcon },
    { id: "rules", label: "Rules", icon: PencilIcon }
  ] },
  { title: "Media", pages: [
    { id: "pictures", label: "Pictures", icon: PictureIcon },
    { id: "pronunciation", label: "Pronunciation", icon: SpeakerIcon },
    { id: "clips", label: "Clips", icon: VideoIcon },
    { id: "loops", label: "Loops", icon: RepeatIcon },
    { id: "stories", label: "Stories", icon: OpenBookIcon }
  ] },
  { title: "Server", pages: [
    { id: "providers", label: "Providers", icon: ChipIcon },
    { id: "activity", label: "Activity", icon: PulseIcon },
    { id: "anki", label: "Anki", icon: CardsIcon }
  ] },
  { title: "Data", pages: [
    { id: "sync", label: "Sync", icon: SyncIcon },
    { id: "data", label: "Data", icon: ArchiveIcon }
  ] }
];

const LABELS = Object.fromEntries(GROUPS.flatMap((group) => group.pages.map((entry) => [entry.id, entry.label]))) as Record<Page, string>;

/* Per-device conveniences, so every read and write is allowed to fail: a private window may refuse
   storage, and Settings must open regardless. */
const PAGE_KEY = "acervo-settings-page";
const SIZE_KEY = "acervo-settings-size";

function remembered<T>(key: string, read: (raw: string) => T | null): T | null {
  try { const raw = localStorage.getItem(key); return raw === null ? null : read(raw); } catch { return null; }
}
function remember(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* a convenience, not a record */ }
}

/** With a mouse, the window keeps the size you dragged it to; a touch screen's is the screen's. */
const RESIZABLE = "(pointer: fine) and (min-width: 761px)";

function useRememberedSize(window: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const node = window.current;
    if (!node || typeof matchMedia !== "function" || !matchMedia(RESIZABLE).matches) return;
    const size = remembered(SIZE_KEY, (raw) => {
      const [width, height] = raw.split("x").map(Number);
      return width > 0 && height > 0 ? { width, height } : null;
    });
    if (size) {
      node.style.width = `${size.width}px`;
      node.style.height = `${size.height}px`;
    }
    /* Only a drag of the corner is remembered. Watching for any change in size would also record
       the window following the screen, and then it would stop following it. */
    let before = "";
    const down = (event: MouseEvent) => {
      if (event.target === node) before = `${node.offsetWidth}x${node.offsetHeight}`;
    };
    const up = () => {
      const after = `${node.offsetWidth}x${node.offsetHeight}`;
      if (before && after !== before) remember(SIZE_KEY, after);
      before = "";
    };
    node.addEventListener("mousedown", down);
    document.addEventListener("mouseup", up);
    return () => { node.removeEventListener("mousedown", down); document.removeEventListener("mouseup", up); };
  }, [window]);
}

export default function Settings({ update, email, status, snapshot, language, captureHealth, page: opensOn, arm, onSignOut, onClose, onNotify, onChanged }: {
  update?: UpdateStage;
  email: string;
  /** What this server builds entries with, or `undefined` while that is unknown. */
  captureHealth?: CaptureHealth;
  status: SyncStatus;
  snapshot: ReplicaSnapshot | null;
  /** Which vocabulary the topic counts are shown for — the one the list is currently filtered to. */
  language: string;
  /**
   * Which page to open on, when something asked for one: the Mac menu, Delete All Words…, the sync
   * chip. Without one a wide window reopens the last page and a narrow one opens on the list.
   */
  page?: Page;
  /** A menu item ending in "…" promises a dialog, so Delete All Words opens its own. */
  arm?: "delete" | null;
  onSignOut(): void;
  onClose(): void;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  const [page, setPage] = useState<Page>(() =>
    opensOn ?? remembered(PAGE_KEY, (raw) => raw in LABELS ? raw as Page : null) ?? "general");
  const [level, setLevel] = useState<"list" | "page">(opensOn ? "page" : "list");
  const [sub, setSub] = useState<SubPage | null>(null);
  const windowRef = useRef<HTMLElement>(null);
  useRememberedSize(windowRef);

  useEffect(() => { prefetchSettings(); }, []);

  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  function choose(next: Page) {
    setPage(next);
    setSub(null);
    setLevel("page");
    remember(PAGE_KEY, next);
  }

  function back() {
    if (sub) setSub(null); else setLevel("list");
  }

  const liveLexemes = snapshot?.lexemes.filter((lexeme) => !lexeme.deleted).length ?? 0;

  /**
   * `syncNow` reports by resolving, not by throwing. On a server that fails every request the
   * page's text never changes, and the button looked broken — so the outcome is always said.
   */
  async function syncNow() {
    const result = await syncEngine.syncNow(true);
    onNotify(result.state === "idle" ? "Up to date with the server." : result.message ?? "The vocabulary could not be refreshed.");
  }

  async function downloadAgain() {
    try { await syncEngine.downloadAgain(); }
    catch (error) { onNotify(error instanceof Error ? error.message : "The vocabulary could not be downloaded again."); }
  }

  const content = (() => {
    switch (page) {
      case "general": return <GeneralPage
        update={update} email={email} snapshot={snapshot} captureHealth={captureHealth}
        onSignOut={onSignOut} onNotify={onNotify}
      />;
      case "reading": return <ReadingPage />;
      case "dictionaries": return <DictionaryPanel onNotify={onNotify} />;
      case "vocabularies": return snapshot
        ? <VocabularyEditor snapshot={snapshot} onNotify={onNotify} onChanged={onChanged} />
        : <Placeholder />;
      case "topics": return snapshot
        ? <TopicEditor snapshot={snapshot} language={language} onNotify={onNotify} onChanged={onChanged} />
        : <Placeholder />;
      case "rules": return <RulesPanel onNotify={onNotify} />;
      case "pictures": return <ImagePanel onNotify={onNotify} />;
      case "pronunciation": return <PronunciationPanel onNotify={onNotify} />;
      case "clips": return <ClipPanel onNotify={onNotify} />;
      case "loops": return <LoopPanel onNotify={onNotify} />;
      case "stories": return <StoryPanel onNotify={onNotify} />;
      case "providers": return <ModelPanel onNotify={onNotify} />;
      case "activity": return <ActivitySettings snapshot={snapshot} onNotify={onNotify} />;
      case "anki": return <AnkiPanel onNotify={onNotify} />;
      case "sync": return <SyncPanel
        status={status} lexemeCount={liveLexemes}
        onSyncNow={() => void syncNow()} onDownloadAgain={() => void downloadAgain()}
      />;
      case "data": return <DataPage snapshot={snapshot} arm={arm} onNotify={onNotify} onChanged={onChanged} />;
    }
  })();

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section
      ref={windowRef} className="settings-window" role="dialog" aria-modal="true"
      aria-labelledby="settings-title" data-level={level}
    >
      <button type="button" className="close" onClick={onClose} aria-label="Close settings"><CloseIcon /></button>
      <div className="prefs-frame">
        <aside className="prefs-side">
          <header className="prefs-head"><h2 id="settings-title">Settings</h2></header>
          <div className="prefs-scroll">
            <nav className="prefs-nav" aria-label="Settings sections">
              {GROUPS.map((group) => <div key={group.title}>
                <h4>{group.title}</h4>
                <ul>
                  {group.pages.map(({ id, label, icon: Icon }) => <li key={id}>
                    <button type="button" aria-current={id === page ? "page" : undefined} onClick={() => choose(id)}>
                      <span className="prefs-icon"><Icon /></span>
                      <span>{label}</span>
                      <span className="chev"><ForwardIcon /></span>
                    </button>
                  </li>)}
                </ul>
              </div>)}
            </nav>
          </div>
        </aside>

        <div className="prefs-main" role="region" aria-labelledby="settings-page-title">
          <header className="prefs-head">
            {sub
              ? <button type="button" className="prefs-back" onClick={back}><BackIcon />{LABELS[page]}</button>
              : <button type="button" className="prefs-back to-list" onClick={back}><BackIcon />Settings</button>}
            <h3 id="settings-page-title">{sub?.title ?? LABELS[page]}</h3>
          </header>
          {/* Keyed by where it is, so every page and sub-page starts scrolled to its top. */}
          <div className="prefs-scroll" key={`${page}/${sub?.id ?? ""}`}>
            <div className="prefs-page">
              <SubPageContext.Provider value={{ sub, open: setSub, close: () => setSub(null) }}>
                {content}
              </SubPageContext.Provider>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>;
}
