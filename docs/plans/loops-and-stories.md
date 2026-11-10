# Loops and stories · what is still to do

**Status:** open. The designs as built are [`../features/loops.md`](../features/loops.md) and
[`../features/stories.md`](../features/stories.md). Three pieces, each usable alone. A finished render
stays silent on purpose: the loop or story is in its list when the owner goes back to it.

## 1 · Drawing the favourites

One more order for the make dialogs' draw ([`../features/loops.md`](../features/loops.md) §2.12):
**Favourites**, the starred words first. It needs a star on words, which loops and stories have
([`../features/loops.md`](../features/loops.md) §2.20) and words do not yet: an owner's mark on the
lexeme, so a schema change of its own.

## 2 · Level

- **A level for loops.** A vocabulary has a level now, and compose, chat and a story's text read it
  ([`../features/standing-rules.md`](../features/standing-rules.md), "The reader"). A loop's sentences
  are written by LexiBeat, so following it there means sending it in `render_request` and a change on
  that side.
- **A level for one story**, overriding the language's, in the story dialog.

## 3 · Listening hands-free

The use is walking with the phone in a pocket: tap once, and loops and stories play. Drawn in the
prototype:

- **A story plays part after part**, the deck following the voice when the screen is on, with a footer
  like the loop player's: a segment per part, previous and next part, read it again, go on to the next
  story. Pause is pause and leaving is no longer stop; a swipe moves the voice, a tap on a passage
  reads from it. This changes `stories.md`, "The reader".
- **The queue is the list it was started from**, in the order shown, archived skipped; lock-screen next
  and previous move through it, and stories get Media Session metadata (the part's picture as artwork)
  as loops have.
- **What is playing, per device shape**: the phone's bar, with Next and close, for a loop or a story;
  on a tablet or a desktop a card at the foot of the rail, and the top-bar chip only on a tablet whose
  rail an article has hidden. Each is hidden while the thing playing is open in its own player.
