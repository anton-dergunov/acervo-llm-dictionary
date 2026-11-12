# Chinese, Japanese and Korean · what the schema does not cover

**Status:** not started, deliberately. The three are one plan because what they share — no spaces
between words, or not where a European tool expects them — breaks the same features in all three;
what is Chinese alone is the larger part, and has its own section.

## Words without spaces

A tool that finds the word under a finger, or counts how common a word is, has to cut text into words
first, and for these languages that is a segmenter, not a split on spaces.

- **Rare** (the make dialogs' order by word frequency, `src/acervo/frequency/`) reads wordfreq's
  lists, which exist for all three. Chinese is cut by `jieba`, which is installed; **Japanese and
  Korean need MeCab and its dictionaries, which are not, so Rare refuses them by name** ("There is no
  word-frequency list for Japanese…"). Covering them is installing MeCab with the Japanese and Korean
  dictionaries in the server image and letting `covers()` say yes; measure the image's growth first.
- **A tap on a photo or a story** lands on a character, not a word (below, and
  [`../../features/look-up.md`](../../features/look-up.md)).
- Whatever else Japanese and Korean need beyond this is the audit's to find
  ([`language-support.md`](language-support.md)); Chinese is known to need more, below.

## Chinese

What exists is the part that is painful to retrofit: every
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

### Correctness first

What a Chinese word needs before anything is built on top of it — part of making every feature work in
every language ([`language-support.md`](language-support.md)), but specific enough to list here.
Tones shown as tones, and Pinyin search with or without them, are built
([`../../features/articles.md`](../../features/articles.md), "Readings"); a reading is still rendered,
not checked (the pinyin defect in [`article-quality.md`](../quality/article-quality.md)). How other
scripts would show what their spelling hides is [`readings.md`](readings.md).

### Learning the characters

For a European learner the characters are the hard part, and the one thing a vocabulary tool can do
that a dictionary does not: **help remember them**. Not a second Pleco — the dictionary exists and is
good — but what is useful *in the owner's own vocabulary*, next to words they chose.

How a character is written, and practising it with the strokes checked as they are drawn, are built:
the Write sheet ([`../../features/writing.md`](../../features/writing.md)). Still to do:

- **Writing practice as a queue.** A Write tab beside Loops and Stories, worth building once the sheet
  has been used on the iPad: the owner's characters, each drawn from memory when it is due. It needs
  attempts recorded. An attempt is made once and never edited, so it can wait on the device the way a
  play does ([`../../architecture/sync.md`](../../architecture/sync.md)). It would be per *character*
  rather than per word, since characters recur across words, and the schedule would be read from the
  attempts rather than stored. It is a new replicated record, so a schema change carried across by a
  throwaway converter.
- **Taiwan's stroke order** for Traditional characters, where it differs from the mainland's. It
  needs a second dataset, and is worth it only if Traditional is ever learned in earnest.
- **Pictures over pictographic characters** — a person drawn so that its legs are the strokes of 人 —
  with an experiment first: [`character-pictures.md`](character-pictures.md).
- **What a character is made of** — its components, and which one carries the meaning and which the
  sound, from the composition relation above.
- **Recognising it** — the character alone, without the word around it.

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
