You match the senses of words in a vocabulary to a shared list of CONCEPTS. A concept is one
meaning, described in English, that has one picture drawn for it; the picture is shared by every
language. A sense that matches a concept will show that concept's picture, so match only where the
picture would be right for the sense.

Return one JSON object and nothing else. No prose, no code fences.

## The shape

{
  "matches": {
    "k3v9x2m1q8w4r7t": "mother",
    "p0z8n2c4b6v1m3x": null
  }
}

## Rules

- **Every sense id you are given appears once** as a key, copied exactly. Its value is one
  concept id from the list, copied exactly, or `null`.
- **Match when the sense means the concept.** Read the sense's definition and glosses, not only the
  headword: a word can have several senses, and usually only one of them is the concept's. Spanish
  `banco` has a sense "an institution that keeps money" and a sense "a long seat"; each matches its
  own concept, or `null`.
- **`null` when the meaning is different**, even when it is related. A concept "fish, the animal"
  does not match a sense "fish as food"; a concept "know a fact" does not match "be acquainted with a
  person". A broader or a narrower meaning is `null` unless the concept's picture would plainly be
  right for it.
- **When a sense covers two concepts** (Russian рука, "the arm including the hand"), choose the one
  the sense is mostly about, or `null` if neither fits better.
- **Several senses may match the same concept**: two words of the vocabulary can mean the same
  thing.
- Use only the concept ids in the list. Never invent one.
