# Readings · showing what the spelling hides

**Status:** not started; each language is built when it is learned. Mandarin is done: tones are drawn
as tone marks, colours and contours over the characters
([`../../features/articles.md`](../../features/articles.md), "Readings"). This plan is the same idea for the
other languages people learn, written down while the Mandarin work is fresh.

A learner needs to see what a language's ordinary spelling leaves out: the tones, the pitch accent,
the stress, or the vowels. The `reading` field already exists for this, and `Reading.tsx` already
picks a renderer by language. So each language below costs three things:

- a rule in the compose prompt saying exactly how its reading is written
- a parser and renderer for that reading
- a source to check the reading against, because a model's reading is a guess

A language whose IPA already shows what its spelling hides needs none of this. Spanish, Italian,
Portuguese, French, German and English have stress or vowel quality that IPA marks, and `ipa` is
already shown.

## Ordered by what a learner gains

### Japanese: furigana, then pitch accent

- **Hidden:** which reading a kanji takes, and the pitch accent. Tokyo Japanese has a pitch accent,
  not tones: each word either has a fall after one mora, or has none (*heiban*).
- **Furigana** are kana set as ruby over each kanji, with okurigana (the kana already in the word)
  left bare. The reading would be the whole word in kana. Lining it up with the kanji means matching
  the okurigana first, then splitting what is left. That works the way `alignHanzi` does, falling back
  to a line whenever it cannot be sure.
- **Pitch accent** is drawn as a line over the high morae with a step down where the pitch falls. This
  is the NHK accent dictionary's and OJAD's notation. It needs a new lexeme field: the accent number,
  where 0 is heiban and *n* means the fall comes after mora *n*. That is a schema change. A model
  cannot be trusted with pitch accent, so the data has to come from a dictionary source. The Kanjium
  accent data is a candidate; check its licence first.
- Japanese shares the word-segmentation work in [`cjk.md`](cjk.md).

### Cantonese: Jyutping, six tones

- **Hidden:** six tones. In Chao numbers they are 55, 25, 33, 21, 23 and 22.
- **Notation:** Jyutping. It writes tones as digits by convention, not as marks (Yale romanization uses
  marks, but learners rarely meet it). So the digits stay, drawn small and raised.
- **Visual:** the same columns as Mandarin. Contours do more of the work here: three of the six tones
  are level, and six colours are too many to remember.
- **Source:** the CC-Canto converter already compiles Jyutping. Cantonese has a `yue` tag, and
  `isMandarin` already keeps it out of the Pinyin renderer.

### Korean: the standard pronunciation

- **Hidden:** Hangul spells morphemes, not sounds. Liaison, nasalisation and tensing change how a word
  is said: 국물 is said [궁물], and 같이 is said [가치]. Korean has no tones.
- **Notation:** the standard pronunciation in Hangul, in brackets. This is what Korean dictionaries
  print, and it is only shown when it differs from the spelling. Revised Romanization can sit beside
  it for a beginner.
- **Source:** the sound changes follow rules, so a rule-based grapheme-to-phoneme library can check
  the model, rather than trusting it.

### Russian and Ukrainian: stress

- **Hidden:** stress is free and moves between forms, and normal spelling never marks it. The vowels
  are reduced around it, so it changes how the whole word sounds.
- **Notation:** an acute accent on the stressed vowel (молоко́), as learner dictionaries print it. ё
  is always stressed.
- **Visual:** draw the headword itself with the mark, using a combining acute (U+0301), and keep the
  stored headword unmarked. The headword is what dictionaries and search match on, and the dictionary
  merge already ignores stress marks.
- **Source:** Wiktionary-derived dictionaries carry stressed forms.

### Thai: five tones the script encodes indirectly

- **Hidden:** five tones (mid, low, falling, high and rising). Working one out takes the consonant
  class, the vowel length, whether the syllable is live or dead, and the tone mark. That is hard to
  read off the script.
- **Notation:** a romanization that marks tones, such as Paiboon's. The romanization Thailand uses
  officially (RTGS) does not mark tones, so it is no use here.
- **Visual:** the same colours and contours as Mandarin, per syllable.
- Thai writes no spaces between words, which is the same segmentation problem as in [`cjk.md`](cjk.md).

### Arabic, Persian and Hebrew: the unwritten vowels

- **Hidden:** the short vowels, which ordinary text leaves out.
- **Notation:** the vowelled headword (harakat in Arabic and Persian, niqqud in Hebrew), plus a
  transliteration. For Arabic that is DIN 31635 or ALA-LC.
- **Visual:** the vowelled form as the reading under an unvowelled headword. Right-to-left layout in
  the masthead and the list needs checking first.

### Hindi: the inherent vowel

- **Hidden:** schwa deletion. Devanagari writes an inherent *a* that is often not said: कमरा is
  *kamrā*, not *kamarā*.
- **Notation:** IAST or ISO 15919 romanization.

### Vietnamese: nothing to add

The six tones are already in the spelling as diacritics. Colouring syllables by tone would be cheap,
since the tone can be read off the letters, but the learner gains little from it. There is one
regional difference: in the south, the *hỏi* and *ngã* tones merge, which belongs with
[`accents.md`](accents.md).
