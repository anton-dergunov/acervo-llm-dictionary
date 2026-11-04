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
import { Action, Group, Notice, Placeholder, Row, Segmented, Select, Toggle, Value } from "./kit";
import { offeredVoices } from "./PronunciationPanel";

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

  /* The guide's voice for one model and language: the same record as the voices, the same shape. */
  const chooseGuide = (provider: string, model: string, language: string, choice: string) => {
    if (!voice) return;
    const guideVoices = offeredVoices(structuredClone(voice.guideVoices), voice);
    const forModel = { ...(guideVoices[provider]?.[model] ?? {}) };
    if (choice) forModel[language] = choice; else delete forModel[language];
    guideVoices[provider] = { ...(guideVoices[provider] ?? {}), [model]: forModel };
    void save({ guideVoices }, { ...voice, guideVoices, chosen: true });
  };

  /* The models that read loops, in the order chosen above, that have voices in a language the guide
     speaks. */
  const guideModels = voice
    ? voice.orders[voice.delivery.loops].filter((model) =>
      voice.guideLanguages.some((language) => (model.voices[language] ?? []).length > 0))
    : [];

  const keep = async (on: boolean) => {
    setLoopCacheEnabled(on);
    if (!on) { await forgetLoops(); setKept(0); }
  };

  return <>
    {voice ? <>
      <Group title="Voice">
        <Segmented label="Repetitions are" value={voice.delivery.loops} options={ORDERS} onChange={chooseOrder} />
      </Group>
      {guideModels.length > 0 && <Group title="Guide’s voice" foot="Who says the lines in your own language. Unset, one voice says every line.">
        {guideModels.flatMap((model) => voice.guideLanguages
          .filter((language) => (model.voices[language] ?? []).length > 0)
          .map((language) => <Select
            key={`${model.provider}/${model.model}/${language}`}
            label={languageOf(language).name}
            hint={`${model.providerLabel} · ${model.model}${model.available ? "" : " · not configured"}`}
            value={voice.guideVoices[model.provider]?.[model.model]?.[language] ?? ""}
            options={[{ value: "", label: "The same voice" }, ...model.voices[language].map((one) => ({ value: one, label: one }))]}
            onChange={(choice) => chooseGuide(model.provider, model.model, language, choice)}
          />))}
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
