# Several vocabularies per language

**Status:** wanted, not designed in detail. Raised by the owner on 25 Nov 2026, to be taken up in a
session of its own.

## Why

Today an account holds one vocabulary per language. A word names its vocabulary only through its
language code, so importing a Spanish starter into an account that already studies Spanish merges 500
words into the owner's own Spanish. The interim way to try the starters is two extra accounts
(`scripts/starter/test_accounts.sh`): `starters@…` for nineteen of them and `starters-es@…` for Spanish
(Spain), because Spanish (Mexico) is already in the first. Each account needs its own browser profile,
since signing out clears a device's copy of the words. That is too awkward to use.

What is wanted instead: the starters in the owner's own account, beside their own vocabularies, set
apart **below a line** as vocabularies kept for testing. The same change serves other people too:
- someone learning two varieties of one language, kept apart;
- a class's word set kept apart from one's own words;
- a starter tried first and adopted later.

## The model change

A vocabulary becomes a thing in its own right: a word names its vocabulary by id (`vocabularyId`),
and a language code is used only where the language itself is meant. Today the language does two
jobs, and this session's survey separated them.

**Uses of the language as the vocabulary's identity**, which move to the vocabulary id:
- **The word → vocabulary join.** Client: `glossLanguagesFor` / `notesLanguageFor` /
  `definitionLanguageFor` (`web/src/languages.ts:81-94`). Server: `src/acervo/article.py:83`,
  `services/reader.py:95-97`, and the twelve callers of `repository/graph.py` `owner_vocabularies()`.
- **The vocabulary switcher and `languageOptions`** (`web/src/App.tsx:1629-1640`,
  `web/src/selectors.ts:141`), and the `language` state passed through the views (MadeBar, MapView,
  StoryView, LoopView, the dialogs).
- **Remembered place and selection** (`web/src/lastPlace.ts`, `web/src/wordSelection.ts`, one of each
  per language in localStorage).
- **Import and export.** Import matches a vocabulary by language (`web/src/transfer.ts:826-849`), its
  duplicate key is `(language, headword)` (`transfer.ts:780`, `repository/graph.py:488-526`), and word
  files and pictures sit under `<language>/`.
- **The meaning map** (`GET /map/{language}`, `services/meaning.py:72`, `web/src/mapStore.ts:21`, the
  `map.name` job's subject).
- **Stats** (`api/routes/reviews.py:47-61`, `repository/reviews.py:83-89`).
- **Anki decks** (`consumers/anki/build.py:46`, `:199-229`).
- **The Obsidian mirror's names** (`web/src/markdown.ts:48`).
- **Loop and story lists and positions** (`repository/graph.py:748-798`; the loop and story dialogs).
- **Capture's vocabulary pick** (`services/capture/pipeline.py:108-126`): it detects the language,
  then takes the vocabulary of that language.
- **`checkVocabularyLanguages`** (`web/src/domain.ts:1005-1015`), the only rule enforcing one
  vocabulary per language. The server has none.

**Uses that need the language itself**, which stay:
- voices and locale (`services/pronunciations.py`, which also reads the vocabulary's region);
- dictionaries;
- IPA, pinyin and the reading a Chinese word must have;
- rarity;
- the article stripped before a headword (Anki);
- script hints for reading a photo;
- the language capture detects.

## Interface

- **The switcher** lists vocabularies, not languages. A vocabulary set apart (how it is marked is
  decided here: a field on the vocabulary, or its place in the list) sits below a line.
- **Capture and look-up** add a word to the vocabulary in view. When the language detected has
  several vocabularies and the one in view is not among them, they ask which one.
- **Import** asks, in its confirmation, whether a bundle's vocabulary goes into a new vocabulary (the
  default when it differs in variety or support language, and for a starter) or joins an existing one.
- Designed in `design/ui-prototype/` first, and screenshotted at the tablet's size.

## Data

- A schema change with a throwaway converter (`scripts/throwaway/`, run by `./deploy.sh --transition`):
  each word gets the id of the vocabulary of its language.
- A `LOCAL_SCHEMA_VERSION` bump, so every replica is wiped and pulled again.
- The bundle format: `vocabularies.yaml` and the word paths keyed by vocabulary. An `upgradeBundle`
  adaptation for older bundles only if it maps cleanly (one vocabulary per language does).

## What it retires

The testing accounts: `scripts/starter/test_accounts.sh` and the installer's `--testing`. The starters
are imported into the owner's account as vocabularies set apart.

## Open questions

- Does a word keep `language` at all, or read it from its vocabulary?
- One meaning map and one Anki deck per vocabulary, or per language?
- Are vocabularies set apart left out of Anki, stats, loops and stories by default?
- Is "set apart" one kind of vocabulary, or the general mechanism for archiving one?
