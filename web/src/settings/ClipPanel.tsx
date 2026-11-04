/**
 * Settings ▸ Clips: whether the corpus is consulted unattended, what it holds, and which channels
 * it harvests.
 *
 * The page opens on the owner's two switches, which are Acervo's own and come back at once. What
 * the corpus holds is a call to a **separate service**, so it is asked for on its own and shown when
 * it answers, and its channel list — long, read rarely, changed more rarely still — is a sub-page
 * fetched only when it is opened. Acervo ships no channel list (`docs/features/spoken-clips.md`
 * §2.10): copying one here would create a second thing to keep in step.
 *
 * The corpus reading is deliberately not a health dashboard. It answers the two questions someone
 * actually has in front of this screen — does the service answer, and does it hold anything for the
 * language I am learning — and stops there.
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import { AcervoApiError, backendSession, type ClipSettings, type CorpusReadout } from "../api";
import { addChannel, channels, setChannelEnabled, SpeechRetrievalApiError } from "../clips";
import { OpenIcon } from "../icons";
import { isOpen, jobFor, jobStream } from "../jobs";
import { languageOf } from "../languages";
import { SETTINGS, useServerSetting } from "./cache";
import { Action, Group, Link, Notice, Placeholder, Row, Toggle, Value, useSubPage } from "./kit";

type Channel = Awaited<ReturnType<typeof channels>>[number];

/**
 * By language, then by the catalogue's own sections.
 *
 * The sections are the retrieval repository's curation — "Long-form conversation and contemporary
 * informal speech" is a judgement somebody made about what a learner gets from those channels, and
 * it is more use here than any grouping Acervo could invent.
 */
function grouped(rows: Channel[]): { language: string; name: string; rows: Channel[] }[] {
  const sections = new Map<string, { language: string; name: string; rows: Channel[] }>();
  for (const row of rows) {
    const name = row.section_name || "Other";
    const key = `${row.source_language}\u0000${name}`;
    const section = sections.get(key) ?? { language: row.source_language, name, rows: [] };
    section.rows.push(row);
    sections.set(key, section);
  }
  return [...sections.values()];
}

function reason(error: unknown, fallback: string): string {
  if (error instanceof AcervoApiError) return error.message;
  if (error instanceof SpeechRetrievalApiError) return error.message;
  return fallback;
}

export default function ClipPanel({ onNotify }: { onNotify(message: string): void }) {
  const { sub, open } = useSubPage();
  const { value: settings, error, set } = useServerSetting(SETTINGS.clips);
  const corpus = useServerSetting(SETTINGS.corpus);

  if (sub?.id === "channels") return <Channels onNotify={onNotify} />;

  const apply = async (changes: Partial<Pick<ClipSettings, "searchEnabled" | "selfContainedOnly">>) => {
    const before = settings;
    if (!before) return;
    set({ ...before, ...changes, chosen: true });
    try {
      set(await backendSession.saveClipSettings(changes));
    } catch (error) {
      set(before);
      onNotify(reason(error, "That change was not saved."));
    }
  };

  return <>
    <CorpusLine corpus={corpus.value} error={corpus.error} />

    {settings ? <Group>
      <Toggle
        label="Look for clips" hint="New words get short spoken examples from videos"
        checked={settings.searchEnabled} onChange={(on) => void apply({ searchEnabled: on })}
      />
      <Toggle
        label="Only passages that stand on their own" hint="Fewer clips, none that begin mid-thought"
        checked={settings.selfContainedOnly} onChange={(on) => void apply({ selfContainedOnly: on })}
      />
    </Group> : error ? <Notice>{error}</Notice> : <Placeholder rows={2} />}

    {corpus.value?.reachable && <Group>
      <Link label="Channels" onOpen={() => open({ id: "channels", title: "Channels" })} />
    </Group>}
  </>;
}

/** One line for what the corpus holds, or the one fact about it that needs acting on. */
function CorpusLine({ corpus, error }: { corpus: CorpusReadout | undefined; error: string | null }) {
  if (!corpus) return error ? <Notice>{error}</Notice> : <Placeholder rows={1} />;
  if (!corpus.configured) return <Notice>No clip corpus is set up on this server, so no clips can be found.</Notice>;
  if (!corpus.reachable) return <Notice>
    The clip corpus is not answering{corpus.error ? ` (${corpus.error})` : ""}. Clips already saved still play.
  </Notice>;
  if (!corpus.ready) return <Notice>The clip corpus has not built its index yet, so nothing can be searched.</Notice>;
  const languages = corpus.indexedLanguages ?? [];
  return <Group>
    <Row
      label="Clip corpus"
      hint={corpus.builtAt ? `Indexed ${new Date(corpus.builtAt).toLocaleDateString()}` : undefined}
    >
      <Value>
        {corpus.videos?.toLocaleString()} videos · {languages.map((code) => languageOf(code).name).join(", ") || "no language yet"}
      </Value>
    </Row>
    {/* The player's target text is the corpus's and not Acervo's (spoken-clips §2.13), and the one
        part of this that goes quiet without complaining — so it has a line. */}
    {corpus.translation && <Row label="Translated in the player">
      <Value mono={corpus.translation.available}>
        {corpus.translation.available ? corpus.translation.model || corpus.translation.provider : "Off: no model for the corpus"}
      </Value>
    </Row>}
  </Group>;
}

/** The fields the corpus needs for a channel. Everything else it fills in from the channel itself. */
const BLANK = { source_language: "", section_id: "", id: "", name: "", url: "" };

/** Clips ▸ Channels: read only when opened, because it is a call to the corpus every time. */
function Channels({ onNotify }: { onNotify(message: string): void }) {
  const [rows, setRows] = useState<Channel[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ ...BLANK });
  const [saving, setSaving] = useState(false);
  const live = useSyncExternalStore(jobStream.subscribe, jobStream.getStatus);
  const updating = isOpen(jobFor(live, "corpus.update", "corpus"));

  useEffect(() => {
    let current = true;
    void channels()
      .then((found) => { if (current) setRows(found); })
      .catch((error: unknown) => { if (current) setFailed(reason(error, "The channel list could not be read.")); });
    return () => { current = false; };
  }, []);

  /** Update now: the same job the nightly run uses, so pressing it twice asks for one update. */
  const update = async () => {
    try {
      jobStream.apply(await backendSession.enqueueJob({ kind: "corpus.update", subject: { kind: "corpus", id: "corpus" } }));
    } catch (error) {
      onNotify(reason(error, "The corpus could not be asked to update."));
    }
  };

  const add = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const created = await addChannel({ ...draft, enabled: true });
      setRows([...(rows ?? []), created as Channel]);
      setDraft({ ...BLANK });
      setAdding(false);
      onNotify(`Added ${created.name}. Its videos arrive with the next update.`);
    } catch (error) {
      onNotify(reason(error, "That channel could not be added."));
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (channel: Channel, enabled: boolean) => {
    const before = rows ?? [];
    setRows(before.map((row) => row.id === channel.id && row.source_language === channel.source_language ? { ...row, enabled } : row));
    try {
      await setChannelEnabled(channel.source_language, channel.id, enabled);
    } catch (error) {
      setRows(before);
      onNotify(reason(error, "That channel could not be changed."));
    }
  };

  return <>
    <Group>
      <Row label="Update now" hint="Fetch new videos and rebuild the index">
        <button type="button" className="tb-btn" disabled={updating} onClick={() => void update()}>
          {updating ? "Updating…" : "Update"}
        </button>
      </Row>
    </Group>

    {failed && <Notice>{failed}</Notice>}
    {!failed && !rows && <Placeholder rows={4} />}
    {rows && grouped(rows).map((section) => <Group
      key={`${section.language}/${section.name}`}
      title={`${languageOf(section.language).name} · ${section.name}`}
      count={`${section.rows.filter((row) => row.enabled).length} of ${section.rows.length} on`}
    >
      {section.rows.map((channel) => <Toggle
        key={channel.id} label={channel.name} checked={channel.enabled}
        hint={[...(channel.varieties ?? []), ...(channel.speech_style ?? [])].join(" · ") || undefined}
        onChange={(on) => void toggle(channel, on)}
      >
        {/* The useful thing to do with a channel you are deciding about is watch some of it. */}
        <a className="icon-btn" href={channel.url} target="_blank" rel="noreferrer noopener" aria-label={`Watch ${channel.name}`}>
          <OpenIcon />
        </a>
      </Toggle>)}
    </Group>)}

    {adding ? <form onSubmit={(event) => void add(event)}>
      <Group title="Add a channel" foot="The section is one the language already has. Its videos arrive with the next update.">
        {([
          ["source_language", "Language", "es"],
          ["section_id", "Section", "learning_and_language"],
          ["id", "Identifier", "easy-spanish"],
          ["name", "Name", "Easy Spanish"],
          ["url", "URL", "https://www.youtube.com/@EasySpanish/videos"]
        ] as const).map(([field, label, placeholder]) => <label key={field} className="pref-row">
          <span className="pref-text"><span className="pref-label">{label}</span></span>
          <input
            className="pref-input" required value={draft[field]} placeholder={placeholder} aria-label={label}
            onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
          />
        </label>)}
        <div className="pref-row pref-buttons">
          <button type="button" className="tb-btn" onClick={() => setAdding(false)}>Cancel</button>
          <button type="submit" className="tb-btn primary" disabled={saving}>Add channel</button>
        </div>
      </Group>
    </form> : rows && <Group foot="Changes take effect at the next update. Clips you already saved stay.">
      <Action onClick={() => setAdding(true)}>Add a channel…</Action>
    </Group>}
  </>;
}
