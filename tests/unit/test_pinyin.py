"""The Anki side of numbered Pinyin, held to the interface's own cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acervo.pinyin import accented_pinyin, is_mandarin

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
