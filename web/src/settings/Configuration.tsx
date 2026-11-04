import { useState } from "react";
import { Action, Group, Link, Notice, Reorder, Row, useSubPage } from "./kit";
import type { Topic, Vocabulary } from "../domain";
import { languageOf } from "../languages";
import { repository, type ReplicaSnapshot } from "../repository";
import { topicOptions, vocabularies as configuredVocabularies } from "../selectors";

/**
 * The two things capture cannot work without: which languages this owner keeps, and which topics a
 * word can be filed under (`docs/architecture/data-model.md` — both are records, never a fixed
 * enum).
 *
 * Every action here is an ordinary online-only write through the repository, so it fails loudly and
 * changes nothing locally when the server is unreachable, exactly like editing an article.
 */

const LANGUAGE_TAG = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;

function parseLanguageList(value: string): string[] | null {
  const codes = value.split(",").map((code) => code.trim()).filter(Boolean);
  if (!codes.length || codes.some((code) => !LANGUAGE_TAG.test(code))) return null;
  return [...new Set(codes)];
}

/** A text field in a row, its label on the left. */
function Field({ label, value, placeholder, onChange }: {
  label: string;
  value: string;
  placeholder?: string;
  onChange(value: string): void;
}) {
  return <label className="pref-row">
    <span className="pref-text"><span className="pref-label">{label}</span></span>
    <input
      className="pref-input" value={value} placeholder={placeholder} aria-label={label}
      autoComplete="off" spellCheck={false} onChange={(event) => onChange(event.target.value)}
    />
  </label>;
}

/** Vocabularies ▸ one of them: its name, flag and the three languages it is written in. */
function VocabularyForm({ vocabulary, onSave, onRemove, onDone }: {
  vocabulary: Vocabulary;
  onSave(changes: Partial<Vocabulary>): void;
  onRemove(): void;
  onDone(): void;
}) {
  const fallback = languageOf(vocabulary.language);
  const [name, setName] = useState(vocabulary.displayName ?? fallback.name);
  const [flag, setFlag] = useState(vocabulary.flag ?? fallback.flag);
  const [definitionLang, setDefinitionLang] = useState(vocabulary.definitionLang);
  const [glossLangs, setGlossLangs] = useState(vocabulary.glossLangs.join(", "));
  const [notesLang, setNotesLang] = useState(vocabulary.notesLang);

  return <>
    <Group foot="Language tags, most preferred first, such as es, en or zh-Hans.">
      <Field label="Name" value={name} onChange={setName} />
      <Field label="Flag" value={flag} onChange={setFlag} />
      <Field label="Senses defined in" value={definitionLang} onChange={setDefinitionLang} />
      <Field label="Translated into" value={glossLangs} placeholder="en, ru" onChange={setGlossLangs} />
      <Field label="Notes written in" value={notesLang} onChange={setNotesLang} />
    </Group>
    <div className="pref-buttons">
      <button type="button" className="tb-btn" onClick={onDone}>Cancel</button>
      <button type="button" className="tb-btn primary" onClick={() => {
        onDone();
        onSave({
          displayName: name.trim() || null,
          flag: flag.trim() || null,
          definitionLang: definitionLang.trim(),
          glossLangs: parseLanguageList(glossLangs) ?? vocabulary.glossLangs,
          notesLang: notesLang.trim() || vocabulary.notesLang
        });
      }}>Save</button>
    </div>
    <Group><Action danger onClick={onRemove}>Remove this vocabulary</Action></Group>
  </>;
}

export function VocabularyEditor({ snapshot, onNotify, onChanged }: {
  snapshot: ReplicaSnapshot;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  const entries = configuredVocabularies(snapshot);
  const { sub, open, close } = useSubPage();
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const counts = new Map<string, number>();
  snapshot.lexemes.filter((lexeme) => !lexeme.deleted)
    .forEach((lexeme) => counts.set(lexeme.language, (counts.get(lexeme.language) ?? 0) + 1));

  async function run(action: () => Promise<unknown>, failure: string): Promise<boolean> {
    setBusy(true);
    try {
      await action();
      onChanged();
      return true;
    } catch (error) {
      onNotify(error instanceof Error ? error.message : failure);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function add() {
    const language = code.trim();
    if (!LANGUAGE_TAG.test(language)) {
      onNotify("That is not a language tag. Try es, en, ru or zh-Hans.");
      return;
    }
    if (entries.some((entry) => entry.language === language)) {
      onNotify(`You already keep a ${language} vocabulary.`);
      return;
    }
    const defaults = languageOf(language);
    // A language the table does not know has no sensible pivot to guess, so English is the
    // starting point and the row is immediately editable.
    const glossLangs = defaults.glossLangs.length ? defaults.glossLangs : ["en"];
    void run(() => repository.saveVocabulary({
      language,
      definitionLang: language,
      glossLangs,
      notesLang: glossLangs[0],
      displayName: defaults.name,
      flag: defaults.flag,
      order: entries.length
    }), "That vocabulary could not be added.").then((added) => {
      if (!added) return;
      setAdding(false);
      setCode("");
    });
  }

  function remove(vocabulary: Vocabulary): boolean {
    const words = counts.get(vocabulary.language) ?? 0;
    if (words > 0) {
      // Removing the configuration would leave those words with no gloss preference and no way back
      // to it, which reads as data loss even though nothing was deleted.
      onNotify(`${vocabulary.displayName ?? vocabulary.language} still has ${words} ${words === 1 ? "word" : "words"}. Delete or move them first.`);
      return false;
    }
    void run(() => repository.delete("vocabularies", vocabulary.id), "That vocabulary could not be removed.");
    return true;
  }

  const editing = sub?.id.startsWith("vocabulary:") ? entries.find((entry) => `vocabulary:${entry.id}` === sub.id) : undefined;
  if (editing) return <VocabularyForm
    key={editing.id}
    vocabulary={editing}
    onDone={close}
    onSave={(changes) => void run(() => repository.saveVocabulary({
      language: editing.language,
      definitionLang: editing.definitionLang,
      glossLangs: editing.glossLangs,
      notesLang: editing.notesLang,
      displayName: editing.displayName,
      flag: editing.flag,
      order: editing.order,
      ...changes
    }, editing.id), "That vocabulary could not be saved.")}
    onRemove={() => { if (remove(editing)) close(); }}
  />;

  return <>
    {entries.length ? <Group>
      {entries.map((vocabulary) => {
        const fallback = languageOf(vocabulary.language);
        const name = vocabulary.displayName ?? fallback.name;
        const words = counts.get(vocabulary.language) ?? 0;
        return <Link
          key={vocabulary.id}
          label={`${vocabulary.flag ?? fallback.flag}  ${name}`}
          hint={`${vocabulary.language} · defined in ${vocabulary.definitionLang} · translated into ${vocabulary.glossLangs.join(", ")} · notes in ${vocabulary.notesLang}`}
          value={`${words.toLocaleString()} ${words === 1 ? "word" : "words"}`}
          onOpen={() => open({ id: `vocabulary:${vocabulary.id}`, title: name })}
        />;
      })}
    </Group> : <Notice>None yet. Add the first language you are learning: a word needs one to be captured.</Notice>}

    {adding ? <>
      <Group foot="A language tag, such as es, en, ru or zh-Hans.">
        <label className="pref-row">
          <span className="pref-text"><span className="pref-label">Language tag</span></span>
          <input
            className="pref-input" value={code} autoComplete="off" spellCheck={false} placeholder="es"
            aria-label="Language tag" onChange={(event) => setCode(event.target.value)}
          />
        </label>
      </Group>
      <div className="pref-buttons">
        <button type="button" className="tb-btn" onClick={() => { setAdding(false); setCode(""); }}>Cancel</button>
        <button type="button" className="tb-btn primary" disabled={busy} onClick={add}>Add vocabulary</button>
      </div>
    </> : <Group><Action onClick={() => setAdding(true)}>Add a vocabulary…</Action></Group>}
  </>;
}

/** Topics ▸ one of them: its name and icon. */
function TopicForm({ topic, onSave, onRemove, onDone }: {
  topic: Topic;
  onSave(name: string, icon: string): void;
  onRemove(): void;
  onDone(): void;
}) {
  const [name, setName] = useState(topic.name);
  const [icon, setIcon] = useState(topic.icon ?? "");
  return <>
    <Group>
      <Field label="Name" value={name} onChange={setName} />
      <Field label="Icon" value={icon} placeholder="💬" onChange={setIcon} />
    </Group>
    <div className="pref-buttons">
      <button type="button" className="tb-btn" onClick={onDone}>Cancel</button>
      <button type="button" className="tb-btn primary" onClick={() => { onDone(); onSave(name.trim(), icon.trim()); }}>Save</button>
    </div>
    <Group><Action danger onClick={() => { onDone(); onRemove(); }}>Remove this topic</Action></Group>
  </>;
}

export function TopicEditor({ snapshot, language, onNotify, onChanged }: {
  snapshot: ReplicaSnapshot;
  language: string;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  const topics = snapshot.topics.filter((topic) => !topic.deleted)
    .slice()
    .sort((left, right) => left.order - right.order || left.name.localeCompare(right.name));
  const counts = new Map(topicOptions(snapshot, language).map((option) => [option.id, option.count ?? 0]));
  const { sub, open, close } = useSubPage();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, failure: string): Promise<boolean> {
    setBusy(true);
    try {
      await action();
      onChanged();
      return true;
    } catch (error) {
      onNotify(error instanceof Error ? error.message : failure);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function add() {
    const trimmed = name.trim();
    if (!trimmed) {
      onNotify("A topic needs a name.");
      return;
    }
    if (topics.some((topic) => topic.name.toLowerCase() === trimmed.toLowerCase())) {
      onNotify(`You already have a topic called ${trimmed}.`);
      return;
    }
    void run(() => repository.saveTopic({
      name: trimmed, icon: icon.trim() || null, order: topics.length
    }), "That topic could not be added.").then((added) => {
      if (!added) return;
      setAdding(false);
      setName("");
      setIcon("");
    });
  }

  /* Two writes rather than one: the repository saves a record at a time, and reordering is rare
     enough that a second round trip costs less than a bespoke batch path would. */
  function move(index: number, direction: -1 | 1) {
    const other = topics[index + direction];
    const topic = topics[index];
    if (!other) return;
    void run(async () => {
      await repository.saveTopic({ name: topic.name, icon: topic.icon, order: other.order }, topic.id);
      await repository.saveTopic({ name: other.name, icon: other.icon, order: topic.order }, other.id);
    }, "Those topics could not be reordered.");
  }

  const editing = sub?.id.startsWith("topic:") ? topics.find((topic) => `topic:${topic.id}` === sub.id) : undefined;
  if (editing) return <TopicForm
    key={editing.id}
    topic={editing}
    onDone={close}
    onSave={(nextName, nextIcon) => void run(
      () => repository.saveTopic({ name: nextName || editing.name, icon: nextIcon || null, order: editing.order }, editing.id),
      "That topic could not be saved."
    )}
    onRemove={() => void run(() => repository.delete("topics", editing.id), "That topic could not be removed.")}
  />;

  return <>
    {topics.length ? <Group foot="New entries are filed under these and nothing else.">
      {topics.map((topic, index) => {
        const count = counts.get(topic.id) ?? 0;
        return <Row key={topic.id} label={`${topic.icon ?? "📌"}  ${topic.name}`} hint={`${count} ${count === 1 ? "word" : "words"}`}>
          <Reorder name={topic.name} first={index === 0} last={index === topics.length - 1} onMove={(direction) => move(index, direction)} />
          <button type="button" className="tb-btn" onClick={() => open({ id: `topic:${topic.id}`, title: topic.name })}>Edit</button>
        </Row>;
      })}
    </Group> : <Notice>None yet. Words cannot be filed until you add a topic.</Notice>}

    {adding ? <>
      <Group>
        <Field label="Name" value={name} placeholder="Slang" onChange={setName} />
        <Field label="Icon" value={icon} placeholder="💬" onChange={setIcon} />
      </Group>
      <div className="pref-buttons">
        <button type="button" className="tb-btn" onClick={() => { setAdding(false); setName(""); setIcon(""); }}>Cancel</button>
        <button type="button" className="tb-btn primary" disabled={busy} onClick={add}>Add topic</button>
      </div>
    </> : <Group><Action onClick={() => setAdding(true)}>Add a topic…</Action></Group>}
  </>;
}
