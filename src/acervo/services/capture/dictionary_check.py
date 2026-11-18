"""How far a model's `reading`, `ipa` and `gender` are from what an installed dictionary attests.

Pure comparisons, sorted into named classes rather than a yes or no, because a dictionary can
disagree with a right answer: 东西 is `dōngxi` (thing) and `dōngxī` (east and west), and a
transcription may be in another variety than the one the dictionary lists first. Which classes demote
a model is decided by measuring them on stored words (`experiments/dictionary-checks/`); the classes
themselves are written once, here, so the measurement measures what the check uses.

Nothing names a language. A reading is compared where it reads as Pinyin syllables on both sides;
a transcription is compared phone by phone with IPA's own letters; a gender against the dictionary's
genders.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from acervo.pinyin import Syllable, pinyin_syllables, unmark

# ── readings ─────────────────────────────────────────────────────────────────────────────────────

#: Best first. `neutral-only`: the two differ only where one side has the neutral tone. `sandhi-only`:
#: only where the citation tone and the spoken one differ by a rule (一 and 不 before a fourth or
#: other tone, a third tone before a third), possibly with neutral-tone differences beside.
READING_CLASSES = ("match", "neutral-only", "sandhi-only", "tone-mismatch", "mismatch")

# 一 and 不 change tone before another syllable; the dictionary writes the citation tone.
_SANDHI_SYLLABLES = {"yi": {1, 2, 4}, "bu": {2, 4}}


@dataclass(frozen=True)
class Verdict:
    """A comparison's class, and the dictionary's value the model's came nearest, for the sentence."""

    kind: str
    nearest: str | None = None


def _bare(syllable: Syllable) -> str:
    return unmark(syllable.text)[0].lower()


def _reading_class(model: list[Syllable], attested: list[Syllable]) -> str:
    if len(model) != len(attested) or any(_bare(a) != _bare(b) for a, b in zip(model, attested)):
        return "mismatch"
    differing = [index for index, (a, b) in enumerate(zip(model, attested)) if a.tone != b.tone]
    if not differing:
        return "match"
    if all(5 in (model[index].tone, attested[index].tone) for index in differing):
        return "neutral-only"

    def sandhi(index: int) -> bool:
        said, written = model[index].tone, attested[index].tone
        if 5 in (said, written):
            return True
        tones = _SANDHI_SYLLABLES.get(_bare(attested[index]))
        if tones and index + 1 < len(attested) and {said, written} <= tones:
            return True
        following = attested[index + 1].tone if index + 1 < len(attested) else None
        return written == 3 and said == 2 and following == 3

    return "sandhi-only" if all(sandhi(index) for index in differing) else "tone-mismatch"


def reading_verdict(model: str | None, attested: Iterable[str]) -> Verdict:
    """`no-entry` when no dictionary reading reads as Pinyin, `unparsed` when the model's does not."""
    readings = [(reading, pinyin_syllables(reading)) for reading in attested if reading]
    readings = [(reading, syllables) for reading, syllables in readings if syllables]
    if not readings:
        return Verdict("no-entry")
    said = pinyin_syllables(model or "")
    if not said:
        return Verdict("unparsed")
    ranked = sorted(((READING_CLASSES.index(_reading_class(said, syllables)), reading)
                     for reading, syllables in readings), key=lambda item: item[0])
    return Verdict(READING_CLASSES[ranked[0][0]], ranked[0][1])


# ── transcriptions ───────────────────────────────────────────────────────────────────────────────

#: Best first. `stress-only`: the same phones, stress or length marked differently. `vowels-agree`:
#: the same vowels in the same order and the same stressed vowel, consonants aside — where varieties
#: of one language mostly differ (θ/s, ʝ/ʎ/ʃ) and where the measured `/ˈaska/` does not. `close`: a
#: phone error rate of at most `CLOSE_PER` against the dictionary's.
IPA_CLASSES = ("match", "stress-only", "vowels-agree", "close", "mismatch")
CLOSE_PER = 0.2

_DELIMITERS = set("/[]‿. ͜͡")
_STRESS = set("ˈˌ'")
_LENGTH = set("ːˑ")
_VOWELS = set("iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒᵻᵿ")
#: One sound written two ways, by convention rather than by what is heard: ASCII `g` for `ɡ`, `r`
#: for the approximant `ɹ` in a broad transcription, the hooked `ɚ` for `ər`. Syllabicity and
#: non-syllabicity marks (`l̩`, `eɪ̯`) are a transcriber's choice of detail, and dropped.
_SPELLED = {"g": "ɡ", ":": "ː", "ɹ": "r", "ɚ": "ər", "ɝ": "ɜr", "̯": "", "̩": "", "̍": ""}
_OPTIONAL = re.compile(r"\(([^()]*)\)")
_MOST_VARIANTS = 16


def phones(transcription: str) -> list[tuple[str, bool]]:
    """`(phone, stressed)` per phone: a letter with its combining marks and modifier letters.

    Delimiters and syllable dots are dropped; a stress mark sets `stressed` on the phone after it;
    length is kept on the phone, so `stress-only` can set it aside.
    """
    found: list[tuple[str, bool]] = []
    stressed = False
    spelled = "".join(_SPELLED.get(character, character)
                      for character in unicodedata.normalize("NFD", transcription.strip()))
    for character in spelled:
        if character in _DELIMITERS or character in "()":
            continue
        if character in _STRESS:
            stressed = True
            continue
        if found and (unicodedata.combining(character) or unicodedata.category(character) == "Lm"
                      or character in _LENGTH):
            found[-1] = (found[-1][0] + character, found[-1][1])
            continue
        found.append((character, stressed))
        stressed = False
    return found


def _edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def _vowels(sequence: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    return [(phone[0], stressed) for phone, stressed in sequence if phone[0] in _VOWELS]


def variants(transcription: str) -> list[str]:
    """The transcriptions one string stands for: a list split at its commas, and each optional
    sound in parentheses both said and left out (`/ˈblɪsf(ə)l/` is `/ˈblɪsfəl/` and `/ˈblɪsfl/`)."""
    expanded: list[str] = []
    for part in transcription.split(","):
        pending = [part.strip()]
        while pending and len(expanded) < _MOST_VARIANTS:
            item = pending.pop(0)
            optional = _OPTIONAL.search(item)
            if optional is None:
                if item and item not in expanded:
                    expanded.append(item)
                continue
            pending += [item[:optional.start()] + optional.group(1) + item[optional.end():],
                        item[:optional.start()] + item[optional.end():]]
    return expanded


def per(model: str, attested: str) -> float:
    """Phone error rate: edits from the dictionary's phones to the model's, over the dictionary's count."""
    reference = [phone for phone, _ in phones(attested)]
    said = [phone for phone, _ in phones(model)]
    return _edit_distance(reference, said) / max(len(reference), 1)


def _ipa_class(model: str, attested: str) -> str:
    said, reference = phones(model), phones(attested)
    if said == reference:
        return "match"
    strip = lambda sequence: ["".join(c for c in phone if c not in _LENGTH) for phone, _ in sequence]
    if strip(said) == strip(reference):
        return "stress-only"
    said_vowels, reference_vowels = _vowels(said), _vowels(reference)
    marked = any(stressed for _, stressed in said_vowels) and any(stressed for _, stressed in reference_vowels)
    if [v for v, _ in said_vowels] == [v for v, _ in reference_vowels] and reference_vowels and (
            not marked or said_vowels == reference_vowels):
        return "vowels-agree"
    if per(model, attested) <= CLOSE_PER:
        return "close"
    return "mismatch"


def ipa_verdict(model: str | None, attested: list[str], first_only: bool = False) -> Verdict:
    """The best class over the dictionary's transcriptions (or only its first), or `no-entry`."""
    listed = [item for item in attested if item and phones(item)]
    if first_only:
        listed = listed[:1]
    candidates = [variant for item in listed for variant in variants(item) if phones(variant)]
    if not candidates:
        return Verdict("no-entry")
    if not (model or "").strip():
        return Verdict("model-none")
    ranked = sorted(((IPA_CLASSES.index(_ipa_class(model or "", item)), per(model or "", item), item)
                     for item in candidates), key=lambda item: (item[0], item[1]))
    return Verdict(IPA_CLASSES[ranked[0][0]], ranked[0][2])


# ── gender ───────────────────────────────────────────────────────────────────────────────────────

def gender_verdict(model: str | None, attested: list[str]) -> Verdict:
    genders = [item for item in attested if item]
    if not genders:
        return Verdict("no-entry")
    if not model:
        return Verdict("model-none", " / ".join(genders))
    # A noun of common gender is one a dictionary may list as both masculine and feminine.
    either = model == "common" and {"masculine", "feminine"} <= set(genders)
    return Verdict("match" if model in genders or either else "mismatch", " / ".join(genders))


# ── which word to look up, and which part of a transcription it answers for ─────────────────────

def keys_for(headword: str, lemma: str) -> list[str]:
    """What to look a word up under, in order: the headword, then the headword without its first word
    (`el asco`, `se va`: a dictionary files nothing under the article or pronoun), then the lemma.
    Never a phrase's last word alone: `roja` says nothing about `la bandera roja`."""
    words = headword.split()
    keys = [headword.strip(), " ".join(words[1:]), lemma]
    return list(dict.fromkeys(key for key in keys if key))


def transcription_to_judge(headword: str, model_ipa: str | None,
                           found: Iterable[Any]) -> tuple[str, list[str]] | None:
    """The part of the model's transcription a dictionary entry answers for, and the entry's ones.

    Only an entry found under the headword or its last words is the same form as what the model
    transcribed; one found under the lemma (`asustar` for `asustado`, `apunte` for `los apuntes`) is
    another word's sound and is not compared. When the headword's last words were the key, the
    transcription is compared whole if it has as many words as the key, and by its same number of
    last words if it has one word per headword word.
    """
    words = headword.split()
    spoken = (model_ipa or "").strip().strip("/[]").split()
    attested_ipas: list[str] = []
    part: str | None = None
    for item in found:
        key_words = item.key.split()
        if not key_words or words[len(words) - len(key_words):] != key_words:
            continue
        if len(key_words) == len(words) or len(spoken) == len(key_words):
            candidate = (model_ipa or "").strip()   # `el asco` is often transcribed `/ˈasko/` alone
        elif len(spoken) == len(words):
            candidate = " ".join(spoken[len(spoken) - len(key_words):])
        else:
            continue
        if part not in (None, candidate):
            continue  # a longer key was found by an earlier dictionary; compare that one only
        part = candidate
        attested_ipas += [value for value in attested(item.articles)[1] if value not in attested_ipas]
    return (part, attested_ipas) if part is not None and attested_ipas else None


# ── reading what the dictionaries hold ──────────────────────────────────────────────────────────

def attested(articles: Iterable[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    """Every reading, transcription and gender a word's dictionary articles give, without repeats."""
    readings: list[str] = []
    transcriptions: list[str] = []
    genders: list[str] = []
    for article in articles:
        for target, values in ((readings, [article.get("reading")]),
                               (transcriptions, article.get("ipas") or [article.get("ipa")]),
                               (genders, article.get("genders") or [])):
            for value in values:
                if isinstance(value, str) and value.strip() and value not in target:
                    target.append(value)
    return readings, transcriptions, genders
