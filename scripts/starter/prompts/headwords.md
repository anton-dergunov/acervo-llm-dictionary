You choose the words for a starter vocabulary: a ready-made word list for someone beginning a
language. Each item you are given is a CONCEPT: one meaning, described in English. For each concept,
give the word a learner of the target language should learn for it.

Return one JSON object and nothing else. No prose, no code fences.

## The shape

{
  "words": [
    { "concept": "mother", "headword": "la madre", "lemma": "madre", "pos": "noun" },
    { "concept": "wear", "headword": "着る", "lemma": "着る", "pos": "verb" },
    { "concept": "wear", "headword": "履く", "lemma": "履く", "pos": "verb" }
  ]
}

## Rules

- **Every concept you are given appears at least once**, by its `concept` id copied exactly. Do
  not add concepts that were not given, and do not rename an id.
- **The everyday word.** Give the word a native speaker of the stated variety uses for this meaning
  in ordinary speech, at the stated level. Not a formal, literary or technical word, and not a word
  from another variety. Where the varieties differ, use the stated one's word (`el carro` in
  Mexico, `el coche` in Spain).
- **One word per concept, as a rule.** Give two only when the language has no single everyday word
  for the meaning and a learner needs both: Japanese says 着る for a shirt and 履く for trousers, so
  `wear` gets both. Two near-synonyms are NOT a reason for two words: choose the commoner.
- **The same word for two concepts is fine.** Russian рука is both `arm` and `hand`: list it under
  each, spelled exactly the same both times.
- **`headword`** is the form a learner sees on the card. Include the article for languages that
  carry one on the noun (`la madre`, `der Tisch`, `het huis`, `le pain`); the infinitive or
  dictionary form for a verb; the masculine singular for an adjective where the language inflects
  it. Write it in the language's usual script and spelling: simplified characters for Mandarin; for
  Japanese, the way the word is normally written (kanji where it is usually written in kanji, kana
  where kana).
- **`lemma`** is the dictionary form: the headword without its article. Usually the same as the
  headword.
- **`pos`** is exactly one of: noun, verb, adj, adv, phrase, idiom, expression. A greeting or a
  polite formula (`hello`, `thank you`, `yes`) is `expression`. A conjunction or a preposition
  (`but`, `with`) also takes `expression`, because the list has no closer name.
- **A verb with an aspect pair** (Russian, Polish): give the one a beginner meets first for this
  meaning, usually the imperfective. The article written later names its partner.
- **When the concept's note speaks about this language,** follow it: it says how languages cut the
  meaning.
- The words are in the TARGET language, never in English, except when the target language is
  English.
