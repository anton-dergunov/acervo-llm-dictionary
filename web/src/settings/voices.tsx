/**
 * Choosing a voice: who reads a language clearly, who reads it with feeling, in which accent, and
 * what each sounds like. Settings ▸ Pronunciation draws a language's two voices with it, and
 * Settings ▸ Loops its guide's.
 *
 * Nothing here knows a provider. A voice is what a catalogue row declares — a name, perhaps a gender
 * and a word for its character, and the locale it was made for, or none when it speaks any accent it
 * is told — and who actually reads a language, first and then as backups, is the server's readout
 * (`readers`), computed by the rule the recording follows. This page draws that and sends choices
 * back; it never restates the rule.
 */

import type { ReactNode } from "react";
import {
  backendSession, type FirstVoices, type PronunciationOrder, type PronunciationSettings,
  type VoiceChoices, type VoiceMatch, type VoiceOption, type VoiceReader
} from "../api";
import { regionName, regionOf } from "../languages";
import { playPreview, useSpeechState } from "../pronunciation";
import { Action, Choice, Group, Link, Listen, Row, Select } from "./kit";

/** Whose voice: the vocabulary's own, or a loop's guide saying the lines in your language. */
export type Role = "native" | "guide";

export type VoiceChanges = Partial<{
  voices: VoiceChoices; guideVoices: VoiceChoices; first: FirstVoices; guideFirst: FirstVoices;
}>;

export const ORDER_NAMES: Record<PronunciationOrder, string> = {
  plain: "Clear voice",
  expressive: "Expressive voice"
};

const RANK: Record<VoiceMatch, number> = { exact: 0, any: 1, near: 2, main: 3, other: 4, unstated: 5 };

/**
 * A voice's own name, without a locale it repeats: `es-ES-Wavenet-F` is "Wavenet-F" once its accent
 * is shown beside it. Any leading `xx-YY-`, whoever names voices that way.
 */
export function shortName(name: string): string {
  return name.replace(/^[a-z]{2,3}-(?:[A-Z][a-z]{3}-)?(?:[A-Z]{2}|\d{3})-/, "") || name;
}

/** "Kore · female · firm". */
export function voiceLabel(option: VoiceOption): string {
  return [shortName(option.name), option.gender, option.note].filter(Boolean).join(" · ");
}

/**
 * The accent a voice is heard in, in words: its own locale's country, or — for one that speaks any —
 * the country it will be told, `locale` being what this language is heard in.
 */
export function accentOf(option: VoiceOption | null, locale: string): string {
  if (option?.locale) {
    const region = regionOf(option.locale);
    return region ? regionName(region) : "Accent not stated";
  }
  if (option?.match === "any") {
    const region = regionOf(locale);
    return region ? regionName(region) : "Any accent";
  }
  return "Accent not stated";
}

function readersOf(settings: PronunciationSettings, role: Role, order: PronunciationOrder, language: string): VoiceReader[] {
  return (role === "guide" ? settings.guideReaders : settings.readers)?.[order]?.[language] ?? [];
}

/** A voice document held to the models the two orders offer now (`offeredVoices`'s rule). */
export function offeredVoices(document: VoiceChoices, settings: PronunciationSettings): VoiceChoices {
  const offered = [...settings.orders.plain, ...settings.orders.expressive];
  const kept: VoiceChoices = {};
  for (const [provider, models] of Object.entries(document)) {
    for (const [model, languages] of Object.entries(models)) {
      if (!offered.some((one) => one.provider === provider && one.model === model)) continue;
      kept[provider] = { ...(kept[provider] ?? {}), [model]: languages };
    }
  }
  return kept;
}

/** The same for which pair reads first: a pair its order no longer holds is let go, or the server
    would refuse every later change for it. */
export function offeredFirst(document: FirstVoices, settings: PronunciationSettings): FirstVoices {
  const kept: FirstVoices = {};
  for (const order of ["plain", "expressive"] as const) {
    for (const [language, pair] of Object.entries(document[order] ?? {})) {
      if (!settings.orders[order].some((one) => one.provider === pair[0] && one.model === pair[1])) continue;
      kept[order] = { ...(kept[order] ?? {}), [language]: pair };
    }
  }
  return kept;
}

function documents(settings: PronunciationSettings, role: Role) {
  return {
    voices: offeredVoices(structuredClone(role === "guide" ? settings.guideVoices : settings.voices), settings),
    first: offeredFirst(structuredClone((role === "guide" ? settings.guideFirst : settings.first) ?? {}), settings)
  };
}

function withVoice(voices: VoiceChoices, provider: string, model: string, language: string, name: string): VoiceChoices {
  const forModel = { ...(voices[provider]?.[model] ?? {}) };
  if (name) forModel[language] = name; else delete forModel[language];
  return { ...voices, [provider]: { ...(voices[provider] ?? {}), [model]: forModel } };
}

function changesFor(role: Role, voices: VoiceChoices, first: FirstVoices): VoiceChanges {
  return role === "guide" ? { guideVoices: voices, guideFirst: first } : { voices, first };
}

function optimistic(settings: PronunciationSettings, changes: VoiceChanges): PronunciationSettings {
  return { ...settings, ...changes, chosen: true } as PronunciationSettings;
}

/** Hear a voice read your newest example. The same player as every other sound in the app. */
function usePreview(settings: PronunciationSettings, onNotify: (message: string) => void) {
  const speech = useSpeechState();
  const keyOf = (order: PronunciationOrder, language: string, provider: string, model: string, voice: string | null) =>
    `preview:${order}:${settings.accents?.[language] ?? language}:${provider}:${model}:${voice ?? ""}`;
  return (order: PronunciationOrder, language: string, provider: string, model: string, voice: string | null, name: string): ReactNode => {
    const key = keyOf(order, language, provider, model, voice);
    return <Listen
      name={name} playing={speech.playing === key} busy={speech.busy === key}
      onPlay={() => void playPreview(key, () => backendSession.previewVoice({ order, language, provider, model, voice }))
        .catch((error: unknown) => onNotify(error instanceof Error ? error.message : "That voice could not be heard."))}
    />;
  };
}

/** One row on a page: who reads `language` first in `order`, with a ▶, leading to the choice. */
export function VoiceRow({ settings, role, order, language, label = ORDER_NAMES[order], onOpen, onNotify }: {
  settings: PronunciationSettings;
  role: Role;
  order: PronunciationOrder;
  language: string;
  /** What the row is called; the order's name unless the group already says it. */
  label?: string;
  onOpen(): void;
  onNotify(message: string): void;
}) {
  const listen = usePreview(settings, onNotify);
  const readers = readersOf(settings, role, order, language);
  const locale = settings.accents?.[language] ?? language;
  const first = readers[0];
  if (!first) {
    return <Row label={label} hint={order === "expressive"
      ? "Nothing in Providers ▸ Expressive voice can read it with feeling"
      : "Nothing in Providers ▸ Clear voice speaks it"} />;
  }
  const backups = readers.length - 1;
  return <Link
    label={label}
    hint={`${first.model}${backups ? ` · ${backups} ${backups === 1 ? "backup" : "backups"}` : ""}`}
    value={`${first.voice ? shortName(first.voice.name) : "Its own voice"} · ${accentOf(first.voice, locale)}`}
    before={listen(order, language, first.provider, first.model, first.voice?.name ?? null, first.voice?.name ?? first.model)}
    onOpen={onOpen}
  />;
}

/** Whether the voice that reads first has the accent asked for — made for it, or told it. */
export function speaksTheAccent(settings: PronunciationSettings, role: Role, order: PronunciationOrder, language: string): boolean {
  const match = readersOf(settings, role, order, language)[0]?.voice?.match;
  return !regionOf(settings.accents?.[language]) || match === "exact" || match === "any";
}

interface Offered { provider: string; providerLabel: string; model: string; available: boolean; option: VoiceOption }

/** The page for one language in one order: every voice the order can offer, by accent, and its backups. */
export function VoicePage({ settings, role, order, language, apply, onNotify }: {
  settings: PronunciationSettings;
  role: Role;
  order: PronunciationOrder;
  language: string;
  apply(changes: VoiceChanges, optimistic: PronunciationSettings): void;
  onNotify(message: string): void;
}) {
  const listen = usePreview(settings, onNotify);
  const readers = readersOf(settings, role, order, language);
  const locale = settings.accents?.[language] ?? language;
  const region = regionOf(locale);
  const first = readers[0];

  /* Every voice of every model in the order, once: two models of one provider that share a voice
     list (one Gemini and the next) show it once, under the first, because choosing it there makes the
     next say it too. */
  const offered: Offered[] = [];
  for (const model of settings.orders[order]) {
    for (const option of model.voices[language] ?? []) {
      if (offered.some((one) => one.provider === model.provider && one.option.name === option.name)) continue;
      offered.push({ provider: model.provider, providerLabel: model.providerLabel, model: model.model, available: model.available, option });
    }
  }
  const groups = new Map<string, { title: string; rank: number; voices: Offered[] }>();
  for (const one of offered) {
    const key = one.option.locale ?? (one.option.match === "any" ? "*" : "?");
    const title = key === "*" ? "Speaks any accent" : accentOf(one.option, locale);
    const group = groups.get(key) ?? { title, rank: RANK[one.option.match], voices: [] };
    group.rank = Math.min(group.rank, RANK[one.option.match]);
    group.voices.push(one);
    groups.set(key, group);
  }
  const ordered = [...groups.entries()].sort(([, a], [, b]) => a.rank - b.rank || a.title.localeCompare(b.title));

  const choose = (one: Offered) => {
    const { voices, first: firsts } = documents(settings, role);
    const changes = changesFor(role, withVoice(voices, one.provider, one.model, language, one.option.name),
      { ...firsts, [order]: { ...(firsts[order] ?? {}), [language]: [one.provider, one.model] } });
    apply(changes, optimistic(settings, changes));
  };
  const chooseBackup = (reader: VoiceReader, name: string) => {
    const { voices, first: firsts } = documents(settings, role);
    const changes = changesFor(role, withVoice(voices, reader.provider, reader.model, language, name), firsts);
    apply(changes, optimistic(settings, changes));
  };
  const chooseDefault = () => {
    const { voices, first: firsts } = documents(settings, role);
    const kept = { ...(firsts[order] ?? {}) };
    delete kept[language];
    const changes = changesFor(role,
      first ? withVoice(voices, first.provider, first.model, language, "") : voices,
      { ...firsts, [order]: kept });
    apply(changes, optimistic(settings, changes));
  };
  const chosen = Boolean((role === "guide" ? settings.guideFirst : settings.first)?.[order]?.[language]
    || (first && (role === "guide" ? settings.guideVoices : settings.voices)[first.provider]?.[first.model]?.[language]));
  const accentMet = speaksTheAccent(settings, role, order, language);

  return <>
    {ordered.map(([key, group], index) => <Group
      key={key}
      title={group.title}
      foot={index === 0 && region
        ? (accentMet ? (key === "*" ? `Told to speak as in ${regionName(region)}.` : undefined)
          : `None of these voices has an accent from ${regionName(region)}; the nearest reads. The accent is set in Vocabularies.`)
        : undefined}
    >
      {group.voices.map((one) => <Choice
        key={`${one.provider}/${one.model}/${one.option.name}`}
        label={voiceLabel(one.option)}
        hint={`${one.providerLabel} · ${one.model}${one.available ? "" : " · not configured"}`}
        checked={first?.provider === one.provider && first.voice?.name === one.option.name}
        before={listen(order, language, one.provider, one.model, one.option.name, one.option.name)}
        onSelect={() => choose(one)}
      />)}
    </Group>)}

    {readers.length > 1 && <Group title="If it can’t answer" foot="Each is asked in turn, in the order Providers gives.">
      {readers.slice(1).map((reader) => {
        const voices = settings.orders[order].find((model) => model.provider === reader.provider && model.model === reader.model)?.voices[language] ?? [];
        const own = (role === "guide" ? settings.guideVoices : settings.voices)[reader.provider]?.[reader.model]?.[language] ?? "";
        return <Select
          key={`${reader.provider}/${reader.model}`}
          label={`${reader.providerLabel} · ${reader.model}`}
          hint={accentOf(reader.voice, locale)}
          value={own}
          options={[
            { value: "", label: `Automatic · ${reader.voice ? shortName(reader.voice.name) : "its own voice"}` },
            ...voices.map((option) => ({ value: option.name, label: voiceLabel(option) }))
          ]}
          onChange={(name) => chooseBackup(reader, name)}
        >{listen(order, language, reader.provider, reader.model, reader.voice?.name ?? null, reader.voice?.name ?? reader.model)}</Select>;
      })}
    </Group>}

    {chosen && <Group><Action onClick={chooseDefault}>Use the default voice</Action></Group>}
  </>;
}
