# The server

One Python service owns the whole server: FastAPI over one SQLite file, serving the interface at `/`
and the API under `/api/acervo/v1` on one port. It runs on the always-on machine, and everything a
device does that is not a read goes through it.

Python on the request path is what makes the rest possible: chat, capture, grounding lookups, a real
HTML sanitiser and any provider that needs a signed token are ordinary library work. One language
runs from the request path to the batch jobs, and one process holds the database, so capture, the
sync route and every job share one transaction primitive.

How work that nobody is waiting on is run is [`jobs.md`](jobs.md); how models are called is
[`models.md`](models.md); what the interface guarantees about sync is [`sync.md`](sync.md).

---

## Shape

```
src/acervo/
  settings.py        the one place the environment is read
  domain/            pydantic models — the canonical server model and the wire projection
  db/                SQLAlchemy tables, engine, session factory, alembic/
  repository/        the only code that touches the database
  api/               FastAPI: routers, the error envelope, auth, the static surfaces
  services/          request-path work, and the binding layer between the packages below and Acervo
  work/              the job runner and its kinds
  models/            the provider catalogue, and text() / image() / speech() / ocr()
  article.py         one word and its senses, the view every enrichment reads
  images/            sense pictures: a brief per lexeme, a picture per sense
  clips/             spoken clips: a corpus search and one selection per lexeme
  pronunciation/     reading a record aloud
  meaning/           the meaning map: embed, lay out, cluster, name
  ocr/               photo capture's page: an OCR engine's words to lines and sentences
  stories/, loops/   the story pipeline, and the client for the loop generator
  speech/            the corpus's translation seam, running on the owner's chain
  dictionaries/      the external-dictionary artifact compiler
  jobs/              one-shot batch work, run by acervo-worker
  consumers/anki/    the headless Anki robot, bound to the server by services/anki.py
  tokens.py          signing Acervo's own tokens
  trace.py           the request id that joins the logs
  activity.py        the activity log, and the reader for all three
  logfiles.py        opening a log file, the one way it is done
  client.py          the one HTTP client against the service
  admin.py           the management CLI
experiments/         experiments and benchmark tooling; never imported by the service
```

**Prompts are content, not code.** `prompts/` holds every prompt as tracked text, copied into the image
and read at request time, so changing what an entry says never means changing the code that builds a
request. **`experiments/` is outside the distribution**: one directory per experiment, holding its
apparatus and its write-up, with heavy dependencies in the experiment's own environment; nothing that
ships imports it.

### The rules

`tests/unit/server/test_layering.py` asserts every one of these, because each can be broken with one
import and nothing else would fail.

**1 · `repository/` is the only code that touches the database.** Routes, services and jobs all go
through it — the server-side twin of the client's rule that interface code reads and writes only
through `AcervoRepository`.

**2 · A repository function is a transaction.** It opens its own session and closes it. There is no
`Depends(get_db)` and no request-scoped session. Capture makes two model calls of up to two minutes
each and runs them outside any transaction, wrapping only the write; a request-scoped session with
`BEGIN IMMEDIATE` would hold an exclusive write lock across both calls and block every other request.
Owning session lifetime in the repository makes that impossible to write by accident. Anything that
must be atomic across several operations is *one* repository function.

**3 · `api/` may not import `jobs/`, and `work/` may not import `api/`.** Capture, review and the sync
API work with batch work absent. A route reaches jobs only through `repository/jobs.py`, and
`services/` does not know jobs exist.

**4 · One revision counter per owner, shared by every replicated table, allocated in the same
transaction as the record it numbers.** Never a per-table sequence. A record left at revision zero is
invisible to every `revision > cursor` pull, permanently and silently.

**5 · Batch work outside the server writes through `client.py`, against the service's own graph
route.** Same route, same validation, same revision allocation as a phone. Work inside it — the
runner's jobs, and the Anki loop they run — writes through `merge_graph`, the function that route
calls, so the rule holds there by construction; `consumers/anki/` itself still never touches the
repository, and `services/anki.py` hands it plain data. `client.py` carries no retries: a retry layer in the
transport would change the file ingestion's retry behaviour without changing its retry code.

**6 · The pipeline packages stand alone.** `models/` imports no settings, graph, database or Acervo
wire vocabulary; it decides *what kind of thing* went wrong — a closed seven-value `Reason` — and
`services/models.py` decides what Acervo's wire calls that. `images/`, `clips/`, `pronunciation/`,
`meaning/` and `ocr/` may import the provider package and `article.py`, and nothing else of Acervo's;
`services/` is where each meets settings and the graph. This is the rule that breaks most quietly:
one `from acervo.errors import ApiError` in `models/call.py` and everything still works — the package
is simply no longer usable without Acervo.

**7 · `article.py` is the view every enrichment reads.** One word, its senses and their examples,
assembled from the graph's change mapping, so a request-path service and a laptop batch run feed it
different sources and neither knows which. What differs is the judgement each makes afterwards, and
that stays in the pipeline: `images.article.anchor_for` decides which example a picture illustrates.
`article.py` imports nothing of Acervo's at all, which is what makes it safe to share.

**The corpus and the loop generator are not in this repository.** Each is a separate service behind
a version pin, reached over HTTP ([`../features/spoken-clips.md`](../features/spoken-clips.md),
[`../features/loops.md`](../features/loops.md)); nothing here writes to either's store.

---

## Storage

> **DECISION: SQLite, one file, for the core graph.**

One owner, 20–50 MB, and a write rate measured in words per day. `sqlite3 .backup` is the backup
path ([`durability.md`](durability.md)).

Four connection settings, each silently wrong if omitted:

| Setting | Why |
|---|---|
| `journal_mode=WAL` | Readers do not block the writer |
| `synchronous=NORMAL` | WAL's companion; `FULL` buys an fsync per commit for nothing here |
| `busy_timeout=5000` | Ordinary contention |
| `foreign_keys=ON` | **Defaults off, and is per-connection.** Without a SQLAlchemy `connect` listener every foreign key in the schema is decorative |

And one that is easy to miss: **`BEGIN IMMEDIATE`**, via an engine `begin` listener. Under WAL a
deferred transaction that reads and then writes fails its lock upgrade with `SQLITE_BUSY` at once —
the busy handler is not invoked for an upgrade — and the revision counter reads-then-writes on every
write.

**`GET /graph` is a pure read.** It is the most frequent request, once a minute per visible device,
so the owner's `sync_state` row is created with the account rather than on first pull. **A
`since=0` pull is unbounded** and materialises the whole vocabulary before serialising; the core
stays small enough for that, and it is the first thing to measure if that changes.

**Derived stores live beside the database file and in no table**: the loop take cache (`takes/`)
and the meaning map's embeddings and drawn maps (`maps/`). Both are server-local and keyed by a digest
of what they hold, so neither needs a mount, an environment variable or a schema change, and both
survive a rebuilt database.

### The schema is bootstrapped, not upgraded

> **DECISION: Alembic defines and bootstraps the schema. It is one head, not an upgrade path.**

**The head revision id is a digest of the schema** — tables, columns, indexes and foreign keys — so
changing the schema changes the head with nobody remembering to. A database stamped with any other
head is refused **by name, before the server serves a single request**, with the way out named in the
refusal. A deployment that needs a rebuild therefore fails rather than half-working: without this, a
changed column answered every route that named it with an anonymous 500 while `/health` stayed green.
`tests/unit/server/test_bootstrap.py` asserts the refusal.

A schema change is deployed by rebuilding (`./deploy.sh --reset-database`) or, when the owner's data
should survive it, by a one-off converter run by `./deploy.sh --transition`. The converter lives
outside the application and is deleted once it has run; the server never learns an earlier schema
existed.

---

## Auth

- **Passwords:** argon2, at least eight characters.
- **Tokens:** JWT, HS256, signed with a per-user `token_key` mixed into the key, so changing a password
  invalidates every outstanding token. `src/acervo/tokens.py` is the one place that signs; a render
  gets a token audienced to the take route and good for an hour.
- **Lifetime: 30 days.** The client refreshes once at startup and never again, so anything much
  shorter signs out a phone left unopened for a week.
- **Unknown email and wrong password return the same 401 with the same message**, and the unknown-email
  path runs a dummy hash verify so timing does not leak what the message will not.
- **Both `Bearer <token>` and a bare token are accepted**, because callers use both and `HTTPBearer`
  answers a bare one with a 403 no client handles.

Registration is closed. Accounts are made by `admin.py accounts create`, reading the password from
stdin, and the owner's `sync_state` row is created in the same transaction.

---

## The wire contract

Every JSON response is `{"data": …}` or `{"error": {"code", "message"}}`. The client treats *any* body
without `data` as a generic failure, so FastAPI's `{"detail": …}` must never reach it:
`RequestValidationError` becomes `400 invalid_input`, and a ≥ 500 keeps its message off the wire. The
one exception is the corpus proxy under `/speech/…`, which returns the corpus's body verbatim so the
packaged client works unchanged.

The routes, under `/api/acervo/v1` unless shown:

| Area | Routes |
|---|---|
| Session and health | `GET /health` (none), `POST /session`, `POST /session/refresh` |
| The graph | `GET /graph?since=` (pure read), `POST /graph` (one transaction, all or nothing), `POST /graph/reset` (confirmation token `delete-all-words`), `POST /articles` (one parsed document, diffed on the server) |
| Capture | `POST /capture`, `POST /capture/resolve`, `POST /captures` (a job), `POST /photo/read`, `POST /photo/store`, `POST /photo/warm` |
| Chat | `POST /chat` |
| Work | `GET /jobs`, `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `POST /jobs/{id}/dismiss`, `GET /events` (a stream) |
| Pictures | `GET`/`DELETE /images/prompts/{id}`, `PUT /images/senses/{id}/picture`, `GET`/`PUT /images/settings` |
| Pronunciation | `POST /pronunciations/utterance`, `POST /pronunciations/take`, `POST /pronunciations/{collection}/{id}`, `PUT …/{id}/audio`, `GET`/`PUT /pronunciations/settings` |
| Loops and stories | `POST /loops`, `GET /loops/schema`, `POST /loops/{id}/music`, `DELETE /loops/{id}`, `POST /stories`, `GET /stories/types`, `DELETE /stories/{id}`, `POST /stories/{id}/parts/{part}/audio` |
| The map | `GET /map/{language}` |
| Review history | `POST /reviews` (a batch, append-only), `GET /reviews/latest?system=`, `GET /stats?language=&days=&weeks=` |
| Anki | `GET /anki`, `PUT /anki/settings`, `POST /anki/push`, `POST /anki/pull` (due at once) |
| Clips and the corpus | `GET`/`PUT /clips/settings`, and the allow-listed proxy under `/speech/…` |
| Dictionaries | `GET /dictionaries`, `GET /dictionaries/online/{source}` |
| Settings | `GET /models`, `PUT /models/selection`, `GET`/`PUT /rules`, `GET`/`PUT /schedule/settings` |
| Static | `GET /api/acervo/media/{path}` (bearer), `GET /api/acervo/dictionaries/{file}` (bearer), `GET /api/acervo/downloads/{file}` (none), `GET /api/acervo/v1/mac-release` (none), `GET /` (the PWA) |

What is load-bearing and easy to unify by accident:

- **`/health` is owner-independent.** It is the liveness probe and the pre-sign-in readout, so a body
  that varied by caller would be wrong behind a cache; `GET /models` is where an owner sees their own
  choices. Its `capture.reason` names an environment variable and never a value.
- **The static mounts have different auth on purpose.** Downloads are open because the macOS updater
  fetches them with no credentials; dictionaries and media are closed. A photo is served to its owner
  only, and a pending one never.
- **Every static mount answers `Range`.** The dictionary reader reads artifacts by byte range, so a
  dictionary the device does not hold is read over the network by the same code. Two silent ways to
  lose it: compression in front of these routes, which strips `Content-Length`; and a hand-rolled
  `StreamingResponse` to bolt on auth, which has no Range handling. Check the token in the route and
  return a `FileResponse`.
- **Path containment is checked in the route**, for every file served.
- **CORS is configured.** The macOS host loads its interface from `acervo://app` and calls the server
  cross-origin with headers that trigger a preflight. Without CORS every call fails inside the browser
  with no server-side log, and the client reports *"The Acervo server could not be reached"* — the
  wrong diagnosis, with nothing pointing at the truth.

### Invariants every writer keeps

Each has a test, and each is something a reasonable re-derivation gets subtly wrong.

1. The collection order is merge order, and reversed, tombstone order — with vocabularies and topics
   excluded from the sweep.
2. `matchedForm` must occur **verbatim** in the example text: untrimmed, uncased, un-normalised.
   Capture silently drops a form that fails this exact test, so loosening the validator breaks the
   drop and tightening it turns a good capture into a 400. Same for `matchedTranslationForm`.
3. Chinese lexemes require a reading, on a **prefix** test, so `zh-Hant-TW` and `zho` match — in both
   copies of the validation, with both messages.
4. `translation` ⇔ `translationLang`, and `imageRef` ⇔ `imageModelId`: XOR on emptiness.
5. A clip's title, start, end, channel or `clipRef` requires a video reference — *and* the projection
   hides them all when there is none. Two mechanisms for one invariant, both asserted.
6. `origin: "attestation"` requires a source attestation sharing the owner **and** the sense's lexeme
   — a two-hop join.
7. A `fromSentence` of `null`, `""` or absent must not collapse to `0`, or the learner is credited with
   every model-invented example.
8. A stale revision refuses the whole batch; an unknown id with a non-zero revision is also stale.
9. `datasetId` is the `sync_state` row id: stable across restarts, unique per owner, and changed by a
   rebuild.
10. Wire timestamps are exactly `YYYY-MM-DDTHH:MM:SS.mmmZ` — 24 characters, three fractional digits.
11. Ids are 15 characters of `[a-z0-9]`, from `secrets.choice`, except the three derived ones.
12. An id already held by another owner is `id_conflict`, not an overwrite. It takes a second lookup,
    and skipping it is a silent cross-owner write.
13. The model-call HTTP-status → error-code mapping is a contract: the file ingestion and the job
    runner retry on exactly `llm_rate_limited`, `llm_unavailable` and `llm_unreachable`. An SDK whose
    exceptions replace those codes changes the retry behaviour without changing a line of retry code.
