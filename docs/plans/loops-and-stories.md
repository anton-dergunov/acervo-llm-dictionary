# Loops and stories · what is still to do

**Status:** open. The designs as built are [`../features/loops.md`](../features/loops.md) and
[`../features/stories.md`](../features/stories.md). Four pieces, each usable alone. A finished render
stays silent on purpose: the loop or story is in its list when the owner goes back to it.

## 1 · Drawing the favourites

One more order for the make dialogs' draw ([`../features/loops.md`](../features/loops.md) §2.12):
**Favourites**, the starred words first, once words can be starred (§2).

## 2 · Favourites and order

- **A star on words, loops and stories**, with a filter to starred and a "starred first" order. It is
  an owner's mark on a record, so it replicates.
- **Reordering loops and stories** by hand. Both records already carry a `position`; nothing in the
  interface sets it yet.
- **Groups**, only if the lists get long enough that stars and order do not keep them usable.

## 3 · Level and length

- **A level for loops.** A vocabulary has a level now, and compose, chat and a story's text read it
  ([`../features/standing-rules.md`](../features/standing-rules.md), "The reader"). A loop's sentences
  are written by LexiBeat, so following it there means sending it in `render_request` and a change on
  that side.
- **A level for one story**, overriding the language's, in the story dialog.
- **How many parts**, in the same dialog. The writer is free today, and the server accepts three to
  eight.

## 4 · Listening hands-free

The use is walking with the phone in a pocket: tap once, and loops and stories play.

- **Play a whole story.** Today a part plays its passages in order and stops; leaving the page stops
  it too. A story should play part after part, with the text following along when the screen is
  on.
- **A queue across loops and stories**, with next and previous, as loops already have.
- **One player per device shape**, designed rather than inherited: the phone first, then the
  tablet. On the desktop the now-playing chip leaves the top bar; where it goes instead is part of
  this design.
