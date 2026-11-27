# Several vocabularies per language

**Status:** built, apart from the starters. A word, a loop and a story name their vocabulary by id,
an account keeps any number of vocabularies of one language, and a word, a capture or an import that
could go in several asks which ([`../architecture/data-model.md`](../architecture/data-model.md),
"Vocabulary: a set of words, not a language"; [`../features/capture.md`](../features/capture.md),
"Which vocabulary"; [`../features/export.md`](../features/export.md), "Import"). What is left is moving
the starters into the owner's own account.

## Why

The starters are tried in two extra accounts (`scripts/starter/test_accounts.sh`): `starters@…` for
nineteen of them and `starters-es@…` for Spanish (Spain), because Spanish (Mexico) is already in the
first. Each account needs its own browser profile, since signing out clears a device's copy of the
words. That is too awkward to use, and no longer needed: a starter now imports as its own vocabulary
beside the owner's words of that language.

The same change serves other people: someone learning two varieties of one language, kept apart; a
class's word set kept apart from one's own words; a starter tried first and adopted later.

**There is no special kind of vocabulary.** A starter is an ordinary vocabulary told apart only by its
name — `Spanish (Mexico) · Everyday words` — with no field, no line in the switcher, and nothing
excluded from Anki, stats, the map, loops or stories: other people will *use* the starters, not test
them.

## Starters into the owner's account

- The starter builder names each `<Language (Variety)> · Everyday words`; the 20 bundles and
  `vocabularies/README.md` are rebuilt (with no model calls).
- The testing accounts retire: `scripts/starter/test_accounts.sh` and the installer's `--testing` go,
  and the deployment guide's section on them becomes installing the starters into one's own account.
