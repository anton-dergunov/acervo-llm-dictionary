# Capture · getting a word in

Capture is make-or-break: past a few seconds you stop doing it, and every other feature is moot. A
word arrives as a scrap of text — a word, or a sentence containing it — and leaves as a complete
article the owner reads before it is saved.

---

## One server pipeline, several thin transports

> **DECISION: one capture pipeline on the server. Every way in is a thin client against it.**

Transports have very different lifespans and platform constraints, while what they submit is the same:
some text, optionally the sentence around it, a source URL and title, a headword hint. Keeping the
intelligence on the server means a new transport is an afternoon and losing one costs nothing.
**Adding a transport must not add a second pipeline**: every path goes through
`services/capture/pipeline`.

| Transport | Route | What it is for |
|---|---|---|
| **Add ▸ Text**, in the app | `POST /capture`, then the ordinary save | the floor — a word you *heard* has no source to share from |
| **Add ▸ Photo** | `POST /photo/read`, `POST /capture/resolve`, then `/capture` | a word met on a printed page or a sign ([`photo-capture.md`](photo-capture.md)) |
| **"Add to my words"** on a dictionary entry | `/capture` with the entry as `reference` | promoting an external entry ([`dictionaries.md`](dictionaries.md)) |
| **A notes file**, `scripts/ingest_vocabulary_file.py` | `POST /captures`, a job | walking a messy vocabulary file into the Inbox |

The share sheets, a browser extension, an iOS Shortcut and the rest are surveyed, with the experiments
that decide between them, in [`../plans/capture-transports.md`](../plans/capture-transports.md). An iOS
Shortcut cannot end in Acervo's review screen — iOS has no deep link into an installed home-screen web
app, whose storage is separate from Safari's, and no share target for one — so on iOS a transport
either posts and walks away into the Inbox or confirms inside Shortcuts first.

**Capture is online by nature.** Building an article means calling a model on the server, so there was
never a capture that worked on a plane; online-only writes take away nothing it had.

## Resolve, then compose

Two model calls, assembled on the server from tracked prompts (`prompts/acervo_resolve.md`,
`prompts/acervo_compose.md`):

1. **Resolve** decides what the text is about — which word or phrase, which language, which of the
   sentences are the learner's own, and, walking a file, how many lines that entry occupied. That answer
   is what makes the rest safe: a language with no `vocabularies` record is refused before anything is
   generated, and a word the account already holds returns the entry it has rather than a
   near-duplicate. The submitter may name the word (`headword`), which is a hint resolve still
   corrects, not a bypass of it.
2. **Compose** writes the article from the definition and the learner's own sentences, choosing from
   the owner's real topics and glossing into the languages the vocabulary asks for. Every prose field in
   its prompt states which language it is written in. The owner's standing rules (Settings ▸ Rules,
   [`standing-rules.md`](standing-rules.md)) are appended to it, and an optional request in Add
   ("Anything to ask the generator") travels with it.

The model answers in JSON mode and the shape is checked by Acervo's own parser — no schema is ever
sent ([`../architecture/models.md`](../architecture/models.md)). Resolve and compose run on the
owner's `text` chain; the photo tap's resolve runs alone on the faster `quick` chain.

**Provenance is carried by the records, not a flag.** The learner's sentence is kept verbatim as an
`attestation`, and the example drawn from it says so and names it; an example the model invented
carries the model that wrote it. Both are created by one save, which is why a document that names no
stored entry may carry ids its producer minted.

### Grounding on a reference

A capture may carry a **reference** — a dictionary entry the owner chose to promote — with one of two
treatments: *stay close to the reference*, carrying over its senses and no others, or *fill in the
gaps*, keeping what it says right and condensing it. Grounding demotes the model from knowledge source
to selector and formatter, where hallucinating a meaning is much less likely, and it recovers the
senses a model silently drops: asked cold, a model gives the two obvious meanings of `picar` and not
the other five. A reference is grounding and nothing else: it never becomes an attestation, because a
dictionary's examples are not places the owner met the word. Whether grounding makes better articles
than no grounding is unmeasured, and the evaluation is planned in
[`../plans/quality/article-quality.md`](../plans/quality/article-quality.md) §6.

## A proposal, reviewed as the article it will become

`/capture` writes nothing. It returns an `ArticleDraft`, and **review is reading the rendered
article**, not its serialisation: the Add view is Text / Photo / Article / YAML and processing lands on
Article, rendered by the same component a stored word is read in. YAML sits behind it as the edit
surface and stays the document of record there; the Article tab is derived from the editor text, so
the preview and the editor cannot drift apart. The owner can also ask about the proposal before saving
it — the article conversation works on an unsaved draft, and one sentence changes one thing rather
than regenerating everything ([`article-chat.md`](article-chat.md) §8.4).

Saving is `saveArticle(parseArticle(text))`, one round trip to `POST /articles` — exactly what saving a
hand-typed document does, so a generated entry and a typed one are indistinguishable downstream. The
save queues the word's enrichment ([`../architecture/jobs.md`](../architecture/jobs.md)), and the word
opens in page view while its clips, pictures and recordings arrive.

## A word already held is added to, never duplicated

The same word arrives again and again — that is what reading a lot looks like — and the second
encounter is often *better*: a sharper sentence, a sense not met before. So a capture of a held word
stops at the duplicate and offers to **fold it in**: it opens the stored article and asks the article
conversation to add the new sentence, with no extra model call, since resolve has already separated
the learner's own sentences from anything else. `suppressed` is what keeps a *rejected* word from
arriving forever, and this is what keeps an *accepted* one from arriving twice.

## The Inbox

```
captured → processing → review → active         (you added it: you read it before saving)
captured → processing → inbox  → active         (it arrived unattended: a file, a headless transport)
                          │
                          └── suppressed
```

**Processing is immediate even when approval is deferred**: the senses, glosses and examples are fully
determined by the word and its sentence, so by the time the owner looks, the article is built and
waiting. An entry saved from Add is an ordinary word; the Inbox holds only what arrived without anyone
reading it. It has a door — **File it** on an article and **File all** on the tab, both an ordinary
write of `status: active` — because a few hundred words can land there at once. Review is of the whole
entry, so there is no approval flag on individual records.

**Headless capture is a job.** `POST /captures` takes one submission and answers with a `capture` job,
because the caller cannot know how many words a text holds; the job walks it entry by entry, stops at
words already held, saves the rest to the Inbox through the same save, and queues each one's
enrichment. The notes-file script submits a chunk at a time and follows the job, holding no prompt, no
pacing and no retries of its own; it only remembers how far the server got, checkpointed outside the
notes, and leaves the file alone unless told to consume it.
