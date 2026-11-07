"""Saying one piece of text, over a chain of speech models, in its own language.

Two decisions live here and nowhere else.

**Only a model that speaks the language is asked.** The provider says which languages each model
covers — Aura is English, Google's WaveNet voices exist per language, Gemini's speak anything — and a
pair that cannot say Russian is left out of the walk for Russian rather than asked and refused. When
nothing in the chain can, that is its own answer (`NoVoice`), because "your chain has no Russian
voice" is something the owner can fix and a refusal from the first provider would hide it.

**A direction reaches only a voice that can follow one.** The emotion is sent where the answering
model takes a direction, and the result says whether it was, so the stored clip records
the delivery it actually got rather than the one that was hoped for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from acervo.models import chain, locales
from acervo.models import call as provider
from acervo.models.providers import Providers
from acervo.models.errors import ProviderUnavailable
from acervo.models.results import AudioResult

# Only what a direction needs in order to read naturally ("Say this Spanish sentence…"). An unknown
# tag is used as it is; a voice that takes directions understands `pt-BR` perfectly well.
LANGUAGE_NAMES = {
    "es": "Spanish", "en": "English", "ru": "Russian", "zh": "Mandarin Chinese", "pt": "Portuguese",
    "fr": "French", "de": "German", "it": "Italian", "ja": "Japanese", "ko": "Korean",
}

# Keyed by *use*, not by order: which chain reads a word is the owner's answer and may change, but
# the call log should still say what was being read.
CALLERS = {
    "words": "pronounce-word", "examples": "pronounce-sentence",
    "selection": "pronounce-selection", "loops": "pronounce-take", "stories": "pronounce-story",
    "preview": "pronounce-preview",
}


class NoVoice(Exception):
    """Nothing in the chain speaks this language."""

    def __init__(self, language: str) -> None:
        super().__init__(language)
        self.language = language


@dataclass(frozen=True)
class Spoken:
    result: AudioResult
    # The direction actually sent, or None when there was none or the voice could not take it.
    direction: str | None
    # The voice *asked for*, which is None when the owner chose none and the provider used its own
    # default. What came back is `result.voice`; this is what a take cache keys on, because it is the
    # half that can be known before the call as well as after it.
    asked_voice: str | None = None


def language_name(language: str) -> str:
    """The language a tag names, in English. The table first, for the names a direction has always
    used ("Mandarin Chinese"); CLDR's name for anything else."""
    return LANGUAGE_NAMES.get(language.split("-")[0].lower()) or locales.language_name(language)


def speaker(language: str) -> str:
    """Who a direction asks the voice to sound like: "a native speaker from Argentina" for `es-AR`,
    "a native speaker" for a bare language, where no accent was chosen."""
    region = locales.region_name(locales.parse(language).region)
    return f"a native speaker from {region}" if region else "a native speaker"


def accented(language: str) -> bool:
    """Whether an accent was chosen, which is what makes a direction worth sending on its own."""
    return bool(locales.parse(language).region)


class Direction(str):
    """A direction: the sentence a voice that reads instructions is sent, carrying the short form a
    voice that reads a tag in the words is sent instead (`tag`, or None for nothing).

    Two forms because the two kinds of voice differ in what a direction costs and what it does.
    Heard by the owner on ElevenLabs v4, 7 Nov 2026: the sentence written for Gemini (136-194
    characters, each billed) was read aloud; a short tag, "surprised and amused; accent from
    Argentina", was not, and carried the feeling, and "accent from Argentina" the accent;
    and an accent tag alone made a short text be said twice ("picar, picar"; "la calle amarilla",
    in a very good Argentine accent, twice). So the tag is the note, with the accent where one was
    chosen, and an accent alone sends none.

    A `str` so that everything that reads, logs or keys on the sentence goes on doing so.
    """

    tag: str | None

    def __new__(cls, sentence: str, tag: str | None) -> "Direction":
        made = super().__new__(cls, sentence)
        made.tag = tag
        return made


def carried(sent: str | None, direction: str | None) -> bool:
    """Whether what was sent is this direction, in either of its forms."""
    if not sent or not direction:
        return False
    return sent == direction or sent == getattr(direction, "tag", None)


def direction(template: str, note: str, language: str) -> Direction:
    """The template with its blanks filled. `replace` rather than `format`: a direction is free text.

    Two names for the same blank, because the same thing is written down twice under two names. An
    example's arrives on the record as its `emotion`; a take's arrives from the loop generator as a
    `direction`. Both are a short English phrase saying how a line should be said, and a template
    uses whichever name reads correctly in its own sentence. `{speaker}` carries the accent.
    """
    filled = template.strip().replace("{language}", language_name(language))
    filled = filled.replace("{speaker}", speaker(language))
    region = locales.region_name(locales.parse(language).region)
    filled = filled.replace("{accent}", f"Speak with the accent of {speaker(language)}. " if region else "")
    tag = note.strip() or None
    if tag and region:
        tag = f"{tag}; accent from {region}"
    return Direction(filled.replace("{emotion}", note).replace("{direction}", note), tag)


def asked_of(row, model: str, language: str, style: str | None,
             voice: Callable[[str, str, str], str | None]) -> tuple[str | None, str | None]:
    """What this pair would actually be *sent*: the voice and the direction, after its own limits.

    A voice the model does not declare for that language is dropped rather than sent — one picked for
    WaveNet must not reach Gemini, which would refuse it — and a direction reaches only a model that
    takes one, in the form its family reads (`Direction`).

    One function because it has three callers that must agree exactly: the call itself, and the two
    halves of the take cache. Keying a take on what was *asked for* rather than on what came back is
    what lets the key be computed before the call as well as after it.
    """
    offered = row.voices_for(model, language)
    preferred = voice(row.id, model, language)
    sent = style if style and row.takes_direction(model) else None
    if sent is not None and row.family.audio.get("direction") == "tag":
        sent = getattr(sent, "tag", sent) or None
    return (preferred if preferred and (not offered or preferred in offered) else None, sent)


def speakers(chosen: Sequence[chain.Choice] | None, catalogue: Providers, language: str) -> tuple[chain.Candidate, ...]:
    """The pairs in this chain that can say something in `language`, in order."""
    return tuple(
        candidate for candidate in chain.resolve("audio", chosen, catalogue)
        if candidate.row.speaks(candidate.model, language)
    )


def speak(
    text: str,
    language: str,
    *,
    chosen: Sequence[chain.Choice] | None,
    catalogue: Providers,
    style: str | None = None,
    voice: Callable[[str, str, str], str | None] = lambda provider_id, model, language: None,
    caller: str = "pronounce-word",
    hedge_after: float | None = None,
) -> Spoken:
    """Say `text`, falling through the chain on the usual retryable failures.

    `voice(provider, model, language)` is the owner's choice for a pair, and a name the model does not
    declare for that language is ignored rather than sent — a voice picked for WaveNet must not reach
    Gemini, which would refuse it.
    """
    everyone = chain.resolve("audio", chosen, catalogue)
    if not everyone:
        raise chain.unconfigured("audio", chosen, catalogue)
    able = [candidate for candidate in everyone if candidate.row.speaks(candidate.model, language)]
    if not able:
        raise NoVoice(language)

    def ask(candidate: chain.Candidate) -> AudioResult:
        row, model = candidate.row, candidate.model
        wanted_voice, wanted_style = asked_of(row, model, language, style, voice)
        result = provider.speech(
            text, row=row, model=model, language=language, voice=wanted_voice, style=wanted_style,
        )
        if not result.data:
            raise ProviderUnavailable("empty", "the model returned no audio", provider_id=row.id, model=model)
        return result

    result: AudioResult = chain.walk(
        "audio", [candidate.named for candidate in able], catalogue, ask, chain.stamped,
        caller=caller, hedge_after=hedge_after,
    )
    answered = catalogue.find(result.answer.provider_id)
    asked_voice, sent = asked_of(answered, result.answer.model, language, style, voice)
    return Spoken(result=result, direction=sent, asked_voice=asked_voice)


EXTENSIONS = {"audio/mpeg": "mp3", "audio/wav": "wav", "audio/ogg": "ogg", "audio/flac": "flac"}


def extension_for(mime: str) -> str:
    return EXTENSIONS.get(mime, "bin")
