"""What a pronunciation reads, found in the wire-shaped records of one word.

Four kinds of thing can be spoken, and each carries its own language rather than assuming the word's:
a definition is in `definitionLang`, which is often the learner's own language rather than the one
being learned, and an example says what it is written in.

**The *use* is decided here; which order reads it is not.** A headword and a definition are `words`;
an example and an attestation are `examples` — and only an example has an emotion to give, since an
attestation is a sentence the learner met rather than one written to be remembered. Which of the two
orders reads each use is the owner's answer, held in `pronunciation_settings`, and this package may
not read that: it stands alone beside the provider package and the article view. So the service maps
use to order, and this module never learns that an order exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from acervo.article import live

KINDS = ("lexeme", "sense", "example", "attestation")
COLLECTION = {
    "lexeme": "lexemes", "sense": "senses", "example": "examples", "attestation": "attestations"
}
# What is being read, never which chain reads it. See `repository/pronunciation_settings`.
WORDS, EXAMPLES = "words", "examples"


@dataclass(frozen=True)
class Target:
    kind: str
    id: str
    lexeme_id: str
    # The vocabulary of the word it belongs to, whose variety it is heard in when it is in that
    # vocabulary's language.
    vocabulary_id: str
    text: str
    language: str
    # The example's own emotion, whether or not it will be sent: that is the service's decision.
    emotion: str | None
    # What is being read: `words` or `examples`. The owner's delivery setting turns this into an order.
    use: str


def target_in(changes: Mapping[str, list[dict]], kind: str, identifier: str) -> Target | None:
    """The live record a request names, as something to say, or nothing.

    Nothing covers a record that does not exist, one that is deleted, and one whose text is empty,
    because none of them can be spoken and the caller must not be able to tell which it was.
    """
    if kind not in KINDS:
        return None
    record = next(
        (one for one in live(changes.get(COLLECTION[kind], [])) if one.get("id") == identifier), None
    )
    if record is None:
        return None
    lexemes = {one["id"]: one for one in live(changes.get("lexemes", []))}
    senses = {one["id"]: one for one in live(changes.get("senses", []))}

    if kind == "lexeme":
        lexeme, text, language, emotion = record, record.get("headword"), record.get("language"), None
    elif kind == "sense":
        lexeme = lexemes.get(record.get("lexemeId", ""))
        text, language, emotion = record.get("definition"), record.get("definitionLang"), None
    elif kind == "example":
        sense = senses.get(record.get("senseId", ""))
        lexeme = lexemes.get((sense or {}).get("lexemeId", ""))
        text, language, emotion = record.get("text"), record.get("textLang"), record.get("emotion")
    else:
        lexeme = lexemes.get(record.get("lexemeId", ""))
        text, language, emotion = record.get("text"), (lexeme or {}).get("language"), None

    if lexeme is None or not (text or "").strip() or not language:
        return None
    return Target(
        kind=kind,
        id=identifier,
        lexeme_id=lexeme["id"],
        vocabulary_id=str(lexeme.get("vocabularyId") or ""),
        text=str(text),
        language=str(language),
        emotion=(emotion or "").strip() or None,
        use=EXAMPLES if kind in ("example", "attestation") else WORDS,
    )


def wanted(changes: Mapping[str, list[dict]], lexeme_id: str, choice: Mapping[str, bool]) -> list[Target]:
    """What recording in advance means for one word: target-language text only, in reading order.

    The headword always is target language. A definition is only when the vocabulary defines words
    in the language being learned, and an example only when it is written in it — a gloss-language
    example is read the day somebody presses play, not on the day the word is saved.
    """
    lexeme = next((one for one in live(changes.get("lexemes", [])) if one.get("id") == lexeme_id), None)
    if lexeme is None:
        return []
    language = lexeme.get("language", "")
    senses = sorted(
        (one for one in live(changes.get("senses", [])) if one.get("lexemeId") == lexeme_id),
        key=lambda one: (one.get("order", 0), one.get("id", "")),
    )
    found: list[Target | None] = []
    if choice.get("headword"):
        found.append(target_in(changes, "lexeme", lexeme_id))
    for sense in senses:
        if choice.get("definitions") and _same_language(sense.get("definitionLang", ""), language):
            found.append(target_in(changes, "sense", sense["id"]))
        if choice.get("examples"):
            for example in live(changes.get("examples", [])):
                # A clip example is recorded speech already, and is never recorded again.
                if (example.get("senseId") == sense["id"] and not example.get("videoRef")
                        and _same_language(example.get("textLang", ""), language)):
                    found.append(target_in(changes, "example", example["id"]))
    return [target for target in found if target is not None]


def current(clip: Mapping | None, target: Target) -> bool:
    """Whether a stored clip still says what its record says. An edited record makes it stale."""
    return bool(
        clip and not clip.get("deleted") and clip.get("text") == target.text
        and clip.get("lang") == target.language and clip.get("audioRef")
    )


def _same_language(one: str, other: str) -> bool:
    return one.split("-")[0].lower() == other.split("-")[0].lower()
