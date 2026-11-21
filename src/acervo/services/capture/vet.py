"""Compose's check: judging one model's answer inside the chain, before any draft is built from it.

Run from `llm_json`'s `ask` callback, so a model whose answer fails is passed over and the next pair
in the owner's order answers — rather than the refusal being raised after the walk, where one weak
answer from the head of the chain refused the capture while a stronger model behind it was never
asked. Each rule has one of five dispositions (`docs/features/capture.md`, "Compose's checks"):

- **refuse and demote** where no draft could be built: not an object, no senses, a Chinese entry
  with no reading — the very conditions `draft.refusal_of` holds, read from there so the two cannot
  drift;
- **demote** where the article would be in the wrong language: glosses, notes or a definition in a
  script the vocabulary's language is not written in;
- **coerce** where a fallback exists: `primaryGloss` to its first term, an emoji to its first
  grapheme cluster, a domain to lower case;
- **drop the field, keep the record** where the field is decoration: a domain too long or repeated
  between the senses, a word-level `emotion` out of shape;
- **demote softly** where a judge that can be wrong doubts the answer: a definition a language
  identifier reads as another of the vocabulary's languages written in the same script
  (`definition_doubt`, measured in `experiments/definition-language/`), or an installed dictionary
  disagreeing with a Mandarin reading, a transcription or a noun's gender (`dictionary_check.py`,
  measured in `experiments/dictionary-checks/`). This raises `Demoted`: the next pair is asked, and
  if none does better the first demoted answer is kept rather than the capture refused.

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

from acervo.domain.validation import GENDER_VALUES, POS_VALUES
from acervo.grammatical_gender import gender_for
from acervo.pinyin import is_mandarin
from acervo.services.capture.coerce import language_or_none, pick_choice, pick_optional_choice, trimmed
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

# The parts of speech a gender belongs to: a noun, or a phrase or idiom standing for one
# (`el día de la madre`). An adjective agrees with its noun and has none of its own.
GENDERED_POS = ("noun", "phrase", "idiom")

# How sure the language identifier must be that a definition is in another of the vocabulary's
# languages before it doubts it. Measured on 5,763 Latin-script starter definitions and 1,467 of the
# owner's Spanish ones (`experiments/definition-language/`): English read as Italian or French reached
# 0.64 on four-word definitions, and of the 110 read between 0.5 and 0.95, every one at 0.7 or more
# was in another language.
DEFINITION_CONFIDENCE = 0.7

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


_WORD = regex.compile(r"[\p{L}\p{M}]+")

# Scripts one word may legitimately mix: Japanese writes kanji, kana and Latin letters in one word
# (`Tシャツ`, `時々`), Chinese a Latin letter in a few (`T恤衫`), Korean Hangul with hanja.
MIXABLE = (frozenset({"Han", "Kana", "Latin"}), frozenset({"Hangul", "Han"}))


def _script_of_letter(letter: str) -> str | None:
    """A letter's script by its Unicode name ("GREEK SMALL LETTER PI" → Greek), as `_name_of_script`
    reads it; the ideographs and their marks are Han, both kana are Kana, modifier letters none."""
    words = unicodedata.name(letter, "").split(" ")
    if words[0] in ("FULLWIDTH", "HALFWIDTH") and len(words) > 1:
        words = words[1:]
    head = words[0]
    if not head or head == "MODIFIER":
        return None
    if head in ("CJK", "IDEOGRAPHIC"):
        return "Han"
    if head in ("HIRAGANA", "KATAKANA", "KATAKANA-HIRAGANA"):
        return "Kana"
    return head.title()


def garbled(text: str) -> str | None:
    """The first word of `text` written in two scripts, or `None`.

    The measured failure (`experiments/compose-audit/`): 3.5 Flash-Lite wrote Greek with Latin letters
    inside the words (`σπίti`, `Λαtrεύω`) in a fifth of its Greek articles, and Thai, Hindi and Dutch
    the same less often. No language writes a word that way, so nothing needs to be measured to know
    it is wrong; only the mixes in `MIXABLE` are real.
    """
    for word in _WORD.findall(text or ""):
        scripts = {_script_of_letter(letter) for letter in word if letter.isalpha()} - {None}
        if len(scripts) > 1 and not any(scripts <= allowed for allowed in MIXABLE):
            return word
    return None


# A Russian stress mark typed as a Latin accented vowel (`писáть`): the Cyrillic vowel and U+0301.
_CYRILLIC_STRESS = {"á": "а́", "é": "е́", "ó": "о́", "ý": "у́"}
_IN_CYRILLIC = regex.compile(r"[\p{sc=Cyrillic}\p{M}]*[áéóý][\p{sc=Cyrillic}\p{M}áéóý]*")


def restressed(text: str) -> str:
    """`text` with a stressed vowel inside a Cyrillic word written as Cyrillic plus the acute mark."""
    def fix(found: regex.Match[str]) -> str:
        word = found.group(0)
        if not regex.search(r"\p{sc=Cyrillic}", word):
            return word
        return "".join(_CYRILLIC_STRESS.get(letter, letter) for letter in word)
    return _IN_CYRILLIC.sub(fix, text)


_KANA = regex.compile(r"[\p{sc=Hiragana}\p{sc=Katakana}ー]+")
_HAN = regex.compile(r"\p{sc=Han}")


def reading_for(language: str | None, headword: str, reading: str | None) -> str | None:
    """The `reading` a word of `language` keeps (`docs/features/articles.md`, "Readings").

    Chinese keeps its own (Pinyin, checked elsewhere). Japanese keeps the whole word in hiragana, and
    only when the headword has a kanji for it to read; a reading in romaji says nothing a learner can
    line up with the kanji. Every other language has no reading yet
    (`docs/plans/languages/readings.md`): what models wrote there was half a dozen romanisations,
    some with tone marks the language does not have.
    """
    value = trimmed(reading)
    if not value:
        return None
    base = (language or "").split("-", 1)[0].lower()
    if base == "zh":
        return value
    if base != "ja" or not _HAN.search(headword):
        return None
    joined = "".join(value.split())
    if not _KANA.fullmatch(joined):
        return None
    return "".join(chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char for char in joined)


def ipa_of_lemma(headword: str, lemma: str, ipa: str | None) -> str | None:
    """`ipa` without the article's transcription when the headword is the article and the lemma
    (`der Stern` → `/ʃtɛʁn/`): the prompt's own example transcribes `el disfraz` as the lemma only."""
    value = trimmed(ipa)
    words, lemma_words = headword.split(), lemma.split()
    if not value or len(words) != len(lemma_words) + 1 or words[1:] != lemma_words:
        return value or None
    opening, closing = value[:1], value[-1:]
    delimited = opening in "/[" and closing in "/]"
    spoken = (value[1:-1] if delimited else value).split()
    if len(spoken) != len(words):
        return value
    rest = " ".join(spoken[1:])
    return f"{opening}{rest}{closing}" if delimited else rest


def _base(language: str | None) -> str | None:
    """`zh-Hans` → `zh`: the language a language identifier can name, or `None`."""
    import langcodes

    try:
        return langcodes.Language.get(language).language if language else None
    except (ValueError, LookupError):
        return None


@lru_cache(maxsize=64)
def _detector(languages: tuple[str, ...]) -> Any:
    """A lingua detector that chooses among exactly these languages, or `None` if it knows < two.

    Built per set of languages, not over every language lingua knows: asked among dozens, a short
    English definition spreads its confidence so thin that nothing can be read from it, and the
    detector's models for every Latin-script language cost the server ~230 MB.
    """
    from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

    known = []
    for code in languages:
        try:
            known.append(Language.from_iso_code_639_1(getattr(IsoCode639_1, code.upper())))
        except (AttributeError, ValueError):
            continue
    return LanguageDetectorBuilder.from_languages(*known).build() if len(known) >= 2 else None


def definition_doubt(definition: str, vocabulary: dict[str, Any], resolution: dict[str, Any],
                     quoted: list[str] | None = None) -> tuple[str, bool] | None:
    """Why one definition is not in the vocabulary's `definitionLang`, and whether that is certain.

    `(sentence, True)` when it is in another script than `definitionLang`'s: certain, and the answer
    is passed over. `(sentence, False)` when a language identifier, choosing only among the
    vocabulary's own languages that share that script (the word's, the definitions', the first
    gloss language, the notes'), finds another with at least `DEFINITION_CONFIDENCE`: a doubt. The
    measured failure is a definition in the word's own language for a vocabulary that defines in
    the learner's (`experiments/definition-language/`). `quoted` is the word itself, taken out first.
    """
    target = vocabulary.get("definitionLang")
    text = _without(trimmed(definition), [item for item in quoted or [] if item])
    script = wrong_script(text, target)
    if script:
        return (f"the definitions are in {script} script, and the vocabulary defines its senses in "
                f"{_language_name(target or '')}"), True
    base = _base(target)
    if base is None:
        return None
    gloss_langs = vocabulary.get("glossLangs") or []
    candidates = {_base(item) for item in (resolution.get("language"), *gloss_langs[:1], vocabulary.get("notesLang"))}
    others = sorted(item for item in candidates - {None, base} if scripts_of(item) == scripts_of(base))
    if not others or len(_LETTER.findall(text)) < FEWEST_LETTERS:
        return None
    detector = _detector((base, *others))
    if detector is None:
        return None
    confidence = {value.language.iso_code_639_1.name.lower(): value.value
                  for value in detector.compute_language_confidence_values(text)}
    other = max(others, key=lambda item: confidence.get(item, 0.0))
    if confidence.get(other, 0.0) < DEFINITION_CONFIDENCE:
        return None
    headword = trimmed(resolution.get("headword"))
    return (f"a definition of {headword} reads as {_language_name(other)}, and the vocabulary defines "
            f"its senses in {_language_name(target or '')}"), False


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


def _written(answer: dict[str, Any], senses: list[dict[str, Any]]):
    """Every prose field of an answer, with what it is called in a sentence."""
    yield "the headword", trimmed(answer.get("headword"))
    notes = answer.get("notes")
    for note in notes if isinstance(notes, list) else []:
        yield "a note", trimmed(note)
    for sense in senses:
        yield "a definition", trimmed(sense.get("definition"))
        for gloss in sense.get("glosses") or []:
            if isinstance(gloss, dict):
                for term in gloss.get("terms") or []:
                    yield "a gloss", trimmed(term)
        for example in sense.get("examples") or []:
            if isinstance(example, dict):
                yield "an example", trimmed(example.get("text"))
                yield "an example's translation", trimmed(example.get("translation"))
                yield "an example's note", trimmed(example.get("note"))


def _restress_all(answer: dict[str, Any], senses: list[dict[str, Any]]) -> bool:
    """Apply `restressed` to the notes, definitions and examples; whether anything changed."""
    changed = False

    def fix(holder: Any, key: Any) -> None:
        nonlocal changed
        value = holder[key]
        if isinstance(value, str):
            fixed = restressed(value)
            if fixed != value:
                holder[key] = fixed
                changed = True

    if isinstance(answer.get("notes"), list):
        for index in range(len(answer["notes"])):
            fix(answer["notes"], index)
    for sense in senses:
        if "definition" in sense:
            fix(sense, "definition")
        for example in sense.get("examples") or []:
            if isinstance(example, dict):
                for key in ("text", "note"):
                    if key in example:
                        fix(example, key)
    return changed


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

        # ── demote: a definition in another language than `definitionLang` ──
        quoted = [trimmed(item) for item in word]
        misdefined: str | None = None
        for sense in senses:
            doubt = definition_doubt(sense.get("definition"), vocabulary, resolution, quoted)
            if doubt and doubt[1]:
                raise Unusable(doubt[0])
            misdefined = misdefined or (doubt[0] if doubt else None)

        # ── coerce: the headword resolve settled, a stress mark typed in Latin ─
        settled = trimmed(resolution.get("headword"))
        written = trimmed(answer.get("headword"))
        if settled and written and unicodedata.normalize("NFC", " ".join(written.split())) != \
                unicodedata.normalize("NFC", settled):
            answer["headword"] = settled  # resolve chose it; compose rewrote it into another script
            fixed.append("headword")
        if _restress_all(answer, senses):
            fixed.append("stress")

        # ── demote: a word in two scripts, an example in another script ─────
        for where, text in _written(answer, senses):
            word = garbled(text)
            if word:
                raise Unusable(f"{where} has {word!r}, a word written in two scripts")
        language = str(resolution.get("language") or "")
        for sense in senses:
            for example in sense.get("examples") or []:
                if not isinstance(example, dict):
                    continue
                script = wrong_script(trimmed(example.get("text")), language)
                if script:
                    raise Unusable(f"an example is in {script} script, and "
                                   f"{settled or 'the word'} is {_language_name(language)}")

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

        # ── coerce: reading, transcription and gender as the language has them ─
        headword = trimmed(answer.get("headword")) or settled
        lemma = trimmed(answer.get("lemma")) or trimmed(resolution.get("lemma")) or headword
        if trimmed(answer.get("reading")):
            reading = reading_for(language, headword, answer.get("reading"))
            if reading != trimmed(answer.get("reading")):
                answer["reading"] = reading
                (fixed if reading else dropped).append("reading")
        if trimmed(answer.get("ipa")) and not is_mandarin(language):
            ipa = ipa_of_lemma(headword, lemma, answer.get("ipa"))
            if ipa != trimmed(answer.get("ipa")):
                answer["ipa"] = ipa
                fixed.append("ipa")
        gender = pick_optional_choice(answer.get("gender"), GENDER_VALUES)
        if gender:
            pos = pick_choice(answer.get("pos"), POS_VALUES, resolution.get("pos"))
            kept = gender_for(language, gender) if pos is None or pos in GENDERED_POS else None
            if kept != gender:
                answer["gender"] = kept
                (fixed if kept else dropped).append("gender")

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

        # ── demote softly: the language identifier or a dictionary doubts it ─
        if misdefined:
            raise Demoted(misdefined, Vetted(answer, fixed, dropped), by="language")
        doubted = disagreement(answer, resolution, entries)
        if doubted:
            raise Demoted(doubted, Vetted(answer, fixed, dropped), by="dictionary")

        return Vetted(answer, fixed, dropped)

    return check
