# Observability · what Acervo can tell you

Acervo is a single-owner system with no operations team, which changes what this is for. There is no
alerting and no dashboard anybody will watch. The whole question is narrower and harder: **when
something the owner asked for does not happen, can they find out why without reading the source?**

The answer is three rotating text files beside the database, one id that joins them to each other and
to the companion services, and one command that reads them back as a single account.

```bash
docker exec acervo-server-1 python -m acervo.admin log --failed     # what went wrong lately
docker exec acervo-server-1 python -m acervo.admin log <id>         # everything about one job or request
docker exec acervo-server-1 python -m acervo.admin calls            # how long each model takes
```

---

## §1 · Three logs, one shape

| File | Written by | One line per | Read to answer |
|---|---|---|---|
| `model-calls.log` | `models/journal.py` | attempt on a provider, and what the caller did with the answer | which provider refused, and how long a call really takes |
| `jobs.log` | `work/journal.py` | job start, step outcome, job end | why a job failed |
| `activity.log` | `activity.py` | request refused, media file removed, server start and stop | why was I told no, and what was running when |

They are separate files because they are read for different questions and written at very different
rates; mixing them makes every `grep` worse. All three keep the same shape:

- **`key=value` pairs**, so a `grep` is a question with an answer: `grep code=stale_record activity.log`.
- **The package that emits never configures.** Each writes to a named logger and stops. Where the lines
  go is decided by whoever reads `Settings` — `services/models.py`, the runner, `api/app.py` — through
  the one opener in `logfiles.py`. `models/` may import nothing of Acervo's, and this is what lets it
  log anyway.
- **A log that cannot be opened warns and is dropped.** A server that cannot write its log should still
  do its work.
- **Rotating and bounded**, because an unbounded file on the database's volume is a way to lose the
  database. Paths and sizes are `ACERVO_CALL_LOG_*`, `ACERVO_JOB_LOG_*` and `ACERVO_ACTIVITY_LOG_*`; an
  empty path switches a log off.
- **Every line has a reader in mind** — a question somebody will actually ask. A log that records
  everything is one nobody reads.

The container's stderr (`docker logs`) carries tracebacks and uvicorn's access lines, and nothing else
is sent there. A traceback from a failed request names its request id, so it can be matched to the
activity line that carries the same one.

## §2 · The request id

One id, 15 lowercase alphanumerics like every other id in Acervo, held in a context variable
(`trace.py`) and appended to a line as `rid=…` **where the file is opened**, never where the line is
emitted. It is set in three places:

- **A request is given one.** Its own `X-Request-ID` if it sent a well-formed one — batch work through
  `client.py` sends one id for a whole run — otherwise a new one. The response carries it in the same
  header. Anything not of that shape is replaced rather than repaired: a header is a stranger's text and
  it is about to be written into a log.
- **A job is one.** The runner holds the job's id for as long as the job runs, so every model call a job
  makes is filed under the job. `jobs.log` does not repeat it as `rid`; its lines already say `id=`.
- **A call home adopts one.** A loop render calls back seventy-odd times for its takes and its lines.
  The render token it was given carries the id of the job that asked (`tokens.mint_render`), and the
  routes it calls take that up once the signature has verified. The generator carries nothing it has to
  know about, and each take is filed under the job rather than arriving as a request from nowhere.

And it is sent out: **every client of a companion service sends `X-Request-ID`** — `loops/client.py`,
`clips/corpus.py` and the corpus proxy in `services/speech.py`. The corpus logs under it and says it
back in an error. The loop generator's own handle is its operation id, which `jobs.log` records as
`operationId`; `admin log` matches that too, so an id read off the generator's container log leads back
to the job.

Solved once on purpose: a new companion is a new client that sends the header and, if it calls home, a
token that carries the id. It is not a new mechanism.

## §3 · What is written down

**Every refusal**, by construction. Each response is `{"data": …}` or `{"error": …}`, and the handlers
in `api/errors.py` that build the second are the one place a refusal passes through — so that is where
it is logged: status, code, method, path, and **the sentence the owner was shown**. A route gets this by
raising `ApiError`; it does nothing else. A code that proves too frequent to be worth a line is added to
`QUIET` there, from a real log rather than ahead of one.

An error may also carry `noted` — facts for the log that never reach the wire:

- **A stale write** says which record, the revision the device claimed and the one stored, and the
  device. The owner's sentence is right for the owner and useless for finding which device was behind.
- **A 401** says which: `missing`, `malformed`, `expired`, `bad_signature` (a changed password, or a
  secret that was rotated or lost), `no_account`, `wrong_audience`. The caller is still told one thing.

An unhandled exception is logged in its own words and answered in none of them.

**Every media file removed.** `services/media.remove` is the only code that unlinks one, and it says
which file and why: `replaced`, `deleted`, `rollback` (written for a row that then failed to land) or
`unclaimed` (a pending photo nobody added). Writing a file is not logged; the row that names it is the
record of that, and it replicates.

**The server starting and stopping**, with its version and build — which is how a deploy is recorded,
and what answers "what changed before this broke". The installer does not write into a file the
container owns and rotates.

**Deliberately silent:** a cursor pull that returned nothing (the replica already shows it), a
dictionary lookup that fell through to an online source (it is per keystroke), a job step that is merely
waiting (a render polls hundreds of times), and a healthcheck that answered 200.

## §4 · Reading it back

`python -m acervo.admin log` merges the three files and their rotations into one account in the order
it happened, each line marked `call`, `job` or `act`.

- **With an id**, everything filed under it as `rid=`, `id=` or `operationId=`. A job's id shows the
  job, its steps, and every model call and take made on its behalf.
- **`--failed`** keeps warnings and errors only.
- Otherwise the newest `--lines` (60).

`admin calls` reads `model-calls.log` alone, for timings: every timeout in the code is set from it
rather than guessed. `admin jobs list` shows recent jobs with their error and message, from the table.

## §5 · The rule for anything new

**A change that adds a way to fail is not finished until `admin log` shows that failure with its
sentence.** Most of it is free, which is the point of the design:

- **A request-path failure is an `ApiError` raised through the envelope**, never an error response a
  route builds itself. That is what logs it. Facts for the log go in `noted`, not into the message.
- **Work that outlives a request is a job** ([`jobs.md`](jobs.md)), and the runner logs it. Anything else
  that runs unattended — a tick, a thread, startup — writes its own activity line when it fails.
- **Every client of a companion service sends `X-Request-ID`**, and a route a companion calls home on
  adopts the id from its token.
- **A media file is removed only through `services/media.remove`.**
- **A new line is `key=value` from `activity.fields`**, emitted by a module that configures nothing, with
  a question in mind that a `grep` answers. A fourth file needs a reason the three cannot hold it.
- **Never a credential in a line.** Ids and the owner's own words are fine; a token, a key or a
  password is not, whatever was wrong with it.

`tests/unit/server/test_layering.py` enforces the ones that break with a single line: the three modules
every layer logs through are leaves; a module that speaks HTTP to a companion sends the id; nothing
under `services/` or `api/` unlinks a file itself; and no route builds an error response.

## §6 · What this is not

Not metrics, not tracing, not a time-series database, not a dashboard. One owner, one machine, a few
hundred jobs a month. Three rotating text files and an `admin` command that reads them back is the
right size.
