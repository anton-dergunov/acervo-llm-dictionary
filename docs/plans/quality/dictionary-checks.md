# Readings, IPA and gender checked against installed dictionaries, and a switch for the checks

**Status:** measured 17 Nov 2026, dispositions chosen by the owner. What is left is wiring the checks
into compose and adding one setting that turns compose's checks off. This covers defects 1 and 2 and
§3 of [`article-quality.md`](article-quality.md), and backlog row 2.

## Already built

- **Dictionary entries.** Wiktionary entries keep every transcription (`ipas`) and the noun's genders
  (`genders`) (`dictionaries/converters.py`, `model.py`; `web/src/dictionary.ts`). The external article
  shows the gender ([`../../features/dictionaries.md`](../../features/dictionaries.md), "The artifact").
- **The server's reader.** `services/dictionaries/lookup.articles_for(directory, language, keys)`
  returns a `Found(dictionary_id, key, articles)` per installed `fields` dictionary of the word's
  language. With none installed, an unreadable one or no entry, the list is empty.
- **The comparisons**, in `services/capture/dictionary_check.py`, pure and pinned by
  `tests/unit/server/test_dictionary_check.py`:
  - `keys_for(headword, lemma)`: headword, then the headword without its first word, then lemma;
  - `reading_verdict` and `gender_verdict`;
  - `transcription_to_judge(headword, ipa, found)`, which compares only an entry of the same form, then
    `ipa_verdict(said, ipas)` against any variant;
  - `attested(articles)`.
- **The measurement**: [`experiments/dictionary-checks/`](../../../experiments/dictionary-checks/README.md).

## 1 · The dispositions (owner, 18 Nov 2026)

| Check | Demotes on | Passes | False alarms on stored words |
| --- | --- | --- | --- |
| `reading` (Pinyin on both sides) | `neutral-only`, `tone-mismatch`, `mismatch` | `match`, `sandhi-only` | ≈ 1.7% (two published sources) |
| `ipa` (same form, any variant) | `mismatch` (phone error rate > 0.2) | everything else | Spanish 0%, English 1.5% |
| `gender` (nouns) | `mismatch` | `match`, `model-none` | 0% |

Each is a **soft demotion**: a disagreement never refuses a capture.

- **`llm_json`** (`services/models.py`) gets a `Demoted(Unusable)` exception that carries the checked
  answer. `ask` raises it as `unusable`, so the pair is passed over and its sentence goes in the call
  log, and keeps `(result, checked)` aside. On `ChainExhausted`, if any pair was only demoted, the first
  one kept is returned with its own `Answer`, and `journal.outcome(caller, kept="dictionary",
  pair=…, detail=<sentence>)` is written. Any other exhaustion behaves as today.
- **`vet.vet`** takes the found articles as an argument, so the check stays pure. They are fetched once
  in `compose.compose` before the walk: `lookup.articles_for(settings.dictionaries_path, language,
  keys_for(headword, lemma))` for the resolution's word. The dictionary checks run after the script
  checks pass, and raise `Demoted` naming the dictionary: "kaikki-es-en reads asco as /ˈasko/; the
  model wrote /ˈaska/", "cc-cedict reads 麻烦 as ma2 fan5; the model wrote máfán". A Mandarin `ipa` is
  derived from the reading, so it is not checked; its reading is.
- **`admin calls`** totals `kept=` beside `fixed=` and `dropped=`.

## 2 · A setting: "Check what models write"

Models improve fast, and a check that helps today may only cost a call tomorrow. A check can also
misfire for one language or one broken dictionary. So one switch per owner turns compose's checks off,
and having it in Settings also tells the owner that checks happen at all.

- **What it covers.** On: as today plus §1. Off: `vet` runs only `draft.refusal_of` (not an object, no
  senses, a Chinese entry with no reading). Those conditions mean no draft can be built at all, so
  they are not a judgement and stay. Everything else is skipped: the script checks, the coercions and
  drops, and the dictionary checks. Deriving Mandarin `ipa` from the reading is not a check and
  stays. Default: on.
- **Where it is stored.** It is a per-owner preference of the model chain, so it goes in
  `model_selection`, the server-only row that holds the chains, as a new column `check_answers`
  (Boolean, default true). That is a schema change, so it needs a throwaway converter
  (`scripts/throwaway/`, `FROM_REVISION`, `main(argv)` with `--database` and `--dry-run`, tests), run
  by `./deploy.sh --transition` (`AGENTS.md`, "Backward compatibility").
  - The converter adds the column with `true` for every existing row; an owner with no row reads as
    on.
  - `GET /models` carries `checkAnswers`, and `PUT /models/selection` accepts it beside `chains`.
- **Where it is shown.** Settings ▸ Models, in its own `Group`, as a `Toggle` from `settings/kit.tsx`
  read through `settings/cache.ts`. The label is "Check what models write", with a one-line hint on
  what it does for you: "Passes a word to the next model when its glosses are in the wrong language,
  or its reading, IPA or gender disagree with an installed dictionary." Change the prototype
  (`design/ui-prototype/`) with it, and screenshot it at 834×1112.
- **Observable.** When off, compose's outcome line says `checks=off`, so `admin calls` can tell an
  unchecked answer from one that passed.

## 3 · Tests, docs and handover

- Tests (`tests/unit/server/test_compose_checks.py`, `test_observability.py`, the converter's own):
  - the head pair demoted by a dictionary and the next pair agreeing;
  - every pair demoted, so the first answer is kept and `kept=` is logged;
  - no dictionary installed, so there is no check;
  - checks off, so a wrong-script answer passes and a no-senses answer is still refused;
  - `admin log --failed` shows a demotion's sentence.
- Docs:
  - [`capture.md`](../../features/capture.md), "Compose's checks": the dictionary rows with their
    dispositions and a link to the measurement, the soft demotion and the setting;
  - [`models.md`](../../architecture/models.md): `Demoted`;
  - [`article-quality.md`](article-quality.md): defects 1 and 2 get one line each saying which check
    now catches them, backlog row 2 records the result, and the §3 IPA/gender paragraphs say it is
    built.
  - Then delete this file and its line in [`../README.md`](../README.md).
- Hand over:
  - the exact `./deploy.sh --transition` run;
  - the dictionaries to rebuild on the server: every `kaikki-*` row the owner has installed (only
    `kaikki-es-en`, `kaikki-es-es`, `kaikki-en-en` and `kaikki-en-ru` were rebuilt on the laptop
    with the new fields);
  - the suggested commit message.
