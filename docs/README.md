# Acervo

> *acervo* — *m.* — the body of words a person actually holds

A self-hosted, offline-capable store for the words *you personally chose to learn*, in every language
you are learning — and a set of consumers that turn it into study material: Anki cards, recorded
native speech, pictures, songs, stories, a map of what you know, an article you can argue with.

---

## One durable core, several disposable consumers

The failure mode of every tool in this space is that the word list is scaffolding for one output — a
deck, a reader, a mining workflow — so the list inherits that tool's assumptions and dies with it.
Acervo inverts this. **The vocabulary is the asset**; everything else is a renderer that can be
deleted and rebuilt.

```
CONSUMERS — disposable, rebuildable
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│ Anki+FSRS  │ │ Article    │ │ Loops and  │ │ Spoken     │ │ Meaning    │ │ Export     │
│ state flows│ │ chat       │ │ stories    │ │ clips      │ │ map        │ │ bundle and │
│ back in    │ │            │ │            │ │            │ │            │ │ Obsidian   │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      ▼              ▼              ▼              ▼              ▼              ▼
═══════════════════════════════════════════════════════════════════════════════════════
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ THE CORE — durable, synced, yours                                                   │
│   lexeme · sense · attestation · example · picture · recording · study state        │
│   a full replica on every device · tombstoned · revision cursor · multilingual      │
└─────────────────────────────────────────────────────────────────────────────────────┘
            ╎ consulted, never replicated
            ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ REFERENCE — large, read-only, outside the core                                      │
│   the spoken-usage corpus (its own service) · compiled dictionaries · model providers│
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### The invariants

- **Content flows out of the core; statistics flow in. Never both ways.** Anki does not own "is this
  word learned"; it reports, and the core decides. Bidirectional content sync between a structured
  store and a flashcard collection is the swamp that eats these projects.
- **The core is small enough to hold entirely, on every device, forever.** No pagination, no
  server-side query, no sync scoping. This is a design constraint, not a happy fact.
- **Reads are offline-first; writes are online-only.** Only the server mints a version, so `revision`
  alone orders records and there is no merge to implement ([`architecture/sync.md`](architecture/sync.md)).
- **Every generated record carries its provenance and the model that made it**, which is what lets the
  vocabulary be regenerated years later without touching a word the owner wrote.
- **A word with no picture and no recording is complete.** Media is an enhancement with its own
  lifecycle, never a blocker on a word being usable, reviewable or exportable — which is what makes
  best-effort, opportunistic enrichment safe.
- **The core and the reference layer share nothing** — not a database, a container or a backup
  policy. One is tens of megabytes of hand-curated relational data that must sync to a phone; the
  other is gigabytes of read-only text that must be searched. Every design pressure points the
  opposite way for each, and the reference side can be rebuilt, swapped or got wrong with no risk to
  the words.

### Sizing

Even **10,000 fully structured words** with no media are only tens of megabytes.

| Layer | Realistic ceiling | On disk | Lives where | If lost |
|---|---|---|---|---|
| **Core** | ~10,000 words | 20–50 MB | every device, in full | irreplaceable |
| **Recordings** | ~40,000 clips | a few hundred MB | server, and every device that keeps them | re-record |
| **Pictures** | ~30,000 files | 2–10 GB | server, fetched on demand | redraw |
| **Dictionaries** | ~1 M senses per language | 1–3 GB | server, and devices that install one | re-download |
| **Spoken-usage corpus** | millions of segments | gigabytes | its own service | the index rebuilds; the caption cache does not |

---

## The documents

**Architecture** — how the system is built.

- [`architecture/data-model.md`](architecture/data-model.md) — the records, their fields, and the rules every writer keeps.
- [`architecture/sync.md`](architecture/sync.md) — the replica, the cursor, online-only writes, media on the device.
- [`architecture/server.md`](architecture/server.md) — the Python service: layering, storage, auth, every route.
- [`architecture/jobs.md`](architecture/jobs.md) — what is a job, the runner, where work runs, what the interface shows.
- [`architecture/models.md`](architecture/models.md) — providers as catalogue rows, chains, and why no schema is ever sent.
- [`architecture/observability.md`](architecture/observability.md) — three logs, one id across them, and how to find out why.
- [`architecture/durability.md`](architecture/durability.md) — what protects the vocabulary, and how to restore.
- [`architecture/performance.md`](architecture/performance.md) — the measured write path.

**Features** — what the owner uses, and the design behind each.

- [`features/articles.md`](features/articles.md) — reading a word, and editing it as a YAML document.
- [`features/capture.md`](features/capture.md) — getting a word in: resolve, compose, review.
- [`features/photo-capture.md`](features/photo-capture.md) — tap a word in a photographed page.
- [`features/look-up.md`](features/look-up.md) — tap a word in a story, a loop or an article, and add it.
- [`features/article-chat.md`](features/article-chat.md) — ask about an article; its answer is a proposed revision.
- [`features/sense-images.md`](features/sense-images.md) — one picture per sense, briefed together per word.
- [`features/pronunciation.md`](features/pronunciation.md) — every spoken field, recorded and replicated.
- [`features/spoken-clips.md`](features/spoken-clips.md) — real native speech for a word, chosen by a model.
- [`features/word-selection.md`](features/word-selection.md) — a working pile of words to make something from.
- [`features/loops.md`](features/loops.md) — words and their translations over music, with LexiBeat.
- [`features/stories.md`](features/stories.md) — a short illustrated story from a handful of words, read aloud.
- [`features/meaning-map.md`](features/meaning-map.md) — a language's senses laid out by meaning.
- [`features/dictionaries.md`](features/dictionaries.md) — external dictionaries, compiled and read in place.
- [`features/anki.md`](features/anki.md) — cards out, review state back.
- [`features/export.md`](features/export.md) — the bundle, the Obsidian mirror, and import.
- [`features/standing-rules.md`](features/standing-rules.md) — telling every prompt something once.
- [`ml.md`](ml.md) — a tour of the machine-learning decisions across all of the above.

**Operations** — running it.
[`operations/deployment.md`](operations/deployment.md) ·
[`operations/vertex-setup.md`](operations/vertex-setup.md) ·
[`operations/anki-sync.md`](operations/anki-sync.md) ·
[`operations/cloudflare-workers-ai.md`](operations/cloudflare-workers-ai.md)

**Research** — surveys, measurements and readings that informed the design.
[`research/similar-projects.md`](research/similar-projects.md) ·
[`research/external-dictionaries.md`](research/external-dictionaries.md) ·
[`research/image-generation-research.md`](research/image-generation-research.md) ·
[`research/image-benchmark.md`](research/image-benchmark.md) ·
[`research/image-benchmark-finalist-results.md`](research/image-benchmark-finalist-results.md) ·
[`research/clip-selection-rounds.md`](research/clip-selection-rounds.md). Experiments with their
apparatus and results are in [`../experiments/`](../experiments/README.md).

**Plans** — what is still to do, including experiments not yet run: [`plans/`](plans/README.md).
