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
import {
  AcervoApiError, backendSession, type LoopSchema, type PronunciationOrder, type PronunciationSettings
} from "./api";
import { setLoopCacheEnabled, useLoopCache } from "./editorPreferences";
import { languageOf } from "./languages";
import { forgetLoops, keptLoopBytes } from "./loops";

/* The same two orders Settings ▸ Pronunciation offers, said in terms of what each does to a loop.
   Both facts are measured rather than felt: a directed take is its own model call per repetition,
   and a plain one is recorded once a line and varied by the generator afterwards. */
const ORDERS: { id: PronunciationOrder; title: string; help: string }[] = [
  {
    id: "expressive", title: "A voice that takes a direction",
    help: "Every repetition is read again, with its own direction — so a word you wrote an emotion for "
      + "sounds it, and the rest are still said three different ways. Three calls a line."
  },
  {
    id: "plain", title: "A clear, even voice",
    help: "Recorded once a line, and the repetitions are varied by the generator in pitch and speed. "
      + "A third of the calls, and no emotion."
  }
];

function megabytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function LoopPanel({ onNotify }: { onNotify(message: string): void }) {
  const [schema, setSchema] = useState<LoopSchema | null>(null);
  const [trouble, setTrouble] = useState<string | null>(null);
  const [voice, setVoice] = useState<PronunciationSettings | null>(null);
  const keeping = useLoopCache();
  const [kept, setKept] = useState<number | null>(null);

  useEffect(() => {
    void backendSession.loopSchema()
      .then(setSchema)
      .catch((error: unknown) => setTrouble(error instanceof AcervoApiError
        ? error.message
        : "The loop generator could not be reached."));
    void backendSession.pronunciationSettings().then(setVoice).catch(() => undefined);
    void keptLoopBytes().then(setKept);
  }, []);

  /* Optimistic, then reconciled, then rolled back if the server refused — the shape
     `PronunciationPanel` uses, because it is the same record being written. */
  const chooseOrder = async (order: PronunciationOrder) => {
    const before = voice;
    if (!before) return;
    setVoice({ ...before, delivery: { ...before.delivery, loops: order }, chosen: true });
    try {
      setVoice(await backendSession.savePronunciationSettings({ delivery: { loops: order } }));
    } catch (error) {
      setVoice(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That could not be saved.");
    }
  };

  /* The guide's voice for one model and language: the same record as the voices, the same shape. */
  const chooseGuide = async (provider: string, model: string, language: string, choice: string) => {
    const before = voice;
    if (!before) return;
    const guideVoices = structuredClone(before.guideVoices);
    const forModel = { ...(guideVoices[provider]?.[model] ?? {}) };
    if (choice) forModel[language] = choice; else delete forModel[language];
    guideVoices[provider] = { ...(guideVoices[provider] ?? {}), [model]: forModel };
    setVoice({ ...before, guideVoices, chosen: true });
    try {
      setVoice(await backendSession.savePronunciationSettings({ guideVoices }));
    } catch (error) {
      setVoice(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That could not be saved.");
    }
  };

  /* The models that read loops, in the order chosen above, that have voices in a language the guide
     speaks. The one chosen for that language on Settings ▸ Pronunciation is what "the same voice"
     is. */
  const guideModels = voice
    ? voice.orders[voice.delivery.loops].filter((model) =>
      voice.guideLanguages.some((language) => (model.voices[language] ?? []).length > 0))
    : [];

  const keep = async (on: boolean) => {
    setLoopCacheEnabled(on);
    if (!on) { await forgetLoops(); setKept(0); }
  };

  return <section className="config-section">
    <h3>Loops</h3>
    <p className="config-help">
      A loop takes a handful of your words and sets them to music, so they are learned while you are
      doing something else. Each is made in a format you choose when you make it — a drill, a radio
      lesson, a story.
    </p>

    <h4 className="provider-heading">The voice</h4>
    <p className="config-help">
      Which of the two pronunciation orders speaks a loop. It is the same choice Settings ▸
      Pronunciation makes for words and for example sentences, and a loop already made keeps the
      voice it was made with.
    </p>
    {voice && ORDERS.map((order) => <label key={order.id} className="config-switch">
      <input
        type="radio" name="loop-delivery" checked={voice.delivery.loops === order.id}
        onChange={() => void chooseOrder(order.id)}
      />
      <span><strong>{order.title}</strong><span>{order.help}</span></span>
    </label>)}

    <h4 className="provider-heading">The guide’s voice</h4>
    <p className="config-help">
      Who says the translations, remarks and announcements — the lines in your own language. Unset,
      the same voice says every line.
    </p>
    {voice && guideModels.length === 0 && <p className="config-help">
      No model that reads loops has voices in the language your translations are in.
    </p>}
    {voice && guideModels.map((model) => <div key={`${model.provider}/${model.model}`} className="voice-model">
      <strong>{model.providerLabel} · {model.model}{!model.available && <span className="label"> not configured</span>}</strong>
      {voice.guideLanguages.filter((language) => (model.voices[language] ?? []).length > 0).map((language) =>
        <label key={language} className="config-field">
          <span>{languageOf(language).name}</span>
          <select
            value={voice.guideVoices[model.provider]?.[model.model]?.[language] ?? ""}
            onChange={(event) => void chooseGuide(model.provider, model.model, language, event.target.value)}
          >
            <option value="">The same voice</option>
            {model.voices[language].map((one) => <option key={one} value={one}>{one}</option>)}
          </select>
        </label>)}
    </div>)}

    <h4 className="provider-heading">The generator</h4>
    {trouble && <p className="config-help warn">{trouble}</p>}
    {!trouble && !schema && <p className="config-help" role="status">Asking what it can do…</p>}
    {schema && <>
      <p className="config-help">
        Engine {schema.engineVersion} · up to {schema.maxItems} words a loop ·{" "}
        {schema.families.length} {schema.families.length === 1 ? "kind" : "kinds"} of music.
      </p>
      {/* Not "plainer": without the pack, fifteen of the generator's sixteen bed families name
          instruments loaded from its catalogue, so a render dies partway through rather than
          sounding thinner. It installs on the server, so this names the command. */}
      <p className={`config-help${schema.productionBundle ? "" : " warn"}`}>
        {schema.productionBundle
          ? "The sample pack is installed, so beds are built from recorded instruments."
          : <>Loops cannot be made: the sample pack is not installed on this server. Install it once
            with <code>./deploy.sh --install-samples</code>.</>}
      </p>
    </>}

    <h4 className="provider-heading">On this device</h4>
    <label className="config-switch">
      <input type="checkbox" checked={keeping} onChange={(event) => void keep(event.target.checked)} />
      <span>
        <strong>Keep loops on this device</strong>
        <span>
          A loop heard once plays again with no connection. Off, a loop is fetched when you press
          play and held only until you close Acervo — a track is megabytes where a pronunciation is
          kilobytes, which is the whole reason this is a choice.
        </span>
      </span>
    </label>
    <div className="sync-actions">
      <button
        className="tb-btn" disabled={!kept}
        onClick={() => void forgetLoops().then(() => { setKept(0); onNotify("Loops forgotten on this device"); })}
      >Forget loops on this device</button>
      {kept !== null && <span className="config-help">{kept ? `${megabytes(kept)} kept` : "Nothing kept"}</span>}
    </div>
  </section>;
}
