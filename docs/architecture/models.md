# Models · how Acervo calls a model

**`src/acervo/models/` is the one way to call a model, a provider is an account the owner added, and
a provider fact found the hard way belongs in its family.** Text, pictures, speech and OCR all go
through it — `text()`, `image()`, `speech()`, `ocr()` — and every call returns an `Answer` naming the
(provider, model) pair that **answered**, which under a chain is not knowable before the call. The
contract is that a record names the model that did the work, not the one asked first. Every attempt is
counted for Usage (below). Which providers Acervo supports, and how each is added, is
[`../providers.md`](../providers.md).

---

## Providers and families

**A provider is one account: one credential, offering one or more kinds.** "Google Cloud" is one
provider, answering text and pictures through Vertex, voices through Cloud Text-to-Speech and photos
through Cloud Vision. Providers belong to the server, not to an account: every account on a server
spends the same keys. A provider is a row the owner adds (`providers`, never replicated) holding:

- an `id`, a slug orders and voice choices name, which does not change once saved;
- its `family`, the code that speaks to it;
- the family's non-secret `settings` — a Cloudflare account id, a Vertex project and location, the
  address of an Ollama;
- its models per kind, in the order they were added, each carrying only what varies between models
  and can be checked on the provider's own page: whether a voice takes a `direction`, the
  `languages` it speaks, `voices` typed in where the provider cannot list them, and an optional free
  `allowance`;
- `extra`, a JSON object merged into every call for the quirk no family foresaw;
- what its last key check said.

**The key is not in the row.** It is in `providers.secrets.json` beside the database (see
*Credentials*), so a database backup, a deploy's copy of it and an export never carry one.

**A family is code** (`models/families.py`), and it carries what a user should never need to know:
the route LiteLLM takes and its prefix, the base URL, whether JSON mode is native, the parameters a
provider needs, how long it is worth waiting, what its image route does with a size, a seed and
reference pictures, what its speech route needs, its usage page. Every one of those was found by a
call that failed — that one text-to-speech route takes `text` where another took `prompt`, that
Vertex refuses `response_format`, that Workers AI truncates at 256 tokens unless told otherwise, that
the same call answers in under two seconds on a free tier and takes half a minute on Vertex — and
each is a fact about the provider rather than about anybody's account. The OpenAI-compatible
services are one family's code with a preset each: a prefix, a base URL and a listing endpoint.

**Two families are written from the provider's reference and not yet tried with a real call**:
Azure Speech and Forge or A1111. Their requests follow the reference and their unit tests pin it,
but the quirks a family holds are found by calls that fail, and none has been made. The key check
on saving is the first real call, and it says in the provider's words what is wrong. The guide does
not recommend either until a call has answered.

**What changes with the provider's catalogue comes from the provider** (`models/listing.py`): its
models, and its voices with their locales and genders, asked for with calls that spend nothing.
Settings asks for them when a picker opens — `GET /providers/{id}/models?kind=` and
`GET /providers/{id}/voices?model=` — and each says `listed: false` where the provider cannot say, so
the owner types the name instead; which kinds each family can list is one table in `listing.py`. A
listing the provider turns away is refused in its own words (`key_refused`, or
`provider_listing_failed`), and the envelope writes it down with the provider, the kind and the
reason, so `admin log --failed` shows it.
Google's voice list is the one a call depends on, so it is kept in memory for a day per provider and
credential. A Gemini voice is listed once (`Kore`) under `en-US`, which is where it was made rather
than all it says, so it speaks any locale and is sent the nearest one Google lists any voice under —
`es-US` for Argentina, which shares `es-419` with it; a Gemini voice refuses `es-AR` and a bare `es`
(measured on 5 Nov 2026). Locales typed on a model win over that list.
The Gemini API's voice list (`GET /v1beta/voices`, about 2,100 voices) is kept the same way, and has
the same two kinds. The thirty voices named once (`kore`) speak any language. The rest are made for
a locale and say so in their id (`es-419-advisor-1`). Latin American Spanish is one locale there, and
the voice's accent names the country ("Argentina Spanish"), so such a voice is offered as `es-AR`.
A voice is sent by its `name` and shown by its `label` where the provider's id is not a word anybody
would read: ElevenLabs sends `EXAVITQu4vr4xnSDxMaL` for the voice it calls Sarah. Its voices speak
every language their model has, so none carries a locale. A speech server's voices carry theirs in
their names, by Kokoro's convention (`ef_dora`: Spanish, female) or Piper's (`en_GB-alan-medium`), so
a language none of its voices speaks is not asked of it.

**A family may carry its usual models** (`Ready` in `families.py`): the models per kind Acervo has
called through it with its own prompts, which voices take a direction, and the free allowance where
the provider publishes one. Add a provider offers them with one switch, on by default, and
`listing.ready` chooses once the key works: a kind or model only a credentials file reaches comes only
with the file, and a model the provider lists is added only while its list still holds it, so a set
that ages costs a missing model and never a broken one. The page is the same afterwards; the set is
where a provider starts, not a mode it is in. Google Cloud's is everything Acervo does, from one
account, and is what the owner runs.

**Laptop tools** — the scripts, the experiments and the live tests — read a gitignored
`providers.local.json` in the shape the server stores, with each key inline (`models/local.py`). The
server never reads it.

`text()` and `image()` go over LiteLLM, imported lazily so the rate limiter (`models/pacing`) works in
the worker image, which does not install it. What LiteLLM does not cover is reached by hand:
Cloudflare's image and audio models (`cloudflare.py`), Cloud Text-to-Speech (`google_tts.py`), the
Gemini API's speech (`gemini_tts.py`, the Interactions API), ElevenLabs (`elevenlabs.py`), a speech
server on OpenAI's route (`openai_speech.py`: Kokoro, Piper behind Speaches), Azure Speech
(`azure_speech.py`, SSML), pictures on your own machine through A1111's route (`a1111.py`: Draw
Things, Forge, A1111) and Cloud Vision (`google_vision.py`).
Speech never goes through LiteLLM: reached that way, a Gemini voice drops its direction before the
request is built.

The Gemini API's speech request has no language field, and the model guesses the language from the
words. It gets a sentence right and a single word wrong: "picar" came back as English and "pie" as
Hindi (measured on 6 Nov 2026, with a transcriber listening back). So the language always heads the
direction ("Say this in Spanish."), whatever else the direction says. The free tier allows three
speech requests a minute per model, and its 429 says when to come back.

ElevenLabs v3 and v4 take a direction as one free-text tag at the head of the words,
`[Surprised and amused] No me digas.`, and do not read it out (a transcriber listening back heard only
the sentence). A month's free credits spent is a 402 `insufficient_credits`, which the bare status
table would call a refusal; the adapter says it as an allowance spent, so the expressive order passes
to the next voice. The free plan allows `wav_24000` as its best master (6 Nov 2026).

### Left out, and why

- **Hume**: it shut down its speech API on 13 Nov 2026.
- **Amazon Polly**: its generative engine covers 11 languages, and its free allowance lasts 12 months.
- **fal, Replicate, Black Forest Labs, Stability**: each needs its own asynchronous adapter, and none
  has a free tier worth one.
- **ComfyUI**: A1111's route is far simpler to drive, and Draw Things, Forge and A1111 all answer it.
- **A local voice that takes a direction** (Qwen3-TTS, CosyVoice 3): realistic on an Apple Silicon Mac
  and not on the NAS's processor, and neither ships a server. One run behind an OpenAI-style speech
  server is added as a speech server with `direction` switched on; Acervo does not build or pin it.
- **OpenAI's own speech and pictures**: the speech-server and LiteLLM image routes reach them, and
  no family offers them until a call has been made through them; OpenAI retires its speech models on
  6 Jan 2027.

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
- **A pair naming a model its provider does not offer is refused**, because nothing is supposed to
  produce it — removing a model removes it from every order — and skipping it would walk half the
  chain forever with no symptom. The speech orders are
  the one exception, and theirs is logged on every read
  ([`../features/pronunciation.md`](../features/pronunciation.md)).

## Whose chain it is

**Which pairs answer is the owner's choice**, per kind, in Settings ▸ Providers. `services/models.py`
resolves the owner's `model_selection` row, and with none, the providers in the order they were
added and their models in the order they were added — re-read on every request, so a change takes
effect on the next call with nothing restarted. The row is owner-scoped server state, never
replicated, and **no row means "follow the providers' own order"**, a legitimate answer rather than a
gap, so nothing creates one eagerly. A chain has **three states**: absent follows that order, an
explicitly empty one means "generate nothing of this kind", and a list is an order. Collapsing the
first two would make unticking the last model look like switching a kind off while the server
carried on with its own order.

**A pair whose provider cannot be asked is kept and skipped**, not refused: no key, a missing
setting, or a key the provider refused when it was last checked. A chain is a preference and a
working key is a fact about the provider, and a refused key must not destroy an order or lock the
owner out of changing it. **Removing a provider, or one of its models, takes it out of every order
and voice choice** in the same transaction, which is why a pair naming a model nobody offers is
refused rather than skipped: nothing is supposed to produce one.

**The kinds are `text`, `quick`, `image`, `ocr`, and two voice orders.** `quick` is the text models in a
second order, for a call made while a finger is still on the glass (photo capture's tap). The voice
orders, `audioPlain` and `audioExpressive`, both draw from the one `audio` kind
([`../features/pronunciation.md`](../features/pronunciation.md)). **Only a voice whose model takes a
direction reads the expressive order**: that order exists to carry a direction, and a voice that
cannot take one recorded as though none had been asked for, silently. Its default is only the voices
that take one; a saved order is kept as saved and the walk skips the others; and when no directed
voice can answer, the plain order reads instead, with a log line saying so.

**A companion service is given no key.** The clip service calls home to `POST /companion/text` for
each translation and alignment, authenticated by the operator token the two already share, and
Acervo walks the providers' own order for it — its job has no owner
([`../features/spoken-clips.md`](../features/spoken-clips.md) §2.13). LexiBeat's writer calls home the
same way with a render token. Keys live in one container.

## Credentials

**A credential never leaves the server, with one bounded exception.** The readout — `GET /models`,
and what every provider change answers with — shows a key as its first four and last four
characters, so Settings can say *which* key is set: "a key is set" and "*that* key is set" are
different answers, and only the second closes a half-finished rotation. A
credentials file is shown as the account it names. `test_it_never_returns_a_key_or_a_credentials_file`
asserts the whole secret is absent from the whole response body.

**Keys live in `providers.secrets.json` beside the database**, mode 600, written whole through a
temporary file and a rename, and read on every call (`services/provider_secrets.py`). A lost file
costs typing the keys again, and keys can be made again; that is the right way round.

**Every change to a provider answers with the whole readout** — what `GET /models` answers, and
the id of the provider it changed — because removing a model or a provider also takes it out of the
orders, and Settings renders what the server holds rather than guessing it.

**Saving a key makes one call that spends nothing** — a model list, or Google's voice list — and says
plainly whether the key works, and as whom where the provider says (`listing.check`). A provider is
stored only when its check works; a key the provider refuses is said in the provider's own words and
nothing is stored. Every check is an `activity.log` line, so `admin log --failed` shows a refused
key with its sentence.

**Google Cloud takes a key or a credentials file.** A key reaches Cloud Text-to-Speech and Cloud
Vision, sent as `x-goog-api-key` so it is never in an address. It does not reach a Gemini voice on
Cloud Text-to-Speech, which runs on Vertex ("Permission 'aiplatform.endpoints.predict' denied",
measured on 6 Nov 2026 with a key restricted to the two APIs), so the family refuses such a model on
a provider with only a key; with a key, Gemini voices come through the Gemini API. A file — a service account's key or a
user's own sign-in — reaches those and Vertex text and pictures, and is handed to LiteLLM per call
with the provider's project and location, so two Google Cloud providers can be two accounts; its
access token is cached per provider and credential, and a user's sign-in sends the project as its
quota project. `python -m acervo.admin providers` prints the server's providers, which key each
holds, and what its last check said, spending nothing.

**Every value a credential could leak is redacted** from every provider error, at construction:
building a provider teaches `redact.py` its secrets, so no list of names has to be kept in step.

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

## Usage

Settings ▸ Providers ▸ Usage ([`../features/settings.md`](../features/settings.md) §8) shows, per
provider and model, how many calls were made, how many failed and why, and what they used up, against
the free allowance typed on the model. Five rules shape it:

- **Every attempt is counted, not only the one that answered**, because a 429 spends a free request
  too. `chain.walk` is where every attempt is seen, so it reports each one: the pair that answered,
  every pair passed over, a refusal that ends the walk (which also writes a call-log line, where it
  used to leave none), and a raced pair that finishes after another won. Every server call goes
  through a walk; the laptop image sweep does not, and nothing counts its calls.
- **The package reports; it does not count.** `models/usage.py` hands an `Attempt` to the sinks it
  was given and stops, the rule the call log follows. `services/usage.py` attaches the one sink that
  writes, when the application starts, and a sink can never fail a call: a count that cannot be
  written is an `activity.log` line, `usage not counted`, with the sentence
  ([`observability.md`](observability.md) §3).
- **Units come from the answer.** `Answer.spent` (`Spent`) carries tokens from LiteLLM's `usage`, the
  characters sent to a voice, and one picture or one photo per call; `cost_usd` is kept where LiteLLM
  priced the call. A failed call carries no units — and so an answer refused for its shape
  (`unusable`, `empty`) counts as a failed call whose tokens are not known.
- **One row a UTC day per (provider, model, kind)**, in the never-replicated `model_usage` table:
  calls, those that answered, failures by reason, the seconds of the answered calls (a timeout
  measures the bound, as the call log's timings argue), the units, the cost and the day's last
  failure. The day is UTC for everyone — Cloudflare's allowance resets at 00:00 UTC, Gemini's at
  midnight in California, so its gauge runs some hours off — and "this month" is the UTC calendar
  month. "All time" is the sum of the table, so the rotating call log does not limit it, and nothing
  deletes from it: a removed provider's calls are still shown under its id.
- **An allowance is measured, never enforced.** A gauge is the allowance's own unit over its own
  period — every attempt for `calls`, tokens in and out for `tokens`, and what was counted for the
  rest — and the provider's own limit is still what refuses a call. Cloudflare reports no neurons per
  call, so its allowance is typed in pictures or characters (about 95 FLUX.2 klein pictures a day).

`GET /usage` answers every period, every model's last thirty days and every gauge at once, so the
pages switch period without asking again.

## The call log

Every model call is one `key=value` line in a rotating file beside the database
(`ACERVO_CALL_LOG_PATH`), naming the pair that answered, how long it took, what it used up — `in=` and
`out=` tokens, `characters=`, `pictures=`, `photos=`, `cost=` — and what the caller did with the
answer. `python -m acervo.admin calls` reads it back per job and per model, and it is where every
timeout here is set from: a bound is read from the log rather than guessed. Each line ends with the id
of the request or job that made the call, added where the file is opened — the package itself emits
and knows nothing of it ([`observability.md`](observability.md) §2).
