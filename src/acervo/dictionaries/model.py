"""What a compiled dictionary entry says.

Deliberately **not** `ArticleDraft`. External entries are render-only: they never reach the database,
never carry record ids, and never round-trip through `parseArticle` — `docs/acervo-external-
dictionaries.md` §11.3 settled that, because Acervo's seven-value part-of-speech enum does not
survive contact with real dictionaries and `parseArticle` rejects the free-text label that replaces
it.

Two differences from the draft shape are size decisions rather than modelling ones. §11.0a measured
the `fields` tier as larger than HTML raw and traced it to `definitionLang` and `order` being
repeated on every sense; `definitionLang` is hoisted to the entry, where it is uniform for a whole
dictionary anyway, and `order` is deleted because a JSON array is already ordered.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: `web/src/domain.ts`. An external entry uses this only when the source's own value genuinely lands
#: in it, and says nothing at all otherwise.
ACERVO_POS = {"noun", "verb", "adj", "adv", "phrase", "idiom", "expression"}

#: Source label -> Acervo's enum. Anything absent keeps its own label and gets no `pos` (§11.3):
#: bucketing `preposition` into `expression` is a lie and dropping the entry is a worse one.
POS_MAP = {
    "noun": "noun", "name": "noun", "proper noun": "noun", "propn": "noun", "n": "noun",
    "verb": "verb", "v": "verb", "adj": "adj", "adjective": "adj",
    "adv": "adv", "adverb": "adv",
    "phrase": "phrase", "prep_phrase": "phrase", "proverb": "phrase",
    "prepositional phrase": "phrase", "phraseologicalunit": "phrase",
    "idiom": "idiom", "intj": "expression", "interjection": "expression", "int": "expression",
    "exp": "expression", "expression": "expression",
}

REGISTER_TAGS = {
    "colloquial": "colloquial", "informal": "colloquial", "slang": "slang",
    "vulgar": "vulgar", "formal": "formal", "literary": "formal",
}

GRAMMAR_TAGS = {"transitive", "intransitive", "reflexive", "pronominal"}

#: `GENDER_VALUES` in `domain/validation.py`: the genders an entry may say a noun has.
GENDERS = ("masculine", "feminine", "common", "neuter")


@dataclass
class Example:
    text: str
    textLang: str | None = None
    translation: str | None = None
    translationLang: str | None = None


@dataclass
class Sense:
    definition: str
    definitionLang: str | None = None
    domain: str | None = None
    examples: list[Example] = field(default_factory=list)


@dataclass
class Entry:
    """One headword, with every part of speech the source holds for it."""

    headword: str
    language: str
    senses: list[Sense] = field(default_factory=list)
    lemma: str | None = None
    definitionLang: str | None = None
    ipa: str | None = None
    #: Every distinct transcription the source gives, `ipa` first, when there is more than one.
    #: Wiktionary lists one per variety (`calle` is /ˈkaʝe/, /ˈkaʎe/, /ˈkaʃe/…) without saying which
    #: is which, so a transcription is attested when it is any of them.
    ipas: list[str] = field(default_factory=list)
    reading: str | None = None
    pos: str | None = None
    posLabel: str | None = None
    register: str | None = None
    #: The noun's genders, in `GENDERS`, in the order the source gives them: several when homographs
    #: differ (French `livre` is masculine as a book and feminine as a pound).
    genders: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    def payload(self) -> bytes:
        """Compact JSON, the stored form: always an *array* of articles, usually of length one.

        A headword can genuinely have more than one article — CC-CEDICT writes a separate line per
        reading, so simplified 行 is both *háng* and *xíng* — and an array is what lets the packer
        splice those together without knowing anything about what an entry means. Keeping the shape
        uniform costs two bytes per entry before compression and nothing after it.

        JSON rather than YAML because the only argument for YAML would have been reusing
        `parseArticle`, which §11.3 rules out anyway — so YAML would cost a parser call per lookup
        and buy nothing. Keys are sorted so a rebuild is byte-identical.
        """
        return json.dumps([_prune(self)], ensure_ascii=False, separators=(",", ":"),
                          sort_keys=True).encode("utf-8")


def _prune(value: Any) -> Any:
    """Drop empties. An absent field is smaller than a null one and means the same thing."""
    if isinstance(value, (Entry, Sense, Example)):
        return _prune(vars(value))
    if isinstance(value, dict):
        cleaned = {key: _prune(item) for key, item in value.items() if item not in (None, "", [], {})}
        return {key: item for key, item in cleaned.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_prune(item) for item in value]
    return value


def resolve_pos(source_label: str | None) -> tuple[str | None, str | None]:
    """`(enum value or None, the source's own word or None)`.

    The source's word is always kept and always displayed; the enum value appears only when it is
    genuinely the same thing. Where a source says nothing — CC-CEDICT carries no part of speech at
    all — the entry says nothing and the interface shows nothing.
    """
    if not source_label:
        return None, None
    return POS_MAP.get(source_label.strip().lower()), source_label.strip()
