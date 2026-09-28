# Chinese · the subsystem beyond the schema

**Status:** not started, deliberately. What exists is the part that is painful to retrofit: every
record carries its `language`, a Chinese lexeme **requires** a `reading` (pinyin, on a prefix test so
`zh-Hant-TW` and `zho` match), and dictionaries, pictures, voices
and the map already work per language. What is not built is modelling how the language works — and
that is a subsystem, not a column, worth building once there are opinions from using the rest.

Three things about Chinese break the assumptions the model makes for Spanish:

1. **The unit of learning is not the word.** It is component ↔ character ↔ word — three levels. 妈妈 is
   a word made of a character made of components. Modelling it needs a lexeme→lexeme composition
   relation.
2. **Tone is not decoration.** mā / má / mǎ / mà are four different words, so a reading must be
   checked, not trusted (see the pinyin defect in [`article-quality.md`](../quality/article-quality.md)).
3. **Traditional and Simplified are a variant axis**, not a dialect.

**Why components are worth it.** 妈 (mā, mother) = 女 (woman) + 马 (mǎ, horse): the horse is there for
**sound**, the woman for meaning. This is a phono-semantic compound, and roughly 80% of characters are
built this way. The anchor European languages share through Latin and Greek roots has a real analogue
in Chinese; it lives *inside* the character rather than across languages.

To do, when Chinese is being learned in earnest: the composition relation, component modelling,
measure words, a corpus for Chinese in the retrieval service, photo capture's tap-on-a-character
(below), and the Chinese views — a character network, a tone-pair grid, a syllable table
([`../../research/similar-projects.md`](../../research/similar-projects.md)).

## Correctness first

What a Chinese word needs before anything is built on top of it — part of making every feature work in
every language ([`language-support.md`](language-support.md)), but specific enough to list here.

- **Tones shown as tones.** A reading is written with tone marks, never trailing digits, everywhere a
  reading appears; dictionary entries already are (`web/src/pinyin.ts`). Beyond the mark, a small
  picture of each syllable's contour — level, rising, dipping, falling — is what a European ear
  actually needs to remember it.
- **Search by pinyin properly**: with marks, with digits, or with no tones at all (`tushu` finding
  图书) — today it is the numbered form that finds a word.

## Learning the characters: a spike

For a European learner the characters are the hard part, and the one thing a vocabulary tool can do
that a dictionary does not: **help remember them**. Not a second Pleco — the dictionary exists and is
good — but what is useful *in the owner's own vocabulary*, next to words they chose. A spike first,
to find out what that is:

- **What a character is made of** — its components, and which one carries the meaning and which the
  sound, from the composition relation above.
- **How it is drawn** — stroke order, animated, from an open dataset of stroke data rather than
  generated.
- **Drawing it** — practising with a pencil on the iPad, which is where the owner uses Acervo, with the
  strokes checked as they are drawn.
- **Recognising it** — the character alone, without the word around it.

What can be taken from existing datasets and what would have to be generated, checked or drawn is
the spike's first answer.

## Photos of Chinese and Japanese

Photo capture is built for languages that put spaces between words
([`../../features/photo-capture.md`](../../features/photo-capture.md)).

- **OCR is the easy part.** Vision reads both.
- **A tap lands on a character, not a word.** With no spaces, "the word under the finger" needs a
  segmenter (jieba, SudachiPy) or, more simply, the quick call choosing the unit around the tapped
  character, which it already does for *New York*.
- **SaT covers both languages**, but measure it rather than assume it.
- **Vertical Japanese text** changes reading order and the line geometry.
- **It needs its own fixtures**: photos with hand-checked text, and taps whose unit is several
  characters.

The layout format is character offsets and polygons, so nothing in it assumes spaces.
