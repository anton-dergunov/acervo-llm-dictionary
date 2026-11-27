# Several vocabularies per language

**Status:** built, apart from the starters. A word, a loop and a story name their vocabulary by id,
an account keeps any number of vocabularies of one language, and a word, a capture or an import that
could go in several asks which ([`../architecture/data-model.md`](../architecture/data-model.md),
"Vocabulary: a set of words, not a language"; [`../features/capture.md`](../features/capture.md),
"Which vocabulary"; [`../features/export.md`](../features/export.md), "Import"). What is left is the
add-a-vocabulary page, which still reads as if a vocabulary were its language and still carries the
owner's own languages as defaults, and moving the starters into the owner's own account.

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

## Adding a vocabulary

Settings ▸ Vocabularies ▸ *Add a vocabulary…* ▸ a language (`VocabularyForm`, `newDraft` and
`presented` in `web/src/settings/Configuration.tsx`). Designed in `design/ui-prototype/` first, like
the rest of this plan.

- **Say plainly which language it is.** Today the language shows only as the default text of *Name*
  and as the page title (`open({ title: language.name })`), so a second Spanish vocabulary named
  "Spanish Variety Mexico" no longer says anywhere that it is Spanish once renamed, and the title is
  the same word as the name above it. The page should name the language as a fixed fact, apart from
  the editable name: a read-only *Language* row (flag and name, "🇪🇸 Spanish · español") at the top of
  the first group, and a title that says what the page is ("New vocabulary"; a kept vocabulary's page
  keeps its name as title). The language cannot change once there are words, so it is shown, not
  offered. The same row on a kept vocabulary's page.
- **The header's two words do not line up.** The back link ("‹ Vocabularies") and the page title sit
  on different baselines (`.prefs-back` beside the title in `Settings.tsx`, the title in the display
  face at a larger size). Align them on one baseline, in `styles.css` and the prototype together; check
  with a screenshot, since jsdom does no layout.
- **A flag beside a language follows the vocabulary being edited.** *Senses defined in* shows 🇦🇷 on a
  new Spanish vocabulary whose variety is Mexico: `presented(code, kept)` takes the flag of the first
  *kept* vocabulary of that language — the owner's Argentine Spanish — not of the draft. Where the code
  is the draft's own language, use the draft's flag (its own, else its variety's); for any other
  language, the language's main region, as now. Nothing is hard-coded to Argentina: it is the owner's
  data leaking into another vocabulary's page.
- **English by default, never the owner's languages.** A new vocabulary is *Translated into* and has
  *Notes written in* English (for an English vocabulary, the browser's language when it is not
  English, else Spanish), not what the owner's other vocabularies translate into most (`newDraft`'s
  `preferred`, which is how English and Russian arrived here). The owner chooses others on the page.
  Russian is also a default in three other places, each to become English (and an English
  vocabulary's, Spanish):
  - `GLOSS_DEFAULTS` in `web/src/languages.ts` (`en: ["ru"]`, `zh-Hans`/`zh-Hant: ["ru", "en"]`), which
    gives the translation languages for a word in no vocabulary and for an imported bundle that lists
    none (`readBundle`, via `glossLanguagesFor`).
  - `STARTER_VOCABULARIES` in `src/acervo/seed_data.py`, the seeded demonstration account (`admin
    seed`): English and Chinese translated into Russian, notes in Russian.
  - The prototype's fixture (`design/ui-prototype/data.js`), whose English and Chinese vocabularies say
    `glossLangs: ["ru"]` — fixture data rather than a default, so it changes only if the pages it
    draws are meant to show the defaults.

  Russian glosses in example words (seed data, tests, the chat prompt's examples) are content, not
  defaults, and stay.

## Starters into the owner's account

- The starter builder names each `<Language (Variety)> · Everyday words`; the 20 bundles and
  `vocabularies/README.md` are rebuilt (with no model calls).
- The testing accounts retire: `scripts/starter/test_accounts.sh` and the installer's `--testing` go,
  and the deployment guide's section on them becomes installing the starters into one's own account.
