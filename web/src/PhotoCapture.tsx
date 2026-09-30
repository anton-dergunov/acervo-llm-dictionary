import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type {
  CaptureFoldable, CaptureResolution, PhotoPoint, PhotoReading, QuickLookUp, QuickLookUpRequest
} from "./api";
import Composer from "./Composer";
import type { PhotoRegion, SourceKind } from "./domain";
import { cropSquare, encodePhoto, still } from "./photoImage";
import {
  cropRegion, hitTest, isWord, photoRegionFor, pointsOf, selectedText, selectionIn, sentenceOf,
  sentenceOutlines, span, tapped, UNCERTAIN, wordOutlines
} from "./photoText";

/** The photo as it will be kept, with the bytes behind it so the article under review can show it. */
export interface KeptPhoto {
  photoRef: string;
  photoRegion: PhotoRegion | null;
  sourceKind: SourceKind;
  photo: Blob;
}

/** What Add sends: the sentence as it stands in the sheet, and what was learned about it. */
export interface PhotoAdd {
  text: string;
  resolution: CaptureResolution | null;
  photoRef: string | null;
  photoRegion: PhotoRegion | null;
  sourceKind: SourceKind;
  /** The bytes that were uploaded, so the article under review can show the photo it keeps. */
  photo: Blob | null;
}

type Stage =
  | { kind: "idle" }
  | { kind: "camera" }
  | { kind: "reading" }
  | { kind: "read"; reading: PhotoReading }
  | { kind: "failed"; message: string };

type LookUp =
  | { state: "loading" }
  | { state: "done"; result: QuickLookUp }
  | { state: "failed"; message: string };

/** Where the word was met, in the sheet's words. `sign` is a photo of the world rather than a page. */
const SOURCES: { kind: SourceKind; label: string }[] = [
  { kind: "book", label: "Book" },
  { kind: "sign", label: "Sign" },
  { kind: "web", label: "Screen" },
  { kind: "unknown", label: "Other" }
];

const CAMERA_ERRORS: Record<string, string> = {
  NotAllowedError: "Acervo is not allowed to use the camera. Allow it in the browser's settings for this site, or choose an image instead.",
  NotFoundError: "This device has no camera Acervo can use. Choose an image instead.",
  NotReadableError: "The camera is in use by another app. Close it, then try again."
};

/** How far a finger may move and still be a tap, in CSS pixels. */
const SLOP = 8;

/** A tapped selection's look-up is cached by the sentence it was asked about and where the tap was. */
const keyOf = (text: string, at: { start: number; end: number }) => `${at.start}:${at.end}\u0000${text}`;

/**
 * Photo capture (docs/features/photo-capture.md): take or choose a picture, tap a word on it, read
 * what it means in that sentence, and add it — or fold the sentence into the word you already have.
 *
 * **Never the default and never on its own.** The camera starts only when "Take a photo" is pressed:
 * this is an occasional way in, and a camera that switches itself on is one nobody asked for.
 *
 * Nothing here writes a record. Reading a photo stores it on the server, pending; a tap asks the
 * quick look-up; Add hands the sentence, the look-up and the photo to the ordinary capture, whose
 * proposal is reviewed as an article and saved like any other. The frame sits above the sheet and
 * never beside it, because the device this matters most on is a tablet in portrait.
 *
 * **Every photo is shown in one square.** A camera photo *is* that square — the viewfinder is square
 * and the shutter keeps exactly what it showed, so the photo read and kept is the photo framed. An
 * image that is not square fills the square's width, so a screenshot reads at about its real size,
 * and scrolls up and down inside it; a sideways drag is then always free to select a phrase. What is
 * kept of a scrolled image is the square that was on screen when Add was pressed.
 *
 * The highlight is an SVG over the frozen image in the image's own coordinates. That is not the
 * overlay the YAML editor was forbidden: that one failed because two text layouts had to agree to
 * the pixel, and here there is one coordinate system and nothing to drift.
 */
export default function PhotoCapture({
  head, notices, offline, unavailable, working, onRead, onStore, onLookUp, onAdd, onOpenLexeme, onFoldIn,
  onWarm
}: {
  head: ReactNode;
  /** The Add view's own notices — a duplicate, a fall-through, a refusal — shown above the buttons. */
  notices: ReactNode;
  offline: boolean;
  /** Why no entry can be built at all, when that is known. The notices say so; this disables. */
  unavailable: string | null;
  /** Add is on its way to the server. */
  working: boolean;
  onRead(photo: Blob): Promise<PhotoReading>;
  /** Keeps a photo pending without reading it: the square of a scrolled image that was on screen. */
  onStore(photo: Blob): Promise<{ photoRef: string }>;
  onLookUp(request: QuickLookUpRequest, signal: AbortSignal): Promise<QuickLookUp>;
  onAdd(add: PhotoAdd): void;
  onOpenLexeme(id: string): void;
  /** `photo` is null when the owner chose not to keep it. The device attaches it, never the model. */
  onFoldIn(lexemeId: string, foldable: CaptureFoldable, photo: KeptPhoto | null): void;
  onWarm(): void;
}) {
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const [photo, setPhoto] = useState<{ blob: Blob; url: string } | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [selection, setSelection] = useState<string[]>([]);
  const [sentence, setSentence] = useState("");
  const [typed, setTyped] = useState(false);
  const [lookUps, setLookUps] = useState<Map<string, LookUp>>(new Map());
  /** A look-up whose repaired sentence replaced the one in the box: it answers for that text too. */
  const [settled, setSettled] = useState<{ text: string; result: QuickLookUp } | null>(null);
  const [keep, setKeep] = useState(true);
  const [source, setSource] = useState<SourceKind>("book");
  const video = useRef<HTMLVideoElement | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const frame = useRef<HTMLDivElement | null>(null);
  const viewport = useRef<HTMLDivElement | null>(null);
  const picker = useRef<HTMLInputElement | null>(null);
  const pressed = useRef<{ from: string | null; x: number; y: number; dragged: boolean } | null>(null);
  /** Whether the image runs past the square, and which way there is more of it. */
  const [overflow, setOverflow] = useState({ tall: false, above: false, below: false, scrolled: false });
  const [keeping, setKeeping] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const asking = useRef<AbortController | null>(null);

  const reading = stage.kind === "read" ? stage.reading : null;
  const blocked = offline || Boolean(unavailable);

  // The owner opened this tab, so a photo is likely: the server loads its sentence splitter now.
  useEffect(() => { if (!offline) onWarm(); }, [offline, onWarm]);

  const stopCamera = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  useEffect(() => {
    const hidden = () => { if (document.visibilityState === "hidden") { stopCamera(); setStage((now) => now.kind === "camera" ? { kind: "idle" } : now); } };
    document.addEventListener("visibilitychange", hidden);
    return () => { document.removeEventListener("visibilitychange", hidden); stopCamera(); asking.current?.abort(); };
  }, [stopCamera]);

  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo.url); }, [photo]);

  const read = useCallback(async (blob: Blob) => {
    setStage({ kind: "reading" });
    setSelection([]);
    setLookUps(new Map());
    setSettled(null);
    setTyped(false);
    try {
      setStage({ kind: "read", reading: await onRead(blob) });
    } catch (error) {
      setStage({ kind: "failed", message: error instanceof Error ? error.message : "That photo could not be read." });
    }
  }, [onRead]);

  const take = useCallback(async (source: Blob | HTMLCanvasElement, kind: SourceKind) => {
    let blob: Blob;
    try {
      blob = await encodePhoto(source);
    } catch (error) {
      setStage({ kind: "failed", message: error instanceof Error ? error.message : "That picture could not be opened." });
      return;
    }
    setPhoto({ blob, url: URL.createObjectURL(blob) });
    setSource(kind);
    await read(blob);
  }, [read]);

  async function openCamera() {
    setCameraError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("The camera is not available in this browser. Choose an image instead.");
      return;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 4096 }, height: { ideal: 4096 } }
      });
      setStage({ kind: "camera" });
    } catch (error) {
      const name = error instanceof DOMException ? error.name : "";
      setCameraError(CAMERA_ERRORS[name] ?? "The camera could not be opened. Choose an image instead.");
    }
  }

  // The element exists only once the stage says so, so the stream is attached after it renders.
  useEffect(() => {
    if (stage.kind !== "camera" || !video.current || !stream.current) return;
    video.current.srcObject = stream.current;
    // `play` answers a promise in a browser and nothing at all where there is no media stack.
    void Promise.resolve(video.current.play?.()).catch(() => undefined);
  }, [stage.kind]);

  async function shutter() {
    if (!video.current) return;
    const shot = still(video.current);
    stopCamera();
    await take(shot, "book");
  }

  // Paste and drop, for a screenshot on a desktop or a tablet on its stand.
  useEffect(() => {
    const pasted = (event: ClipboardEvent) => {
      const file = [...(event.clipboardData?.files ?? [])].find((one) => one.type.startsWith("image/"));
      if (!file || blocked) return;
      event.preventDefault();
      void take(file, "web");
    };
    window.addEventListener("paste", pasted);
    return () => window.removeEventListener("paste", pasted);
  }, [blocked, take]);

  function dropped(event: React.DragEvent) {
    const file = [...event.dataTransfer.files].find((one) => one.type.startsWith("image/"));
    if (!file || blocked) return;
    event.preventDefault();
    void take(file, "web");
  }

  const current = useMemo(() => (reading ? sentenceOf(reading, selection) : null), [reading, selection]);

  /** Where the selection sits in the sentence as it now reads — found again if it was edited. */
  const pointer = useMemo(() => {
    if (!reading || !selection.length) return null;
    if (current && sentence === current.text) return selectionIn(reading, current, selection);
    const words = selectedText(reading, selection);
    const at = sentence.indexOf(words);
    return at >= 0 && words ? { start: at, end: at + words.length } : null;
  }, [reading, selection, current, sentence]);

  // A new sentence under the finger replaces the text in the box; the same one keeps what was typed.
  const place = current?.id ?? `words:${selection.join(",")}`;
  useEffect(() => {
    if (!reading || !selection.length) return;
    setTyped(false);
    setSettled(null);
    setSentence(current ? current.text : selectedText(reading, selection));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [place, reading]);

  const key = pointer && sentence.trim() ? keyOf(sentence, pointer) : null;
  const lookUp: LookUp | null = (key ? lookUps.get(key) : undefined)
    ?? (settled && settled.text === sentence ? { state: "done", result: settled.result } : null);

  // Every settled selection asks at once; typing in the sentence asks once it pauses.
  useEffect(() => {
    if (!key || !pointer || lookUps.has(key) || blocked || !reading) return;
    if (settled && settled.text === sentence) return;
    const asked = { text: sentence, selection: pointer, words: selectedText(reading, selection), typed };
    const timer = window.setTimeout(() => {
      asking.current?.abort();
      const controller = new AbortController();
      asking.current = controller;
      setLookUps((was) => new Map(was).set(key, { state: "loading" }));
      onLookUp({ text: asked.text, selection: asked.selection, source: "photo" }, controller.signal)
        .then((result) => {
          setLookUps((was) => new Map(was).set(key, { state: "done", result }));
          // OCR damage the look-up repaired becomes the sentence in the box, and is not asked again.
          const repaired = result.resolution.sentences[0]?.text;
          if (repaired && repaired !== asked.text && !asked.typed) {
            setSettled({ text: repaired, result });
            setSentence(repaired);
          }
        })
        .catch((error) => {
          if (controller.signal.aborted) {
            setLookUps((was) => { const next = new Map(was); next.delete(key); return next; });
            return;
          }
          setLookUps((was) => new Map(was).set(key, {
            state: "failed", message: error instanceof Error ? error.message : "That word could not be looked up."
          }));
        });
    }, typed ? 600 : 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, blocked]);

  function at(event: React.PointerEvent): PhotoPoint | null {
    const bounds = frame.current?.getBoundingClientRect();
    if (!bounds || !bounds.width || !bounds.height) return null;
    return [(event.clientX - bounds.left) / bounds.width, (event.clientY - bounds.top) / bounds.height];
  }

  function down(event: React.PointerEvent) {
    if (!reading) return;
    const point = at(event);
    pressed.current = { from: point ? hitTest(reading, point) : null, x: event.clientX, y: event.clientY, dragged: false };
  }

  function move(event: React.PointerEvent) {
    const press = pressed.current;
    if (!reading || !press) return;
    const dx = Math.abs(event.clientX - press.x);
    const dy = Math.abs(event.clientY - press.y);
    if (!press.dragged) {
      // A finger moving up or down is scrolling, which the browser does itself (`touch-action:
      // pan-y`); one moving along a line is selecting a phrase. A mouse has a wheel for scrolling.
      const along = event.pointerType === "mouse" ? Math.max(dx, dy) > SLOP : dx > SLOP && dx > dy;
      if (!along) return;
      press.dragged = true;
      (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
    }
    const point = at(event);
    const over = point ? hitTest(reading, point) : null;
    if (!over) return;
    press.from = press.from ?? over;
    setSelection(span(reading, press.from, over));
  }

  function up(event: React.PointerEvent) {
    const press = pressed.current;
    pressed.current = null;
    if (!reading || !press || press.dragged) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > SLOP) return;
    // A tap on nothing selects nothing, so it is plain that the word was not read.
    setSelection(press.from ? tapped(reading, selection, press.from) : []);
  }

  /** Which way the image runs past the square, measured whenever it moves or arrives. */
  function measure() {
    const box = viewport.current;
    if (!box) return;
    const tall = box.scrollHeight > box.clientHeight + 2;
    setOverflow((was) => ({
      tall,
      above: tall && box.scrollTop > 2,
      below: tall && box.scrollTop + box.clientHeight < box.scrollHeight - 2,
      scrolled: was.scrolled || box.scrollTop > 2
    }));
  }

  function another() {
    asking.current?.abort();
    setStage({ kind: "idle" });
    setPhoto(null);
    setSelection([]);
    setLookUps(new Map());
  }

  /**
   * The photo as it will be kept, for Add and for Fold in alike, handed to `use`. A square photo is
   * kept whole. A taller one is kept as the square that is on screen now: cropped here, sent to be
   * stored, and its region moved onto the crop — so what the article shows later is what was looked
   * at while choosing the word. Null when the owner chose not to keep it; `use` is not called at all
   * when it could not be kept, and the problem is on screen instead.
   */
  async function withKeptPhoto(use: (kept: KeptPhoto | null) => void) {
    if (!reading || !photo || !keep) { use(null); return; }
    const region = photoRegionFor(reading, selection, typed ? null : current);
    const box = viewport.current;
    if (!box || box.scrollHeight <= box.clientHeight + 2) {
      use({ photoRef: reading.photoRef, photoRegion: region, sourceKind: source, photo: photo.blob });
      return;
    }
    const top = box.scrollTop / box.scrollHeight;
    const size = box.clientHeight / box.scrollHeight;
    setKeeping(true);
    setProblem(null);
    let kept: KeptPhoto;
    try {
      const square = await cropSquare(photo.blob, top, size);
      const { photoRef } = await onStore(square);
      kept = { photoRef, photoRegion: cropRegion(region, top, size), sourceKind: source, photo: square };
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The photo could not be kept.");
      return;
    } finally {
      setKeeping(false);
    }
    use(kept);
  }

  function add() {
    if (!reading || !photo) return;
    const found = lookUp?.state === "done" ? lookUp.result : null;
    const resolution = found && !found.duplicates.length ? found.resolution : null;
    void withKeptPhoto((kept) => onAdd({
      text: sentence.trim(), resolution, photoRef: kept?.photoRef ?? null,
      photoRegion: kept?.photoRegion ?? null, sourceKind: source, photo: kept?.photo ?? null
    }));
  }

  const outlines = useMemo(() => {
    if (!reading) return null;
    return {
      uncertain: reading.words.filter((word) => isWord(word) && word.confidence < UNCERTAIN).flatMap((word) => word.polygons),
      sentence: current ? sentenceOutlines(reading, current) : [],
      words: wordOutlines(reading, selection)
    };
  }, [reading, current, selection]);

  const found = lookUp?.state === "done" ? lookUp.result : null;
  const held = found?.duplicates ?? [];

  const buttons = <div className="composer-buttons">
    {stage.kind !== "idle" && stage.kind !== "camera" && <button className="tb-btn" onClick={another}>Another photo</button>}
    <span className="spacer" />
    {held.length === 1 && found?.foldable && <button
      className="tb-btn" aria-label="Fold this sentence in" disabled={keeping}
      onClick={() => void withKeptPhoto((kept) => onFoldIn(held[0].id, found.foldable!, kept))}
    >Fold in</button>}
    {held.length > 0
      ? <button className="tb-btn primary" aria-label={`Open ${held[0].headword}`} onClick={() => onOpenLexeme(held[0].id)}>Open</button>
      : <button
          className="tb-btn primary"
          disabled={!reading || !selection.length || !sentence.trim() || working || keeping || blocked}
          onClick={add}
        >{keeping ? "Keeping…" : working ? "Building…" : "Add"}</button>}
  </div>;

  // No action bar under a live camera: its own buttons are the ones that matter, and the bar would
  // cover the shutter.
  return <Composer label="Add a word from a photo" head={head} fill={false} actions={stage.kind === "camera" ? null : <>
    {notices}
    {problem && <div className="validation bad" role="alert"><strong>{problem}</strong></div>}
    {offline && <div className="validation bad" role="alert">
      <strong>Photo capture needs the server.</strong>
      <span>Your words are all still here; try again once it can be reached.</span>
    </div>}
    {buttons}
  </>}>
    <input
      ref={picker} type="file" accept="image/*" hidden
      onChange={(event) => {
        const [file] = event.target.files ?? [];
        event.target.value = "";
        if (file) void take(file, "web");
      }}
    />

    {stage.kind === "idle" && <div
      className="photo-start" onDragOver={(event) => event.preventDefault()} onDrop={dropped}
    >
      <div className="photo-start-buttons">
        <button className="tb-btn primary" disabled={blocked} onClick={() => void openCamera()}>Take a photo</button>
        <button className="tb-btn" disabled={blocked} onClick={() => picker.current?.click()}>Choose an image</button>
      </div>
      <p className="hint">
        Or paste or drop a screenshot here. The whole picture is read, and every word on it can be
        tapped. The camera only turns on when you ask it to.
      </p>
      {cameraError && <div className="validation bad" role="alert"><strong>{cameraError}</strong></div>}
    </div>}

    {stage.kind === "camera" && <div className="photo-camera">
      <div className="photo-window"><div className="photo-square fixed">
        <video ref={video} className="photo-viewfinder" playsInline muted aria-label="Camera" />
      </div></div>
      <div className="photo-camera-buttons">
        <button className="tb-btn" onClick={() => { stopCamera(); setStage({ kind: "idle" }); }}>Cancel</button>
        <button className="photo-shutter" aria-label="Take the photo" onClick={() => void shutter()} />
      </div>
    </div>}

    {photo && stage.kind !== "idle" && stage.kind !== "camera" && <div
      className={`photo-window${overflow.above ? " more-above" : ""}${overflow.below ? " more-below" : ""}`}
    >
      <div className="photo-square" ref={viewport} onScroll={measure}>
      <div
        className="photo-frame" ref={frame}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { pressed.current = null; }}
      >
        <img src={photo.url} alt="The photo being read" draggable={false} onLoad={measure} />
        {outlines && <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
          {outlines.uncertain.map((polygon, index) => <polygon key={`u${index}`} className="photo-uncertain" points={pointsOf(polygon)} />)}
          {outlines.sentence.map((polygon, index) => <polygon key={`s${index}`} className="photo-sentence" points={pointsOf(polygon)} />)}
          {outlines.words.map((polygon, index) => <polygon key={`w${index}`} className="photo-word" points={pointsOf(polygon)} />)}
        </svg>}
      </div>
      </div>
      {stage.kind === "reading" && <div className="photo-status" role="status">Reading the photo…</div>}
    </div>}
    {overflow.tall && !overflow.scrolled && stage.kind === "read" && <p className="hint photo-scroll-hint">
      Swipe up or down to see the rest. The square on screen is what is kept.
    </p>}

    {stage.kind === "failed" && <div className="validation bad" role="alert">
      <strong>{stage.message}</strong>
      {photo && <div className="fold-in"><button className="tb-btn" onClick={() => void read(photo.blob)}>Try again</button></div>}
    </div>}

    {reading && <PhotoSheet
      reading={reading} selection={selection} current={current} sentence={sentence}
      lookUp={lookUp} keep={keep} source={source}
      onSentence={(text) => { setSentence(text); setTyped(true); }}
      onKeep={setKeep} onSource={setSource}
    />}
  </Composer>;
}

function PhotoSheet({
  reading, selection, current, sentence, lookUp, keep, source, onSentence, onKeep, onSource
}: {
  reading: PhotoReading;
  selection: string[];
  current: ReturnType<typeof sentenceOf>;
  sentence: string;
  lookUp: LookUp | null;
  keep: boolean;
  source: SourceKind;
  onSentence(text: string): void;
  onKeep(keep: boolean): void;
  onSource(kind: SourceKind): void;
}) {
  if (!reading.words.some(isWord)) {
    return <div className="photo-sheet"><p className="empty">No text was found in this photo. Try another one, closer and in focus.</p></div>;
  }
  const foreign = !reading.vocabulary && reading.language
    ? <div className="validation warn" role="status">
        <strong>This looks like {reading.language}, which you have no vocabulary for.</strong>
        <span>Add it in Settings {"▸"} Vocabularies to keep words from it.</span>
      </div>
    : null;
  if (!selection.length) {
    return <div className="photo-sheet">
      {foreign}
      <p className="hint">Tap a word to see what it means here. Tap the word beside it, or drag across them, for a phrase.</p>
    </div>;
  }
  const found = lookUp?.state === "done" ? lookUp.result : null;
  const held = found?.duplicates ?? [];
  return <div className="photo-sheet">
    {foreign}
    <div className="photo-meaning" aria-live="polite">
      {lookUp?.state === "failed"
        ? <span className="photo-meaning-failed">{lookUp.message}</span>
        : found
          ? <>
              <strong lang={found.resolution.language}>{found.resolution.headword}</strong>
              {found.resolution.gloss ? <span> — {found.resolution.gloss}</span> : null}
              {held.length > 0 && <span className="photo-held"> · already in your words as {held[0].headword}</span>}
            </>
          : <span className="photo-meaning-pending">
              <strong lang={reading.language ?? undefined}>{selectedText(reading, selection)}</strong> — looking it up…
            </span>}
    </div>
    <label className="label" htmlFor="photoSentence">The sentence, as it will be kept</label>
    <textarea
      id="photoSentence" className="capture-area photo-sentence-text" lang={reading.language ?? undefined} rows={3}
      value={sentence} onChange={(event) => onSentence(event.target.value)}
    />
    {current?.truncatedStart && <p className="hint">The start of this sentence is cut off by the edge of the photo.</p>}
    {current?.truncatedEnd && <p className="hint">The end of this sentence is cut off by the edge of the photo.</p>}
    {found && !found.resolution.sentences.length && <p className="hint">
      This is not a sentence, so none is kept — the photo is kept as the place you met the word.
    </p>}
    <div className="photo-options">
      <div className="photo-sources" role="group" aria-label="Where you met it">
        {SOURCES.map((one) => <button
          key={one.kind} className={`cards-chip${source === one.kind ? " on" : ""}`}
          aria-pressed={source === one.kind} onClick={() => onSource(one.kind)}
        >{one.label}</button>)}
      </div>
      <label className="config-switch">
        <input type="checkbox" checked={keep} onChange={(event) => onKeep(event.target.checked)} />
        <span>
          <strong>Keep the photo</strong>
          <span>With the sentence, so you can see where on the page you met the word.</span>
        </span>
      </label>
    </div>
  </div>;
}
