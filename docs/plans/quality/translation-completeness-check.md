# Experiment · catching a translation that stopped early

**Status:** Unstarted, and deliberately so. The prompt half of this shipped first — the translation
section of [`../../../prompts/acervo_clip_select.md`](../../../prompts/acervo_clip_select.md) was rewritten to
demand every clause, and the rewrite is measured in
[`experiments/clip-translation/`](../../../experiments/clip-translation/README.md). What has **not**
shipped is any code that refuses an incomplete translation, and this document exists because the
data to set such a check honestly does not exist yet in this deployment.

## The question

A clip's stored translation can come back covering only part of the passage it is a translation of.
Can that be detected in `parse_reply`, **without ground truth, without a second model call, and
across every language Acervo might translate into**, at a false-rejection rate low enough to be
worth having?

## Why it matters more than a prose defect

The reader taps a word in the passage and the words that answer to it light up in the translation.
`web/src/clips.ts` sends Acervo's **stored** translation to the corpus as `targetText`, so only the
alignment stage runs and the alignment is computed against exactly that text. A missing clause is
therefore a row of source words with nothing to attach to — and, before anyone notices that, a
learner reading a confident translation of something other than what is in front of them, with no
way to tell. The clip search is one-shot at save, so nothing replaces it.

## The signal, and the reason it is not yet a constant

Truncation has a length signature. Measured on the passage that prompted this work (source 187
characters):

| translation | chars | ratio to source |
| --- | ---: | ---: |
| es→en, as stored, first sentence dropped | 96 | **0.51** |
| es→en, complete | 195 | **1.04** |
| es→zh, complete | 66 | **0.35** |
| es→zh, same first sentence dropped | 32 | **0.17** |

A truncation is about **half** of what its own language normally weighs — in both scripts. But the
normal weight differs by a factor of three between them, so a single absolute floor catches the
broken English and rejects the perfectly good Chinese. Per-script-class constants are the obvious
answer and **cannot be produced from this deployment's data**: the vocabularies are ~1,437 Spanish
senses, ~855 English and one Chinese, which yields es→en and en→ru and nothing else. A constant for
a dense script fitted to a handful of rows would be a guess wearing a measurement's clothes, and
this is a guardrail whose false positives cost real clips.

## The data, since ours is too thin

In this order:

1. **FLORES-200** — the same 2,009 sentences professionally translated into 200+ languages. Because
   it is the *same* sentences everywhere, per-language length ratios are directly comparable with no
   alignment work and no sampling bias between languages. This is the backbone, and the one source
   that answers "what about the languages we have never seen".
2. **OPUS / OpenSubtitles**, per language pair, for **register**. Acervo's passages are transcribed
   speech; FLORES is clean written prose. A ratio fitted only to prose may not survive real captions,
   and this is the cheapest way to find out before shipping rather than after.
3. **The owner's own export bundle**, as the reality check on es→en and en→ru: real Acervo records,
   in the exact shape the check will see, including its short and formulaic ones.

## The method, which needs no model calls at all

Truncation can be **simulated**, which is what removes the need for ground truth. For every parallel
pair:

- compute the length ratio of the complete translation;
- recompute it with the first sentence dropped, with the last dropped, and with an interior clause
  dropped.

That yields, for every language pair, the distribution of ratios for complete translations and for
each shape of truncation. A threshold is then read off where the two separate, with its
false-positive rate **stated** rather than asserted — and it is read off per script class rather than
per language, since the class is what a runtime check can detect from the text itself.

The one thing this cannot simulate is how a **model** truncates, which is not the same as dropping a
sentence with a script. That is what `experiments/clip-translation/` supplies: real truncations from
real pairs, labelled complete or not by character-weighted clause coverage, held out as the check on
whatever threshold the simulation produces.

## What else to measure while the corpora are open

Each of these ships only on evidence, and a negative result is worth writing down so the next session
does not try it again:

- **Numeral parity** — every digit run in the source occurs in the translation. Free, script
  independent, and it catches a dropped clause that carried a number. Its one false-positive mode is
  a model spelling *forty-eight*; measure that rate.
- **Sentence-terminator count**, which is the obvious idea and probably a bad one: a target language
  is free to join or split sentences.
- **A per-request prior.** `build_request` already passes each sense's own `text`/`translation`
  pairs, in the same language pair, from the same article. Whether two or three short examples
  supply a usable local expectation — no table, no constant, no corpus — is worth one afternoon
  because if it works it is strictly better than any global number.

## What would have to be true to ship it

Written down before the numbers, as `docs/plans/quality/clip-selection.md` does:

- **Zero false rejections** over complete translations at the chosen threshold, with N stated.
- A catch rate worth having on the simulated truncations — a check that fires on nothing is a check
  nobody should pay attention to.
- Agreement with the real truncations from `experiments/clip-translation/`.
- **A script class with no data ships no check for that class.** Not a guessed constant, and not a
  constant borrowed from a different script.

If the answer is that no threshold separates the two distributions well enough, that is a result:
write it down, and the prompt stays the only instrument.

## The cheaper first step to consider first

Record the length ratio of every clip translation in the model-call journal — the log
`python -m acervo.admin calls` already reads — and look at real traffic for a few weeks. It costs
nothing, risks nothing, is reversible, and produces exactly the distribution this experiment is
trying to borrow from public corpora, in the deployment's own languages and register. The argument
against is only that it is slow, and that it says nothing about a language the owner has not started
learning yet. Decide that here rather than by default.

## Where the check would go, if it ships

`parse_reply` in [`src/acervo/clips/select.py`](../../../src/acervo/clips/select.py), beside the
existing upper bound — `len(translation) > max(240, 3 × len(source))`, "the model did not stop
writing". A lower bound is the same kind of fact about a pair and is handled the same way: raise,
`_select_once` turns it into `ProviderUnavailable("unusable")`, and the chain passes that pair over.

The false-rejection cost must be stated correctly when that is argued. A raise does **not** mark the
word searched: `services/clips.py` never reaches `_write`, so `clipsSearchedAt` stays null and
a backfill — which derives its work from `clipsSearchedAt IS NULL` — picks the word up again. So a false reject costs the clip at save time *and* an unbounded re-search of a word that was
fine, which is the worse half and the reason the threshold must sit well clear of the complete
distribution.
