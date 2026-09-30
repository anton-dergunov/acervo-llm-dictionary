import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type {
  CaptureFoldable, CaptureHealth, CaptureRequest, CaptureResult, ChatResult, ChatTurn, PhotoReading,
  QuickLookUp, QuickLookUpRequest
} from "./api";
import AskDock from "./AskDock";
import {
  applyOps, diffDrafts, EditRefused, type DraftDiff, type EditOp
} from "./articleEdit";
import Composer from "./Composer";
import type { VocabularyGraph } from "./domain";
import { useEditorPreferences } from "./editorPreferences";
import { CaretIcon, CloseIcon } from "./icons";
import LexemeArticle, { type MarkSlot } from "./LexemeArticle";
import { newId } from "./ids";
import { seed as seedPicture } from "./media";
import PhotoCapture, { type KeptPhoto, type PhotoAdd } from "./PhotoCapture";
import { articleFromDraft, type Article } from "./selectors";
import { ValidationPanel } from "./ValidationPanel";
import {
  parseArticle, YAML_TEMPLATE, yamlForDraft, YamlProblems,
  type ArticleDraft, type YamlProblem
} from "./yaml";

// CodeMirror is the largest dependency in the bundle and is only needed once the YAML tab is
// actually opened, so it is loaded on demand rather than with everything else.
const EditorSurface = lazy(() => import("./YamlPane").then((module) => ({ default: module.EditorSurface })));

/** `capture` is the Text tab. Photo is never where Add opens: it is an occasional way in, chosen. */
export type AddTab = "capture" | "photo" | "article" | "yaml";

const noop = () => undefined;

/** Why a provider was passed over, in words rather than in the chain's own vocabulary. */
const REASONS: Record<string, string> = {
  rate_limited: "out of allowance for now",
  unavailable: "the provider had a problem",
  unreachable: "could not be reached"
};

/**
 * A composition that starts somewhere other than an empty box — today, a word taken from an
 * external dictionary.
 *
 * It carries what the reader was looking at so the generator is grounded on that rather than on the
 * word alone, and it processes itself on arrival: the choice was already made on the article, and
 * landing on a filled-in form with a Process button to press again would be asking twice.
 */
export interface CaptureSeed {
  headword: string;
  reference: string;
  referenceMode: "faithful" | "expand" | null;
  note: string | null;
  /** Which dictionaries the reference came from, so the panel can name them. */
  sources: string[];
}

/**
 * Capture (`docs/features/capture.md`), the rendered proposal, and the YAML escape hatch — one
 * view, because they are three views of one thing.
 *
 * A view rather than a dialog: composing an entry is work, not an interruption, and it wants the
 * whole content area — which is also the only shape that survives a phone, where a centred overlay
 * never had room for a header, an editor and its buttons at once.
 *
 * Processing does not save anything. It returns a proposal, which is rendered as an ordinary
 * article — the same component a stored entry uses, so approving a generated entry is reading the
 * thing you will get rather than reading its serialization. YAML sits behind it as the edit surface
 * and stays the document of record here: the Article tab is derived from the editor text on every
 * keystroke, so the preview and the editor cannot drift apart. Saving goes by exactly the path a
 * hand-written document takes, so there is one writer, one validator and one diff.
 */
export default function AddView({
  tab, onTab, graph, problems, busy, seed, captureHealth,
  onClose, onCreate, onCapture, onOpenLexeme, onFoldIn, onChat, onReadPhoto, onStorePhoto, onLookUp, onWarmPhoto,
  offline = false, onNotify
}: {
  tab: AddTab;
  onTab(tab: AddTab): void;
  /** Where this composition started, when it did not start empty. */
  seed?: CaptureSeed | null;
  /**
   * What the server can build entries with, or `undefined` while that is unknown. Unknown is not
   * unavailable: only a definite refusal turns Capture off, and then it says which setting is
   * missing rather than letting someone discover it by pressing the button.
   */
  captureHealth?: CaptureHealth;
  /** The replica, for resolving the topic names a document carries. Null only during startup. */
  graph: VocabularyGraph | null;
  problems: YamlProblem[];
  busy: boolean;
  onClose(): void;
  onCreate(draft: string): void;
  onCapture(request: CaptureRequest): Promise<CaptureResult>;
  onOpenLexeme(id: string): void;
  /** Open the word already held and ask one question against it, seeded with what was captured. */
  onFoldIn?(lexemeId: string, foldable: CaptureFoldable, photo: KeptPhoto | null): void;
  /** One turn about the unsaved document. Absent when the server has no model, like Capture itself. */
  onChat?(document: string, turns: ChatTurn[]): Promise<ChatResult>;
  /** Photo capture's three round trips. Without them there is no Photo tab. */
  onReadPhoto?(photo: Blob): Promise<PhotoReading>;
  onStorePhoto?(photo: Blob): Promise<{ photoRef: string }>;
  onLookUp?(request: QuickLookUpRequest, signal: AbortSignal): Promise<QuickLookUp>;
  onWarmPhoto?(): void;
  /** From `syncStatus`: chat is a round trip, and the dock is the only part of this that needs one. */
  offline?: boolean;
  onNotify(message: string, action?: { label: string; run(): void }): void;
}) {
  const [capture, setCapture] = useState("");
  const [headword, setHeadword] = useState(seed?.headword ?? "");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceTitle, setSourceTitle] = useState("");
  const [note, setNote] = useState(seed?.note ?? "");
  const [draft, setDraft] = useState(YAML_TEMPLATE);
  const [working, setWorking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<CaptureResult["duplicates"]>([]);
  /** What this capture carried that the word already held may not have. Null when it carried nothing. */
  const [foldable, setFoldable] = useState<CaptureFoldable | null>(null);
  /** The photo the last capture carried, so folding it into a word already held keeps it too. */
  const [capturedPhoto, setCapturedPhoto] = useState<KeptPhoto | null>(null);
  const [passedOver, setPassedOver] = useState<CaptureResult["passedOver"]>([]);
  /**
   * What the last chat turn changed in this unsaved proposal, so it can be marked.
   *
   * Held rather than derived because the editor text is the document of record here: once you touch
   * it by hand the comparison is against something that no longer exists, so it is dropped.
   */
  const [edited, setEdited] = useState<{ before: ArticleDraft; diff: DraftDiff } | null>(null);
  /** In memory and gone with this composition, exactly as it is on a stored article. */
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const { wrap, numbers } = useEditorPreferences();

  /** The server has told us it cannot build entries. Writing YAML by hand still can. */
  const cannotBuild = captureHealth && !captureHealth.available ? captureHealth : null;

  /**
   * No vocabulary means no entry can land anywhere, whatever the model says.
   *
   * Checked here rather than left to the server because the server checks it *after* the first
   * model call — deliberately, so that a resolved language can be named in the refusal — which from
   * the outside is a long wait ending in "this looks like en, which you have no vocabulary for".
   * A word cannot be filed before there is somewhere to file it, and saying so costs nothing.
   */
  const noVocabularies = graph !== null && graph.vocabularies.every((entry) => entry.deleted);

  /** Nothing has been proposed or written yet, so there is nothing to render. */
  const untouched = draft === YAML_TEMPLATE;

  /** Every write to the document goes through here, so nothing can move without the marks noticing. */
  const rewrite = (text: string, diff: { before: ArticleDraft; diff: DraftDiff } | null = null) => {
    setDraft(text);
    setEdited(diff);
  };

  const marks = useMemo<MarkSlot | null>(() => {
    if (!edited) return null;
    const { records, notes } = edited.diff;
    return {
      of: (id) => records.get(id)?.mark ?? null,
      field: (id, field) => records.get(id)?.fields.get(field) ?? null,
      note: (index) => notes.get(index) ?? null,
      movedFrom: (id) => records.get(id)?.wasAt ?? null
    };
  }, [edited]);

  /**
   * Asking about a proposal that has not been saved yet (§8.4).
   *
   * The document is the editor text, which already carries the ids the server minted for its
   * children, so operations address it exactly as they address a stored entry. What comes back is
   * written straight back into the editor, and the preview re-derives on the next render as it does
   * on every keystroke — so one sentence changes one thing, instead of re-running generation and
   * losing what was already right.
   */
  const askAboutDraft = (turns: ChatTurn[]) => onChat!(draft, turns);

  const applyToDraft = (ops: EditOp[], modelId: string) => {
    try {
      const before = parseArticle(draft);
      const applied = applyOps(before, ops, {
        modelId,
        glossLang: preview.article?.glossLangs[0] ?? null,
        // A document with no lexeme id mints freely on save, so nothing here needs a minted set.
        mintId: newId
      });
      rewrite(yamlForDraft(applied.draft), { before, diff: diffDrafts(before, applied.draft) });
    } catch (error) {
      onNotify(error instanceof EditRefused ? error.message
        : "That proposal could not be applied, so nothing was changed.");
    }
  };

  /**
   * The preview is derived from the editor text rather than kept beside it. That is what makes
   * "read it, then go fix it in YAML, then read it again" work without the two ever disagreeing.
   */
  const preview = useMemo<{ article: Article | null; problems: YamlProblem[] }>(() => {
    if (!graph || untouched) return { article: null, problems: [] };
    try {
      return { article: articleFromDraft(graph, parseArticle(draft)), problems: [] };
    } catch (error) {
      if (error instanceof YamlProblems) return { article: null, problems: error.problems };
      return { article: null, problems: [{ line: null, message: String(error) }] };
    }
  }, [graph, draft, untouched]);

  async function submit(request: CaptureRequest) {
    setWorking(true);
    setFailure(null);
    setDuplicates([]);
    setPassedOver([]);
    try {
      const result = await onCapture(request);
      setPassedOver(result.passedOver ?? []);
      if (result.duplicates.length) {
        setDuplicates(result.duplicates);
        setFoldable(result.foldable ?? null);
        return;
      }
      if (!result.draft) {
        setFailure("The server built nothing from that text, so there is nothing to review.");
        return;
      }
      // The proposal becomes an ordinary editable document from here on, and is read as an article.
      rewrite(yamlForDraft(result.draft));
      onTab("article");
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "That text could not be processed.");
    } finally {
      setWorking(false);
    }
  }

  function process() {
    setCapturedPhoto(null);
    return submit({
      // The word alone is a complete capture. Sending it as the text too keeps that from needing
      // its own request shape — the server resolves what it is given, and here that is the word.
      text: capture.trim() || headword.trim(),
      headword: headword.trim() || null,
      sourceUrl: sourceUrl.trim() || null,
      sourceTitle: sourceTitle.trim() || null,
      note: note.trim() || null,
      // A dictionary's entry, when there is one. Never `text`: that becomes attestations, and a
      // dictionary's examples are not sentences this person met.
      reference: seed?.reference ?? null,
      referenceMode: seed?.referenceMode ?? null
    });
  }

  /**
   * A word from a photo, through the same capture: the sentence as the text, the look-up it already
   * had, and the photo. The photo's own bytes go into the picture cache first, under the reference it
   * will have once kept, so the article under review shows it — the server holds it pending and will
   * not serve it until the save.
   */
  async function addFromPhoto(add: PhotoAdd) {
    if (add.photoRef && add.photo) await seedPicture(add.photoRef, add.photo);
    setCapturedPhoto(add.photoRef && add.photo ? {
      photoRef: add.photoRef, photoRegion: add.photoRegion, sourceKind: add.sourceKind, photo: add.photo
    } : null);
    await submit({
      text: add.text,
      resolution: add.resolution,
      photoRef: add.photoRef,
      photoRegion: add.photoRegion,
      sourceKind: add.sourceKind
    });
  }

  /**
   * Fold into a word already held, with the photo when one is kept. Its bytes go into the picture
   * cache for `addFromPhoto`'s reason: the proposal under review shows the photo before the save.
   */
  async function foldIn(lexemeId: string, carried: CaptureFoldable, photo: KeptPhoto | null) {
    if (photo) await seedPicture(photo.photoRef, photo.photo);
    onFoldIn?.(lexemeId, carried, photo);
  }

  /* A seeded composition processes itself. The decision was taken on the article — which word,
     which treatment — and asking for it a second time here would be a form standing between
     someone and the thing they already asked for. */
  const started = useRef(false);
  useEffect(() => {
    // A seed that processes itself would fail on arrival on a server that cannot build entries.
    if (!seed || started.current || cannotBuild || noVocabularies) return;
    started.current = true;
    void process();
    // Deliberately once, on arrival. `seed` is fixed for the life of this view: App remounts it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const head = <>
    {/* "a word" goes on the smallest phones, before the tabs lose their labels. */}
    <h2>Add<span className="head-rest"> a word</span></h2>
    <span className="spacer" />
    <div className="seg">
      <button className={tab === "capture" ? "on" : ""} onClick={() => onTab("capture")}>Text</button>
      {onReadPhoto && <button className={tab === "photo" ? "on" : ""} onClick={() => onTab("photo")}>Photo</button>}
      <button className={tab === "article" ? "on" : ""} onClick={() => onTab("article")}>Article</button>
      <button className={tab === "yaml" ? "on" : ""} onClick={() => onTab("yaml")}>YAML</button>
    </div>
    <button className="icon-btn" aria-label="Close" onClick={onClose}><CloseIcon /></button>
  </>;

  // Pinned with the buttons on purpose, on Text and on Photo alike: a refusal you have to go looking
  // for is one you miss.
  const notices = <>
    {duplicates.length > 0 && <div className="validation ok" role="status">
      <strong>{duplicates.length === 1 ? "You already have this word." : "You already have these."}</strong>
      <ul>
        {duplicates.map((duplicate) => <li key={duplicate.id}>
          <button className="link-btn" onClick={() => onOpenLexeme(duplicate.id)}>{duplicate.headword}</button>
          {duplicate.shortGloss ? ` — ${duplicate.shortGloss}` : ""}
        </li>)}
      </ul>
      <span>
        {foldable
          ? "Nothing was created. Open it to read it, or fold what you just captured into it."
          : "Nothing was created. Open the entry to see what it already says."}
      </span>
      {/* §05: a repeat capture is an addition, not an entry. Folding it in is one ordinary turn
          of the article conversation producing one ordinary proposal — no merge path, no second
          writer, and nothing the chat could not already do. */}
      {foldable && duplicates.length === 1 && <div className="fold-in">
        <button className="tb-btn primary" onClick={() => void foldIn(duplicates[0].id, foldable, capturedPhoto)}>
          Fold in
        </button>
      </div>}
    </div>}
    {/* A fall-through is silent otherwise. The entry names the model that wrote it, but a
        provider at the head of the order that is quietly broken looks exactly like one that was
        never chosen — and the owner goes on believing it built their words. */}
    {passedOver?.length ? <div className="validation warn" role="status">
      <strong>{passedOver.length === 1 ? "A provider was passed over." : "Some providers were passed over."}</strong>
      <ul>{passedOver.map((one) => <li key={`${one.provider} ${one.model}`}>
        <code>{one.model}</code> — {REASONS[one.reason] ?? one.reason}
      </li>)}</ul>
      <span>The next one in your order answered instead.</span>
    </div> : null}
    {noVocabularies && <div className="validation bad" role="alert">
      <strong>There is no vocabulary to add a word to yet.</strong>
      <span>Add the language you are learning in Settings {"\u25B8"} Vocabularies, then capture
        this again.</span>
    </div>}
    {!noVocabularies && cannotBuild && <div className="validation bad" role="alert">
      <strong>This server cannot build entries right now.</strong>
      <span>{cannotBuild.reason}. You can still write the entry yourself.</span>
    </div>}
    {failure && <div className="validation bad" role="alert"><strong>{failure}</strong></div>}
  </>;

  if (tab === "photo" && onReadPhoto && onStorePhoto && onLookUp) {
    return <PhotoCapture
      head={head}
      notices={notices}
      offline={offline}
      unavailable={noVocabularies ? "There is no vocabulary to add a word to yet" : cannotBuild?.reason ?? null}
      working={working}
      onRead={onReadPhoto}
      onStore={onStorePhoto}
      onLookUp={onLookUp}
      onAdd={(add) => void addFromPhoto(add)}
      onOpenLexeme={onOpenLexeme}
      onFoldIn={(lexemeId, carried, photo) => void foldIn(lexemeId, carried, photo)}
      onWarm={onWarmPhoto ?? noop}
    />;
  }

  if (tab === "capture") {
    return <Composer
      label="Add a word"
      head={head}
      fill={false}
      actions={<>
        {notices}
        <div className="composer-buttons">
          <span className="spacer" />
          <button className="tb-btn" onClick={() => onTab("yaml")}>Write YAML instead</button>
          <button
            className="tb-btn primary"
            disabled={(!capture.trim() && !headword.trim()) || working
              || Boolean(cannotBuild) || noVocabularies}
            onClick={() => void process()}
          >
            {working ? "Building…" : "Process"}
          </button>
        </div>
      </>}
    >
      <label className="label" htmlFor="captureText">{seed
        ? <>A sentence of your own, if you have one <span className="opt">optional</span></>
        : "Paste a word, or the sentence you met it in"}</label>
      <textarea
        className="capture-area" id="captureText" style={{ marginTop: 8 }} value={capture}
        onChange={(event) => { setCapture(event.target.value); setDuplicates([]); setFailure(null); }}
        placeholder="Se pican las verduras en dados de un centímetro y se reservan."
      />

      <label className="label" htmlFor="captureWord" style={{ marginTop: 14 }}>
        Which word? <span className="opt">optional</span>
      </label>
      <input
        className="capture-word" id="captureWord" value={headword} autoComplete="off"
        placeholder="picar" onChange={(event) => { setHeadword(event.target.value); setFailure(null); }}
      />

      {seed ? <>
        <p className="hint">
          Built from the dictionary entry you were reading, which is sent as reference only — its
          example sentences are the dictionary's, not places you met the word, so none of them is
          kept as an attestation. You read the entry before it is saved.
        </p>
        {/* Shown rather than merely described. What is sent to a model on someone's behalf should
            be readable by them first, and "it carries some context" is not the same as saying so. */}
        <details className="fold capture-fold">
          <summary>
            <span className="caret"><CaretIcon /></span>
            <span className="label">
              What is being sent as reference{seed.sources.length ? ` · ${seed.sources.join(" · ")}` : ""}
            </span>
          </summary>
          <div className="fold-body"><pre className="reference-text">{seed.reference}</pre></div>
        </details>
      </> : <p className="hint">
        Share the whole sentence — the word is picked out for you unless you name it above, and the
        sentence is kept as the place you met it. You read the entry before it is saved.
        {!untouched && " Processing again replaces the draft you have."}
      </p>}

      <details className="fold capture-fold">
        <summary>
          <span className="caret"><CaretIcon /></span>
          <span className="label">Where it came from, and what to ask for</span>
        </summary>
        <div className="fold-body capture-details">
          <label className="label" htmlFor="captureUrl">Source link</label>
          <input
            id="captureUrl" value={sourceUrl} autoComplete="off" spellCheck={false}
            placeholder="https://example.com/receta" onChange={(event) => setSourceUrl(event.target.value)}
          />
          <label className="label" htmlFor="captureTitle">Where it came from</label>
          <input
            id="captureTitle" value={sourceTitle} autoComplete="off"
            placeholder="Receta — pisto manchego" onChange={(event) => setSourceTitle(event.target.value)}
          />
          <label className="label" htmlFor="captureNote">Anything to ask the generator</label>
          <input
            id="captureNote" value={note} autoComplete="off"
            placeholder="contrast it with picante" onChange={(event) => setNote(event.target.value)}
          />
        </div>
      </details>
    </Composer>;
  }

  if (tab === "article") {
    return <Composer
      label="Add a word"
      head={head}
      fill={false}
      actions={<>
        <ValidationPanel problems={preview.problems.length ? preview.problems : problems} notice={null} />
        <div className="composer-buttons">
          <span className="spacer" />
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button className="tb-btn" onClick={() => onTab("yaml")}>Edit YAML</button>
          <button
            className="tb-btn primary" disabled={busy || !preview.article}
            onClick={() => onCreate(draft)}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </>}
    >
      {preview.article
        ? <div className="article-preview">
            {/* No delete, and no storage footer: there is nothing stored to delete or describe. */}
            <LexemeArticle
              article={preview.article} onNotify={onNotify} meta={false} marks={marks}
            />
            {/* The same dock, over a proposal nobody has saved yet. `meta={false}` already says this
                is not a stored word, and there is no review bar: the editor text *is* the proposal,
                and Save is already on this surface. */}
            {onChat && <AskDock
              headword={preview.article.lexeme.headword}
              emoji={preview.article.lexeme.emoji}
              turns={chat}
              onTurns={setChat}
              ask={askAboutDraft}
              offline={offline}
              onPropose={(found, modelId) => applyToDraft(found.ops as EditOp[], modelId)}
              /* No `full` here: this surface is itself a review, and its Composer already owns the
                 height. There is nothing for the sheet to take over. */
              expandable={false}
              inline
            />}
          </div>
        : <p className="empty">
            {untouched
              ? "Nothing to preview yet — process a capture, or write the document yourself."
              : "This document cannot be read, so there is nothing to show. Fix it in YAML."}
          </p>}
    </Composer>;
  }

  return <Composer
    label="Add a word"
    head={head}
    fill
    actions={<>
      <ValidationPanel problems={problems} notice={null} />
      <div className="composer-buttons">
        <span className="spacer" />
        <button className="tb-btn" onClick={onClose}>Cancel</button>
        <button className="tb-btn primary" disabled={busy} onClick={() => onCreate(draft)}>
          {busy ? "Saving…" : "Validate & save"}
        </button>
      </div>
    </>}
  >
    <div className="code-wrap">
      <div className="code-head"><span className="label">new-entry.yaml</span></div>
      <Suspense fallback={<p className="empty">Loading the editor…</p>}>
        <EditorSurface value={draft} onChange={(text) => rewrite(text)} wrap={wrap} numbers={numbers} />
      </Suspense>
    </div>
  </Composer>;
}
