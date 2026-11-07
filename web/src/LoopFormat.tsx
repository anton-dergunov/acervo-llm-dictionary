/**
 * Choosing what kind of loop to make: three tiles — a drill, a radio lesson, a story — and under
 * Options, the chosen kind's variants and switches.
 *
 * **The formats are the generator's catalogue**, read from `GET /loops/schema`, each with its own label
 * and the sentence it gives to choose it by. What this file adds is only how they are grouped: the
 * four ways of drilling (`classic`, `alternating`, `echo`, `review`) are one tile and its variants,
 * because to a listener they are one kind of loop said four ways, and six cards of equal weight was the
 * longest thing in the dialog. The table names ids and nothing else; a format it does not know gets a
 * tile of its own under the generator's label, so a format added in a later version still appears
 * with nothing changing on this side. The switches are drawn generically: an on/off one is a checkbox
 * row, a choice is a row of segments.
 *
 * **A format this server cannot make says so before it is chosen**, not after four minutes. What a
 * format needs — a model to write its lines, a loop voice that can say two languages in one line —
 * is set up elsewhere, and the card names where. One that has a fallback stays choosable, and says
 * what will be made instead; one without is not.
 *
 * The format last made on this device, and each format's switches as they were last set, are what
 * the dialog opens on (`editorPreferences.ts`). A device fact, like the loop player's switches.
 */

import { useRef, type ReactNode } from "react";
import type { LoopFormat, LoopSchema, LoopSwitch } from "./api";
import { DrillIcon, MicIcon, NoteIcon, TaleIcon } from "./icons";
import { formatLabel } from "./selectors";

/* What a format needs, said as what the owner would set up, and where. */
const NEEDS: Record<string, { what: string; where: string }> = {
  writer: { what: "a writing model", where: "Settings ▸ Providers" },
  multilingual_voice: { what: "a loop voice that can mix languages", where: "Settings ▸ Loops" }
};

/** Why a loop is not the format it was asked for, in the listener's words. */
export function fallbackNote(formats: readonly LoopFormat[] | undefined, asked: string, made: string): string {
  const wanted = formats?.find((format) => format.id === asked);
  const needs = (wanted?.requires ?? []).map((need) => NEEDS[need]?.what).filter(Boolean);
  const reason = needs.length ? ` — it needs ${needs.join(" and ")}` : "";
  return `${formatLabel(formats, made)} instead of ${formatLabel(formats, asked)}${reason}`;
}

/** What a format requires that this server does not have. */
export function missingFor(format: LoopFormat, schema: Pick<LoopSchema, "writerAvailable" | "mixesLanguages">): string[] {
  return format.requires.filter((need) =>
    (need === "writer" && !schema.writerAvailable) || (need === "multilingual_voice" && !schema.mixesLanguages));
}

/** Whether a format can be asked for here: it has what it needs, or something to make instead. */
export function formatUsable(format: LoopFormat, schema: Pick<LoopSchema, "writerAvailable" | "mixesLanguages">): boolean {
  return missingFor(format, schema).length === 0 || Boolean(format.fallback);
}

/** A format's switches as they stand: each remembered value it still accepts, else its default. */
export function switchesFor(format: LoopFormat, remembered: Record<string, boolean | string>): Record<string, boolean | string> {
  return Object.fromEntries(Object.entries(format.switches).map(([name, spec]) => {
    const value = remembered[name];
    const accepted = spec.choices ? typeof value === "string" && spec.choices.includes(value) : typeof value === "boolean";
    return [name, accepted ? value : spec.default];
  }));
}

/* ── kinds: how the formats are grouped into tiles ── */

/** The drill's variants, in the order they are offered; the first is the drill a tile means. */
const DRILL = ["classic", "alternating", "echo", "review"];
/** A variant named by what is different about it, since all four are "the drill". */
const VARIANTS: Record<string, string> = {
  classic: "Pause to recall", alternating: "Straight through", echo: "Say it back", review: "Meaning first"
};
const ICONS: Record<string, () => ReactNode> = { drill: DrillIcon, "radio-lesson": MicIcon, story: TaleIcon };

export interface LoopKind {
  id: string;
  label: string;
  icon: () => ReactNode;
  /** The formats this tile stands for, its first the one it means alone. */
  formats: LoopFormat[];
}

export function loopKinds(formats: readonly LoopFormat[]): LoopKind[] {
  const kinds: LoopKind[] = [];
  for (const format of formats) {
    if (DRILL.includes(format.id)) {
      let drill = kinds.find((kind) => kind.id === "drill");
      if (!drill) { drill = { id: "drill", label: "Drill", icon: DrillIcon, formats: [] }; kinds.push(drill); }
      drill.formats.push(format);
      drill.formats.sort((left, right) => DRILL.indexOf(left.id) - DRILL.indexOf(right.id));
    } else {
      kinds.push({ id: format.id, label: format.label, icon: ICONS[format.id] ?? NoteIcon, formats: [format] });
    }
  }
  return kinds;
}

export function variantLabel(format: LoopFormat): string {
  return VARIANTS[format.id] ?? format.label;
}

/** What is missing, said as what the owner would set up and where. */
function needs(format: LoopFormat, schema: LoopSchema): { what: string; where: string } | null {
  const missing = missingFor(format, schema);
  if (!missing.length) return null;
  return {
    what: missing.map((need) => NEEDS[need]?.what ?? need).join(" and "),
    where: [...new Set(missing.map((need) => NEEDS[need]?.where).filter(Boolean))].join(" and ")
  };
}

function Note({ format, schema }: { format: LoopFormat; schema: LoopSchema }) {
  const need = needs(format, schema);
  if (!need) return null;
  return <span className="format-note warn">
    {format.fallback
      ? ` Falls back to ${formatLabel(schema.formats, format.fallback)} here: it needs ${need.what} (${need.where}).`
      : ` Needs ${need.what} — set one up in ${need.where}.`}
  </span>;
}

function Switch({ name, spec, value, onChange }: {
  name: string; spec: LoopSwitch; value: boolean | string; onChange(value: boolean | string): void;
}) {
  if (spec.choices) return <div className="format-switch">
    <span>{spec.label}</span>
    <span className="seg" role="radiogroup" aria-label={spec.label}>
      {spec.choices.map((choice) => <button
        key={choice} type="button" role="radio" aria-checked={value === choice}
        className={value === choice ? "on" : ""} onClick={() => onChange(choice)}
      >{choice}</button>)}
    </span>
  </div>;
  return <label className="format-switch">
    <input type="checkbox" name={`switch-${name}`} checked={value === true} onChange={(event) => onChange(event.target.checked)} />
    <span>{spec.label}</span>
  </label>;
}

/** The options folded under the tiles, said in a line so they need not be opened to be read. */
function summary(kind: LoopKind, format: LoopFormat, switches: Record<string, boolean | string>): string {
  const parts: string[] = [];
  if (kind.formats.length > 1) parts.push(variantLabel(format));
  for (const [name, spec] of Object.entries(format.switches)) {
    const value = switches[name] ?? spec.default;
    if (spec.choices) parts.push(/^\d+$/.test(String(value)) ? `${value}×` : String(value));
    else if (value === true) parts.push(spec.label);
  }
  return parts.join(" · ");
}

export function KindChoices({ schema, value, switches, onChoose, onSwitch }: {
  schema: LoopSchema;
  /** The format chosen: a kind's own, or one of the drill's variants. */
  value: string;
  switches: Record<string, boolean | string>;
  onChoose(format: string): void;
  onSwitch(name: string, value: boolean | string): void;
}) {
  const kinds = loopKinds(schema.formats);
  const format = schema.formats.find((one) => one.id === value);
  const kind = kinds.find((one) => one.formats.some((member) => member.id === value));
  // The variant last chosen under each tile in this dialog, so going to Radio and back to Drill
  // returns to the drill that was set up.
  const variants = useRef<Record<string, string>>({});
  if (kind) variants.current[kind.id] = value;
  const usableVariants = kind ? kind.formats.filter((member) => formatUsable(member, schema)) : [];
  const hasOptions = Boolean(format && kind && (usableVariants.length > 1 || Object.keys(format.switches).length));

  return <div className="kind-choice">
    <div className="kind-tiles" role="radiogroup" aria-label="Kind of loop">
      {kinds.map((one) => {
        const usable = one.formats.filter((member) => formatUsable(member, schema));
        const on = one.id === kind?.id;
        const blocked = usable.length ? null : needs(one.formats[0], schema);
        const Icon = one.icon;
        return <button
          key={one.id} type="button" role="radio" aria-checked={on} disabled={!usable.length}
          className={`kind-tile${on ? " on" : ""}`}
          title={blocked ? `Needs ${blocked.what} — set one up in ${blocked.where}.` : undefined}
          onClick={() => onChoose(usable.find((member) => member.id === variants.current[one.id])?.id ?? usable[0].id)}
        >
          <Icon />
          <span className="kind-text">
            <span className="kind-name">{one.label}</span>
            {blocked && <span className="kind-needs">Needs {blocked.what}</span>}
          </span>
        </button>;
      })}
    </div>
    {format && <p className="kind-about">{format.description}<Note format={format} schema={schema} /></p>}
    {format && kind && hasOptions && <details className="kind-options">
      <summary><span>Options</span><span className="kind-summary">{summary(kind, format, switches)}</span></summary>
      <div className="format-switches">
        {usableVariants.length > 1 && <div className="format-switch">
          <span>{kind.label}</span>
          <span className="seg" role="radiogroup" aria-label={`Kind of ${kind.label.toLowerCase()}`}>
            {usableVariants.map((member) => <button
              key={member.id} type="button" role="radio" aria-checked={member.id === value}
              className={member.id === value ? "on" : ""} onClick={() => onChoose(member.id)}
            >{variantLabel(member)}</button>)}
          </span>
        </div>}
        {Object.entries(format.switches).map(([name, spec]) => <Switch
          key={name} name={name} spec={spec} value={switches[name] ?? spec.default}
          onChange={(next) => onSwitch(name, next)}
        />)}
      </div>
    </details>}
  </div>;
}
