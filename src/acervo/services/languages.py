"""The languages a vocabulary may be kept in, for Settings ▸ Vocabularies.

CLDR's answer through `models/locales.catalogue`, not a list in the code: each language's English
name and its own, the region a flag stands for when no variety is chosen, and the varieties it has —
so the form can offer a language's varieties before the vocabulary exists.
"""

from __future__ import annotations

from typing import Any

from acervo.models import locales


def catalogue_view() -> dict[str, Any]:
    return {"languages": [
        {"tag": language.tag, "name": language.name, "autonym": language.autonym,
         "region": language.region, "varieties": list(language.varieties)}
        for language in locales.catalogue()
    ]}
