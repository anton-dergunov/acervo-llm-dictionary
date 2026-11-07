# Sync · a full replica on every device, writes only through the server

> **DECISION: every read is served from the device's replica and works with the server unreachable.
> Every write — create, edit, delete, reset — is a synchronous round trip that fails loudly when
> offline and leaves the replica untouched. Nothing is ever queued.**

The server is the durable store; IndexedDB holds a complete owner-scoped replica on each device and is
the only store the interface reads. The records are [`data-model.md`](data-model.md); the server side
is [`server.md`](server.md).

---

## Why writes are online-only

Almost every write in Acervo creates or revises a rich article, and almost all of it originates on
the server anyway: capture and chat call a model, enrichment is a server job, study state arrives from
Anki. What is left for a device to originate by hand is rare — setting a word aside, correcting a
generated sentence. Merging two independently edited versions of an article has no honest answer, and
the machinery to attempt it would buy a case that barely occurs.

So the conflict-resolution surface is deleted rather than implemented, and it pays for itself twice.
**Only the server mints a version of a record, so `revision` alone totally orders versions**: there is
no timestamp comparison anywhere in the merge path and no clock skew to tolerate. And a concurrent edit
is simply refused — an interactive save can be retried, where a queued one could not.

| | Acervo | Why |
|---|---|---|
| Offline writes | **Refused, with an error** | Rich records; merging two edited articles has no honest answer |
| Merge key | **`revision` alone** | Only the server mints versions |
| Concurrent edit | **Refused — `409 stale_record`** | An interactive save can be retried; a queued one cannot |
| Pull and push | **Separate** | There is nothing to push at poll time |
| Partial failure | **All or nothing per batch** | One save is one article; half an article is worse than none |
| Pending queue | **Does not exist** | Nothing is ever unsent |
| Rebuilt server | **Stop and ask** | Nothing is re-pushed, so wiping the replica could destroy the last full copy |

---

## The cursor is a counter, not a clock

Every replicated row carries `revision`: a position in one strictly increasing per-owner sequence,
shared by every replicated table. A device stores the highest revision it has received and asks for
`revision > cursor`.

A timestamp cursor would lose records: one written while a pull is in flight is stamped *before* the
moment the pull finishes, so asking next time for "everything since then" skips it — permanently,
silently, and only on the unlucky device. A counter has no such gap.

The counter lives in a `sync_state` row per owner, in a table that is **never replicated**, because a
counter only the server may advance must not be something a stale device can overwrite. That row's id
is the **`datasetId`**: rebuild the database and every outstanding cursor is invalidated for free.

**Every writer allocates through `repository.graph`**, in the same transaction as the record it
numbers — routes, jobs, the Anki consumer and the seeder alike. A record left at revision zero is
invisible to every pull, forever, so no writer may be able to forget.

---

## The protocol

**Pull — `GET /api/acervo/v1/graph?since=<cursor>`** returns `{schemaVersion, datasetId, cursor,
serverTime, changes}`, where `changes` holds every collection's records above the cursor, tombstones
included. `since=0` returns everything, so a first sync and a steady poll are one code path.

**Push — `POST /api/acervo/v1/graph`** carries `{schemaVersion, deviceId, changes}` and applies it in
one transaction, in merge order. Each record states the revision it was edited from; if the stored
revision has moved on, the whole batch is refused with `409 stale_record` naming the entry. The answer
is the canonical stored rows plus the new cursor, so the screen repaints at once. An article is saved
through `POST /articles` instead, which diffs a parsed document on the server and sends `base` — the
revision this replica holds of each of the entry's records — so an edit made from a stale copy is
refused rather than laid over a newer one, and only records this device could have seen are
tombstoned.

**Both requests carry `schemaVersion`.** A mismatch is a `409` that puts the device in a terminal
*blocked* state: it stops syncing and says the app needs updating, while reading carries on.

**When to pull.** Every 60 seconds while visible, on focus, on regaining the network, and immediately
after a write — single-flight throughout. The server also streams `GET /events`, which says *that*
something changed — a job's state, or the owner's revision — and never carries a record; on a revision
the device pulls. So a replica changes one way only, the cursor pull, and without the stream the poll
still converges. A failed sync is not an error to act on: it is a sync that happens later, and the
interval is the retry.

**Applied records, their dependent tombstones and the cursor are one IndexedDB transaction.**

---

## The replica on the device

**Who talks to the server.** Interface code reads and writes only through `AcervoRepository`
(`repository.ts`), never directly against the server. `domain.ts` is the canonical client model and
`localDatabase.ts` persists the replica. `sync.ts` owns every call to the graph routes — the cursor pull,
the write route and the reset — and the sync schedule and status; the repository reaches the write
route only through the transport `sync.ts` attaches to it. `selectors.ts` derives every view model from
the graph and is pure, so the interface is testable without a replica.

- **It is immutable and shared.** A merge replaces the records and collections it changes and shares
  the rest; `snapshot()` hands out the same object until something changes; a merge validates only the
  incoming records, falling back to the whole graph only when a record another depends on moved.
  Records are frozen outside production so a test catches a mutation. Never clone or validate the
  whole replica on a save, a pull or a repaint: at 1,700 words that costs ~190 ms per saved word and
  grows with every word ([`performance.md`](performance.md)).
- **The interface is not drawn until the replica has been read.** A cold start shows the launch screen
  (`Launch.tsx`, with the same markup in `index.html`) rather than a shell reporting an empty
  vocabulary — "All 0" about a vocabulary of 1,700 — then reopens the place `lastPlace.ts` remembered;
  Settings ▸ Sync says how long that took.
- **A replica belonging to another account or another `LOCAL_SCHEMA_VERSION` is wiped and pulled
  again**, into storage — never kept in memory instead, or every cold start would download the whole
  vocabulary again while showing none of it. Memory is only for a device whose storage cannot be opened
  at all. Replicas are never transformed.
- **A replica whose `datasetId` no longer matches the server is not wiped.** The server was rebuilt or
  restored, so this replica may be the most complete copy left: sync stops, the device explains what
  happened, and nothing destructive happens until the owner chooses
  ([`durability.md`](durability.md)).

## Resetting

Two destructive actions, and they are not the same action:

- **Replace this device's copy with the server's** — discard the replica and pull from zero. The server
  is unaffected. After a dataset change it asks for `REPLACE` to be typed, since the device may hold
  more than the server.
- **Delete all words** — tombstone every word and everything hanging off it, including loops and
  stories, on the server, replicating everywhere. Vocabularies, topics, the account and the dataset
  identity remain. It quotes the live counts and needs `DELETE` typed, and it never removes a row, so
  even this stays undoable.

---

## Media

**Pictures are not replicated; recordings are.** All media lives on the server under
`ACERVO_MEDIA_PATH` and is fetched behind bearer auth as a blob — which is why a picture is not an
`<img src>` — and cached in `mediaStore.ts`, a store separate from the replica.

A spoken headword is a couple of kilobytes: a vocabulary's recordings cost about what its text does,
while its pictures cost two orders of magnitude more. So a recording is a record like any other, and
the device's `fill()` (`pronunciation.ts`) brings down the audio the replica names after each sync —
which is what makes a word recorded on another device, or a story, play on a plane. Keeping them is a per-device switch, on
by default; keeping loop tracks, which cost more than a vocabulary's clips and text together, is off
by default. The text of the vocabulary works on a plane, and so does hearing it; the pictures do not.

**Every media file name carries a digest of its bytes**, so a redrawn picture or a re-recorded clip is
a *new* reference and the file its predecessor named is removed once the new row has landed. That is
what lets `mediaStore.ts` be a plain cache with no invalidation at all: a reference names immutable
bytes, and a device holding an old one simply misses. Do not add a cache keyed on anything else.
