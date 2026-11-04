/**
 * Settings ▸ Loops: which voice speaks one, who says its guide lines, whether tracks are kept on this
 * device, and what the generator can do.
 *
 * Three kinds of thing, kept apart on the page as `PronunciationPanel` keeps its two apart. The
 * voices are **owner** state, stored beside the other two pronunciation uses and read by the server
 * when it renders — a phone that has never opened this screen gets the voices chosen here. Keeping a
 * track is a **device** fact — a laptop with room and a phone without want different answers, and it
 * never leaves the device. What the generator is and whether it has its sample pack is the
 * **deployment's**, read from the server and not settable here.
 *
 * Keeping is **off** by default, where keeping clips is on, and the difference is measured rather
 * than felt: a vocabulary's clips cost about what its text does, and one loop costs more than both.
 * With it off a loop still plays — the track is held for the session — it is simply not kept.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type PronunciationOrder, type PronunciationSettings } from "../api";
import { setLoopCacheEnabled, useLoopCache } from "../editorPreferences";
import { languageOf } from "../languages";
import { forgetLoops, keptLoopBytes } from "../loops";
import { SETTINGS, useServerSetting } from "./cache";
import { Action, Group, Notice, Placeholder, Row, Segmented, Toggle, Value, useSubPage } from "./kit";
import { VoicePage, VoiceRow } from "./voices";

/* The same two orders Settings ▸ Pronunciation offers, said in terms of what each does to a loop.
   Both facts are measured rather than felt: a directed take is its own model call per repetition,
   and a plain one is recorded once a line and varied by the generator afterwards. */
const ORDERS: { value: PronunciationOrder; label: string; hint: string }[] = [
  { value: "expressive", label: "Read again each time", hint: "Expressive voice: the emotion you wrote, three calls a line" },
  { value: "plain", label: "Recorded once, varied", hint: "Clear voice: varied in pitch and speed, a third of the calls" }
];

function megabytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function LoopPanel({ onNotify }: { onNotify(message: string): void }) {
  const schema = useServerSetting(SETTINGS.loopSchema);
  const { value: voice, set: setVoice } = useServerSetting(SETTINGS.pronunciations);
  const keeping = useLoopCache();
  const [kept, setKept] = useState<number | null>(null);
  const { sub, open } = useSubPage();

  useEffect(() => { void keptLoopBytes().then(setKept); }, []);

  /* Optimistic, then reconciled, then rolled back if the server refused — the shape
     `PronunciationPanel` uses, because it is the same record being written. */
  const save = async (changes: Parameters<typeof backendSession.savePronunciationSettings>[0], optimistic: PronunciationSettings) => {
    const before = voice;
    if (!before) return;
    setVoice(optimistic);
    try {
      setVoice(await backendSession.savePronunciationSettings(changes));
    } catch (error) {
      setVoice(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That could not be saved.");
    }
  };

  const chooseOrder = (order: PronunciationOrder) => voice && void save(
    { delivery: { loops: order } },
    { ...voice, delivery: { ...voice.delivery, loops: order }, chosen: true }
  );

  /* The guide's voice for a language: who says the lines in it, chosen like any other voice, in
     the order that reads loops. Unchosen, the voice that reads the words says them too. */
  const guideLanguages = voice
    ? voice.guideLanguages.filter((language) => (voice.guideReaders?.[voice.delivery.loops]?.[language] ?? []).length > 0)
    : [];

  const keep = async (on: boolean) => {
    setLoopCacheEnabled(on);
    if (!on) { await forgetLoops(); setKept(0); }
  };

  const [, guideLanguage] = sub?.id.startsWith("guide:") ? sub.id.split(":") : [];
  if (voice && guideLanguage && guideLanguages.includes(guideLanguage)) {
    return <VoicePage
      settings={voice} role="guide" order={voice.delivery.loops} language={guideLanguage}
      apply={(changes, next) => void save(changes, next)} onNotify={onNotify}
    />;
  }

  return <>
    {voice ? <>
      <Group title="Voice">
        <Segmented label="Repetitions are" value={voice.delivery.loops} options={ORDERS} onChange={chooseOrder} />
      </Group>
      {guideLanguages.length > 0 && <Group title="Guide’s voice" foot="Who says the lines in your own language. Unchosen, the same voice says every line.">
        {guideLanguages.map((language) => <VoiceRow
          key={language} settings={voice} role="guide" order={voice.delivery.loops} language={language}
          label={languageOf(language).name} onNotify={onNotify}
          onOpen={() => open({ id: `guide:${language}`, title: `${languageOf(language).name} · Guide’s voice` })}
        />)}
      </Group>}
    </> : <Placeholder rows={2} />}

    {schema.value && !schema.value.productionBundle && <Notice>
      Loops cannot be made: the sample pack is not installed on this server.
      Install it with <code>./deploy.sh --install-samples</code>.
    </Notice>}
    {!schema.value && schema.error && <Notice>{schema.error}</Notice>}
    {schema.value && <Group title="Generator">
      <Row label={`Engine ${schema.value.engineVersion}`} hint={`Up to ${schema.value.maxItems} words a loop`}>
        <Value>{schema.value.families.length} kinds of music</Value>
      </Row>
    </Group>}

    <Group title="On this device">
      <Toggle
        label="Keep loops" hint={`Play offline${kept ? ` · ${megabytes(kept)} kept` : " · a loop is megabytes"}`}
        checked={keeping} onChange={(on) => void keep(on)}
      />
      <Action danger disabled={!kept} onClick={() => void forgetLoops().then(() => {
        setKept(0);
        onNotify("Loops forgotten on this device");
      })}>Forget loops on this device</Action>
    </Group>
  </>;
}
