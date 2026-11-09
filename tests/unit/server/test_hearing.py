"""The rules that decide whether a take is recorded again, on the cases that settled them.

Every transcript and direction below is one of `experiments/take-verification/`'s: Whisper's own
words for a stored take, and the director note that take was sent. The owner judged each by ear.
"""

from __future__ import annotations

import pytest

from acervo import hearing
from acervo.hearing.rule import added, by_character, leaked

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


# ── a story passage: anything said outside it ───────────────────────────────
#
# The transcripts are Whisper base's, from `experiments/story-fragments/`: the take the server kept
# on 24 Sep 2026, and the fallback voice reading its direction aloud in Spanish, which `leaked` misses
# because none of its words is the English direction's.

FRAGMENT = "Sin mostrar ningún temor,"
DEFIANT = ("Read this Spanish passage from a short story aloud, as a storyteller would. Calm and resolute, "
           "with a hint of defiance. Do not add, drop, translate or explain any words.")


@pytest.mark.parametrize("heard", [
    "Sin mostrar ningún temor, el joven luchó contra aquellos seres con una gran ferocidad. Se sabía defender con arte.",
    "sin mostrar ningún temor, con un hinto de defiancia.",
    "Sin mostrar ningún temor, con un hinto de defiencia, no digas nada, no hagas ni lucharás.",
    "sin mostrar ningún temor, seguirán con todo.",
], ids=["a sentence of its own", "the direction, in Spanish", "the direction and the template",
        "three words of its own"])
def test_a_story_passage_that_says_more_than_itself_is_caught(heard):
    assert added(heard, FRAGMENT, "es")


def test_the_loop_rule_alone_would_have_let_the_spanish_direction_through():
    assert leaked("sin mostrar ningún temor, con un hinto de defiancia.", FRAGMENT, DEFIANT, "es") == []


@pytest.mark.parametrize(("heard", "text"), [
    ("sin mostrar ningún temor.", FRAGMENT),
    ("Fry pensó que sería genial usar el adhesivo débil de Silver.",
     "Fry pensó que sería genial usar el adhesivo de Silver."),
    ("¡Ay, ay, esto es una estafa!", "«¡Esto es una estafa!»"),
    ("¡Y estoy suena y tafa!", '"¡Esto es una estafa!",'),
], ids=["the passage", "a misheard name", "an exclamation of two words", "a shout Whisper could not follow"])
def test_a_story_passage_said_as_written_is_not(heard, text):
    assert added(heard, text, "es") == []


@pytest.mark.parametrize(("text", "language"), [
    ("図書館に行きました。", "ja"), ("ฉันไปห้องสมุด", "th"), ("图书馆", "zh"), ("圖書館", "yue"),
])
def test_a_script_with_no_spaces_is_compared_by_character_whatever_the_language_is_called(text, language):
    assert by_character(text, language)


@pytest.mark.parametrize(("text", "language"), [
    ("Sin mostrar ningún temor,", "es"), ("Без всякого страха,", "ru"), ("Without any fear,", "en"),
])
def test_a_script_with_spaces_is_compared_by_word(text, language):
    assert not by_character(text, language)


def test_a_japanese_passage_is_caught_saying_its_direction_and_not_for_its_full_stop():
    text = "図書館に行きました"
    assert added("図書館に行きました。", text, "ja") == []
    assert added("図書館に行きました。ゆっくり話してください。", text, "ja")
