# Every feature in every language worth supporting

**Status:** open. Every record already carries its `language`, and dictionaries, pictures, voices and
the map work per language. What has never been done is checking that the whole of Acervo works, end
to end, for the languages people actually learn — rather than for the ones the owner happened to
start with.

## 1 · An audit, one row per language

The ten or so most-learned languages — at least Spanish, French, German, Italian, Portuguese,
Russian, Japanese, Chinese, Korean and English — each checked against every feature:

| Feature | What to check |
|---|---|
| Capture and compose | an article that is right in the language's own terms: gender, aspect, reading, script |
| Search | finding a word by its lemma, an inflected form, a transliteration |
| Fonts and layout | every script renders in the article, the list, loops, stories and Anki cards |
| Pictures | a brief that understands the sense |
| Voices | a voice exists on the chain for the language, plain and expressive |
| Clips | the corpus holds the language at all |
| Dictionaries | a source worth installing ([`../dictionaries.md`](../dictionaries.md)) |
| Loops, stories, Anki, the map | made and shown correctly |

The result is the table filled in, and a short list of fixes. Chinese has more beyond correctness
than a row can hold, and is its own plan ([`chinese.md`](chinese.md)); Japanese and Korean may turn
out to need the same once the audit has looked.

## 2 · Conjugations and other forms

Shown in the article, per language, where they help: a verb's conjugation, a noun's case forms. A
dictionary's `forms` are one source ([`../dictionaries.md`](../dictionaries.md) §2); a model is the
other, and a generated table is exactly the kind of output a learner cannot check. So a model-written
form ships only behind a check — against a dictionary where one exists, or a rule where the
morphology is regular — and the quality work in [`../quality/`](../quality/article-quality.md) is where
that check is designed.
