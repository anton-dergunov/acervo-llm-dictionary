# AGENTS.md

## Product and current phase

Acervo is a self-hosted vocabulary store. One Python service is the durable shared store and every
client keeps a complete owner-scoped replica in IndexedDB. The vocabulary graph is
`topic -> lexeme -> sense -> example / attestation / imagePrompt / pronunciation / studyState`; a
lexeme may belong to multiple topics, and loops and stories are made from words. Markdown and
extended-article JSON are not storage formats.

**Reads are offline-first; writes are online-only.** The interface serves every read from the replica
and works with the server unreachable. Every write is a synchronous round trip that fails loudly when
offline and leaves the replica untouched. This is deliberate (`docs/architecture/sync.md`): only the
server mints a version, so `revision` alone orders records and there is no merge to implement.

There is one owner and no other users yet. The owner's vocabulary, its pictures and its recordings are
real and irreplaceable.

## Backward compatibility stays out of the shipped code

The clean current design wins. Obsolete schemas, models, interfaces and files are replaced directly,
and **the shipped code never learns that an earlier version existed**.

That prohibition was once absolute because there was nothing to lose. There is now: a real
vocabulary, its pictures and its recordings. What the rule was protecting was never "never migrate"
— it was the code staying clean. So the prohibition keeps its full force *inside* the application,
and there is one named way out that lives outside it.

- Do not add adapters, transformers, compatibility readers, legacy importers, aliases, dual
  reads/writes, fallback schemas, data-preserving migrations, or version branches anywhere in
  `src/acervo/` or `web/`.
- Do not retain an obsolete interface to ease a transition. Delete it and update every caller.
- The Alembic bootstrap defines and deploys the current schema; it is one head and not an upgrade
  path, and must not convert data from superseded Acervo models.
- If a proposed implementation needs compatibility machinery, stop and redesign it around the
  current canonical model.
- **A one-off converter outside the application is allowed**, and is how the owner's data survives a
  schema change. It is a script under `scripts/throwaway/`, written for one specific transition, run
  by `./deploy.sh --transition`, and deleted once it has run. It says in its own docstring that it is
  throwaway; it declares the one revision it converts *from* as `FROM_REVISION` and refuses to run
  against anything else, naming both; it exposes `main(argv)` taking `--database` and `--dry-run`;
  and nothing that ships imports it. Preserving the owner's data is worth one such script. It is not
  worth a branch in the server, and a script that is still there two changes later has become one —
  which shows: its `FROM_REVISION` matches no database any more, so it can never run again, and the
  only reason to keep it is to forget to delete it. Its tests are deleted with it.
- **Hard rule: a change that needs a throwaway converter is not finished until the owner can run the
  transition without working anything out.** Writing the script is half the job; the other half is
  getting it onto the server and run, and that half used to cost the owner half an hour of hand
  copying and corrected commands. Two obligations, in this order of preference:
  1. **`./deploy.sh --transition` runs it, and takes no argument.** It does not need to be told which
     script: `scripts/transition.py` reads the revision the database is stamped with and picks the
     one converter under `scripts/throwaway/` whose `FROM_REVISION` names it. A database already at
     the release's revision is left alone; one no converter names is refused, naming both revisions,
     and the answer is then `--reset-database`. Revisions are digests and have no order, so a database
     "newer" than the release cannot be told from one nobody wrote a converter for — both are refused.
     The deploy stops the server, copies the database files into the dated
     `backups/<UTC timestamp>/server/` directory every deploy already makes (the ten newest are kept
     automatically) and **prints that path, twice**, then runs the converter's dry run and stops if it
     refuses, converts, checks the whole schema again whatever the converter said, and only then
     starts the new server. A refusal restarts the previous server and deploys nothing. The script
     travels in the release archive like everything else; the owner never rsyncs directories by hand.
     It runs **inside the new server image** as the database file's owner, because the host's Python
     has neither SQLAlchemy nor the `acervo` package and a root-owned write would leave the database
     unreadable to the server. It goes through the launcher's fixed operation list
     (`remote-helper.sh`, a protocol bump, so `./deploy.sh --install-helper` once) and never an
     arbitrary remote command. The mechanism is generic and knows nothing about what any converter
     does, so deleting one leaves nothing behind and the deploy code never learns an earlier version
     existed. The backup is the database only: a schema converter does not touch media. A change
     where the owner should look before anything is written is one that should not use this path —
     hand over the commands below instead, with the dry run as its own step.
  2. **Where a converter cannot go through that path, or the owner should drive it by hand, hand over
     the exact commands** — never a generic outline. Written for the owner's real deployment, read from
     `deploy/acervo/compose.yaml`, `install.sh`, `deployment.env.example` and `deploy.sh` rather than
     recalled: the host directories behind `/var/lib/acervo/server` and `/var/lib/acervo/media`
     (`data/server`, `data/media` under the deployment root), the built image's real name (`docker
     images`, not a placeholder), and the real container name. Each command says **which machine** it
     runs on — the NAS or the laptop — because `./deploy.sh` and `git rm` do not run on the NAS. Cover
     every step: stop, back up the database *and* the media, dry run and what its output must say,
     convert, deploy, and delete the script. Say how the script reaches the server if the release
     does not already carry it. Do not assume the owner will locate code, paths or an image name
     themselves; an instruction they must correct is a defect in the change.
  Either way the change ends with the suggested commit message and the exact commands — for the first
  path, `./deploy.sh --transition` and then deleting the script — and the script is still deleted
  once it has run.
- A local IndexedDB replica is still wiped rather than transformed. It is a replica, and re-pulling
  it costs a minute.
- **One in-application exception**, and only one: `upgradeBundle` in `transfer.ts`. An exported
  bundle is a file that has left the application and outlived the schema it was written under, which
  is the reason the export exists at all. An easy adaptation there — a renamed field, a new one with
  a sensible default, an enum value that maps cleanly — belongs in that function, applied to the text
  before `parseArticle` reads it. Anything harder is refused, naming both versions, and converted by
  a throwaway script. Do not let this grow into a second pipeline, and do not cite it to justify
  compatibility anywhere else.

## Documentation

The design lives in [`docs/`](docs/README.md), and `docs/README.md` is the map. **Read the document for
the area before changing it** — [`docs/architecture/server.md`](docs/architecture/server.md) before
anything under `src/acervo/` or `deploy/`, the feature's own document before a feature. The rules below
are the ones that break quietly; each links to where it is argued.

- **Docs describe the current design only.** No "the first version did X", no REVISED or SUPERSEDED
  notes, no archive: git is the history. A rejected alternative stays only as the reason the current
  shape is what it is. Change the doc in the same change as the code it describes.
- **Unfinished work lives in [`docs/plans/`](docs/plans/)**, including experiments designed and not yet
  run. A plan leaves only when it is built — its reasoning folded into the topic doc — or obsolete. Never
  move an unfinished plan into `experiments/`.
- **`experiments/` holds apparatus and results**, one directory each, indexed in
  `experiments/README.md`; a doc keeps the decision and a link to the numbers.
- **An experiment's raw results are committed** — labels, scores, reports, model replies — when they
  hold no personal data, credentials or private paths and come to a few MB of text. Media and caches
  that can be regenerated stay ignored. The owner's own words are the product's data, not personal
  data; an email address, a hostname or a deployment detail is. Check before the first commit.
- **Cite a doc by path and section** (`docs/features/loops.md` §2.13): several documents number their
  own sections, and a bare "§2.13" is ambiguous. This file is untracked, so tracked code and docs never
  point at it.

## Architecture

**The client** ([`docs/architecture/sync.md`](docs/architecture/sync.md),
[`docs/features/articles.md`](docs/features/articles.md)):

- Interface code reads and writes only through `AcervoRepository`. `sync.ts` owns every call to the
  graph routes, the sync schedule and status; `selectors.ts` derives every view model and is pure.
- **The replica is immutable and shared.** Never mutate a snapshot (records are frozen outside
  production so a test catches it), and never clone or validate the whole replica on a path a save, a
  pull or a repaint takes — at 1,700 words that cost ~190 ms a word and grew with every word. A merge
  validates only the incoming records (`validateChanges`).
- **Any change to a replicated record's shape bumps `LOCAL_SCHEMA_VERSION`** in `repository.ts`. A
  replica under another account or version is wiped and pulled again *into storage*, never kept in
  memory instead; one whose `datasetId` no longer matches is not wiped — sync stops and the owner
  chooses.
- **`yaml.ts` is the only place YAML is understood**, and `saveArticle(parseArticle(text))` is the one
  writer, for typed edits, captures, chat and imports alike. Do not render an article by
  round-tripping stored records through YAML: `articleFor` and `articleFromDraft` feed one renderer.
  Gloss lines are flow style and quoted conservatively, for the strictest YAML reader.
- **The YAML editor is CodeMirror. Do not reintroduce an overlay.** Wrapping and line numbers are
  per-device settings.
- **`styles.css` is the design in `design/ui-prototype/`: change them together, never one alone.** The one
  legitimate difference is the YAML editor, whose colours in `YamlPane.tsx` and the prototype change
  together. **No mark may change where body text sits** — jsdom does no layout, so check a visual
  change with a screenshot (see Commands).
- `SwipeRow.tsx` is the one row for words, loops and stories; do not write a fourth. The selection is
  device-local and never synced ([`docs/features/word-selection.md`](docs/features/word-selection.md)).
- Players stop each other through `pronunciation.registerPlayer` / `silencePlayers`; there are three.

**The server** ([`docs/architecture/server.md`](docs/architecture/server.md)):

- **Python is the server language, with no exception**: FastAPI over one SQLite file.
- **`repository/` is the only code that touches the database, and a repository function is a
  transaction** — never a request-scoped session, since capture holds two long model calls.
- **`api/` may not import `jobs/`; `work/` may not import `api/`; `services/` does not know jobs exist.**
  Batch work under `jobs/` never imports `repository/` or `api/` and writes the graph through
  `client.py`, the one HTTP client against the API, which carries no retries.
- **The pipeline packages stand alone** — `models/`, `images/`, `clips/`, `pronunciation/`, `meaning/`,
  `ocr/`, `stories/` — importing the provider package and `article.py` and nothing else of Acervo's;
  `services/` is the binding layer. `test_layering.py` enforces all of this.
- **Every writer allocates revisions through `repository.graph`**, in the same transaction as the record,
  one counter per owner across every replicated table.
- Prompts are tracked content in `prompts/`, read at request time. The owner's standing rules are
  appended in the binding layer only ([`docs/features/standing-rules.md`](docs/features/standing-rules.md)).

**Work** ([`docs/architecture/jobs.md`](docs/architecture/jobs.md)):

- The request waits only while the owner waits; anything that lands on a record while they may walk away
  is a job. A save that creates a word or adds a sense queues `enrich` **in the same transaction**.
- A job says *which word*; each step re-derives what is missing, so a job run twice writes nothing.
  Retry and pacing live in the runner; a route makes one attempt; there are no client retries.
- A new capability is a new job kind and nothing else. A deploy never carries a job across a version.
- **A failure's sentence must survive every hand-off** — the service, the runner and the progress line
  each keep it rather than replacing it with a constant.

**Observability** ([`docs/architecture/observability.md`](docs/architecture/observability.md)):

- **Hard rule: a change that adds a way to fail is not finished until `admin log` shows that failure
  with its sentence.** Cause it and look, as a visual change is checked with a screenshot. New
  functionality is observable in the same change that introduces it, never in a follow-up.
- Three rotating logs beside the database — model calls, jobs, and `activity.log` for refusals, media
  removal and server starts — all `key=value`, all opened through `logfiles.py`, none configured by the
  package that emits. A fourth file needs a reason the three cannot hold it.
- **A request-path failure is an `ApiError` raised through the envelope**, never an error response a
  route builds: the handlers in `api/errors.py` are what write it down. Facts for the log go in the
  error's `noted`, not into the message the owner reads.
- **One request id joins everything** (`trace.py`): a request is given one, a job *is* one, and a call
  home adopts the one in its render token. It is stamped where a log file is opened, never where a
  line is emitted, because `models/` may import nothing of Acervo's.
- **Every client of a companion service sends `X-Request-ID`**, and a route a companion calls home on
  adopts the id. A new companion is not a new mechanism.
- **A media file is removed only through `services/media.remove`**, which says which and why.
- Work that outlives a request is a job and is logged by the runner; anything else that runs
  unattended — a tick, a thread, startup — writes its own activity line when it fails.
- A new line has a reader in mind: a question somebody will ask, phrased so a `grep` answers it.
  **Never a credential in a line**; ids and the owner's own words are fine.
- `test_layering.py` enforces the leaves, the header, the single unlink and the single error builder.

**Models** ([`docs/architecture/models.md`](docs/architecture/models.md)):

- `src/acervo/models/` is the one way to call a model, and **a provider is a catalogue row**; a provider
  fact discovered the hard way belongs in the row, not in a branch. Nothing should be designed as if
  today's Google-heavy defaults will last ([`docs/plans/provider-management.md`](docs/plans/provider-management.md)).
- A chain falls through on 429, 5xx, timeouts, dropped connections and unusable answers — never on an
  authentication or configuration error.
- **Constrained decoding is not used, anywhere.** Reintroducing it needs a measurement on the real
  prompt, models and largest input, not an argument. The measurements are also written up in
  `~/Dropbox/notes/blog/_drafts/constrained-decoding/` (private; never cite it from a tracked file).
- **A credential never leaves the server**, apart from a key's first and last four characters on
  `GET /models`.

**Features** — the one-line rules; the design is each feature's document:

- **Capture** is one server pipeline; adding a transport must not add a second one. Headless capture is
  the `POST /captures` job ([`docs/features/capture.md`](docs/features/capture.md)).
- **Photo capture** keeps exactly the square the viewfinder showed; do not add a crop the owner did not
  see ([`docs/features/photo-capture.md`](docs/features/photo-capture.md)).
- **Look-up**: a tap on a word being read moves no audio — what the tap used to do is the sheet's
  button; words are hit-tested by caret, never wrapped in elements; `source: "reading"` keeps the
  sentence verbatim ([`docs/features/look-up.md`](docs/features/look-up.md)).
- **Chat**: `articleEdit.ts` is the only place the edit language is understood, and change marks come
  from diffing two drafts, never from reading operations
  ([`docs/features/article-chat.md`](docs/features/article-chat.md)).
- **Pictures**: brief per word, draw per sense; the writer picks from every style left on and may not
  invent one; the server writes the file *and* the row. The brief template and style table are settled
  ([`docs/features/sense-images.md`](docs/features/sense-images.md)).
- **Media names carry a digest of their bytes**, so `mediaStore.ts` is a cache with no invalidation. Do
  not add a cache keyed on anything else, or an invalidation call.
- **Derived ids** — `image_prompt_id`, `clip_example_id`, `pronunciation_id` — are implemented twice and
  pinned by shared vectors; every writer derives them ([`docs/architecture/data-model.md`](docs/architecture/data-model.md)).
- **Pronunciation**: Opus from the master; the take route answers FLAC, with `take` in the cache key
  ([`docs/features/pronunciation.md`](docs/features/pronunciation.md)).
- **Clips**: `clips/corpus.py` is the only place the corpus's wire shape is read; refusing is the
  default; the stored sentence is the corpus's, verbatim; the proxy is an allow-list
  ([`docs/features/spoken-clips.md`](docs/features/spoken-clips.md)).
- **Loops**: LexiBeat is a separate service holding no provider credential; `loops/client.py` is the
  only place its wire shape is read ([`docs/features/loops.md`](docs/features/loops.md)).
- **Stories**: marks are found, not stored; narration is tiled back onto the text; one file per passage,
  never seeked ([`docs/features/stories.md`](docs/features/stories.md)).
- **The meaning map**: `web/src/meaningMap/` imports nothing of Acervo's; the drawn map carries no
  vectors and no text ([`docs/features/meaning-map.md`](docs/features/meaning-map.md)).
- **Dictionaries**: a compiled dictionary is never committed; the artifact format is described twice
  (`container.py`, `dictionary.ts`) and changed in both; one converter per format family;
  `externalHtml.ts` is the only place an `html` payload is trusted; "Add to my words" sends
  `reference`, never `text` ([`docs/features/dictionaries.md`](docs/features/dictionaries.md)).
- **Export**: a bundle is word files read by `parseArticle` and written by `saveArticle`; the Obsidian
  mirror is terse on purpose ([`docs/features/export.md`](docs/features/export.md)).
- **Anki**: content out, FSRS state back, never both ways ([`docs/features/anki.md`](docs/features/anki.md)).
- **`acervo-worker`** is one-shot: a new job is a new subcommand, never a compose service
  ([`docs/operations/deployment.md`](docs/operations/deployment.md)).
- **The macOS host** marks the menu bar and never interrupts or restarts unasked.

## Data rules

The model and its reasons are [`docs/architecture/data-model.md`](docs/architecture/data-model.md).

- IDs are 15 lowercase alphanumerics minted by clients, stored unchanged everywhere; three are derived.
  A document naming no stored entry may carry ids its producer minted; one editing a stored entry may
  not.
- **Provenance is modelled, never flagged.** Do not add a field for "the user wrote this".
- Every record carries `ownerId`, `deleted`, `createdAt`, `editedAt`, `editedBy`, `revision`. Deletions
  are tombstones, never collected. Related records share an owner.
- **`revision` is assigned by the server** and is the only ordering; `editedAt`/`editedBy` are
  provenance. A write states the revision it was edited from, and a stale one is refused, never merged.
- **No uniqueness constraints on replicated collections**; `sync_state`, `model_selection`, `jobs`
  and `loop_scripts` are exempt because they never replicate.
- A vocabulary language is a `vocabularies` record, with `definitionLang`, `glossLangs` and `notesLang`,
  not interchangeable. Every prose field in the compose prompt states which it is written in.
- State is derived where it can be — a picture, a loop, a story — never a status column.
- Applied records, their dependent tombstones and the cursor are one IndexedDB transaction.
- UI startup and every read work without the server; a write without it fails visibly and changes
  nothing locally. Never queue a write.

## Commands

```bash
# Use the project interpreter: `pyproject.toml` pins >=3.12,<3.13, and a system Python collects
# nine import errors and aborts the run, which reads like a broken test suite rather than a
# misconfigured one. Not `uv sync` — pyproject carries no test dependencies, so it removes pytest.
uv pip install -r requirements/dev.txt
# `src/acervo/` is an installed package, not a `sys.path` insertion. Without this, every `acervo`
# import fails and the suite reads as broken rather than as uninstalled.
uv pip install -e .
# Before `npm install`: `web/package.json` depends on the pinned spoken-usage-retrieval player by
# its versioned tarball path, so a clean clone cannot install until the artifacts are on disk. The
# script verifies digests against deploy/acervo/speech/pin.json and skips what is already correct.
./scripts/fetch_speech.sh
npm install --prefix web

.venv/bin/python -m pytest
npm --prefix web run test
npm --prefix web run build
npm run test:pwa

# Look at an interface change, not only test it. Playwright is a dev dependency of web/, with its own
# headless Chromium — install that once per machine. jsdom does no layout, so a menu that opens off
# screen, a mark that shifts body text or a control hidden behind another passes every test; a
# screenshot is how a change to `styles.css` or the prototype is checked before it is called done.
# Write a small .mjs, run it with node from web/ so `import { chromium } from "playwright"` resolves,
# and take shots at the owner's working size — a tablet in portrait, 834×1112 — then read them.
# The prototype is static: serve it with `python3 -m http.server --directory design/ui-prototype`,
# and hide its `#harness` toolbar, which sits over the foot of the screen. Keep the scripts and the
# shots in a scratch directory; neither belongs in the repository.
npx --prefix web playwright install chromium
npm run test:mac

# The packaged server image, built and started for real. Everything about the wire contract is in
# tests/unit/server/, which runs against the same application in-process.
RUN_DOCKER_INTEGRATION_TESTS=true .venv/bin/python -m pytest tests/integration/test_acervo_server_docker.py

# What this machine can call, and whose account it would spend. Spends nothing to answer.
.venv/bin/python -m acervo.admin providers
docker exec acervo-server-1 python -m acervo.admin providers   # the same reading on the server

# How long each job actually takes, per model, from the call log — and therefore what a timeout
# should be. Every model call is recorded, one line each, rotating, beside the database at
# ACERVO_CALL_LOG_PATH; this reads it back. Set a bound from this rather than from feel: the 120
# seconds the code used to carry was a guess, and one dead connection then cost two minutes of
# "Writing a brief…" for a brief that takes two.
docker exec acervo-server-1 python -m acervo.admin calls
docker exec acervo-server-1 tail -f /var/lib/acervo/server/model-calls.log   # while it happens

# Choose which providers answer, in order, as ids from models/catalogue.json. Unset means every
# provider this server has credentials for, in catalogue order. A key is read from the terminal and
# never reaches a command line; the other providers' keys are retained for a switch back.
./deploy.sh --configure-llm --llm-chain gemini-free,cloudflare \
  --llm-set CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef \
  --llm-key CLOUDFLARE_API_TOKEN --llm-api-key-stdin

# One real call per kind against real providers. Gated, costs money, and skips a provider this
# machine has no credentials for rather than failing.
set -a; . ./.env; set +a
RUN_LIVE_MODEL_TESTS=true .venv/bin/python -m pytest tests/integration/test_models_live.py

# The article conversation against a real model. Gated for the same reason, and worth running after
# any change to `prompts/acervo_chat*.md`: what a stub cannot tell you is whether a question comes
# back with no proposal, which is the most common correct answer and the easiest one to lose.
RUN_LIVE_CHAT_TESTS=true .venv/bin/python -m pytest tests/integration/test_chat_live.py -s

# Rebuild the vocabulary database after a schema change. There is one head and no upgrade path, so
# rebuilding is the default way a schema change is deployed, and a plain `./deploy.sh` will *refuse
# to start* against a database written under a different schema rather than serving it — the head
# revision id is a digest of the schema, so changing one changes the other with nobody remembering
# to. Accounts go with it and are recreated below; Anki is untouched — `--reset-anki` empties that,
# and nothing else.
#
# A *purely additive* change — new tables, nothing existing altered — may instead be carried across
# by a throwaway converter that creates them and re-stamps the head, so the owner's words, pictures
# and recordings are not rebuilt with the schema. That is a script under `scripts/throwaway/`, run
# by `./deploy.sh --transition` and deleted afterwards; see "Backward compatibility stays out of the
# shipped code". The guard does not change: a database nobody has converted is still refused by name.
./deploy.sh --reset-database

# Carry the database across a schema change instead. No argument: the deploy reads the revision the
# database is stamped with and runs the converter this release ships for it — after stopping the
# server, backing the database up into backups/<UTC timestamp>/server/ (the path is printed) and a
# dry run. Already current is a no-op; a revision no converter names is refused and nothing deploys.
# Delete the converter (and its test file) once it has run.
./deploy.sh --transition

# A deploy rebuilds only what changed: the images' base is pinned by digest (the same one in all four
# Dockerfiles — upgrading it is editing it), each Dockerfile copies what changes most often last with
# nothing run after it, and only dictionaries that changed since this machine's last deploy are sent
# (`docs/operations/deployment.md`, "What a deploy rebuilds"). A `RUN` placed after a `COPY` of
# Acervo's own files runs again on every code change, and on the NAS every rebuilt layer costs 5–40 s;
# a test refuses it. This reuses nothing — every layer, every dictionary, about a quarter of an hour:
./deploy.sh --rebuild

# Walk a messy vocabulary notes file into the Inbox, one entry at a time. Leaves the file alone
# unless --consume is given; progress is checkpointed outside the notes.
.venv/bin/python scripts/ingest_vocabulary_file.py "notes.md" --server-url https://acervo.example.com \
  --owner-email learner@account.example.com --limit 5 --dry-run

# Create an account. Registration is closed and there is no superuser, so this is the only thing
# that makes one, and it comes before the seeder after every --reset-database. The password is read
# from the terminal and never reaches a command line.
./deploy.sh --create-account
# …or, on the server itself, the command that flag runs. `-it` rather than `-i` so a password typed
# by hand is not echoed; `-i` alone is for a piped one.
sudo docker exec -it acervo-server-1 python -m acervo.admin accounts create --email learner@account.example.com

# Compile an external dictionary. `list` shows the catalogue; `verify` compiles a sample into a
# throwaway directory, which is how a catalogue row is promoted from listed to trusted.
.venv/bin/python scripts/build_dictionary.py list
.venv/bin/python scripts/build_dictionary.py build --id cc-cedict
.venv/bin/python scripts/build_dictionary.py verify --id kaikki-es-es

# The same thing on the server, writing into the directory the server publishes
docker compose -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker \
  dictionary build --id cc-cedict

# The same worker operations without a password, through the reviewed launcher. On Synology the
# Docker socket is root-owned with no docker group, so reaching the worker means reaching root —
# socket access *is* root access, since anything holding it can start a privileged container over
# the host filesystem. The question is therefore how narrow the path to root is, not whether to
# take it, which is what the launcher's fixed operation list answers. `--install-helper` once, then
# unattended from cron or DSM Task Scheduler.
sudo -n /usr/local/sbin/deploy-acervo worker anki-pull-state
./deploy.sh --worker backfill --owner-email learner@account.example.com   # from the laptop

# Fetch the pinned lexibeat wheel. The ~3.1 GB sample bundle the same pin names is deliberately not
# fetched here: it goes once into a directory on the server, with the URL and digest read from the
# pin. **Not by hand**: a bare `docker compose run --rm lexibeat lexibeat-bundle fetch …` omits the
# deployment's env file, so compose falls back to a named volume and the bundle unpacks, verifies
# and reports success into a store the running service does not mount. Without it no loop can be
# made — fifteen of the sixteen bed families load instruments from that catalogue.
./scripts/fetch_lexibeat.sh
./deploy.sh --install-samples

# Make one loop by hand and report how long each part took, which is what the poll and the timeout
# in work/loop.py are set from. It runs in the worker because the generator publishes no port.
docker compose -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker \
  loop render --owner-email learner@account.example.com --words 12

# The loop take cache: FLAC masters addressed by what they record. Unbounded on purpose, emptied by
# hand, the way dictionaries and media are.
docker exec acervo-server-1 python -m acervo.admin takes show
docker exec acervo-server-1 python -m acervo.admin takes prune --older-than 90 --dry-run

# Fetch the pinned retrieval artifacts named by deploy/acervo/speech/pin.json. `--check` verifies
# without touching the network. Upgrading the corpus service is: edit the pin, run this, redeploy.
./scripts/fetch_speech.sh
./scripts/fetch_speech.sh --check

# Anki is kept up to date by the server itself, behind two switches in Settings ▸ Anki: a push a
# minute after the vocabulary stops changing, and a read of the review state every hour and after
# each push. These do the same now, by hand, inside the server container. Bootstrapping an empty Anki
# is the one step that is always by hand, and it switches both on. `anki-export-state` prints what a
# read would store without storing it. Every deploy also writes the server's timezone, from this
# machine's own or `--timezone ZONE`.
./deploy.sh --worker anki-bootstrap-vocabulary
./deploy.sh --worker anki-push-vocabulary
./deploy.sh --worker anki-pull-state
./deploy.sh --worker anki-export-state

# Why something did not happen. The three logs — model calls, jobs, activity — as one account in the
# order it happened. With an id, everything filed under it: a job's id shows the job, its steps and
# every model call and take made on its behalf; the id is also the `X-Request-ID` of a response.
docker exec acervo-server-1 python -m acervo.admin log --failed
docker exec acervo-server-1 python -m acervo.admin log --lines 200
docker exec acervo-server-1 python -m acervo.admin log 0a1b2c3d4e5f6g7
docker exec acervo-server-1 tail -f /var/lib/acervo/server/activity.log   # refusals, as they happen

# What the server is doing, and what a deploy reads before it ships. Cancelling waits for the runner
# to stop between model calls, then abandons anything still inside one.
docker exec acervo-server-1 python -m acervo.admin jobs open --json
docker exec acervo-server-1 python -m acervo.admin jobs list
./deploy.sh --cancel-jobs                      # cancel them, then deploy
./deploy.sh --jobs cancel                      # cancel them and deploy nothing
./deploy.sh --cancel-jobs --transition         # cancel them, then carry the database across

# Enrich the words that predate all of this — an old import, or anything that lacks a clip search,
# a picture or a recording. The same `enrich` job a save queues, so it is not a second pipeline;
# `--dry-run` prints what it would queue and spends nothing. Nothing runs it on a schedule.
./deploy/acervo/run-worker.sh backfill --owner-email learner@account.example.com --dry-run
./deploy/acervo/run-worker.sh backfill --owner-email learner@account.example.com --limit 50

# The corpus is kept fresh by the server itself: the nightly run in Settings ▸ Schedule, or
# Update now in Settings ▸ Clips. Both ask the retrieval service to update and follow it, so there
# is no shell command for it any more — and no analyzer drift, since that service both builds and
# serves its own index.

# Draw sense pictures on this laptop, which is where the prompt work happened. Which provider draws
# is a chain, not a constant: the flag, else the chain you chose in Settings, else the catalogue's
# order. `check` says what would answer and as whom, and spends nothing. `--size 512` is the cheap
# run, Cloudflare's allocation being metered in pixels.
.venv/bin/python scripts/generate_images.py check
.venv/bin/python scripts/generate_images.py run --image-chain cloudflare,vertex --limit 20 \
  --server-url https://acervo.example.com --owner-email learner@account.example.com

# Write a verified sense-image run into the graph and the media directory. `verify` is the gate:
# it refuses a run directory that is not internally consistent, and `publish` refuses one whose
# senses this account does not hold rather than writing half of it.
.venv/bin/python scripts/generate_images.py verify --output output/images
.venv/bin/python scripts/generate_images.py publish --output output/images \
  --media /path/to/data/media --server-url https://acervo.example.com \
  --owner-email learner@account.example.com

# Insert disposable examples into an existing account. It writes through the service layer rather
# than over HTTP, so it needs no password.
docker exec -i acervo-server-1 python -m acervo.admin seed --owner-email learner@account.example.com
```

Credentials and deployment-specific addresses must never be committed.

## Shared-host deployment invariant

Acervo runs beside unrelated self-hosted applications; never assume ownership of the host, claim
ports 80 or 443 by default, or reset unrelated Tailscale Serve, reverse-proxy, firewall, Docker, or
port configuration. Any infrastructure mutation must target only Acervo's explicitly configured
listener or resources. Port 443 may be used only when explicitly selected and verified free.

A Tailscale service (`--service NAME`) is the exception that proves this, not a breach of it: its
443 is bound on the service's own virtual IP, so it is never the host's 443 and cannot collide with
another application or service. Acervo needs its own hostname because Android mints a WebAPK only
on a default port, and two apps separated by port alone are installed as one.

## Public-repository privacy

This repository is public. Never write real names, usernames, hostnames, email addresses, home
paths, private addresses, device names, credentials, tokens, or deployment targets into tracked
files. Use reserved examples such as `learner@account.example.com`, `user@server.example.com`, and
`https://acervo.example.com`. Keep machine-specific configuration in ignored files or external
secret storage.

## The owner's other repositories

`spoken-usage-retrieval` is the owner's own project, like this one. **When a fix belongs there, make
it there** — do not work around a missing field or a missing prop on this side to avoid touching it.
Three of the clip player's defects were on that side, and each of them had an obvious wrong answer
available here: synthesising a search result to smuggle a match span in, or storing a second
translation to avoid asking for one.

`lexibeat`, the loop generator, is the owner's too, and the same holds: a fix that belongs there is
made there, and it reaches Acervo through `deploy/acervo/lexibeat/pin.json`. **One word is prohibited in
both repositories** — the obvious English word for what a loop does to you is a competitor's product
name, and it may not appear in code, comments, identifiers, documents or directory names
(`docs/features/loops.md` §2.16).

Changing either is not free, and the cost is the thing to plan around rather than to avoid. For the
corpus, a change there means a version bump, a tag, a release, and a re-pin in
`deploy/acervo/speech/pin.json` plus `web/package.json`. Its CI installs with `uv sync --locked`, so a version bump also means `uv lock`,
and `docs/openapi-v1.json` is a snapshot that a version bump invalidates. Push the tag only once
that repository's own checks pass locally.

## Git workflow

Never run `git commit`; suggest a commit message and let the user commit.

A commit message is a one-line summary, a blank line, then the details as a short bullet list or a
few plain sentences. The body says what changed and why it changed, one point per thing a reader
would otherwise have to reconstruct from the diff. It is not a file-by-file inventory: group small
related edits into one line, and leave out anything a reader would guess anyway.

    Add per-sense mnemonic image generation

    - Draw one picture per sense from a two-call pipeline: a batched LLM brief
      per lexeme, then one image call per sense.
    - Art direction lives in a tracked style table; a sense is offered three
      styles and the brief writer picks one.
    - Phase A runs locally and writes only to the filesystem, so it cannot
      disturb the live ingestion.
