# Look-up · tap a word you are reading

**Built**, in the story reader, the loop player and the article. Reading a story, an example or a loop
line, most unknown words are ones the owner has not added, and learning one used to mean leaving for
Add and typing it. Now: tap the word, read what it means *in this sentence* where it sits, and add it
with one more tap if it is worth keeping. The design of record is the prototype
(`design/ui-prototype/`, `?story=1&part=0&tap=migajas`).

## A new place to tap, not a second pipeline

Photo capture already had the whole pipeline ([`photo-capture.md`](photo-capture.md)): a tap chooses
the unit under the finger, `POST /capture/resolve` answers on the fast `quick` chain with the lemma
and a gloss, and the answer is carried into the capture that follows so resolve is not paid for
twice. A word tapped while reading is the same call with `source: "reading"`, and its Add is the
headless `POST /captures` job carrying that answer ([`capture.md`](capture.md)).

- **The sentence comes back verbatim.** A photo's text may be repaired, since OCR damages it; text
  read in Acervo is finished, and the `reading` section of `prompts/acervo_resolve.md` switches
  "Fixing the input" off for it. Without that, resolve "corrects" a story's sentence, the capture
  refuses a sentence its text does not contain (`pipeline.given_resolution`), and the attestation is
  no longer what was read. The section is quick-only, like `photo`: the full resolve never sees it,
  because Add carries the look-up's answer and does not resolve again.
- **Add files the word in the Inbox** rather than opening a review. The owner is reading, and a
  review screen would take them out of the story. The job checks the carried answer as `/capture`
  does, composes, and saves through the ordinary save, so the word arrives enriched with the
  sentence as its attestation. `sourceTitle` says where it was met — `Story · …`, `Loop · …`,
  `Entry · …` — with the kind `unknown`, because a `story` kind would change a replicated enum for a
  label a title already carries.
- **Online-only, like every write.** A look-up with the server unreachable says so on the sheet, and
  Add queues nothing.

## The tap moves nothing

In the story reader a tap already played a passage, and in the loop player a tap on a card seeked to
it. **A tap on a word in the language being learned now looks it up and moves no audio**; whatever the
tap used to do is a button on the sheet. That is *From here* or *This passage* in a story, which is
`playSegment` exactly as a passage tap was, and *Play from this line* in a loop. Anything that is not
such a word keeps its tap. In a loop that means the translation line, the language chip and the
card's edge still seek. In a story it means punctuation or a gap still plays the passage, and the
head button still reads the part. The alternatives were weighed in the prototype:

- **Tap to play, select to look up** kept listening unchanged, but it costs a long press for every
  look-up. The iPad's own callout also competes with the pill.
- **A look-up mode switch** has no conflict, but it is a mode to remember.

A tap on a word is the commoner want while reading, and hearing the sentence the word is in is what
follows it anyway.

**A selection offers Look up beside Listen** (`SelectionPill.tsx`), in the article and the story
reader. That is how a phrase the quick call did not widen to is looked up.

## A word you hold is answered from your words

`heldWord` in `selectors.ts` answers a tapped word from the replica, at once and offline. A story's
mark names its lexeme (`data-lexeme`); otherwise the tapped form is compared with each headword, with
and without its article, and each lemma. The sheet then shows the short gloss with **Open** rather
than jumping to the article, because leaving mid-story costs the owner their place. An inflected
form the replica misses is found by the server's look-up, which answers with `duplicates`, and the
sheet offers Open for that too. In an article, the article's own word is "this word" and has no Open.

**Open, then Back, returns to where the owner was**: the same page of the story, or the loop, still
playing. `App.tsx` keeps a `readingReturn` beside `mapReturn`, for the same reason Back from a word
opened on the map goes back to the map.

## Hit-testing without touching the DOM

`tapWord.ts` asks the browser where the caret would land under the finger (`caretPositionFromPoint`,
or WebKit's `caretRangeFromPoint`) and chooses the word around it with `Intl.Segmenter`. So nothing
is wrapped to become tappable, and a story, a loop line and an article are hit-tested as already
drawn. Measured in the prototype, WebKit and Chromium both hit-test inside a loop card's `<button>`,
so the card stays a button.

- **A tap near nothing selects nothing.** The caret lands on the nearest letter wherever the finger
  is, so the point must also fall on the word's own boxes, give or take a fifth of a line. This is
  photo capture's rule; without it a tap in the margin looks up the first word of the line beside
  it.
- **Which text counts** is the innermost block with a `lang` attribute, which every rendered block
  already carries for `selectionSpeech.ts`. It must be in the language being learned: a translation,
  a gloss or a note in the reader's own language is not looked up, nor is an article's headword.
- **A language written without spaces** gets its unit from the segmenter's word boundaries around the
  tapped character, and the quick prompt widens it as it does *New York*
  ([`../plans/languages/chinese.md`](../plans/languages/chinese.md)).

## The sheet

`LookUpSheet.tsx` has one hook per surface and one component. It is placed at the foot of whatever
is being read:

| Surface | Placement | Why |
|---|---|---|
| Story page | Over the foot of the page (`over`), moving to the top when the tapped word would be under it | Never cover the word the sheet is about |
| Loop player | Between the cards and the controls (`flow`) | Never over the controls |
| Article, page view | On top of the ask dock (`docked`) | The dock already owns the foot of the column |
| Article, Cards | Over the cards (`over`) | |

Its meaning line is photo capture's. For a word the owner does not hold it shows the sentence that
Add will keep. It is solid rather than translucent, because what showed through was words and
legible. The tapped word is painted with the CSS Custom Highlight API (`::highlight(look-up)`), which
colours text where it already is, so no mark can move body text. Where the API is missing the sheet
still names the word. Answers are cached per sentence and selection, so tapping back is free, and a
new tap aborts the one in flight.

## Not built

- **A clip's own player**, the corpus's component in the clip dialog, is not looked up in. The
  article's clip lines are, since they are ordinary examples.
- **Loop lines cannot be selected**, because they are buttons. A phrase in a loop is looked up by
  tapping one of its words, which the quick call widens.
