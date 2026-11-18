# Dictionary checks: how often does an installed dictionary disagree with a right answer?

Compose writes a word's `reading`, `ipa` and `gender` from memory, and the register in
[`article-quality.md`](../../docs/plans/quality/article-quality.md) holds two cases where that went
wrong: `el asco` as `/ˈaska/` (6 of 6 calls on the head model) and `麻烦` as `máfán`. Installed
dictionaries attest all three fields, and [`dictionary-checks.md`](../../docs/plans/quality/dictionary-checks.md)
plans to demote a model whose answer disagrees. But a dictionary can disagree with a right answer
too: 东西 is both `dōngxi` and `dōngxī`, and Wiktionary lists one transcription per variety without
saying which. This measurement counts how often, and in which way, before any check is switched on.

**Status:** measured 17 Nov 2026. The dispositions are the owner's to choose (below).

## Method

Free: no model is called.

- **The words** are every live word in the owner's store, pulled read-only (`extract_remote.py`):
  936 Spanish, 801 English, 4 Chinese. The English vocabulary holds 227 words twice, identical, so
  each word is counted once (574 English). All were written before varieties existed, so they are in
  each language's default variety. Most were written by `gemini-3.7-flash`, and some were corrected by
  hand. They are mostly right, so **a disagreement here is mostly a false alarm the check would raise**.
- **The dictionaries** are the wiktextract ones rebuilt with this change (`kaikki-es-en`,
  `kaikki-es-es`, `kaikki-en-en`, `kaikki-en-ru`, which now keep every transcription and the noun's
  genders) and CC-CEDICT, read through the shipped server reader.
- **The comparisons** are the shipped ones (`src/acervo/services/capture/dictionary_check.py`), so
  what is counted is what a check would see:
  - A word is looked up under its headword, then the headword without its first word (`el asco` →
    `asco`), then its lemma. A transcription is compared only with an entry of the same form: one
    found under the lemma (`asustar` for `asustado`, `apunte` for `los apuntes`) is another word's
    sound, and those are counted as `other-form`.
  - **Readings** are cut into Pinyin syllables on both sides. Classes: `match`; `neutral-only` (they
    differ only where one side has the neutral tone); `sandhi-only` (only where 一, 不 or a third tone
    before a third is said differently from how it is written); `tone-mismatch`; `mismatch` (other
    syllables).
  - **Transcriptions** are compared phone by phone after notation that does not change the sound is
    evened out: delimiters, syllable dots and ties; `ɹ`/`r`, `ɚ`/`ər`, ASCII `g`; syllabicity marks;
    optional sounds in parentheses, expanded both ways; lists split at commas. Classes: `match`;
    `stress-only` (stress or length marked differently); `vowels-agree` (the same vowels and the same
    stressed vowel, consonants aside); `close` (phone error rate ≤ 0.2); `mismatch`. Each word is
    scored against the dictionary's first transcription and against any of them.
  - **Gender** is compared for nouns. A stored `common` agrees with a dictionary that lists both
    masculine and feminine.
- **Two published sources.** Four Chinese words cannot give a rate, so Wiktionary's Mandarin Pinyin
  (English edition) is also compared with CC-CEDICT's for all 4,721 words both hold. Both are
  published and edited, so this is how often two right answers disagree, and how.

Run: `.venv/bin/python experiments/dictionary-checks/measure.py --words out/words.json --dictionaries
data/dictionaries/out --chinese data/dictionaries/src/kaikki.org-dictionary-Chinese.jsonl`. It writes
[`report.md`](report.md) (every table, and every disagreement listed in full) and `results.json`
(one row per word).

## Results

### Readings: neutral tones are where sources disagree

| Wiktionary against CC-CEDICT, per word (4,721) | words | share |
| --- | ---: | ---: |
| `match` | 4,617 | 97.8% |
| `neutral-only` | 80 | 1.7% |
| `tone-mismatch` | 2 | 0.04% |
| `mismatch` (literary readings: 百 `bó`) | 13 | 0.3% |
| unparsed or not held | 9 | 0.2% |

Per reading rather than per word, `neutral-only` rises to 3.3% and `tone-mismatch` to 3.5%, because
Wiktionary often lists a Taiwan reading beside the mainland one (`wǒmén`, `péngyǒu`). The check takes
a model's single reading against every entry, which is the per-word figure. **A neutral-tone
difference is exactly defect 2 (`máfán` for `ma2 fan5`), and it is also what separates two right
sources in 1.7% of words.** All 4 stored Chinese words match.

### Transcriptions: once forms and notation agree, almost nothing is left

| | Spanish (806 compared) | | English (521 compared) | |
| --- | ---: | ---: | ---: | ---: |
| | first variant | **any variant** | first variant | **any variant** |
| `match` | 69.9% | 77.0% | 58.3% | 72.0% |
| `stress-only` | 1.0% | 1.1% | 9.8% | 15.9% |
| `vowels-agree` | 26.3% | 21.5% | 9.2% | 1.9% |
| `close` (PER ≤ 0.2) | 1.6% | 0.1% | 15.4% | 8.6% |
| `mismatch` | 1.2% | **0.2%** | 7.3% | **1.5%** |

127 Spanish and 53 English words were found only under another form and not compared.

- **Comparing against any variant matters.** It cuts mismatches five-fold in both languages, which
  is the variety effect the plan expected (`calle` is `/ˈkaʝe/`, `/ˈkaʎe/`, `/ˈkaʃe/`… in that order).
- **Spanish's two mismatches are both real errors**: `arruinar` as `/aruˈnaɾ/` (a sound dropped) and
  `las acciones` as `/akˈsjon/` (the plural lost). The one `close` is notation (`awto`/`auto`).
- **Spanish `vowels-agree` (21.5%) is mostly allophones and notation**: `/baˈriɣa/` against
  `/baˈriɡa/`, `/eˈɾiða/` against `/eˈɾida/`. But not only. `el aviso` as `/aˈbiθo/` is in this class,
  and a `θ` where the spelling has `s` is wrong in every variety. A check that passed `vowels-agree`
  would not see it.
- **English's eight mismatches are mostly notation and variety**: `/dred/` against `/dɹɛd/` (`e` for
  `ɛ` is a British convention), `/ˈsɑːfəmɔːr/` against `/ˈsɒfəmɔɹ/`, `/ˌoʊvərˈzɛləs/` against
  `/ˌəʊvəˈzɛləs/`. The `close` band is full of them too. English transcriptions disagree in
  convention far more than Spanish ones.
- `/ˈaska/` against `/ˈasko/` scores PER 0.25, so it is a `mismatch`, as is any one wrong phone in a
  word of four or fewer phones. One wrong phone in a longer word falls under 0.2 and is `close`.

### Gender: no disagreement at all

383 Spanish nouns held by a dictionary: **383 match**. Seven disagreed before two fixes: five
`common` nouns (`el guionista`, `el intérprete`) that Wiktionary lists as masculine and feminine,
and `la enana`, which had been looked up under its lemma `enano` instead of its own form.

## What the dispositions could be

The cost of a false alarm is set by the decision already taken: a disagreement never refuses a
capture. It asks the next model, and keeps the first answer if none agrees. So a false alarm costs
one more call and its seconds, never a word.

| Check | Proposal | False alarms on stored words | Catches |
| --- | --- | --- | --- |
| reading | demote on `neutral-only`, `tone-mismatch`, `mismatch`; pass `sandhi-only` | ≈ 2% of Chinese captures (1.7% two-source rate) | defect 2 |
| reading | demote on `tone-mismatch`, `mismatch` only | ≈ 0.3% | not defect 2 |
| ipa | demote on `mismatch` against any variant | Spanish 0% (both were real), English 1.5% | defect 1, `arruinar`, `las acciones` |
| ipa | also demote on `vowels-agree` | Spanish 21.5%, mostly right answers | `el aviso`'s `θ`, at that price |
| gender | demote on `mismatch` | 0% | a wrong gender |
