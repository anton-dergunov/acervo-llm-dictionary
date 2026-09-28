# Providers: managed in Settings, audited, and easy to set up

**Status:** planned, not scheduled. Nothing here is built. It collects what is known so the work can
start from a page rather than from memory.

## Why

Acervo reaches every model through `models/catalogue.json`, a tracked file that ships to the server
inside the release, and every credential through `llm.env`, which `./deploy.sh --configure-llm`
writes on the server. That was the right shape for one owner and one machine. It is the wrong shape
for anyone else: a new user should be able to add a provider, paste a key and see it answer without
editing a file on a NAS or knowing what `passes` or `jsonMode` mean.

It is also the wrong shape for the owner's own future. Today almost everything — text, pictures,
voices, OCR — runs on Google, because a time-limited trial makes that the obvious choice while it
lasts. When it ends the chains must move to other hosted providers, or to models running on the NAS
or the Mac, without that being a code change. The provider package already makes a provider a row
rather than a branch; this plan makes a row something the interface can create.

## Where things stand

- **Eight rows, four kinds.** `gemini-free`, `vertex`, `google-tts`, `google-vision`, `cloudflare`,
  `openai`, `openrouter`, `ollama-local`, across `text`, `image`, `audio` and `ocr`. Five of them are
  Google or reach Google's credential. Two local models are *not* rows at all: the map's encoder
  (`models/encoder.json`) and the sentence splitter (`models/segmenter.json`), both baked into the
  image.
- **A row declares what the provider can do**: model ids per kind, `capabilities` (JSON mode, audio
  style, languages and voices per model, image references), `params`, `timeouts`, `passes`, and the
  environment variables it needs (`keyEnv`, `requires`, `authEnv`, `accountEnv`). Every one of those
  facts was discovered by calling the provider and getting it wrong first.
- **The owner already chooses the order.** Settings ▸ Providers edits `model_selection`, per kind,
  among pairs whose provider has a credential; `GET /models` reports which credentials exist and a
  key's first and last four characters, and nothing more.
- **Keys arrive by deploy.** `--configure-llm --llm-key NAME --llm-api-key-stdin` writes `llm.env`;
  Vertex additionally needs a credentials *file* mounted and named by `authEnv`
  ([`../operations/vertex-setup.md`](../operations/vertex-setup.md)).
- **Related open defect:** [`issues.md`](issues.md) §1 — the expressive
  order offers voices that cannot take a direction. Whatever the Settings form for audio looks like,
  it should make that impossible to configure.

## Four pieces of work

### 1 · Audit the providers

For each thing Acervo asks a model to do, which providers can do it, how well, on what free
allowance, and in which languages. Measured on Acervo's own prompts with the apparatus that already
exists, not read off a pricing page:

| Task | Existing apparatus |
|---|---|
| Compose, resolve, chat, clip selection, story write/translate/brief | `experiments/compose-lesson-line/`, `story-quality/`, `clip-translation/`, `tests/integration/test_models_live.py` |
| Sense and story pictures | `experiments/image_benchmark/`, [`../research/image-benchmark.md`](../research/image-benchmark.md) |
| Voices, plain and directed | `experiments/pronunciation-encoding/` (blind listening) |
| OCR | `experiments/photo-capture/` |
| Embedding for the map | `experiments/meaning-space/` |

Local and on-device options belong in the same table as hosted ones, judged on the same prompts:
Ollama for text on the NAS or the Mac, Piper or Kokoro for voices on the NAS, a local diffusion model
on the Mac (the idle-machine question is [`nas-to-mac-job-queue.md`](nas-to-mac-job-queue.md)),
RapidOCR. The photo spike already measured RapidOCR on the NAS and it lost; that is the kind of
answer this should produce for every kind.

The output is a recommendation per kind — a default chain that does not depend on one company — and
the catalogue rows to go with it.

**Local models, as an opportunity.** Running a model on the owner's own machines is a real option,
not a curiosity, and the likeliest place it pays is the voice. What the pronunciation research of
15 Sep 2026 found, as a starting point:

| Route | Languages | Quality for a reference | Where it runs |
|---|---|---|---|
| **Kokoro on the NAS** (CPU, Docker) | 8 | excellent for 82 M parameters | ~1.3 core-hours per audio hour: fine for recording in advance |
| **Piper on the NAS** (CPU, Docker) | ~30, 100+ voices | good, not native | ~10× real time per core |
| Kokoro in the browser (`kokoro-js`) | English only offline | very good | 92 MB q8 / 326 MB fp32 — ruled out, since other languages phonemise over the network |
| Piper in the browser (WASM) | ~30, phonemised offline | good, not native | ~60 MB per voice — not needed, since writes are online |

The server once had a Kokoro adapter (`src/acervo/tts/`, since deleted), so a local voice is a rebuild
rather than a revival — but the shape it would take is already settled: a catalogue row whose
transport is a local HTTP service, like `ollama-local` for text, recording into the same
`pronunciations` rows as any other voice. Text on Ollama and images on the Mac fit the same way.

**Candidates already known**, parked here rather than dropped:

- **Cloudflare Aura-2** for Spanish — a second model id and a voice list in the existing row, no code.
  Aura-2 exists only as `-en` and `-es`.
- **Azure Neural voices**, whose styles are an SSML enum rather than free text: a third value for
  `capabilities.audio.style`, and the first real test of that declaration.
- **Human recordings** as a source tier above TTS: Lingua Libre / Wikimedia Commons / Wiktionary
  (150–310 languages, CC-BY-SA, patchy per word), and Forvo (430+ languages; at the time of the
  research $2/month non-profit, 500 requests a day, no commercial use, attribution required — check
  whether its terms allow storing the file).
- **Isolated words read badly** — stress pairs, tone sandhi, a model that answers a short word with
  generated text. A carrier phrase synthesised and trimmed is the standard fix. Worth measuring per
  provider before deciding anything.

**Voice costs, desk research of 15 Sep 2026** — a starting point to re-check, not a result. A whole
vocabulary at the design's ceiling is ~1.9 M characters (10,000 headwords at ~9 characters, ~30,000
sentences at ~60):

| Provider | Metered by | Headwords | Sentences | Free allowance |
|---|---|---|---|---|
| Google Cloud TTS Standard | characters, $4/1M | $0.36 | $7.20 | 4 M chars/month |
| Google Cloud TTS WaveNet | characters, $4/1M | $0.36 | $7.20 | 1 M chars/month |
| Cloudflare Aura-1 | neurons ≈ $15/1M chars | $1.35 | $27.00 | ≈ 7.3 k chars/day |
| Azure Neural | characters, $16/1M | $1.44 | $28.80 | 500 k chars/month |
| Google Chirp 3: HD | characters, $30/1M | $2.70 | $54.00 | 1 M chars/month |
| Gemini 3.5 Flash TTS | audio tokens, $6/1M | $1.20 | $15.75 | — (Vertex, paid) |
| Gemini 3.1 Flash TTS | audio tokens, $20/1M | $4.00 | $52.50 | 10 requests/day |
| OpenAI gpt-4o-mini-tts | ≈ $0.015/min | $2.00 | $26.25 | — |

Steady state (~100 headwords a day) sits inside every character-metered free tier by two orders of
magnitude, so for voices the deciding questions are language coverage and whether the voice is right,
not price. The same research found local voices comfortable on the NAS's CPU — Piper at roughly 10×
real time per core, Kokoro at roughly real time — and named the honest reason to run one: not cost,
but independence from free tiers that expire. Piper's published 2.6 GB peak memory is a harness
artefact and should be measured before a shared machine is trusted with it.

### 2 · Providers and keys in Settings

Add, edit and remove a provider, and enter its key, from Settings ▸ Providers, taking effect on the
next request with nothing redeployed.

Rules that already hold and must keep holding:

- **A credential never leaves the server**, apart from the bounded first-four/last-four exception.
  A key typed into the interface travels to the server once and never comes back.
- **A provider fact is a declaration, not code.** A user cannot be expected to know that Vertex
  refuses `response_format` or that Aura takes `text` where another takes `prompt`, so the form
  starts from a **preset** per provider family — "Gemini API key", "OpenAI-compatible endpoint",
  "Cloudflare account", "Ollama on this network" — and a preset is a catalogue row with the blanks
  left for the user.
- **Which pairs answer stays the owner's choice**, and a chain still falls through only on the
  transient reasons. A key that is rejected is a mistake to show, not a condition to route around —
  so saving a key should make one cheap call and say plainly whether it worked and as whom.

Questions to answer before building:

- **Where rows live.** An owner-scoped, never-replicated server table like `model_selection` is the
  obvious home. The tracked catalogue would then be the list of presets, the way
  `dictionaries/catalogue.json` is a list and not data. There must be one source of truth for a row,
  not the file *and* the table. **The owner wants the JSON kept as a way to define rows**, not only
  the form — so the likely shape is that a row can be written as JSON in the form or imported from a
  file, and becomes a table row either way, rather than the server reading two sources.
- **Where keys live, and how they are protected at rest.** Today they are an env file only root can
  read. A table in the same SQLite file as the vocabulary is backed up with it; that is either a
  feature or a leak, and needs deciding.
- **What happens to `--configure-llm`.** Two ways to set a key is one too many; the deploy flag
  either goes or becomes the way to seed the table.
- **Vertex's file credential.** Uploading a service-account JSON through the interface, or keeping
  that one provider a deployment fact. The organisation policy that blocks creating keys
  ([`../operations/vertex-setup.md`](../operations/vertex-setup.md)) means a user login may be the only option some people
  have.
- **Local models as rows.** Whether the encoder and segmenter become choosable at all, or stay pinned
  because a changed encoder means a recomputed map.

### 3 · A setup guide for new users

For each provider the audit recommends: how to sign up, what the free allowance covers in Acervo
terms (words a day, pictures a day), which key to create with which permissions, and where to paste
it. A recommended starter set — the fewest accounts that cover every kind — with a no-cost path
first. [`../operations/vertex-setup.md`](../operations/vertex-setup.md) is the existing example of one provider's page;
the guide should read like that, for someone who has never deployed Acervo.

### 4 · How much each model is used, and how often it fails

Settings ▸ Providers shows, per provider and model, how many calls were made and how many failed — by
day, week, month and in total — so the owner can see which free tier is being spent and which model
is unreliable, without a shell on the server.

The numbers already exist. Every model call is a line in the call log beside the database, and
`python -m acervo.admin calls` reads it back per job and per provider:model — succeeded, failed,
median and p95 time. What is missing is a route that serves the same reading and the panel that
draws it. The log rotates, so "in total" is either as far back as the log reaches, or a small
counter the server keeps; which is part of building it.

## Order

The audit first, because it decides which presets the Settings form needs and which providers the
guide covers. Then Settings, then the guide. The audit can start any time and does not wait on the
trial ending — the point is to know the answer before it does. The usage figures depend on none of
it and can come first.
