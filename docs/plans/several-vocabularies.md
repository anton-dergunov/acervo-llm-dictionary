# Several vocabularies per language

**Status:** the model is built — a word, a loop and a story name their vocabulary by id, and
everything per vocabulary follows the switcher ([`../architecture/data-model.md`](../architecture/data-model.md),
"Vocabulary: a set of words, not a language"). What is left is letting an account keep two of one
language, and moving the starters into the owner's own account.

## Why

Importing a Spanish starter into an account that already studies Spanish today merges 500 words into
the owner's own Spanish. The interim way to try the starters is two extra accounts
(`scripts/starter/test_accounts.sh`): `starters@…` for nineteen of them and `starters-es@…` for Spanish
(Spain), because Spanish (Mexico) is already in the first. Each account needs its own browser profile,
since signing out clears a device's copy of the words. That is too awkward to use.

The same change serves other people: someone learning two varieties of one language, kept apart; a
class's word set kept apart from one's own words; a starter tried first and adopted later.

**There is no special kind of vocabulary.** A starter is an ordinary vocabulary told apart only by its
name — `Spanish (Mexico) · Everyday words` — with no field, no line in the switcher, and nothing
excluded from Anki, stats, the map, loops or stories: other people will *use* the starters, not test
them.

## Several of a language

No schema change.

- **Drop the one-per-language rule** (`checkVocabularyLanguages` in `web/src/domain.ts`). Settings
  "Add a vocabulary…" offers a language already kept; the form refuses a name another vocabulary
  already shows — an interface check only, since a replicated collection carries no uniqueness rule.
- **Which vocabulary a word goes in.** One client rule picks the vocabulary in view when it is in the
  word's language, else the only one of that language, else asks — a "Which vocabulary?" sheet — for
  typed add, look-up Add, dictionary Add and photo capture. Server capture already answers
  `409 vocabulary_ambiguous` with the candidates ([`../features/capture.md`](../features/capture.md));
  the sheet asks and resends with `vocabulary`. A queued capture job that meets the same question fails
  with a sentence naming the vocabularies, visible in `admin log --failed`.
- **Import asks, per vocabulary in the bundle**: *Import as a new vocabulary* (named as in the bundle;
  a clash with a name already kept must be renamed first) or *Add to <the owner's vocabulary of that
  language>* (the bundle's name is dropped; words already held are skipped). The report says "new
  vocabularies" and groups skipped words by vocabulary name. `web/scripts/install-bundle.ts` imports
  as a new vocabulary, with `--name` to rename and `--into <name>` to add to one.
- Designed in `design/ui-prototype/` (the switcher with two Spanish vocabularies, the import
  confirmation, the "Which vocabulary?" sheet).

## Starters into the owner's account

- The starter builder names each `<Language (Variety)> · Everyday words`; the 20 bundles and
  `vocabularies/README.md` are rebuilt (with no model calls).
- The testing accounts retire: `scripts/starter/test_accounts.sh` and the installer's `--testing` go,
  and the deployment guide's section on them becomes installing the starters into one's own account.
