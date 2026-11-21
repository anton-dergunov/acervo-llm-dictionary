"""Which grammatical genders a language's nouns have, from CLDR — a fact of the language, not a choice.

Read from CLDR's `common/supplemental/grammaticalFeatures.xml` (Unicode, Inc.; Unicode License v3,
https://www.unicode.org/copyright.html), its `nominal` features without a `scope`, as of November
2026. CLDR splits the Slavic masculine into animate, inanimate and personal; Acervo has one
masculine, so all three read as it. A language CLDR lists with no gender has none; a language it does
not list is unknown, and nothing is said about it.

Used by compose's check to clear a gender a model wrote where the language has none (an English
noun marked neuter) and to name a Dutch *de*-word `common` where a model wrote masculine or feminine.
"""

from __future__ import annotations

_NONE: tuple[str, ...] = ()
_MF = ("masculine", "feminine")
_MFN = ("masculine", "feminine", "neuter")
_CN = ("common", "neuter")

GENDERS: dict[str, tuple[str, ...]] = {
    "af": _NONE, "am": _NONE, "ar": _MF, "az": _NONE, "bn": _NONE, "ca": _MF, "cs": _MFN, "da": _CN,
    "de": _MFN, "el": _MFN, "en": _NONE, "es": _MF, "fa": _NONE, "fi": _NONE, "fil": _NONE, "fr": _MF,
    "gu": _MFN, "he": _MF, "hi": _MF, "hr": _MFN, "hu": _NONE, "hy": _NONE, "id": _NONE, "is": _MFN,
    "it": _MF, "ja": _NONE, "kk": _NONE, "kn": _MFN, "ko": _NONE, "ky": _NONE, "lo": _NONE, "lt": _MF,
    "lv": _MF, "ml": _MFN, "mr": _MFN, "ms": _NONE, "my": _NONE, "nb": _MFN, "ne": _NONE, "nl": _CN,
    "nn": _MFN, "no": _MFN, "pa": _MF, "pl": _MFN, "pt": _MF, "ro": _MFN, "ru": _MFN, "si": _MFN,
    "sk": _MFN, "sl": _MFN, "sr": _MFN, "sv": _CN, "ta": _NONE, "te": _NONE, "th": _NONE, "tr": _NONE,
    "uk": _MFN, "ur": _MF, "uz": _NONE, "vi": _NONE, "zh": _NONE,
}


def genders_of(language: str | None) -> tuple[str, ...] | None:
    """The genders a language's nouns take, `()` for none, or `None` when CLDR does not say."""
    if not language:
        return None
    base = language.replace("_", "-").split("-", 1)[0].lower()
    return GENDERS.get(base)


def gender_for(language: str | None, gender: str | None) -> str | None:
    """`gender` as the language has it: kept, renamed, or cleared.

    A noun of either gender (`el estudiante`, `la estudiante`) is `common` in a language with
    masculine and feminine; in one whose genders are common and neuter, masculine and feminine are the
    old names of the common gender. A language CLDR does not know keeps what it was given.
    """
    if not gender:
        return None
    known = genders_of(language)
    if known is None or gender in known:
        return gender
    if gender == "common" and {"masculine", "feminine"} <= set(known):
        return gender
    if gender in ("masculine", "feminine") and "common" in known:
        return "common"
    return None
