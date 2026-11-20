/**
 * The IPA guide's panel: each sound of a transcription, in its order, with how to make it, the
 * nearest English sound or a word that has it, and ▶. A tone is drawn as a pitch line and named; a
 * Mandarin word also lists its Pinyin letters with the IPA each stands for.
 *
 * Under the transcription on a tablet or desktop; on a phone a sheet over the lower part of the
 * screen, so the word it explains stays in view above it. A mark is explained inside its letter's
 * row (`u̯` is one row, with a line for ̯); stress and phrasing marks are rows of their own, where the
 * transcription has them, and stress is lit in the panel's copy of the transcription. Both were
 * chosen by trying the alternatives on a tablet and a phone (docs/features/ipa-guide.md).
 *
 * Many recordings are a word rather than the sound alone (a Pinyin letter is heard in a syllable,
 * `Zh-dà` for d), so a row says what its recording says.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CloseIcon, PlayIcon } from "../icons";
import { isMandarin } from "../languages";
import { useSpeechState } from "../pronunciation";
import { pinyinParts } from "./pinyinParts";
import { soundKey, playSound } from "./sounds";
import { distinctUnits, soundOf, splitTranscription, type MarkUse, type Unit } from "./split";
import { readTone, recordingSays, STRESS, type LetterRow } from "./table";

const PHONE = "(max-width: 720px)";

function usePhone(): boolean {
  const query = () => typeof window.matchMedia === "function" && window.matchMedia(PHONE).matches;
  const [phone, setPhone] = useState(query);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(PHONE);
    const changed = () => setPhone(list.matches);
    list.addEventListener?.("change", changed);
    return () => list.removeEventListener?.("change", changed);
  }, []);
  return phone;
}

/** A combining mark is shown on a dotted circle, as the chart prints it, and a stress mark before one. */
const onCircle = (mark: string) => /\p{M}/u.test(mark) ? `◌${mark}` : STRESS.has(mark) ? `${mark}◌` : mark;

/** A Pinyin tone as its mark alone (`ā` → ◌̄), so it is not read as the letter a. */
const toneMark = (marked: string) => `◌${marked.normalize("NFD").replace(/\P{M}/gu, "")}`;

function Play({ sound, label, onError }: { sound?: string; label: string; onError(message: string): void }) {
  const speech = useSpeechState();
  if (!sound) return <span className="ipa-play-none" />;
  const key = soundKey(sound);
  const on = speech.busy === key || speech.playing === key;
  return <button type="button" className={`say always${on ? " playing" : ""}`} aria-label={label}
    aria-busy={speech.busy === key}
    onClick={() => playSound(sound).catch((error: unknown) =>
      onError(error instanceof Error && error.message ? error.message : "That recording could not be played."))}>
    <PlayIcon />
  </button>;
}

function Pitch({ levels }: { levels: number[] }) {
  const step = levels.length > 1 ? 24 / (levels.length - 1) : 0;
  const points = levels.length > 1
    ? levels.map((level, index) => `${2 + index * step},${17 - (level - 1) * 3.5}`).join(" ")
    : `2,${17 - (levels[0] - 1) * 3.5} 26,${17 - (levels[0] - 1) * 3.5}`;
  return <svg className="ipa-pitch" viewBox="0 0 28 20" aria-hidden="true">
    <line x1="0" y1="19" x2="28" y2="19" />
    <polyline points={points} />
  </svg>;
}

function Row({ symbol, children, sound, label, onError }: {
  symbol: ReactNode; children: ReactNode; sound?: string; label: string; onError(message: string): void;
}) {
  const says = recordingSays(sound);
  return <li className="ipa-row">
    <span className="ipa-sym">{symbol}</span>
    <div className="ipa-text">
      {children}
      {says && <p className="ipa-says">The recording says <span className="ipa-said-word">{says}</span>.</p>}
    </div>
    <Play sound={sound} label={label} onError={onError} />
  </li>;
}

function LetterLines({ row }: { row: LetterRow }) {
  return <>
    <p className="ipa-how">{row.how}</p>
    {/* Most comparisons start from the English word ("t" in "top"); the rest are whole sentences. */}
    {row.like && <p className="ipa-like">{row.like.startsWith('"') ? `Like ${row.like}` : row.like}</p>}
    {row.heard && <p className="ipa-like">Heard in {row.heard}</p>}
    <p className="ipa-name">{row.name}</p>
  </>;
}

function MarkLine({ use }: { use: MarkUse }) {
  return <p className="ipa-mark-line">
    <span className="ipa-mark-sym">{onCircle(use.text)}</span> <b>{use.row.name}</b>{use.row.how ? `: ${use.row.how}` : ""}
  </p>;
}

function UnitRow({ unit, mandarin, onError }: { unit: Unit; mandarin: boolean; onError(message: string): void }) {
  if (unit.kind === "mark") {
    return <Row symbol={onCircle(unit.text)} label="" onError={onError}>
      <p className="ipa-how"><b>{unit.row.name[0].toUpperCase() + unit.row.name.slice(1)}.</b> {unit.row.how}</p>
    </Row>;
  }
  if (unit.kind === "unknown") {
    return <Row symbol={unit.text} label="" onError={onError}>
      <p className="ipa-how">Not a symbol this guide explains.</p>
    </Row>;
  }
  if (unit.kind === "tone") {
    const tone = readTone(unit.text);
    return <Row symbol={<span className="ipa-tone"><span>{unit.text}</span><Pitch levels={tone.levels} /></span>}
      sound={tone.sound} label={`Listen to the ${tone.name} tone`} onError={onError}>
      <p className="ipa-how"><b>{tone.name[0].toUpperCase() + tone.name.slice(1)}.</b> {tone.how}</p>
      {mandarin && tone.mandarin && <p className="ipa-like">Mandarin {tone.mandarin}</p>}
    </Row>;
  }
  const marks = unit.marks.filter((use) => !(unit.rows.length > 1 && use.row.name === "tie bar"));
  return <Row symbol={unit.text} sound={soundOf(unit)} label={`Listen to ${unit.rows[0].name}`} onError={onError}>
    {unit.rows.length === 1
      ? <LetterLines row={unit.rows[0]} />
      : <>
          <p className="ipa-how">{unit.rows.map((row) => row.symbol).join(" and ")} said together, as one sound.</p>
          {unit.rows.map((row) => <p key={row.symbol} className="ipa-like"><span className="ipa-mark-sym">{row.symbol}</span> {row.how}</p>)}
        </>}
    {marks.map((use, index) => <MarkLine key={index} use={use} />)}
  </Row>;
}

/** The transcription at the top of the panel, its stress marks lit. */
function Heading({ ipa }: { ipa: string }) {
  return <span className="ipa-heading">
    {Array.from(ipa).map((character, index) => STRESS.has(character)
      ? <span key={index} className="ipa-stress">{character}</span>
      : character)}
  </span>;
}

function PinyinRows({ reading, onError }: { reading: string; onError(message: string): void }) {
  const parts = useMemo(() => pinyinParts(reading), [reading]);
  if (!parts) return null;
  return <section className="ipa-pinyin" aria-label="Pinyin">
    <h3>Pinyin</h3>
    {parts.map((part, index) => <div key={index} className="ipa-syllable">
      <p className={`ipa-syllable-name tone-${part.syllable.tone}`}>{part.syllable.text}</p>
      <ul className="ipa-rows">
        {[part.initial, part.final, part.erhua].map((row) => row && <Row key={row.letters}
          symbol={<span className="ipa-pinyin-letters">{row.letters.replace(/ \(.*\)$/, "")}</span>}
          sound={row.sound} label={`Listen to Pinyin ${row.letters}`} onError={onError}>
          <p className="ipa-how"><span className="ipa-said">/{row.ipa}/</span> {row.how}</p>
        </Row>)}
        {part.tone && <Row symbol={<span className={`ipa-tone-mark tone-${part.tone.number}`}>{toneMark(part.tone.mark)}</span>}
          sound={part.tone.sound} label={`Listen to tone ${part.tone.number}`} onError={onError}>
          <p className="ipa-how"><b>{part.tone.number === 5 ? "Neutral tone" : `Tone ${part.tone.number}`}</b>
            {part.tone.ipa && <> <span className="ipa-said">{part.tone.ipa}</span></>}. {part.tone.how}</p>
        </Row>}
      </ul>
    </div>)}
  </section>;
}

export default function SoundsPanel({ ipa, reading, language, onClose }: {
  ipa: string; reading: string | null; language: string | null; onClose(): void;
}) {
  const phone = usePhone();
  const panel = useRef<HTMLElement>(null);
  const [error, setError] = useState<string | null>(null);
  const units = useMemo(() => distinctUnits(splitTranscription(ipa)), [ipa]);
  const mandarin = Boolean(language && isMandarin(language));

  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    const away = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target || panel.current?.contains(target) || target.closest(".ipa-open")) return;
      if (!phone) onClose();
    };
    window.addEventListener("keydown", key);
    document.addEventListener("pointerdown", away);
    return () => { window.removeEventListener("keydown", key); document.removeEventListener("pointerdown", away); };
  }, [onClose, phone]);

  const body = <section ref={panel} className={`ipa-panel ${phone ? "sheet" : "pop"}`} role="dialog" aria-label={`Sounds in ${ipa}`}>
    <header className="ipa-head">
      <Heading ipa={ipa} />
      <button type="button" className="icon-btn ipa-close" aria-label="Close" onClick={onClose}><CloseIcon /></button>
    </header>
    {error && <p className="ipa-error" role="status">{error}</p>}
    <ul className="ipa-rows">
      {units.map((unit, index) => <UnitRow key={index} unit={unit} mandarin={mandarin} onError={setError} />)}
    </ul>
    {mandarin && reading && <PinyinRows reading={reading} onError={setError} />}
  </section>;

  /* A sheet goes to the document, so nothing the article is inside can clip or move it. */
  return phone ? createPortal(<><div className="ipa-backdrop" onClick={onClose} />{body}</>, document.body) : body;
}
