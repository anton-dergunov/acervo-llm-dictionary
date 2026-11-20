/**
 * The IPA guide's panel: each sound of a transcription, in its order, with how to make it, the
 * nearest English sound or a word that has it, and ▶. A tone is drawn as a pitch line and named; a
 * Mandarin word also lists its Pinyin letters with the IPA each stands for.
 *
 * Under the transcription on a tablet or desktop. On a phone, while the layout is being tried, a
 * bottom sheet, a full screen, or inline in the article (`trial.ts`); and a mark is explained inside
 * its letter's row or on a row of its own.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CloseIcon, PlayIcon } from "../icons";
import { isMandarin } from "../languages";
import { useSpeechState } from "../pronunciation";
import { pinyinParts } from "./pinyinParts";
import { soundKey, playSound } from "./sounds";
import { distinctUnits, soundOf, splitTranscription, type MarkUse, type Unit } from "./split";
import { readTone, STRESS, type LetterRow, type MarkRow } from "./table";
import { useIpaTrial, type MarksLayout } from "./trial";

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
  return <li className="ipa-row">
    <span className="ipa-sym">{symbol}</span>
    <div className="ipa-text">{children}</div>
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

function MarkRowItem({ text, row, onError }: { text: string; row: MarkRow; onError(message: string): void }) {
  return <Row symbol={onCircle(text)} sound={row.sound} label={`Listen to ${row.name}`} onError={onError}>
    <p className="ipa-how"><b>{row.name}</b>{row.how ? `: ${row.how}` : ""}</p>
  </Row>;
}

function UnitRows({ unit, marks, mandarin, onError }: {
  unit: Unit; marks: MarksLayout; mandarin: boolean; onError(message: string): void;
}) {
  if (unit.kind === "unknown") {
    return <Row symbol={unit.text} label="" onError={onError}>
      <p className="ipa-how">Not a symbol this guide explains.</p>
    </Row>;
  }
  if (unit.kind === "mark") return <MarkRowItem text={unit.text} row={unit.row} onError={onError} />;
  if (unit.kind === "tone") {
    const tone = readTone(unit.text);
    return <Row symbol={<span className="ipa-tone"><span>{unit.text}</span><Pitch levels={tone.levels} /></span>}
      sound={tone.sound} label={`Listen to the ${tone.name} tone`} onError={onError}>
      <p className="ipa-how"><b>{tone.name[0].toUpperCase() + tone.name.slice(1)}.</b> {tone.how}</p>
      {mandarin && tone.mandarin && <p className="ipa-like">Mandarin {tone.mandarin}</p>}
    </Row>;
  }
  const letters = unit.rows.map((row) => row.symbol).join("");
  const inside = marks === "inside";
  const ownMarks = unit.marks.filter((use) => !(unit.rows.length > 1 && use.row.name === "tie bar"));
  return <>
    <Row symbol={inside ? unit.text : letters} sound={soundOf(unit)} label={`Listen to ${unit.rows[0].name}`} onError={onError}>
      {unit.rows.length === 1
        ? <LetterLines row={unit.rows[0]} />
        : <>
            <p className="ipa-how">{unit.rows.map((row) => row.symbol).join(" and ")} said together, as one sound.</p>
            {unit.rows.map((row) => <p key={row.symbol} className="ipa-like"><span className="ipa-mark-sym">{row.symbol}</span> {row.how}</p>)}
          </>}
      {inside && ownMarks.map((use, index) => <MarkLine key={index} use={use} />)}
    </Row>
    {!inside && ownMarks.map((use, index) => <MarkRowItem key={index} text={use.text} row={use.row} onError={onError} />)}
  </>;
}

/** The transcription at the top of the panel; in the inside layout, its stress marks lit. */
function Heading({ ipa, lit }: { ipa: string; lit: boolean }) {
  if (!lit) return <span className="ipa-heading">{ipa}</span>;
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
        {part.tone && <Row symbol={<span className={`ipa-pinyin-letters tone-${part.tone.number}`}>{part.tone.mark}</span>}
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
  const trial = useIpaTrial();
  const phone = usePhone();
  const panel = useRef<HTMLElement>(null);
  const [error, setError] = useState<string | null>(null);
  const units = useMemo(() => distinctUnits(splitTranscription(ipa)), [ipa]);
  const mandarin = Boolean(language && isMandarin(language));
  const inside = trial.marks === "inside";
  const standing = units.filter((unit): unit is Extract<Unit, { kind: "mark" }> => unit.kind === "mark");
  const listed = inside ? units.filter((unit) => unit.kind !== "mark") : units;
  const layout = phone ? trial.phone : "pop";

  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    const away = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target || panel.current?.contains(target) || target.closest(".ipa-open")) return;
      if (layout === "pop" || layout === "inline") onClose();
    };
    window.addEventListener("keydown", key);
    document.addEventListener("pointerdown", away);
    return () => { window.removeEventListener("keydown", key); document.removeEventListener("pointerdown", away); };
  }, [onClose, layout]);

  const body = <section ref={panel} className={`ipa-panel ${layout}`} role="dialog" aria-label={`Sounds in ${ipa}`}>
    <header className="ipa-head">
      <Heading ipa={ipa} lit={inside && standing.some((unit) => STRESS.has(unit.text))} />
      <button type="button" className="icon-btn ipa-close" aria-label="Close" onClick={onClose}><CloseIcon /></button>
    </header>
    {error && <p className="ipa-error" role="status">{error}</p>}
    {inside && standing.length > 0 && <div className="ipa-marks-note">
      {standing.map((unit) => <MarkLine key={unit.text} use={{ text: unit.text, row: unit.row }} />)}
    </div>}
    <ul className="ipa-rows">
      {listed.map((unit, index) => <UnitRows key={index} unit={unit} marks={trial.marks} mandarin={mandarin} onError={setError} />)}
    </ul>
    {mandarin && reading && <PinyinRows reading={reading} onError={setError} />}
  </section>;

  if (layout === "sheet" || layout === "full") {
    return createPortal(<>
      {layout === "sheet" && <div className="ipa-backdrop" onClick={onClose} />}
      {body}
    </>, document.body);
  }
  return body;
}
