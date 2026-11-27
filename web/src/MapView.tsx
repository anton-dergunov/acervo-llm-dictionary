/* The Map surface: one vocabulary's senses laid out by meaning (docs/features/meaning-map.md).

   The picture is `meaningMap/`, which knows nothing of Acervo; this is the host around it — which map,
   the header, the peek, Find, and the way to an article and back. It is the prototype's `?map=1`
   (`design/ui-prototype/`), which is the design.

   **It opens on the map this device already holds.** The last map for each vocabulary is kept in
   `mapStore.ts`, so a map seen once is on screen at once, offline included, and the server is asked
   in the background whether it is still current — with its version, so an unchanged map costs a line
   of JSON. A newer one arrives as an update: the words already there glide to where they now
   belong and the new ones ring. The server is asked again when a sync brings changes and when the
   job naming the regions finishes. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { AcervoApiError, backendSession, type ServerMap } from "./api";
import type { VocabularyGraph } from "./domain";
import { BackIcon, CloseIcon, FitIcon, ForwardIcon, MinusIcon, PlusIcon, SearchIcon, SelectIcon } from "./icons";
import { isOpen, jobFor, jobStream } from "./jobs";
import { languageOf } from "./languages";
import { createMapStore, type MapStore } from "./mapStore";
import { MeaningMap, type MapCamera, type MeaningMapHandle } from "./meaningMap";
import { usePicture } from "./picture";
import { mapDataFor, mapPeekFor, type VocabularyOption } from "./selectors";

let store: MapStore = createMapStore();
export function replaceMapStoreForTests(replacement: MapStore): void { store = replacement; }

/* Regions churn below this many senses, so a young language is shown as words with no regions. */
const REGIONS_FROM = 150;
const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "\u2318" : "Ctrl+";
const fold = (text: string) => text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
const plural = (count: number, one: string, many: string) => `${count.toLocaleString()} ${count === 1 ? one : many}`;

type Phase = "reading" | "drawing" | "ready" | "offline" | "failed";

export interface MapViewProps {
  graph: VocabularyGraph;
  owner: string;
  /** The vocabulary the map is of. */
  vocabularyId: string;
  /** Its language, for drawing and reading its words. */
  language: string;
  vocabularies: VocabularyOption[];
  /* The top bar's slot, where the map's row goes: the bar is the top bar, not a card over the map. */
  bar?: HTMLElement | null;
  /* Where the map was left in this vocabulary, so coming back from an article puts it back exactly. */
  camera: MapCamera | null;
  onCamera(camera: MapCamera): void;
  /* The sense being peeked at, held by the host so it survives a trip to the article. */
  selected: string | null;
  onSelect(senseId: string | null): void;
  onVocabulary(id: string): void;
  /* A sense to fly to and select once it is on the map — from its article's "show on the map". */
  fly?: string | null;
  onFlown?(): void;
  onOpen(lexemeId: string, senseId: string): void;
  onClose(): void;
  /* The selection, as lexeme ids: every sense of a selected word wears its mark, because selection
     is of words and a map is of senses. Toggled from the peek. */
  chosen?: ReadonlySet<string>;
  onToggleChosen?(lexemeId: string): void;
}

export function MapView(props: MapViewProps) {
  const { graph, owner, vocabularyId, language, selected, onSelect } = props;
  const [map, setMap] = useState<ServerMap | null>(null);
  const [phase, setPhase] = useState<Phase>("reading");
  const [arrived, setArrived] = useState(0);
  const [find, setFind] = useState("");
  const [hitsOpen, setHitsOpen] = useState(false);
  const [langMenu, setLangMenu] = useState(false);
  const handle = useRef<MeaningMapHandle | null>(null);
  const peek = useRef<HTMLElement | null>(null);
  const surface = useRef<HTMLElement | null>(null);
  const held = useRef<ServerMap | null>(null);
  const asking = useRef<Promise<void> | null>(null);

  /* Ask the server for this vocabulary's map, sending the fingerprint of the one on screen. An answer
     for a vocabulary no longer on screen is dropped: the switcher may have moved on while it came. */
  const showing = useRef(vocabularyId);
  showing.current = vocabularyId;
  const refresh = useRef<(quiet: boolean) => Promise<void>>(async () => undefined);
  refresh.current = async (quiet: boolean) => {
    if (asking.current) return asking.current;
    const have = held.current;
    const slow = have || quiet ? 0 : window.setTimeout(() => setPhase((now) => (now === "reading" ? "drawing" : now)), 500);
    asking.current = (async () => {
      try {
        const asked = vocabularyId;
        const answer = await backendSession.readMap(asked, have?.version);
        if ("current" in answer || showing.current !== asked) return;
        held.current = answer;
        setMap(answer);
        setPhase("ready");
        await store.save(owner, asked, answer).catch(() => undefined);
      } catch (error) {
        if (have) return; // A map on screen stays on screen; being offline is not news here.
        setPhase(error instanceof AcervoApiError && (error.code === "offline" || error.code === "not_configured") ? "offline" : "failed");
      } finally {
        window.clearTimeout(slow);
        asking.current = null;
      }
    })();
    return asking.current;
  };

  useEffect(() => {
    let cancelled = false;
    held.current = null;
    setMap(null);
    setPhase("reading");
    setArrived(0);
    setFind("");
    (async () => {
      const kept = await store.read(owner, vocabularyId).catch(() => null);
      if (cancelled) return;
      if (kept) { held.current = kept; setMap(kept); setPhase("ready"); }
      await refresh.current(false);
    })();
    return () => { cancelled = true; };
  }, [owner, vocabularyId]);

  /* A sync that brought changes may have moved the map; ask, once things have settled. */
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const timer = window.setTimeout(() => { if (held.current) void refresh.current(true); }, 1500);
    return () => window.clearTimeout(timer);
  }, [graph]);

  /* The regions' names arrive after the map, from a job; when it finishes, ask again. */
  const jobs = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const naming = jobFor(jobs, "map.name", vocabularyId);
  const wasNaming = useRef(false);
  useEffect(() => {
    const open = isOpen(naming);
    if (wasNaming.current && !open && naming?.state === "done") void refresh.current(true);
    wasNaming.current = open;
  }, [naming]);

  /* "12 new meanings" says what the update just showed, and then goes. */
  useEffect(() => {
    if (!arrived) return;
    const timer = window.setTimeout(() => setArrived(0), 4200);
    return () => window.clearTimeout(timer);
  }, [arrived]);

  const data = useMemo(() => (map ? mapDataFor(graph, map, vocabularyId) : null), [graph, map, vocabularyId]);
  const index = useMemo(() => (data && selected ? data.points.findIndex((p) => p.id === selected) : -1), [data, selected]);
  const view = useMemo(() => (index >= 0 ? mapPeekFor(graph, selected as string) : null), [graph, selected, index]);

  const matches = useMemo(() => {
    const query = fold(find.trim());
    if (!query || !data) return [];
    const scored: { i: number; score: number }[] = [];
    data.points.forEach((p, i) => {
      const at = fold(p.headword).indexOf(query);
      const inGloss = fold(p.gloss).includes(query);
      if (at < 0 && !inGloss) return;
      scored.push({ i, score: (at === 0 ? 0 : at > 0 ? 1 : 2) - p.rank * 0.1 });
    });
    return scored.sort((a, b) => a.score - b.score).map((entry) => entry.i);
  }, [data, find]);
  const lit = useMemo(() => (find.trim() ? new Set(matches) : null), [find, matches]);
  const chosen = props.chosen;
  const chosenPoints = useMemo(() => {
    if (!data || !chosen?.size) return null;
    const indices = new Set<number>();
    data.points.forEach((p, i) => { if (chosen.has(p.word)) indices.add(i); });
    return indices;
  }, [data, chosen]);

  /* Asked to show one sense, the map flies to it as Find does, once it is drawn and holds it. */
  useEffect(() => {
    if (!props.fly || !data) return;
    const i = data.points.findIndex((p) => p.id === props.fly);
    if (i < 0) return;
    onSelect(props.fly);
    handle.current?.select(i, { fly: true });
    props.onFlown?.();
    // `data` and `fly` are what decide it; the callbacks are the host's and change every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, props.fly]);

  function goTo(i: number) {
    if (!data) return;
    onSelect(data.points[i].id);
    setHitsOpen(false);
    handle.current?.select(i, { fly: true });
  }

  /* Tell the camera what the peek covers, so a sense it flies to lands in the part still visible:
     a sheet across the bottom of a phone, a card at the bottom left of anything wider. */
  useLayoutEffect(() => {
    const map = handle.current;
    const card = peek.current;
    const box = surface.current;
    if (!map || !box) return;
    if (!card) { map.setInsets({ left: 0, bottom: 0 }); return; }
    const sheet = card.offsetWidth >= box.clientWidth - 2;
    map.setInsets(sheet ? { left: 0, bottom: card.offsetHeight } : { left: card.offsetWidth + 12, bottom: 0 });
  }, [view]);

  /* Escape puts the innermost thing away: the peek, then the map. Find handles its own. */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const target = event.target as Element | null;
      if (target?.closest?.("input, textarea")) return;
      if (langMenu) setLangMenu(false);
      else if (selected) onSelect(null);
      else props.onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  const option = props.vocabularies.find((entry) => entry.id === vocabularyId) ?? { ...languageOf(language), id: vocabularyId, count: 0 };
  const small = data !== null && map !== null && map.regions.length === 0 && data.points.length < REGIONS_FROM;

  return <section className={`map${view ? " peeking" : ""}`} ref={surface} onClick={(event) => {
    if (!(event.target as Element).closest(".map-lang")) setLangMenu(false);
    if (!(event.target as Element).closest(".map-find")) setHitsOpen(false);
  }}>
    {data && <MeaningMap
      ref={handle}
      data={data}
      dataKey={vocabularyId}
      initialCamera={props.camera}
      selected={index}
      highlighted={lit}
      chosen={chosenPoints}
      label={`A map of your ${option.name} words, arranged by meaning`}
      onSelect={(point, i) => {
        onSelect(point ? point.id : null);
        if (i >= 0) window.requestAnimationFrame(() => handle.current?.reveal(i));
      }}
      onCamera={props.onCamera}
      onUpdate={(count) => { if (count > 0) setArrived(count); }}
    />}

    {props.bar && createPortal(<div className="map-top">
      <button className="icon-btn" aria-label="Back to your words" onClick={props.onClose}><BackIcon /></button>
      <div className="map-title">
        <h2>Map</h2>
        {data && <span className="map-count label">
          {plural(data.points.length, "meaning", "meanings")} · {plural(new Set(data.points.map((p) => p.word)).size, "word", "words")}
        </span>}
      </div>
      {data && <div className="map-find">
        <SearchIcon />
        <input
          type="search" placeholder="Find a word on the map" aria-label="Find a word on the map"
          autoComplete="off" spellCheck={false} value={find}
          onChange={(event) => { setFind(event.target.value); setHitsOpen(true); }}
          onFocus={() => { if (find.trim()) setHitsOpen(true); }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && matches.length) { event.preventDefault(); goTo(matches[0]); event.currentTarget.blur(); }
            if (event.key === "Escape") { event.preventDefault(); setFind(""); setHitsOpen(false); event.currentTarget.blur(); }
          }}
        />
        {hitsOpen && find.trim() && <ol className="map-hits">
          {matches.length ? matches.slice(0, 8).map((i, k) => {
            const p = data.points[i];
            return <li key={p.id}><button className={k === 0 ? "on" : ""} onClick={() => goTo(i)}>
              <span>{p.emoji}</span><span lang={language}>{p.headword}</span>
              <span className="hit-gloss">{p.gloss}</span>
            </button></li>;
          }) : <li className="hit-none">Nothing on this map matches “{find.trim()}”.</li>}
        </ol>}
      </div>}
      <div className="map-lang">
        <button className="tb-btn lang-btn" aria-haspopup="menu" aria-label={`Vocabulary: ${option.name}`}
          onClick={() => setLangMenu((open) => !open)}>
          <span className="flag">{option.flag}</span><span className="code">{option.code.toUpperCase()}</span>
        </button>
        <div className={`menu map-lang-menu ${langMenu ? "open" : ""}`} role="menu">
          <div className="label menu-label">Vocabulary</div>
          {props.vocabularies.map((entry) => <button key={entry.id} className={entry.id === vocabularyId ? "on" : ""}
            onClick={() => { setLangMenu(false); props.onVocabulary(entry.id); }}>
            <span>{entry.flag}</span><span>{entry.name}</span><span className="cnt">{entry.count}</span>
          </button>)}
        </div>
      </div>
    </div>, props.bar)}

    {data && <div className="map-tools">
      <button className="map-tool" aria-label="Show the whole map" title={`Show the whole map  ${MOD}0`}
        onClick={() => handle.current?.fit(true)}><FitIcon /></button>
      <button className="map-tool pointer-only" aria-label="Zoom in" title={`Zoom in  ${MOD}+  ·  ${MOD} + scroll`}
        onClick={() => handle.current?.zoomBy(1.8)}><PlusIcon /></button>
      <button className="map-tool pointer-only" aria-label="Zoom out" title={`Zoom out  ${MOD}\u2212`}
        onClick={() => handle.current?.zoomBy(1 / 1.8)}><MinusIcon /></button>
    </div>}

    {view && data && <aside className="map-peek" ref={peek} aria-live="polite">
      <Peek view={view} language={language} onClose={() => onSelect(null)}
        onSense={(senseId) => {
          const i = data.points.findIndex((p) => p.id === senseId);
          if (i >= 0) goTo(i);
        }}
        near={data.points[index].near.map((i) => data.points[i])}
        chosen={chosen?.has(view.lexeme.id) ?? false}
        onToggleChosen={props.onToggleChosen ? () => props.onToggleChosen?.(view.lexeme.id) : undefined}
        onOpen={() => props.onOpen(view.lexeme.id, view.sense.id)} />
    </aside>}

    {phase === "drawing" && !data && <div className="map-note center">
      <div className="map-drawing" aria-hidden="true"><span /><span /><span /></div>
      <h3>Drawing your map</h3>
      <p>The first time takes a minute or so, while every meaning is read. After that the map opens at once.</p>
    </div>}
    {phase === "offline" && !data && <div className="map-note center">
      <h3>No map yet</h3>
      <p>Your server draws the map, and this device has not reached it since you added words to this
        vocabulary. It will appear here the first time it can.</p>
    </div>}
    {phase === "failed" && !data && <div className="map-note center">
      <h3>The map could not be drawn</h3>
      <p>The server did not manage it this time. Open the map again to ask once more.</p>
    </div>}
    {small && <div className="map-note">
      Regions appear once a vocabulary has about {REGIONS_FROM} meanings. {option.name} has {data?.points.length}.
    </div>}
    {arrived > 0 && <div className="map-note arrived">
      {plural(arrived, "new meaning", "new meanings")} since you last opened the map
    </div>}
  </section>;
}

interface PeekProps {
  view: NonNullable<ReturnType<typeof mapPeekFor>>;
  language: string;
  near: { id: string; headword: string; emoji: string }[];
  onClose(): void;
  onSense(senseId: string): void;
  onOpen(): void;
  /* Whether this word is in the selection, and the toggle beside the way on. */
  chosen: boolean;
  onToggleChosen?(): void;
}

/* What a tap shows: enough to know the sense, and the way on. The word's other senses are one tap
   each, and the map flies there along the arc it has drawn, which is why a map of senses beats a map
   of words. */
function Peek({ view, language, near, onClose, onSense, onOpen, chosen, onToggleChosen }: PeekProps) {
  const { sense, lexeme, senses } = view;
  const picture = usePicture(view.picture?.imageRef ?? null);
  const position = senses.findIndex((entry) => entry.id === sense.id);
  return <>
    <div className="peek-head">
      <span className="peek-plate" aria-hidden="true">{sense.emoji || lexeme.emoji || "\u{1F4C4}"}</span>
      <div className="peek-id">
        <div className="peek-word" lang={language}>{lexeme.headword}</div>
        <div className="peek-meta label">{lexeme.pos}{sense.domain ? ` · ${sense.domain}` : ""}</div>
      </div>
      {picture.url && <img className="peek-pic" src={picture.url} alt="" />}
      <button className="icon-btn peek-close" aria-label="Close" onClick={onClose}><CloseIcon /></button>
    </div>
    {senses.length > 1 && <div className="peek-senses">
      <span className="label">Meaning {position + 1} of {senses.length}</span>
      {senses.map((entry, k) => <button key={entry.id} className={`peek-sib${entry.id === sense.id ? " on" : ""}`}
        aria-label={`Meaning ${k + 1}`} onClick={() => onSense(entry.id)}>
        {entry.emoji || lexeme.emoji || ""} {k + 1}
      </button>)}
    </div>}
    <p className="peek-def" lang={sense.definitionLang}>{sense.definition}</p>
    {view.terms.length > 0 && <p className="peek-gloss" lang={view.glossLang ?? undefined}>{view.terms.join("; ")}</p>}
    {near.length > 0 && <div className="peek-near">
      <span className="label">Near</span>
      {near.map((point) => <button key={point.id} className="peek-chip" lang={language} onClick={() => onSense(point.id)}>
        {point.emoji} {point.headword}
      </button>)}
    </div>}
    {/* Select beside the way on: two things a tap on a sense can lead to, and the article is the larger. */}
    <div className="peek-actions">
      {onToggleChosen && <button
        className={`tb-btn peek-pick${chosen ? " on" : ""}`} aria-pressed={chosen}
        title={chosen ? "In your selection — remove it" : "Add to selection"} onClick={onToggleChosen}
      ><SelectIcon on={chosen} /><span>{chosen ? "Selected" : "Select"}</span></button>}
      <button className="tb-btn primary peek-open" onClick={onOpen}>Open the article <ForwardIcon /></button>
    </div>
  </>;
}
