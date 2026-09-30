/**
 * Settings ▸ Pronunciation: what is recorded in advance, which order reads each thing, which voice
 * each model uses, and whether clips are kept on this device.
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
import { AcervoApiError, backendSession, type PronunciationModel, type PronunciationOrder, type PronunciationPregenerate, type PronunciationSettings, type PronunciationUse } from "./api";
import { setPronunciationCacheEnabled, usePronunciationCache } from "./editorPreferences";
import { languageOf } from "./languages";
import { forgetPronunciations, keptPronunciationBytes } from "./pronunciation";

type Changes = Partial<{
  pregenerate: Partial<PronunciationPregenerate>;
  delivery: Partial<Record<PronunciationUse, PronunciationOrder>>;
  voices: PronunciationSettings["voices"];
}>;

/* Two of the four uses. The pair of orders is chosen in Settings ▸ Providers and named there for
   what each can do; this is where each use picks one.

   The other two uses are loops and stories, and each is chosen on its own page (Settings ▸ Loops,
   Settings ▸ Stories) rather than here — the same stored value, on the page you are on when you are
   thinking about them, because what it costs and what it does to a track are facts about the thing
   that is read and belong beside it. */
const DELIVERY: { id: PronunciationUse; title: string; help: string }[] = [
  { id: "words", title: "Words and definitions", help: "And anything you select on the page. These should sound the same every time." },
  { id: "examples", title: "Example sentences", help: "A sentence heard the way somebody would say it is easier to remember." }
];

const ORDERS: { id: PronunciationOrder; title: string; help: string }[] = [
  { id: "plain", title: "A clear, even voice", help: "Cheaper and faster. No emotion is sent." },
  { id: "expressive", title: "A voice that takes a direction", help: "Reads with the emotion where the model can take one." }
];

const ADVANCE: { id: keyof PronunciationPregenerate; title: string; help: string }[] = [
  { id: "headword", title: "The word itself", help: "A few kilobytes a word." },
  { id: "definitions", title: "Definitions", help: "Only where a vocabulary defines words in the language you are learning." },
  { id: "examples", title: "Example sentences", help: "In the language you are learning, with their emotion where the voice can take it." }
];

type VoiceDocument = PronunciationSettings["voices"];

/**
 * A voice document held to the models the two orders offer now. A change sends the whole document,
 * and the server refuses one naming a model the catalogue no longer offers for speech — so a choice
 * for a voice nobody can be asked for any more is let go here rather than refusing every later save.
 */
export function offeredVoices(document: VoiceDocument, settings: PronunciationSettings): VoiceDocument {
  const offered = [...settings.orders.plain, ...settings.orders.expressive];
  const kept: VoiceDocument = {};
  for (const [provider, models] of Object.entries(document)) {
    for (const [model, languages] of Object.entries(models)) {
      if (!offered.some((one) => one.provider === provider && one.model === model)) continue;
      kept[provider] = { ...(kept[provider] ?? {}), [model]: languages };
    }
  }
  return kept;
}

function megabytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function PronunciationPanel({ onNotify }: { onNotify(message: string): void }) {
  const [settings, setSettings] = useState<PronunciationSettings | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const intended = useRef<PronunciationSettings | null>(null);
  const newest = useRef(0);
  const keeping = usePronunciationCache();
  const [kept, setKept] = useState<number | null>(null);

  const commit = (next: PronunciationSettings) => {
    intended.current = next;
    setSettings(next);
  };

  useEffect(() => {
    void backendSession.pronunciationSettings()
      .then(commit)
      .catch((error: unknown) => setFailed(error instanceof AcervoApiError
        ? error.message
        : "These settings live on the server, which could not be reached."));
    void keptPronunciationBytes().then(setKept);
  }, []);

  /* Move the control at once, then reconcile with what the server stored — `ImagePanel`'s rule. */
  const apply = async (changes: Changes, optimistic: PronunciationSettings) => {
    const before = intended.current;
    if (!before) return;
    const token = ++newest.current;
    commit(optimistic);
    try {
      const stored = await backendSession.savePronunciationSettings(changes);
      if (newest.current === token) commit(stored);
    } catch (error) {
      if (newest.current === token) commit(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    }
  };

  const keep = async (on: boolean) => {
    setPronunciationCacheEnabled(on);
    if (!on) {
      await forgetPronunciations();
      setKept(0);
    }
  };

  const device = <>
    <h4 className="provider-heading">On this device</h4>
    <label className="config-switch">
      <input type="checkbox" checked={keeping} onChange={(event) => void keep(event.target.checked)} />
      <span>
        <strong>Keep pronunciations on this device</strong>
        <span>
          A clip heard once plays again with no connection, and clips recorded elsewhere are brought
          here after each sync. Off, every press asks the server, and what was kept is forgotten.
        </span>
      </span>
    </label>
    <div className="sync-actions">
      <button
        className="tb-btn" disabled={!kept}
        onClick={() => void forgetPronunciations().then(() => { setKept(0); onNotify("Pronunciations forgotten on this device"); })}
      >Forget pronunciations on this device</button>
      {kept !== null && <span className="config-help">{kept ? `${megabytes(kept)} kept` : "Nothing kept"}</span>}
    </div>
  </>;

  if (failed) return <section className="config-section">
    <h3>Pronunciation</h3>
    <p className="config-help warn">{failed}</p>
    {device}
  </section>;

  if (!settings) return <section className="config-section">
    <h3>Pronunciation</h3>
    <p className="config-help" role="status">Reading your settings…</p>
  </section>;

  const chooseVoice = (model: PronunciationModel, language: string, voice: string) => {
    const voices = offeredVoices(structuredClone(intended.current?.voices ?? {}), intended.current!);
    const forModel = { ...(voices[model.provider]?.[model.model] ?? {}) };
    if (voice) forModel[language] = voice; else delete forModel[language];
    voices[model.provider] = { ...(voices[model.provider] ?? {}), [model.model]: forModel };
    void apply({ voices }, { ...intended.current!, voices, chosen: true });
  };

  /* One model appears in both orders more often than not, and its voice is one choice, not two. */
  const models = [...settings.orders.plain, ...settings.orders.expressive]
    .filter((model, index, all) => all.findIndex((other) => other.provider === model.provider && other.model === model.model) === index)
    .filter((model) => Object.keys(model.voices).some((language) => settings.languages.includes(language)));

  return <section className="config-section">
    <h3>Pronunciation</h3>
    <p className="config-help">
      Every play button reads its text in that text’s own language. The first press records the clip
      on the server and every press after plays the same one; after you hear a bad one, Record again
      in the message that appears replaces it.
    </p>

    <h4 className="provider-heading">Record in advance</h4>
    <p className="config-help">
      When a word is saved, record these straight away rather than on the first press — so they play
      offline on a device that has never heard them.
    </p>
    {ADVANCE.map((entry) => <label key={entry.id} className="config-switch">
      <input
        type="checkbox" checked={settings.pregenerate[entry.id]}
        onChange={(event) => {
          const pregenerate = { ...intended.current!.pregenerate, [entry.id]: event.target.checked };
          void apply({ pregenerate: { [entry.id]: event.target.checked } }, { ...intended.current!, pregenerate, chosen: true });
        }}
      />
      <span><strong>{entry.title}</strong><span>{entry.help}</span></span>
    </label>)}

    <h4 className="provider-heading">Delivery</h4>
    <p className="config-help">
      Which of the two pronunciation orders reads each thing. Choosing the directed voice <em>is</em>
      {" "}asking for emotion — there is no separate switch — so the clear voice is how you read
      something plainly and cheaply. A clip already recorded keeps the delivery it has until you
      record it again. Loops and stories choose in Settings ▸ Loops and Settings ▸ Stories.
    </p>
    {DELIVERY.map((use) => <label key={use.id} className="config-field">
      <span>
        <strong>{use.title}</strong>
        <span className="config-help">{use.help}</span>
      </span>
      <select
        value={settings.delivery[use.id]}
        onChange={(event) => {
          const order = event.target.value as PronunciationOrder;
          const delivery = { ...intended.current!.delivery, [use.id]: order };
          void apply({ delivery: { [use.id]: order } }, { ...intended.current!, delivery, chosen: true });
        }}
      >
        {ORDERS.map((order) => <option key={order.id} value={order.id}>{order.title}</option>)}
      </select>
    </label>)}

    <h4 className="provider-heading">Voices</h4>
    <p className="config-help">
      One voice per model and language, held steady so you learn it. A change applies to the next
      recording, not to clips you already have.
    </p>
    {models.length === 0 && <p className="config-help">No model in your pronunciation orders speaks your vocabularies’ languages.</p>}
    {models.map((model) => <div key={`${model.provider}/${model.model}`} className="voice-model">
      <strong>{model.providerLabel} · {model.model}{!model.available && <span className="label"> not configured</span>}</strong>
      {Object.entries(model.voices).filter(([language]) => settings.languages.includes(language)).map(([language, voices]) => <label key={language} className="config-field">
        <span>{languageOf(language).name}</span>
        <select
          value={settings.voices[model.provider]?.[model.model]?.[language] ?? ""}
          onChange={(event) => chooseVoice(model, language, event.target.value)}
        >
          <option value="">Default · {voices[0]}</option>
          {voices.map((voice) => <option key={voice} value={voice}>{voice}</option>)}
        </select>
      </label>)}
    </div>)}

    {device}
  </section>;
}
