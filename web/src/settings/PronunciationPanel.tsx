/**
 * Settings ▸ Pronunciation: what is recorded in advance, which order reads each thing, which voice
 * reads each of your languages clearly and which with feeling, and whether clips are kept on this
 * device.
 *
 * Two kinds of setting on one page, and they are kept apart on it. The first three are owner-scoped
 * **server** state, because the recording happens on the server: a phone that has never opened this
 * screen still gets the voices chosen here. Keeping clips is a **device** fact, like wrapping in the
 * editor — a laptop with room and a phone without want different answers — so it is stored on the
 * device and never leaves it.
 *
 * Which models read, and in what order, is Settings ▸ Providers, beside every other order. This page
 * says what those models are to do.
 */

import { useEffect, useRef, useState } from "react";
import { AcervoApiError, backendSession, type PronunciationOrder, type PronunciationPregenerate, type PronunciationSettings, type PronunciationUse } from "../api";
import { setPronunciationCacheEnabled, usePronunciationCache } from "../editorPreferences";
import { languageOf, regionName, regionOf } from "../languages";
import { forgetPronunciations, keptPronunciationBytes } from "../pronunciation";
import { SETTINGS, useServerSetting } from "./cache";
import { Action, Group, Notice, Placeholder, Select, Toggle, useSubPage } from "./kit";
import { ORDER_NAMES, VoicePage, VoiceRow, speaksTheAccent, type VoiceChanges } from "./voices";

export { ORDER_NAMES, offeredVoices } from "./voices";

type Changes = Partial<{
  pregenerate: Partial<PronunciationPregenerate>;
  delivery: Partial<Record<PronunciationUse, PronunciationOrder>>;
}> & VoiceChanges;

/* Two of the four uses. The pair of orders is chosen in Settings ▸ Providers; this is where each
   use picks one. Loops and stories choose on their own pages, beside what they read. */
const DELIVERY: { id: PronunciationUse; title: string }[] = [
  { id: "words", title: "Words and definitions" },
  { id: "examples", title: "Example sentences" }
];

const ADVANCE: { id: keyof PronunciationPregenerate; title: string; hint?: string }[] = [
  { id: "headword", title: "The word itself" },
  { id: "definitions", title: "Definitions", hint: "When they are in the language you learn" },
  { id: "examples", title: "Example sentences" }
];

function megabytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function PronunciationPanel({ onNotify }: { onNotify(message: string): void }) {
  const { value: settings, error, set } = useServerSetting(SETTINGS.pronunciations);
  const intended = useRef<PronunciationSettings | null>(null);
  const pending = useRef(0);
  if (pending.current === 0) intended.current = settings ?? null;
  const newest = useRef(0);
  const keeping = usePronunciationCache();
  const [kept, setKept] = useState<number | null>(null);
  const { sub, open } = useSubPage();

  const commit = (next: PronunciationSettings) => {
    intended.current = next;
    set(next);
  };

  useEffect(() => { void keptPronunciationBytes().then(setKept); }, []);

  /* Move the control at once, then reconcile with what the server stored — `ImagePanel`'s rule. */
  const apply = async (changes: Changes, optimistic: PronunciationSettings) => {
    const before = intended.current;
    if (!before) return;
    const token = ++newest.current;
    pending.current += 1;
    commit(optimistic);
    try {
      const stored = await backendSession.savePronunciationSettings(changes);
      if (newest.current === token) commit(stored);
    } catch (error) {
      if (newest.current === token) commit(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    } finally {
      pending.current -= 1;
    }
  };

  const keep = async (on: boolean) => {
    setPronunciationCacheEnabled(on);
    if (!on) {
      await forgetPronunciations();
      setKept(0);
    }
  };

  /* A device fact, shown whatever the server says: it is the one part of this page that works
     without it. */
  const device = <Group title="On this device">
    <Toggle
      label="Keep pronunciations"
      hint={`Play offline${kept ? ` · ${megabytes(kept)} kept` : ""}`}
      checked={keeping} onChange={(on) => void keep(on)}
    />
    <Action danger disabled={!kept} onClick={() => void forgetPronunciations().then(() => {
      setKept(0);
      onNotify("Pronunciations forgotten on this device");
    })}>Forget pronunciations on this device</Action>
  </Group>;

  if (!settings) return <>{error ? <Notice>{error}</Notice> : <Placeholder rows={3} />}{device}</>;

  /* A language's voice page: `voice:<order>:<language>`. */
  const [, subOrder, subLanguage] = sub?.id.startsWith("voice:") ? sub.id.split(":") : [];
  if (subOrder && subLanguage && settings.languages.includes(subLanguage)) {
    return <VoicePage
      settings={settings} role="native" order={subOrder as PronunciationOrder} language={subLanguage}
      apply={(changes, next) => void apply(changes, next)} onNotify={onNotify}
    />;
  }

  return <>
    <Group title="Record in advance" foot="Recorded when a word is saved, so they play offline straight away.">
      {ADVANCE.map((entry) => <Toggle
        key={entry.id} label={entry.title} hint={entry.hint} checked={settings.pregenerate[entry.id]}
        onChange={(on) => {
          const pregenerate = { ...intended.current!.pregenerate, [entry.id]: on };
          void apply({ pregenerate: { [entry.id]: on } }, { ...intended.current!, pregenerate, chosen: true });
        }}
      />)}
    </Group>

    <Group title="Which voice reads" foot="The expressive voice reads with emotion; the clear one is cheaper and faster.">
      {DELIVERY.map((use) => <Select<PronunciationOrder>
        key={use.id} label={use.title} value={settings.delivery[use.id]}
        options={(["plain", "expressive"] as const).map((order) => ({ value: order, label: ORDER_NAMES[order] }))}
        onChange={(order) => {
          const delivery = { ...intended.current!.delivery, [use.id]: order };
          void apply({ delivery: { [use.id]: order } }, { ...intended.current!, delivery, chosen: true });
        }}
      />)}
    </Group>

    {settings.languages.map((language) => {
      const presentation = languageOf(language);
      const region = regionOf(settings.accents?.[language]);
      const title = `${presentation.flag} ${presentation.name}${region ? ` · ${regionName(region)}` : ""}`;
      const unmet = region && !speaksTheAccent(settings, "native", "plain", language);
      return <Group
        key={language} title={title}
        foot={unmet ? `No clear voice has an accent from ${regionName(region)} yet; the nearest reads.` : undefined}
      >
        {(["plain", "expressive"] as const).map((order) => <VoiceRow
          key={order} settings={settings} role="native" order={order} language={language} onNotify={onNotify}
          onOpen={() => open({ id: `voice:${order}:${language}`, title: `${presentation.name} · ${ORDER_NAMES[order]}` })}
        />)}
      </Group>;
    })}

    {device}
  </>;
}
