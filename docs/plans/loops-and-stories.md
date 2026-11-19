# Loops and stories · what is still to do

**Status:** open, undecided. The designs as built are [`../features/loops.md`](../features/loops.md) and
[`../features/stories.md`](../features/stories.md).

## A level for loops

A vocabulary has a level, and compose, chat and a story's text read it
([`../features/standing-rules.md`](../features/standing-rules.md), "The reader"). A loop does not: the
lines a loop speaks beyond the word and its gloss are written by LexiBeat, whose prompt reaches the
owner's text chain through `POST /loops/write` (`services/loops.write`) untouched — neither the reader
nor the standing rules are added there.

- **What it would change.** Only the formats that speak written lines: a radio lesson, a story, and
  any format's examples, remarks or intro. `classic`, `alternating`, `echo` and `review` speak the
  headword and its `primaryGloss` only, so a level changes nothing in them.
- **Two ways to do it.** Send the level in `render_request` and have LexiBeat's prompt use it (a
  LexiBeat release and re-pin), or join the reader and standing rules onto the prompt in
  `services/loops.write`, as every other writer does, which needs that route to know the loop's
  vocabulary. The second keeps LexiBeat ignorant of the reader and brings the standing rules along.
