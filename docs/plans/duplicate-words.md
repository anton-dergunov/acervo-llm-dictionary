# Duplicate words · 227 English words held twice

**Status:** open. Found 17 Nov 2026 by `experiments/dictionary-checks/`, which reads every stored word.

## What is there

The English vocabulary holds **227 words twice**: 454 live lexemes in pairs with the same headword,
lemma, part of speech, IPA, topics and model. No Spanish or Chinese word is duplicated. Each copy is
a whole word of its own, with its own senses, examples and study state. For example, `burgeon` has
two senses and two study states in each copy.

| headword | copy | created (UTC) | senses | examples | study states |
| --- | --- | --- | ---: | ---: | ---: |
| burgeon | `m07zby8sq7olt5k` | 2026-09-19 08:57:12.3 | 2 | 2 | 2 |
| burgeon | `xs95x202z2c1tm9` | 2026-09-19 08:57:13.4 | 2 | 2 | 2 |
| burgeoning | `o2vzctanlge3p64` | 2026-09-19 08:57:13.8 | 1 | 1 | 1 |
| burgeoning | `a4y4zndp0vez04b` | 2026-09-19 08:57:15.0 | 1 | 1 | 1 |
| bystander | `2z000a02bgxrnm9` | 2026-09-19 08:57:14.6 | 1 | 1 | 1 |
| bystander | `7ecfoawgi5inpg6` | 2026-09-19 08:57:15.9 | 1 | 1 | 1 |

**All 454 were created on 19 Sep 2026 between 08:57 and 09:01 UTC, and each pair about a second
apart.** That is the day bundle import learned to file words into their topics (commit `5c9c49a`).

## Likely cause

Two imports of the same bundle running at once. `importBundle` (`web/src/transfer.ts`) skips a word
the vocabulary already holds, but it decides that from a snapshot taken when the run starts. Two
runs started a second apart each saw an empty English vocabulary, and each added every word. The
interleaved times fit two runs walking the same list side by side.

To confirm before fixing:
- Can a second import start while one runs: a second press, a second tab, or a second device?
  Check `settings/TransferPanel.tsx`: the import button is disabled only when the plan is empty.
- If it still can, the fix belongs in the client, because replicated collections carry no
  uniqueness constraint (`data-model.md`). Two possible fixes:
  - refuse a second run on the device while one is in flight;
  - check each word against the live replica just before saving it, rather than the start-of-run
    snapshot, which also covers two devices once the first device's words have been pulled.

## Cleaning up

One change, run once, by a laptop tool in the style of
`experiments/primary-gloss-emotion-tuning/backfill_apply.py`. It writes through the graph route as
the owner, with a dry run first. It is not a schema change, so there is no `--transition`.

1. **Choose the copy to keep** in each pair. Keep the one with more history: reviews and study-state
   repetitions, Anki review history (the Anki note follows the lexeme id), plays, pictures, recordings,
   clips, and the loops (`loop_items`) and stories (`story_words`) that name it. Where both copies
   carry history, list the pair for the owner instead of choosing.
2. **Tombstone the other copy** with its dependent records (senses, examples, attestations, image
   prompts, pronunciations, study states), as the client's own delete does, in one change set per
   word. Nothing is collected, so a wrong choice can be undone.
3. **Anki:** the next push deletes the dropped copy's note, so do it after step 1 has kept every note
   with reviews.
4. Dry-run output first: pairs, the copy kept and why, record counts. The owner reads it and then
   applies it.
5. Afterwards, re-run `experiments/dictionary-checks/extract_remote.py` and confirm no headword appears
   twice in one language.

Delete this file once the cause is fixed and the store is clean.
