# Providers: the models Acervo calls, and how to add them

Acervo writes entries, draws pictures, records words and reads photos by calling models that other
companies run, or that you run yourself. Each account you give it is a **provider**. You add one in
**Settings ▸ Providers ▸ Add a provider**: choose the company, paste a key, and press **Check and
add**. Acervo makes one call that costs nothing to check the key and tells you plainly whether it
works. Nothing is edited in a file, and nothing is redeployed.

Acervo needs six kinds of work done:

| Kind | Used for |
|---|---|
| Text | Writing an entry, the chat under it, choosing clips, writing stories |
| Quick text | Looking up a tapped word, which has to answer within a second or two |
| Pictures | A picture for each meaning, and for each part of a story |
| Clear voice | Reading a word, a definition or an example evenly |
| Expressive voice | Reading an example or a story with feeling, following a direction |
| Photos | Finding the words on a photographed page |

**There are two ways to start.** One account does everything, for a small bill. Or several free
accounts together cost nothing, at the price of setting up four of them.

---

## The quick way: Google Cloud does everything

One Google Cloud account covers all six kinds: Gemini text and pictures through Vertex AI, WaveNet,
Chirp 3 HD and Gemini voices through Cloud Text-to-Speech, and Cloud Vision for photos. It is the
set Acervo is used with every day.

**What it costs.**
- **Within a monthly free allowance:** WaveNet voices are free up to 4 million characters a month,
  Chirp 3 HD up to 1 million, and Cloud Vision up to 1,000 photos. For a vocabulary, that is
  effectively free.
- **Paid by use:** text, pictures and the Gemini voices.
- **Trial credit:** a new Google Cloud account gets one, which covers months of steady use.
- **Watching it:** your spending is on the **Billing** page of the Google Cloud console. Settings ▸
  Providers ▸ Usage shows what Acervo has asked for.

### 1. A project with billing

1. Sign in at [console.cloud.google.com](https://console.cloud.google.com) and create a project, or
   use the one it made for you. The project ID is shown in the project picker at the top.
2. Go to **Billing** and check that a billing account is linked to the project. A trial account has
   one. Vertex answers every call from a project without billing with a refusal that does not say
   why.

### 2. Turn on the three APIs

In **APIs & Services ▸ Library**, open each one and press **Enable**:

- **Vertex AI API**: text and pictures.
- **Cloud Text-to-Speech API**: voices.
- **Cloud Vision API**: photos.

Or from a terminal, with [gcloud](https://cloud.google.com/sdk/docs/install):

```bash
gcloud services enable aiplatform.googleapis.com texttospeech.googleapis.com vision.googleapis.com \
  --project=PROJECT_ID
```

### 3. A credentials file

Vertex AI accepts a credentials file and not a plain key, so this path needs one. There are two
kinds of file, and Acervo takes either.

**Your own sign-in** is the quickest, and right on a computer with one Google account:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID
```

This writes `~/.config/gcloud/application_default_credentials.json`. The file does not say which
account wrote it, so Acervo can say only that it "works with your own sign-in".

**A service account** names its account every time the key is checked. Use one on a server, or on a
computer with more than one Google login:

1. **IAM & Admin ▸ Service accounts ▸ Create service account.** Name it `acervo`, and give it the
   single role **Vertex AI User** (`roles/aiplatform.user`). Nothing broader is needed.
2. Open the account, go to **Keys ▸ Add key ▸ Create new key ▸ JSON**, and keep the file that
   downloads. Google does not keep a copy.
3. **If Create is refused with a policy error,** your organisation blocks service-account keys.
   Google switches this on for new organisations, including the one made behind a personal
   account. Turn it off for this one project:

   ```bash
   gcloud resource-manager org-policies describe \
     iam.disableServiceAccountKeyCreation --effective --project=PROJECT_ID   # enforced: true means blocked
   gcloud resource-manager org-policies disable-enforce \
     iam.disableServiceAccountKeyCreation --project=PROJECT_ID
   ```

   This needs the **Organization Policy Administrator** role. If the organisation appeared on its
   own with your personal account, you can grant it to yourself:
   `gcloud organizations add-iam-policy-binding ORG_ID --member="user:address@gmail.com"
   --role="roles/orgpolicy.policyAdmin"` (`gcloud organizations list` shows `ORG_ID`). In the
   console the same switch is in **IAM & Admin ▸ Organization policies**. Check the resource picker
   at the top shows *your project*, not the organisation. Then open *Disable service account key
   creation*, choose **Manage policy ▸ Override parent's policy**, add a rule with **Enforcement:
   Off**, and **Set policy**. You can turn the block back on once the key is made: that stops new
   keys, not this one.

### 4. Add it

In **Settings ▸ Providers ▸ Add a provider**, choose **Google Cloud**, then **Credentials file**:

- **Choose…** the file. Your own sign-in is in a folder the macOS file dialog hides: press **⇧⌘G**
  and type `~/.config/gcloud/`, or press **⇧⌘.** to show hidden folders.
- **Paste…** works anywhere the dialog cannot reach, such as an iPad. Copy the file on the Mac with
  `pbcopy < ~/.config/gcloud/application_default_credentials.json`, then paste it on the Google
  Cloud page.
- Fill in the **project**, and leave **location** at `global`: the Gemini picture models are not
  found in a named region.
- Leave **Add the usual models** on. The provider then starts with Gemini text and pictures, WaveNet
  and Chirp 3 HD voices, two Gemini voices that take a direction, and photo reading, each in the
  order Acervo uses them. You can change any of it on the provider's page afterwards.

**Check and add** says whose file it is, or "Works with your own sign-in".

### Google Cloud with a key instead

A plain API key reaches **voices and photos only**: WaveNet, Chirp 3 HD, Standard and Cloud Vision.
It does not reach Vertex AI, or the Gemini voices, which run on Vertex. A key does not need the
credentials file, and a trial account can create one.

1. **APIs & Services ▸ Credentials ▸ + Create credentials ▸ API key.**
2. Open the key. Under **API restrictions**, choose **Restrict key**, tick **Cloud Text-to-Speech API**
   and **Cloud Vision API**, and **Save**.
3. In Acervo, add **Google Cloud** with **API key**. The usual models it adds are the voices and
   photo reading.

With a key, Gemini voices come from the **Gemini API** provider below.

---

## At no cost

No single free account covers everything, but four do between them:

| Kind | Free providers, in the order to put them |
|---|---|
| Text | Gemini API → Groq → Cloudflare, and a model on your own computer if you have one |
| Pictures | Cloudflare, or Draw Things on a Mac |
| Clear voice | Google Cloud with a key (WaveNet) → Kokoro on your own computer |
| Expressive voice | Gemini API → ElevenLabs |
| Photos | Google Cloud with a key (Cloud Vision) |

That is four accounts: Google AI Studio (the Gemini API), Google Cloud with billing enabled, which
stays within its free allowances, Cloudflare, and ElevenLabs. Groq is optional. Each section below
says what its free allowance means in words and pictures.

### Gemini API: text, and voices that take a direction

1. Sign in at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and **Create API
   key**. No card is needed.
2. In Acervo, add **Gemini API** with the key, and leave **Add the usual models** on. It adds Gemini
   3.5 and 3.1 Flash-Lite for text, and 3.8 Flash TTS and 3.8 Flash-Lite TTS for voices.

**Free allowance:**
- **Text:** about 500 requests a day for each Flash-Lite model, so about 1,000 between the two. One
  entry takes two.
- **Voices:** three requests a minute for each speech model, and 10 a day (Google's own refusal on
  3.8 Flash-Lite TTS, 7 Nov 2026). That is a few words a day, not a vocabulary. Your own numbers are
  on AI Studio's [rate limit page](https://aistudio.google.com/rate-limit).
- **When it runs out:** Acervo waits as long as Google says and moves to the next provider in the
  order meanwhile.

The voices speak about a hundred languages, and many have voices made for a country (Argentine,
Mexican and Castilian Spanish, for example). A voice made for a country is offered first for that
accent.

### Cloudflare: text, pictures and an English voice

1. Open the [Workers AI dashboard](https://dash.cloudflare.com/?to=/:account/ai/workers-ai), choose
   **Use REST API ▸ Create a Workers AI API Token**, keep the template it fills in, and copy the token
   when it is shown. Cloudflare shows it once.
2. Copy the **Account ID** from the same page (or press `⌘K` and choose *Copy account ID*).
3. In Acervo, add **Cloudflare** with both. **Add the usual models** adds Llama 3.3 70B for text,
   FLUX.2 klein for pictures, and Aura, an English voice.

**Free allowance:** 10,000 "neurons" a day, reset at midnight UTC. That is about **95 pictures a
day** with FLUX.2 klein at 1024×1024, or about 170 with FLUX.1 schnell. Do not use the account's
global API key or an AI Gateway token: only a Workers AI token works.

### Google Cloud with a key: clear voices and photos

As described [above](#google-cloud-with-a-key-instead). Cloud Text-to-Speech and Cloud Vision ask
for a billing account even within their free allowance, but at 4 million WaveNet characters and
1,000 photos a month, a vocabulary does not reach the end of it.

### ElevenLabs: an expressive voice

1. Sign up at [elevenlabs.io](https://elevenlabs.io), with no card, and create a key under
   **Developers ▸ API keys** with access to text to speech, voices and user.
2. In Acervo, add **ElevenLabs** with the key. **Add the usual models** adds Eleven v4 and v3, which
   both take a direction.

**Free allowance:** 10,000 credits a month, for non-commercial use, with attribution. One credit is
one character, and that includes the direction. Acervo therefore sends ElevenLabs a short tag,
the feeling and the accent ("surprised and amused; accent from Argentina"), not the full direction
sentence it sends Gemini, which ElevenLabs reads aloud. It sends nothing for an accent alone,
which made a short word or phrase be said twice. A month buys about:

| Recording | Credits | A month |
|---|---|---|
| A word, read evenly | ~7 | ~1,400 |
| A sentence, with a feeling | ~95 | ~100 |
| A story passage, with a feeling | ~440 | ~20 |

So ElevenLabs is worth keeping for expressive sentences, behind the Gemini API in the expressive
voice's order. The free plan's voices are general ones, and their accent is their own.

### Groq: fast text

Create a key at [console.groq.com/keys](https://console.groq.com/keys) and add **Groq**. **Add the
usual models** adds gpt-oss 120B and Qwen 3.8 27B. The free allowance is per model and per day,
about 1,000 requests on the larger models; your own numbers are on Groq's console.

### OpenRouter

One key in front of many models, some of them free (their ids end in `:free`): about 50 requests a
day, or 1,000 once you have bought 10 credits. Create a key at
[openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) and add **OpenRouter**, then choose
its models on the provider's page.

---

## Paid text providers

**OpenAI, Anthropic, Mistral and DeepSeek** are added the same way: a key from the provider's own
console, then the models you want, chosen from the provider's list on its page. They have no usual
set in Acervo, because none has been measured on Acervo's own prompts, so you choose the models.
Each provider page links to where the key is made and where the bill is read.

**Any compatible service** is anything that answers OpenAI's chat route. Give its address, a key if
it wants one, and whether it understands JSON mode.

---

## On your own computer

A model on your own computer costs nothing per use, and the words never leave your network. **The
server calls the address you give**, so `localhost` means the machine the Acervo server runs on. For
a model on your Mac with the server on another machine, give the Mac's address on your network or
your tailnet. The program on the Mac must also accept connections from other machines, not only
from the Mac itself.

### Ollama and LM Studio: text

Add **Ollama** (`http://localhost:11434`) or **LM Studio** (`http://localhost:1234/v1`), then choose a
model from what it has downloaded.

### A speech server: Kokoro or Piper

[Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) runs in Docker and answers on port 8880:

```bash
docker run -d --name kokoro -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

Add **Speech server** with its address (`http://localhost:8880/v1` by default). **Add the usual
models** adds `kokoro`. Its 72 voices are English, Spanish, French, Hindi, Italian, Japanese,
Brazilian Portuguese and Mandarin. A voice's name says its language (`ef_dora` is a Spanish woman's
voice), and a language none of them speaks is never asked of it. On a Mac's processor a word takes
about a second. Piper, served by [Speaches](https://speaches.ai), is added the same way.

### Draw Things: pictures on a Mac

1. Install [Draw Things](https://drawthings.ai) from the App Store.
2. In its settings, turn on **API Server**, with HTTP on port 7860. Leave *bridge mode* off: it sends
   the drawing to Draw Things' own servers.
3. Download a model in the app. On an M1 with 16 GB, **SDXL Turbo (8-bit)** draws a 512×512 picture
   in about 9 seconds, and 20 for the first one after the model loads.
4. Add **Draw Things**. The check says which model is loaded, and that is the model to add.

A fast model (Turbo, Lightning, schnell, klein) is sent the four steps it is made for. Any other
model draws with the steps and guidance set in Draw Things' own window.

### Not yet tried with Acervo

These two are written from the provider's own documentation, and no real call has been made through
them yet. The key check when you add one is that first call, and it says in the provider's words
what is wrong.

- **Forge or A1111**, on a computer with a graphics card: start it with `--api` and add its address.
- **Azure Speech**: in [portal.azure.com](https://portal.azure.com), create a **Speech service**
  resource on the **Free F0** tier (S0 bills). Then copy **Key 1** and the **region** (such as
  `westeurope`) from its **Keys and Endpoint** page. Its free allowance is 500,000 characters a
  month, in over a hundred languages, with no direction.

---

## Orders

Each kind has an **order**: the providers and models to ask, first to last. Until you choose one,
the order is the providers in the order you added them, and each provider's models in the order
they were added. **Settings ▸ Providers** shows each order, and you can rearrange it.

- **When a model is busy or has spent its free allowance,** the next one is asked. The same happens
  when a model is down or gives an answer Acervo cannot use. So two free models with 500 requests a
  day each are 1,000 between them.
- **A refused key stops the order** and is shown as a mistake to fix. Acervo never routes around a
  wrong key, because that hides the mistake and spends another provider's allowance.
- **The expressive voice's order holds only voices that take a direction.** When all of them are
  spent, the clear voice reads instead.

**Settings ▸ Providers ▸ Usage** counts what each model has been asked for, today and this month,
against its free allowance where one is set.

---

## For whoever runs the server

The providers, their keys as first and last four characters, and what each last check said, without
spending anything:

```bash
docker exec acervo-server-1 python -m acervo.admin providers
```

**Keys are kept** in `providers.secrets.json` beside the database, readable only by the server, and
never in the database. A database backup or an export therefore never carries a key. A lost secrets
file costs entering the keys again.

**To replace a key,** use **Replace** on the provider's page. The new key is checked before the old
one is let go. **To revoke one,** delete it at the provider. Acervo's next call is refused, and the
check says so in the provider's words.

**Laptop tools** — the scripts, the experiments and the live tests — read a gitignored
`providers.local.json` in the repository, in the server's shape with each key inline:

```json
{"providers": [
  {"id": "gemini-api", "family": "gemini-api", "key": "…",
   "models": {"text": ["gemini-3.5-flash-lite"], "audio": [{"id": "gemini-3.8-flash-tts", "direction": true}]}},
  {"id": "vertex", "family": "google-cloud", "credentials": "~/.config/gcloud/application_default_credentials.json",
   "settings": {"project": "PROJECT_ID"}, "models": {"text": ["gemini-3.8-flash"]}}
]}
```

One real call per kind and every key check, against those providers. It costs a little, and a
provider with no key is skipped:

```bash
RUN_LIVE_MODEL_TESTS=true .venv/bin/python -m pytest tests/integration/test_models_live.py
```

How providers work inside Acervo is in [`architecture/models.md`](architecture/models.md).
