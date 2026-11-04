import { useState } from "react";
import type { LanguageEntry } from "../api";
import { Action, Group, Link, Notice, Reorder, Row, Select, TextArea, TextField, useSubPage, type SubPage } from "./kit";
import { CEFR_LEVELS, LEARNER_NOTE_LIMIT, type CefrLevel, type Topic, type Vocabulary, type VocabularyInput } from "../domain";
import { automaticFlag, flagFor, flagOf, languageName, mainRegion, regionName, varietyOptions } from "../languages";
import { CloseIcon } from "../icons";
import { SETTINGS, useServerSetting } from "./cache";
import { LanguageSearch } from "./LanguageSearch";
import { repository, type ReplicaSnapshot } from "../repository";
import { topicOptions, vocabularies as configuredVocabularies } from "../selectors";

/**
 * The two things capture cannot work without: which languages this owner keeps, and which topics a
 * word can be filed under (`docs/architecture/data-model.md` — both are records, never a fixed
 * enum).
 *
 * Every action here is an ordinary online-only write through the repository, so it fails loudly and
 * changes nothing locally when the server is unreachable, exactly like editing an article.
 *
 * A language is always shown by its name and flag; the tag is how it is stored, never what is read
 * (`docs/features/settings.md`, "Vocabularies").
 */

const LEVEL_NAMES: Record<CefrLevel, string> = {
  A1: "Beginner", A2: "Elementary", B1: "Intermediate", B2: "Upper intermediate", C1: "Advanced", C2: "Proficient"
};

/** A vocabulary as it is being edited: on its page and on the pages its languages are chosen on. */
interface VocabularyDraft {
  /** The record being edited, or null for one being added. */
  id: string | null;
  language: string;
  displayName: string;
  /** The owner's own flag, or "" for the one that follows the variety. */
  flag: string;
  region: string;
  definitionLang: string;
  glossLangs: string[];
  notesLang: string;
  level: CefrLevel | "";
  learnerNote: string;
}

function draftOf(vocabulary: Vocabulary): VocabularyDraft {
  return {
    id: vocabulary.id,
    language: vocabulary.language,
    displayName: vocabulary.displayName ?? languageName(vocabulary.language),
    flag: vocabulary.flag ?? "",
    region: vocabulary.region ?? "",
    definitionLang: vocabulary.definitionLang,
    glossLangs: vocabulary.glossLangs,
    notesLang: vocabulary.notesLang,
    level: vocabulary.level ?? "",
    learnerNote: vocabulary.learnerNote ?? ""
  };
}

/**
 * A new vocabulary, filled in the way the owner's others are: translated into the languages they
 * already translate into most, and defined in the language itself, as every vocabulary starts.
 */
function newDraft(language: LanguageEntry, others: Vocabulary[]): VocabularyDraft {
  const used = new Map<string, number>();
  others.forEach((entry) => entry.glossLangs.forEach((code, index) =>
    used.set(code, (used.get(code) ?? 0) + (entry.glossLangs.length - index))));
  const preferred = [...used.entries()].sort((a, b) => b[1] - a[1]).map(([code]) => code)
    .filter((code) => code !== language.tag);
  const fallback = [...(typeof navigator === "undefined" ? [] : navigator.languages ?? []), "en", "es"]
    .map((code) => code.split("-")[0]).find((code) => code !== language.tag) ?? "en";
  const glossLangs = preferred.length ? preferred : [fallback];
  return {
    id: null, language: language.tag, displayName: language.name, flag: "", region: "",
    definitionLang: language.tag, glossLangs, notesLang: glossLangs[0], level: "", learnerNote: ""
  };
}

/**
 * The vocabulary being edited, kept outside the page: the window draws each sub-page afresh, so a
 * draft held in the page's own state would be lost the moment one of its languages is chosen.
 */
let editing: VocabularyDraft | null = null;

/** A language as it reads in a row: the owner's own flag where they keep it, else its country's. */
function presented(code: string, kept: Vocabulary[]): string {
  const vocabulary = kept.find((entry) => entry.language === code);
  return `${vocabulary ? flagFor(vocabulary) : flagOf(mainRegion(code))} ${languageName(code)}`;
}

/** Vocabularies ▸ one of them: what it is called, its variety, its three languages and its learner. */
function VocabularyForm({ draft, kept, busy, page, onChange, onSave, onCancel, onRemove }: {
  draft: VocabularyDraft;
  kept: Vocabulary[];
  busy: boolean;
  page: SubPage;
  onChange(changes: Partial<VocabularyDraft>): void;
  onSave(): void;
  onCancel(): void;
  onRemove(): void;
}) {
  const { open } = useSubPage();
  /* Which varieties the language has comes from the server, which reads it from CLDR; any variety a
     voice is declared for is offered too. Offline, only the one already chosen. */
  const catalogue = useServerSetting(SETTINGS.languages).value;
  const voices = useServerSetting(SETTINGS.pronunciations).value;
  const declared = Object.values(voices?.orders ?? {}).flat()
    .flatMap((model) => model.voices[draft.language] ?? [])
    .flatMap((voice) => voice.locale ? [voice.locale] : []);
  const choices = catalogue?.languages.find((entry) => entry.tag === draft.language)?.varieties ?? [];
  const varieties = varietyOptions(choices, declared, draft.region || null);
  const choose = (field: "definition" | "gloss" | "notes", title: string) =>
    open({ id: `${page.id}:${field}`, title, parent: page });

  return <>
    <Group aligned>
      <TextField label="Name" value={draft.displayName} onChange={(displayName) => onChange({ displayName })} />
      <TextField
        label="Flag" value={draft.flag} maxLength={32}
        placeholder={automaticFlag(draft.language, draft.region || null)}
        onChange={(flag) => onChange({ flag })}
      />
      <Select
        label="Variety" value={draft.region}
        options={[{ value: "", label: "None" }, ...varieties]}
        // A flag follows the variety it was chosen for; one pasted in is the owner's to paste again.
        onChange={(region) => onChange({ region, flag: "" })}
      />
    </Group>
    <Group title="Written in">
      <Link label="Senses defined in" value={presented(draft.definitionLang, kept)}
        onOpen={() => choose("definition", "Senses defined in")} />
      <Link label="Translated into" value={draft.glossLangs.map((code) => presented(code, kept)).join(", ")}
        onOpen={() => choose("gloss", "Translated into")} />
      <Link label="Notes written in" value={presented(draft.notesLang, kept)}
        onOpen={() => choose("notes", "Notes written in")} />
    </Group>
    <Group title="You" aligned>
      <Select
        label="Level" value={draft.level}
        options={[{ value: "" as const, label: "Not set" },
          ...CEFR_LEVELS.map((level) => ({ value: level, label: `${level} · ${LEVEL_NAMES[level]}` }))]}
        onChange={(level) => onChange({ level })}
      />
      <TextArea
        label="About you" value={draft.learnerNote} limit={LEARNER_NOTE_LIMIT}
        placeholder={"Your goals, what you know well and what you don't.\n"
          + "For example: preparing for a trip to Argentina; the subjunctive is my weak spot."}
        onChange={(learnerNote) => onChange({ learnerNote })}
      />
    </Group>
    <div className="pref-buttons">
      <button type="button" className="tb-btn" onClick={onCancel}>Cancel</button>
      <button type="button" className="tb-btn primary" disabled={busy} onClick={onSave}>
        {draft.id ? "Save" : "Add vocabulary"}
      </button>
    </div>
    {draft.id && <Group><Action danger onClick={onRemove}>Remove this vocabulary</Action></Group>}
  </>;
}

/** A vocabulary ▸ Translated into: the gloss languages, most preferred first, and a way to add one. */
function GlossLanguages({ draft, kept, onChange }: {
  draft: VocabularyDraft;
  kept: Vocabulary[];
  onChange(glossLangs: string[]): void;
}) {
  const list = draft.glossLangs;
  const move = (index: number, direction: -1 | 1) => {
    const next = [...list];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    onChange(next);
  };
  return <>
    <Group foot="The first is the one a word's one-line gloss is written in.">
      {list.map((code, index) => <Row key={code} label={presented(code, kept)}>
        <Reorder name={languageName(code)} first={index === 0} last={index === list.length - 1}
          onMove={(direction) => move(index, direction)} />
        <button type="button" className="icon-btn" aria-label={`Remove ${languageName(code)}`}
          disabled={list.length === 1} onClick={() => onChange(list.filter((one) => one !== code))}>
          <CloseIcon />
        </button>
      </Row>)}
    </Group>
    <LanguageSearch
      label="Add a language to translate into"
      unavailable={Object.fromEntries(list.map((code) => [code, "Already in the list"]))}
      onChoose={(language) => onChange([...list, language.tag])}
    />
  </>;
}

export function VocabularyEditor({ snapshot, onNotify, onChanged }: {
  snapshot: ReplicaSnapshot;
  onNotify(message: string): void;
  onChanged(): void;
}) {
  const entries = configuredVocabularies(snapshot);
  const { sub, open, close } = useSubPage();
  const [draft, keep] = useState<VocabularyDraft | null>(() => editing);
  const setDraft = (next: VocabularyDraft | null) => { editing = next; keep(next); };
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

  function leave() {
    close();
    setDraft(null);
  }

  function save(current: VocabularyDraft) {
    if (current.learnerNote.trim().length > LEARNER_NOTE_LIMIT) {
      onNotify(`What you say about yourself may be at most ${LEARNER_NOTE_LIMIT} characters.`);
      return;
    }
    const record = current.id ? entries.find((entry) => entry.id === current.id) : undefined;
    const input: VocabularyInput = {
      language: current.language,
      definitionLang: current.definitionLang,
      glossLangs: current.glossLangs,
      notesLang: current.notesLang,
      displayName: current.displayName.trim() || null,
      flag: current.flag.trim() || null,
      region: current.region || null,
      level: current.level || null,
      learnerNote: current.learnerNote.trim() || null,
      order: record?.order ?? entries.length
    };
    void run(() => repository.saveVocabulary(input, current.id ?? undefined),
      current.id ? "That vocabulary could not be saved." : "That vocabulary could not be added.")
      .then((saved) => { if (saved) leave(); });
  }

  function remove(vocabulary: Vocabulary) {
    const words = counts.get(vocabulary.language) ?? 0;
    if (words > 0) {
      // Removing the configuration would leave those words with no gloss preference and no way back
      // to it, which reads as data loss even though nothing was deleted.
      onNotify(`${vocabulary.displayName ?? languageName(vocabulary.language)} still has ${words} ${words === 1 ? "word" : "words"}. Delete or move them first.`);
      return;
    }
    void run(() => repository.delete("vocabularies", vocabulary.id), "That vocabulary could not be removed.")
      .then((removed) => { if (removed) leave(); });
  }

  if (sub?.id === "vocabulary:add") return <LanguageSearch
    label="Find a language"
    unavailable={Object.fromEntries(entries.map((entry) => [entry.language, "Already kept"]))}
    onChoose={(language) => {
      setDraft(newDraft(language, entries));
      open({ id: "vocabulary:new", title: language.name });
    }}
  />;

  const [, key, field] = sub?.id.match(/^vocabulary:([^:]+)(?::(\w+))?$/) ?? [];
  const record = key ? entries.find((entry) => entry.id === key) : undefined;
  const current = draft && (draft.id ?? "new") === key ? draft : record ? draftOf(record) : null;
  if (key && current) {
    const page: SubPage = sub?.parent ?? sub!;
    const change = (changes: Partial<VocabularyDraft>) => setDraft({ ...current, ...changes });
    if (field === "gloss") return <GlossLanguages draft={current} kept={entries}
      onChange={(glossLangs) => change({ glossLangs })} />;
    if (field === "definition" || field === "notes") return <LanguageSearch
      label={field === "definition" ? "Find the language senses are defined in" : "Find the language notes are written in"}
      onChoose={(language) => {
        change(field === "definition" ? { definitionLang: language.tag } : { notesLang: language.tag });
        open(page);
      }}
    />;
    return <VocabularyForm
      key={key} draft={current} kept={entries} busy={busy} page={page}
      onChange={change} onCancel={leave} onSave={() => save(current)}
      onRemove={() => { if (record) remove(record); }}
    />;
  }

  return <>
    {entries.length ? <Group>
      {entries.map((vocabulary) => {
        const name = vocabulary.displayName ?? languageName(vocabulary.language);
        const words = counts.get(vocabulary.language) ?? 0;
        const hint = [
          vocabulary.region ? regionName(vocabulary.region) : null,
          vocabulary.level,
          `translated into ${vocabulary.glossLangs.map(languageName).join(", ")}`
        ].filter(Boolean).join(" · ");
        return <Link
          key={vocabulary.id}
          label={`${flagFor(vocabulary)}  ${name}`}
          hint={hint}
          value={`${words.toLocaleString()} ${words === 1 ? "word" : "words"}`}
          onOpen={() => { setDraft(draftOf(vocabulary)); open({ id: `vocabulary:${vocabulary.id}`, title: name }); }}
        />;
      })}
    </Group> : <Notice>None yet. Add the first language you are learning: a word needs one to be captured.</Notice>}
    <Group><Action onClick={() => open({ id: "vocabulary:add", title: "Add a language" })}>Add a language…</Action></Group>
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
    <Group aligned>
      <TextField label="Name" value={name} onChange={setName} />
      <TextField label="Icon" value={icon} placeholder="💬" onChange={setIcon} />
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
      <Group aligned>
        <TextField label="Name" value={name} placeholder="Slang" onChange={setName} />
        <TextField label="Icon" value={icon} placeholder="💬" onChange={setIcon} />
      </Group>
      <div className="pref-buttons">
        <button type="button" className="tb-btn" onClick={() => { setAdding(false); setName(""); setIcon(""); }}>Cancel</button>
        <button type="button" className="tb-btn primary" disabled={busy} onClick={add}>Add topic</button>
      </div>
    </> : <Group><Action onClick={() => setAdding(true)}>Add a topic…</Action></Group>}
  </>;
}
