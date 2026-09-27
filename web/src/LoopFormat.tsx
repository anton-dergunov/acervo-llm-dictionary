/**
 * Choosing what kind of loop to make: the formats the generator offers, and each one's switches.
 *
 * **The formats are the generator's catalogue**, read from `GET /loops/schema` and never copied here,
 * each with its own label and the sentence it gives to choose it by — so a format added in a later
 * version appears with nothing changing on this side. The switches are drawn from the same answer
 * and drawn generically: an on/off one is a checkbox row, a choice is a row of segments.
 *
 * **A format this server cannot make says so before it is chosen**, not after four minutes. What a
 * format needs — a model to write its lines, a loop voice that can say two languages in one line —
 * is set up elsewhere, and the card names where. One that has a fallback stays choosable, and says
 * what will be made instead; one without is not.
 *
 * The format last made on this device, and each format's switches as they were last set, are what
 * the dialog opens on (`editorPreferences.ts`). A device fact, like the loop player's switches.
 */

import type { LoopFormat, LoopSchema, LoopSwitch } from "./api";
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

function Note({ format, schema }: { format: LoopFormat; schema: LoopSchema }) {
  const missing = missingFor(format, schema);
  if (!missing.length) return null;
  const needs = missing.map((need) => NEEDS[need]?.what ?? need).join(" and ");
  const where = [...new Set(missing.map((need) => NEEDS[need]?.where).filter(Boolean))].join(" and ");
  return <span className="format-note warn">
    {format.fallback
      ? `Falls back to ${formatLabel(schema.formats, format.fallback)} here: it needs ${needs} (${where}).`
      : `Needs ${needs} — set one up in ${where}.`}
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

export function FormatChoices({ schema, value, switches, onChoose, onSwitch }: {
  schema: LoopSchema;
  value: string;
  switches: Record<string, boolean | string>;
  onChoose(format: string): void;
  onSwitch(name: string, value: boolean | string): void;
}) {
  const chosen = schema.formats.find((format) => format.id === value);
  return <div className="format-choices">
    {schema.formats.map((format) => {
      const usable = formatUsable(format, schema);
      return <label key={format.id} className={`config-switch format-card${format.id === value ? " on" : ""}${usable ? "" : " off"}`}>
        <input
          type="radio" name="loop-format" value={format.id} checked={format.id === value}
          disabled={!usable} onChange={() => onChoose(format.id)}
        />
        <span>
          <strong>{format.label}</strong>
          <span>{format.description}</span>
          <Note format={format} schema={schema} />
        </span>
      </label>;
    })}
    {chosen && Object.keys(chosen.switches).length > 0 && <div className="format-switches">
      {Object.entries(chosen.switches).map(([name, spec]) => <Switch
        key={name} name={name} spec={spec} value={switches[name] ?? spec.default}
        onChange={(next) => onSwitch(name, next)}
      />)}
    </div>}
  </div>;
}
