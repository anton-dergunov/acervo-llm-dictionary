# Loops and stories · what is still to do

**Status:** open. The designs as built are [`../features/loops.md`](../features/loops.md) and
[`../features/stories.md`](../features/stories.md). Two pieces, each usable alone. A finished render
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
