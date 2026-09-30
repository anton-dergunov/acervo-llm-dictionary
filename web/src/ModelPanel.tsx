import { useCallback, useEffect, useState } from "react";
import {
  backendSession,
  type ModelCatalogue,
  type ModelChain,
  type ModelPair,
  type ModelProvider
} from "./api";

/**
 * The Models pane: which provider and model build an entry, in what order.
 *
 * The unit is a **(provider, model) pair**, not a provider. A free tier is metered per model, so
 * Gemini's two 500-a-day models are a thousand a day and the second is reached by the first one's
 * 429 — choosing between them is a real choice, not a detail.
 *
 * This is server state, not a device preference like the dictionary switches next door: it decides
 * what the vocabulary is made of, so an entry captured on a phone should be built by the same model
 * as one captured on a laptop. Saving is an ordinary online-only write that fails loudly.
 *
 * A pair whose provider this server has no credential for stays in the list, keeps its place and is
 * simply skipped when the chain is walked. That is deliberate: a chain is a preference and a
 * credential is a deployment fact, and a rotated key must not destroy an order or lock the owner
 * out of changing it.
 */

/* `offers` is the catalogue kind a chain draws its models from. The two pronunciation orders both draw
   from `audio`: any voice can read either, and which one should is the owner's answer, not a fact
   about the voice. */
const KINDS: { id: string; offers: string; label: string; help: string }[] = [
  {
    id: "text",
    offers: "text",
    /* Not "Entries": the same models write the briefs the picture generator works from, and will
       write whatever else needs words. What they have in common is that they produce text. */
    label: "Text",
    help: "Writes definitions, glosses, examples and usage notes when you capture a word — and the "
      + "briefs the picture models draw from. The first that answers wins; a rate-limited one hands "
      + "on to the next."
  },
  /* The same models as Text in a second order, because the two questions want different answers:
     an entry wants the best writer, and a tap on a photo wants an answer before the finger lifts. */
  {
    id: "quick",
    offers: "text",
    label: "Quick look-up",
    help: "Says what a word you tapped on a photo means in its sentence, while you wait. Put the "
      + "fastest first: the entry itself is still written by the Text order when you add the word."
  },
  {
    id: "image",
    offers: "image",
    label: "Pictures",
    help: "For the sense pictures. Nothing reads this order yet — the job that draws them is still "
      + "to come — but what you choose here is kept."
  },
  /* Named for what these voices *can do*, not for what they are used for. They were labelled by use
     — "words and definitions", "example sentences" — which stopped working the moment there were
     three uses and still two orders. Settings ▸ Pronunciation ▸ Delivery is where each use picks
     one, and the ids are unchanged. */
  {
    id: "audioPlain",
    offers: "audio",
    label: "Pronunciation — a clear, even voice",
    help: "For anything that should sound the same every time. Cheaper and faster, and it reads "
      + "whatever Settings ▸ Pronunciation points at it. A voice that does not speak the word's "
      + "language is passed over."
  },
  {
    id: "audioExpressive",
    offers: "audio",
    label: "Pronunciation — a voice that takes a direction",
    help: "For anything that should sound like somebody saying it. Only voices that take a "
      + "direction are listed: any other would read without the emotion and look as though it had "
      + "worked. When none of these can answer, the clear voice reads instead, plainly."
  },
  {
    id: "ocr",
    offers: "ocr",
    label: "Reading photos",
    help: "Reads the text on a photo you take or choose, word by word with where each one is, so "
      + "any word on it can be tapped."
  }
];

const same = (one: ModelPair, other: ModelPair) =>
  one.provider === other.provider && one.model === other.model;

/** The order that exists to carry a direction, and so offers only voices that take one. */
const DIRECTED = "audioExpressive";

/** Every pair a kind can offer, in catalogue order. */
function offeredPairs(providers: ModelProvider[], kind: string, offers: string): ModelPair[] {
  return providers.flatMap((provider) => (provider.models[offers] ?? [])
    .filter((model) => kind !== DIRECTED || provider.styles?.[model] === "instruction")
    .map((model) => ({ provider: provider.id, model })));
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
  return <div className={`config-row model-row${missing ? " unavailable" : ""}`}>
    <label className="model-switch">
      <input type="checkbox" checked={on} onChange={(event) => onToggle(event.target.checked)} />
      <span className="config-main">
        <strong>
          {label}
          {/* Dimmed text alone was too quiet to notice while scrolling a long list. */}
          {missing && <span className="model-badge" title="Not available on this server">
            <span aria-hidden="true">{"⚠"}</span> unavailable
          </span>}
        </strong>
        <span className="model-id">{pair.model}</span>
        {missing && <span className="model-warning">
          {provider?.reason}. It keeps its place in the order and is passed over.
        </span>}
        {/* Which account is being spent. Only Google needs saying: its credentials are a file that
            may belong to any of several logins, where a key belongs to whoever holds it. */}
        {provider?.account && <span className="model-account">Billed to {provider.account}</span>}
      </span>
    </label>
    <button
      className="icon-btn" aria-label={`Move ${label} ${pair.model} up`}
      disabled={!on || first} onClick={() => onMove(-1)}
    >{"↑"}</button>
    <button
      className="icon-btn" aria-label={`Move ${label} ${pair.model} down`}
      disabled={!on || last} onClick={() => onMove(1)}
    >{"↓"}</button>
  </div>;
}

function KindSection({ kind, offers, label, help, catalogue, onChange }: {
  kind: string;
  offers: string;
  label: string;
  help: string;
  catalogue: ModelCatalogue;
  onChange(kind: string, pairs: ModelPair[] | null): void;
}) {
  const chain: ModelChain | undefined = catalogue.chains[kind];
  if (!chain) return null;
  const providers = new Map(catalogue.providers.map((provider) => [provider.id, provider]));
  /* What is switched on is what will actually be asked — under an owner's chain *and* under the
     server's own order, which the server resolves and sends here as `pairs`.

     Showing every box unchecked under the deployment default was a lie with consequences: unticking
     the last model looked like turning capture off, and the server carried on building entries with
     the model at the head of its own order. The pane must show what will happen, so an inherited
     order arrives ticked and says whose it is. Changing anything makes the order yours. */
  const offered = offeredPairs(catalogue.providers, kind, offers);
  /* A saved expressive order is kept as it was saved, and the server walks only its directed
     voices. What is shown is what will be asked, so a pair this order cannot use is not drawn —
     and the next change you make saves the order without it. */
  const live = kind === DIRECTED
    ? chain.pairs.filter((pair) => offered.some((one) => same(one, pair)))
    : chain.pairs;
  const inherited = chain.source === "deployment";
  const pairs = orderedPairs(offered, live);

  /* Three states, and unticking the last box reaches the third rather than bouncing off it:
     an order of your own, nothing at all, or "whatever the server does". Switching everything off
     is a real answer — most of Acervo works without a model, and reading, editing and writing YAML
     by hand all still do — so it is stored rather than refused. `null` is the way back, and it has
     its own button, because no arrangement of tick boxes could mean "stop deciding". */
  const change = (next: ModelPair[]) => onChange(kind, next);
  const followServer = () => onChange(kind, null);

  return <div className="model-kind">
    <h4>{label}</h4>
    <p className="config-help">{help}</p>
    {inherited && <p className="config-help">
      {live.length
        ? "You have not chosen, so this server’s own order is in force — shown ticked below. "
          + "Change anything and the order becomes yours."
        : "You have not chosen, and this server has nothing it can use."}
      {chain.reason ? ` Right now it cannot build: ${chain.reason}.` : ""}
    </p>}
    {!inherited && live.length === 0 && (chain.pairs.length
      ? <p className="config-help model-warning">
          Nothing you chose here takes a direction, so the clear voice reads instead.
        </p>
      : <p className="config-help model-warning">
          Switched off. Nothing here will be generated, and the rest of Acervo works as usual.
        </p>)}
    {!inherited && live.length > 0 && chain.reason && <p className="config-help model-warning">
      Nothing you have chosen can be asked right now — {chain.reason}.
    </p>}
    {!inherited && <p className="config-help">
      <button className="link-btn" onClick={followServer}>Use this server’s order instead</button>
    </p>}
    <div className="config-list">
      {pairs.map((pair) => {
        const at = live.findIndex((one) => same(one, pair));
        return <ModelRow
          key={`${pair.provider} ${pair.model}`}
          pair={pair}
          provider={providers.get(pair.provider)}
          on={at >= 0}
          first={at <= 0}
          last={at < 0 || at === live.length - 1}
          onToggle={(next) => change(
            next ? [...live, pair] : live.filter((one) => !same(one, pair))
          )}
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
    </div>
  </div>;
}

/**
 * Every credential this server holds, and whose account it spends.
 *
 * This reading used to need an SSH session and a root password — `python -m acervo.admin
 * providers` on the machine itself. It answers a question the chain above cannot: *which* key is
 * deployed. Two keys for the same provider are otherwise indistinguishable, so a rotation that
 * only half happened looks exactly like one that worked.
 *
 * A key is shown as four characters at each end and never more. That is enough to match against
 * the provider's own dashboard by eye and not enough to use, and it is the entire relaxation of
 * the rule that this route serves what the server is credentialed *for* and never the credential.
 * A file credential shows no fragment at all — it is named by its account, which is the better
 * answer and the reason to prefer a service-account key over a bare login.
 */
function ProviderTable({ providers }: { providers: ModelProvider[] }) {
  return <div className="provider-table" data-testid="provider-table">
    {providers.map((provider) => {
      const credential = provider.credential;
      const missing = provider.available === false;
      return <div key={provider.id} className={`provider-line${missing ? " unavailable" : ""}`}>
        <span className="provider-name">{provider.label}</span>
        <span className="provider-credential">
          {credential?.kind === "none" && <span className="provider-none">no credential needed</span>}
          {credential?.kind === "key" && (credential.hint
            ? <><span className="provider-var">{credential.variable}</span>{" "}
                <span className="provider-hint">{credential.hint}</span></>
            : <span className="provider-none">{credential.variable} not set</span>)}
          {credential?.kind === "file" && <>
            <span className="provider-var">{credential.variable}</span>{" "}
            <span className="provider-none">
              {credential.present ? "a credentials file" : "no file installed"}
            </span>
          </>}
        </span>
        <span className="provider-account">
          {provider.account && <span className="provider-hint">{provider.account}</span>}
          {(provider.settings ?? []).map((setting) => <span key={setting.name} className="provider-setting">
            {setting.name.replace(/^ACERVO_|^CLOUDFLARE_/, "").toLowerCase().replace(/_/g, " ")}
            {" "}
            <span className="provider-hint">{setting.value || "not set"}</span>
          </span>)}
        </span>
        <span className="provider-usage">
          {/* The visible word is the same in every row, so the accessible name carries the
              provider — otherwise a screen reader reads six links all called "usage". */}
          {provider.usageUrl && <a
            href={provider.usageUrl} target="_blank" rel="noreferrer noopener"
            aria-label={`${provider.label} usage`}
          >usage{" ↗"}</a>}
        </span>
      </div>;
    })}
  </div>;
}

export default function ModelPanel({ onNotify }: { onNotify(message: string): void }) {
  const [catalogue, setCatalogue] = useState<ModelCatalogue | null>(null);
  const [failed, setFailed] = useState(false);
  const [working, setWorking] = useState(false);

  const refresh = useCallback(async () => {
    try { setCatalogue(await backendSession.fetchModels()); }
    catch { setFailed(true); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  /** One write, and the server's answer replaces what is shown — never this client's optimism. */
  async function save(kind: string, pairs: ModelPair[] | null) {
    setWorking(true);
    try {
      setCatalogue(await backendSession.saveModelSelection({ [kind]: pairs }));
      if (pairs === null) onNotify("This server’s own order is back in force.");
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "That choice could not be saved.");
    } finally { setWorking(false); }
  }

  if (failed) return <section className="config-section">
    <h3>Providers</h3>
    <p className="config-help">
      Your server could not be reached, so what it builds entries with is unknown right now.
    </p>
  </section>;

  if (!catalogue) return <section className="config-section">
    <h3>Providers</h3>
    <p className="config-help">Asking your server which models it can use…</p>
  </section>;

  return <section className="config-section">
    <h3>Providers</h3>
    <p className="config-help">
      Which model builds what, and in what order. Switch one on to use it, and use the arrows to say
      which is asked first; when one is rate limited or down the next answers, and the entry records
      which one actually did. This is an account setting, so it follows you to every device.
    </p>

    {KINDS.map((entry) => <KindSection
      key={entry.id} {...entry} kind={entry.id} catalogue={catalogue}
      onChange={(kind, pairs) => void save(kind, pairs)}
    />)}

    <h4 className="provider-heading">Credentials</h4>
    <p className="config-help">
      What your server holds, and whose account each one spends. A key is shown as four characters
      at each end — enough to tell two apart, never enough to use. No provider will tell Acervo how
      much of an allowance is left, so the links open the provider{"’"}s own page.
    </p>
    <ProviderTable providers={catalogue.providers} />

    {working && <p className="config-help" role="status">Saving…</p>}
  </section>;
}
