# Setting up Vertex AI for Acervo

Vertex is reached through a **Google Cloud** provider signed in with a credentials **file**: Google
will not authenticate Vertex from a value through LiteLLM. An API key on the same provider reaches
Cloud Text-to-Speech and Cloud Vision but not Vertex. The file is uploaded in Settings ▸ Providers,
kept in the server's secrets file beside the database, and handed to each Vertex call with the
provider's project and location.

There are two shapes of that file and Acervo accepts both. This page walks each one end to end.

---

## §01 · Which one to use

|  | Application default credentials | Service-account key |
|---|---|---|
| What it is | The file `gcloud auth application-default login` writes on your machine | A JSON file that authenticates as a non-human identity in your project |
| Unlocking needed | None | One organization-policy override |
| Says whose account it is | **No** — it has an `account` field and leaves it empty | **Yes** — `client_email` |
| Settings ▸ Providers shows | "Works with your own sign-in" | "Works as" the service account |
| Good for | A workstation, and getting going quickly | A server, and any machine that holds more than one Google login |

**Pick the key if you can.** Application default credentials are simply whichever Google login was
signed in last, so on a machine that also holds a work account, "which account is Acervo spending?"
can change without anything in Acervo changing. A service account's key answers that question:
the provider's check says which account it is, every time it is checked.

Everything below uses `PROJECT_ID` for your project and
`acervo-vertex@PROJECT_ID.iam.gserviceaccount.com` for the service account. Substitute your own.

---

## §02 · Once, whichever path you pick

### Enable the Vertex AI API

**Console** → [console.cloud.google.com/apis/library/aiplatform.googleapis.com](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com)
→ check the project selector at the top is your project → **Enable**.

**Command line**

```bash
gcloud services enable aiplatform.googleapis.com --project=PROJECT_ID
```

To check it is already on:

```bash
gcloud services list --enabled --project=PROJECT_ID | grep aiplatform
```

### Enable Cloud Text-to-Speech, which is what says the words

A different API from Vertex on the same project and the same credentials, and it is what reads a
headword or an example aloud. Standard and WaveNet voices have a permanent free allowance far above
what a vocabulary needs; the Gemini voices, which take a delivery direction, are billed with
everything else.

**Console** → [console.cloud.google.com/apis/library/texttospeech.googleapis.com](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
→ **Enable**.

**Command line**

```bash
gcloud services enable texttospeech.googleapis.com --project=PROJECT_ID
gcloud services list --enabled --project=PROJECT_ID | grep texttospeech
```

Cloud TTS refuses a *user* login that names no quota project, which is what Step 2 of Path A sets —
so if speech says the project is missing while Vertex is happy, that is the setting to check. Acervo
sends the provider's project as the quota project on every speech call for the same reason.

To hear that it works, before Acervo is involved at all:

```bash
curl -s -X POST https://texttospeech.googleapis.com/v1/text:synthesize \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "x-goog-user-project: PROJECT_ID" -H "Content-Type: application/json" \
  -d '{"input":{"text":"picar"},"voice":{"languageCode":"es-ES","name":"es-ES-Wavenet-F"},
       "audioConfig":{"audioEncoding":"MP3"}}' \
  | python3 -c 'import base64,json,sys;open("picar.mp3","wb").write(base64.b64decode(json.load(sys.stdin)["audioContent"]))'
afplay picar.mp3
```

### Make sure the project has billing

Vertex is paid. A project with no billing account answers every call with a 403 that does not say
so in those words.

**Console** → [console.cloud.google.com/billing](https://console.cloud.google.com/billing) → pick
your project → confirm a billing account is linked.

---

## §03 · Path A — the file you already have

Fastest, nothing to unlock, and the right choice on a laptop with one Google login.

**Step 1.** Sign in. This opens a browser and writes
`~/.config/gcloud/application_default_credentials.json`.

```bash
gcloud auth application-default login
```

**Step 2.** Point it at the project whose quota you want to spend.

```bash
gcloud auth application-default set-quota-project PROJECT_ID
```

**Step 3.** Add it to the server — §05.

> **What this file will not tell you.** Open it and you will see `"account": ""`. Google does not
> record which login wrote it, so Acervo cannot say whose account the server is spending. If that
> matters to you, use §04 instead.

---

## §04 · Path B — a service-account key

Six steps. Step 4 is the one the console explains badly.

### Step 1 · Create the service account

**Console** → [console.cloud.google.com/iam-admin/serviceaccounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
→ **Create service account** →

- **Service account name**: `Acervo Vertex`
- **Service account ID**: `acervo-vertex` (fills itself in)
- **Create and continue**

**Command line**

```bash
gcloud iam service-accounts create acervo-vertex \
  --display-name="Acervo Vertex" --project=PROJECT_ID
```

### Step 2 · Give it permission to call Vertex

Still in the create flow, at **Grant this service account access to the project**:

- **Role** → type `Vertex AI User` → pick it
- **Continue** → **Done**

`roles/aiplatform.user` is the whole grant. Do not give it Editor or Owner: this identity only ever
generates text, pictures and speech.

**Command line**

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:acervo-vertex@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

To check what it already holds:

```bash
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:acervo-vertex@PROJECT_ID.iam.gserviceaccount.com" \
  --format="value(bindings.role)"
```

### Step 3 · Find out whether key creation is blocked

Google applies a set of secure-by-default policies to new organizations — including the one created
automatically behind a personal Google account — and one of them switches off service-account keys
entirely. It is inherited by every project, and the symptom is a **Create** button that refuses
with a policy error.

```bash
gcloud resource-manager org-policies describe \
  iam.disableServiceAccountKeyCreation --effective --project=PROJECT_ID
```

`enforced: true` means blocked. Do step 4. `enforced: false`, or a `NOT_FOUND`, means skip to step 5.

### Step 4 · Turn the block off for this one project

You need `roles/orgpolicy.policyAdmin`. If you created the organization — which you did if it
appeared on its own with your personal account — you have it. Check:

```bash
gcloud organizations list
gcloud organizations get-iam-policy ORG_ID \
  --flatten="bindings[].members" --filter="bindings.members:learner@account.example.com" \
  --format="value(bindings.role)"
```

**Command line — one command, project scope only**

```bash
gcloud resource-manager org-policies disable-enforce \
  iam.disableServiceAccountKeyCreation --project=PROJECT_ID
```

**Console** — this is the path that is easy to get lost in, so it is spelled out:

1. Go to [console.cloud.google.com/iam-admin/orgpolicies](https://console.cloud.google.com/iam-admin/orgpolicies).
2. **Check the resource selector at the very top of the page.** It usually opens on the
   organization. Click it and choose **your project**. Setting the policy on the organization works
   too but turns keys on everywhere, which is not what you want.
3. In the filter box type `Disable service account key creation`.
4. Click the constraint's name to open it.
5. **Manage policy**.
6. Choose **Override parent's policy**.
7. **Add a rule** → **Enforcement: Off**.
8. **Set policy**.

The change takes effect within a minute or two.

> **Scope, on purpose.** Overriding at project level leaves every other project of yours protected.
> This is the smallest change that unblocks Acervo.

The following sequence of commands might also be required to get Organization Policy Administrator (`roles/orgpolicy.policyAdmin`) on the organization:

```bash
% gcloud organizations add-iam-policy-binding ORG_ID \
  --member="user:address@gmail.com" \
  --role="roles/orgpolicy.policyAdmin"
% gcloud organizations get-iam-policy ORG_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:address@gmail.com" \
  --format="value(bindings.role)"
...
roles/orgpolicy.policyAdmin
% gcloud resource-manager org-policies disable-enforce \
  iam.disableServiceAccountKeyCreation \
  --project=PROJECT_ID
```

### Step 5 · Create and download the key

**Console** → [console.cloud.google.com/iam-admin/serviceaccounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
→ click `acervo-vertex@…` → **Keys** tab → **Add key** → **Create new key** → **JSON** → **Create**.

The file downloads immediately and **is not stored by Google**. If you lose it, you create another
one; you cannot download this one again.

**Command line**

```bash
gcloud iam service-accounts keys create ~/acervo-vertex.json \
  --iam-account=acervo-vertex@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
chmod 600 ~/acervo-vertex.json
```

Move it somewhere outside any repository. It is a credential; never commit it.

> A key already listed under **Keys** with a two-year expiry that you cannot download is a
> Google-managed key. It is not the one you want and it is not usable here. `--managed-by=user` on
> `gcloud iam service-accounts keys list` shows only the downloadable ones.

### Step 6 · Optionally, turn the block back on

The constraint stops keys being **created**. Re-enforcing it does not revoke or disable the key you
just downloaded, so you can close the door behind you:

```bash
gcloud resource-manager org-policies enable-enforce \
  iam.disableServiceAccountKeyCreation --project=PROJECT_ID
```

Remember you will have to turn it off again to rotate the key.

---

## §05 · Adding it

In **Settings ▸ Providers**, add **Google Cloud**, choose *Credentials file*, and upload the file —
`~/acervo-vertex.json` for a key (path B), or `~/.config/gcloud/application_default_credentials.json`
for your own sign-in (path A). Fill in the project, and leave the location at `global`: the Gemini
image models 404 in a named region. Saving checks the file with a call that spends nothing and says
whose it is; then add the Vertex models — `gemini-3.8-flash` for text, `gemini-3.1-flash-lite-image`
for pictures — and put them in the orders on the same page.

Nothing about this is deployment configuration: no file to send, no variable, no deploy.

---

## §06 · Checking it

The provider's page says what its last check said. On the server, the same reading, spending nothing:

```bash
sudo docker exec acervo-server-1 python -m acervo.admin providers
```

### When the check says no

| What it says | What to do |
|---|---|
| `…needs its project` | Fill in the project on the provider's page. |
| `…refused this key` with Google's sentence | The file was revoked, or the account lacks the Vertex AI User role (§04). |
| `Vertex AI API has not been used in project …` | Enable the API (§02). |

### One real call per kind

Gated, costs money, reads this machine's `providers.local.json`, and skips a provider with no key:

```bash
RUN_LIVE_MODEL_TESTS=true .venv/bin/python -m pytest tests/integration/test_models_live.py
```

---

## §07 · Rotating and revoking

**Rotate.** Create a second key (§04 step 5), deploy it, then delete the first:

```bash
gcloud iam service-accounts keys list \
  --iam-account=acervo-vertex@PROJECT_ID.iam.gserviceaccount.com --managed-by=user
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=acervo-vertex@PROJECT_ID.iam.gserviceaccount.com
```

**Revoke.** Delete the key, or disable the service account. Vertex then reports `no` with a reason,
and **the chain is not damaged**: a pair whose provider has no credential keeps its place in the
owner's order and is passed over, so the next provider answers and putting the key back restores the
order exactly as it was. A rotated credential must never be able to destroy a choice.

**Where the file lives on the server.** `$ACERVO_ROOT/credentials/google.json`, mode 600, mounted at
`/run/acervo/credentials/google.json` read-only in both the server and the worker. Deleting it and
re-deploying is a clean way to go back to having no Vertex at all.
