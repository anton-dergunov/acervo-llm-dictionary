"""The rule that decides whether a loop take is recorded again, on the cases that settled it.

Every transcript and direction below is one of `experiments/take-verification/`'s: Whisper's own
words for a stored take, and the director note that take was sent. The owner judged each by ear.
"""

from __future__ import annotations

import pytest

from acervo import hearing
from acervo.hearing.rule import leaked

COUGH = ("Speak annoyed and raspy, seeking relief from irritation in the throat, but clearly, at a "
         "natural pace, with a natural pitch range.")
HOST = ("Speak a helpful host offering more food, warm and generous, but clearly, slightly slowly, "
        "with a natural pitch range.")
WEARY = ("Speak frustrated and weary, fed up with someone's behavior, but clearly, slightly slowly, "
         "with a slightly lower pitch.")
IRRITABLE = ("Speak annoyed and slightly irritable with a sharp tone, but clearly, at a natural pace, "
             "with a natural pitch range.")
DISMISSIVE = ("Speak dismissive and lighthearted, writing something off as unimportant, but clearly, "
              "slightly slowly, with a slightly lower pitch.")
LAUGHING = ("Speak laughing affectionately at someone dropping their keys, gentle and amused, but "
            "clearly, slightly briskly, with a slightly brighter pitch.")
WRY = ("Speak half-smiling at a bitter joke, dry and quietly amused, but clearly, slightly slowly, "
       "with a slightly lower pitch.")
TEACHING = "Speak warmly, as if teaching someone, but clearly, at a natural pace, with a natural pitch range."


@pytest.mark.parametrize(("heard", "text", "direction", "words"), [
    ("Seek relief from irritation in the throat.", "cough", COUGH, ["irritation", "relief", "throat"]),
    ("I need to congestion relief.", "cough", COUGH, ["relief"]),
    ("to provide more.", "to provide", HOST, ["more"]),
], ids=["the direction read out", "a word of it instead of the text", "a word of it after the text"])
def test_the_three_takes_the_owner_judged_wrong_fire(heard, text, direction, words):
    assert leaked(heard, text, direction, "en") == words


@pytest.mark.parametrize(("heard", "text", "direction", "language"), [
    ("Pfff, bancarse.", "bancarse", WEARY, "es"),
    ("¡Aah! ¡Quejarse!", "quejarse", IRRITABLE, "es"),
    ("Oh, frivolous.", "frivolous", DISMISSIVE, "en"),
    ("Hahaha", "clumsy", LAUGHING, "en"),
    ("Riley.", "wryly", WRY, "en"),
    ("圖書館", "图书馆", TEACHING, "zh"),
], ids=["an exclamation", "two exclamations", "an interjection", "a laugh", "a homophone",
        "traditional characters"])
def test_an_emotional_delivery_or_a_mishearing_does_not(heard, text, direction, language):
    assert leaked(heard, text, direction, language) == []


def test_an_accent_word_counts_though_no_direction_named_it():
    """An accent sent alone is a direction too, and «acento argentino» said aloud is it read out."""
    assert leaked("Acento argentino. Bancarse.", "bancarse", "", "es") == ["acento", "argentino"]


def test_a_word_of_the_direction_that_is_the_text_itself_does_not():
    assert leaked("Warm, warm.", "warm", "Speak warm and generous", "en") == []


class Stub:
    def __init__(self, heard: str) -> None:
        self.said = heard
        self.asked: list[str] = []

    def hear(self, audio: bytes, language: str) -> str:
        self.asked.append(language)
        return self.said


def test_the_check_tells_whisper_the_primary_language_and_applies_the_rule():
    ear = Stub("to provide more.")
    found = hearing.check(ear, b"audio", "en-GB", "to provide", HOST)
    assert ear.asked == ["en"]
    assert found == hearing.Heard(heard="to provide more.", leaked=("more",))
