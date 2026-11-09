"""Listening to a recording before it is kept: what was heard, and whether it said more than its text.

Audio, a language, the text asked for and the direction it was asked in; a transcript back, with the
words of the direction found around the text (`leaked`, the loop rule) and every word found around it
(`added`, the story rule). It knows nothing of whose recording it is, where it is kept or what is done
about it — the binding layer decides that: `services/pronunciations.py` for a loop take and
`services/story_audio.py` for a story passage (`docs/features/pronunciation.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

from acervo.hearing.ear import Transcriber, shared, use
from acervo.hearing.rule import added, leaked

__all__ = ["Heard", "Transcriber", "check", "shared", "use"]


@dataclass(frozen=True)
class Heard:
    heard: str
    leaked: tuple[str, ...]
    added: tuple[str, ...] = ()


def check(transcriber: Transcriber, audio: bytes, language: str, text: str, direction: str) -> Heard:
    """Transcribe `audio` and apply the rule. `language` may be a full tag; Whisper is told its
    primary subtag. Raises whatever the transcriber raises: a check that cannot run is the caller's
    to report."""
    primary = language.split("-")[0].lower()
    heard = transcriber.hear(audio, primary)
    return Heard(heard=heard, leaked=tuple(leaked(heard, text, direction, primary)),
                 added=tuple(added(heard, text, primary)))
