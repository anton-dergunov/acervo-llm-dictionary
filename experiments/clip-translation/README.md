# Experiment · does the selector translate the whole passage?

**Question.** When the clip selector picks a recorded passage for a sense, does its translation carry
**every clause** of that passage — and does saying so in the prompt actually change what models do?

**Status.** Run 16 Sep 2026: 343 calls across the three credentialed (provider, model) text pairs,
$0.33. The rewrite shipped. Results below.

## Why

A stored translation came back covering only the second half of the passage it belonged to:

> *"era un castillo un poco pijo, pero sí, trabajaba de camarera en un castillo que celebraba bodas.
> Y en el castillo nos daban un traje que picaba mucho, picaba mucho y era de color gris con"*

> *"And at the castle they gave us an outfit that itched a lot, it itched a lot and it was gray
> with"*

The castle, the waitressing and the weddings are gone, and nothing marks their absence. This is worse
than a badly chosen clip on two counts. A learner is reading a fluent translation of something other
than what is in front of them and cannot tell. And `web/src/clips.ts` sends the **stored** translation
to the corpus as `targetText` so that only the alignment stage runs — so the missing clause is also a
row of source words with nothing to attach to, and the passage stops answering to touch half way
down.

The prompt never asked for completeness. Its translation section said only *"translate that sentence
… as a whole, naturally, the way a subtitle would"* — and was wrong about its own input, since a
candidate is a passage that may run over several sentences and very often breaks off mid-phrase.

## The two arms

Whole prompt files, so the comparison stays reproducible after the rewrite ships.

- `arms/before.md` — a byte copy of `prompts/acervo_clip_select.md` as it stood, sha256
  `0024e8e9…`. Frozen **before** anything was edited.
- `arms/after.md` — the rewrite: the translation section moved from last position to second, directly
  after "Picking nothing is a success", and rewritten to demand every clause, to say what the input
  actually is, to keep a repetition repeated, to leave a broken tail broken, and to state why (the
  word-level alignment). It quotes the failure above and a complete translation beside it.

Both are rendered through the shipped reader, `acervo.services.prompts.sections`, with the shipped
default `selfContainedOnly: false`. That knob belongs to
[`clip-selection.md`](../../docs/plans/quality/clip-selection.md) and is not varied
here.

## Method

- **`passages.json`** — 10 passages, 13 (passage, target) rows. Three are segments the corpus
  actually returned, taken with their real provenance from
  `tests/unit/clips/fixtures/search-es-picar.json`; two more are the real sentences quoted inside the
  prompt itself; five are authored in the same shape and are marked `real: false`. Between them they
  carry: cut at both ends, several sentences, a repetition, a false start, fillers and a
  self-correction, two speakers, quoted speech, numerals, one 70-word run-on, one short clean control
  and one French source. Targets are English, Chinese, Japanese and Russian.
- **Requests are built by the shipped code.** `acervo.clips.select.build_request` assembles them and
  `parse_reply` reads the answers, so what is measured is the pipeline rather than a copy of it. No
  JSON Schema is sent, per AGENTS.md.
- **Every pair is called directly, never through `chain.walk`.** The chain exists to fall through,
  and a fall-through would attribute one pair's answer to another.
- **Two modes.** `translate` gives one sense and one candidate, so the passage is almost always picked
  and there is a translation to score. `select` gives two senses and a pool of candidates, and asks
  only whether the rewrite made the selector pick *more* — the prompt's first rule is that refusing is
  a success, and a longer translation section must not cost that. The `select` pools are assembled
  from the dataset rather than retrieved, which is valid for a paired before/after delta and invalid
  as an absolute production refusal rate.
- Jobs run **repeat-major**, so a run that dies half way still has both arms equally sampled.

### How coverage is measured

Each source is partitioned into clauses whose texts **concatenate back to it exactly** — asserted at
load, because a partition that has drifted scores 0.9 while meaning nothing — and each clause carries
one disjunction of acceptable renderings in each target language. Coverage is weighted by how many
characters of the source each clause is, which is what separates "dropped the whole first sentence"
(≈0.45) from "skipped one adjective" (≈0.96); a plain fraction-of-anchors-found scores both near 0.67
and is useless here.

Clauses are matched to occurrences by **maximum-weight bipartite matching**: a clause may take any
position, but no two clauses may take the same one. Both halves are load-bearing. Without the
one-occurrence-each rule, *picaba mucho, picaba mucho* is two clauses that a single "itched a lot"
satisfies twice and a dropped repetition scores full. With an **order** rule instead — the first
thing tried — every clause a target language legitimately reorders starves the next one: English puts
*posh* before *castle* and Chinese puts a relative clause before its head, and an in-order walk
scored both as missing.

Anchors are matched case- and accent-folded, as **stems** bounded at the word start and open at the
end (`itch` finds *itched*; `at` cannot find *nature*), and as plain substrings in scripts that have
no word boundaries.

The anchor-free cross-check is **relative length**: a row's length ratio over the median ratio of
*complete* rows in the same target language. It needs no per-language constant, and it puts a
faithful translation near 1.0 in every script.

`score.py --selftest` proves the metric against the real failure before any money is spent: the
stored half-translation scores 0.57 and a complete one 1.00, **identically in English and Chinese**,
and the two truncations normalise to 0.49 and 0.48 relative length.

### Anchors were corrected during a pilot, and then frozen

A 26-call pilot on one model surfaced five false negatives — renderings that plainly carry a clause
and that the first anchor list did not cover: 有点装 and 资产阶级气息 for *pijo*, 最初の月 for *el
primer mes*, 収まる and 気がまぎれる for *se me pasaba*, and "not a single soul" for *ni un alma*.
All five were widened before the measured run and applied to both arms. Three of the five were
misses in the **before** arm, so correcting them worked against the result this experiment was
hoping for, which is the direction that keeps it honest. No anchor was changed after the measured run
began.

### What the metric cannot do

`openingDropped` — "the first clause is missing" — does not fire on the very passage that prompted
this, and cannot. *castillo* occurs three times in it, so the one *castle* surviving in the truncated
translation satisfies the first clause; an anchor cannot tell which occurrence it is. Coverage and
relative length separate the two cleanly (0.57 against 1.00), so the headline numbers are those and
`openingDropped` is reported only as a diagnostic.

## Pre-registered thresholds

Written down before the measured run:

| | Threshold |
| --- | --- |
| Full-coverage rate on `usable` rows, after, every pair | ≥ 0.95 |
| Full-coverage rate, after ≥ before | per pair, and overall |
| Refusal-rate movement in `select` mode, paired on identical inputs | \|Δ\| ≤ 10 points |
| Invalid `matchedTranslationForm` rate | no worse than before |
| Median latency | ≤ 1.5 × before |

Prompt growth is **reported, not bounded**: the file grew 7,448 → 10,876 characters (+46%), which is
a much smaller share of a real request, where 20 candidates dominate.

## Results

343 calls (234 in translate mode, 109 in select mode), every one answered by a real provider, total
reported cost **$0.33**. Three pairs were credentialed: `gemini-3.5-flash-lite`,
`gemini-3.1-flash-lite` and Cloudflare's `llama-3.3-70b-instruct-fp8-fast`. Vertex, OpenAI,
OpenRouter and Ollama skipped, named, for want of a credential.

### The headline

**The rewrite eliminated severe truncation.** Coverage below 0.6 — most of the passage missing, which
is the failure that started this — happened **12 times under the old prompt and 4 under the new one,
and all 4 of those are wrong-language answers rather than truncations** (below). Counting truncation
proper: **8 before, 0 after.**

The old prompt reproduced the reported bug repeatedly and unprompted. The ten-sentence *pistachos*
passage came back from Gemini three times out of three as:

> I'm going to take something to snack on, something to eat. What can I take? I have some pistachios.
> I'm going to put them

— five of its ten clauses gone — and from Cloudflare three times as an even shorter fragment. The
castle passage lost its first half in Chinese twice, exactly as it did in the article that prompted
this work. Under the new prompt none of these recur.

### Translation coverage

| arm | pair | n picked | pick rate | mean coverage | fully covered (95% CI) | severe (<0.6) | wrong language | median rel. length | p10 rel. length | numerals kept |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| after | cloudflare/llama-3.3-70b-instruct-fp8-fast | 36 | 92% | 0.904 | 86% (71%–94%) | 3 | 3 | 1.01 | 0.91 | 100% |
| after | gemini-free/gemini-3.1-flash-lite | 39 | 100% | 0.993 | 95% (83%–99%) | 0 | 0 | 1.03 | 0.94 | 100% |
| after | gemini-free/gemini-3.5-flash-lite | 30 | 77% | 0.964 | 93% (79%–98%) | 1 | 1 | 1.04 | 0.95 | 100% |
| before | cloudflare/llama-3.3-70b-instruct-fp8-fast | 39 | 100% | 0.840 | 72% (56%–83%) | 7 | 4 | 0.97 | 0.58 | 100% |
| before | gemini-free/gemini-3.1-flash-lite | 39 | 100% | 0.992 | 90% (76%–96%) | 0 | 0 | 0.99 | 0.89 | 100% |
| before | gemini-free/gemini-3.5-flash-lite | 33 | 85% | 0.914 | 82% (66%–91%) | 5 | 0 | 0.96 | 0.28 | 100% |
| after | all pairs | 105 | 90% | 0.954 | 91% (85%–95%) | 4 | 4 | 1.02 | 0.95 | 100% |
| before | all pairs | 111 | 95% | 0.915 | 81% (73%–87%) | 12 | 4 | 0.98 | 0.80 | 100% |

Reference ratios (median length ratio of complete translations, per target language): {'en': 1.0534, 'zh': 0.3556, 'ja': 0.4799, 'ru': 1.0209}

### The paired comparison

Paired on 102 cells where both arms picked (same passage, pair and repeat):

| | after complete | after incomplete |
| --- | ---: | ---: |
| **before complete** | 79 | 2 |
| **before incomplete** | 14 | 7 |

14 cells fixed, 2 broken. McNemar exact p = 0.0042.

### Selection health

| pair | paired requests | picked before | picked after | Δ | the passage the off-by-default rule rejects, refused | invented ids |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cloudflare/llama-3.3-70b-instruct-fp8-fast | 10 | 60% | 70% | +10 pp | 0/1 | 0 |
| gemini-free/gemini-3.1-flash-lite | 19 | 79% | 79% | +0 pp | 0/2 | 0 |
| gemini-free/gemini-3.5-flash-lite | 20 | 70% | 80% | +10 pp | 0/2 | 0 |
| all pairs | 49 | 71% | 78% | +6 pp | 0/5 | 0 |

8 request(s) answered under only one prompt and 3 that did not answer are excluded: Cloudflare reached its daily allowance during the second repeat and was parked.

### Latency and cost

| arm | pair | calls | median s | p90 s | median prompt chars | median reply chars | reported cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| after | cloudflare/llama-3.3-70b-instruct-fp8-fast | 49 | 2.90 | 4.68 | 10364 | 365 | $0.0530 |
| after | gemini-free/gemini-3.1-flash-lite | 58 | 2.46 | 4.41 | 10364 | 377 | $0.0555 |
| after | gemini-free/gemini-3.5-flash-lite | 59 | 0.91 | 1.33 | 10364 | 377 | $0.0722 |
| before | cloudflare/llama-3.3-70b-instruct-fp8-fast | 57 | 2.69 | 6.31 | 6956 | 356 | $0.0508 |
| before | gemini-free/gemini-3.1-flash-lite | 58 | 3.23 | 6.09 | 6956 | 370 | $0.0435 |
| before | gemini-free/gemini-3.5-flash-lite | 59 | 0.86 | 1.23 | 6956 | 343 | $0.0564 |

### Where the two metrics disagree

- `acostumbrarse-larga` ja (after, cloudflare): normal length (2.03) but coverage 0.00
- `acostumbrarse-larga` ja (after, cloudflare): normal length (2.04) but coverage 0.00
- `acostumbrarse-larga` ja (after, cloudflare): normal length (2.17) but coverage 0.00
- `empatia-picar` ru (after, cloudflare): normal length (0.97) but coverage 0.78
- `empatia-picar` ru (after, cloudflare): normal length (0.97) but coverage 0.78
- `acostumbrarse-larga` en (after, gemini-free): normal length (0.96) but coverage 0.93
- `castillo-picar` zh (after, gemini-free): normal length (1.04) but coverage 0.81
- `acostumbrarse-larga` ja (after, gemini-free): normal length (2.02) but coverage 0.00
- `castillo-picar` zh (after, gemini-free): normal length (1.08) but coverage 0.93
- `empatia-picar` ru (before, cloudflare): normal length (0.97) but coverage 0.90
- `acostumbrarse-larga` ja (before, gemini-free): normal length (0.99) but coverage 0.92
- `acostumbrarse-larga` ja (before, gemini-free): normal length (1.12) but coverage 0.92

### The worst translations in the run

**`acostumbrarse-larga` → ja, after prompt, cloudflare** — coverage 0.00, 0.97 of the source's length:

> Well, what happened is that I arrived in Madrid without knowing anyone, not a soul, and the first month was very tough, because it was also raining every day, and I would leave work at 9 and had no one to call, so I got used to walking alone in the center until it passed, and look, in the end that's what saved me

**`acostumbrarse-larga` → ja, after prompt, cloudflare** — coverage 0.00, 0.98 of the source's length:

> Well, what happened was that I arrived in Madrid without knowing anyone, not a soul, and the first month was really tough, because it was also raining every day, and I would leave work at 9 and had no one to call, so I got used to walking alone in the center until it passed, and look, in the end that's what saved me

**`acostumbrarse-larga` → ja, after prompt, cloudflare** — coverage 0.00, 1.04 of the source's length:

> Well, what happened was that I arrived in Madrid without knowing anyone, not a single soul, and the first month was incredibly tough, because it was also raining every day, and I would leave work at 9 and had no one to call, so I got used to walking alone in the city center until I felt better, and look, in the end that's what saved me



### Against the thresholds set before the run

| | Threshold | Result | |
| --- | --- | --- | --- |
| Full coverage, after, every pair | ≥ 0.95 | 0.91 overall (0.95 / 0.93 / 0.86) | **missed** |
| …excluding wrong-language answers | — | **0.95** overall | met, once that separate failure is separated |
| Full coverage, after ≥ before | per pair and overall | 0.91 vs 0.81 overall; every pair up | met |
| Severe truncation (< 0.6), after | — | 8 → 0 | met |
| Refusal movement, select mode, paired | \|Δ\| ≤ 10 pp | +6 pp overall (+10 / 0 / +10) | met, at the boundary on two pairs |
| Invalid `matchedTranslationForm` | no worse | 0% both arms; *omitted* fell 4 → 0 | met |
| Median latency | ≤ 1.5 × before | 2.12 s → 2.23 s (×1.05) | met |

Prompt growth, reported not bounded: the file grew 7,448 → 10,876 characters, but a real request
carries its candidates too, so the whole prompt grew 6,956 → 10,364 characters — **+49%** on a request
that in production is larger still, since these requests offer at most nine candidates against the
twenty the corpus returns.

**The ≥0.95 bar was missed and is reported as missed.** The shortfall is one pair — Cloudflare's
llama at 0.86 — and it is not truncation: three of its five failures are the wrong-language answers
below, and the other two are a single clause each.

### Two failures the experiment found that it was not looking for

**Answering in the wrong language.** Asked to translate into Japanese, Cloudflare's llama replied in
fluent, complete English — three times under each prompt — and Gemini did it once. Eight rows in all,
**four under each prompt**, so it is nothing to do with the rewrite. It is a complete translation and
a total failure of the request, and coverage reported it as 0.00 with no way to say why. The scorer
now names it (`inTargetScript`), by reading the reply's own codepoints against the script the target
language uses. Worth a rule in the prompt, and worth a check in `parse_reply` — the script of a reply
is cheap and unambiguous to test, unlike its completeness — but both are out of scope here.

**Leaving a fragment untranslated.** Cloudflare's llama returned a Russian translation with a Spanish
clause still sitting in it:

> Чтобы в конце концов у тебя была немного эмпатия, чтобы если тебе нужно что-нибудь, даже сахар, что
> **parece una tontería**, но это очень реально и чтобы ты мог перекусить

Coverage marked the clause missing, which is right: for a reader of Russian it is missing.

### What the metric got wrong, and what was done about it

The anchor lists carry a false-negative rate, and at three models over three repeats it was large
enough to matter: the first scoring of the measured run put full coverage at 80%/70%, and inspection
of every incomplete row showed most were renderings the lists had not anticipated — *a foolish
thing*, 势利, 気が晴れる, *coming back* (a stem anchor cannot reach an inflection that changes the
stem), *until I felt better*. Those were widened, applied to both arms, and the run re-scored — which
costs nothing, because scoring never makes a call.

This is post-hoc correction of the instrument and is disclosed as such. Three guards on it: only
false negatives were corrected, never a coverage verdict on a genuinely missing clause; every
correction applies to both arms; and the direction of the corrections was **against** the hypothesis
as often as for it — the pre-correction numbers were 80% after / 70% before, the post-correction ones
91% / 81%, so the correction lifted the old prompt by 11 points and the new one by 11.

One conflation was also found and fixed in the analysis rather than the data. The first paired table
counted "this arm refused to pick" as "this arm translated incompletely", which charged the rewrite
for obeying the prompt's first rule; p fell from 0.34 to **0.0042** once the pairing was restricted to
cells where both arms picked. Refusal movement is Table 2's question and is answered there.

### Postscript: it shipped, and it regressed

**The rewrite was deployed and immediately produced a failure this experiment had no metric for.**
Two clips on `la casa` came back with the Spanish passage copied verbatim into `translation` —
`translationLang: en`, `modelId: gemini/gemini-3.5-flash-lite`, a model this run measured 69 times.
In the article the translation line read identically to the sentence above it, and the player,
which is handed the stored translation as its target text, aligned the passage against itself.

Reproduced against the real article, with the request built by the shipped `build_request`:
**4 of 8 translations copied under the new prompt, 0 of 8 under the old one**, same model, same
request. The cause is the rewrite's own emphasis: "every clause must appear", "nothing left out",
"translated as far as it goes and left broken", landing near the pre-existing "do not change the
sentence", adds up to *reproduce the passage* for a model reading quickly.

It is **intermittent**, which is why the numbers above did not catch it: across every sample since,
the regressing prompt copied 4 times in 22 and the corrected one 0 in 20 — encouraging, well short
of proof, and both free tiers were exhausted before a decisive sample could be taken.

Three things changed as a result, and only one of them is the prompt:

- **The prompt** now states the target language as an equal half of the instruction, names copying as
  a failure with a worked example of it, and makes the final check ask "is this in `translationLang`,
  and is it not simply the passage again?" before asking about completeness.
- **`parse_reply` refuses a translation identical to its passage** (`select.py`), the way it already
  refuses one that never stops. Exact, so it needs no threshold and no language table — and it is the
  guarantee the prompt cannot give, since a prompt is a request and this is a check.
- **The scorer gained `copiedSource`**, and the dataset now carries the **examples a real article
  holds**. The requests measured above had none: one sense, one candidate, no examples, which is a
  shape the server never sends. Re-scored with the new metric, all 296 recorded rows are clean — the
  copying genuinely did not occur in this run — but a class of failure that no metric names is a
  class that cannot be reported, and that is the lesson worth keeping.

**What this says about the experiment, not the prompt.** Three repeats over ten passages is enough
power for a failure that happens half the time and nowhere near enough for one that happens a fifth
of the time on one passage. Every number above is honest about the failure it measured; none of them
had anything to say about the failure that shipped.

### Verdict

The rewrite ships, with the correction and the code guard the postscript describes. It does what it
was written to do — severe truncation goes from 8 occurrences to none, full coverage rises 10 points,
and the improvement is significant on a paired test — at a cost of half a second of median latency
and no measurable damage to refusal behaviour. It does not reach 0.95 on every pair, and the gap is
one weak model whose remaining failures are mostly a different bug.

It also shipped a regression, which is in the postscript rather than hidden here, and the
measurements above should be re-run once the free tiers reset: the request shape has changed to carry
examples, and `copiedSource` is a column this run could not report.

What this run does **not** support is a code-level completeness check: see
[`docs/plans/quality/translation-completeness-check.md`](../../docs/plans/quality/translation-completeness-check.md).
The reference ratios here — en 1.05, ru 1.02, ja 0.48, zh 0.36 — are each from one or two passages,
which is enough to show that a single absolute floor cannot serve every script and nowhere near
enough to set one per script.

## Reproducing

```bash
set -a; . ./.env; set +a
PYTHONPATH=experiments/clip-translation .venv/bin/python experiments/clip-translation/score.py --selftest
.venv/bin/python experiments/clip-translation/run.py --dry-run
PYTHONPATH=experiments/clip-translation .venv/bin/python experiments/clip-translation/run.py --mode translate --repeats 3
PYTHONPATH=experiments/clip-translation .venv/bin/python experiments/clip-translation/run.py --mode select --repeats 2 --run <runId>
PYTHONPATH=experiments/clip-translation .venv/bin/python experiments/clip-translation/score.py experiments/clip-translation/runs/<runId>
PYTHONPATH=experiments/clip-translation .venv/bin/python experiments/clip-translation/report.py experiments/clip-translation/runs/<runId>
```

`build_passages.py` rewrites `passages.json` from the authored source and is where the clause
partition is checked; run it after editing a clause or an anchor.
