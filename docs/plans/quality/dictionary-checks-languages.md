# Dictionary checks in the languages not yet measured

**Status:** open, not run. Written 18 Nov 2026, when the checks were built
([`../../features/capture.md`](../../features/capture.md), "Compose's checks").

The dictionary checks fire for every language that has an installed `fields` dictionary, but their
dispositions were measured on Spanish and English transcriptions, Spanish genders and Mandarin
readings only (`experiments/dictionary-checks/`). A server that holds `kaikki-ru-*`, `kaikki-de-*`,
`kaikki-fr-*`, `kaikki-it-en`, `kaikki-pt-en`, `kaikki-ja-*` or `kaikki-zh-*` already checks those
languages, unmeasured. A false alarm costs one more model call and never the word, so nothing has to
change before this runs. But nobody knows the rate, and two languages give reasons to expect trouble:

- **Chinese entries mix varieties.** A `kaikki-zh-*` entry carries Mandarin, Cantonese, Hokkien and
  Wu transcriptions, and the converter keeps them without saying which is which (`_ipas_of` drops
  the tags). A Cantonese (`zh-yue`) word is compared against all of them, so a right answer may be
  flagged for its tone notation, and a wrong one may pass because it is close to another variety's.
- **Japanese entries are narrow phonetic transcriptions**: `犬` is `[inɯ̟]`, `馬` is `[ɯ̟ma̠]`. A
  model writes `/inu/`. The comparison keeps diacritics as part of the phone, so `ɯ̟` is not `u`, and
  in a word of two or three phones a single difference is a `mismatch`.

Russian matters most of all: it is a wave-1 starter vocabulary
([`../first-use/starter-vocabularies.md`](../first-use/starter-vocabularies.md)), and the owner can
check it. Wiktionary writes Russian phonetically, with vowel reduction (`[sɐˈbakə]`), while a model
may write it phonemically. Gender has been measured only for Spanish. German's neuter and Russian's
three genders are untested.

## The question

For each language a check now fires on (Russian, German, French, Italian, Portuguese, Japanese,
Cantonese), how often does a dictionary disagree with a **right** answer, and how often does it catch
a **wrong** one? The checks are IPA (any variant, same form) and gender (nouns).

## The run

1. **Dictionaries.** Rebuild every `kaikki-*` above on the laptop with the current converter; the
   sources are already in `data/dictionaries/src/`. Free.
2. **Words.** The stored words cannot serve, because the owner holds none in these languages. Compose
   a sample with the shipped request (`compose.build_user_message`, through `llm_json` with the
   shipped `vet` and checks **off**, so every raw answer is kept). The sample is the 200 most frequent
   nouns, verbs and adjectives per language that a dictionary holds, from `wordfreq`. For
   Cantonese, take the Chinese list's words that `cc-canto` holds. `wordfreq` goes in the
   experiment's own environment, never in `requirements/`. Seven languages × 200 words on the head
   model costs roughly $1–2, charged to the Vertex trial credits. If the starter vocabularies are
   composed first, their raw model output replaces this sample through the same apparatus.
3. **Measure** with the existing `experiments/dictionary-checks/measure.py`, extended to take the
   sample's words file. It writes a second report beside the first (`report-languages.md`) with the
   same tables per language and every disagreement in full.
4. **Adjudicate the disagreements**, which unlike the first run were never checked by anyone. Claude
   labels each one as model wrong, dictionary or notation, or two right varieties, and the owner
   spot-checks the Russian ones. That yields both rates: false alarms and real catches.

## What the result decides

- A language whose false alarms are notation: fix the notation step in `dictionary_check.phones`,
  which is generic (advanced and retracted marks such as `̟` and `̠`, for example), and re-measure. Never add a branch for one
  language.
- If Chinese's mixed varieties are what fails, keep each transcription's variety tag in the artifact
  and compare only the vocabulary's own variety. That changes the artifact format, so `container.py`
  and `dictionary.ts` change together and the `kaikki-zh-*` dictionaries are rebuilt.
- Gender: if any language disagrees on right answers, its cause goes into the converter, as Spanish's
  `common` nouns did.
- The results and dispositions fold into `capture.md`, "Compose's checks", and this file is deleted.

Out of scope: Japanese kana readings and Korean (no `kaikki-ko` is installed, so nothing fires).
