# Spoken clips · how Acervo uses the retrieval corpus

**Built.** How the tuning went is [`clip-selection-rounds.md`](../research/clip-selection-rounds.md) and
[`experiments/clip-translation/`](../../experiments/clip-translation/README.md); what might come next
is [`../plans/clip-curation.md`](../plans/clip-curation.md).

A word's article can show what a word means, how it is used, and a picture of it. This is how it
also shows a native speaker saying it. The corpus is
[`spoken-usage-retrieval`](https://github.com/anton-dergunov/spoken-usage-retrieval), a separate
project; this document is how the two meet.

When a word is saved, Acervo asks the corpus what real speakers said, hands the messy answer to a
model, and stores at most one authentic clip per sense — or none, which is a good answer. The clip
renders as an example under the sense it illustrates, plays in place, and can be removed with one
button. Both repositories keep their own release cadence: Acervo names one version of the retrieval
service and upgrades it when it wants to.

---

## §1 · What the other repository gives

- A **corpus of timestamped caption segments** harvested from a curated channel list — mostly
  YouTube's automatic captions, which that repository measured as more verbatim and better aligned
  to the speech than creator-authored ones. The stored unit is a reconstructed utterance with its
  timing, its stable content-derived `segment_id`, the matched surface span with character offsets,
  the channel and video, the caption kind, and the reason the segment boundary fell where it did.
- **Morphological retrieval.** `match_mode=auto` unions surface and contiguous lemma matches, so
  `estar podrido de` retrieves `estoy podrido de`. Acervo's `lemma` field is exactly the key it
  wants.
- **A versioned HTTP contract** under `/api/v1`, snapshotted there as `docs/openapi-v1.json`:
  search, clips, status, statistics, channel CRUD behind an operator token, updates, and
  liveness/readiness.
- **A foreground CLI** that never daemonizes; the host owns process supervision. Acervo is that host.
- **`@spoken-usage-retrieval/react`** — `SpeechClipPlayer`, a typed client, and one stylesheet with
  `sur-player`-prefixed classes and documented CSS variables. It renders a bounded YouTube excerpt
  with its own transport, progressive source text, a direct-source fallback, keyboard control and a
  reduced-motion mode. **It deliberately owns no modal**: the host does.
- **Clip translation and word alignment**, as an asynchronous job with its own cache. Acervo uses
  the alignment only — §2.13 says why.

What it does not give, and this integration therefore does not use: audio, forced alignment of audio
to text, and any ranking model. Its `Clip.alignment_status` (audio timing) and its
`TranslationResult.alignment_status` (the word graph) are different things that share a word.

---

## §2 · The decisions

### 1 · Two repositories, one version pin

The retrieval repository has a wholly different lifecycle: it is a research project, its index is
regenerable by definition, and its interesting sessions are experiments rather than features. Acervo
is the thing with irreplaceable data. Vendoring its source, submoduling it, or letting Acervo's
build track its `main` would couple the two release cadences and make "regenerable" merely intended
rather than structurally true.

> **DECISION: the retrieval repository publishes tagged releases carrying two artifacts, and Acervo
> names one version in one tracked file.**
>
> A release is a git tag plus a Python wheel and an `npm pack` tarball attached to it. Acervo tracks
> `deploy/acervo/speech/pin.json` — the version, the tag, and a SHA-256 for each artifact, beside the
> Dockerfile that consumes it — and `scripts/fetch_speech.sh` downloads them into an untracked
> `vendor/speech/`, verifying the digests. Registry publication to PyPI and npm is a later choice
> that changes nothing here.

Upgrading is then one command and one edited file, and a build that cannot reach the pinned version
fails loudly instead of silently taking a newer one. The corpus therefore does not live in this
repository.

### 2 · A service beside Acervo, not a package inside it

The core's invariants ([`../README.md`](../README.md)) already forbid sharing: *the core and the corpus do not share a database, a
container, or a backup policy.* The retrieval service holds gigabytes of disposable read-only text
that must be full-text searched; the core holds tens of megabytes of precious relational data that
must sync to a phone.

> **DECISION: `speech-retrieval` is a long-running compose service, like `anki-sync-server`, and the
> Acervo server reaches it over HTTP only.**

The wheel is a **deployment artifact, not a code dependency**. Acervo's server image does not install
it, does not import `speech_retrieval`, and never opens its SQLite file. It talks to the pinned
`/api/v1` contract through a narrow hand-written client. That keeps `yt-dlp`, Stanza and the model
files out of Acervo's image entirely, and it means a retrieval version bump is a container swap
rather than a Python dependency resolution.

The npm tarball **is** a genuine code dependency: `web/` imports `SpeechClipPlayer` and the typed
client from it.

**The corpus is kept fresh by asking it over HTTP.** The server's nightly `corpus.update` step, or
Update now in Settings ▸ Clips, starts an update in the service and follows it
([`jobs.md`](../architecture/jobs.md)). The service is designed for this — it builds into a temporary
file and swaps it in with an atomic rename, while readers open a fresh read-only connection per
query — so an update adds videos without a restart, and a query that straddles the swap still sees
a consistent snapshot.

The update runs *inside* the serving container rather than in a second one, for a reason beyond
simplicity: the index records which analyzer built it and readiness *refuses* an index built by a
different analyzer version. One image that both builds and serves cannot drift; two images can, and
the symptom would be a service that reports itself unready after a routine rebuild. (The first
version reached it with `docker compose exec` from a cron line, for the same reason.)

### 3 · The cache is not the index, and only one of them is disposable

The captions downloaded from YouTube are the one thing here that cost bandwidth and cannot be
politely re-fetched at will. The index built from them is derived and rebuildable by design.

> **DECISION: two directories, mounted at two subpaths of the service's one data directory.**
>
> - `$acervo_root/data/speech-cache` → `…/data/raw` — immutable acquired input. **Nothing in either
>   repository deletes this.** Not `deploy.sh --reset-database`, not `--reset-anki`, not `reindex`,
>   not a version bump, not an image rebuild.
> - `$acervo_root/data/speech-index` → `…/data/index` and `…/data/derived` — rebuildable. Throwing
>   it away costs CPU and no traffic.

Host paths under `$acervo_root`, not named Docker volumes. Every existing mount takes its path from
the installer through a `"${HOST_PATH:-fallback}"` default, so a genuinely named volume would be the
first of its kind, would sit outside `$acervo_root`, and would be invisible to whoever is looking
after the machine. Both resets are then safe by construction rather than by care: `deploy.sh`
deletes nothing at all, and `install.sh` deletes three specific paths by name, none of them these.

The greenfield rule that development databases are disposable stops at the cache. It is the only
store in this deployment that is neither disposable nor reconstructible from something Acervo holds.
The deploy-time backup copies named files and will not touch it, which is correct for something this
size but means **the operator owns its backup** ([`../architecture/durability.md`](../architecture/durability.md)). Detecting videos deleted at the source, and pruning what they left behind, is the other
repository's problem and is not in scope.

### 4 · A clip is an `Example`, not a new record

`EXAMPLE_ORIGINS` already contains `subtitle`. `Example` already carries `videoRef`, `videoTitle`
and `videoStart`, `LexemeArticle.tsx` already draws a clip button, and `projection.py` already
hides the title and start when there is no reference. The model was designed for this and the
remaining work is three fields.

> **DECISION: a clip is an example with `origin: "subtitle"`.** It gains `videoEnd`, `videoChannel`
> and `clipRef` — the corpus's stable `segment_id` — and nothing else. No ninth table.

Provenance stays modelled rather than flagged, exactly as with attestations: the origin says where
the sentence came from and `clipRef` says which segment it is, so the stored text can be audited
against the corpus at any time. `videoRef` remains the field the invariants hang on — a title, a
start, an end, a channel or a `clipRef` without a video reference is refused, and the projection
hides them all when there is none.

The `matchedForm` invariant applies unchanged: the form must occur **verbatim** in the example text,
untrimmed and un-normalised. The corpus hands over `match.text` with code-point offsets into the
same sentence, so this holds by construction — and a candidate where it does not hold loses its
`matchedForm` rather than being stored with a lie.

### 4a · A clip example's id is derived, for the reason an image prompt's is

There are two writers here and they do not coordinate: the `enrich` job of the word you just saved,
and a backfill walking words that predate it. That is the same pair that draws pictures, and it is exactly why an `imagePrompt`'s id is a namespaced hash of its sense rather
than a random 15 characters — the lesson written into the data rules after a client that minted a
random one gave an imported sense two rows and *nothing failed*.

> **DECISION: a clip example's id is derived from `(senseId, clipRef)`**, by the same namespaced
> SHA-256 in base 36, implemented in both `src/acervo/clips/ids.py` and `web/src/ids.ts` and pinned
> against shared vectors from both sides — the shape `image_prompt_id` already has.

Two writers that pick the same segment for the same sense then converge on one row, and whichever
arrives second finds the work already done or is refused as stale. It also holds a sense to one
example per segment without a uniqueness constraint, which the replicated collections may not have.
A sense may still accumulate clips from *different* segments, which is correct: the pair is the
identity, not the sense alone.

Removal stays an ordinary tombstone — deliberately not `imagePrompt`'s `suppressed` field — and it
is safe only because §2.5 makes the search one-shot. A derived id means a later re-search that
re-selected the same segment would write at the tombstone's id and resurrect it. Nothing in this
work re-searches, so nothing can; a rescan must add a suppression field before it ships, exactly as
the image pipeline had to.

### 5 · The search happens after the save, never during the capture

> **DECISION: capture never consults the corpus.**

The first model call writes a clean article from the definition and the owner's own attestations.
Feeding it caption fragments would condition the whole entry on the messiest input in the system,
and the failure mode is invisible — a slightly worse definition, in every word, forever.

The order is deliberately the opposite: **write the article, then go looking for real speech that
matches the senses it already has.** The senses are the query's context, not its product. A word
whose corpus turns up nothing is a normal word with a normal article.

That also means the clip search is one-shot at save. Adding a channel does **not** re-scan the words
already held, and there is no rescan button — see §2.12.

### 6 · The corpus segments; the model only selects

> **DECISION: the stored example text is the corpus's sentence, verbatim. The model chooses; it
> never rewrites, trims or joins.**

Where a shown passage starts and ends is an open research question in the other repository (its
Plan 17 exists to answer it by blind human comparison). A model that quietly re-cut the passage here
would make every one of those measurements meaningless, and would break the audit in §2.4 — stored
text that no longer matches the segment it names.

### 7 · One text call per lexeme, at most one clip per sense, and none is a good answer

> **DECISION: one corpus search and one text call per lexeme.**

The search is the lexeme's `lemma`, falling back to its `headword`, in the lexeme's `language`, with
`match_mode=auto` and `order=ranked`, bounded to **20 candidates** (the API caps at 50). The
candidates go to the model with the article's senses, and the model returns for each sense either one
candidate id or nothing — with the translation of the clip it chose, which is §13.

The senses are described to the model the way `prompts/acervo_image_brief.md` describes them, and
for the reason that prompt learned the hard way: **the definition in the language being learned is
the authority, and the glosses are hints that can mislead.** A gloss is a rough handle chosen for
closeness, and judging a fragment against the gloss rather than the definition finds instances of
the English word instead of the Spanish one. Reuse that prompt's wording rather than inventing a
second phrasing of the same rule.

The model is the **last and best quality gate**, not the retrieval mechanism. The other repository
improves ranking with traditional IR because it has millions of segments and cannot afford a model
call per candidate; Acervo can afford exactly one call per word, and spends it where a frontier
model is genuinely better than a feature — reading a messy fragment and judging whether it is really
an instance of *this* sense.

Three things follow, and all three are the point:

- **Refusing is the default, not the failure.** The prompt must make "none of these are good enough"
  cheap to say. A thin corpus should produce articles with no clips, never articles with bad clips.
- **Every returned id is validated against the request's candidate map.** An id the request did not
  offer is dropped and counted, and the count is surfaced. Dropping rather than refusing the whole
  word is deliberate: a hallucinated id is a prompt bug to fix, and refusing the batch would throw
  away the good selections with it.
- **It runs on the owner's text chain**, through `acervo.models`, with the prompt as tracked text in
  `prompts/acervo_clip_select.md`. No new catalogue kind: this is a text call, and a separate kind
  would be a knob invented before a need.

The prompt itself is a research question of its own. Five informal readings of it are
[`clip-selection-rounds.md`](../research/clip-selection-rounds.md), the translation rewrite is measured in
[`experiments/clip-translation/`](../../experiments/clip-translation/README.md), and a labelled
experiment is designed and not yet run
([`../plans/clip-selection-experiment.md`](../plans/clip-selection-experiment.md)).

### 8 · The marker is a date, not a flag

Two questions need answering later: *which words have never been through this?* and *which words
were searched against a corpus that has since grown?* One field answers both.

> **DECISION: `clipsSearchedAt` on the lexeme — the instant the corpus was last successfully
> consulted, or null.**

- Null → never consulted. The word's enrichment, or a backfill, picks it up. This is what an
  imported word looks like.
- Set, no `subtitle` examples → consulted, nothing was good enough. Nothing comes back for it, and
  no model call is spent re-learning that the corpus is thin.
- Set and older than the corpus's own `built_at` from `GET /status` → the corpus has moved on. That
  is the rescan predicate, available for free, with no rescan button built.

It is written only on a **successful** consultation, so a retrieval service that was down leaves the
word looking untouched and Try again, or a backfill, finds it later. This is why a save can never fail because the
corpus was unreachable: the word is already written before anything is asked.

### 9 · The browser reaches the corpus through Acervo

> **DECISION: Acervo's server proxies a fixed allow-list of retrieval routes under
> `/api/acervo/v1/speech/…`, behind the same bearer auth as everything else.**

The alternative — exposing the retrieval service to the browser directly — means a second hostname,
a second CORS configuration, an unauthenticated read API on the network, and the operator token for
channel mutations somewhere near a browser. The proxy costs one router and removes all four. The
retrieval service stays bound to the internal compose network and is never published.

The allow-list is `GET /clips/{segment_id}`, `GET /search`, `GET /status`, `GET /statistics`, and the
channel routes. It is an allow-list rather than a pass-through so that adding a retrieval route
never silently adds an Acervo route. Acervo holds the operator token as deployment configuration and
attaches it to the mutating channel calls; it never leaves the server, exactly like a provider key.

On the client, `web/src/clips.ts` owns **every** call to those routes and nothing else makes one —
the rule `sync.ts` lives by for the graph and `dictionaries.ts` for dictionaries. It creates the
packaged typed client with Acervo's proxy base URL and a `fetch` that carries the session token, so
the packaged client is used unchanged rather than reimplemented.

A clip example renders from its stored fields, so the article reads offline like every other read.
Pressing it needs the network — YouTube is on the other side of it regardless. The player is opened
with the **current** clip fetched by `clipRef`, falling back to the stored video reference, start and
end when the service cannot be reached. Acervo owns the dialog; `SpeechClipPlayer` owns playback.

### 10 · One channel catalogue, and it is the retrieval service's

The retrieval repository already owns a curated catalogue (`config/channels/es.json` today), CRUD
routes, enable/disable, and a reviewable per-language curation session template. Copying that list
into Acervo would create a second thing to keep in step and a second place to curate.

> **DECISION: Acervo ships no channel list. Settings ▸ Clips reads and writes the retrieval
> service's catalogue through the proxy.**

The catalogue directory is a **mount seeded from the installed package when it is empty, and never
overwritten**, so a channel the owner added survives a version bump. Seeding is mandatory rather
than a convenience: the repository can only edit a `<language>.json` that already exists, and the
schema forbids a catalogue with no sections, so an empty directory cannot be bootstrapped through
the API at all. That is also why the wheel carries the default catalogue as package data, rather
than the file being found only because it sits in that repository's working tree.

Two costs, both honest. A channel newly shipped by a later retrieval version does not appear on its
own — the owner's list is the owner's. And a language the seed does not cover cannot be added from
Settings; that is a limitation to fix in the retrieval repository rather than to work around here.

**Settings ▸ Clips** shows whether the service answers and what its corpus holds, lists the channels with
enable, disable and add, offers Update now, and has two switches: `searchEnabled`, which stops the search
a save queues while a person's own request still searches, and `selfContainedOnly`, a matter of taste —
speech tidy enough to follow cold, or as messy as a real room. **Disabling a channel stops new downloads
and removes its clips from search at the next update**; clips already stored in articles stay, being
records the owner kept rather than a live query.

### 11 · A step of the word's enrichment, not a second engine

A clip search is the first step of the server's `enrich` job ([`jobs.md`](../architecture/jobs.md)):
one job per word, its steps in one order, showing in one place. It comes before pictures because it
is the faster of the two and the owner is looking at the page. **Its rests are its own.** A picture
is one image call metered by an image provider at roughly one a minute; a clip search is one text
call metered somewhere else. Sharing one backoff would let an image 429 silence clip search for ten
minutes for no reason.

The article's empty states differ from pictures, deliberately. A picture's absence is a gap to fill,
so it keeps a frame; a clip's absence is the expected outcome for most words. A sense whose search
is pending shows a quiet skeleton row; one whose search found nothing settles into *No recorded
example* while the word stays open, so nothing jumps, and shows **nothing at all** the next time it
is opened ([`../architecture/jobs.md`](../architecture/jobs.md), "What the interface shows").

### 12 · What is deliberately not built

- **No manual corpus search surface.** The owner does not browse the corpus and pick clips by hand.
  If that turns out to be wanted, it is a separate feature with a separate design.
- **No rescan.** Neither adding a channel nor a completed index update touches words already held.
  §2.8 leaves the predicate available; the button is not built, and §2.4a says what it
  would have to add first.
- **No cross-service health dashboard.** Settings ▸ Clips shows whether the service answers and what
  its corpus contains, which is what a person actually needs. A dashboard is not that.
- **No audio, no ranking model.** Additive on the other side.

### 13 · Target-language text: two surfaces, and only one of them is Acervo's

The retrieval service can translate a clip. It should not translate *Acervo's*, and separating the
two surfaces is what makes the question easy.

**The article's line is Acervo's, and it is free.** `Example.translation`, `translationLang` and
`matchedTranslationForm` already exist with the `translation ⇔ translationLang` XOR invariant, and
`prompts/acervo_compose.md` already produces exactly that shape — a translation into
`glossLangs[0]` plus a verbatim matched form — in the *same call* that produces an example.

> **DECISION: the clip-selection call of §7 also returns the translation of the clip it chose**, in
> `glossLangs[0]`, with `matchedTranslationForm`, exactly as capture does for a generated example.

No second call, no second provider configuration. It goes into the graph, so it replicates to the
phone and reads offline like every other example — which a per-clip fetch from the retrieval service
could never do, since `GET /clips/{segment_id}` never populates `target_text` and translation there
is always a job.

**The player's word alignment is the service's.** It yields a validated many-to-many
word-alignment graph that the packaged player renders as an interactive relation: click a word and
its counterparts light up, and during playback the translation illuminates in step with the audio.
Acervo stores none of it and reimplements none of it.

> **DECISION: Acervo stores nothing the retrieval service computed, and the player shows Acervo's
> own sentence.** *(Amended from the first version, which let the service translate the clip for
> the player.)* The player is handed the stored translation as `targetText`, so only the alignment
> stage runs — one provider call, fetched when the dialog opens, online-only like the clip. Asking
> the service to translate afresh produced a second, differently worded sentence for the same
> passage, cost two calls and up to two minutes, and left the player and the article disagreeing in
> front of the reader. A deployment with no translation provider still shows its own sentence.

**The service's model calls run on the owner's chain.** `TranslationProvider` and
`WordAlignmentProvider` are Protocols there, and `create_app` takes both — a public entry point. So
Acervo writes the adapter against `acervo.models` and the speech container calls `create_app` with
it injected, in place of the console script. The other repository changes nothing at all: no LiteLLM
dependency, no schema-dialect port, no error-taxonomy mapping.

`acervo.models` stands alone by design, so that image carries it and `models/catalogue.json` and
nothing else of Acervo's; Acervo's *server* image still never imports `speech_retrieval`. The chain
is **given** as `ACERVO_TEXT_CHAIN` rather than looked up, since that container has no business
reaching the database — the rule already stated for work that cannot import `repository/`. And
Vertex needs only the credentials directory two containers already mount.

One rule for that adapter: the cache is keyed on the `provider` and `model` it reports, so it
reports **the chain**, never the row that happened to answer. Otherwise fall-through thrashes the
cache. Translation and alignment are separate stages with separate keys, so they need not be served
by the same model.

### 14 · A clip anchors a picture last

`src/acervo/images/article.py` ranks example origins for the picture brief writer: `attestation`,
`manual`, `llm`, `tatoeba`, `wiktionary`, `subtitle`. A clip anchors a picture only for a sense with
no other sentence. `llm` sits above `tatoeba` and `wiktionary` because a generated example is written
for *this* sense, in the vocabulary's own languages, with a translation and both matched forms.

The first version excluded clips outright: a picture of what the clip already shows seemed drawn for
nothing, and pictures and clips were heading for separate full-screen surfaces. In use, a clip's
sentence made a good scene, and the article now puts a picture and its clip on one card, so a clip
ranks last instead.

---

## §3 · Operating it

**The model calls in the speech container carry no schema.** The service's two prompts name no
field and leave the shape to a `responseSchema`. Acervo's adapter renames that dialect and writes
the shape into the instructions instead, because no schema is sent anywhere in Acervo (`AGENTS.md`,
"Constrained decoding is not used"): the alignment schema, the strongest case for one, bought no
accuracy against constructed ground truth and was rejected with a 400 above roughly a hundred tokens.

Three facts, each of which once produced the same single grey line in the player:

- **The image must carry `google-auth`.** LiteLLM reaches Vertex through a deferred import of it and
  does not require it; a catalogue row is checked for environment variables and a credentials file,
  never for an importable library, so the row looked available and raised on the first call.
- **The startup guard must ask the question the chain asks.** Asking whether *any* text row is
  credentialed, while `chain.resolve` honours `ACERVO_TEXT_CHAIN`, injects a provider that can only
  fail. Injecting nothing is what produces the truthful "Translation is unavailable."
- **The service caches a refusal.** A stage that produced unusable output is served from memory ever
  after, `cache_hit` and all, unless `retry_failed` is sent — so a correct fix still shows the old
  failure on every clip already attempted. The player's retry sends that flag.

**Clearing the translation cache needs a restart.** Delete
`data/speech-index/derived/translations.sqlite3`, then restart the service
(`docker restart acervo-speech-retrieval-1`). `TranslationStore` creates its tables once, in the
container's lifespan, so a file deleted under a running service comes back as a zero-byte database
with no tables and every query fails. The symptom is a corpus that answers but reports translation
unavailable, beside a `translations.sqlite3` of exactly 0 bytes.

**A model call must not run on the event loop.** `generate` is synchronous; awaited inline it held
the container's single uvicorn loop for the length of a call, during which nothing answered — its
own three-second healthcheck included. `_Stage` runs it in a thread.

---

## §4 · How it is tested

The retrieval contract is pinned in two pieces rather than against a copy of `openapi-v1.json`. A
**recorded response** — `tests/unit/clips/fixtures/search-es-picar.json`, a real `/search` answer
trimmed to three results — is Acervo's statement of the contract in the shape it consumes and the
data every fake corpus serves; re-record it when the pin moves. A **gated live check**
(`RUN_SPEECH_CONTRACT_TESTS=true`) asserts against a running service that the routes still exist and
the fields the client reads keep their names. The spec itself belongs where it is generated: a 117 KB
copy here would be re-committed in full on every pin bump and still only assert, one level removed,
what the live check asserts against the real thing.

Beside those: `test_layering.py` keeps `acervo.clips` free of settings, graph and database; shared
vectors pin the derived clip id from both sides, with a test that two searches of one lexeme produce
one row; a test asserts the operator token never appears in a proxied response; and an article with
the retrieval service stopped, on a device with no network, still reads.
