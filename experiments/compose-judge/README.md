# Compose judge

**Two jobs, one pass of Gemini 4 Argon over every starter article:**

1. **A failure inventory** for the next round of compose prompt work: which serious faults the
   composer (Flash-Lite) makes, how often, in which languages, the kinds nobody anticipated included.
   Only the worst kinds will be fixed, because the prompt cannot grow without limit for a small model.
2. **Corrected starter articles.** Each article comes back corrected and, where it passes compose's
   checks, replaces the starter draft, so users download the better one. What the corrector changed is
   itself a record of what the composer gets wrong.

**Why a judge.** `experiments/compose-audit/` took everything a rule can decide and made it compose's
checks; what is left needs reading, over 10,177 articles in twenty languages. Argon is half price in
batch until 30 Nov 2026. It is a Gemini model, the same family as the composer
(`docs/plans/quality/article-quality.md` §5, self-preference): what it lists is read as leads to
check, not as a verdict on compose.

## The instrument (rubric v2)

- `rubric.md`: the system instruction. It says what a good entry is: short, a phone screen and not a
  dictionary page. It lists **only serious faults**: severity 3 (a learner would learn something
  false, or misses an everyday meaning) or 2 (clearly worth fixing). Each fault has a category from a
  **closed set**, or **`new:<name>`** with what it is. The closed set makes faults countable, and the
  open name is how unseen kinds surface, as clusters of their own instead of free text.
  Polish is never listed; it is only fixed. Then it returns the **corrected entry** in compose's
  answer shape, with `was` naming each sense's original. It returns `null` when nothing needs
  changing, which costs nothing, and the corrected entry may be at most 1.5 times as long.
- `judge.py`: renders each article compactly with every field it judges. Under each article it adds a
  **dictionary hint**: up to 12 senses from the best installed dictionary, Wiktionary's English
  extracts first, fenced off as not part of the entry and never shown to the learner. It is there
  for spotting a missing everyday sense, the thing the owner cares about most. Five articles of one
  vocabulary go in a request, so the rubric is paid for once per five. It runs online (pilot) or as
  Vertex batch rounds, which resume after an interruption and ask again for any article an answer
  left out.
- Dictionaries: the served set, plus `data/dictionaries/judge/`. The latter holds the kaikki extracts
  for the ten languages the served set lacks (tr, pl, el, nl, ko, th, ar, hi, vi, id), compiled for
  the judge only, because compose's dictionary checks have unmeasured false alarms there. Arabic is
  looked up without its vowel marks, as Wiktionary files it (`docs/plans/issues.md`).
- `gcp.py`: every call runs on the account pinned in the gitignored `.env` (`.env.example`), or
  nothing is sent. The ADC file's account and quota project, the gcloud configuration and the shell
  must all agree, and batch files live only in that project's bucket. `judge.py check` prints it.
- `spend.jsonl`: every call's tokens and cost. `--max-usd` (default **$100**) caps all runs together
  and is checked against an estimate before anything is sent.
- `apply.py`: puts each correction into the starter drafts, completing it with what the judge does
  not write (emoji, emotions, topics). It runs it through compose's own check and enforces the
  growth limit; a correction that fails either keeps the original, and the reason is listed. A sense
  keeps its id when `was` names it, so picture matches stand, and the topic's match file takes the
  new definitions. The compose file keeps `draftBefore` and the run's faults.
- `report.py`: the inventory. Kinds by severity-weighted count, per vocabulary and per composing
  model, quoted examples, the `new:` kinds, and the article keys behind every number.

## Pilot 1 (rubric v1, 21 Nov 2026): what changed the design

Rubric v1 listed every fault, of any severity, with no corrected entry. Four online arms over 72
articles (20 each of es-ES, en-US, ru, plus 12 defects read by hand), $1.80:

| arm | thinking | known defects named (of 12) | faults | major |
| --- | --- | ---: | ---: | ---: |
| `pilot-low` | low | 8 | 114 | 27 |
| `pilot-med` | medium | 10 | 124 | 30 |
| `pilot-high` | high (~3,300 tokens a request) | 10 | 112 | 43 |
| `pilot-one` | low, 1 article a request | 9 | 131 | 36 |

- **Argon does not think at low or medium.** Neither reports a thinking token, and a probe at high
  thought 249 tokens on a one-line question. So `pilot-med` is a second run of `pilot-low`'s setting,
  and the spread between them is the judge's own noise. High thinking named no more of the known
  defects, at 3.6 times the price; it marked more faults major.
- **About a third of the faults come and go between runs**: of 166 merged faults, 59 were raised by
  all four arms and 56 by one.
- **The owner's verdicts** (14 marked, `runs/review/labels.json`): 9 agree, 4 unsure, 1 wrong. The
  wrong one judged *cough*'s example against the dictionary's sense numbers, as though the reference
  were part of the entry; hence the hint's fencing in v2. The agreed ones include an adjective defined
  as a noun ("Un lugar donde…"), now `definition.form`, and a calqued translation ("llamar su
  nombre").
- **Why the owner's labelling stopped:** agree / wrong does not fit the question that matters, which
  is whether a fault is serious enough to spend prompt space on, and marking 166 faults was too slow.
  The inventory is read by the analysis session instead, ranked by severity. Not faults: a place name
  in an example (the owner is fine with them); a pronunciation note, wanted only where the spelling
  misleads.

## Pilot 2 (rubric v2)

`v2-pilot` on the same 72 articles, medium thinking, $0.39 online (so about $30 for the corpus in
batch). 64 of 72 came back corrected; 117 faults listed, 24 of them severity 3 (`note.filler` 39,
`shortgloss.mismatch` 12, `example.unnatural` 9, `note.false` 9, `sense.missing` 8, `note.missing` 8).
8 of the 12 hand-read defects named. `apply.py --dry-run` took 63 corrections, median 0.95 times the
original's length, and kept one original that grew 1.57 times.

Read by the session, in languages it can check: the corrections are the kind wanted. *dar* gains
"dar una fiesta" and "dar miedo" and the note on *doy*/*di*; *box* drops the theatre box for the
checkbox; *busy* defines the adjective as a quality and notes the *u*; *брать*'s examples, which used
*взять*, now use *брать*, and the *бер-* stem is noted; *la mañana*'s oversplit sense is merged.
Submitted for the whole corpus on 21 Nov 2026.

**A defect this pilot caught in the apparatus:** a word key repeats between vocabularies (547 keys,
such as `dar-verb-…` in Spanish and Portuguese), and results were filed under the key alone. Every
result is now filed as `<vocabulary>/<key>` (`judge.ident`).

## Full run (batch)

```
cd experiments/compose-judge
../../.venv/bin/python judge.py sample --name all
../../.venv/bin/python judge.py batch --run full --sample all --thinking medium --submit-only
../../.venv/bin/python judge.py batch --run full --sample all --thinking medium   # wait, collect, ask again
../../.venv/bin/python judge.py export --run full && ../../.venv/bin/python report.py --run full
../../.venv/bin/python apply.py --run full --dry-run      # then without --dry-run
```

## Files

- `runs/<run>/`: `manifest.json` (settings and rubric digest), `results.json` (per article, faults
  and corrected entry; rubric v1 runs have `faults.json`), `replies.jsonl` (raw answers with usage),
  `faults.jsonl`, `report.md`, `report.json`, `applied.json`. A batch run also has `r<n>/` per round,
  whose state, input and downloads are gitignored because they name the project.
- `runs/samples/`: the samples, as (vocabulary, key) lists. `runs/review/`: pilot 1's page items
  and the owner's labels.
