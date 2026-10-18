# Chat edits · why "replace this word everywhere" could not be done, and what fixed it

**Question.** Asked in the article chat to replace «абиссальный» with «бездонный» in an entry under
review, the production model (`gemini-3.5-flash-lite`) failed twice in a row: a card that could not be
applied, then no card at all. What exactly happened, why, and what change to the prompt — first — and
to the code makes an edit like this right on the first attempt?

**Answer.** End to end, first attempt, 46 cases × 3 repeats on the production model:
**72% → 94%** (99 → 130 of 138; paired exact McNemar p < 0.0001), **96%** once the device's repair
has run (two repair calls in 138 turns). On the held-out half, which no prompt round saw:
**70% → 90%** (44 → 57 of 63, p = 0.0002). Replacements went from **42% to 91%**. The owner's own
turns 3 and 4 went from **0 of 3 each to 3 of 3**. Every failure class the shipped code had —
refused by the device, dropped by the server, a request answered with no proposal — is gone. What
remains is six edits that apply but are not quite what was asked.

The decision and the design live in [`docs/features/article-chat.md`](../../docs/features/article-chat.md)
§5; this is the evidence.

## The case

The owner was adding *abyssal* (English, glossed into Russian). The four turns, verbatim:

| # | They said | The reply they saw |
| --- | --- | --- |
| 1 | абиссальный - is there such word in Russian? | Да, слово «абиссальный» есть… |
| 2 | so better replace with бездонный, because I guess it can be replaced in this vocabulary item? for example as well. | …их можно добавить как основные глоссы… Но полностью заменять «абиссальный» не обязательно… |
| 3 | It is better if we just change абиссальный to бездонный everywhere in this article. Do this. | I have updated the headword, lemma, short and primary glosses, and all references… |
| 4 | Don’t rewrite, update. | I apologize… Let me update the glosses and translations… |

After turns 2 and 3 a card offered a change and *Review* failed; after turn 4 nothing was offered.
The production log held four lines of `chat … ok in 1.89s` and nothing about what was returned — the
original answers are lost. So the four requests were rebuilt exactly (the YAML tab and the thread,
copied from the window still open: [`documents/abyssal.yaml`](documents/abyssal.yaml),
`dataset.py` `REPLAY`) and replayed three times each against the same model
([`runs/replay/`](runs/replay/)). Turn 3, three times:

- set `headword` **and** `lemma` to «бездонный», gave it a Russian IPA and rewrote the note — and
  this one **applied**, because it touched a single record: it would have turned the English entry
  into a Russian one;
- almost exactly the right edit, plus an unasked rewrite of the note — **refused** as a rewrite;
- the right fields, but kept «абиссальный» in the glosses — **refused** as a rewrite.

Every reply began "I have updated…". Turn 4, the model having no way to know turn 3 was refused,
concluded the headword was the problem; one answer even included a `set` of sense 2's glosses to
exactly what they already were.

**And the right answer could not have been applied either.** «абиссальн…» sits in four fields of
three records — `shortGloss` and `primaryGloss` on the lexeme, sense 1's `glosses`, example 1's
`translation` and its `matchedTranslationForm`. The device refused any proposal reaching more than
half the entry's records, and this entry has five: three of five is a "rewrite", whatever is written
in them. That alone guaranteed both failures the owner saw.

## Root causes

1. **The prompt never said which field is in which language**, had no recipe for "replace this
   everywhere", never listed the allowed values (`register: "informal"` was refused), never said
   `shortGloss` is one string, and still named a retired operation language (`addSense`).
2. **The rewrite rule counted records reached, not words changed** — refusing a one-word swap across
   three records while passing a headword turned into another language.
3. **A refusal was invisible to the next turn**: the transcript carried reply text only.
4. **The document contradicted itself**: an entry under review was headed "No ids here" over four ids.
5. **Nothing was recorded**: a proposal the server could not read became `null` silently, a device
   refusal reached no log, and a `set` missing its `value` was read as null — erasing the field.

## Method

- **Apparatus.** `run.py` asks one pair directly (`gemini-free:gemini-3.5-flash-lite`, the one that
  answered in production), never through the chain, so a fall-through cannot attribute one model's
  answer to another. Each answer is shaped by the arm's own `services/chat.py` and applied by the
  arm's own `applyOps` — `checker.ts`, bundled from `web/src` — exactly as the Add view would. An arm
  is a prompt plus a code revision ([`arms/`](arms/)); `before` is loaded from git at `c46759f`, so
  later edits cannot leak into the baseline. `score.py` re-judges stored answers for free.
- **Cases.** [`dataset.py`](dataset.py): the four real turns plus 42 more over eight documents in two
  language pairs — replacements (8), rewordings (6), additions (8), removals (4), head fields (4),
  questions that must get no proposal (6), two multi-turn cases and four deliberately light
  adversarial ones ("remove everything", "translate the article into French", where declining and
  complying are both a pass and only breakage fails). Split dev / held-out; the prompt rounds saw
  only dev and the four real turns. Documents: the real abyssal YAML, four fixture words rendered
  through the shipped `yamlFor` ([`render_fixtures.ts`](render_fixtures.ts)), *el disfraz* from
  the live test, and two written in the same format with planted faults (a typo, a wrong
  translation, an example without one).
- **Scoring.** Per case, deterministic: was a proposal expected; did it survive the server; did it
  apply; and is the applied draft what was asked — for a replacement, the old word gone from every
  learner-language field, the new one where it belongs, nothing in the word's own language touched,
  no record outside the expected ones changed. **The headline is the first attempt.** Repairs are
  reported apart.
- **Spend.** 431 of the 450 calls allowed: 12 replay, 138 baseline, 141 over four prompt rounds,
  138 final, 2 repairs.

## Prompt rounds (dev and the real turns only)

| Round | Change | First attempt |
| --- | --- | --- |
| r1 | `intent` first; field-language table; exact types and allowed values; a recipe per request; never ask permission; offered-change markers | 24/25 |
| r2 | a replacement that does not say where means everywhere | 49/50 |
| r3 | the three places a translation is written; no `set` that repeats a value; the cap raised to 24 | 48/50 |
| r4 | the replacement as a walk through the document in a fixed order | 15/16 (replacement cases) |

Two of r2's misses were correct thirteen-operation answers over the old cap of twelve: one word in
seven records plus each example's emphasis mark. The cap now limits runaway answers; telling an
edit from a rewrite is the half rule's job. r4 is what shipped, as `prompts/acervo_chat.md`.

## Results

| | before (shipped) | after |
| --- | --- | --- |
| first attempt, all | 99/138 (72%) | **130/138 (94%)** |
| first attempt, held-out | 44/63 (70%) | **57/63 (90%)** |
| after repair | — | **132/138 (96%)**, 2 repair calls |
| replacements | 14/33 (42%) | 30/33 (91%) |
| additions · removals · head fields | 35/48 (73%) | 48/48 (100%) |
| questions answered without a proposal | 21/21 | 21/21 |
| light adversarial: nothing broken | 12/12 | 12/12 |
| failures | 14 refused, 14 no proposal, 11 wrong edit | 6 wrong edit, 2 refused (both repaired) |

Paired on (case, repeat): discordant 2 vs 33, exact p < 0.0001; held-out alone 0 vs 13, p = 0.0002.

**What is left**, all six an edit that applied but is not quite what was asked:

- *Turn 2* (2 of 3): "so better replace with бездонный… for example as well" — the new prompt reads it
  as the request it is and then replaces it in only some fields. The baseline "passed" this turn by
  proposing nothing at all.
- *"use бездонный instead of абиссальный"* (1 of 3): the example translation missed.
- *After a refusal, "Try again, smaller."* (3 of 3): the model does exactly that — a smaller change.
  The case's expectation, the full replacement, is arguable; it is reported as written.

None of these is visible to the device, so no repair can catch them; they are the prompt's residual.

**Found by the experiment and fixed outside the prompt**, each pinned by a test:

- the half rule counts a record as rewritten only when it was added, removed, or a prose field of it
  kept less than half its words — never a one-word field or an emphasis mark, never a no-op `set`;
- an entry under review is headed "Not saved yet. Every record keeps its id…";
- a `set` whose value sits under the field's own name is read from there; one with no value at all is
  a problem sentence, never a null — the shipped code would have erased a translation (two answers of
  three on one case wrote this shape);
- a proposal that changes nothing is refused, so the device sends it back — both such answers were
  then fixed by one repair.

## Reproducing

    set -a; . ./.env; set +a
    export PYTHONPATH=experiments/chat-edits
    .venv/bin/python experiments/chat-edits/run.py --arm after --split held --repeats 1 --dry-run
    .venv/bin/python experiments/chat-edits/run.py --arm after --split dev --split held --repeats 3 --repairs 2
    .venv/bin/python experiments/chat-edits/score.py runs/final --pair before after

`build/` is ignored. The worktree checker is bundled on every run. `build/checker-c46759f.mjs`, the
baseline's device code, has to be bundled from `c46759f`'s `web/src`: check that commit out with
`web/node_modules` installed, put this directory's `checker.ts` at `experiments/chat-edits/` in it
(the checker postdates the commit and imports `../../web/src/` relative to itself), and run
`npx rolldown ../experiments/chat-edits/checker.ts -o <here>/build/checker-c46759f.mjs -f esm -p node`
from its `web/`. Rescoring the stored baseline answers needs that file; nothing else does.
