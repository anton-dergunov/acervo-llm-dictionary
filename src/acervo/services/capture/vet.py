"""Compose's check: judging one model's answer inside the chain, before any draft is built from it.

Run from `llm_json`'s `ask` callback, so a model whose answer fails is passed over and the next pair
in the owner's order answers — rather than the refusal being raised after the walk, where one weak
answer from the head of the chain refused the capture while a stronger model behind it was never
asked. Each rule has one of five dispositions (`docs/features/capture.md`, "Compose's checks"):

- **refuse and demote** where no draft could be built: not an object, no senses, a Chinese entry
  with no reading — the very conditions `draft.refusal_of` holds, read from there so the two cannot
  drift;
- **demote** where the article would be in the wrong language: glosses or notes in a script the
  vocabulary's language is not written in;
- **coerce** where a fallback exists: `primaryGloss` to its first term, an emoji to its first
  grapheme cluster, a domain to lower case;
- **drop the field, keep the record** where the field is decoration: a domain too long or repeated
  between the senses, a word-level `emotion` out of shape;
- **demote softly** where an installed dictionary disagrees: a Mandarin reading, a transcription or a
  noun's gender (`dictionary_check.py`, measured in `experiments/dictionary-checks/`). A dictionary
  can be wrong about a right answer, so this raises `Demoted`: the next pair is asked, and if none
  does better the first demoted answer is kept rather than the capture refused.

All of it but the refusal is the owner's to switch off ("Check what models write"): with checks off,
only what no draft could be built from is refused.

These judge a *model's answer*, not a record, which is why they live here and not in
`domain/validation.py`: a hand-typed article is never refused by them, and nothing in
`web/src/domain.ts` mirrors them. What was coerced or dropped is returned for the call log, never
for the owner's message.
"""

from __future__ import annotations

import copy
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable

import regex

from acervo.domain.validation import GENDER_VALUES
from acervo.pinyin import is_mandarin
from acervo.services.capture.coerce import language_or_none, pick_optional_choice, trimmed
from acervo.services.capture.dictionary_check import (
    attested, gender_verdict, ipa_verdict, reading_verdict, transcription_to_judge, variants,
)
from acervo.services.capture.draft import refusal_of, usable_senses
from acervo.services.dictionaries.lookup import Found
from acervo.services.models import Demoted, Unusable

# A script check is only worth its verdict over enough letters to have a majority: "3D", "TV" or a
# lone CJK character say nothing about what language a field is in.
FEWEST_LETTERS = 3

# A script tag that names a *writing system* of several Unicode scripts. Everything else maps to
# itself: `Cyrl` is Cyrillic, `Grek` Greek, `Deva` Devanagari.
COMPOSITE_SCRIPTS = {
    "Hans": ("Hani",),
    "Hant": ("Hani",),
    "Jpan": ("Hani", "Hira", "Kana"),
    "Kore": ("Hang", "Hani"),
}

DOMAIN_WORDS = 2
EMOTION_WORDS = (3, 12)

# Which classes demote, chosen by the owner on the measured false-alarm rates on stored words
# (`docs/features/capture.md`, "Compose's checks"). Everything else passes.
DEMOTING_READINGS = {"neutral-only", "tone-mismatch", "mismatch"}
DEMOTING_TRANSCRIPTIONS = {"mismatch"}
DEMOTING_GENDERS = {"mismatch"}

_TERM_BREAK = regex.compile(r"[;,/]")
_GRAPHEME = regex.compile(r"\X")
_PICTOGRAPHIC = regex.compile(r"\p{Extended_Pictographic}")
_LETTER = regex.compile(r"\p{L}")


@dataclass(frozen=True)
class Vetted:
    """An answer that passed, as corrected, and the fields corrected on the way — for the call log."""

    answer: dict[str, Any]
    fixed: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


@lru_cache(maxsize=256)
def scripts_of(language: str) -> tuple[str, ...]:
    """The Unicode scripts a language is written in, by its likeliest script, or `()` when unknown."""
    import langcodes

    try:
        script = langcodes.Language.get(language).maximize().script
    except (ValueError, LookupError):
        return ()
    if not script:
        return ()
    return COMPOSITE_SCRIPTS.get(script, (script,))


@lru_cache(maxsize=64)
def _in_script(scripts: tuple[str, ...]) -> regex.Pattern[str]:
    return regex.compile("[" + "".join(rf"\p{{sc={script}}}" for script in scripts) + "]")


def _name_of_script(text: str) -> str:
    """The script most of `text`'s letters are in, by name — for the sentence, not the verdict.

    Read off each letter's Unicode name ("CYRILLIC SMALL LETTER A"), whose first word is its script
    for every alphabet that matters here; the unified ideographs say "CJK", which is Han.
    """
    counts: dict[str, int] = {}
    for letter in _LETTER.findall(text):
        name = unicodedata.name(letter, "").split(" ", 1)[0]
        name = "Han" if name == "CJK" else name.title() or "another"
        counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.__getitem__) if counts else "another"


def _language_name(language: str) -> str:
    import langcodes

    try:
        return langcodes.Language.get(language).display_name("en")
    except (ValueError, LookupError):
        return language


def wrong_script(text: str, language: str | None) -> str | None:
    """The name of the script `text` is mostly in when that is not `language`'s, else `None`.

    A proxy for "is this in the right language", not a language identifier — but it is the part of
    the rule that can be checked mechanically, and it catches the measured failure: an English gloss
    for a word the vocabulary glosses into Russian first. Two languages written in one script are
    never told apart here, so a vocabulary glossing Spanish into English is never demoted by it.
    """
    scripts = scripts_of(language) if language else ()
    if not scripts:
        return None
    letters = _LETTER.findall(text)
    if len(letters) < FEWEST_LETTERS:
        return None
    pattern = _in_script(scripts)
    if sum(1 for letter in letters if pattern.match(letter)) * 2 >= len(letters):
        return None
    return _name_of_script(text)


def first_term(value: str) -> str:
    return _TERM_BREAK.split(value, 1)[0].strip()


def first_grapheme(value: str) -> str:
    found = _GRAPHEME.match(value)
    return found.group(0) if found else value


def _fold(value: Any) -> str:
    return " ".join(trimmed(value).casefold().split())


def _without(text: str, quoted: list[str]) -> str:
    """`text` with the word itself taken out: notes quote the headword, in its own script."""
    for item in sorted({item for item in quoted if item}, key=len, reverse=True):
        text = text.replace(item, " ")
    return text


def _holding(found: list[Found], value: str | None, which: int) -> str:
    """The first dictionary whose articles give `value` — a reading (`which` 0) or a transcription
    (1), one of whose variants it may be — so a sentence names the dictionary that disagreed."""
    for item in found:
        for held in attested(item.articles)[which]:
            if held == value or (which == 1 and value in variants(held)):
                return item.dictionary_id
    return found[0].dictionary_id if found else "the dictionary"


def disagreement(answer: dict[str, Any], resolution: dict[str, Any], found: list[Found]) -> str | None:
    """The sentence for the first installed dictionary that disagrees with the answer, or `None`.

    A reading is compared only for Mandarin, the language whose readings are Pinyin; its `ipa` is
    derived from the reading (`draft.py`), so it is not compared. A transcription is compared only
    against an entry of the same form (`transcription_to_judge`).
    """
    if not found:
        return None
    headword = trimmed(resolution.get("headword"))
    language = str(resolution.get("language") or "")
    readings, _, genders = ([value for item in found for value in attested(item.articles)[index]]
                            for index in range(3))

    reading = trimmed(answer.get("reading"))
    if is_mandarin(language) and reading:
        verdict = reading_verdict(reading, readings)
        if verdict.kind in DEMOTING_READINGS:
            return (f"{_holding(found, verdict.nearest, 0)} reads {headword} as {verdict.nearest}; "
                    f"the model wrote {reading}")

    ipa = trimmed(answer.get("ipa"))
    if not is_mandarin(language) and ipa:
        judged = transcription_to_judge(headword, ipa, found)
        if judged is not None:
            part, ipas = judged
            verdict = ipa_verdict(part, ipas)
            if verdict.kind in DEMOTING_TRANSCRIPTIONS:
                return (f"{_holding(found, verdict.nearest, 1)} reads {headword} as {verdict.nearest}; "
                        f"the model wrote {part}")

    gender = pick_optional_choice(answer.get("gender"), GENDER_VALUES)
    verdict = gender_verdict(gender, genders)
    if verdict.kind in DEMOTING_GENDERS:
        holder = next((item.dictionary_id for item in found if attested(item.articles)[2]), "")
        return f"{holder} has {headword} as {verdict.nearest}; the model wrote {gender}"
    return None


def vet(vocabulary: dict[str, Any], resolution: dict[str, Any], found: list[Found] | None = None,
        checking: bool = True) -> Callable[[Any], Vetted]:
    """The check compose passes to `llm_json`, for one word in one vocabulary.

    `found` is what the installed dictionaries hold for the word (`lookup.articles_for`), fetched once
    by the caller so this stays pure. `checking` is the owner's "Check what models write": off, only
    an answer no draft could be built from is refused, and nothing is corrected.

    Pure, and called once per pair on that pair's own reply: raced pairs each check their own.
    """
    gloss_langs = vocabulary.get("glossLangs") or []
    gloss_lang = gloss_langs[0] if gloss_langs else None
    notes_lang = vocabulary.get("notesLang") or gloss_lang
    entries = found or []

    def check(parsed: Any) -> Vetted:
        refused = refusal_of(parsed, resolution)
        if refused is not None:
            raise Unusable(refused.message, refusal=refused)
        answer: dict[str, Any] = copy.deepcopy(parsed)
        if not checking:
            return Vetted(answer)
        fixed: list[str] = []
        dropped: list[str] = []
        senses = usable_senses(answer)

        # ── demote: the wrong language, read by its script ──────────────────
        glossed = [trimmed(answer.get("primaryGloss")), trimmed(answer.get("shortGloss"))]
        for sense in senses:
            glossed.append(trimmed(sense.get("domain")))
            for gloss in sense.get("glosses") or []:
                if isinstance(gloss, dict) and language_or_none(gloss.get("lang")) == gloss_lang:
                    glossed.extend(trimmed(term) for term in gloss.get("terms") or [])
        found = wrong_script(" ".join(glossed), gloss_lang)
        if found:
            raise Unusable(f"the glosses are in {found} script, and the vocabulary glosses into "
                           f"{_language_name(gloss_lang or '')} first")

        noted = [trimmed(note) for note in answer.get("notes") or []] if isinstance(
            answer.get("notes"), list) else []
        for sense in senses:
            for example in sense.get("examples") or []:
                if isinstance(example, dict):
                    noted.append(trimmed(example.get("note")))
        word = [resolution.get("headword"), resolution.get("lemma"), trimmed(answer.get("headword")),
                trimmed(answer.get("lemma")), trimmed(answer.get("reading"))]
        found = wrong_script(_without(" ".join(noted), [trimmed(item) for item in word]), notes_lang)
        if found:
            raise Unusable(f"the notes are in {found} script, and the vocabulary writes its notes in "
                           f"{_language_name(notes_lang or '')}")

        # ── coerce: one term, one emoji ─────────────────────────────────────
        primary = trimmed(answer.get("primaryGloss"))
        if primary and first_term(primary) != primary:
            answer["primaryGloss"] = first_term(primary) or None
            fixed.append("primaryGloss")
        for holder, name in [(answer, "emoji"), *((sense, "sense.emoji") for sense in senses)]:
            emoji = trimmed(holder.get("emoji"))
            if emoji and first_grapheme(emoji) != emoji:
                holder["emoji"] = first_grapheme(emoji)
                fixed.append(name)

        # ── drop the field, keep the record ─────────────────────────────────
        seen: set[str] = set()
        for sense in senses:
            domain = trimmed(sense.get("domain"))
            if not domain:
                continue
            lowered = " ".join(domain.lower().split())
            if lowered != domain:
                sense["domain"] = lowered
                fixed.append("domain")
            if len(lowered.split()) > DOMAIN_WORDS or lowered in seen:
                sense["domain"] = None
                dropped.append("domain")
            seen.add(lowered)

        emotion = trimmed(answer.get("emotion"))
        if emotion:
            words = len(emotion.split())
            spoken = {_fold(example.get("emotion")) for sense in senses
                      for example in sense.get("examples") or [] if isinstance(example, dict)}
            if not EMOTION_WORDS[0] <= words <= EMOTION_WORDS[1] or _PICTOGRAPHIC.search(emotion) \
                    or _fold(emotion) in spoken:
                answer["emotion"] = None
                dropped.append("emotion")

        # ── demote softly: an installed dictionary disagrees ────────────────
        doubted = disagreement(answer, resolution, entries)
        if doubted:
            raise Demoted(doubted, Vetted(answer, fixed, dropped), by="dictionary")

        return Vetted(answer, fixed, dropped)

    return check
