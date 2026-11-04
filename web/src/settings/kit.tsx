/**
 * What every page of Settings is built from, so that every page looks and behaves alike.
 *
 * A **group** is a titled card of rows. A **row** is a label with at most one short hint under it on
 * the left and its control on the right. The hint says what the setting does for you, in a dozen
 * words — never how it works inside; that is what the feature's document is for. A **notice** is a
 * fact the owner has to act on (no provider, a service that does not answer), never an explanation.
 *
 * The markup is the prototype's (`design/ui-prototype/settings.js`), and so is the CSS.
 */

import { createContext, useContext, type ReactNode } from "react";
import { AlertIcon, ChevronIcon, DownIcon, ForwardIcon } from "../icons";

export function Group({ title, count, foot, children }: {
  title?: string;
  /** A short tally at the right of the title, such as "18 of 23 on". */
  count?: string;
  foot?: ReactNode;
  children: ReactNode;
}) {
  return <section className="pref-group" aria-label={title}>
    {title && <h4>{title}{count && <span className="count">{count}</span>}</h4>}
    <div className="pref-card">{children}</div>
    {foot && <p className="pref-foot">{foot}</p>}
  </section>;
}

function Text({ label, hint }: { label: ReactNode; hint?: ReactNode }) {
  return <span className="pref-text">
    <span className="pref-label">{label}</span>
    {hint && <span className="pref-hint">{hint}</span>}
  </span>;
}

/** A row whose control is whatever it is given: a button, a value, a badge. */
export function Row({ label, hint, children, stack = false }: {
  label: ReactNode;
  hint?: ReactNode;
  children?: ReactNode;
  /** The control goes under the label rather than beside it: a segmented choice, a text area. */
  stack?: boolean;
}) {
  return <div className={`pref-row${stack ? " stack" : ""}`}><Text label={label} hint={hint} />{children}</div>;
}

/** A row that is not a setting at all, only something to read: "12,340 videos · 5 languages". */
export function Value({ children, mono = false }: { children: ReactNode; mono?: boolean }) {
  return <span className={`pref-value${mono ? " mono" : ""}`}>{children}</span>;
}

/** The switch. A checkbox underneath, so the whole row toggles it and a test can tick it. */
export function Toggle({ label, hint, checked, disabled, onChange, children }: {
  label: string;
  hint?: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange(checked: boolean): void;
  /** Anything that goes before the switch, such as a button that belongs to the same thing. */
  children?: ReactNode;
}) {
  const input = <input
    type="checkbox" role="switch" className="toggle" checked={checked} disabled={disabled}
    aria-label={label} onChange={(event) => onChange(event.target.checked)}
  />;
  /* A label's control is its first labelable descendant, and a button is one — so a row that also
     holds a button cannot be a label, or tapping its text would press the button. */
  if (children) return <div className="pref-row"><Text label={label} hint={hint} />{children}{input}</div>;
  return <label className="pref-row"><Text label={label} hint={hint} />{input}</label>;
}

export function Select<T extends string>({ label, hint, value, options, disabled, onChange }: {
  label: string;
  hint?: ReactNode;
  value: T;
  options: { value: T; label: string }[];
  disabled?: boolean;
  onChange(value: T): void;
}) {
  return <label className="pref-row">
    <Text label={label} hint={hint} />
    <select
      className="pref-select" value={value} disabled={disabled} aria-label={label}
      onChange={(event) => onChange(event.target.value as T)}
    >
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>;
}

/** Two or three choices, side by side; the hint is the chosen one's, so it says what it means. */
export function Segmented<T extends string>({ label, value, options, onChange }: {
  label: string;
  value: T;
  options: { value: T; label: string; hint?: string }[];
  onChange(value: T): void;
}) {
  const chosen = options.find((option) => option.value === value);
  return <div className="pref-row stack">
    <Text label={label} hint={chosen?.hint} />
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((option) => <button
        key={option.value} type="button" role="radio" aria-checked={option.value === value}
        className={option.value === value ? "on" : ""} onClick={() => onChange(option.value)}
      >{option.label}</button>)}
    </div>
  </div>;
}

/** A row that leads somewhere: a sub-page of this page, with what is there as its value. */
export function Link({ label, hint, value, onOpen }: {
  label: string;
  hint?: ReactNode;
  value?: ReactNode;
  onOpen(): void;
}) {
  return <button type="button" className="pref-row" onClick={onOpen}>
    <Text label={label} hint={hint} />
    {value !== undefined && <Value>{value}</Value>}
    <span className="chev"><ForwardIcon /></span>
  </button>;
}

/** A whole-row button: an action in the accent, or in the warning colour when it destroys. */
export function Action({ children, danger = false, disabled, onClick }: {
  children: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  onClick(): void;
}) {
  return <button type="button" className={`pref-row pref-action${danger ? " danger" : ""}`} disabled={disabled} onClick={onClick}>
    {children}
  </button>;
}

/** The two arrows of an ordered list. Each names what it moves, for a screen reader. */
export function Reorder({ name, first, last, disabled, onMove }: {
  name: string;
  first: boolean;
  last: boolean;
  disabled?: boolean;
  onMove(direction: -1 | 1): void;
}) {
  return <span className="pref-reorder">
    <button type="button" className="icon-btn" aria-label={`Move ${name} up`} disabled={disabled || first}
      onClick={(event) => { event.preventDefault(); onMove(-1); }}><ChevronIcon /></button>
    <button type="button" className="icon-btn" aria-label={`Move ${name} down`} disabled={disabled || last}
      onClick={(event) => { event.preventDefault(); onMove(1); }}><DownIcon /></button>
  </span>;
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="pref-notice" role="status"><AlertIcon /><span>{children}</span></div>;
}

/** Between what a page sets and what it reports. */
export function Divider({ children }: { children: string }) {
  return <div className="pref-divider" role="separator">{children}</div>;
}

/** A page before its first answer: the shape it will have, never a line of text. */
export function Placeholder({ rows = 3 }: { rows?: number }) {
  return <section className="pref-group" aria-busy="true" aria-label="Loading">
    <div className="pref-card">
      {Array.from({ length: rows }, (_, index) => <div key={index} className="pref-row">
        <span className="pref-text"><span className="pref-skel" /><span className="pref-skel" /></span>
      </div>)}
    </div>
  </section>;
}

/**
 * A page's own sub-pages: Clips ▸ Channels, Providers ▸ Credentials, a vocabulary being edited.
 *
 * The window owns the back button and the title, so a page opens a sub-page by naming it here and
 * renders it when `sub` says so. Leaving the page closes it.
 */
export interface SubPage { id: string; title: string }

export const SubPageContext = createContext<{
  sub: SubPage | null;
  open(sub: SubPage): void;
  close(): void;
}>({ sub: null, open: () => undefined, close: () => undefined });

export function useSubPage() {
  return useContext(SubPageContext);
}
