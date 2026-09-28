# Jobs · where and when the work runs

Everything runs in one server process on the NAS, against hosted providers. A save queues its
enrichment in the same transaction as the word, a runner inside the server does the work, and the
interface shows it and never does it. The same holds for headless capture, redraws, loops, stories,
naming the map's regions, the nightly corpus update, and keeping Anki up to date.

## Synchronous and asynchronous

The server is the unit that works, and the package layout draws the line.

- **`api/` + `services/` — synchronous.** Capture for review, chat, the graph and article routes,
  session, health, dictionary lookups, pressing play. Must work with everything else down.
- **`work/` — asynchronous, in the same process.** A durable `jobs` row per piece of work, and a
  runner that takes one at a time: a saved word's enrichment, a headless capture, a redraw, the
  nightly corpus update, a push to Anki and the hourly read back. It calls the same `services/` functions the routes call, so a job and a
  request are one pipeline entered from two places.
- **`jobs/` — batch work that runs somewhere else.** The dictionary compiler and the laptop image
  run, one-shot through `acervo-worker` or on the laptop, writing the graph through `client.py`.

> **DECISION: the request waits only while the owner is waiting on its answer to continue.
> Anything that lands on a stored record while the owner may walk away is a job.**

| Synchronous (the owner is waiting) | A job (the result lands on a record) |
|---|---|
| `POST /capture`: resolve and compose for review | the enrichment of a saved word |
| `POST /chat` | a headless capture |
| pressing play on a pronunciation | a redraw, a new brief, edit-and-draw |
| dictionary lookups | the nightly corpus update; loops and stories; Anki's push and read |

A redraw is a job even though the owner asked for it: the point was being able to leave the word
while it fills in, and a request that dies when the article closes is not that. **There are no
client retries anywhere.** A synchronous failure is shown and the owner presses again; the provider
chain's fall-through still happens inside the request.

## How a job works

**Work is started by the write that makes it necessary.** A save that creates a lexeme, or adds a
sense to one, queues an `enrich` job inside `repository.graph`, in the same transaction as the
record — so every writer is covered (`POST /articles`, `POST /graph`, a capture job's save, an
approved chat edit) and a client never asks for enrichment. A job's own writes create no lexemes or
senses, so they queue no enrichment.

**A push to Anki is queued the same way, and waits for the writes to stop.** Any write to what the
cards are made from — a job's picture or recording as much as an edit — queues `anki.push` in the same
transaction when the owner has it on, due a minute later (`jobs.enqueue_later`). A write while one
waits moves it on a minute, never past ten minutes from the first; a write while one runs queues one
more behind it. Study states, which a read writes, queue nothing, or every read would queue a push. **Inbox words are enriched on arrival**, before anyone has reviewed
them, so the owner opens a complete entry; the calls spent on a word later rejected are the accepted
cost. Editing a sense's text does not re-enrich: a picture that no longer
fits is the owner's call, through Redraw. A bundle import saves without enrichment, restores its
pictures, and then queues `enrich`, which skips what the restore put back.

**Why a durable job table is safe here.** The usual objections to a work queue, and what answers
each:

| The concern | The answer |
|---|---|
| A lost enqueue loses work. | The job is written in the same transaction as the word that needs it: both exist or neither does. |
| A job store is owner-scoped data, so it would replicate to every phone. | `sync_state` and `model_selection` are owner-scoped and never replicated; `jobs` is the third. |
| An in-process task dies on every deploy. | A deploy refuses while jobs are open, or cancels them when told to. Nothing crosses a version. |
| It makes the process that must stay responsive the orchestrator. | The work is waiting on remote APIs, and no database session is held across a model call. The load is a thread waiting on sockets. |
| A backgrounded tab freezes its timers. | True, and the argument *for* the server. |

Three properties keep it honest. **Steps are idempotent by derivation**: a job says *which word*, and
what that word still lacks — senses without a brief, `clipsSearchedAt IS NULL`, the recordings the
settings want — is read from the graph when each step runs, so a job run twice writes nothing the
second time. **Derived ids make writers converge**, so a person's action and a job on the same sense
cannot create two rows. And **"none" is a success**: a word with no picture or no clip is complete.

**The record.** One `jobs` table, owner-scoped, never replicated, owned by `repository/jobs.py`: kind,
subject, a small JSON input, state (`queued` → `running` → `done` | `failed` | `cancelled`), trigger,
steps with their progress and error codes, and a parent for the words a capture created. It is exempt
from the no-uniqueness rule like the other two, and carries one partial constraint: **at most one
open `enrich` per lexeme**. An enqueue that meets a queued one does nothing; one that meets a running
one sets `rerun`, and a fresh job is queued when it finishes. Finished jobs are kept 14 days; a
failure is kept until it is dismissed.

**`enrich` is clips, then pictures, then pronunciations.** Clips first because one call covers every
sense, it is the fastest, and it is the step that changes the example set; pictures second because
they are what the owner is waiting to see; recordings last because they are invisible and by then
the examples are final. Each step reads its own switch when it starts, so a setting changed mid-job
affects the next step, and a failed step is recorded and the job goes on.

**Retry and pacing live in the runner**, and a route makes one attempt. The chain decides *which* pair
answers — fall-through, hedging, cooldowns — and the runner decides *whether to ask again*: only on
the transient codes — `llm_rate_limited`, `llm_unavailable`, `llm_unreachable`, and the loop
generator's busy and unreachable —, resting rather than sleeping inside a request. A rest is 30 s
doubling to ten minutes, and starts again from 30 s when the step got somewhere before it was refused,
since that is an allowance refilling rather than a provider failing. Patience is per kind — six rests,
about 25 minutes, for most; twenty for a story, which is nothing until it is written. Each lane keeps a
calls-a-minute window where the allowance is known — pictures at one a minute, kept to rather than
discovered by 429 — and **a resting step's `waitingOn` names every provider that refused and why**, so
the row says "Gemini is overloaded; Cloudflare is out of allowance", never only "the provider is busy".
Exhaustion is recorded where the owner will look — a picture's `failureReason`, a step's error — and
the word stays usable.

**The runner** (`src/acervo/work/`) is a thread started from the application's lifespan, running one
job at a time because the allowances are the owner's own; a job that must wait gives up its turn.
Cancellation is checked between model calls. **Nothing resumes**: a job still running when the
process stops is marked interrupted, and Try again queues a new one. `work/` may import `services/`
and `repository/` but never `api/`, `services/` does not know jobs exist, and a route reaches jobs
only through `repository/jobs.py` (`test_layering.py`).

**A deploy never carries a job across a version.** Carrying state across means versioning it, and
the jobs involved take minutes. `./deploy.sh` reads the open jobs from the running server and
refuses; `--cancel-jobs` cancels them first; `--jobs open|cancel` asks without deploying. A job
queued between the check and the stop comes back interrupted — an accepted race.

**Telling the device.** `GET /events` is one authenticated stream with two messages: a job's state,
and "the owner's revision moved". On the second the device pulls; on the first it updates its map of
open jobs, rebuilt from `GET /jobs?open=true` after a reconnect. It is read with `fetch`, because
`EventSource` cannot send a bearer header. It carries notifications and never records, so a replica
still changes one way only, and without it the 60-second pull still converges.

**Headless capture is one job per submission**, because the caller cannot know how many words a text
holds — resolving discovers that. The `capture` job resolves, stops at a duplicate or composes and
saves each word to the Inbox through the same save, records each word's outcome, and creates one
child `enrich` per saved word. Interactive capture stays synchronous, because someone is reviewing
it.

**One timed run.** Settings ▸ Schedule holds one hour, read in `ACERVO_TIMEZONE`, and a switch per
step; at that hour one
`nightly` job runs its steps in order, so they can never compete for an allowance. A failed step does
not stop the next, a night the server missed runs once when it comes back, and missed nights do not
accumulate. There is no cron and no host scheduler. Reading Anki back is not a nightly step: it is
queued every hour, for an owner who has it on, by a tick of the runner the way the nightly run is.

**A new capability is a new job kind, and nothing else.** A kind declares a name, a subject (a
lexeme, a set of ids, or none), its steps and its output — always a record or a media file written
through `merge_graph` — and inherits queuing, retry, pacing, cancellation, the event stream and the
interface's progress for free. That is how loops and stories were added. A kind may do light CPU
work, an encode or a composite; anything heavy is out of scope for the runner.

## What a job leaves behind

**A job says what it did in a log as well as in its row.** `work/journal.py` writes one `key=value` line
when a job starts, one per step outcome and one when it ends, with the error and its sentence, to a
rotating file beside the database (`ACERVO_JOB_LOG_PATH`) — shaped like the model-call log, never
configured by the package that emits it, and dropped with a warning if it cannot be opened. It carries
`operationId`, the one id shared with the loop generator's container and the only thing that joins the
two trails. It exists because a failure recorded only in a job row's JSON is invisible from the command
line; `admin jobs list` shows recent jobs with their error and message.

**A failure's sentence must survive every hand-off.** The service keeps a provider's or generator's own
words beside Acervo's code, the runner copies the failed step's message onto the job, and the progress
line appends it rather than replacing it with a constant. Each of those three once threw it away, and
between them turned *"No samples cached for 'salamander'"* into *"the loop could not be made"*. What is
still silent is [`../plans/observability.md`](../plans/observability.md).

## A second machine

The always-on machine has no GPU, and the machine with one is not always on. Nothing needs the Mac
today, because the chosen providers are hosted. If a local model becomes worth running there, the
sketch of how it would claim work is [`../plans/nas-to-mac-job-queue.md`](../plans/nas-to-mac-job-queue.md),
and which models are worth it is the audit in
[`../plans/provider-management.md`](../plans/provider-management.md).

## Prefect

**Considered, and not used — deliberately kept in view.** The runner in `src/acervo/work/` does the
job an orchestrator would, because at this scale an orchestrator costs more than it returns: a Prefect server and its database are a few
hundred megabytes resident on a shared Synology, one more service for every deploy to start and
check, and one more thing a new user would have to run. One owner, one process and one lane need
none of it.

It stays on the table for two reasons. Orchestrating ML pipelines is a skill worth practising, and
this project is a natural place to do it. And a second machine, or pipelines that outgrow one lane,
would change the arithmetic. If it is adopted, the cautions written for it still hold:

- **It wraps the same functions.** Stages are ordinary Python in `services/`, already idempotent by
  derivation; Prefect would schedule them and never own their logic.
- **The request path must not know it exists.** Capture, review and the sync API work with the
  orchestrator down, as they work today with the runner stopped.
- **Measure the footprint first**, on the NAS, beside everything else that runs there.

## What the interface shows

The rule is that the interface **shows** work and never **does** it.

- **After Add or Save the word opens in page view**, whatever the device's default, because that is
  where reserved slots keep the layout still.
- **Cards are disabled while the word is enriching**, with the hint "Cards open when pictures and
  clips are ready", and re-enable however the job ends. There is no held snapshot and nothing
  re-flows under the reader.
- **One quiet progress line** under the article header, driven by the word's open job. It collapses
  when the job finishes; if a step failed it leaves one line — *2 of 3 pictures drawn · Try again* —
  until dismissed.
- **A clip has a reserved slot** while the search is pending, drawn as a quiet skeleton row. Found,
  the clip takes its place; nothing found, it settles into *No recorded example* for as long as the
  word stays open, so nothing jumps, and is absent next time, because for most words no clip is the
  expected answer; failed, *Couldn't search recorded speech · Try again*.
- **A picture keeps its reserved frame**; a failed draw shows its reason, Try again and
  use-my-own-picture; a redraw shows over the old picture and survives leaving the word.
- **Pronunciations get no slot.** They are a phase of the progress line, and press-to-record still
  works when one fails.
- **Settings ▸ Activity** lists open, queued and recently failed jobs with Cancel and Try again, and
  the word list marks a word that is still filling in.
