# Loops and stories · what is still to do

**Status:** open. The designs as built are [`../features/loops.md`](../features/loops.md) and
[`../features/stories.md`](../features/stories.md). Four pieces, each usable alone. A finished render
stays silent on purpose: the loop or story is in its list when the owner goes back to it.

## 1 · Choosing the words

Today a loop or a story is made from the selection, or from a random draw of the words on screen
(`sampleLexemeIds` in `web/src/selectors.ts`). The make dialog should offer one choice of *how* to draw:

- **Random**, as now.
- **Not used yet** — words with no loop yet, for a loop; words in no story yet, for a story. Counted
  per kind: a word already in a story is still new to loops.
- **Hardest** — by the figure in [`anki.md`](anki.md) §2, the one the list's "Hardest" sort uses.
- **Newest.**
- **Favourites** (§2).

Each is a filter or an order over the words on screen, so topics and search still narrow it first.
Two may combine — hardest among the unused — but only if a single one proves too blunt.

## 2 · Favourites and order

- **A star on words, loops and stories**, with a filter to starred and a "starred first" order. It is
  an owner's mark on a record, so it replicates.
- **Reordering loops and stories** by hand. Both records already carry a `position`; nothing in the
  interface sets it yet.
- **Groups**, only if the lists get long enough that stars and order do not keep them usable.

## 3 · Level and length

- **A learner level per language**, on the `vocabularies` record, which every prompt that writes for
  the owner reads: stories, loops, and the examples compose writes. It is a schema change on both
  sides, so how it is deployed is decided when it is built. It touches the compose prompt, so it goes
  through the article-quality checks ([`quality/article-quality.md`](quality/article-quality.md))
  before it ships.
- **A level for one story**, overriding the language's, in the story dialog.
- **How many parts**, in the same dialog. The writer is free today, and the server accepts three to
  eight.
- **A level for a loop**, if the loop's sentences turn out to need one.

## 4 · Listening hands-free

The use is walking with the phone in a pocket: tap once, and loops and stories play.

- **Play a whole story.** Today a part plays its passages in order and stops; leaving the page stops
  it too. A story should play part after part, with the text following along when the screen is
  on.
- **A queue across loops and stories**, with next and previous, as loops already have.
- **One player per device shape**, designed rather than inherited: the phone first, then the
  tablet. On the desktop the now-playing chip leaves the top bar; where it goes instead is part of
  this design.
