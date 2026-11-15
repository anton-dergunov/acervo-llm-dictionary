# Compose checks inside the chain

**Status:** ready to build. These are engineering fixes from
[`article-quality.md`](article-quality.md) §2 that need no experiment. Each check has a right
answer, so building one needs no measurement first. One Claude Code session.

## Why

A check that fails **inside** the chain's callback demotes the model that failed it, and the next
pair in the chain answers. `clips/select.py` and `images/brief.py` already work this way
(`ProviderUnavailable("unusable", …)`, see `models/errors.py`). Compose does not. It goes through
`services/models.llm_json` (`src/acervo/services/models.py:211`), which rejects a reply only when it
is not JSON. Compose's own refusals are raised as `ApiError` after the chain has finished
(`services/capture/compose.py:104`, the "not an entry" refusal; `services/capture/draft.py:196–209`,
"no meanings" and "a Chinese entry with no reading"). So they are terminal: one bad answer from the
first model refuses the capture, while a stronger model behind it is never asked.

## What to build

1. **`llm_json` takes an optional check.** A callable on the parsed reply, run inside `ask` (models.py,
   the nested `ask` at about line 240) after the JSON check. A `ValueError` it raises becomes
   `ProviderUnavailable("unusable", <its sentence>, provider_id=…, model=…)`, exactly as
   `clips/select.py` does it. `docs/architecture/models.md` describes the hook.
2. **Compose passes a check that applies the refusals the save would apply.** These are: not an
   object, no senses, a Chinese entry with no reading. Prefer calling the same code the draft uses
   over restating the conditions, so the check and the refusal cannot drift. A refusal that still
   happens after the chain, because every pair failed, keeps its current sentence.
3. **The rule checks**, each with the disposition from `article-quality.md` §2, "The four
   dispositions":

| Check | Disposition | Note |
| --- | --- | --- |
| Gloss language by script against `glossLangs[0]` | demote | Only where the two languages use different scripts (Cyrillic, Han, Latin…); a pair with the same script gets no check. Measured: `llama-3.3-70b` glossed in English 28% of the time for Russian-first vocabularies. A working `script_of` is in `experiments/compose-lesson-line/score.py:52`. |
| Notes language by script against `notesLang` | demote | Same rule. |
| `primaryGloss` is one term (no `;`, `,` or `/`) | coerce to the first term | Held in 158 of 158 replies, so this is a guard. |
| `emoji` is one grapheme cluster | coerce to the first cluster | Grapheme segmentation needs a library (`regex`'s `\X`, or `grapheme`); add one and say so. |
| `domain` is one or two lower-case words, distinct between the senses of one word | lower-case; drop the field if longer or repeated | Drop the field, keep the record. |
| `emotion` is 3–12 words, has no emoji, and does not repeat one of the article's example emotions | drop the field | Same. |

A coerced or dropped field is **counted** in the model-call log's line for that call (`noted`, never
the owner's message). That way `admin calls` can answer "how often does each model need fixing, and
where".

## Constraints

- These checks live in the chain callback, not in `domain/validation.py`. They judge a model's
  answer, not a record, so nothing changes in `web/src/domain.ts`, and a hand-typed article is never
  refused by them.
- **Observability rule:** a demotion must show in `admin log` / `admin calls` with its sentence ("the
  glosses are in Latin script, and the vocabulary glosses into Russian first"). Cause one and look.
- Tests: one per check (passes, coerces, demotes), and one chain test where the first pair fails the
  check and the second pair's answer is the one saved.

## When it is built

- Backlog row 3 of `article-quality.md` (does in-chain routing work on real traffic) becomes free to
  read from `admin calls`. Tell the owner; do not edit `article-quality.md` without asking.
- The starter vocabularies run these checks over every composed word
  ([`../first-use/starter-vocabularies.md`](../first-use/starter-vocabularies.md), step 5).
- [`dictionary-checks.md`](dictionary-checks.md) builds on the hook.
