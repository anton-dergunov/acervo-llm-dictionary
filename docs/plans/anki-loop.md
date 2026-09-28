# The Anki loop · closing it in both directions

**Status:** half built. Cards go out by themselves, a minute after the vocabulary changes, and review
state comes back per sense every hour, with every review kept as history
([`../features/anki.md`](../features/anki.md)). What is missing is acting on what comes back. Without that, Acervo cannot say whether
anything it does helps a word stick — the thing every competitor sells
([`../research/similar-projects.md`](../research/similar-projects.md), "The learning loop is not
closed").

## 1 · Cards out: built

Decided and built; the design is [`../features/anki.md`](../features/anki.md), "The cards".

- **Both levels, split by skill.** Meaning is tested per sense — a Recognise card per example and a
  Produce card per sense — and sound per word, with a Listen card. So the study-state join is per
  sense, with the word's own row beside it.
- **Sentences by trust**: the owner's own, then generated, then dictionaries', clips last.
- **One deck per language, topics as tags**; pictures at 768 px.
- **Still to check on the tablet**: WebP pictures and `<audio>` playback on AnkiMobile, and whether
  it lets the Listen card play by itself.
- Keep `.apkg` export for bootstrapping and disaster recovery: it is the only export that works when
  nothing else does. Not built.

## 2 · Statistics in: acting on FSRS

`studyStates` already arrive. What they should change:

| Signal | Source | Effect on the word |
|---|---|---|
| **Learned** | stability above a year | `status → learned`, out of active rotation |
| **Struggling** | high difficulty or many lapses | **gates expensive treatment** — extra pictures, clips, stories |
| **"I know this"** | a green flag, or a suspension | `status → learned`, overriding FSRS |
| **"This card is wrong"** | a red flag | back to `inbox` for regeneration |
| **Never scheduled** | no card | drift between the vocabulary and the deck |

Flags and suspension would need the robot to report them — today they are exported and deliberately
not stored. FSRS difficulty is the free answer to "which words deserve the expensive treatment",
with no marking discipline required.

## Open

- **Where the daily review happens.** Anki is a better scheduler; Acervo is a better place for LLM
  grading and clip playback. Likely both — but which one owns the daily session should be decided
  before building either side further. See also [`learning-modes.md`](learning-modes.md).
- **What the history should show, and where.** The review history is kept and `GET /stats` reads it
  ([`../features/anki.md`](../features/anki.md), "The review history"); nothing in the interface shows
  it yet. The view to design is statistics and, above all, the before and after of a word that went
  into a loop, a story or a new picture. With the history in hand, retrievability can also be
  computed when shown — from stability and days since the last review — rather than read once at pull
  time and left to go stale.
