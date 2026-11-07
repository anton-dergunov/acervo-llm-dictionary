# Providers: added in Settings, with their keys, and their usage shown

**Status:** designed and agreed with the owner on 5 Nov 2026. **S1, S2, S3 and S5 are built.** What
is built is described in [`../architecture/models.md`](../architecture/models.md) — Usage included —
and [`../features/settings.md`](../features/settings.md) §8; this page keeps what is left. The mock-ups
in `design/ui-prototype/settings.html?page=providers` are the specification for S4 onwards.

## Why

Anyone should be able to install Acervo, open **Settings ▸ Providers**, add the providers they want,
paste a key, and have it answer. There should be no file to edit, no deploy, and nothing to know about
`passes` or `jsonMode`. It should also be possible to run with **no API bill at all**, on free tiers and
models on your own machines.

Today none of that holds:

- Every provider is a row in the tracked `models/catalogue.json`.
- Every key is a line in `llm.env`, which `./deploy.sh --configure-llm` writes.
- Compose passes a fixed list of variable names into three containers.
- The file also freezes facts that belong to the provider: Google's voice lists copied from
  `voices.list` by hand, the locales a Gemini voice accepts, and the voices of a model that has no
  list at all.

A new provider, or a new voice, should not be a commit.

## The shape

**A provider is one account: one credential, offering one or more kinds.** "Google Cloud" is one
provider. It answers text and pictures through Vertex, voices through Cloud TTS and photos through
Cloud Vision, rather than the three rows that share one credential today. Providers belong to the
server, not to an account: every account on a server spends the same keys. Whether a second account
should have keys of its own is a question for [`first-use/other-users.md`](first-use/other-users.md),
and the shape does not need to change for it.

```json
{
  "id": "gemini",
  "family": "gemini-api",
  "label": "Gemini API",
  "settings": {},
  "models": {
    "text":  [{"id": "gemini-3.5-flash-lite", "allowance": {"amount": 500, "unit": "calls", "per": "day"}}],
    "audio": [{"id": "gemini-3.8-flash-tts", "direction": true, "languages": "any"}]
  },
  "extra": {}
}
```

- **`id`** is a slug. The form suggests one from the family and the owner may change it. Orders and
  voice choices refer to it, so it does not change once saved.
- **`family`** picks the code that speaks to the provider. A family's preset fills in the base URL,
  the route LiteLLM takes, whether JSON mode is native, the provider's own usage page and its docs
  link. The user never sees any of that.
- **`settings`** are the non-secret values a family asks for: a Cloudflare account id, a Vertex
  project and location, the base URL of an Ollama or a custom endpoint.
- **A model** carries only what varies between models and what a user can check on the provider's
  own page:
  - `direction`: whether a voice takes a free-text direction;
  - `languages`: `"any"` or a list;
  - `voices`: typed in only when the provider cannot list them;
  - `allowance`: optional, for the usage gauge.
- **`extra`** is an optional JSON object merged into every call, for the quirk no family foresaw.
  It is never needed for the families below.
- **The secret is not in the row.** See *Keys*.

What stays as it is:

- **The orders.** The six kinds are `text`, `quick`, `image`, `audioPlain`, `audioExpressive` and
  `ocr`, each an ordered list of (provider, model) pairs in `model_selection`.
- **The fall-through rules.** A chain passes on only on 429, 5xx, timeouts, dropped connections and
  unusable answers, never on a rejected key.
- **The expressive rule.** The expressive voice order can only hold models with `direction: true`.

**With no order chosen, the default is the providers in the order they were added, then their models
in the order they were added.** That default replaces both `ACERVO_TEXT_CHAIN` and the catalogue's
`defaultChains`.

**Provider facts move from the file into the family, and the family is code.** That is a deliberate
change from "a provider is a row":

- The quirks found the hard way stay out of the user's hands. Examples: Vertex refuses
  `response_format` on images; Cloudflare needs `max_tokens`; Aura takes `text` where another takes
  `prompt`; Cloud TTS wants `LINEAR16` for Gemini voices.
- The facts that change with the provider's catalogue, models and voices, come from the provider.

## Families

Measured or read on 5 Nov 2026. A free allowance marked *(console)* is one Google, Groq or Mistral no
longer publish: the number is from a third-party table, and the guide tells the user where their own
console shows it.

### Text

| Family | Presets | Free allowance | Notes |
|---|---|---|---|
| **OpenAI-compatible** | Gemini API, OpenAI, Anthropic, OpenRouter, Groq, Mistral, DeepSeek, Cloudflare, Ollama, LM Studio, *any other* | Gemini 3.5 / 3.1 Flash-Lite ≈ 500 requests a day, 3.8 Flash ≈ 20 *(console)*. Groq ≈ 1,000 a day on the 70B models *(console)*. OpenRouter `:free` models 50 a day, or 1,000 once 10 credits are bought. Cloudflare 10,000 neurons a day. | Every preset lists its models from `GET /models`. Anthropic ignores `response_format`, so its preset asks for JSON in the prompt; the *any other* preset has a switch for it. |
| **Google Cloud** (Vertex) | — | trial credit only | Needs the credentials file (see *Keys*). |

Text was never the hard kind: there are plenty of providers, and one family reaches nearly all of
them.

### Pictures

| Family | Presets | Free allowance | Notes |
|---|---|---|---|
| **Cloudflare Workers AI** (native `/ai/run`) | — | 10,000 neurons a day, reset at 00:00 UTC: about **170** pictures with FLUX.1 schnell, or **95** with FLUX.2 klein 4B, at 1024² | The free picture provider. Its compatible endpoint does not cover images. |
| **OpenAI images** (`/v1/images/generations`) | OpenAI, Together, *any other* | none (Together's free FLUX.1 schnell is listed, but whether it is served is unverified) | gpt-image-2 and gpt-image-1-mini are billed by token. |
| **Gemini image** | through the Gemini API key, or Vertex | **none**: no image model has a free tier | Takes reference pictures, which keep a story's characters the same. Imagen has left the Gemini API. |
| **A1111** (`/sdapi/v1/txt2img`) — *built; Draw Things tried* | Draw Things on a Mac, Forge or A1111 on a GPU machine | free | The simplest local picture API. ComfyUI is more capable and much harder to drive, so it is left out. |

### Voices

| Family | Free allowance | Languages | Takes a direction | Voices listed by |
|---|---|---|---|---|
| **Google Cloud TTS** | Standard and WaveNet 4 M characters a month; Neural2 and Chirp 3 HD 1 M; Gemini-TTS unlisted | the widest catalogue; Gemini-TTS 24 GA and 63 preview | Gemini-TTS models, through `prompt` | `voices.list` |
| **Gemini API TTS** (Interactions API) — *built* | free tier: 3 requests a minute per model (measured), daily cap *(console)* | 3.8 Flash TTS 130+, Flash-Lite TTS 100+ | yes, `speech_metadata.style`, free text | `GET /v1beta/voices` (language, accent, gender) |
| **ElevenLabs** — *built* | 10,000 credits a month through the API (checked), non-commercial, attribution required | v4: 90+ | v3 and v4, through free-text `[tags]` | `GET /v1/voices` |
| **OpenAI-compatible speech** (`/v1/audio/speech`) | presets: Kokoro (Kokoro-FastAPI), Piper (Speaches), Ollama; OpenAI | Kokoro 9, Piper 37, Ollama English only | only OpenAI's `instructions`, and OpenAI retires its speech models on **6 Jan 2027** | `/v1/audio/voices` where the server has it |
| **Cloudflare Workers AI** | 10,000 neurons a day ≈ 540 minutes of MeloTTS, or 7,000 characters of Aura-1 | MeloTTS en, es, fr, zh, ja, ko; Aura-2 en, es | no | typed in |
| **Azure Speech** — *built, not yet tried* | 500,000 characters a month | 100+ | no: its styles are a fixed SSML list, a later addition | `voices/list` |

**ElevenLabs direction.** Eleven v3 and v4 take audio tags in square brackets, and the tags are free
text: ElevenLabs' own prompting guide shows `[Warm, conversational tone, faint amusement]`. So a v3 or
v4 model counts as `direction: true`, and the family sends Acervo's direction as one leading tag,
`[<direction>] <text>`. Older models (multilingual v2, flash) are plain.

### Photos

**Google Cloud Vision only**, with 1,000 photos a month free. Photo capture needs every word's
outline, which a vision language model does not return reliably, and RapidOCR was measured on the NAS
and lost ([`../features/photo-capture.md`](../features/photo-capture.md)). Vision takes an API key or
the credentials file.

### Left out, and why

- **Hume.** It shuts down its TTS API on 13 Nov 2026.
- **Amazon Polly.** Its generative engine covers 11 languages, and its free allowance lasts 12 months.
- **fal, Replicate, Black Forest Labs, Stability.** Each needs its own asynchronous adapter, and none
  has a free tier worth the adapter.
- **ComfyUI.** A1111 is the simpler local API.
- **A local voice that takes a direction.** Qwen3-TTS (`instruct`, 10 languages, Apache-2.0) and
  CosyVoice 3 are realistic on an Apple Silicon Mac and not on the NAS's CPU, and neither ships a
  server. Anyone who runs one behind an OpenAI-style speech server can add it as that family with
  `direction` on. Acervo does not build or pin that server.

## The zero-cost set

This is the guide's first page: the fewest accounts that cover every kind, at no cost.

| Kind | Order |
|---|---|
| Text | Gemini API Flash-Lite → Groq → Cloudflare → Ollama, if there is one |
| Pictures | Cloudflare (FLUX.2 klein 4B, or FLUX.1 schnell for more a day) |
| Clear voice | Google Cloud TTS WaveNet → Kokoro on the NAS, if there is one |
| Expressive voice | Gemini API TTS and ElevenLabs v4. S4b decides which comes first. When both are spent, the expressive order already falls back to the clear voice. |
| Photos | Google Cloud Vision |

That set is four accounts: Google AI Studio, Google Cloud with billing enabled, Cloudflare and
ElevenLabs. Groq is optional. Steady use, about 100 words a day, sits well inside every
character-metered allowance. The directed voice is the scarce one, which is why it has two providers
and a fall-back.

## Keys

- **A key is typed once and never comes back.** The interface sends it to the server once. From
  then on the server shows only its first and last four characters, the one exception
  `GET /models` already makes.
- **Keys live in a secrets file beside the database, not in it.** The file is
  `providers.secrets.json`, mode 600, owned by the server's user, and it holds keys and uploaded
  credential files keyed by provider id. Keeping it out of SQLite means a database backup, a deploy's
  backup copy and an export bundle never carry a key. A lost secrets file costs re-entering the keys,
  and keys can be created again; that is the right way round. The off-machine export in
  [`backups.md`](backups.md) leaves it out by construction.
- **Saving a key makes one call that spends nothing**, such as a model list or a voice list, and says
  plainly whether the key works, and as whom where the provider says. A key that is refused is shown
  as a mistake to fix. It is never routed around.
- **Google Cloud takes an API key or a credentials file.**
  - **A key:** Cloud TTS (`text:synthesize`) and Cloud Vision (`images:annotate`) both take `?key=`,
    so voices and photos need no file. Use a key restricted to those two APIs.
  - **The file:** a service account or a user login, uploaded through the form. It adds Vertex text
    and pictures, and it is the only way for someone whose organisation blocks key creation
    ([`../operations/vertex-setup.md`](../operations/vertex-setup.md)).
  - **Checked in S4** (6 Nov 2026), with a key restricted to Cloud TTS and Vision on a trial
    account: WaveNet, Chirp 3 HD and Vision answer; a Gemini voice on Cloud TTS is refused, because
    it runs on Vertex. Gemini voices with a key are the Gemini API family's. A Vertex express-mode
    key could not be tried: an account that has used Google Cloud cannot have one.
  - **Checked in S1** (5 Nov 2026): Google's `voices.list` lists the 30 Gemini voices under plain
    names (`Kore`) with their gender, but only under `en-US`, so it cannot say which locales they
    accept. A Gemini voice refuses `es-AR` and a bare `es` and accepts `es-419` and `es-US`. Acervo
    therefore sends a voice that speaks any locale the nearest one Google lists any voice under
    (`es-US` for Argentina), unless locales are typed on the model.
  - **Credentials per provider:** each Google Cloud provider holds its own credential, which replaces
    the one process-wide default in `google_auth.py`.
- **Ways that stop existing:** `--configure-llm`, `llm.env` and `ACERVO_TEXT_CHAIN`, along with the
  variable lists in compose. Settings is the only way to add a key.

## Settings ▸ Providers

Built in S2 and S3 ([`../features/settings.md`](../features/settings.md) §8). What the mock-ups show
and is left for later:

- **The new families** (S4): OpenAI's own speech and pictures. "Add a provider" lists whatever
  families the server has, so each appears there when it is built.

## What goes away

- `models/catalogue.json`, with its hardcoded voices, `accepts` lists and `defaultChains`.
- `llm.env`, `deploy/acervo/llm.env.example`, `--configure-llm` and its flags, `ACERVO_TEXT_CHAIN`,
  and the provider variables in `compose.yaml` and `run-worker.sh`.
- `cloudflare.py`'s own read of `CLOUDFLARE_ACCOUNT_ID`, and the process-wide Google credential.
- The check in `install.sh` that refuses a variable the release's catalogue does not name.

**The encoder and the segmenter stay pinned files.** They are not providers: a changed encoder means
a recomputed map.

**Laptop tools** are the scripts, the experiments and the live tests. They read a gitignored
`providers.local.json` in the shape the server stores, with keys inline. The server never reads it.

**The clip service stops holding keys.** Today its container imports `acervo.models` and calls
providers itself with the keys compose hands it. Instead it asks Acervo for each text call, the way
LexiBeat's writer already does through `POST /loops/write`
([`../features/loops.md`](../features/loops.md), "The writer calls home, like the voice"). Acervo
walks the owner's chain and answers, so keys live in one container.

**Crossing over.** The new tables are additive, so a throwaway converter creates them and re-stamps
the head, and the vocabulary survives. The owner then adds their providers again in Settings and
picks the orders and voices once more. Nothing reads the old ids.

## Sessions

1. **S1 · The provider store.** *Built, with S5; deploys with S2.* The orders' default now includes
   every voice in the clear order, the Gemini voices last, where `defaultChains` held only WaveNet and
   Standard; the expressive default holds only voices that take a direction.
   - The families registry, covering today's families only (OpenAI-compatible through LiteLLM,
     Google Cloud, Cloudflare).
   - The providers table, the secrets file, and `models/` taking rows instead of reading the
     environment.
   - Routes to add, change, check and remove a provider, and `GET /models` reshaped.
   - The converter, `providers.local.json`, and the deploy path removed.
   - Behaviour is otherwise unchanged. The owner re-adds Gemini, Google Cloud and Cloudflare, and
     everything answers as before.
2. **S2 · Settings.** *Built, and deploys with S1.* The provider list, Add a provider, the
   provider's sub-page, the key check, and the model and voice pickers from the provider's own lists
   (`GET /providers/{id}/models` and `/voices`).
3. **S3 · Usage.** *Built* ([`../architecture/models.md`](../architecture/models.md), "Usage"): the
   counters, the sink, the route and the two Usage pages.
4. **S4 · New families.** Gemini API TTS, ElevenLabs and a speech server on OpenAI's route, tried
   with Kokoro, and Draw Things (*built*, [`../architecture/models.md`](../architecture/models.md)).
   Azure (plain voices) and Forge or A1111 are built from their references and not yet tried: the
   owner's Azure account cannot create the resource, and there is no GPU machine. Left: OpenAI's own
   speech and images. Each one is tried on Acervo's own prompts before the
   guide recommends it, and every failure it adds shows in `admin log` with its sentence.
5. **S4b · ElevenLabs as the free directed voice.**
   - Put v4 and v3 in the expressive order beside Gemini API TTS.
   - Record a fixed set: words, sentences, accent directions (es-ES, es-AR) and story directions.
     The owner rates it blind on the tablet, with the `experiments/pronunciation-encoding/`
     apparatus and its own scoring page.
   - Work out what 10,000 credits a month buy in words, sentences and passages.
   - The result decides the zero-cost set's expressive order.
6. **S5 · The clip service calls home.** *Built in S1*, so that removing `llm.env` did not leave
   the clip service without a provider: `POST /companion/text`, authenticated by the operator token,
   walking the providers' own order.
7. **S7 · Ready-made models.** *Later; asked for by the owner on 6 Nov 2026, not designed yet.* Adding
   a popular provider should be the account and nothing more: for Google Cloud, a project and a key or
   a credentials file, and every kind it reaches arrives configured. Today each model is added by hand,
   and a voice's direction switched on by hand.
   - Each family that has an obvious set names it, in code beside its other facts: which models per
     kind, which voices take a direction, and the free allowance where it is published. For Google
     Cloud, Flash-Lite text and Gemini image on Vertex, WaveNet, Chirp 3 HD and Gemini-TTS voices,
     and document text detection.
   - The add form offers it with one switch, on by default, saying what it adds. A model the
     provider's own list no longer holds is left out rather than added, so a set that ages costs a
     missing model and never a broken one. Kinds only a credentials file reaches come only with the
     file.
   - The page stays as it is afterwards: the set is where a provider starts, not a mode it is in.
8. **S6 · The guide.**
   - Write `docs/providers.md`, which leads with the zero-cost set, then the popular paid providers,
     then local models. Each provider gets how to sign up, which key to create, what the free
     allowance means in words and pictures a day, and where to paste it.
   - Say where a Google credentials file is and how to reach it. Your own sign-in is
     `~/.config/gcloud/application_default_credentials.json`, in a folder a file dialog hides. In the
     macOS dialog, ⇧⌘G opens a typed path and ⇧⌘. shows hidden folders. On an iPad, or anywhere the
     dialog cannot reach it, copy the file on the Mac (`pbcopy < ~/.config/gcloud/application_default_credentials.json`)
     and use **Paste…** on the Google Cloud page.
   - Add a short README section linking to it.
   - Rewrite `docs/architecture/models.md` for the store.
   - Fold `vertex-setup.md` and `cloudflare-workers-ai.md` into the guide.
   - Delete this plan, once S7 is built or moved to a plan of its own.
