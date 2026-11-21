# Compose audit

**Question.** In the 10,177 starter articles (`data/starter/`, twenty vocabularies, written by
`gemini-3.5-flash-lite` and `gemini-3.1-flash-lite` through compose's own prompt and checks), what is
wrong that a rule can find with no model? Which of it should compose stop, and what is left for a
judge?

**Why.** `docs/plans/quality/article-quality.md` §0–§1: no criteria and no measured accuracy. The
corpus is the first large multilingual sample of what compose writes. An Argon judge is planned next
(starter plan step 5), and it should spend itself on what a rule cannot see.

## Method (free)

`audit.py` reads every composed word and counts, per vocabulary and model, the failures a rule
decides. `--selftest` runs each counter on cases it must and must not flag. Every flagged article
behind the first numbers was read in the session that wrote it (21 Nov 2026), and the false positives
that came out of that are excluded by the counters: `々` and `T恤衫` are not two scripts, Arabic
transliteration in an English note is not garbled, and a German separable verb has no single
`matchedForm`.

## What it found, 21 Nov 2026, before the fixes

| Failure | Articles | Where |
| --- | ---: | --- |
| A word written in two scripts (`σπίti`, `Λαtrεύω`, `बच्चe`, `ชาว농장에`, `De bij zoemมี`, and one example reading "Πτάin the text -> Πτό... wait, let's make a clean example.") | 80 | el-GR **62 of 297** on 3.5 Flash-Lite (21%), **0 of 206** on 3.1; hi 8, th 4, ko 2, ar 2, ru 1, nl 1 |
| An example in another script: an English sentence as a Thai example ("The learner did not provide a sentence for this."), `vending machine.` as Chinese, Hindi examples in Urdu's script | 5 | hi 3, th 1, zh 1 |
| The headword rewritten by compose (`देना` → `denā`, `जानना` → `جاننا`, `पढ़ाना` → `प पढ़ाना`, `ήδη` → polytonic `ἤδη`) | 7 | hi 6, el 1 |
| `reading` in another form than the language's: Japanese 299 romaji against 218 kana, Korean romanised with tone marks it does not have (`mā si da`), Thai, Hindi and Arabic in several schemes | 1,211 | ja, ko, th, hi, ar, ru |
| `ipa` with the article (`der Stern /deːɐ̯ ʃtɛʁn/` beside `das Dach /dax/`) | 366 | de 121, pt 80, es-MX 49, el 40 |
| `gender` the language or the part of speech does not have: English nouns `neuter`, adjectives, verbs | 487 | es 116, en 58, ar 55, pt 49, fr 49 |

All six are now compose's checks (`docs/features/capture.md`, "Compose's checks"). `build.py revet`
applied them to the stored corpus: coercions to the drafts in place (sense ids kept, so matches
stand), and **85 words** whose reply is now refused set aside under `compose.replaced/` to be
composed again (62 Greek). `report.md` after revet: every one of the six at 0.

## What is left for a judge

`report.md` keeps the signals. They are not errors by themselves:

- **Senses.** Mean 1.4–1.7 a word, and 37–61% of words single-sense, the same on both models.
  Common verbs come out thin (`dar` 2, `llevar` 2, `stellen` without *eine Frage stellen*, `go` 2),
  while marginal senses get in (chemistry *salt*, `uyumak` "lie dormant"). Only a judge with a
  reference can tell a missing sense from a word that has one.
- **Notes.** ~430 notes restate the gender or the meaning ("Barato means cheap"), and reading found
  false ones (`museum`: "museo is stressed on the last syllable") and notes naming a sense the article
  lacks (`caro` "dear").
- **Examples.** 54 with no marked word, a few of them not containing the word at all (`el pato`, `il
  fratello` → *frate*, `工作` → `工具`); unnatural grammar a rule cannot see (`Muszę kupować…`).
- **The two models differ** in what they leave out: 3.1 Flash-Lite wrote no example at all for 299
  words against 13, and no IPA for 1,167 against 230.

## Files

- `audit.py`: the counters, the report and the selftest.
- `audit.json`: flagged word keys per counter and vocabulary, and per-cell counts.
- `report.md`: the table, per vocabulary and per model.
