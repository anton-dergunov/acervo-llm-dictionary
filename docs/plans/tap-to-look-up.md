# Tap a word to look it up

**Status:** open. The gesture exists in one place — photo capture — and should exist wherever the
owner reads text in the language being learned.

**The use.** Reading a story, an example or a clip, most unknown words are ones the owner has not
added. Today the way to learn one is to leave, open Add and type it. Instead: tap the word, see a short
explanation where it sits, and add it with one more tap if it is worth keeping.

## What already exists

Photo capture does exactly this on a photographed page
([`../features/photo-capture.md`](../features/photo-capture.md)): a tap chooses the unit under the
finger, `POST /capture/resolve` answers on the fast `quick` chain with the lemma and a gloss, and
"Add" hands the word and its sentence to the ordinary capture pipeline, so it arrives with the
sentence as its attestation. That is the whole pipeline this needs; **a new place to tap is a new
transport, not a second pipeline** ([`../features/capture.md`](../features/capture.md)).

## Where to add it

- **The story reader.** Words from the vocabulary are already marked there, but not tappable, and a
  tap on a passage plays it. Look-up and playback both want the tap, so the reader has to choose —
  a tap on a word looks up, a tap elsewhere in the passage plays, is the likeliest answer.
- **An article's examples and clips.** Selecting text there offers only "Listen" today; "Look up"
  belongs beside it.
- **A loop's lines**, if it turns out to be wanted while listening.

A tapped word that is already held opens its article instead of looking it up. Words in languages
with no spaces need the unit chosen around the tapped character, as for photos
([`languages/chinese.md`](languages/chinese.md)).
