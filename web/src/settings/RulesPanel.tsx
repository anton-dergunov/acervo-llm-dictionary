import { useEffect, useState } from "react";
import { AcervoApiError, backendSession } from "../api";
import { SETTINGS, useServerSetting } from "./cache";
import { Group, Notice, Placeholder } from "./kit";

/**
 * Settings ▸ Rules: free text the models are given with everything they write for you.
 *
 * Saved with a button rather than on every keystroke: this is prose, and a rule saved half-typed
 * would reach the next entry written while you were still typing it.
 */
export default function RulesPanel({ onNotify }: { onNotify(message: string): void }) {
  const { value: stored, error, set } = useServerSetting(SETTINGS.rules);
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  /* The draft starts from what the server holds, once; a refresh behind it must not erase typing. */
  useEffect(() => { if (stored && draft === null) setDraft(stored.rules); }, [stored, draft]);

  const save = async () => {
    if (draft === null) return;
    setSaving(true);
    try {
      const saved = await backendSession.savePromptRules(draft);
      set(saved);
      setDraft(saved.rules);
      onNotify(saved.rules ? "Rules saved." : "Rules cleared.");
    } catch (error) {
      onNotify(error instanceof AcervoApiError ? error.message : "Your rules were not saved.");
    } finally {
      setSaving(false);
    }
  };

  if (!stored) return error ? <Notice>{error}</Notice> : <Placeholder rows={1} />;

  const text = draft ?? stored.rules;
  const over = text.trim().length > stored.limit;
  const unchanged = text.trim() === stored.rules;
  return <Group
    title="Rules for everything written for you"
    foot="Applies to new entries, examples, chat, pictures, stories and clip choices. Ask again to rewrite what exists."
  >
    <div className="pref-row stack">
      <textarea
        className="pref-text-area"
        aria-label="Rules for generated content"
        value={text}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={"For example:\nI am vegan, so never show or mention meat or fish as food.\n"
          + "Never use profanity in an example."}
      />
      <div className="pref-buttons">
        <span className={`pref-hint${over ? " warn" : ""}`}>{text.trim().length} / {stored.limit}</span>
        <button type="button" className="tb-btn primary" disabled={saving || over || unchanged} onClick={() => void save()}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  </Group>;
}
