"""Numbered Pinyin as it is read: ``tu2 shu1 guan3`` → ``tú shū guǎn``.

The twin of ``accentedPinyin`` in ``web/src/pinyin.ts``, for the one reader of a reading that is not
the interface: an Anki card. Both are held to the same cases in
``web/src/testFixtures/pinyinVectors.json``, so the two cannot drift. Only the conversion is here;
the syllables, tones and columns the interface draws are the interface's.

Anything that is not recognisably numbered Pinyin is returned untouched, so a reading already
written with marks, or not Pinyin at all, passes through. Imports nothing of Acervo's.
"""

from __future__ import annotations

import re

_MARKS = {
    "a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ",
}
_SYLLABLE = re.compile(r"^([a-zü]+)([0-5])$", re.IGNORECASE)


def is_mandarin(language: str) -> bool:
    """Every Chinese tag but Cantonese, whose Jyutping has six tones and no marks."""
    lower = language.lower()
    if lower.startswith("cmn"):
        return True
    return lower.startswith("zh") and not re.match(r"^zh-yue\b", lower)


def _mark_position(letters: str) -> int:
    lower = letters.lower()
    for vowel in ("a", "e"):
        if vowel in lower:
            return lower.index(vowel)
    if "ou" in lower:
        return lower.index("ou")
    for index in range(len(lower) - 1, -1, -1):
        if lower[index] in _MARKS:
            return index
    return -1


def _accent_syllable(token: str) -> str:
    normalised = re.sub(r"([nljqxy])v", r"\1ü", re.sub(r"u:", "ü", token, flags=re.IGNORECASE),
                        flags=re.IGNORECASE)
    parts = _SYLLABLE.match(normalised)
    if not parts:
        return token
    letters, tone = parts.group(1), parts.group(2)
    if tone in ("0", "5"):
        return letters
    at = _mark_position(letters)
    if at < 0:
        return letters
    vowel = letters[at]
    marked = _MARKS[vowel.lower()][int(tone) - 1]
    if vowel != vowel.lower():
        marked = marked.upper()
    return letters[:at] + marked + letters[at + 1:]


def is_numbered_pinyin(reading: str) -> bool:
    tokens = reading.split()
    if not tokens:
        return False
    syllables = [token for token in tokens if _SYLLABLE.match(re.sub(r"u:", "ü", token, flags=re.IGNORECASE))]
    # Most of it, not all: a reading may carry a stray `·` between syllables.
    return bool(syllables) and len(syllables) >= len(tokens) - 1


def accented_pinyin(reading: str) -> str:
    if not is_numbered_pinyin(reading):
        return reading
    return "".join(part if part.isspace() else _accent_syllable(part)
                   for part in re.split(r"(\s+)", reading.strip()))
