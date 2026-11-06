import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { ModelCatalogue, UsageCounts, UsageModel, UsageReadout } from "../api";
import { ForwardIcon } from "../icons";
import { SETTINGS, useServerSetting } from "./cache";
import { Group, Notice, Placeholder, Row, Segmented, Value, type SubPage } from "./kit";
import {
  AllowanceForm, allowanceAmount, allowancePage, compact, gaugeWords, KIND_TITLES, modelPage, parseSub,
  providerTotal, usageModelPage, type Write
} from "./ProviderPages";

/**
 * Settings ▸ Providers ▸ Usage: what this server has asked of each model, and how much of each free
 * allowance is gone. Every attempt is counted, the ones that failed too — a refused request spends a
 * free one — and the counts are the server's, in UTC days (`docs/architecture/models.md`, "Usage").
 *
 * One answer (`GET /usage`) holds every period and every model's last thirty days, so switching
 * period or opening a model asks the server nothing more.
 */

type Period = "today" | "month" | "all";

const PERIODS: { value: Period; label: string }[] = [
  { value: "today", label: "Today" }, { value: "month", label: "This month" }, { value: "all", label: "All time" }
];

/** Why calls failed, in the owner's words: what happened, then what it means. */
const REASONS: Record<string, { label: string; hint: (provider: string) => string }> = {
  rate_limited: { label: "Allowance spent", hint: (provider) => `${provider} said no more for now` },
  unavailable: { label: "Overloaded", hint: (provider) => `${provider} was too busy to answer` },
  unreachable: { label: "Not answering in time", hint: () => "No answer before the time ran out" },
  unusable: { label: "Answer could not be used", hint: () => "It answered in the wrong shape" },
  empty: { label: "Answered with nothing", hint: () => "The answer was empty" },
  authentication: { label: "Key refused", hint: (provider) => `${provider} did not accept its key` },
  configuration: { label: "Request refused", hint: (provider) => `${provider} would not take the request` },
  refused: { label: "Request refused", hint: (provider) => `${provider} would not take the request` }
};

const plural = (count: number, word: string) => `${compact(count)} ${count === 1 ? word.replace(/s$/, "") : word}`;

/** "96 calls · 980k tokens", "18 pictures · 1 failed": what a model was asked, in its own unit. */
function countWords(counts: UsageCounts, kind: string): string {
  const head = kind === "image" ? plural(counts.pictures, "pictures")
    : kind === "ocr" ? plural(counts.photos, "photos") : plural(counts.calls, "calls");
  const failed = counts.failed ? `${compact(counts.failed)} failed` : null;
  const units = kind === "text" && counts.inputTokens + counts.outputTokens
    ? plural(counts.inputTokens + counts.outputTokens, "tokens")
    : kind === "audio" && counts.characters ? plural(counts.characters, "characters") : null;
  return [head, failed, units].filter(Boolean).join(" · ");
}

/** How much of an allowance is gone: the figure over a thin bar, in the warning colour from 90%. */
function Gauge({ gauge }: { gauge: NonNullable<UsageModel["gauge"]> }) {
  const share = Math.min(1, gauge.used / gauge.amount);
  const words = gaugeWords(gauge);
  return <span className={`pref-gauge${share >= 0.9 ? " near" : ""}`}>
    <span className="pref-gauge-words">{words}</span>
    <span className="pref-gauge-track" role="meter" aria-valuemin={0} aria-valuemax={gauge.amount}
      aria-valuenow={gauge.used} aria-label={words}><span style={{ width: `${(share * 100).toFixed(1)}%` }} /></span>
  </span>;
}

/** A row of headline figures, each with what it counts under it. */
function Figures({ items }: { items: [string, string][] }) {
  return <section className="pref-group">
    <div className="pref-card">
      <div className="pref-figures">{items.map(([figure, label]) => <div key={label} className="pref-figure">
        <span className="pref-figure-n">{figure}</span><span className="pref-figure-l">{label}</span>
      </div>)}</div>
    </div>
  </section>;
}

function totalsFigures(counts: UsageCounts): [string, string][] {
  const tokens = counts.inputTokens + counts.outputTokens;
  return ([
    [counts.calls, "calls", true], [counts.failed, "failed", true], [tokens, "tokens", false],
    [counts.pictures, "pictures", false], [counts.characters, "characters", false], [counts.photos, "photos", false]
  ] as [number, string, boolean][]).filter(([value, , always]) => always || value > 0)
    .map(([value, label]) => [compact(value), label]);
}

/* ── the list ── */

/** Usage of every provider, or of one when opened from its page. */
export function UsageList({ provider, page, onOpen }: { provider?: string; page: SubPage; onOpen(sub: SubPage): void }) {
  const { value, error } = useServerSetting(SETTINGS.usage);
  const [period, setPeriod] = useState<Period>("today");
  if (!value) return error ? <Notice>{error}</Notice> : <Placeholder rows={4} />;

  const groups = value.providers.filter((group) => !provider || group.id === provider);
  const totals = provider ? providerTotal(groups.flatMap((group) => group.models), period) : value.totals[period];
  /* A model with nothing in this period is left out, unless it has an allowance: how much of it is
     left is the question its gauge answers, even at nought. */
  const shown = groups
    .map((group) => ({ ...group, models: group.models.filter((model) => model[period].calls > 0 || model.gauge) }))
    .filter((group) => group.models.length > 0);
  const foot = "Counted by Acervo. Your provider’s own page has the bill.";

  return <>
    <Group>
      <Segmented<Period> label="Period" labelHidden value={period} options={PERIODS} onChange={setPeriod} />
    </Group>
    <Figures items={totalsFigures(totals)} />
    {shown.length === 0 && <Group foot={foot}>
      <Row label={period === "all" ? "Nothing asked yet" : "Nothing asked in this period"} />
    </Group>}
    {shown.map((group, index) => <Group key={group.id}
      title={group.present ? group.label : `${group.label} · no longer on this server`}
      foot={index === shown.length - 1 ? foot : undefined}>
      {group.models.map((model) => <button
        key={`${model.kind} ${model.model}`} type="button" className="pref-row usage"
        onClick={() => onOpen(usageModelPage(page, group.id, model.kind, model.model))}
      >
        <span className="pref-text">
          <span className="pref-label mono">{model.model}</span>
          <span className="pref-hint">{countWords(model[period], model.kind)}</span>
        </span>
        {model.gauge && <Gauge gauge={model.gauge} />}
        <span className="chev"><ForwardIcon /></span>
      </button>)}
    </Group>)}
  </>;
}

/* ── one model ── */

/** "5 Nov", or "Today" for the last bar. Days are the server's, in UTC. */
function dayLabel(day: string, today: string): string {
  if (day === today) return "Today";
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** A round figure at or under `value`: 1, 2 or 5 times a power of ten. */
function roundUnder(value: number): number {
  const power = 10 ** Math.floor(Math.log10(value));
  return [5, 2, 1].map((step) => step * power).find((step) => step <= value) ?? power;
}

/**
 * The last thirty days, a stacked column each: answered under failed. The one line across it is the
 * daily allowance where one is counted in calls, which is what a rate limit looks like here — the
 * columns run into it — and otherwise a round figure to read the heights by.
 */
function Chart({ days, today, limit }: { days: UsageModel["days"]; today: string; limit: number | null }) {
  const plot = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLSpanElement>(null);
  const [hot, setHot] = useState<{ index: number; left: number } | null>(null);
  const peak = Math.max(0, ...days.map((day) => day.succeeded + day.failed));
  const line = limit ?? (peak > 0 ? roundUnder(peak) : null);
  const top = Math.max(1, limit ? Math.max(peak, limit) * 1.5 : peak * 1.25);
  const words = (index: number) => {
    const day = days[index];
    return `${dayLabel(day.day, today)}: ${day.succeeded} answered${day.failed ? `, ${day.failed} failed` : ""}`;
  };

  /* Kept inside the plot: the tip is centred on its bar until that would cross an edge. */
  useLayoutEffect(() => {
    const tip = tipRef.current;
    if (!tip || !hot || !plot.current) return;
    const half = tip.offsetWidth / 2;
    tip.style.left = `${Math.max(half, Math.min(plot.current.clientWidth - half, hot.left))}px`;
  }, [hot]);

  function show(index: number, bar: HTMLElement) {
    const bars = bar.parentElement as HTMLElement;
    setHot({ index, left: bars.offsetLeft + bar.offsetLeft + bar.offsetWidth / 2 });
  }

  const middle = Math.floor(days.length / 2);
  return <div className="pref-chart">
    <div className="pref-legend"><span><i className="seg-ok" />Answered</span><span><i className="seg-failed" />Failed</span></div>
    <div className="pref-plot" ref={plot} onPointerLeave={() => setHot(null)}>
      {line !== null && <>
        <span className="pref-tick" style={{ bottom: `${(line / top) * 100}%` }}>{compact(line)}</span>
        <span className="pref-grid" style={{ bottom: `${(line / top) * 100}%` }} />
      </>}
      <div className="pref-bars">{days.map((day, index) => <span
        key={day.day} className={`pref-bar${hot?.index === index ? " hot" : ""}`} tabIndex={0} aria-label={words(index)}
        onPointerEnter={(event) => show(index, event.currentTarget)}
        onFocus={(event) => show(index, event.currentTarget)}
        onBlur={() => setHot(null)}
        onClick={(event) => show(index, event.currentTarget)}
      >
        {day.succeeded > 0 && <span className={`seg-ok${day.failed ? "" : " end"}`} style={{ height: `${(day.succeeded / top) * 100}%` }} />}
        {day.failed > 0 && <span className="seg-failed end" style={{ height: `${(day.failed / top) * 100}%` }} />}
      </span>)}</div>
      {hot && <span className="pref-tip" ref={tipRef} role="tooltip">{words(hot.index)}</span>}
    </div>
    <div className="pref-axis" aria-hidden="true">
      <span>{dayLabel(days[0].day, today)}</span><span>{dayLabel(days[middle].day, today)}</span><span>Today</span>
    </div>
  </div>;
}

/** "Today, 11:42", "3 Nov, 09:15": when the last failure was, in this device's time. */
function when(at: string | null): string {
  if (!at) return "";
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return "";
  const time = date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return date.toDateString() === new Date().toDateString()
    ? `Today, ${time}` : `${date.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${time}`;
}

/** The unit a kind's thirty days are summed in, beside its calls and failures. */
function unitFigure(counts: UsageCounts, kind: string): [string, string] | null {
  if (kind === "text") return [compact(counts.inputTokens + counts.outputTokens), "tokens"];
  if (kind === "image") return [compact(counts.pictures), "pictures"];
  if (kind === "audio") return [compact(counts.characters), "characters"];
  if (kind === "ocr") return [compact(counts.photos), "photos"];
  return null;
}

function UsageModelView({ readout, providerId, kind, model, catalogue, page, onOpen }: {
  readout: UsageReadout;
  providerId: string;
  kind: string;
  model: string;
  catalogue: ModelCatalogue;
  page: SubPage;
  onOpen(sub: SubPage): void;
}) {
  const group = readout.providers.find((one) => one.id === providerId);
  const entry = group?.models.find((one) => one.kind === kind && one.model === model);
  if (!group || !entry) return <Notice>Nothing has been asked of {model} yet.</Notice>;
  const provider = catalogue.providers.find((one) => one.id === providerId);

  const window = entry.window;
  const share = window.calls ? Math.round((window.failed / window.calls) * 100) : 0;
  const unit = unitFigure(window, kind);
  const hint = [
    entry.allowance ? `Free allowance ${allowanceAmount(entry.allowance)}` : "No free allowance set",
    entry.seconds !== null ? `answers in ${entry.seconds.toFixed(1)} s on average` : null
  ].filter(Boolean).join(" · ");
  /* A voice keeps its allowance on its own page, with its languages; any other model has no page,
     so its allowance is set from here. */
  const change = provider && entry.offered
    ? () => onOpen(kind === "audio" ? modelPage(provider, model) : allowancePage(page, providerId, kind, model))
    : null;
  const limit = entry.allowance && entry.allowance.per === "day"
    && ["calls", "pictures", "photos"].includes(entry.allowance.unit) ? entry.allowance.amount : null;
  const reasons = Object.entries(entry.failures).sort((one, other) => other[1] - one[1]);
  const label = group.present ? group.label : providerId;

  return <>
    <Group>
      <Row label={`${label} · ${KIND_TITLES[kind] ?? kind}`} hint={hint}>
        {change && <button type="button" className="tb-btn" onClick={change}>Change</button>}
      </Row>
    </Group>
    <Figures items={[
      [compact(window.calls), "calls, 30 days"],
      [compact(window.failed), window.calls ? `failed · ${share}%` : "failed"],
      ...(unit ? [unit] : [])
    ]} />
    <Group title="Last 30 days"><Chart days={entry.days} today={readout.day} limit={limit} /></Group>
    {reasons.length > 0 && <Group title="Why calls failed"
      foot={reasons.some(([reason]) => !["authentication", "configuration", "refused"].includes(reason))
        ? "A failed call passes to the next in the order." : undefined}>
      {reasons.map(([reason, count]) => {
        const said = REASONS[reason] ?? { label: reason, hint: () => "" };
        return <Row key={reason} label={said.label} hint={said.hint(label) || undefined}><Value>{count.toLocaleString("en-GB")}</Value></Row>;
      })}
    </Group>}
    {entry.lastFailure && <Group title="Last failure">
      <Row label={entry.lastFailure.said || (REASONS[entry.lastFailure.reason ?? ""]?.label ?? "It failed")}
        hint={when(entry.lastFailure.at) || undefined} />
    </Group>}
  </>;
}

/* ── which page ── */

/** The Usage sub-page `sub` names: the list, one model, or a model's allowance. */
export function UsageSubPage({ sub, catalogue, write, open, onNotify }: {
  sub: SubPage;
  catalogue: ModelCatalogue;
  write: Write;
  open(sub: SubPage): void;
  onNotify(message: string): void;
}): ReactNode {
  const { value, error } = useServerSetting(SETTINGS.usage);
  const found = parseSub(sub.id);
  if (!found) return null;
  if (found.kind === "usage") return <UsageList provider={found.parts[0]} page={sub} onOpen={open} />;
  const [providerId, kind, model] = found.parts;
  if (found.kind === "allowance") {
    const provider = catalogue.providers.find((one) => one.id === providerId);
    const stored = provider?.models[kind]?.find((one) => one.id === model);
    if (!provider || !stored) return <Notice>This model is no longer on the server.</Notice>;
    return <AllowanceForm provider={provider} kind={kind} model={stored} write={write} onNotify={onNotify}
      onSaved={() => { if (sub.parent) open(sub.parent); }} />;
  }
  if (!value) return error ? <Notice>{error}</Notice> : <Placeholder rows={4} />;
  return <UsageModelView readout={value} providerId={providerId} kind={kind} model={model}
    catalogue={catalogue} page={sub} onOpen={open} />;
}
