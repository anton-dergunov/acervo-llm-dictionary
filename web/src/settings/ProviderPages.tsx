import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AcervoApiError,
  backendSession,
  type Allowance,
  type ModelCatalogue,
  type ModelProvider,
  type ProviderBody,
  type ProviderChange,
  type ProviderFamily,
  type ProviderModel,
  type ProviderVoice,
  type UsageCounts
} from "../api";
import { SETTINGS, useServerSetting } from "./cache";
import { CloseIcon } from "../icons";
import { flagOf, languageName, mainRegion } from "../languages";
import { LanguageSearch } from "./LanguageSearch";
import {
  Action, Group, Link, Notice, Placeholder, Row, Segmented, Select, StateMark, TextField, Toggle, Value,
  type SubPage
} from "./kit";

/**
 * Settings ▸ Providers' sub-pages: adding a provider, a provider's own page, and picking its models.
 *
 * A provider is one account: one key, offering models of several kinds. What it offers comes from
 * the provider itself where it can say — its model list, its voices — and is typed where it cannot.
 * Every write is one request answered by the whole readout (`ProviderChange`), which replaces what
 * is shown: taking a model away also takes it out of the orders, and the page shows what the server
 * did rather than guess it. A key is sent once and never comes back; the page shows its first and
 * last four characters.
 */

export type Write = (call: () => Promise<ProviderChange>) => Promise<ProviderChange | string>;

export const KIND_TITLES: Record<string, string> = {
  text: "Text", image: "Pictures", audio: "Voices", ocr: "Reading photos"
};
const ADD_TITLES: Record<string, string> = {
  text: "Add a text model", image: "Add a picture model", audio: "Add a voice model", ocr: "Add a model for photos"
};
/** How many of a long voice list show before "Show all". */
const VOICES_SHOWN = 6;

/* A sub-page's id carries what it is about as JSON, because a model's id may hold any character —
   `qwen3-235b:free` has a colon. */
export const subId = (kind: string, ...parts: string[]) => `${kind}:${JSON.stringify(parts)}`;
export function parseSub(id: string): { kind: string; parts: string[] } | null {
  const at = id.indexOf(":");
  if (at < 0) return id === "add-provider" ? { kind: id, parts: [] } : null;
  try { return { kind: id.slice(0, at), parts: JSON.parse(id.slice(at + 1)) as string[] }; }
  catch { return null; }
}

export const ADD_PROVIDER: SubPage = { id: "add-provider", title: "Add a provider" };
export const providerPage = (provider: ModelProvider): SubPage =>
  ({ id: subId("provider", provider.id), title: provider.label });

/** Usage, of every provider or of one; a model's own usage; and a model's free allowance. Their
    pages are `UsagePages.tsx`. */
export const USAGE_PAGES = ["usage", "usage-model", "allowance"];
export const usagePage = (parent?: SubPage, provider?: string): SubPage =>
  ({ id: provider ? subId("usage", provider) : subId("usage"), title: "Usage", parent });
export const usageModelPage = (parent: SubPage, provider: string, kind: string, model: string): SubPage =>
  ({ id: subId("usage-model", provider, kind, model), title: model, parent });
export const allowancePage = (parent: SubPage, provider: string, kind: string, model: string): SubPage =>
  ({ id: subId("allowance", provider, kind, model), title: "Free allowance", parent });
export const modelPage = (provider: ModelProvider, model: string): SubPage =>
  ({ id: subId("model", provider.id, model), title: model, parent: providerPage(provider) });

export function host(url: string | null | undefined): string {
  if (!url) return "";
  try { return new URL(url).host; } catch { return url; }
}

const message = (error: unknown, fallback: string) =>
  error instanceof AcervoApiError || error instanceof Error ? error.message : fallback;

/** Whether a provider can be asked, in two or three words. */
export function stateOf(provider: ModelProvider): { ok: boolean; words: string } {
  if (provider.check && !provider.check.ok) {
    return { ok: false, words: provider.check.reason === "authentication" ? "Key refused" : "Not answering" };
  }
  if (provider.reason) return { ok: false, words: "Not set up" };
  return { ok: true, words: "Works" };
}

/** "1M", "10k", "1,000", "500": the figure a free allowance is read in at a glance. */
export function figure(amount: number): string {
  if (amount >= 1_000_000 && amount % 100_000 === 0) return `${amount / 1_000_000}M`;
  if (amount >= 10_000 && amount % 100 === 0) return `${amount / 1000}k`;
  return amount.toLocaleString("en-GB");
}

/** "142", "1.4k", "980k", "1.2M": a count read at a glance, where the exact figure does not matter. */
export function compact(count: number): string {
  const short = (value: number, unit: string) => `${value < 10 ? value.toFixed(1).replace(/\.0$/, "") : Math.round(value)}${unit}`;
  if (count >= 1_000_000) return short(count / 1_000_000, "M");
  if (count >= 1000) return short(count / 1000, "k");
  return count.toLocaleString("en-GB");
}

/** "10 a day", "1M characters a month". */
export function allowanceAmount(allowance: Allowance): string {
  const unit = allowance.unit === "calls" ? "" : ` ${allowance.unit}`;
  return `${figure(allowance.amount)}${unit} a ${allowance.per}`;
}

export function allowanceWords(allowance: ProviderModel["allowance"]): string | null {
  return allowance ? `${allowanceAmount(allowance)} free` : null;
}

/** How much of an allowance is gone: "96 of 500 today", or with its unit, "212k of 1M characters
    this month". Calls go without, as the allowance's own words do. */
export function gaugeWords(gauge: Allowance & { used: number }, withUnit = false): string {
  const unit = withUnit && gauge.unit !== "calls" ? ` ${gauge.unit}` : "";
  return `${compact(gauge.used)} of ${figure(gauge.amount)}${unit} ${gauge.per === "day" ? "today" : "this month"}`;
}

/** One period's counts over several models: a provider's, from its models'. */
export function providerTotal(models: { today: UsageCounts; month: UsageCounts; all: UsageCounts }[],
  period: "today" | "month" | "all"): UsageCounts {
  return models.reduce<UsageCounts>((sum, model) => {
    const counts = model[period];
    return {
      calls: sum.calls + counts.calls, failed: sum.failed + counts.failed,
      inputTokens: sum.inputTokens + counts.inputTokens, outputTokens: sum.outputTokens + counts.outputTokens,
      characters: sum.characters + counts.characters, pictures: sum.pictures + counts.pictures,
      photos: sum.photos + counts.photos,
      costUsd: counts.costUsd === null ? sum.costUsd : (sum.costUsd ?? 0) + counts.costUsd
    };
  }, { calls: 0, failed: 0, inputTokens: 0, outputTokens: 0, characters: 0, pictures: 0, photos: 0, costUsd: null });
}

/** "Today: 142 calls · 3 failed", for the row that leads to Usage. */
export function todayWords(counts: UsageCounts | undefined): string {
  if (!counts || counts.calls === 0) return "Nothing asked today";
  const failed = counts.failed ? ` · ${counts.failed.toLocaleString("en-GB")} failed` : "";
  return `Today: ${counts.calls.toLocaleString("en-GB")} call${counts.calls === 1 ? "" : "s"}${failed}`;
}

function voiceHint(model: ProviderModel): string {
  const languages = model.languages?.length
    ? model.languages.map(languageName).join(", ")
    : model.direction ? "any language" : null;
  return [model.direction ? "Takes a direction" : null, languages, allowanceWords(model.allowance)]
    .filter(Boolean).join(" · ");
}

function checkedWhen(at: string | null | undefined): string {
  if (!at) return "";
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return "";
  const time = date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const day = date.toDateString() === new Date().toDateString()
    ? "today" : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return `Checked ${day}, ${time}`;
}

/** A provider's models with one of them replaced, or taken away when `next` is null. */
export function withModel(provider: ModelProvider, kind: string, id: string, next: ProviderModel | null) {
  const models = provider.models[kind] ?? [];
  const at = models.findIndex((model) => model.id === id);
  const changed = next === null ? models.filter((model) => model.id !== id)
    : at < 0 ? [...models, next] : models.map((model, index) => index === at ? next : model);
  return { ...provider.models, [kind]: changed };
}

/** A model as it is sent: only the fields it has, so "any language" is the absence of a list. */
export function cleanModel(model: ProviderModel): ProviderModel {
  const kept: ProviderModel = { id: model.id };
  if (model.direction) kept.direction = true;
  if (model.languages?.length) kept.languages = model.languages;
  if (model.voices?.length) kept.voices = model.voices;
  if (model.allowance) kept.allowance = model.allowance;
  return kept;
}

/** The two buttons a form ends with. */
export function Buttons({ busy, label, busyLabel = "Checking…", onCancel, onSubmit }: {
  busy: boolean;
  label: string;
  busyLabel?: string;
  onCancel?(): void;
  onSubmit(): void;
}) {
  return <div className="pref-buttons">
    {onCancel && <button type="button" className="tb-btn" disabled={busy} onClick={onCancel}>Cancel</button>}
    <button type="button" className="tb-btn primary" disabled={busy} onClick={onSubmit}>{busy ? busyLabel : label}</button>
  </div>;
}

/** Where a credentials file usually is, said under the field: the question is "where is it?", and
    gcloud keeps your own sign-in in a folder a file dialog hides. */
const CREDENTIALS_FOOT = <>Your own sign-in is usually at <code>~/.config/gcloud/application_default_credentials.json</code>.
  It is kept on your server.</>;

/**
 * A credentials file, chosen or pasted, and read as text: the server takes its text and nothing else.
 * Pasting is for a file the dialog cannot reach — gcloud keeps it in a hidden folder, and an iPad
 * reaches no folder on the Mac at all — and the clipboard crosses devices. What is pasted is checked
 * to be JSON here, so a half-copied file is said before anything is sent.
 *
 * A real button opens the hidden file input, so it is reached by keyboard like any other.
 */
function CredentialsFile({ hint, button, busy = false, onRead }: {
  hint?: ReactNode;
  button: string;
  busy?: boolean;
  onRead(text: string, name: string): void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");
  const [wrong, setWrong] = useState<string | null>(null);

  function use() {
    try {
      const parsed: unknown = JSON.parse(pasted);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not an object");
    } catch {
      setWrong("That is not the whole file: it should start with { and end with }.");
      return;
    }
    onRead(pasted, "Pasted");
    setPasting(false); setPasted(""); setWrong(null);
  }

  return <>
    <div className="pref-row">
      <span className="pref-text">
        <span className="pref-label">Credentials file</span>
        {hint && <span className="pref-hint">{hint}</span>}
      </span>
      <button type="button" className="tb-btn" disabled={busy} onClick={() => setPasting(!pasting)}>Paste…</button>
      <button type="button" className="tb-btn" disabled={busy} onClick={() => input.current?.click()}>{button}</button>
      <input
        ref={input} type="file" accept="application/json,.json" hidden aria-label="Credentials file"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void file.text().then((text) => onRead(text, file.name));
          event.target.value = "";
        }}
      />
    </div>
    {pasting && <div className="pref-row stack">
      <textarea
        className="pref-text-area short" aria-label="The credentials file’s contents" value={pasted} autoFocus
        spellCheck={false} placeholder={'{ "type": "authorized_user", … }'}
        onChange={(event) => { setPasted(event.target.value); setWrong(null); }}
      />
      <div className="pref-buttons">
        {wrong && <span className="pref-hint warn">{wrong}</span>}
        <button type="button" className="tb-btn" onClick={() => { setPasting(false); setPasted(""); setWrong(null); }}>Cancel</button>
        <button type="button" className="tb-btn primary" disabled={!pasted.trim()} onClick={use}>Use it</button>
      </div>
    </div>}
  </>;
}

/** The family's settings that apply in this sign-in mode, each a field or a pick. */
function SettingFields({ family, mode, values, onChange }: {
  family: ProviderFamily;
  mode: "key" | "file";
  values: Record<string, string>;
  onChange(name: string, value: string): void;
}) {
  return <>{shownFields(family, mode).map((field) => field.choices.length
    ? <Select
      key={field.name} label={field.label} hint={field.hint ?? undefined}
      value={values[field.name] || field.default || field.choices[0]}
      options={field.choices.map((choice) => ({ value: choice, label: choice }))}
      onChange={(value) => onChange(field.name, value)}
    />
    : <TextField
      key={field.name} label={field.label} value={values[field.name] ?? ""} mono={field.name === "baseUrl"}
      placeholder={field.default ?? field.hint ?? ""} onChange={(value) => onChange(field.name, value)}
    />)}</>;
}

function shownFields(family: ProviderFamily, mode: "key" | "file") {
  return family.fields.filter((field) => field.needed !== "file" || mode === "file");
}

/** The kinds one sign-in reaches, in words: "voices and reading photos". */
function reaches(family: ProviderFamily, mode: "key" | "file"): string {
  const kinds = family.kinds.filter((kind) => mode === "file" || !family.fileOnly.includes(kind))
    .map((kind) => KIND_TITLES[kind].toLowerCase());
  return kinds.length <= 1 ? kinds.join("") : `${kinds.slice(0, -1).join(", ")} and ${kinds[kinds.length - 1]}`;
}

type SignIn = "key" | "file";

function signInOptions(family: ProviderFamily): { value: SignIn; label: string; hint: string }[] {
  return [
    { value: "key", label: "API key", hint: `Reaches ${reaches(family, "key")}` },
    { value: "file", label: "Credentials file", hint: `Reaches ${reaches(family, "file")}` }
  ];
}

/** Only what a field was given: an empty one is the family's default. */
function filled(values: Record<string, string>, family: ProviderFamily, mode: "key" | "file") {
  return Object.fromEntries(shownFields(family, mode)
    .map((field) => [field.name, (values[field.name] ?? "").trim()] as const)
    .filter(([, value]) => value));
}

/* ── Add a provider ── */

function AddProvider({ families, onChoose }: { families: ProviderFamily[]; onChoose(family: ProviderFamily): void }) {
  const groups = [...new Set(families.map((family) => family.group))];
  return <>{groups.map((name) => {
    const members = families.filter((family) => family.group === name);
    /* A group of one named after its one member, "Any compatible service", needs no title. */
    const title = members.length === 1 && members[0].label === name ? undefined : name;
    return <Group key={name} title={title}>
      {members.map((family) => <Link key={family.id} label={family.label} hint={family.hint} onOpen={() => onChoose(family)} />)}
    </Group>;
  })}</>;
}

/** Choosing a family opens its page empty: the few fields it needs, then one check. */
function NewProvider({ family, write, onCancel, onAdded }: {
  family: ProviderFamily;
  write: Write;
  onCancel(): void;
  onAdded(answer: ProviderChange): void;
}) {
  const [label, setLabel] = useState(family.label);
  const [mode, setMode] = useState<"key" | "file">("key");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(family.fields.filter((field) => field.default).map((field) => [field.name, field.default as string])));
  const [key, setKey] = useState("");
  const [file, setFile] = useState<{ text: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const usualKinds = readyKinds(family, mode);
  const [usual, setUsual] = useState(true);

  async function add() {
    const body: ProviderBody = { family: family.id, label: label.trim() || family.label, settings: filled(values, family, mode) };
    if (usualKinds.length) body.ready = usual;
    if (mode === "file") {
      if (!file) { setRefused("Choose the credentials file first."); return; }
      body.credentials = file.text;
    } else if (key.trim()) {
      body.key = key.trim();
    }
    setBusy(true);
    setRefused(null);
    const answer = await write(() => backendSession.addProvider(body));
    setBusy(false);
    if (typeof answer === "string") setRefused(answer);
    else onAdded(answer);
  }

  const keyed = family.credential !== "none";
  return <>
    {refused && <Notice>{refused}</Notice>}
    {family.credential === "key-or-file" && <Group>
      <Segmented<SignIn> label="Sign in with" value={mode} options={signInOptions(family)} onChange={setMode} />
    </Group>}
    <Group aligned>
      <TextField label="Name" value={label} onChange={setLabel} />
      <SettingFields family={family} mode={mode} values={values}
        onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))} />
    </Group>
    {keyed && mode === "key" && <Group
      title="Key" aligned
      foot={<>{family.keyUrl && <>Create one at <a href={family.keyUrl} target="_blank" rel="noreferrer noopener">{host(family.keyUrl)}</a>. </>}
        It is kept on your server.</>}
    >
      <TextField
        label={family.keyLabel} hint={family.credential === "optional" ? "If the service asks for one" : undefined}
        value={key} secret mono placeholder="Paste it here" onChange={setKey}
      />
    </Group>}
    {mode === "file" && <Group title="Credentials" foot={CREDENTIALS_FOOT}>
      <CredentialsFile hint={file?.name ?? "A service account, or your own sign-in"} button="Choose…"
        onRead={(text, name) => setFile({ text, name })} />
    </Group>}
    {usualKinds.length > 0 && <Group>
      <Toggle label="Add the usual models" hint={`${sentence(usualKinds)}, ready to use`} checked={usual} onChange={setUsual} />
    </Group>}
    <Buttons busy={busy} label="Check and add" onCancel={onCancel} onSubmit={() => void add()} />
  </>;
}

const KIND_WORDS: Record<string, string> = { text: "text", image: "pictures", audio: "voices", ocr: "reading photos" };

/** The kinds "Add the usual models" adds, signed in this way: a key leaves out what needs a file. */
function readyKinds(family: ProviderFamily, mode: "key" | "file"): string[] {
  const kinds = (family.ready ?? []).filter((one) => mode === "file" || !one.fileOnly).map((one) => one.kind);
  return ["text", "image", "audio", "ocr"].filter((kind) => kinds.includes(kind));
}

/** "Text, pictures and voices". */
function sentence(kinds: string[]): string {
  const words = kinds.map((kind) => KIND_WORDS[kind] ?? kind);
  const said = words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}` : words[0];
  return said.charAt(0).toUpperCase() + said.slice(1);
}

/* ── a provider's own page ── */

function ProviderView({ provider, family, write, onOpen, onRemoved, onNotify }: {
  provider: ModelProvider;
  family: ProviderFamily | undefined;
  write: Write;
  onOpen(sub: SubPage): void;
  onRemoved(): void;
  onNotify(message: string): void;
}) {
  const stored: "key" | "file" = provider.credential.kind === "file" ? "file" : "key";
  const [mode, setMode] = useState<"key" | "file">(stored);
  const [replacing, setReplacing] = useState(false);
  const [key, setKey] = useState("");
  const [file, setFile] = useState<{ text: string; name: string } | null>(null);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [armed, setArmed] = useState(false);

  useEffect(() => { setMode(stored); }, [stored]);

  async function run(what: string, call: () => Promise<ProviderChange>, inline: boolean): Promise<boolean> {
    setBusy(what);
    setRefused(null);
    const answer = await write(call);
    setBusy(null);
    if (typeof answer === "string") {
      if (inline) setRefused(answer); else onNotify(answer);
      return false;
    }
    return true;
  }

  const switching = mode !== stored;
  const page = providerPage(provider);
  const { value: usage } = useServerSetting(SETTINGS.usage);
  const usageToday = usage ? providerTotal(usage.providers.find((one) => one.id === provider.id)?.models ?? [], "today") : undefined;
  const values = draft ?? provider.settings;

  /** The models a sign-in can keep: a key reaches no file-only kind, so those go with the file. */
  const keptModels = (next: "key" | "file") => Object.fromEntries(Object.entries(provider.models)
    .filter(([kind]) => next === "file" || !family?.fileOnly.includes(kind)));

  async function replaceKey() {
    if (!key.trim()) { setRefused(`Paste the new ${family?.keyLabel ?? "key"} first.`); return; }
    const body: ProviderBody = { key: key.trim() };
    if (switching) Object.assign(body, { models: keptModels("key"), settings: filled(values, family!, "key") });
    if (await run("key", () => backendSession.changeProvider(provider.id, body), true)) {
      setKey(""); setReplacing(false); setDraft(null);
    }
  }

  async function replaceFile(text: string) {
    const body: ProviderBody = { credentials: text };
    if (switching && family) {
      body.settings = filled(values, family, "file");
      if (!body.settings.project) { setFile({ text, name: "" }); setRefused("Give the project first, then choose the file."); return; }
    }
    if (await run("file", () => backendSession.changeProvider(provider.id, body), true)) {
      setFile(null); setDraft(null);
    }
  }

  async function saveSettings() {
    if (!draft || !family) return;
    const body: ProviderBody = { settings: filled(draft, family, mode) };
    if (await run("settings", () => backendSession.changeProvider(provider.id, body), true)) setDraft(null);
  }

  const removeModel = (kind: string, id: string) => void run(
    `remove ${id}`, () => backendSession.changeProvider(provider.id, { models: withModel(provider, kind, id, null) }), false);

  const keyGroup = (() => {
    if (family?.credential === "none") return <Group title="Key">
      <Row label="No key needed" hint="It answers at its address" />
      <CheckRow provider={provider} busy={busy === "check"} onCheck={() => void run("check", () => backendSession.checkProvider(provider.id), true)} />
    </Group>;
    if (mode === "file") return <Group title="Credentials" foot={CREDENTIALS_FOOT}>
      <CredentialsFile
        hint={switching ? (file?.name || "A service account, or your own sign-in") : provider.credential.account ?? "Your own sign-in"}
        button={busy === "file" ? "Checking…" : switching ? "Choose…" : "Replace…"} busy={busy === "file"}
        onRead={(text, name) => { setFile({ text, name }); void replaceFile(text); }}
      />
      {!switching && <CheckRow provider={provider} busy={busy === "check"} onCheck={() => void run("check", () => backendSession.checkProvider(provider.id), true)} />}
    </Group>;
    const keyLabel = family?.keyLabel ?? "API key";
    return <Group title="Key" aligned={replacing || switching}
      foot={(replacing || switching) && family?.keyUrl
        ? <>Create one at <a href={family.keyUrl} target="_blank" rel="noreferrer noopener">{host(family.keyUrl)}</a>. It is kept on your server.</>
        : undefined}>
      {replacing || switching
        ? <TextField label={keyLabel} value={key} secret mono placeholder="Paste it here" onChange={setKey} />
        : <Row label={keyLabel} hint="Kept on your server">
          <Value mono>{provider.credential.hint ?? "None"}</Value>
          <button type="button" className="tb-btn" onClick={() => setReplacing(true)}>{provider.credential.hint ? "Replace" : "Add"}</button>
        </Row>}
      {!(replacing || switching) && <CheckRow provider={provider} busy={busy === "check"}
        onCheck={() => void run("check", () => backendSession.checkProvider(provider.id), true)} />}
    </Group>;
  })();

  const fields = family ? shownFields(family, mode) : [];
  return <>
    {refused && <Notice>{refused}</Notice>}
    {family?.credential === "key-or-file" && <Group>
      <Segmented<SignIn> label="Sign in with" value={mode} options={signInOptions(family)}
        onChange={(next) => { setMode(next); setRefused(null); }} />
    </Group>}
    {keyGroup}
    {(replacing || (switching && mode === "key")) && <Buttons
      busy={busy === "key"} label="Check and save"
      onCancel={() => { setReplacing(false); setKey(""); setMode(stored); setRefused(null); }}
      onSubmit={() => void replaceKey()}
    />}
    {family && fields.length > 0 && <Group aligned>
      <SettingFields family={family} mode={mode} values={values}
        onChange={(name, value) => setDraft({ ...values, [name]: value })} />
    </Group>}
    {draft !== null && !switching && <Buttons
      busy={busy === "settings"} label="Check and save"
      onCancel={() => setDraft(null)} onSubmit={() => void saveSettings()}
    />}
    {!switching && (family?.kinds ?? Object.keys(provider.models))
      .filter((kind) => mode === "file" || !family?.fileOnly.includes(kind))
      .map((kind) => <Group key={kind} title={KIND_TITLES[kind] ?? kind}>
        {(provider.models[kind] ?? []).map((model) => kind === "audio"
          ? <Link
            key={model.id} label={model.id} mono hint={voiceHint(model) || undefined}
            onOpen={() => onOpen(modelPage(provider, model.id))}
          />
          : <Row key={model.id} label={model.id} mono hint={allowanceWords(model.allowance) ?? undefined}>
            <button type="button" className="icon-btn" aria-label={`Remove ${model.id}`}
              disabled={busy === `remove ${model.id}`} onClick={() => removeModel(kind, model.id)}><CloseIcon /></button>
          </Row>)}
        <Action onClick={() => onOpen({ id: subId("add-model", provider.id, kind), title: ADD_TITLES[kind] ?? "Add a model", parent: page })}>
          Add a model…
        </Action>
      </Group>)}
    <Group>
      <Link label="Usage" hint={todayWords(usageToday)} onOpen={() => onOpen(usagePage(page, provider.id))} />
      {provider.usageUrl && <Row label={host(provider.usageUrl)} hint="Your limits and the bill">
        <a className="tb-btn" href={provider.usageUrl} target="_blank" rel="noreferrer noopener"
          aria-label={`Open ${provider.label}’s own page`}>Open</a>
      </Row>}
    </Group>
    <Group foot={armed ? "Its key goes too, and every order and voice choice that names it." : undefined}>
      <Action danger disabled={busy === "remove"} onClick={() => {
        if (!armed) { setArmed(true); return; }
        void run("remove", () => backendSession.removeProvider(provider.id), false).then((done) => { if (done) onRemoved(); });
      }}>{armed ? `Remove ${provider.label} and its key` : "Remove this provider"}</Action>
    </Group>
  </>;
}

/** What the last check said, and the button that asks again. */
function CheckRow({ provider, busy, onCheck }: { provider: ModelProvider; busy: boolean; onCheck(): void }) {
  const check = provider.check;
  const when = checkedWhen(check?.at);
  const hint = check && !check.ok && check.reason === "authentication"
    ? [when, "nothing is sent to it until it works"].filter(Boolean).join(" · ") : when;
  return <div className="pref-row">
    <span className="pref-text">
      {check ? <StateMark ok={check.ok}>{check.said}</StateMark> : <StateMark ok={false}>Not checked yet</StateMark>}
      {hint && <span className="pref-hint">{hint}</span>}
    </span>
    <button type="button" className="tb-btn" disabled={busy} onClick={onCheck}>{busy ? "Checking…" : "Check again"}</button>
  </div>;
}

/* ── Add a model ── */

/**
 * One box: it searches what the provider lists, and what it does not list can still be added as
 * typed — a model too new for the list, or one the provider cannot list at all. A second "type its
 * name" field beside the search asked for the same name twice.
 */
function AddModel({ provider, kind, write, onNotify }: {
  provider: ModelProvider;
  kind: string;
  write: Write;
  onNotify(message: string): void;
}) {
  const [listing, setListing] = useState<{ listed: boolean; models: string[] } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    backendSession.providerModels(provider.id, kind).then(
      (answer) => { if (live) setListing(answer); },
      (error: unknown) => { if (live) setFailed(message(error, `${provider.label} could not be asked for its models.`)); });
    return () => { live = false; };
  }, [provider.id, kind, provider.label]);

  const added = new Set((provider.models[kind] ?? []).map((model) => model.id));
  const listed = listing?.listed ? listing.models : [];
  const typed = query.trim();
  const shown = useMemo(() => {
    const wanted = typed.toLowerCase();
    return listed.filter((id) => !wanted || id.toLowerCase().includes(wanted));
  }, [listed, typed]);
  /* What is typed, once the list holds nothing like it: offered as typed, and said so. While
     something listed still matches, the box is a search, and "Add “flash”" would be noise. */
  const unlisted = typed && shown.length === 0 ? typed : null;

  async function add(id: string) {
    if (!id || added.has(id)) return;
    setBusy(id);
    const answer = await write(() => backendSession.changeProvider(provider.id, {
      models: withModel(provider, kind, id, { id })
    }));
    setBusy(null);
    if (typeof answer === "string") onNotify(answer);
    else { onNotify(`${id} added.`); if (id === unlisted) setQuery(""); }
  }

  if (!listing && !failed) return <Placeholder rows={4} />;
  const searching = listing?.listed === true;
  const label = searching ? `Search ${provider.label}’s models` : "The model’s name";
  const unlistedRow = unlisted && (added.has(unlisted)
    ? <Row label={unlisted} mono><Value>Added</Value></Row>
    : <Action disabled={busy !== null} onClick={() => void add(unlisted)}>
      {busy === unlisted ? "Adding…" : `Add “${unlisted}”`}
    </Action>);
  const why = failed
    ? "Type the name as its own page spells it."
    : `${provider.label} does not list ${searching ? "it" : "these"}, so add it only as its own page spells it.`;
  return <>
    {failed && <Notice>{failed}</Notice>}
    <Group foot={searching ? undefined : why}>
      <label className="pref-row">
        <input
          className={`pref-input${searching ? "" : " mono"}`} type={searching ? "search" : "text"} value={query}
          aria-label={label} placeholder={searching ? label : provider.models[kind]?.[0]?.id ?? label}
          autoComplete="off" spellCheck={false} autoFocus
          onChange={(event) => setQuery(event.target.value)}
          /* Enter adds only a name the list holds, or any name where there is no list: a half-typed
             search must not become a model. */
          onKeyDown={(event) => {
            if (event.key === "Enter" && typed && (!searching || listed.includes(typed))) void add(typed);
          }}
        />
      </label>
    </Group>
    {searching
      ? <Group title={`${provider.label} offers`} count={`${listed.length}`} foot={unlisted ? why : undefined}>
        {listed.length === 0 && !unlisted && <Row label="It lists none" />}
        {shown.map((id) => added.has(id)
          ? <Row key={id} label={id} mono><Value>Added</Value></Row>
          : <button key={id} type="button" className="pref-row" disabled={busy !== null} onClick={() => void add(id)}>
            <span className="pref-text"><span className="pref-label mono">{id}</span></span>
            {busy === id && <Value>Adding…</Value>}
          </button>)}
        {unlistedRow}
      </Group>
      : unlistedRow && <Group>{unlistedRow}</Group>}
  </>;
}

/* ── a model's free allowance ── */

/** What each kind's allowance is counted in, as its providers meter it. A picture is one call, and a
    photo one call, so those have one unit; text is metered in requests or in tokens, a voice in
    characters or in requests. */
const ALLOWANCE_UNITS: Record<string, { value: string; label: string }[]> = {
  text: [{ value: "calls", label: "Calls" }, { value: "tokens", label: "Tokens" }],
  image: [{ value: "pictures", label: "Pictures" }],
  audio: [{ value: "characters", label: "Characters" }, { value: "calls", label: "Calls" }],
  ocr: [{ value: "photos", label: "Photos" }]
};
/** What a new allowance starts as: the way each kind's free tiers are usually published. */
const ALLOWANCE_STARTS: Record<string, Omit<Allowance, "amount">> = {
  text: { unit: "calls", per: "day" },
  image: { unit: "pictures", per: "day" },
  audio: { unit: "characters", per: "month" },
  ocr: { unit: "photos", per: "month" }
};

/**
 * A model's free allowance: how much, counted in what, each day or month. Usage measures against it
 * and does nothing else with it — the provider's own limit is what refuses a call. A voice's is on
 * its own page; a text, picture or photo model's is reached from its Usage page, since those have
 * no page of their own.
 */
export function AllowanceForm({ provider, kind, model, write, onNotify, onSaved }: {
  provider: ModelProvider;
  kind: string;
  model: ProviderModel;
  write: Write;
  onNotify(message: string): void;
  onSaved?(): void;
}) {
  const [draft, setDraft] = useState<{ amount: string; unit: string; per: "day" | "month" } | null>(null);
  const [busy, setBusy] = useState(false);
  const start = ALLOWANCE_STARTS[kind] ?? { unit: "calls", per: "day" };
  const shown = draft ?? {
    amount: model.allowance ? String(model.allowance.amount) : "",
    unit: model.allowance?.unit ?? start.unit,
    per: model.allowance?.per ?? start.per
  };
  const offered = ALLOWANCE_UNITS[kind] ?? [{ value: "calls", label: "Calls" }];
  /* A unit stored some other way is still shown, so opening the page does not quietly change it. */
  const units = offered.some((one) => one.value === shown.unit)
    ? offered : [...offered, { value: shown.unit, label: shown.unit[0].toUpperCase() + shown.unit.slice(1) }];
  const amount = Number(shown.amount);

  async function save() {
    setBusy(true);
    const allowance = amount > 0 ? { amount, unit: shown.unit, per: shown.per } : undefined;
    const answer = await write(() => backendSession.changeProvider(provider.id, {
      models: withModel(provider, kind, model.id, cleanModel({ ...model, allowance }))
    }));
    setBusy(false);
    if (typeof answer === "string") { onNotify(answer); return; }
    setDraft(null);
    onSaved?.();
  }

  return <>
    <Group title="Free allowance" aligned
      foot={provider.usageUrl
        ? <>Your own limit is on <a href={provider.usageUrl} target="_blank" rel="noreferrer noopener">{host(provider.usageUrl)}</a>. Usage measures against it.</>
        : "Usage measures against it."}>
      <TextField label="Amount" value={shown.amount} placeholder="None"
        onChange={(value) => setDraft({ ...shown, amount: value.replace(/[^0-9]/g, "") })} />
      {units.length > 1 && <Select label="Counted in" value={shown.unit} options={units}
        onChange={(value) => setDraft({ ...shown, unit: value })} />}
      <Select label="Each" value={shown.per}
        options={[{ value: "day", label: "Day" }, { value: "month", label: "Month" }]}
        onChange={(value) => setDraft({ ...shown, per: value })} />
    </Group>
    {draft && <Buttons
      busy={busy} label={shown.amount ? "Save" : "Clear"} busyLabel="Saving…"
      onCancel={() => setDraft(null)} onSubmit={() => void save()}
    />}
  </>;
}

/* ── a voice model ── */

function VoiceModel({ provider, model, family, write, onOpen, onRemoved, onNotify }: {
  provider: ModelProvider;
  model: ProviderModel;
  family: ProviderFamily | undefined;
  write: Write;
  onOpen(sub: SubPage): void;
  onRemoved(): void;
  onNotify(message: string): void;
}) {
  const [voices, setVoices] = useState<{ listed: boolean; voices: ProviderVoice[] } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [direction, setDirection] = useState<boolean | null>(null);
  const typedVoices = model.voices ?? [];

  useEffect(() => {
    let live = true;
    backendSession.providerVoices(provider.id, model.id).then(
      (answer) => { if (live) setVoices(answer); },
      (error: unknown) => { if (live) setFailed(message(error, `${provider.label} could not be asked for its voices.`)); });
    return () => { live = false; };
    /* Typed voices change with the model; listed ones with the provider. */
  }, [provider.id, model.id, provider.label, typedVoices.length]);

  async function save(next: ProviderModel): Promise<boolean> {
    setBusy(true);
    const answer = await write(() => backendSession.changeProvider(provider.id, {
      models: withModel(provider, "audio", model.id, cleanModel(next))
    }));
    setBusy(false);
    if (typeof answer === "string") { onNotify(answer); return false; }
    return true;
  }

  const page = modelPage(provider, model.id);
  const languages = model.languages ?? [];
  const listedVoices = voices?.listed ? voices.voices : [];

  return <>
    <Group>
      <Toggle
        label="Takes a direction" hint="Reads as asked: warmly, slowly, as in Argentina"
        checked={direction ?? model.direction === true} disabled={busy}
        onChange={(checked) => {
          /* The switch moves at once, and goes back if the save is refused. */
          setDirection(checked);
          void save({ ...model, direction: checked }).finally(() => setDirection(null));
        }}
      />
      <Select
        label="Languages" value={languages.length ? "some" : "any"} disabled={busy}
        options={[{ value: "any", label: "Any language" }, { value: "some", label: "Only some…" }]}
        onChange={(value) => {
          if (value === "any") void save({ ...model, languages: undefined });
          else onOpen({ id: subId("languages", provider.id, model.id), title: "Languages", parent: page });
        }}
      />
      {languages.length > 0 && <Link
        label="Speaks" value={languages.map(languageName).join(", ")}
        onOpen={() => onOpen({ id: subId("languages", provider.id, model.id), title: "Languages", parent: page })}
      />}
    </Group>
    <AllowanceForm provider={provider} kind="audio" model={model} write={write} onNotify={onNotify} />
    {failed
      ? <Notice>{failed}</Notice>
      : !voices ? <Placeholder rows={3} />
      : voices.listed
        ? <Group title="Voices" count={`${listedVoices.length} listed by ${provider.label}`}
          foot="Who reads each language is chosen in Pronunciation.">
          {listedVoices.length === 0 && <Row label="It lists none for this model" />}
          {(all ? listedVoices : listedVoices.slice(0, VOICES_SHOWN)).map((voice) =>
            <Row key={`${voice.name} ${voice.locale ?? ""}`} label={voice.label || voice.name} hint={voiceWords(voice)} />)}
          {!all && listedVoices.length > VOICES_SHOWN && <Action onClick={() => setAll(true)}>Show all {listedVoices.length}</Action>}
        </Group>
        : <Group title="Voices" count={typedVoices.length ? `${typedVoices.length} typed` : undefined}
          foot={<>{family?.voicesUrl && <>Its voices are listed at <a href={family.voicesUrl} target="_blank" rel="noreferrer noopener">{host(family.voicesUrl)}</a>. </>}
            Who reads each language is chosen in Pronunciation.</>}>
          {typedVoices.map((voice) => <Row key={voice.name} label={voice.name} hint={voiceWords(voice)}>
            <button type="button" className="icon-btn" aria-label={`Remove ${voice.name}`} disabled={busy}
              onClick={() => void save({ ...model, voices: typedVoices.filter((one) => one.name !== voice.name) })}><CloseIcon /></button>
          </Row>)}
          <div className="pref-row">
            <span className="pref-text"><span className="pref-label">Add a voice</span></span>
            <input className="pref-input mono" value={typed} aria-label="Voice name" autoComplete="off" spellCheck={false}
              onChange={(event) => setTyped(event.target.value)} />
            <button type="button" className="tb-btn" disabled={busy || !typed.trim() || typedVoices.some((one) => one.name === typed.trim())}
              onClick={() => void save({ ...model, voices: [...typedVoices, { name: typed.trim() }] }).then((done) => { if (done) setTyped(""); })}>Add</button>
          </div>
        </Group>}
    <Group>
      <Action danger disabled={busy} onClick={() => void (async () => {
        setBusy(true);
        const answer = await write(() => backendSession.changeProvider(provider.id, { models: withModel(provider, "audio", model.id, null) }));
        setBusy(false);
        if (typeof answer === "string") onNotify(answer); else onRemoved();
      })()}>Remove this model</Action>
    </Group>
  </>;
}

function voiceWords(voice: ProviderVoice): string | undefined {
  const region = voice.locale ? mainRegion(voice.locale) : null;
  const where = voice.locale
    ? `${region ? `${flagOf(region)} ` : ""}${new Intl.DisplayNames(["en"], { type: "language" }).of(voice.locale) ?? voice.locale}`
    : null;
  return [voice.gender, voice.note, where].filter(Boolean).join(" · ") || undefined;
}

/** The languages a voice model is sent, nearest first, and a search to add one. */
function ModelLanguages({ provider, model, write, onNotify }: {
  provider: ModelProvider;
  model: ProviderModel;
  write: Write;
  onNotify(message: string): void;
}) {
  const chosen = model.languages ?? [];
  const save = async (languages: string[]) => {
    const answer = await write(() => backendSession.changeProvider(provider.id, {
      models: withModel(provider, "audio", model.id, cleanModel({ ...model, languages }))
    }));
    if (typeof answer === "string") onNotify(answer);
  };
  return <>
    {chosen.length > 0 && <Group foot="Removing the last one lets it speak any language.">
      {chosen.map((tag) => <Row key={tag} label={`${flagOf(mainRegion(tag))} ${languageName(tag)}`}>
        <button type="button" className="icon-btn" aria-label={`Remove ${languageName(tag)}`}
          onClick={() => void save(chosen.filter((one) => one !== tag))}><CloseIcon /></button>
      </Row>)}
    </Group>}
    <LanguageSearch
      label="Find a language" unavailable={Object.fromEntries(chosen.map((tag) => [tag, "Added"]))}
      onChoose={(entry) => void save([...chosen, entry.tag])}
    />
  </>;
}

/* ── which page ── */

/** The sub-page `sub` names, or null when it is not one of these. */
export function ProviderSubPage({ sub, catalogue, write, open, close, onNotify }: {
  sub: SubPage;
  catalogue: ModelCatalogue;
  write: Write;
  open(sub: SubPage): void;
  close(): void;
  onNotify(message: string): void;
}): ReactNode {
  const found = parseSub(sub.id);
  if (!found) return null;
  const families = new Map(catalogue.families.map((family) => [family.id, family]));
  if (found.kind === "add-provider") {
    return <AddProvider families={catalogue.families}
      onChoose={(family) => open({ id: subId("new", family.id), title: family.label, parent: ADD_PROVIDER })} />;
  }
  if (found.kind === "new") {
    const family = families.get(found.parts[0]);
    if (!family) return null;
    return <NewProvider family={family} write={write} onCancel={() => open(ADD_PROVIDER)} onAdded={(answer) => {
      const added = answer.providers.find((one) => one.id === answer.provider);
      if (added) open(providerPage(added)); else close();
    }} />;
  }
  const provider = catalogue.providers.find((one) => one.id === found.parts[0]);
  /* A provider removed from under its page — here or on another device — leaves nothing to show. */
  if (!provider) return <Notice>This provider is no longer on the server.</Notice>;
  const family = families.get(provider.family);
  switch (found.kind) {
    case "provider":
      return <ProviderView key={provider.id} provider={provider} family={family} write={write} onOpen={open}
        onRemoved={close} onNotify={onNotify} />;
    case "add-model":
      return <AddModel provider={provider} kind={found.parts[1]} write={write} onNotify={onNotify} />;
    case "model":
    case "languages": {
      const model = (provider.models.audio ?? []).find((one) => one.id === found.parts[1]);
      if (!model) return <Notice>This model is no longer on {provider.label}.</Notice>;
      if (found.kind === "languages") return <ModelLanguages provider={provider} model={model} write={write} onNotify={onNotify} />;
      return <VoiceModel provider={provider} model={model} family={family} write={write} onOpen={open}
        onRemoved={() => open(providerPage(provider))} onNotify={onNotify} />;
    }
  }
  return null;
}
