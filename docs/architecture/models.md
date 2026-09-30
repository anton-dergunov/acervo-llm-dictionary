# Models · how Acervo calls a model

**`src/acervo/models/` is the one way to call a model, and a provider is a row.** Text, pictures,
speech and OCR all go through it — `text()`, `image()`, `speech()`, `ocr()` — and every call returns an
`Answer` naming the (provider, model) pair that **answered**, which under a chain is not knowable
before the call. The contract is that a record names the model that did the work, not the one asked
first. Managing providers from Settings, and auditing the alternatives to today's defaults, are
[`../plans/provider-management.md`](../plans/provider-management.md).

---

## The catalogue

`models/catalogue.json` is tracked and ships the **list, never a credential**: `keyEnv` and `requires`
name environment variables, and `usageUrl` is a template rather than a link with an account in it. It
is the only place a provider's model ids, endpoint and capabilities are written down.

**A row names several models per kind, and the unit of choice is a (provider, model) pair**, not a
provider: a free tier is metered per model, so two models at 500 requests a day each are a thousand,
and the second is reached by the first one's 429. The default walk is provider by provider and,
inside each, model by model, in catalogue order.

**What a row can do is a declaration, not code.** `capabilities.jsonMode` decides whether
`{"type": "json_object"}` is sent or JSON is asked for in prose; `params` carries per-row generation
settings; `timeouts` how long to wait on that row; `passes` which call arguments come from which
variables; `capabilities.audio.models` the style, languages, locales and voices of each voice model;
`capabilities.image` whether a seed is honoured and whether references can be sent. **A provider fact
discovered the hard way belongs in the row, not in a branch** — that one text-to-speech route takes
`text` where another took `prompt`, that Vertex refuses `response_format`, that Gemini will not accept
OpenAI's voice names, that the same call answers in under two seconds on a free tier and takes half a
minute on Vertex.

`text()`, `image()` and `speech()` go over LiteLLM, imported lazily so the rate limiter
(`models/pacing`) works in the worker image, which does not install it. What LiteLLM does not cover is
reached by hand: Cloudflare's image and audio models (`cloudflare.py`), Cloud Text-to-Speech
(`google_tts.py`) and Cloud Vision (`google_vision.py`).

## The chain

A call walks an ordered chain of pairs. **It falls through on a 429, a 5xx, a timeout, a dropped
connection, and an answer the caller declares unusable — and on nothing else.**

- **An authentication failure or a rejected configuration is a mistake to fix**, not a condition to
  route around: routing around it hides the mistake and spends someone else's allowance on it.
- **An unusable answer does fall through.** A model that will not hold a shape has revealed a fact about
  itself, not a mistake in the deployment, and it is the one failure the owner can do nothing about;
  made terminal, a weak row at the head would make every stronger row behind it unreachable. `unusable`
  and `empty` are the two reasons a *caller* raises, from inside the `ask` callback so the walk can see
  them — `llm_json` when a reply is not JSON, `images/brief.py` when a brief will not parse, the clip
  selector when its reply does not validate — and the pair lands in `passed_over` like any other, so
  nothing is hidden.
- **`cooldown.py` remembers a refusal** so an exhausted allowance is not re-probed on every word — as an
  ordering hint only. When every pair is resting the hints are ignored and the chain runs as written,
  which makes recovery automatic without knowing any provider's reset hour. A 429 does not say whether a
  per-minute or a per-day allowance ran out, so the first rest is short and doubling reaches the longer
  case. A single 503 is forgiven: "high demand" lands on one request in three, and resting on it sent
  the second call of one capture to the slower fallback.
- **A caller with somebody waiting hedges.** Resolve, compose and chat pass `hedge_after`: a pair silent
  that long is raced by the next one, the first usable answer wins, and the loser's late outcome is only
  logged. The delays live beside the timeouts in `call.py`, set from measured healthy answers.
- **A pair naming a model the catalogue no longer offers is refused**, because nothing is supposed to
  produce it and skipping it would walk half the chain forever with no symptom.

## Whose chain it is

**Which pairs answer is the owner's choice**, per kind, in Settings ▸ Providers. `services/models.py`
resolves the owner's `model_selection` row, then the deployment's default — `ACERVO_TEXT_CHAIN` for
text, the catalogue's `defaultChains` for the two voice orders — then catalogue order — re-read on
every request, so a change takes effect on the next call with nothing restarted. The row is
owner-scoped server state, never replicated, and **no row means "follow the deployment default"**, a
legitimate answer rather than a gap, so nothing creates one eagerly. A chain has **three states**:
absent follows the default, an explicitly empty one means "generate nothing of this kind", and a
list is an order. Collapsing the first two would make unticking the last model look like switching a
kind off while the server carried on with its own order.

**A pair whose provider has no credential is kept and skipped**, not refused: a chain is a preference
and a credential is a deployment fact, and a rotated key must not destroy an order or lock the owner
out of changing it.

**The kinds are `text`, `quick`, `image`, `ocr`, and two voice orders.** `quick` is the text models in a
second order, for a call made while a finger is still on the glass (photo capture's tap). The voice
orders, `audioPlain` and `audioExpressive`, both draw from the one `audio` kind
([`../features/pronunciation.md`](../features/pronunciation.md)). **Only a voice whose model declares
`style: instruction` reads the expressive order**: that order exists to carry a direction, and a voice
that cannot take one recorded as though none had been asked for, silently. A saved order is kept as
saved and the walk skips such voices; the catalogue refuses an expressive default that names one; and
when no directed voice can answer, the plain order reads instead, with a log line saying so.

## Credentials

**A credential never leaves the server, with one bounded exception.** `GET /models` returns what the
server is credentialed *for*, and a key's first four and last four characters on that one
authenticated owner route, so Settings ▸ Providers can say *which* key is deployed — "a key is set" and
"*that* key is set" are different answers, and only the second closes a half-finished rotation. A
`requires` value, such as a project id, is shown in full, and a row listing its `keyEnv` among them is
refused. `test_it_never_returns_a_key_or_how_a_provider_is_reached` asserts the whole value is absent
from the whole response body.

**Vertex is the one provider whose credential is a file**: Google will not authenticate from a value,
so a workstation uses application default credentials and a server mounts the file, named by the row's
`authEnv`. Because that file is whichever Google login was last signed in, a row may name an
`accountEnv` — set, and the row refuses to run as any other account, and refuses too when the
credentials cannot prove whose they are. Setting it up is [`../operations/vertex-setup.md`](../operations/vertex-setup.md);
`python -m acervo.admin providers` prints what a machine can call, and as whom, spending nothing.

## Constrained decoding is not used, anywhere

`call.text` has no `schema` argument. The most it asks for is JSON *mode* — "answer with a JSON
object" — and the shape is stated in the prompt and enforced by the caller's own parser afterwards.

This was measured, not assumed. Sending a JSON Schema through `response_format` made the clip
selector's translations grow from 61 characters to between 266 and 1,039 — the model drafting *inside
the string value*, writing a version, rejecting it ("Wait, no."), starting again — and three calls in
four timed out. The strongest case for a schema was word alignment, whose schema restricts every id to
an enum of that request's own tokens: against constructed ground truth it bought **no accuracy at any
size**, and above roughly a hundred tokens the provider rejected it with a 400, which the chain treats
as terminal. A schema guarantees validity, never correctness, and bites hardest where the task needs
judgement.

It is a rule rather than a preference because of the failure mode: a constrained reply is structurally
valid by construction, so it passes every check a parser can make while carrying the model's own
drafting into a field a reader sees — an invisible failure an unattended ingestion would write a
thousand times before anyone opened an article. **Reintroducing it needs evidence, not argument**: a
measurement on the actual prompt, the actual models and realistic input sizes, showing it buys
something the caller's own validation cannot — and checked at the largest input the caller can
produce, since the alignment schema worked perfectly at sixty tokens and failed outright at a hundred
and five.

## Layering

**The package stands alone**: it imports no settings, graph, database or Acervo wire vocabulary, and
`test_layering.py` enforces it. It decides *what kind of thing* went wrong — a closed seven-value
`Reason` — and `services/models.py` turns that into Acervo's `llm_*` codes. That split is what lets the
file ingestion and the job runner retry on exactly `llm_rate_limited`, `llm_unavailable` and
`llm_unreachable` without the package knowing those codes exist. Batch work under `jobs/` may not
import `repository/`, so it is *given* a chain rather than looking one up.

## The call log

Every model call is one `key=value` line in a rotating file beside the database
(`ACERVO_CALL_LOG_PATH`), naming the pair that answered, how long it took and what the caller did with
the answer. `python -m acervo.admin calls` reads it back per job and per model, and it is where every
timeout here is set from: a bound is read from the log rather than guessed.
