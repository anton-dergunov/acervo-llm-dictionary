# Experiment · does adding two fields to the compose prompt thin the article?

Spike for [`docs/features/loops.md`](../../docs/features/loops.md) §2.8. The
plan keeps the decision; this document holds the question, the method and every number.

**Run:** 18 September 2026 · 20 words · four languages · three (provider, model) pairs · three
repeats · two arms.

## The question

A loop needs one term to speak and one direction for how the word sounds, so
`docs/features/loops.md` puts `primaryGloss` and `emotion` on the lexeme and has the
**existing** compose prompt write them, rather than adding a second model call.

The risk is not that the two fields come out wrong. It is that a longer prompt **thins everything
else** — fewer senses, shorter notes, a `primaryGloss` that is only `shortGloss` again — and that
this would be invisible until a thousand articles had been written that way.

So: measure the rest of the article, paired, on the same words, through both prompts.

If it degrades, the answer is **not** to carve two fields into their own call — that is too small a
piece to justify a second prompt. It is to split `acervo_compose.md` into comparable parts,
considered whole, as its own task.

## The two arms

- `arms/before.md` — a byte copy of `prompts/acervo_compose.md` as it stood, sha256
  `7ca2c954…0151`, 10,603 bytes. Frozen before anything was edited.
- `arms/after.md` — the same file plus two keys in the shape block and two bullets in `Field rules:`,
  sha256 `2bfd36d4…ad49`, 12,018 bytes. **+1,415 bytes, +13.3%.** Prompt growth is reported, not
  bounded.

Both are rendered through the shipped reader, `acervo.services.prompts.sections`, and the request
around them is the shipped one: `acervo.services.capture.compose.build_user_message` assembles it and
`draft_from` reads the reply, so an arm is measured against the pipeline rather than against a copy
of it. Lifting `build_user_message` out of `compose()` is the only change this experiment made to
shipped code.

The resolve call is deliberately not made. `words.yaml` states the resolution, because resolve is a
separate prompt this experiment does not vary, and calling it would double the spend and add a second
source of variance to a paired comparison.

## Method

Three layers, and only one of them costs human attention.

| Layer | Covers | Answers |
| --- | --- | --- |
| 1 · deterministic metrics | all 360 calls | did the article get **thinner** |
| 2 · an LLM judge, blind and position-swapped | all pairs, ×2 orderings | did it get **duller** |
| 3 · 25 stratified human screens | a calibration set | **is layer 2 worth anything** |

Layer 3 does not produce the verdict. It produces a κ that says how far layer 2's verdict can be
trusted — and that number is reusable by every later prompt experiment, which is why the attention is
spent there rather than on reading 180 pairs.

### Layer 1

Everything about the article is read from the draft `draft_from` builds, so the numbers describe what
Acervo would actually have stored. The two new fields are read from the **raw reply**, because the
shipped parser silently ignores keys it does not know — which is exactly what lets the enlarged
prompt be measured before any schema exists for it. `draft_from` is a measurement here, never allowed
to abort a row: what the shipped path would refuse is one of the things being compared.

**The yardstick is the baseline's own variance.** Three repeats make it measurable: for each metric,
the mean absolute difference between two repeats of the *same* arm is compared with the mean
difference *between* arms. A between-arm gap no larger than the within-arm noise is not an effect.

### Layer 2

One call per pair per ordering, both articles as YAML with **the new fields stripped from the after
side** so the arm cannot be identified. Where the two orderings disagree the pair counts as *no
difference*, and the flip rate is reported: it is the instrument's own noise.

The judge is `vertex_ai/gemini-3.1-pro-preview` — a Pro model, and deliberately **not one of the
arms**, because grading a model's own output is the strong documented self-preference case and
`vertex_ai/gemini-3.8-flash` is an arm. Family preference may remain; every comparison is within one
arm-model, both sides from the same one, so it largely cancels.

### Layer 3

| n | stratum | what it buys |
| ---: | --- | --- |
| 8 | judge confident, both orderings agree | whether its confidence means anything |
| 5 | judge flipped between orderings | its weakest calls, checked |
| 5 | judge and the counts disagree | the "complete but duller" case, directly |
| 3 | uniform random | an unbiased anchor against the stratification |
| 4 | **control: two repeats of the same arm** | the reader's own false-positive rate |

Nothing on screen says which four are controls.

## Pre-registered thresholds

Written down before the measured run, and scored against afterwards.

| metric | bar |
| --- | --- |
| usable-answer rate | after ≥ before − 2 points |
| senses per word | paired median delta = 0, mean ≥ before − 0.15 |
| examples per sense | mean ≥ before − 0.15 |
| note characters | ≥ 90% of before |
| gloss completeness | 100% in both arms |
| `primaryGloss` present / a single term | ≥ 95% / ≥ 90% |
| `primaryGloss` copied a multi-meaning `shortGloss` | ≤ 10% |
| `primaryGloss` in the wrong script for the first gloss language | ≤ 5% |
| `emotion` identical to one of the article's example emotions | ≤ 10% |
| judge win rate for *before* | ≤ 55% |
| judge flip rate between orderings | ≤ 25%, else layer 2 is discarded |
| control false-positive rate | reported, not bounded — it calibrates everything else |
| median latency | ≤ before + 1.0 s |

## What the pilot changed, before the measured run

A 16-call pilot on the free tier found three things, and all three were fixed before spending the
night. Recording them because two were faults in the instrument rather than in the candidate:

1. **The candidate prompt was contaminated.** Its illustration of `emotion` used `asco`, which is in
   `words.yaml`, and the model returned the prompt's own phrase verbatim. An example drawn from the
   test set is an advantage only one arm has. The illustration now uses the entry already in the
   shape block.
2. **A metric was wrong.** `primaryGloss` equal to `shortGloss` was counted as a conflation failure,
   but for a word with one meaning the two *should* agree — `el miércoles` → `Wednesday` was flagged
   when it was correct. The failure is copying a **multi-meaning** `shortGloss`, and that is what is
   now measured.
3. **A real rule violation.** `麻烦` produced `troublesome`, in English, for a vocabulary that glosses
   into Russian first. The rule was restated in the candidate and a script check added to the scorer;
   the re-run produced `хлопотный` and `давай`.

## Coverage, and one pair that could not finish

`gemini-free` completed all 120 cells. `vertex` refused often enough at 20 calls a minute that the
gate was lowered to 6 mid-run, and a later pass recovered all but three cells.

**Cloudflare stopped at two repeats of three.** It began refusing in 0.1–0.9 seconds — the signature
of a consumed daily allowance rather than a per-minute ceiling — and kept refusing an hour after the
00:00 UTC reset, through six further attempts at 4 calls a minute. So 42 of its 120 cells are empty
and repeat 2 is missing for it.

Two things make that a loss of depth rather than a broken comparison, and both were design choices
rather than luck:

- **The missing cells are 21 `before` and 21 `after`.** Jobs run repeat-major — every arm, pair and
  word once, then again — precisely so that a run which dies part way is still balanced. It died
  part way, and it is still balanced.
- **A refusing pair parks rather than dribbling.** Five consecutive refusals stop that pair for the
  rest of the process, because a biased subsample of one pair's answers is worse than a smaller n
  that says so.

So Cloudflare contributes 39 paired comparisons instead of 60, and every number reported for it
carries that n.

## Results

315 calls, 155 paired comparisons, 310 judgements. **$4.04** all in — $1.33 for the arms, $2.71 for
the judge.

### The headline

| arm | pair | n | usable | senses | ex/sense | note chars | def chars | opt fields |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| after | cloudflare/llama-3.3-70b | 39 | 100% (91%–100%) | 1.05 | 0.95 | 108.1 | 66.4 | 3.10 |
| before | cloudflare/llama-3.3-70b | 39 | 97% (87%–100%) | 1.08 | 0.96 | 87.7 | 64.4 | 3.13 |
| after | gemini-free/3.5-flash-lite | 60 | 100% (94%–100%) | 1.58 | 1.02 | 165.3 | 64.4 | 3.40 |
| before | gemini-free/3.5-flash-lite | 60 | 100% (94%–100%) | 1.48 | 1.11 | 184.9 | 62.6 | 3.37 |
| after | vertex/gemini-3.8-flash | 59 | 100% (94%–100%) | 1.76 | 1.03 | 290.5 | 69.0 | 3.46 |
| before | vertex/gemini-3.8-flash | 58 | 100% (94%–100%) | 1.69 | 1.07 | 324.6 | 72.3 | 3.47 |

Gloss-language completeness is **100% in both arms on every pair**. The single unparseable reply in
the whole run is Cloudflare's, in the **before** arm — the shorter prompt.

### The between-arm difference, against the within-arm noise

The yardstick, and the reason three repeats were chosen over more words.

| metric | after − before (mean) | median | same-arm noise | reads as |
| --- | ---: | ---: | ---: | --- |
| senses | +0.039 | 0 | 0.130 | inside the noise |
| examples | −0.019 | 0 | 0.177 | inside the noise |
| examples per sense | −0.055 | 0.0 | 0.099 | inside the noise |
| note count | +0.071 | 0 | 0.323 | inside the noise |
| note characters | −15.65 | −13 | 58.44 | inside the noise |
| definition characters | +0.21 | 0 | 11.26 | inside the noise |
| terms per gloss | +0.030 | 0.0 | 0.213 | inside the noise |
| optional fields | +0.006 | 0 | 0.026 | inside the noise |
| seconds | +1.54 | +0.14 | 4.97 | inside the noise |
| reply characters | +69.7 | +58 | 176.92 | inside the noise |

**Every metric. No exceptions.** The largest effect anybody would have looked for — notes getting
shorter — moves 15.7 characters against a floor of 58.4, and its median is −13 on notes averaging
87 to 325 characters.

### The two new fields

| pair | n | present | single term | copied a list | wrong script | in 1st sense | emotion present | 3–12 words | = an example |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cloudflare/llama-3.3-70b | 39 | 100% | 100% | 0% | **28%** | 72% | 69% | 89% | 5% |
| gemini-free/3.5-flash-lite | 60 | 100% | 100% | 0% | 2% | 88% | 85% | 100% | 0% |
| vertex/gemini-3.8-flash | 59 | 100% | 100% | 0% | 0% | 97% | 71% | 100% | 0% |

`primaryGloss` was present and a single term in **every one of the 158 usable replies**, and never
once copied a multi-meaning `shortGloss` — the conflation the experiment was built to catch did not
happen at all.

**The wrong-script column is one model, not the prompt.** All eleven failures are Cloudflare's, and
every one is an English term for a word whose vocabulary glosses into Russian first: `hoax` →
*deception*, `магазин`'s entry → *magazine*, `麻烦` → *troublesome*, `加油` → *come on*. Gemini gets it
wrong twice in sixty and Vertex never. llama-3.3-70b does not follow "the FIRST language you are
asked to gloss into" — which is a fact about that model, and one worth knowing independently of this
experiment, since `shortGloss` and a sense `domain` already live by the same rule.

### The judge

| pair | comparisons | before wins | after wins | no difference | flipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| cloudflare/llama-3.3-70b | 38 | 42% (28%–58%) | 34% | 24% | 11% |
| gemini-free/3.5-flash-lite | 60 | 37% (26%–49%) | 32% | 32% | 20% |
| vertex/gemini-3.8-flash | 57 | 37% (26%–50%) | 25% | 39% | 25% |
| **all pairs** | **155** | **38%** (31%–46%) | **30%** | **32%** | **19%** |

What decided a call, when one was made: notes 139 · examples 66 · glosses 41 · senses 39 ·
definitions 25.

**Read this two ways, because the threshold as written was ambiguous.** Over all comparisons, before
wins 38% against a ≤55% bar — a clear pass. Among only the 68% where a winner was named, before
takes **56%** and after 44%, which is a mild lean towards the current prompt. The instrument's own
noise is 19%, so an 8-point gap is not much more than the flip rate; the 25 human screens exist to
say whether it is real.

### Latency and cost

| arm | pair | median s | p90 s | request chars | reply chars | cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| after | cloudflare/llama-3.3-70b | 6.5 | 12.6 | 12,348 | 1,128 | $0.0639 |
| before | cloudflare/llama-3.3-70b | 6.0 | 11.6 | 10,941 | 1,037 | $0.0577 |
| after | gemini-free/3.5-flash-lite | 1.8 | 2.7 | 12,347 | 1,628 | $0.1287 |
| before | gemini-free/3.5-flash-lite | 1.7 | 2.5 | 10,940 | 1,515 | $0.1176 |
| after | vertex/gemini-3.8-flash | 14.2 | 34.1 | 12,347 | 1,939 | $0.5049 |
| before | vertex/gemini-3.8-flash | 13.5 | 23.8 | 10,939 | 1,881 | $0.4599 |

The prompt grew 13.3% and the request 12.9%; the reply grew 6–8% and median latency 0.1 to 0.7 s.

### Against the thresholds set before the run

| metric | bar | measured | missed |
| --- | --- | --- | :---: |
| usable-answer rate | after ≥ before − 2 pts | after 100/100/100 vs before 97/100/100 | |
| senses per word | median delta 0, mean ≥ −0.15 | 0 and +0.039 | |
| examples per sense | mean ≥ −0.15 | −0.055 | |
| note characters | ≥ 90% of before | 123% · **89.4%** · **89.5%** | **✗** |
| gloss completeness | 100% both arms | 100% everywhere | |
| `primaryGloss` present / single term | ≥ 95% / ≥ 90% | 100% / 100% | |
| copied a multi-meaning `shortGloss` | ≤ 10% | 0% | |
| wrong script | ≤ 5% | **28%** · 2% · 0% | **✗** |
| `emotion` = an example's | ≤ 10% | 5% / 0% / 0% | |
| judge win rate for *before* | ≤ 55% | 38% of all, 56% of decided | |
| judge flip rate | ≤ 25% | 19% | |
| median latency | ≤ before + 1.0 s | +0.5 / +0.1 / +0.7 s | |
| control false-positive rate | reported | pending the 25 screens | |

Two bars missed, and neither is what the experiment was looking for. Note characters land at 89.4%
and 89.5% against a 90% bar on two pairs — half a point under, on a metric whose paired difference is
a quarter of its own noise floor, so the bar was simply drawn tighter than the instrument can
resolve. The wrong-script miss is one model ignoring a rule that predates these fields.

### The 25 screens, and what they were worth

Rated 18 September 2026, blind, side randomised per screen.

| | |
| --- | --- |
| control false-positive rate | **2 of 4** — 50% |
| agreement with the judge | 33%, **Cohen's κ = −0.097** |
| calls by strength | slight 15 · clear 3 · large 0 |
| calls by side | left 4 · **right 14** · no difference 7 |
| calls by arm | before 10 · after 6 · same 5 |

**The controls looked like the headline, and the reader's own feedback corrected that.** Shown two
articles produced by the *same* prompt, a winner was named half the time — but the screen offered
only *A better*, *B better* and **no difference**, and on a control the third option is literally
false: two generations of one prompt do differ in wording. The reader reported the same problem on
the real screens — *"in some cases I actually saw the differences but they were made in such a way
that it was hard to say if A is better or B is better, because A was better in some things and B in
some others"* — which no option expressed.

So the 50% figure conflates *"I can see these are not the same"* with *"one of them is better"*, and
it is **not** clean evidence about the reader. The option set has since been fixed: a fourth answer,
**both differ, neither better**, now separates perceiving a change from preferring one, and any
future run should quote both. What the controls do still establish is that this instrument could not
reliably return "no preference" even when there was none to have — which is the design lesson either
way.

The rest of the evidence is unaffected and points the same way. κ is at chance — slightly below it — so the human and the
judge were not seeing the same thing. 15 of the 18 calls were "slight" and none were "large". And the
side lean is the tell: left and right were randomised against the arm on every screen, so a 14-to-4
preference for the right-hand column is a fact about reading position, not about prompts. The reader's
own summary was *"I haven't seen any big difference between these cases."*

**κ ≈ 0 here does not mean the judge is bad, and it does not license reusing it either.** Two raters
can only agree when there is something to agree about; on inputs this close there was no signal for
either to find. What the calibration bought is the knowledge that **pairwise judging — human or model
— cannot resolve differences of this size**, which is worth more than a κ that flattered it. A future
experiment on a real quality difference would have to re-establish the judge on that task.

It also retires the one open question from layer 2: the judge's 38%-to-30% lean towards `before` is
not evidence of anything.

### Verdict

**The two fields ship, as planned and as worded here.**

Nothing detected a difference. Ten substance metrics each move less than their own run-to-run
variance. Gloss completeness is 100% in both arms. `primaryGloss` was a single term in all 158 usable
replies and never once copied a multi-meaning `shortGloss`. The only unparseable reply in 315 calls
came from the **shorter** prompt.

The subjective half adds nothing against that and nothing for it: 15 of 18 calls were "slight", none
were "large", the reader's summary was *"I haven't seen any big difference"*, and agreement with the
judge was at chance. **The metrics are what carry this verdict**, not the screens — an earlier draft
of this file leaned on the 50% control rate as the strongest evidence, which it is not, for the
reason given above.

So the plan's condition is met: `primaryGloss` and `emotion` go into `prompts/acervo_compose.md` and
the data model, and `acervo_compose.md` is **not** split. That decision is recorded in
[`docs/features/loops.md`](../../docs/features/loops.md) §2.8.

Two bars were missed and neither changes it: note characters at 89.4% and 89.5% against a 90% bar, on
a metric whose paired difference is a quarter of its own noise; and the gloss-language script, failed
28% of the time by llama-3.3-70b alone, on a rule that predates these fields.

### What this experiment says to do next, and does not do

- **Article quality is the real open question, and it now has its own register:**
  [`docs/plans/quality/article-quality.md`](../../docs/plans/quality/article-quality.md). Three defects went in from
  this run — a reproducibly wrong IPA vowel from `gemini-3.5-flash-lite` (6 of 6 calls, while the
  other two pairs were correct every time), the `emotion: null` boundary, and one pinyin tone error —
  along with what the run showed is already reliable, so it is not re-litigated. Every one of them is
  invisible to this experiment by construction: a defect both arms share cancels exactly.
- **Pairwise "which is better" is the wrong instrument for near-identical articles.** Anything that
  compares two versions of one prompt again should either measure against ground truth, or ask "what
  changed and does it matter" rather than "which is better".
- **The review page is worth keeping.** It reads the same on a tablet, it is one self-contained file,
  and it now shows a line-level diff beside the two articles — changed, only-A and only-B rows
  highlighted and aligned with filler, VS Code style, with both sides still shown whole. It also
  gained a free-text note per screen, and the fourth answer described above.

## Reproducing

```sh
set -a; . ./.env; set +a
export ACERVO_VERTEX_PROJECT=…                      # the row needs it; ACERVO_VERTEX_ACCOUNT must stay unset

PYTHONPATH=experiments/compose-lesson-line .venv/bin/python \
  experiments/compose-lesson-line/score.py --selftest      # the metric, before any money
.venv/bin/python experiments/compose-lesson-line/run.py --dry-run

caffeinate -is ./experiments/compose-lesson-line/overnight.sh <runId>

cd experiments/compose-lesson-line/runs/<runId>/review && python3 -m http.server 8765
PYTHONPATH=experiments/compose-lesson-line .venv/bin/python \
  experiments/compose-lesson-line/review.py score experiments/compose-lesson-line/runs/<runId>
```

`runs/` is gitignored: 360 raw model replies per run are not worth a repository, re-scoring an
existing run is free, and every number this experiment claims is in this file.

## What this does not settle

- **Whether the two fields are well worded.** This run asks whether they can be added without cost,
  not whether they are as good as they could be. The pilot already suggested one tuning question:
  `picar` returned `emotion: null`, where something like *irritated, scratching at it* would serve a
  loop better. Where the `null` boundary should sit, and how vivid a word-level direction should be,
  is a separate tuning pass — and one worth doing before the fields ship, not instead of this.
- **Whether a model is right about a word.** `la sobremesa` → *after-dinner conversation* is a
  judgement call, and nothing here checks lexicography.
- **Anything about the other prompts.** Only `acervo_compose.md` is varied.
