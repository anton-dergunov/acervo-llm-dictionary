# Learner context · does "about you" stay in the background?

**Question.** A vocabulary now carries three facts about its learner — a CEFR level, a variety
(Argentina's Spanish) and a paragraph in their own words ("preparing for a trip to Argentina; I work in
software") — and the writers are told all three ([`docs/features/standing-rules.md`](../../docs/features/standing-rules.md),
"The reader"). The owner's requirement: take the paragraph into account *lightly*. Asked for *cactus*, a
writer must not produce examples about cacti in Argentina; asked for a story, it must not turn the hero
into a programmer on holiday. And the variety is a preference, not a filter: Spain's forms stay
visible. Does the section do that on Flash Lite, and does its weighting matter?

**Answer.** Yes, after two rounds of wording. With the shipped section (v3), on words unrelated to the
paragraph, **6% of Spanish examples** touch it against **3% with no section at all** — the same two
sentences about holiday photos and travelling more, which the model writes either way — **no entry has
more than one**, and English is at **0%**. Stories went from **4 of 6** Spanish stories leaking with
the first wording to **1 of 9**, and that one only sets a restaurant in Buenos Aires. Entries for words
that differ by region name Argentina's form (88%) and still say what is said elsewhere (88%, against
69% with no section); no headword was swapped out of its own entry. Every reply parsed and was accepted
by the shipped reader. **Stating the facts flatly is much worse**: the `plain` arm leaked into 5 of 6
Spanish stories and both English ones, and marked six standard Spanish words as regional.

The decision lives in [`docs/features/standing-rules.md`](../../docs/features/standing-rules.md),
"The reader"; this is the evidence.

## Method

- **Model**: gemini-free `gemini-3.5-flash-lite`, the model these prompts are written for, called
  directly (`acervo.models.call.text`), never through a chain.
- **The real request**: an entry is `build_user_message` under `prompts/acervo_compose.md`, read back by
  `draft_from`; a story is `stories.write.build_request` under `prompts/acervo_story_write.md`, laid out
  as `StoryWriter` lays it out (the `## The request` heading after anything appended). The section is
  `acervo.services.reader.reader_section`, the one `with_reader` appends. The owner's standing rules
  are left out, so the arms differ by the section alone.
- **Two learners** ([`words.yaml`](words.yaml)): Spanish, Argentina, B1, the trip-and-software
  paragraph; English, Britain, C1, "meetings with clients and a lot of email; I like football".
- **36 words in three groups**: *unrelated* to the paragraph (cactus, cuchara, oveja, pebble, whisk…),
  *related* (pasaje, aduana, depurar; agenda, equaliser…), and Spanish *variety* words whose form
  differs between Spain and Argentina (autobús, ordenador, coger, zumo, conducir, piscina, vosotros,
  tener). **Six stories** of four words each, four of them from unrelated words.
- **Arms**: `none` — no section; `plain` — the same three facts stated flatly, with no weighting;
  `light` — the shipped section, in three wordings (below). Two repeats of every entry; stories two
  repeats, three for v3.
- **Measured without a judge** ([`score.py`](score.py)): an example or story part *leaks* when a stem
  from the learner's `leak` list (Argentina, Buenos Aires, viaj-, software, código…; meeting, email,
  football…) appears in it or its translation. Blunt, and readable: every hit was read for this write-up,
  and for the shipped wording so was every sentence it did not flag (below). Reading everything beats
  calibrating a judge model on a sample — the lesson of `compose-lesson-line/` is that a judge must be
  checked against a reader before it is believed anyway. [`review.py`](review.py) serves a blind
  sample for the owner's own labels and reports Cohen's κ between them and the keywords.

## Three wordings

Each run's exact section is in its `manifest.json`.

| | v1 | v2 | v3 (shipped) |
|---|---|---|---|
| Note | "background … not a subject to write about … at most one example in an entry or one detail in a story" | "background … **not material**: do not give it to a character, a setting or an example; no character shares their job, plans or interests; nothing is set where they are going; only where the word belongs to it, one example at most" | as v2 |
| Variety | prefer its forms, do not hide the others, mark regional only when it is | + "a word that is the same everywhere needs no word about Argentina" | + "**the variety decides the words, not the setting**" |

v1 read "one detail in a story" as leave to make the hero a developer debugging code in a café in
Palermo; v2's "not material" fixed the job and the trip but kept a Buenos Aires office; v3's sentence
about the setting removed that too.

## Numbers

Runs [`first`](runs/first/report.md) (`none`, `plain`, `light` v1), [`second`](runs/second/report.md)
(`light` v2) and [`third`](runs/third/report.md) (`light` v3). Shares with counts.

| Measure | none | plain | light v1 | light v2 | **light v3** |
|---|---|---|---|---|---|
| Unrelated Spanish examples about the note | 3% (1/34) | 5% (2/38) | 11% (4/35) | 3% (1/34) | **6% (2/36)** |
| Unrelated Spanish entries with more than one | 0/24 | 0/24 | 0/24 | 0/23 | **0/24** |
| Unrelated Spanish notes that mention it | 0/24 | 8/24 | 4/24 | 2/23 | **3/24** |
| Unrelated English examples / notes | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | **0 / 0** |
| Unrelated Spanish stories that leak | 0/6 | 5/6 | 4/6 | 2/6 | **1/9** |
| … their parts | 0/24 | 10/24 | 8/24 | 3/24 | **1/36** |
| Unrelated English stories that leak | 0/2 | 2/2 | 0/2 | 1/2 | **1/3** ✱ |
| Related Spanish entries that use it | 5/12 | 7/12 | 4/12 | 5/12 | **6/12** |
| Related English entries that use it | 6/8 | 7/8 | 6/8 | 6/8 | **8/8** |
| Variety words: names Argentina's form | 13/16 | 14/16 | 14/16 | 13/15 | **14/16** |
| Variety words: says what is said elsewhere | 11/16 | 14/16 | 14/16 | 13/15 | **14/16** |
| Variety words: headword swapped out of its examples | 0/25 | 1/24 | 0/23 | 0/24 | **0/28** |
| Standard Spanish word marked regional (`dialect`) | 0/36 | 6/36 | 0/36 | 0/35 | **1/36** |
| English word marked regional | 0/20 | 2/20 | 1/20 | 3/20 | **2/20** ✱✱ |
| Words per Spanish example | 8.7 | 9.5 | 8.9 | 9.0 | **9.0** |
| Replies accepted by the shipped reader | 72/72 | 72/72 | 72/72 | 70/70 | **72/72** |

✱ A keyword false positive: "a match*ing* grey pebble". The en stories otherwise never mention meetings,
email or football. In v2 the one hit was a baker's "business".
✱✱ Mostly `en-GB` on *equaliser*, which is the British spelling and so correctly regional.

**The three notes v3 still counts** are not the paragraph at all but the variety, used well: *pintar*
in Argentina for "to feel like" (*no me pinta ir*), twice, and *cuchara* for a mason's trowel. The two
examples are a holiday photo saved to the cloud (*nube*) and "I regret not travelling more"
(*arrepentirse*) — the first of which the `none` arm wrote too.

## What was not measured

- **Voseo in examples.** An entry's examples are rarely addressed to "you": two or three per arm, too
  few to report a share. The variety's effect on grammar shows instead in the notes ("says what is
  said elsewhere", 69% → 88%).
- **The level.** Example length barely moves (8.7 → 9.0 words); whether B1 examples are *easier* is a
  judgement the review page asks for, not a count.
- **The owner's own labels.** The keyword measure was checked both ways by reading, not by a judge
  model: every sentence it *flagged* (precision — the false positives are named above), and every
  sentence of v3 on unrelated words it did *not* flag (recall — 66 examples and 12 stories). That
  second read found **no missed leak**: no software, trip, meetings, email or football. What the
  keywords do not see is the variety at work — *departamento*, *palier*, *mozo*, *mate y galletitas*
  in the stories — which is wanted; and *pintar*'s "the project isn't looking good", which is the
  word's own idiomatic sense. Both reads were made by Claude in the session that ran the experiment,
  so they are a model's labels, not the owner's. To add the owner's (the sample is drawn on first
  start and kept):

      .venv/bin/python experiments/learner-context/review.py serve runs/review \
          --from runs/first:none --from runs/third:light --host "$(tailscale ip -4)" --port 8766
      .venv/bin/python experiments/learner-context/review.py score runs/review

## Running it

    set -a; . ./.env; set +a
    .venv/bin/python experiments/learner-context/run.py --dry-run            # the matrix and the sections
    .venv/bin/python experiments/learner-context/run.py --repeats 2           # every arm, about 32 minutes
    .venv/bin/python experiments/learner-context/run.py --run <id> --arm light --kind story --repeats 3
    .venv/bin/python experiments/learner-context/score.py runs/<id>

A run's replies are one file, `runs/<id>/replies.jsonl`, a JSON object per line, appended as each
lands. A run resumes where it stopped (`--run <id>`): a cell already in that file is never asked
again, and a retryable failure is not written, so a second pass fills it. `light` is always the section the code
ships *now*: a run made after the wording changes measures the new wording, which is why each wording
has its own run.
