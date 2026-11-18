# Readings, IPA and gender checked against installed dictionaries

**Status:** ready to build. It uses `llm_json`'s `check` hook, which compose's checks already use
([`../../features/capture.md`](../../features/capture.md), "Compose's checks").
This covers defects 1 and 2 and §3 of [`article-quality.md`](article-quality.md). Each check starts
with a **free measurement** on the owner's words, because a dictionary can legitimately disagree with
a correct answer, and the measurement shows how often. That measurement is backlog row 2.

**Measured 17 Nov 2026** ([`experiments/dictionary-checks/`](../../../experiments/dictionary-checks/README.md)):
the gender and every-transcription fields are in the converter, the server has a reader, and the
comparisons are in `services/capture/dictionary_check.py`. What is left is wiring the checks into
compose with the dispositions the owner chooses from those numbers. A disagreement never refuses a
capture: it asks the next model, and keeps the first answer if none agrees.

A check runs only where the matching dictionary is installed on the server. Compiled dictionaries
are never committed, so an installation without one has no check, and nothing says it failed.

## 1 · `reading` against CC-CEDICT (defect 2: `麻烦` as `máfán`)

- CC-CEDICT carries numbered pinyin per entry (`src/acervo/dictionaries/converters.py`, `convert_cc_cedict`
  at about line 202). Compare in numbered form, using the syllable parser
  `pinyin_syllables` in `src/acervo/pinyin.py`.
- A word may have several entries (多音字). A reading that matches any of them passes.
- **The neutral tone is where both sides can be right.** `东西` is `dōngxi` (thing) and `dōngxī`
  (east and west): two entries, two meanings. Measure first how often the model and the dictionary
  differ only in a neutral tone, and decide from that number whether such a difference is demoted.
- Disposition: a reading that matches no entry demotes the model, through the chain hook.

## 2 · `ipa` against kaikki (defect 1: `el asco` as `/ˈaska/`)

- `_ipa_of` (`converters.py:127`) already keeps wiktextract's transcription for every `kaikki-*`
  dictionary.
- Compare softly: strip `/ [ ] . ˈ ˌ ː` and compare with a tolerance (`article-quality.md` §1, "Soft
  matching", Soft PER).
- **Variety matters.** A dictionary's Spanish IPA may be Castilian (`θ`), while the vocabulary's
  region is Mexico or Argentina (`s`, `ʃ` for ll/y). Measure how often the two differ only by
  variety before deciding what counts as wrong. For Spanish, comparing only the vowels and stress
  would already have caught `/ˈaska/`.
- Disposition after measuring: demote on a clear mismatch.

## 3 · `gender` from wiktextract

- `head_templates` is dropped today (`WIKTEXTRACT_DROP`, `converters.py:80`), and it carries the gender.
- Keep it as a field of the dictionary entry. **The artifact format is described twice**
  (`container.py` and `web/src/dictionary.ts`): change both, and show the gender in the external
  article.
- Then check compose's `gender` against it, disposition decided by the measurement. Installed
  dictionaries need rebuilding after the converter change (`docs/operations/deployment.md`).

## Rules that apply

- Observability: every demotion shows in `admin log` / `admin calls` with its sentence ("the
  dictionary reads 麻烦 as ma2 fan5; the model wrote ma2 fan2").
- The measurements are results: commit them under `experiments/` with a README, as the other
  experiments are, and tell the owner the numbers. Do not edit `article-quality.md` without asking.
