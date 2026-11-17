"""The server's Pinyin (Anki's marks, compose's syllables), held to the interface's own cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acervo.pinyin import INVENTORY, accented_pinyin, is_mandarin, pinyin_syllables

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "web" / "src" / "testFixtures" / "pinyinVectors.json")
    .read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize(("numbered", "marked"), VECTORS)
def test_marks_every_shared_case_as_the_interface_does(numbered, marked):
    assert accented_pinyin(numbered) == marked


def test_mandarin_is_every_chinese_tag_but_cantonese():
    assert is_mandarin("zh-Hans") and is_mandarin("zh-Hant-TW") and is_mandarin("cmn")
    assert not is_mandarin("zh-yue") and not is_mandarin("yue") and not is_mandarin("es")


SYLLABLE_VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "web" / "src" / "testFixtures" / "pinyinSyllableVectors.json")
    .read_text(encoding="utf-8")
)


def shown(reading: str) -> str | None:
    syllables = pinyin_syllables(reading)
    if syllables is None:
        return None
    return "|".join(f"{one.before}{one.text}{one.tone}" for one in syllables)


@pytest.mark.parametrize(("reading", "expected"), SYLLABLE_VECTORS["cases"])
def test_cuts_every_shared_reading_as_the_interface_does(reading, expected):
    assert shown(reading) == expected


@pytest.mark.parametrize(("reading", "erhua"), SYLLABLE_VECTORS["erhua"])
def test_marks_erhua_as_the_interface_does(reading, erhua):
    assert [one.erhua for one in pinyin_syllables(reading)] == erhua


def test_holds_the_interfaces_syllable_table():
    assert INVENTORY == frozenset(SYLLABLE_VECTORS["inventory"])
    for syllable in INVENTORY:
        assert len(pinyin_syllables(f"{syllable}1")) == 1, syllable
