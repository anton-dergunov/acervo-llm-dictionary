# Sense images · one picture per meaning

Every sense of a word gets a picture, drawn to make that one meaning recallable. The pipeline is
`src/acervo/images/` — a brief writer and a renderer, standing alone on `src/acervo/models/` so a
server job and a laptop run share it; `services/images.py` binds it to Acervo; the `enrich` job draws
for a word that was just saved and the `image.redraw` and `image.rebrief` jobs for a picture somebody
asked for ([`../architecture/jobs.md`](../architecture/jobs.md)); `api/routes/images.py` keeps what a
person does directly — the settings, the readout, attaching their own picture, ruling a sense out. The
prompt iteration that settled the brief is [`experiments/sense-images/`](../../experiments/sense-images/README.md).

Four rules come before everything below:

- **Pictures are their own stage, after the article.** The article is written first, and its pictures
  are briefed afterwards from the validated article, in a call of their own. The two have competing
  objectives — lexical accuracy for one, visual specificity for the other — and sharing a prompt and
  an output budget makes the visual half lose. Keeping them apart also means every picture can be
  redrawn with a better model without touching a single gloss.
- **Style variety is pedagogical, not decorative.** Visual sameness across a thousand cards destroys
  distinctiveness, and distinctiveness is the only reason pictures aid recall at all.
- **A word with no picture is complete.** Drawing is best-effort and opportunistic, never a blocker.
- **A master is 1024×1024 WebP, displayed at most ~512 pt wide.** 1024 is the native output of the
  image models used, so nothing is upscaled and nothing generated is thrown away; capping the layout
  is what makes 1024 *sufficient* — pixel-exact at 2× on an 11" tablet, and about 2.8× on a phone,
  where the layout limits the width anyway. Full-bleed on a tablet would need ~1536 and upscaling.
  Smaller variants are derived from the master, never generated twice.

---

## §01 · The one idea

**The image exists to make one word recallable, not to illustrate a sentence.**

Every decision below follows from that. The picture is a mnemonic hook, so the target meaning must
be the loudest thing in the frame; the sentence is the scaffolding that tells the prompt writer what
scene to build, not a specification to reproduce faithfully. A beautiful, accurate picture in which
the word is one small element among many has failed at the only job it has.

Worked pair, from the reference entry:

| Sense | Anchor example | What must dominate |
|---|---|---|
| toxic fluid | *The snake injects venom through its hollow fangs.* | **the venom** — not the snake |
| extreme bitterness | *Her voice was full of venom when she spoke about her rival.* | **the bitterness, made physical** |

The second is the interesting one, and the one that decides whether this feature is worth building.
A prompt writer that renders "a woman looking angry" has produced a picture of *anger*, which the
learner already has a word for. A prompt writer that renders her words leaving her mouth as a thin
green corrosive vapour that blisters the tabletop between them has produced a picture of *venom*.
Externalising the abstraction as a physical presence in the scene is the core technique, and it is
written into the template as an instruction with examples, not left to the model to discover.

---

## §02 · What gets an image

> ### DECISION
> **One image per sense. None per lexeme.**
>
> **Because** the emoji already carries the lexeme-level anchor at zero cost, and a great many
> headwords — `venom`, `anhelar`, `caído` — have no single picture at all, while each of their
> senses does. `senseId: null` would be a lexeme-level card image; the shape stays in the schema and
> nothing generates it.

The anchor example, in order of preference:

1. an example whose `origin` is `attestation` — the learner met the word in this sentence, so the
   picture attaches to a memory that already exists;
2. `origin: manual`;
3. the first `llm` example;
4. no example at all — the definition and gloss are enough. Generate anyway. A sense with no example
   is not a signal to skip; it is a signal that the sentence cannot help.

The whole sense goes to the prompt writer — definition, domain, every gloss, every example, and the
lexeme's notes — with the anchor marked. The anchor drives the scene. It does not define it: the
writer may build a different scene when a better one exists for the same meaning, and is told so
explicitly. What it may not do is drift to a *different sense*.

---

## §03 · Two calls, and the batch boundary

```
article (validated, from the graph)
   │
   ├─ 1. prompt writer  ── one LLM text call per LEXEME, covering all its senses
   │        in:  headword, pos, register, language, notes, every sense with its
   │             examples, and a sampled style menu per sense
   │        out: one entry per sense — chosen styleId, anchor example id,
   │             a short scene brief, or a refusal
   │
   └─ 2. renderer       ── one image call per SENSE
            in:  the composed prompt = template + brief + style brief
            out: 1024×1024 WebP master
```

> ### DECISION
> **Batch the prompt writer across the senses of one lexeme, never across lexemes.**
>
> One call that sees both venom senses
> can deliberately make them look nothing alike — different style, different setting, different
> palette — which is the entire reason per-sense images beat one image per word. Batching across
> lexemes throws that away and makes a retry coarse.

The renderer is per sense because image models take one prompt and return one image.

---

## §04 · What is stored

> ### DECISION
> **`imagePrompt.prompt` stores the short scene brief. The full prompt sent to the image model is
> composed, not stored.**
>
> The full prompt is a pure function of things already recorded: `prompt` (the brief) + `styleId`
> (names a row in the tracked style table) + `promptVersion` (checksum of the tracked template).
> Storing it as well would store the same text twice and put a wall of instruction text in the
> article view, where the field is already rendered. This is exactly how `image_benchmark/jobs.py`
> already composes `f"{brief}. {style.suffix}"`, so there is one idea here, not a new one.
>
> The cost is honest and small: change a style's wording and yesterday's image is no longer
> byte-reproducible. `styleId` and `promptVersion` record that it changed, and pictures are
> regenerable by design. Reproducing the *file* was never the point; reproducing the
> *intent* is, and the brief carries that.

The brief is one or two sentences, written for a person to read: *"A viper's fangs sunk into a bare
forearm, a single luminous chartreuse droplet swelling at the fang tip and beading down, the snake
itself dim and out of focus behind it."* That is what the article view shows and what a "regenerate
this one, but…" flow will let you edit.

Existing fields, used as follows:

| Field | Value |
|---|---|
| `lexemeId` | the lexeme |
| `senseId` | the sense — always set |
| `prompt` | the scene brief |
| `styleId` | the style the writer chose from the menu |
| `seed` | derived from `senseId`, so a regeneration keeps the look — on a row whose `capabilities.image.seed` is `native`; see below |
| `modelId` | the model that *answered* the brief call, not the one asked first |
| `promptVersion` | checksum of `prompts/acervo_image_brief.md` + the style table |
| `imageRef` | relative path to the master, carrying a digest of its bytes, once drawn; null until then |
| `imageModelId` | the model that *drew* it, which under a chain need not be the first tried |

**The seed derives from `senseId`, not the lexeme.** A seed's job is to keep a picture looking like
itself across regenerations, and per-sense pictures make the sense the stable key: seeding both
senses of `venom` from the word would hand the same starting noise to two pictures the whole design
is trying to make look different. The retry counter is mixed in, so deleting a picture you disliked and
running again gives you a genuinely different one rather than the same picture back.

### A seed is only a seed where the provider takes one

Now that the picture is drawn through the catalogue, the row says whether it honours a seed.
Cloudflare does. Vertex does not — LiteLLM's transformer never puts one in the request — and OpenAI
rejects the parameter outright, so both rows declare `capabilities.image.seed: "ignored"` and the
answer comes back carrying a warning, which the record keeps under `run.usage.warnings`. The seed is
still stored, because it is what a re-run derives, but on those rows "a regeneration keeps the look"
is not true and the record says so rather than implying otherwise. Resolution is the same shape of
fact: Vertex takes an aspect ratio and its own size name, so the row carries
`params.image.imageConfig` and declares `size: "fixed"`.

### What an undrawn record means

On its own, `imageRef: null` would mean three things — "written, not yet drawn", "drawing was
refused" and "the owner does not want one here" — and work defined as *"which senses lack a picture"*
would retry a permanently blocked sense forever. Three columns separate them, and every other state
derives from them rather than being named:

| Field | Type | Notes |
|---|---|---|
| `attempts` | int | Render calls spent. Past a threshold nothing draws the row on its own again. |
| `failureReason` | string? | The last refusal, in the provider's words. Null on success. |
| `suppressed` | bool | The owner has ruled on this sense. Nothing ever regenerates it. |

*ready* = `imageRef` set · *pending* = empty with no attempts · *failed* = empty with a reason ·
*terminal* = failed at or past `MAX_ATTEMPTS`, which lives in `services/images.py` and not in the
record. That split is what keeps `attempts` a count: the row says what happened, the threshold says
what to do about it, and only the first of those is data.

> ### DECISION
> **An image prompt's id is derived from its `senseId`, in *every* writer.**
>
> `image_prompt_id(senseId)` — base-36 of a namespaced SHA-256 — exists in
> `src/acervo/images/ids.py` and in `web/src/ids.ts`, and the two are pinned against the same
> vectors from both sides. It is what makes a job and a person's action converge on one row with no
> coordination, what makes `suppressed` possible instead of a tombstone, and what limits a sense to
> one picture without a database constraint.
>
> "Every writer" includes the interface. A writer that mints a random id instead gives an imported
> sense two rows — an empty frame carrying the brief and a picture carrying none — and nothing fails;
> it just looks like a duplicate.

> ### DECISION
> **`suppressed` is not a tombstone, and could not be.**
>
> An image prompt's id is *derived* from its `senseId`. A tombstoned row is invisible to enrichment,
> which re-briefs the sense and mints **the same id** — so tombstoning does not prevent
> regeneration, it guarantees a collision at a higher revision. The row has to stay, visible, saying
> the owner ruled on this sense.
>
> The same derivation is what makes two writers safe with no coordination whatsoever: whichever
> arrives second finds the work done or is refused as stale.

A provider that looks at the prompt and declines is terminal for that wording: `attempts`
increments, `failureReason` records what it said, and it is deliberately **not** suppressed —
a different brief may well pass, which is what the edit-and-draw flow is for. A writer refusal *is*
suppressed, because that is a judgement about the sense rather than about a wording, and it becomes
a row with no brief so that nothing briefs the sense again. A rate limit is neither: nothing is recorded
against the sense, because an allowance running out says nothing about it and must not spend one of
its retries. A refused *credential* stops the run, since falling through would hide a mistake and
spend somebody else's allowance on it.

---

## §05 · Styles

A style is content, not code: `config/image-styles.yaml`, one row per style, loaded the way the
dictionary catalogue is. Each row carries an `id`, a `label` for the settings screen, a `brief`
spliced into the image prompt, a default `weight`, and a `mono` flag where the style is
monochrome — a monochrome style can quietly destroy a meaning that depends on colour, and the
prompt writer is told to avoid one when it does.

Deliberately absent from every one of these: *flat*, *schematic*, *simple shapes*, *silhouette*,
*icon*, *minimal*, *readable at small size*. The finalist benchmark's `warm_compact_scene` suffix
asks for "silhouettes that remain readable after reduction to 192 pixels" and its own report flags
that wording as a mistake. It is not carried forward. These images are looked at on a tablet at
roughly the size of a photo in a feed, and they should be worth looking at.

| id | Label | mono |
|---|---|---|
| `cinematic-photoreal` | Cinematic photograph |  |
| `golden-hour` | Golden-hour photography |  |
| `oil-painting` | Oil on canvas |  |
| `baroque-chiaroscuro` | Baroque chiaroscuro |  |
| `watercolour-storybook` | Watercolour storybook |  |
| `gouache-poster` | Mid-century gouache poster |  |
| `art-nouveau` | Art nouveau |  |
| `ukiyo-e` | Japanese woodblock |  |
| `anime-cel` | Anime cel |  |
| `manga-panel` | Manga panel | ✓ |
| `comic-book` | Comic-book ink and halftone |  |
| `pixar-3d` | 3D animated feature |  |
| `claymation` | Stop-motion clay |  |
| `papercraft-diorama` | Cut-paper diorama |  |
| `retro-futurism` | Retro-futurism |  |
| `film-noir` | Film noir | ✓ |
| `surrealism` | Surrealist dream logic |  |
| `vintage-botanical` | 19th-century engraved plate |  |
| `constructivist-poster` | Constructivist poster |  |
| `neon-cyberpunk` | Neon night |  |
| `pixel-art` | 16-bit pixel art |  |
| `charcoal-sketch` | Charcoal on toned paper | ✓ |
| `folk-naive` | Naïve folk painting |  |

Twenty-three, and the file is meant to be edited. `stained-glass` is not among them: leaded glass
dragged every scene into a church, and removing a style is editing the file, which is the point of it
being a file. Each `brief` is a full sentence of art direction,
not a label — `oil-painting` becomes *"thick impasto oil on canvas, visible brushwork, deep varnish
tones, old-master lighting"*.

> ### DECISION
> **Offer the writer every style the owner has left switched on, and let it pick. It may not invent
> one that is not on the menu.**
>
> **Because** a real style sometimes cannot express a real meaning — `vintage-botanical` has nothing
> to say about *bitterness*, and forcing it produces the bad image. The writer needs room to pass
> over a style that cannot carry the sense. Letting it *invent* one, though, breaks the record: an
> invented style has no id, so `styleId` stops naming anything and the look is not reproducible.
> The writer must return an id from its own menu, and `parse_reply` rejects the reply if it does
> not — an off-menu style is an error, not a nudge.

This replaces the sampled three-style menu, which round 1 abandoned, and the reason is worth keeping
because it is the opposite of what it looks like. With a menu of three the style is **assigned, not
chosen**: the scene gets written to fit whatever arrived at random, and the writer argues with a dice
roll instead of reading the sense. It shows up in the numbers — `baroque-chiaroscuro` drew three of
that round's fourteen images and *three of its seven rejections*, because a period style drags the
scene into its period and an architectural one into its architecture, neither of which the sentence
asked for. Random assignment buys variety at the cost of meaning, which is the wrong trade for the
only thing the picture is for.

Offered the whole table there is **position bias**: in file order, the writer reads the first row,
`cinematic-photoreal`, as the default (review round 2). The answer is not a shorter menu but a turned
one — `StyleTable.offer(rotate=lexemeId)` rotates by a stable
amount derived from the lexeme, which removes the anchor without taking the choice away and stays
idempotent on a re-run. Within one lexeme the writer is told not to pick the same style twice.

`cinematic-photoreal` has a role, but not a reserved slot: photorealism is the one
register that can carry any meaning at all — an abstraction, a thing you can photograph, a joke, a
threat — so it is where the writer lands when nothing else suits. The template says so in as many
words, and it carries the same weight as every other row.

### What the owner controls

Two settings, and deliberately not a third. Rounds 1–7 tried weights, a sampled three-style menu, and
per-style applicability hints; what survived is that the owner should say *which styles exist for
them* and *how adventurously to choose among them*, and nothing finer.

Both map onto parameters the code already takes, which is why the settings screen adds no mechanism:
a style switched off is a weight of zero in `StyleTable.offer(weights)`, and *boost variety* is
`StyleTable.hints()` on or off. They are stored as the **off** list rather than the on list, for the
reason the dictionary switches record — a set of switched-*on* ids leaves anything added later
permanently silent, so a style added to `config/image-styles.yaml` must be on by default.

| Control | Shape | Default |
|---|---|---|
| **Draw pictures** | one switch, and it governs everything that draws *by itself* — the `enrich` job of a word that was just saved, and a backfill. It deliberately does not gate the per-sense buttons: switching it off is how you get a word with no pictures and then add the one you want by hand. Checked by the two drivers rather than by the routes, for that reason. | on |
| **The styles** | one switch per style, on or off. A style switched off is never offered. At least one must stay on — with none there is nothing to draw with, and "draw nothing" is the switch above rather than an empty list. | all on |
| **Boost variety** | one switch. On, each style is presented with a few of its example subjects, sampled per word, which pushes the writer toward styles it would otherwise pass over. Off, styles are offered on their own descriptions alone. | **on** |

No per-style weight, no sampling temperature. A weight is a number nobody can set meaningfully
without running a few hundred images and counting, which is what the histogram in
`experiments/sense-images/` is for and not what a settings screen is for.

**Boost variety defaults to on** because both modes were reviewed and both produce good pictures.
Round 6 (off) was judged *"on point, and not uniform"*; round 7 (on) was judged less predictable and
equally apt, with two styles appearing that had never been chosen in 300 images. On is the more
interesting of two good options, and the switch exists because the distinction is genuinely a matter
of taste rather than of correctness.

**These are per owner, and therefore server state.** Generation runs on the server, so unlike the
editor's wrapping preference they cannot live on the device. They live in `image_settings`, an
owner-scoped table that is never replicated — the same shape and the same three-state doctrine as
`model_selection`, where **no row means "follow the deployment default"** rather than meaning a gap.

---

## §06 · The prompt template

`prompts/acervo_image_brief.md`, tracked text, read at request time — content, not code, the same
rule as `acervo_compose.md`. Sketch of what it must say:

**The job.** You are writing a scene brief for an image model. The picture is a memory hook for one
word in one meaning. A learner who does not know the word should be able to look at the picture and
guess the meaning.

**The accent rule.** Name the one thing that must dominate the frame, and make the whole scene point
at it — scale, composition, light, focus, colour contrast. Everything else is subordinate and simple
enough not to compete. The target meaning is never one detail among equals.

**Exaggerate.** Theatrical, dramatic, physically impossible if it helps. This is expected, not
tolerated. A picture that is merely accurate is a worse mnemonic than one that is memorable.

**Abstractions get bodies.** When the meaning is not a thing you can photograph — bitterness,
longing, disgrace — give it a physical presence in the scene: a substance, a light, a weight, a
deformation of the space around it. Two worked examples ship in the template, both for *venom*.

**Never render text.** No letters, captions, signage, labels, logos, watermarks, pseudo-text — and
above all never the vocabulary word. A flashcard with the answer written on it is broken.

**Say what you chose.** Return the styleId, the anchor example, the brief, and nothing else.

### Forbidden, and the line

Refuse rather than produce: hate insignia of any kind, Nazi and SS symbols above all; sexualised
imagery; exposed genitals or breasts; nudity; any depiction of a child in an unsafe or suggestive
context; graphic gore; desecration of religious symbols where the word is not itself about them;
identifiable real people; real brand marks.

Permitted, and this half matters as much: rage, contempt, disgust, fear, grief, drunkenness, insult,
threat, vulgar register, implied violence. `atrocity`, `boludo`, `dumb`, `snake bites man` all get
pictures. The line the template draws is **depict the emotion or the situation, not the anatomy and
not the atrocity in graphic detail**. A safety rule that quietly refuses half of a learner's real
vocabulary is a broken feature, not a cautious one.

> ### DECISION
> **A refusal is a successful outcome, and it is not retried.**
>
> §09 already says `none` is a success. The writer returns `refused: true` with a one-line reason,
> no `imagePrompt` row is created, and nothing comes back for it. A provider-side block at drawing
> time is different: the row exists, `attempts` increments, `failureReason` records the provider's
> words, and drawing on its own gives up after a threshold.

---

## §07 · Output format

Master: **1024×1024 WebP, quality ~88**, from Gemini's 1K PNG output. This is §09's decision
unchanged. Square because both consumers — the article fold and an Anki card — want square, and
because it is the model's native output so nothing is upscaled or thrown away. Easy to revisit; it
is one line of config.

Derive variants from the master, never generate twice: 768 for Anki if deck size bites, 256 for a
list thumbnail.

---

## §08 · Where images live

> ### DECISION
> **A static media directory served the way compiled dictionaries are, with `imageRef` holding a
> relative path.**
>
> `ACERVO_MEDIA_PATH` is served at `/api/acervo/media/{path}`, behind bearer auth and answering byte
> ranges, exactly as dictionary artifacts are, and outside anything the service worker precaches. It
> keeps the database small, and the record is what says where its picture is.

Path shape: `images/<lexemeId>/<imagePromptId>-<digest8>.webp`, addressed by the record that owns it
**and by the bytes it holds** — a truncated SHA-256 of the stored master, the way a pronunciation's
file name is. A regeneration is therefore a new name, and the file the row used to name is removed
once the row naming its successor has landed; at most one picture per sense is kept.

The digest is not decoration. A device caches a picture under its reference, so a name that stayed
the same across a redraw would leave the device showing the picture that had just been replaced, and
an invalidation beside it would race the `revision` frame. With the bytes in the name there is nothing
to invalidate: the new picture is asked for under a name nothing has ever held. Nothing parses this
string — it is built in `images/ids.py`, stored, joined onto the media directory and unlinked.

Three consequences:

- **The route needs auth, so `<img src>` cannot fetch it directly.** `web/src/media.ts` fetches with
  the token and hands the element a blob URL — exactly what the dictionary reader does.
- **Offline-first reads apply to pictures too.** `web/src/mediaStore.ts` is a **third** IndexedDB
  database alongside `dictionaryStore.ts`, holding whole files as Blobs and deliberately separate
  from the replica so neither wipe touches the other. Not in the replica: per-record overhead and a
  wipe on account change are both wrong for megabytes of pictures.
- **The media volume is read-write in both the worker and the server, and dictionaries are not.** A
  dictionary is compiled only by the worker, so the server has no reason to hold a pen; a picture is
  drawn by whichever of the two was asked, and the file and the row naming it must be written by the
  same party.

**The transfer bundle carries the reference by default, and the bytes when asked.** `imagePrompts`
round-trip through the YAML projection, so `prompt`, `styleId` and `seed` survive an export/import.
`imageRef` and `imageModelId` deliberately do **not**: they are facts about the server that drew the
picture, and `imageRef` embeds a lexeme id that will not exist after import — keeping it imported a
live-looking reference to a file nobody has.

The bytes are an opt-in `media/<language>/<slug>-<n>.webp` directory. Named after the word file so
the two pair by eye, and suffixed by sense order rather than by prompt id, because a bundle carries
no ids a person or a second account could use — which also makes position the only pairing a restore
can key on. It defaults to off: a bundle should stay a text archive you can read, pictures are
regenerable by design, and the briefs that produced them are in the word file either way. It is the
one export that is not offline-capable, which the panel says plainly.

> ### DECISION
> **The import puts the pictures back, through the same route that attaches one by hand.**
>
> An export whose pictures could not be read back would restore every sense with its brief and
> *"Not drawn yet"*: an archive rather than a backup, and a backup is what the export is for.
>
> It is not a second writer, because a picture is not a graph record. `saveArticle` writes the word,
> and then each picture goes to `PUT /images/senses/{senseId}/picture` — the route a person uses to
> attach one. One pipeline, two callers, exactly as with capture.
>
> `transfer.ts` still holds no transport: it *names* the pictures and takes a callback, and
> `TransferPanel.tsx` supplies it along with the zip, because owning the zip and the browser's file
> handling is already its job.

What travels with the bytes is `imageModelId`, and the distinction is the point. `imageRef` is a
path on the server, embedding a lexeme id that will not exist after import, so it is stripped —
keeping it imported a live-looking reference to a file nobody has. `imageModelId` is not a path: it
is the name of the model that drew this picture, a fact about the past exactly as an example's
`origin` and `modelId` are. Provenance travels in a bundle; server paths do not.

That is also what tells a **restore** from a picture the owner chose, on one route. Naming the model
means the row keeps its provenance and stays replaceable; naming none means the owner picked this
file, so `imageModelId` is empty — the way an example the learner wrote carries no `modelId` — and
the row is `suppressed`, because choosing a picture is choosing it. Without that distinction every
restored picture would read as hand-chosen, and nothing would ever redraw two thousand of them.

The import **pulls** after restoring — in batches, and once at the end — and that is not an
optimisation. A word reaches the replica by itself, because `saveArticle` merges what the server
answers; a picture does not, because the image route wrote it. Without the pull an imported article
would show empty frames until the next scheduled sync, which reads as a failed import rather than a
lagging one.

A picture that cannot be put back is reported and its word is kept: the words are the part that
cannot be regenerated. And a word the import skips as already held keeps its own picture, for the
same reason it keeps its own text — an import must never cost you what you did after the export.

---

## §09 · Where the work runs

**Drawing is a step of the server's `enrich` job** — clips, then pictures, then recordings — queued
by the save that created the word or added a sense ([`../architecture/jobs.md`](../architecture/jobs.md)).
The step writes one brief for the word, then draws one picture per sense, each reading the owner's
switch when it starts. What a sense still lacks is asked of the graph every time the step runs —
"which senses have no picture, no suppression, and attempts to spare" — so a job run twice draws
nothing. The picture lane keeps to the provider's known allowance, one a minute, rather than
discovering it by 429.

**The actions a person asks for are jobs too**, so leaving the word does not lose them, and they are
named rather than guessed because they cost different things: **draw again** (`image.redraw`, one
image call with a fresh seed), **write a new brief** (`image.rebrief`, one text call that rewrites
every sense of the word), and **edit and draw** (`image.redraw` carrying the edited prompt, no text
call at all). The dialog reads the composed prompt from `GET /images/prompts/{id}`.

| Route | |
|---|---|
| `POST /jobs` with `image.redraw` or `image.rebrief` | Queue a redraw, an edit-and-draw, or a new brief |
| `GET /images/prompts/{id}` | The brief, the style and the composed prompt, for the dialog |
| `PUT /images/senses/{id}/picture` | The owner's own file as a raw body, or a picture restored from a bundle |
| `DELETE /images/prompts/{id}` | Removes the picture and sets `suppressed` |
| `GET`/`PUT /images/settings` | The two settings, plus the style table |

> ### DECISION
> **The server writes the file *and* the row, and this is not an exception to the capture rule.**
>
> Only headless transports ask capture to save, because a draft is a proposal for a person to review
> and the interface is where reviewing happens. Drawing has no review step and produces a binary the
> client cannot make and cannot put in the graph. So the server writes both — through
> `repository.graph.merge_graph`, the route every other writer uses, with the same validation and
> the same revision allocation. Calling it an exception would invite a second one.

### Where the pipeline lives

`src/acervo/images/` stands alone on `src/acervo/models/` and imports nothing else of Acervo's — not
settings, not the graph, not `acervo.errors` — and `tests/unit/server/test_layering.py` enforces it.
That independence is what lets a route, a job and a laptop run share one pipeline: `api/` may not
import `acervo.jobs`, and routing through `services/` to reach `jobs/` would make the request path
transitively import `acervo.client`, the HTTP client of its own service.

`ArticleView` is the reuse that matters. `build_articles` takes the `changes` mapping the graph route
speaks, so a laptop run feeds it a `client.pull_graph()` payload and `services/images.py` feeds it
rows the repository projected — one view model, two feeders.

### The laptop run

`jobs/images/` keeps what is genuinely batch and runs on the laptop, where prompt work happens: a run
directory that *is* the queue, a concurrent runner, `verify` and `publish`, behind
`scripts/generate_images.py check | plan | run | verify | publish | sheet`. It reads the graph through
the same cursor route the app uses and writes it through `acervo.client`, so a batch's write path is a
client's write path.

- **Which provider draws is a chain**: the `--brief-chain` / `--image-chain` flag, else the chain the
  owner chose (fetched from `GET /models`, since `jobs/` may not read the owner's chain directly), else
  the catalogue's order.
- **A run is resumable.** Output is `output/images/<runId>/`: a manifest, and per job a JSON record —
  brief, composed prompt, style, seed, models, timings, cost — beside its WebP, keyed by the real
  derived id and skipped if already complete.
- **`sheet` writes one self-contained page** sized for a tablet — word, sense, gloss, anchor, style,
  brief, image — with accept and reject writing a decisions file.
- **`verify` is the gate** for internal consistency, and **`publish` refuses a run whose senses this
  account does not hold** rather than writing half of it.

**Measured on the first full run** (Spanish and English, Vertex):

| | Spanish | English |
|---|---:|---:|
| Senses in scope | 1,437 | 851 |
| Drawn | 1,437 | 848 |
| Refused by the writer | 0 | 2 |
| Blocked by the provider | 0 | 1 |

About **$77** at ~$0.0336 an image — a configured benchmark constant rather than a checked bill; what
the run measured is ~1,120 output tokens per image — over roughly 38 hours at about one image a
minute. **Quota, not cost, was the binding constraint**: three workers spent most of the run waiting,
and a quota increase in the Cloud console is the single highest-leverage fix for a large run. Two rules
came out of it and are built in:

- **Pace every model, not just the expensive one.** One text-quota refusal on an unpaced brief call
  silently lost every sense of that word; the brief writer waits out an exhausted chain, and retries
  are on exactly the three transient codes.
- **A terminal outcome must be recorded as terminal.** A writer refusal and a provider block are both
  finished; unrecorded, they were re-planned on every run. That is what `attempts`, `failureReason` and
  `suppressed` are for.

---

## §10 · Settled

Settled:

| | |
|---|---|
| What `prompt` stores | The brief. It is what the article shows and what the dialog lets you edit; the full prompt is composed on demand and never stored. |
| Scope | Every sense, no cap. |
| Style menu | Every style the owner left on, rotated per lexeme; the writer picks and may not invent. |
| The two settings | `image_settings`, an owner-scoped table never replicated — `model_selection`'s shape and its three-state doctrine, where no row means "follow the deployment default". |
| Style storage | The switched-**off** ids, never the on ones, so a style added later arrives on. |
| Aspect | 1:1. Square suits the article and an Anki card, and it is the model's native output. |
| `attempts` / `failureReason` / `suppressed` | Columns, with the threshold in code. Derived states, no status enum. |
| Where a picture is shown | Under the sentence it was drawn from, which is what `exampleId` records; under the sense when it names none. |
| Backups of the masters | An opt-in `media/` directory in the export, plus whatever backs up the media volume. |
| Budget | Uncapped. |

Presentation is deliberately plain: a square frame under the sentence, a fold with the brief and the
model, and the controls, with every state occupying the same box so nothing reflows when a picture
arrives. Pronunciation ([`pronunciation.md`](pronunciation.md)) reuses the media directory, the route
shape and the job step.

## §11 · What this deliberately does not do

- No local diffusion fallback. Both calls now go through `src/acervo/models/`, so which provider
  draws is a chain of catalogue rows rather than a constant — `--image-chain cloudflare,vertex`
  carries the steady state on Cloudflare FLUX.2 Klein 4B and falls through to Vertex when its daily
  allocation stops. A *local* model is a different matter: the research measured 2.5–10 GiB of
  unified memory and one image per child process, and the machine with the GPU is not the machine
  that is always on. That is [`../plans/nas-to-mac-job-queue.md`](../plans/nas-to-mac-job-queue.md)'s territory, not this one's.
- No automatic quality gate. The benchmark report sketches one — luminance and colour variance,
  entropy, edge density, dominant-colour share — and Gemini's 0/12 rejection rate does not justify
  building it. It becomes interesting when generation moves to a less reliable model.
- **No lexeme-level card images.** `Article.images` is still derived by `selectors.ts` and still
  rendered nowhere, because §02 decided nothing generates it. Left alone rather than removed: it is
  the shape a card image would take if one is ever wanted.
