"""How rare each of the owner's words is, for a make dialog's "Rare" order.

Derived on request and never stored: it is a figure about the language, not about the owner's
record, and a lookup per word costs microseconds. The dialog asks once a session, when Rare is first
chosen, so this is not on any path a save or a sync takes.

A language with no frequency list is refused by name, with a sentence the dialog shows beside the
option, rather than answered with figures that would order the words by nothing.
"""

from __future__ import annotations

from typing import Any

from acervo import frequency
from acervo.errors import ApiError
from acervo.pronunciation.speak import language_name
from acervo.repository import graph


def rarity(owner: str, language: str) -> dict[str, Any]:
    """`{language, zipf: {lexemeId: figure}}` for every live word in `language`; a lower figure is
    a rarer word."""
    if not language or not language.strip():
        raise ApiError(400, "invalid_input", "Say which language's words to rate.")
    if not frequency.covers(language):
        raise ApiError(
            422, "rarity_unavailable",
            f"There is no word-frequency list for {language_name(language)}, so its words cannot be "
            "ordered by how rare they are.",
            noted={"language": language},
        )
    return {
        "language": language,
        "zipf": {lexeme_id: round(frequency.zipf(headword, language), 2)
                 for lexeme_id, headword in graph.headwords(owner, language)},
    }
