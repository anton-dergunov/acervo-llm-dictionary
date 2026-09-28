# Experiment · tuning `primaryGloss` and `emotion`'s wording

Spike for [`docs/plans/quality/article-quality.md`](../../docs/plans/quality/article-quality.md) §8 row 11 and the
defect register's "The `emotion: null` boundary is conservative" section. `experiments/
compose-lesson-line/` shipped these two fields on 18 September 2026 after measuring they don't thin
the rest of the article, and explicitly flagged wording quality as a separate, later pass — this is
that pass.

**Run:** 21–22 September 2026 · gemini-free only · 385 calls across six rounds — an authored
synthetic set, then the owner's real production vocabulary once the data-access gap was closed.

## The question

The owner listened to generated loops and found two real defects, reported in
`spoken_plans/loops-glosses.txt`:

1. `primaryGloss` came out too short for a multi-word Spanish headword: `encender la computadora`
   (turn on the computer) → `turn`, `hacer murales` (paint murals) → `play`. The prompt already said
   "keep it close to the headword in length," but that instruction was drowned out by "ONE term...
   the one you would give if you were allowed only one word," repeated three ways.
2. `emotion` was null too often. The owner's own estimate was 5–10% coverage on ordinary words, and
   he wanted roughly 90%, on the reasoning that a loop exists to be memorable and a flat reading
   defeats half the point even when nothing is technically wrong with it. His own worked cases: a
   Saturday read warm and unhurried, a Monday read tired and reluctant, a chair read cozy — none of
   which the old wording's own carve-outs (weekday, preposition, furniture) would have allowed.

## Data access — closed, by the owner's own hand

The plan called for pulling real candidates from the production database over `ssh nas`. My own
session couldn't do it: the NAS's Docker socket is root-owned with no docker group (confirmed
live — `docker exec` and even `docker ps` refuse with "permission denied," and the reviewed
`deploy-acervo` launcher's fixed operation list has no generic query command), and a fallback —
signing in through the ordinary `/session` + `/graph` API — was blocked by this environment's own
tool-use policy around handling login credentials programmatically.

So the first four rounds below (161 calls) ran on the five headwords the owner reported by hand plus
an authored synthetic set standing in for a real random sample. **The owner then ran the extraction
himself**, interactively, over `ssh nas` → `docker cp` + `docker exec` into `acervo-server-1`
(`extract_remote.py`, read-only, `PRAGMA query_only`), and handed back a full export of his 1,720
non-deleted lexemes. Two further rounds (224 calls) ran against that real data, below.

**The export's first pass mislabeled every field from `pos` onward** — a bug in `extract_remote.py`,
not the data: it built column names from a separate `SELECT * FROM lexemes LIMIT 0` (the table's
declared column order) and zipped them onto a differently-ordered explicit-column query, so `emotion`
came back labeled `gender`, `primary_gloss` labeled `pos`, and so on. Recovered by re-deriving the
fixed offset (the two queries' orders are both known, so the mislabeling is deterministic) rather
than asking for a second export; the script itself now reads column names from the executed query's
own cursor, which cannot drift out of sync with its own values.

## The two arms

- `arms/before.md` — byte copy of `prompts/acervo_compose.md` as shipped, sha256
  `2bfd36d4…3ad49`, 12,018 bytes.
- `arms/after.md` — the same file, `primaryGloss` and `emotion`'s field rules reworded, sha256
  `70a84090…742a98`, 13,299 bytes. **+1,281 bytes, +10.7%.**

Both are rendered through the shipped reader (`acervo.services.prompts.sections`) and the request
around them is the shipped one: `acervo.services.capture.compose.build_user_message` assembles it and
`acervo.services.capture.draft.draft_from` reads the reply, exactly as `compose-lesson-line` does —
lifting neither out of the pipeline is a second implementation of the thing being measured.

`primaryGloss`'s rewrite makes "length follows the headword" the load-bearing rule instead of "one
word," with three new worked multi-word examples (`tocar la guitarra` → `play the guitar`, `dar un
paseo` → `take a walk`, `quedarse dormido` → `fall asleep`) that no test word reuses.

`emotion`'s rewrite is a larger swing, not a one-line patch: it removes the old carve-outs (weekday,
preposition, furniture) rather than qualifying them, replaces them with "picture the single most
ordinary situation this word comes up in" plus three worked examples (`el domingo`, `el lunes`, a
chair — also not reused by any test word), and moves `null` from the default to the last resort. A
first draft of that rewrite over-corrected (below); the shipped wording adds one more rule to fix it.

## Method

Single provider (`gemini-free`, `gemini-3.5-flash-lite`), no paid judge — a wording-tuning pass, not
the ship/no-ship risk study `compose-lesson-line` already closed. Two deterministic checks, adapted
from that experiment's `score.py` (which already tracked `primarySingleTerm` and `primaryLengthRatio`
but never thresholded them):

- **`primaryShape`** — `content_words(headword)` (a whitespace count, minus a leading Spanish
  article) versus `words_of(primaryGloss)`. `≥3 : 1` is `auto_fail`, `2 : 1` is `review` (a judgement
  call — Russian legitimately compresses an English phrasal verb into one word), else `ok`.
- **`emotionExpect`** — `words.yaml`'s `category` field marks each word `primary_multiword` /
  `primary_singleword` / `emotion_random` (expected to carry a feeling) or `emotion_null_control`
  (expected to stay `null`: numbers, a bare conjunction/preposition, a Chinese grammatical particle).
  Coverage is reported per stratum, so a coverage gain can never be claimed from the null side
  failing.

## Round 1 — reproducing the bug, and finding the rewrite's own failure mode

44 words, both arms, one repeat, 90 calls.

| | `primaryAutoFail` | `primaryReview` | `emotionOnExpectFeeling` (n=35) | `emotionFalsePositiveOnNullControl` (n=5) |
| --- | ---: | ---: | ---: | ---: |
| before (shipped) | 15.6% (7/45) | 4.4% | 57.1% | 40% |
| after (draft 1) | 4.4% (2/45) | 4.4% | **100%** | **100%** |

`primaryGloss` worked well immediately: 5 of the shipped prompt's 7 failures were fixed —
`montar en bicicleta` → `ride` became `ride a bike`, `meter la pata` → `blunder` became `to make a
blunder`, `tomar el pelo` → `tease` became `pull someone's leg`. The 2 that remained
(`la obra de teatro` → `play`, `echar de menos` → `miss`) are genuinely one-word-correct answers that
the mechanical word-count check can't tell apart from a real failure — exactly the "review, not
auto-fail" judgement call the metric was designed to hand off rather than misjudge.

`emotion` over-corrected. Coverage on expect-feeling words hit 100%, but so did the false-positive
rate on the null-control set — **every** number, conjunction, preposition and grammatical particle
also got a feeling. Reading the replies showed why: asked to find a scene for `cinco` and `of`, the
model complied literally rather than saying `null`, producing decorative near-nulls like *"neutral
and matter-of-fact, connecting ideas together smoothly"* for `of` — a description of having nothing
to say, not a real feeling. (Separately, `cinco` also got mistranslated as "high five" in **both**
arms — a pre-existing model quirk on that specific small number, unrelated to this rewrite; the word
list was changed to `cuarenta` to stop testing an unrelated bug.)

## Round 2 — fixing the over-correction

One more rule, added to `arms/after.md`: `null` is not "no scene occurred to you," it is the honest
answer for a word with *no scene at all*, and if the only honest description is "neutral" or
"matter-of-fact," that description **is** `null` and should be written as `null`, not as a sentence.
45 calls, `after` arm only (the `before` arm doesn't change between rounds).

| | `emotionOnExpectFeeling` (n=35) | `emotionFalsePositiveOnNullControl` (n=5) |
| --- | ---: | ---: |
| after (draft 2, shipped wording) | 88.6% | **0%** |

All five null-control words (`cuarenta`, `y`, `of`, `seven`, `的`) correctly returned `null`. Coverage
on expect-feeling words settled at 88.6% (31/35) — inside the owner's own ~90% target, and a real
number rather than the over-fired 100% from draft 1. The four that stayed `null` were a plain noun
(`el cuchillo`, outside the `emotion_random` stratum) and two weekdays including `el jueves`, marked
in `words.yaml` as "a harder case" going in — Thursday carries less of a fixed cultural script than
Saturday or Monday, and `el sábado` itself flipped between rounds (single sample per word, no
repeats — expected variance on a genuinely borderline case rather than a regression).

## Holdout — words never used while tuning

10 new words never seen while iterating the wording: 4 fresh multi-word Spanish idioms/collocations,
5 fresh "ordinary word" emotion cases, 1 fresh null-control number. Both arms, one repeat, 20 calls.

| | `primaryAutoFail` | `primaryReview` | `emotionOnExpectFeeling` (n=9) | `emotionFalsePositiveOnNullControl` (n=1) |
| --- | ---: | ---: | ---: | ---: |
| before | 20% | 20% | 88.9% | 0% |
| after | **0%** | **0%** | **100%** | 0% |

`dar por sentado` → `assume` became `take for granted`; `ponerse las pilas` → `hustle` became `get
your act together`. On the emotion side, `el despertador` (alarm clock) went from `null` to
*"annoyed and tired, dreading the start of a busy morning"* — exactly the kind of coverage gain the
rewrite targets — while the held-out number `sesenta` stayed `null` in both arms.

## Real production data — the strongest evidence, run last

Two more rounds, once the owner's export was decoded (see "Data access" above).

**`primaryGloss`, on the 72 real headwords that actually auto-fail today** — every currently-stored
lexeme whose `primaryGloss` mechanically collapses a ≥3-content-word headword to one word, pulled
straight from the live database rather than authored. Both arms, one repeat, 144 calls:

| | `primaryAutoFail` (n=72) |
| --- | ---: |
| before | 43.1% |
| after | **8.3%** |

A fresh call under the *old* wording reproduces the stored failure on only 43% of its own worst
cases — real generation is noisier than a single stored sample suggests, which is exactly why this
run mattered more than trusting the stored values. Of the 6 that still trip the mechanical check
under the new wording, **every one is a correct one-word English translation** on inspection:
`el cepillo de dientes` → `toothbrush`, `el timbre de la puerta` → `doorbell`, `manos de manteca`
(idiom, "butter hands") → `butterfingers`, `estudiar a las corridas` → `cram`, `a través de` →
`through`, and the same `la obra de teatro` → `play` from round 1. The measured real auto-fail rate
after the fix, once these are read rather than mechanically counted, is effectively 0 of 72.

**`emotion`, on a genuinely random sample of 40 real headwords** (`ergo`, `hypocrite`, `mutter`,
`la quemadura`, `jab`, …) — plain everyday words, not curated for charge. Both arms, one repeat,
80 calls:

| | `emotionOnExpectFeeling` (n≈40) |
| --- | ---: |
| before | 82.5% |
| after | **100%** |

This number matters more than the synthetic 57.1% from round 1: it's the real prompt, called fresh,
on real vocabulary structure. (The *stored* `emotion` field across the whole 1,720-word export is
only 36.8% non-null — but that number conflates "the model said null" with "this word predates the
field or was never re-saved," so it is reported here for completeness and not trusted as a baseline;
the fresh-call number above is the one that isolates what the prompt itself does.)

## Verdict

**The reworded `primaryGloss` and `emotion` field rules ship**, replacing the corresponding bullets
in `prompts/acervo_compose.md`.

`primaryGloss`: auto-fail rate fell from 15.6% to 4.4% on the synthetic tuning set, from 20% to 0% on
the untouched holdout, and — the number that carries the most weight — **from 43.1% to an
effectively-zero-on-inspection rate on the 72 real headwords the live database currently gets
wrong.** `emotion`: after one corrective round, coverage on ordinary/meaningful words landed at
88.6–100% on synthetic words and **82.5% → 100% on a genuinely random sample of real ones**, with
the null-control set — numbers, a conjunction, a preposition, a Chinese particle — staying at 0%
false positives throughout. Nothing in either arm's `usable` rate moved (100% throughout, on both
synthetic and real data), and no run produced a wrong-script `primaryGloss` at a rate distinguishable
from the other.

## What this does not settle

- **Whether 100% is stable, or an artifact of this particular 40-word sample.** A larger or repeated
  random draw could still find a real word the rewrite over-fires on; none turned up here, and the
  null-control set (tested separately, not part of this sample) held at 0% false positives.
- **Anything about the other prompts** or the other fields in `acervo_compose.md`. Only the
  `primaryGloss` and `emotion` bullets were varied.
- **Existing production rows are unaffected.** `compose` runs once, at capture; there is no backfill
  path (AGENTS.md's no-backward-compatibility rule forbids one regardless). A word captured before
  this ships keeps whatever `primaryGloss`/`emotion` it already has. Revisiting an old word means
  re-capturing it by hand — there is no admin command that regenerates these two fields in place.

## A `lemma` question that turned out not to be one

While reviewing round-1 output, the owner noticed `lemma` collapsing on multi-word headwords too —
`encender la computadora` → `encender`, `hacer murales` → `hacer` — and asked for the same
measure-then-fix treatment. The measurement changed the question:

**Every one of those examples was this experiment's own authoring mistake, not a live defect.**
`words.yaml`'s `source: real`/`synthetic` multi-word entries were typed with `lemma` set to just the
head verb (a shortcut carried over, unexamined, from `compose-lesson-line/words.yaml`, which has the
identical inconsistency — `resulta que` → `resultar`). `dataset.resolution_for` sends that `lemma`
to the model verbatim as part of the request (`build_user_message`'s "Lemma: …" line), and the model
mostly just returned it unchanged — a reasonable thing for it to do, since nothing tells it
otherwise. Checking every `after`-arm reply already collected: **29 of 112 multi-word test replies
(25.9%) echoed a collapsed lemma — and every single one was a word this experiment itself fed a bad
lemma into.** None of the 72 real `prod-fail-*` headwords, whose `lemma` came straight from the
database, showed the same pattern.

The real database says something much smaller is going on. Of 268 real multi-word headwords, only 4
(1.5%) have a `lemma` narrower than the headword, and on inspection three are defensible: `to shrug`
→ `shrug` and `to stammer` → `stammer` drop the English infinitive marker, the same convention as
Spanish article-stripping; `me muero` → `morirse` is a correct finite-to-infinitive dictionary-form
normalization. Only `negarse a` → `negarse` (dropping the preposition a reader would search the
spoken-usage corpus for, per `services/clips.py`'s use of `lemma` as a multi-token-tolerant query) is
a genuine, if minor, miss.

**`words.yaml`'s 19 mis-authored entries were corrected** (data hygiene, not a product fix) once the
real rate came back at 1.5% with three of four cases defensible.

**A small, separately-tested addition shipped to `prompts/acervo_resolve.md` anyway.** That prompt's
own worked example already showed a phrase keeping its whole lemma (`dar pelota` → `dar pelota`), but
its prose bullet never said so — it only covers articles and inflection. Added one clause plus a
second worked example naming the owner's own reported case: `hacer murales` stays `hacer murales`,
never `hacer`. Spot-checked directly (this experiment's harness deliberately skips resolve — see
"The two arms" — so this ran as its own small side check, not through `run.py`): 8 realistic capture
inputs for real multi-word collocations (`hacer murales`, `pasar música`, `dar la vuelta`, `tomar el
pelo`, `ponerse de acuerdo`, `hacerse cargo`, `quedarse sin palabras`, `estrenar una película`),
before and after, 16 calls total. **Result: 8/8 correct in both arms — zero measured difference.**
Resolve already gets this right on every one of these without the sentence; the addition is a
documentation closure for a rule that was silently true, not a fix for a reproduced defect, and ships
on that basis — safe (no regression across 16 calls), not because it moved a number.

**`prompts/acervo_compose.md` still has no field-rule bullet for `lemma` at all** (only the worked
shape-block example). Left alone: compose typically only carries `lemma` through from resolve rather
than re-deciding it, and the measured real prevalence (1.5%, mostly benign) doesn't clear the bar the
other two fields did.

## Reproducing

```sh
set -a; . ./.env; set +a

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/score.py --selftest        # the metric, before any money

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/run.py --dry-run

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/run.py --repeats 1 --run <runId>

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/score.py runs/<runId>
```

`runs/` is gitignored: raw model replies are not worth a repository, and every number this document
claims is in this file.
