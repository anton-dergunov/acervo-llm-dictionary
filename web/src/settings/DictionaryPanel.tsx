import { useCallback, useEffect, useMemo, useState } from "react";
import { SETTINGS, useServerSetting } from "./cache";
import { Group, Notice, Row, Toggle, Value } from "./kit";
import {
  ANY_LANGUAGE,
  catalogue,
  groupedByLanguage,
  install,
  installed,
  isEnabled,
  knownDictionaries,
  setEnabled,
  uninstall,
  type CatalogueEntry,
  type InstallProgress
} from "../dictionaries";
import { storageReport, type InstalledDictionary, type StorageReport } from "../dictionaryStore";
import { languageOf } from "../languages";
import type { RemoteDictionary } from "../api";

/**
 * The Dictionaries pane: what exists, which of it is switched on here, and what this device holds.
 *
 * Acervo ships the *list* and never the data (§9), so every row is a set of facts and a URL until
 * someone asks for it. Turning a source on is a preference about this device — the phone and the
 * laptop legitimately want different ones — while storing one downloads a compiled artifact from
 * the server that built it.
 *
 * Licence and attribution are shown on every row because the obligation attaches to displaying the
 * content, and this is where someone decides to display it.
 */

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes >= 2 ** 30) return `${(bytes / 2 ** 30).toFixed(1)} GB`;
  if (bytes >= 2 ** 20) return `${Math.round(bytes / 2 ** 20)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * What to say about room on this device.
 *
 * Measured on the device probe: WebKit updates `estimate().usage` lazily and reports zero straight
 * after a 40 MiB write that plainly happened. Repeating a usage figure lower than what this pane
 * knows it is holding would be worse than saying nothing, so in that case it reports the headroom
 * instead — which is the number someone deciding whether to download is actually asking about.
 */
function storageLine(storage: StorageReport | null, storedBytes: number): string {
  if (!storage?.quotaBytes) return "This browser does not say how much room it gives Acervo";
  if (!storage.usedBytes || storage.usedBytes < storedBytes) {
    return `About ${formatBytes(storage.quotaBytes)} available`;
  }
  return `${formatBytes(storage.usedBytes)} of about ${formatBytes(storage.quotaBytes)} used`;
}

function languageName(code: string): string {
  return code === ANY_LANGUAGE ? "Any language" : languageOf(code).name;
}

function languageFlag(code: string): string {
  return code === ANY_LANGUAGE ? "🌐" : languageOf(code).flag;
}

function direction(entry: CatalogueEntry): string {
  const from = entry.sourceLang === ANY_LANGUAGE ? "any" : entry.sourceLang;
  const to = entry.targetLang === ANY_LANGUAGE ? "any" : entry.targetLang;
  return from === to ? `${from}, monolingual` : `${from} → ${to}`;
}

function progressLabel(progress: InstallProgress): string {
  const stage = progress.stage === "index" ? "index"
    : progress.stage === "payloads" ? "entries"
    : progress.stage === "saving" ? "storing" : "details";
  if (progress.stage === "saving") return "Storing on this device…";
  if (!progress.totalBytes) return `Downloading the ${stage}… ${formatBytes(progress.receivedBytes)}`;
  const percent = Math.round((progress.receivedBytes / progress.totalBytes) * 100);
  return `Downloading the ${stage}… ${percent}%`;
}

function DictionaryRow({ entry, local, remote, busy, onToggle, onInstall, onRemove }: {
  entry: CatalogueEntry;
  local: InstalledDictionary | undefined;
  remote: RemoteDictionary | undefined;
  busy: InstallProgress | null;
  onToggle(on: boolean): void;
  onInstall(): void;
  onRemove(): void;
}) {
  const [enabled, setLocalEnabled] = useState(() => isEnabled(entry.id));

  // A link-out has nothing to switch on and nothing to store: it is an address.
  if (entry.kind === "link") {
    return <Row label={entry.name} hint={`${direction(entry)} · opens on the web · ${entry.licence}`}>
      <a className="tb-btn" href={entry.url} target="_blank" rel="noreferrer noopener">Open</a>
    </Row>;
  }

  /* Licence and attribution are shown on every row because the obligation attaches to displaying
     the content, and this is where someone decides to display it. */
  const state = busy ? progressLabel(busy)
    : local ? `Stored · ${local.metadata.entryCount.toLocaleString()} entries · ${formatBytes(local.bytes)}`
    : entry.kind === "online" ? "Looked up as you need it"
    : remote ? `On your server · ${remote.entryCount.toLocaleString()} entries`
    : "Not compiled on your server yet";

  return <Toggle
    label={entry.name} hint={`${direction(entry)} · ${entry.licence} · ${state}`}
    checked={enabled} onChange={(on) => { setLocalEnabled(on); onToggle(on); }}
  >
    {entry.kind === "offline" && !local && <button
      type="button" className="tb-btn" disabled={!!busy || !remote}
      title={remote ? undefined : "Your server has not compiled this dictionary yet."}
      onClick={onInstall}
    >Store</button>}
    {entry.kind === "offline" && local
      && <button type="button" className="tb-btn danger" disabled={!!busy} onClick={onRemove}>Remove</button>}
  </Toggle>;
}

export default function DictionaryPanel({ onNotify }: { onNotify(message: string): void }) {
  const [local, setLocal] = useState<InstalledDictionary[]>([]);
  // What the server has compiled is the one thing here that needs it. Failing is ordinary: the
  // rows still render, and the ones already stored here still work.
  const { value: remote, error: remoteError } = useServerSetting(SETTINGS.dictionaries);
  const [storage, setStorage] = useState<StorageReport | null>(null);
  const [busy, setBusy] = useState<Record<string, InstallProgress>>({});

  const refresh = useCallback(async () => {
    setLocal(await installed());
    setStorage(await storageReport());
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  // The catalogue plus anything already stored here, because a server can compile a dictionary the
  // shipped list does not name and it would be strange for the pane to deny it exists.
  const groups = useMemo(
    () => groupedByLanguage([...knownDictionaries(local),
                             ...catalogue.filter((entry) => entry.kind === "link")]),
    [local]);

  async function storeLocally(entry: CatalogueEntry) {
    try {
      await install(entry.id, (progress) => setBusy((current) => ({ ...current, [entry.id]: progress })));
      onNotify(`${entry.name} is stored on this device.`);
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "That dictionary could not be stored.");
    } finally {
      setBusy(({ [entry.id]: _done, ...rest }) => rest);
      await refresh();
    }
  }

  async function removeLocally(entry: CatalogueEntry) {
    await uninstall(entry.id);
    onNotify(`${entry.name} was removed from this device. Every other dictionary is untouched.`);
    await refresh();
  }

  const storedCount = local.length;
  const storedBytes = local.reduce((total, record) => total + record.bytes, 0);

  return <>
    <Group foot={storage?.persisted ? "Storage here is protected from being cleared."
      : "This device may clear its storage if Acervo goes unused for a while."}>
      <Row
        label={storedCount === 0 ? "Nothing stored on this device"
          : `${storedCount} ${storedCount === 1 ? "dictionary" : "dictionaries"} on this device`}
        hint={storageLine(storage, storedBytes)}
      >{storedCount > 0 && <Value>{formatBytes(storedBytes)}</Value>}</Row>
    </Group>

    {(remote?.length === 0 || remoteError) && <Notice>
      Your server has not compiled any dictionaries, so none can be stored here.
      Build one with <code>acervo-worker dictionary build --id &lt;name&gt;</code>.
    </Notice>}

    {groups.map(([code, entries], index) => <Group
      key={code} title={`${languageFlag(code)} ${languageName(code)}`}
      foot={index === groups.length - 1 ? "Each dictionary downloads from its publisher. Switched on applies to this device only." : undefined}
    >
      {entries.map((entry) => <DictionaryRow
        key={entry.id}
        entry={entry}
        local={local.find((record) => record.id === entry.id)}
        remote={remote?.find((record) => record.id === entry.id)}
        busy={busy[entry.id] ?? null}
        onToggle={(on) => setEnabled(entry.id, on)}
        onInstall={() => void storeLocally(entry)}
        onRemove={() => void removeLocally(entry)}
      />)}
    </Group>)}
  </>;
}
