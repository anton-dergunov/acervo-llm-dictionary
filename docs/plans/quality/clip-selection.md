# Clip selection · tuning the prompt, then curating what it picks

Two halves of one question — are the clips an article shows the right ones? Part 1 measures and tunes
the **shipped** selection prompt, the one every owner gets: an experiment, and the research half. Part 2
is the **product** half, for when the default is good but not to the owner's taste: saying what they
want, and replacing a clip that is wrong. Run Part 1 first; Part 2 is not wanted until there are enough
clips to be annoyed by the wrong ones.

## Part 1 · Tuning the shipped prompt

**Status:** Unstarted. The selection prompt this experiment tunes is built
([`../../features/spoken-clips.md`](../../features/spoken-clips.md) §2.7), and a first reading of it — three runs over eight words, read
by eye — is [`clip-selection-rounds.md`](../../research/clip-selection-rounds.md). That was enough to find one
real failure, fix it, and discover that the first fix was aimed at the wrong thing; it is **not**
this experiment, which nobody has run. Its starting point is the prompt as round 4 left it.

Two knobs it has already surfaced, both to be varied deliberately rather than inherited:
`selfContainedOnly`, which ships off; and the model's own preference for cleanly captioned, more
scripted channels, which showed up in every run independent of any prompt wording.

### The question

Given one lexeme's senses and a bounded set of caption segments retrieved for it, **which segment —
if any — is a good example of which sense?**

This is the one place in the clip pipeline where a frontier model earns its cost. The corpus finds
occurrences with traditional IR because it has millions of segments and cannot afford a model call
per candidate. Acervo spends exactly one call per word, at the very top of the funnel, on the
judgement a feature cannot make: is this messy fragment really an instance of *this* meaning, and is
it worth a learner's attention?

### What "good" means, and why that is the hard part

There is no ground truth to appeal to, so the rubric has to be written down before anything is
measured. A first attempt, to be revised once real output has been read:

| | A clip is good when | It is not good when |
|---|---|---|
| **Sense** | it is unmistakably *this* sense, not a neighbouring one | it fits the headword but not the sense, or the sense is unrecoverable from the fragment |
| **Completeness** | the sentence stands on its own | it starts or ends mid-clause, or its subject is two turns back |
| **Naturalness** | a speaker said it the way speakers say it | it is a definition, a title read aloud, a list, or a lesson explaining the word |
| **Usefulness** | a learner would be glad it is there | it is technically correct and adds nothing over the generated example above it |
| **Cleanliness** | it needs no apology | proper nouns dominate, the register is wrong for the word, the caption is garbled |

**Refusing is a success, not a miss.** The corpus is small and will stay small for a long time. The
prompt's failure mode to hunt is not "found nothing" — it is "found something mediocre and presented
it as evidence". Precision over recall, deliberately and by a wide margin.

### The cheapest useful method first

The direct loop, run by hand:

1. Take 25–40 saved lexemes with real senses, weighted toward the polysemous ones — those are where
   sense confusion shows up at all, and a monosemous word tells you almost nothing.
2. Run the search and the selection call, keeping **every** intermediate artifact: the query sent,
   the full candidate set with ranks and scores, the raw model output, the parsed selections, the
   validation outcome, and which candidates were dropped.
3. Read the output against the rubric. Label each selection `good` / `borderline` / `bad`, and each
   *refusal* `right` / `missed` by reading the candidates it declined.
4. Change one thing in the prompt. Re-run the same set. Compare.

Keep the artifacts on disk under a run directory, the way the image runs already do, so a later run
can be compared against an earlier one rather than remembered.

The two numbers that matter, with their denominators stated: **of the clips selected, how many are
good** (precision — the one to optimise) and **of the words where a good candidate existed, how
often was it found** (recall — the one to watch for collapse). A third worth tracking because it is
free: how often the model returned an id it was not offered.

An LLM judge calibrated against these labels is worth building **only if** the hand loop becomes the
bottleneck. It probably will not at this scale, and the labels collected here are what would
calibrate one anyway. Do not start there.

### What to vary

In roughly this order, one at a time:

- **Candidate count.** 10 / 20 / 40. Too few and the good clip is never offered; too many and the
  prompt drowns and precision falls. This is the cheapest knob and it may matter more than any
  wording.
- **What a candidate carries.** Sentence alone, versus sentence plus channel, speech style, regional
  variety, caption kind (authored or automatic), and the boundary reason the segment closed on. The
  corpus retains all of it precisely because it should be able to inform a judgement — but each
  field is prompt weight, so each has to earn its place.
- **What a sense carries.** Definition alone, versus definition plus glosses, versus plus the
  existing examples. **Suspect the glosses.** The image brief writer was burned by exactly this: an
  English gloss is a rough handle chosen for closeness, and its metaphors are not the word's — it
  drew *ground* for *estar fundado*. The definition in the language being learned is likely the
  authority here too, and that is a hypothesis to test rather than assume.
- **How refusal is framed.** Whether the prompt says "select the best" or "select only if a learner
  would be glad it is there, and otherwise select nothing". Expect this to be the largest single
  effect on precision.
- **Whether the model explains itself.** A one-line reason per selection costs tokens and may
  improve the judgement; it certainly makes the labelling pass faster. Decide on evidence, and note
  that a reason that is never stored is still worth having during tuning.

### Constraints the prompt may not break

These are not tuning parameters. They come from [`spoken-clips.md`](../../features/spoken-clips.md) §2 and hold
whatever the measurements say:

- The selected text is the corpus's sentence **verbatim**. No trimming, joining or rewriting.
- At most one clip per sense, and none is a valid answer for every sense.
- Only ids from the request's candidate set. Anything else is dropped and counted.
- One call per lexeme, covering all of its senses at once — the batching is what lets the model tell
  two senses of one word apart, which is the whole reason for per-sense clips.

### What to write down

A write-up in `experiments/clip-selection/README.md`, in the shape the other repository's `AGENTS.md` asks for and for the same
reason: the evidence has to be auditable rather than asserted. The hypothesis and its success
criterion; the exact model, prompt version and candidate configuration for every run; the language
and the word set with its selection method; per-example diagnostics kept, not just averages; the
rubric as actually applied, with successful, borderline and failed examples quoted; and the run
directory the numbers came from.

Record a negative result the same way. "Adding speech style changed nothing" is worth a line, and
saves the next session from trying it.

### When to stop

When precision on the labelled set is high enough that reading a random article does not make you
wince, and refusals look right when you check the candidates they declined. That is a judgement call
and it is the correct kind of judgement call — the feature exists so that articles are better to
read, and the person reading them is the measure.

Anything beyond that belongs to the retrieval repository: better candidates make this prompt's job
easier, and that is where the ranking work lives.

## Part 2 · Curating the clips a word already has

**Status:** planned, unstarted. `docs/features/spoken-clips.md` shipped the pipeline: a word is
searched once, a model picks at most one passage per sense, and the only control afterwards is a
remove button. That is the right first shape — most words get nothing, and most of what they get is
fine. What follows is the two things reading the first real output made obvious.

`docs/features/spoken-clips.md` shipped the pipeline: a word is searched once, a model picks at most one
passage per sense, and the only control afterwards is a remove button. That is the right first shape
— most words get nothing, and most of what they get is fine. This plan is the two things reading the
first real output made obvious.

### 1 · The selection prompt should be the owner's

`selfContainedOnly` was the first setting that is really a matter of **taste** rather than of
correctness. It exists because two learners disagree about the same passage: one wants speech tidy
enough to follow cold, the other wants it exactly as messy as a real room, because walking in on a
conversation already under way is the thing being practised.

A growing list of booleans is the wrong shape for that. "Advanced and authentic" versus "clear and
simple" is one question, and every future answer to it would be another checkbox that interacts with
the others in ways nobody can predict from the labels.

**Partly answered since.** Settings ▸ Rules appends the owner's standing rules, in their own words,
to the clip selector's prompt as to every prompt that writes something the owner reads — so "clear
and simple" or "as messy as a real room" can already be said once and apply to every search. Try
that first. A full override is worth building only if a rule cannot express what the owner wants,
or the rules start fighting the shipped wording.

> **If rules are not enough: an owner-scoped selection prompt, with the shipped one as its starting
> text.**

What that has to settle:

- **The shipped prompt stays the default and stays tracked.** A custom one is an override, not a
  replacement for the file; an owner who has never opened the screen gets the repository's wording,
  and "reset to the default" is always available.
- **The contract is not negotiable.** Whatever the wording, the reply is still `{senses: [{senseId,
  segmentId, translation, matchedTranslationForm}]}`, ids still come from the offered set, and the
  passage is still quoted verbatim (`docs/features/spoken-clips.md` §2.6). So the shape block and the id rule
  are appended by the server rather than typed by the owner — the same split `acervo_image_brief`
  already has between what the writer decides and what the frame enforces.
- **A custom prompt is not replicated.** It is owner-scoped server state like `clip_settings` and
  `model_selection`, for the same reason: the searching happens on the server.
- `selfContainedOnly` then becomes a section of the default text rather than a column, and
  `services/prompts.py`'s markers are how it survives the move.

Do not build this before there is a second taste knob asking for it, and rules have been tried.
One is a setting; three are a prompt.

### 2 · A dialog for the clips a word already has

Today a clip can be removed and nothing else. The picture pipeline learned the same lesson and has
`ImageDialog.tsx`: read what produced this, change it, ask again, or rule the sense out. Clips want
the same surface — *this one is wrong, show me the others you were offered*.

Shaped on that dialog, it would offer:

- the passage, its channel and its caption kind, as the article shows them;
- **the other candidates from the same search**, so replacing one costs no model call at all;
- search again, which does;
- remove, which it already has.

**What has to land first, and it is not optional.** Removal is currently an ordinary tombstone, and
a clip example's id is derived from `(senseId, clipRef)`. A re-search that chose the same segment
would write at the tombstone's id and bring the clip back — and nothing would fail. That is exactly
the failure `imagePrompt.suppressed` exists to prevent, and the same answer applies: **a suppression
field has to exist before anything re-searches.** `docs/features/spoken-clips.md` §2.4a says so in as
many words; this is the feature that makes it due.

Showing the other candidates also implies keeping them, which the pipeline currently does not: the
search result is used and dropped. Either the dialog re-searches to populate itself — cheap, since a
corpus search costs no model call — or the run keeps its candidate set somewhere. Re-searching is
almost certainly right: it is one HTTP call to a service on the same network, and storing a
candidate set means storing text the owner never chose.

### 3 · Not here

**Passage boundaries.** Half of what looks like a bad clip is a good passage cut badly, and the fix
is upstream: `spoken-usage-retrieval`'s own experiment on where a shown passage should start and end.
Nothing in this plan should compensate for that by trimming text — `spoken-clips.md` §2.6 is what
stops the corpus's own measurements from being invalidated, and it holds however tempting the
trimming looks.

**Tuning the default prompt.** Part 1, with `docs/research/clip-selection-rounds.md` as its
starting point.
