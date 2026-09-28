# Word selection · a working pile of words to make something from

Words put aside by hand, to make something from — today a loop or a story. Without a selection
both could only be made from words drawn at random from whatever the list showed, which is fine for
"give me something to listen to" and useless for "these eight words I keep getting wrong". The store
is `web/src/wordSelection.ts`; the bar is `SelectionBar.tsx`; the row is `SwipeRow.tsx`; the dialogs'
word source is `MakeFrom.tsx`; the design of record is the prototype (`design/ui-prototype/`,
`?select=1`).

---

## What a selection is, and what it is not

**A selection is a working pile, not part of the vocabulary.** It is gathered over minutes or an hour
— reading through a topic, opening articles, noticing words on the map — and then used. That decides
most of the design:

- **It outlives navigation.** Changing topic, searching, opening an article or the map, and reloading
  all leave it alone. This is the whole of what a selection must do that a checkbox in one view
  cannot: a checkbox belongs to the list it is drawn in, and raises questions a pile does not have —
  what happens to it when the topic changes, or when you search?
- **It belongs to this device and is never synced.** It lives in local storage beside the other
  per-device state, not in the replicated graph, so it touches no schema version and needs no write
  route. A pile gathered on the tablet is not on the phone; that is the price, and a pile is short-lived
  enough to pay it. The record carries the account it was made in: another account on the device reads
  an empty selection and its first write replaces the record, the rule the replica follows.
- **There is one selection per vocabulary language**, because a loop and a story are each in one
  language. The bar shows the selection for the language on screen.
- **It is ordered, in the order words were chosen**, because when a dialog cannot take them all, the
  first chosen are the ones used. Order is intent.
- **An entry is a lexeme id and nothing else.** What the word is — its headword, whether it still
  exists — is read from the replica when it is drawn (`selectedWords` in `selectors.ts`), so a word
  deleted since simply stops appearing and nothing ever repairs the store.

**It is not a topic.** A topic files a word permanently, is synced, and is the owner's curation. A
selection is transient, device-local, and exists to be consumed. Keeping them apart keeps a throwaway
pile from becoming a second, half-synced filing system, and a selection never syncs.

## Marking a word

**Mark, don't tick.** A word joins the selection through an explicit action on the word itself — a
row's right-click menu or swipe, a button on the article, the Select toggle in a map peek — never ⌘-click
and never checkboxes. A vocabulary of a thousand words across a dozen topics is not a list anyone ticks
through, and a list of checkboxes invites exactly the bulk-tick-then-lose-it interaction a pile exists
to avoid.

**One row for words, loops and stories** (`SwipeRow.tsx`), because a pointer and a finger do not have
the same gestures. A pointer right-clicks and gets a menu under it; a finger pushes the row aside, right
to left, and finds the same actions behind it, with Delete in red. Word rows offer *Add to / Remove from
selection* and *Delete*; loops and stories offer *Delete*. The swipe is scroll-snap rather than touch
handlers — the way the cards already swipe — so there is no pointer arithmetic to get wrong and a
trackpad gets it free. The scroller and the element the menu hangs off are two elements, because
`overflow-x` makes the vertical axis a scroller too and a menu inside it would be clipped. The row was
written out twice, for loops and for stories, before words needed it; there must not be a fourth.

**The article** has a Select toggle beside Delete on a wide screen, and a *Select* item in the ⋯ menu,
above "Delete this word", on a phone. **The map's peek** has a Select toggle, and selecting there marks
every sense of the word — selection is of words, and a map is of senses.

## The mark

**Selected words look selected, and the mark moves nothing.** A selected row's plate is ringed in the
core colour with a gap of the page's paper, and wears a check badge at its lower right. The ring is a
`box-shadow` and the badge is absolutely placed, so the word, the gloss and the row height never shift —
the rule every mark in Acervo follows. The mark is distinct from hover and from the open row.

On the map the same badge sits on a sense's emoji once the map is zoomed in far enough to show emoji;
further out it is a ring around the dot, which reads differently from Find's plain filled dots.
Selected senses are always labelled and never dimmed, so a pile can be seen where it lives.

## The bar

**It shows the pile and what it is for.** On the left, an icon, the count, and as many whole words as
fit, then "+N"; on the right, **Loop** and **Story**, and **×** to forget the selection. The words are a
button: they open the list of every selected word, where one can be opened or taken out without finding
it again among a thousand.

**Where it is drawn** is the part with the most judgement in it:

- **Over the list, the map and an article; never over Add, the loops or the stories.** Those surfaces
  have their own Make buttons, and the Make buttons offer the selection.
- **Over an article, only on a wide window and only while the ask dock rests.** This is a deliberate
  exception to the rule that the article column carries no second bar ([`loops.md`](loops.md) §2.13):
  the owner reads words in order to gather them, and a wide window has the height to spare.
- **On a phone the article keeps its whole screen**, and its foot belongs to the ask dock. There the ⋯
  menu's Select item and a toast say what the bar would.
- **On a phone, over the list, it takes the place of the Loops / Stories / Map bar** — except that a
  loop that is playing keeps its bar, under the selection bar. Hiding what is sounding would be worse
  than a second row.

**Forgetting is undoable.** × clears the selection at once and the toast offers Undo. A pile can be
twenty words gathered over an hour, and one mistaken tap should not throw that away.

**Making something keeps the selection**, so the same words can become a story and a second loop. Only
× clears it.

## Making from it

Loop and Story open the ordinary make dialogs, and **the dialogs say exactly what will be sent.** When a
selection exists, a switch offers **Your selection · N** or **Random from {scope}**. It starts on the
selection when the dialog was opened from the bar, and on the random draw when opened from a surface's
own Make button — which is what that button always meant.

- **The selection is drawn as chips, in the order chosen.**
- **Undimmed means sent.** A word the kind cannot use is struck through, and a sentence names it and
  says why — for a loop, a word with no `primaryGloss` — because a strike-through alone explains nothing
  on a device with no hover. Words past the kind's limit (the loop schema's `maxItems`, a story's
  maximum of eight) are struck through too, and the first chosen are the ones used.
- **The button counts only the words it will send.**
- **The random draw is the kind's own**: a story draws words a story can use, not words a loop can say
  — sampling a loop's eligible words would give a scope with no single-term glosses no story at all.

**No server change.** `POST /loops` and `POST /stories` already take lexeme ids and never re-derive the
scope, which is what made choosing words by hand the same route with a different list.
