import {
  AcervoApiError,
  backendSession,
  type ModelCatalogue,
  type ModelChain,
  type ModelPair,
  type ModelProvider,
  type ProviderChange
} from "../api";
import { refresh, SETTINGS, useServerSetting } from "./cache";
import { Action, Group, Link, Notice, Placeholder, Reorder, Row, StateMark, useSubPage } from "./kit";
import { ADD_PROVIDER, KIND_TITLES, ProviderSubPage, providerPage, stateOf, type Write } from "./ProviderPages";
import { useState } from "react";

/**
 * Settings ▸ Providers: the providers this server holds, and which of their models build an entry,
 * in what order. Adding a provider, its own page and its model pickers are `ProviderPages.tsx`.
 *
 * The unit is a **(provider, model) pair**, not a provider. A free tier is metered per model, so
 * Gemini's two 500-a-day models are a thousand a day and the second is reached by the first one's
 * 429 — choosing between them is a real choice, not a detail.
 *
 * This is server state, not a device preference like the dictionary switches next door: it decides
 * what the vocabulary is made of, so an entry captured on a phone should be built by the same model
 * as one captured on a laptop. Saving is an ordinary online-only write that fails loudly.
 *
 * A pair whose provider cannot be asked — no key, or a key the provider refused — stays in the list,
 * keeps its place and is simply skipped when the chain is walked. That is deliberate: a chain is a
 * preference and a working key is a fact about the provider, and a refused key must not destroy an
 * order or lock the owner out of changing it.
 */

/* `offers` is the kind of model a chain draws from. The two pronunciation orders both draw
   from `audio`: any voice can read either, and which one should is the owner's answer, not a fact
   about the voice. The kinds are named for what they do, so the names here are the ones the
   Pronunciation, Loops and Stories pages use for the two voices. */
const KINDS: { id: string; offers: string; label: string; hint: string }[] = [
  { id: "text", offers: "text", label: "Text", hint: "Writes entries and picture briefs." },
  /* The same models as Text in a second order, because the two questions want different answers:
     an entry wants the best writer, and a tap on a photo wants an answer before the finger lifts. */
  { id: "quick", offers: "text", label: "Quick look-up", hint: "Answers a word tapped on a photo. Put the fastest first." },
  { id: "image", offers: "image", label: "Pictures", hint: "Draws the sense pictures." },
  { id: "audioPlain", offers: "audio", label: "Clear voice", hint: "For what should sound the same every time." },
  { id: "audioExpressive", offers: "audio", label: "Expressive voice", hint: "Reads with emotion. Only voices that take a direction are listed." },
  { id: "ocr", offers: "ocr", label: "Reading photos", hint: "Reads the words on a photo, and where each one is." }
];

const same = (one: ModelPair, other: ModelPair) =>
  one.provider === other.provider && one.model === other.model;

/** The order that exists to carry a direction, and so offers only voices that take one. */
const DIRECTED = "audioExpressive";

/** Every pair a kind can offer, in the order the providers and their models were added. */
function offeredPairs(providers: ModelProvider[], kind: string, offers: string): ModelPair[] {
  return providers.flatMap((provider) => (provider.models[offers] ?? [])
    .filter((model) => kind !== DIRECTED || model.direction === true)
    .map((model) => ({ provider: provider.id, model: model.id })));
}

/** The offered pairs with the chosen ones lifted to the front. */
function orderedPairs(offered: ModelPair[], chosen: ModelPair[]): ModelPair[] {
  const picked = chosen.filter((pair) => offered.some((one) => same(one, pair)));
  return [...picked, ...offered.filter((one) => !picked.some((pair) => same(pair, one)))];
}

function ModelRow({ pair, provider, on, first, last, onToggle, onMove }: {
  pair: ModelPair;
  provider: ModelProvider | undefined;
  on: boolean;
  first: boolean;
  last: boolean;
  onToggle(next: boolean): void;
  onMove(direction: -1 | 1): void;
}) {
  const label = provider?.label ?? pair.provider;
  const missing = provider?.available === false;
  /* Which account is being spent. Only Google needs saying: its credentials are a file that may
     belong to any of several logins, where a key belongs to whoever holds it. */
  /* Unavailable keeps its place in the order and is passed over; the badge says so, the hint why. */
  const hint = missing ? provider?.reason ?? undefined
    : provider?.credential.account ? `Billed to ${provider.credential.account}` : undefined;
  return <div className={`pref-row model-row${missing ? " unavailable" : ""}`}>
    <input
      type="checkbox" role="switch" className="toggle" checked={on}
      aria-label={`Use ${label} ${pair.model}`} onChange={(event) => onToggle(event.target.checked)}
    />
    <span className="pref-text">
      <span className="pref-label">{label} · <span className="model-id">{pair.model}</span></span>
      {hint && <span className="pref-hint">{hint}</span>}
    </span>
    {/* Dimmed text alone was too quiet to notice while scrolling a long list. */}
    {missing && <span className="badge" title="Not available on this server">Unavailable</span>}
    <Reorder name={`${label} ${pair.model}`} first={!on || first} last={!on || last} onMove={onMove} />
  </div>;
}

function KindSection({ kind, offers, label, hint, catalogue, onChange }: {
  kind: string;
  offers: string;
  label: string;
  hint: string;
  catalogue: ModelCatalogue;
  onChange(kind: string, pairs: ModelPair[] | null): void;
}) {
  const chain: ModelChain | undefined = catalogue.chains[kind];
  if (!chain) return null;
  const providers = new Map(catalogue.providers.map((provider) => [provider.id, provider]));
  /* What is switched on is what will actually be asked — under an owner's chain *and* under the
     providers' own order, which the server resolves and sends here as `pairs`.

     Showing every box unchecked under the default order was a lie with consequences: unticking
     the last model looked like turning capture off, and the server carried on building entries with
     the model at the head of its own order. The pane must show what will happen, so an inherited
     order arrives ticked and says whose it is. Changing anything makes the order yours. */
  const offered = offeredPairs(catalogue.providers, kind, offers);
  /* A saved order is kept as it was saved, and it can name a pair this kind no longer offers: a
     voice that cannot take a direction, in the order that exists to carry one. Such a pair is not drawn — and it is left out of the next change
     you make, because the server refuses an order naming it, and one carried along unseen made
     every change to that order fail. */
  const live = chain.pairs.filter((pair) => offered.some((one) => same(one, pair)));
  const inherited = chain.source === "default";
  const pairs = orderedPairs(offered, live);

  /* Three states, and unticking the last box reaches the third rather than bouncing off it:
     an order of your own, nothing at all, or "whatever the server does". Switching everything off
     is a real answer — most of Acervo works without a model — so it is stored rather than refused.
     `null` is the way back, and it has its own button, because no arrangement of switches could
     mean "stop deciding". */
  const change = (next: ModelPair[]) => onChange(kind, next);

  const state = inherited
    ? (live.length ? "This server’s own order is in force until you change it." : "This server has nothing it can use.")
      + (chain.reason ? ` It cannot answer now: ${chain.reason}.` : "")
    : live.length === 0
      ? (chain.pairs.length ? "Nothing chosen takes a direction, so the clear voice reads instead."
        : "Switched off: nothing here is generated.")
      : chain.reason ? `Nothing chosen can answer now: ${chain.reason}.` : "";

  if (pairs.length === 0) {
    return <Group title={label} foot={hint}>
      <Row label={kind === DIRECTED ? "No voice here takes a direction" : "Nothing offers this yet"}
        hint={kind === DIRECTED ? "Switch it on for a voice model on its provider’s page" : "Add a model to a provider above"} />
    </Group>;
  }

  return <Group
    title={label}
    foot={<>
      {hint}{state && ` ${state}`}
      {!inherited && <> <button type="button" className="pref-link-inline" onClick={() => onChange(kind, null)}>
        Use this server’s order instead
      </button></>}
    </>}
  >
    {pairs.map((pair) => {
      const at = live.findIndex((one) => same(one, pair));
      return <ModelRow
        key={`${pair.provider} ${pair.model}`}
        pair={pair}
        provider={providers.get(pair.provider)}
        on={at >= 0}
        first={at <= 0}
        last={at < 0 || at === live.length - 1}
        onToggle={(next) => change(next ? [...live, pair] : live.filter((one) => !same(one, pair)))}
        onMove={(direction) => {
          const next = [...live];
          const other = next[at + direction];
          if (!other) return;
          next[at + direction] = next[at];
          next[at] = other;
          change(next);
        }}
      />;
    })}
  </Group>;
}

/** The providers, each with what it offers and whether it works, and the way to add another. */
function ProviderList({ providers, onOpen, onAdd }: {
  providers: ModelProvider[];
  onOpen(provider: ModelProvider): void;
  onAdd(): void;
}) {
  return <Group title="Providers">
    {providers.map((provider) => {
      const state = stateOf(provider);
      return <Link
        key={provider.id} label={provider.label}
        hint={provider.kinds.length ? provider.kinds.map((kind) => KIND_TITLES[kind] ?? kind).join(" · ") : "No models yet"}
        mark={<StateMark ok={state.ok}>{state.words}</StateMark>}
        onOpen={() => onOpen(provider)}
      />;
    })}
    <Action onClick={onAdd}>Add a provider…</Action>
  </Group>;
}

const failure = (error: unknown, fallback: string) =>
  error instanceof AcervoApiError || error instanceof Error ? error.message : fallback;

export default function ModelPanel({ onNotify }: { onNotify(message: string): void }) {
  const { sub, open, close } = useSubPage();
  const { value: catalogue, error, set } = useServerSetting(SETTINGS.models);
  const [working, setWorking] = useState(false);

  /** One write, and the server's answer replaces what is shown — never this client's optimism. */
  async function save(kind: string, pairs: ModelPair[] | null) {
    setWorking(true);
    try {
      set(await backendSession.saveModelSelection({ [kind]: pairs }));
      if (pairs === null) onNotify("The providers’ own order is back in force.");
    } catch (error) {
      onNotify(failure(error, "That choice could not be saved."));
    } finally { setWorking(false); }
  }

  /** A provider write: the readout it answers replaces the cached one, orders and all. Voice
      choices live on Pronunciation's settings, and losing a model can change them too. */
  const write: Write = async (call: () => Promise<ProviderChange>) => {
    try {
      const answer = await call();
      set(answer);
      void refresh(SETTINGS.pronunciations).catch(() => undefined);
      return answer;
    } catch (error) {
      return failure(error, "The server could not be reached, so nothing changed.");
    }
  };

  if (!catalogue) return error ? <Notice>{error}</Notice> : <Placeholder rows={4} />;
  if (sub) return <ProviderSubPage sub={sub} catalogue={catalogue} write={write} open={open} close={close} onNotify={onNotify} />;

  const refused = catalogue.providers.filter((provider) => provider.check?.ok === false && provider.check.reason === "authentication");
  return <div className="pref-stack" aria-busy={working}>
    {catalogue.providers.length === 0 && <Notice>
      This server has no provider yet, so nothing can be written, drawn or read aloud. Add one below.
    </Notice>}
    {refused.map((provider) => <Notice key={provider.id}>
      {provider.label} refused its key, so nothing is sent to it.{" "}
      <button type="button" className="pref-link-inline" onClick={() => open(providerPage(provider))}>Replace the key</button>
    </Notice>)}
    <ProviderList providers={catalogue.providers} onOpen={(provider) => open(providerPage(provider))} onAdd={() => open(ADD_PROVIDER)} />
    {KINDS.map((entry) => <KindSection
      key={entry.id} {...entry} kind={entry.id} catalogue={catalogue}
      onChange={(kind, pairs) => void save(kind, pairs)}
    />)}
  </div>;
}
