"""The narration call: split one part into passages, and say how each should be read.

A directed voice is asked for one *passage* at a time, and the model that is best at deciding where a
passage ends is a text model, not a rule. So a part goes through one cold call that returns its own
text cut into segments, each with a short direction — and **the model is never trusted with the
words**. `tile` finds every segment it returned inside the original, in order, and anything it left
out, changed or reworded stays in the story as a segment with no direction. What is spoken is
therefore always exactly what is written, and a segment's place in the text is nothing more than the
lengths of the segments before it.

Cold, for `translate.py`'s reason: this is copying with judgement, not writing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from acervo.models import call, chain
from acervo.models.providers import Providers
from acervo.models.errors import ProviderUnavailable

NARRATE_PARAMS: Mapping[str, Any] = {"temperature": 0.2}

# A part is two to four sentences. More than this many passages is a model that has cut it into
# phrases, and every one is a paid call and an audible seam.
MAX_SEGMENTS = 16
# What `pronunciations.emotion` can hold, which is where a direction that was sent is recorded.
MAX_DIRECTION = 200

_WORD = re.compile(r"\w")


@dataclass(frozen=True)
class Segment:
    text: str
    # The one-line direction for this passage. Empty for a passage the model did not cover, which
    # is read in the voice's own manner.
    direction: str = ""


@dataclass(frozen=True)
class Tiled:
    segments: tuple[Segment, ...]
    # Passages the model returned that could not be found in the text, and stretches of the text
    # it did not return. Both are the model getting the words wrong; the story is unaffected.
    dropped: int
    filled: int


def build_request(*, language_name: str, text: str) -> dict[str, Any]:
    return {"language": language_name, "text": text}


def parse_reply(payload: Any) -> list[Segment]:
    """The passages as the model wrote them. Shape only: whether they are the story's words is
    `tile`'s question, and its answer is never a refusal."""
    if not isinstance(payload, Mapping):
        raise ValueError("the reply is not a JSON object")
    raw = payload.get("segments")
    if not isinstance(raw, list) or not raw:
        raise ValueError("there are no segments")
    if len(raw) > MAX_SEGMENTS:
        raise ValueError(f"{len(raw)} segments is more than a part can hold")
    segments = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ValueError(f"segment {index + 1} is not an object")
        text = str(entry.get("text") or "").strip()
        if not text:
            raise ValueError(f"segment {index + 1} is empty")
        direction = " ".join(str(entry.get("direction") or "").split())[:MAX_DIRECTION]
        segments.append(Segment(text=text, direction=direction))
    return segments


def _pattern(text: str) -> re.Pattern[str]:
    """`text` with any run of whitespace matching any other, because a model that keeps every word
    will still turn a line break into a space."""
    return re.compile(r"\s+".join(re.escape(token) for token in text.split()))


def _spoken(gap: str) -> bool:
    return bool(_WORD.search(gap))


def tile(text: str, returned: Sequence[Segment]) -> Tiled:
    """Cut `text` into segments that join back to exactly `text`.

    Each returned segment is looked for after the end of the last one found. One that is not there
    is dropped — its words are still in the text, and they surface as a gap. A gap with a word in it
    becomes a segment of its own with no direction; a gap with none (a quote mark the model left
    off, the space between two sentences) is glued to a neighbour so it is never sent to a voice on
    its own.
    """
    found: list[tuple[int, int, str]] = []
    cursor = 0
    dropped = 0
    for segment in returned:
        match = _pattern(segment.text).search(text, cursor)
        if match is None:
            dropped += 1
            continue
        found.append((match.start(), match.end(), segment.direction))
        cursor = match.end()

    pieces: list[list[Any]] = []  # [text, direction, is_gap]
    filled = 0
    at = 0
    for start, end, direction in found:
        gap = text[at:start]
        if gap:
            if _spoken(gap):
                pieces.append([gap, "", True])
                filled += 1
            elif pieces:
                pieces[-1][0] += gap
            else:
                pieces.append([gap, "", True])
        pieces.append([text[start:end], direction, False])
        at = end
    tail = text[at:]
    if tail:
        if _spoken(tail):
            pieces.append([tail, "", True])
            filled += 1
        elif pieces:
            pieces[-1][0] += tail
        else:
            pieces.append([tail, "", True])

    # A silent stretch before the first passage was kept as a piece of its own only because there
    # was nothing to glue it to; give it to the passage that follows.
    if len(pieces) > 1 and not _spoken(pieces[0][0]):
        pieces[1][0] = pieces[0][0] + pieces[1][0]
        del pieces[0]

    assert "".join(piece[0] for piece in pieces) == text
    return Tiled(
        segments=tuple(Segment(text=piece[0], direction=piece[1]) for piece in pieces),
        dropped=dropped, filled=filled,
    )


# What one call to a voice may carry. A Gemini voice takes 4,000 bytes of text, and a part is a few
# hundred characters, so this is a guard and not a design: it is here so an unusually long part is
# read in two goes rather than refused by the provider, and it is in bytes because that is the unit
# the provider counts in — accented and CJK text costs more than its length.
LIMIT_BYTES = 3500

_SENTENCE_END = re.compile(r"(?<=[.!?…»”\"])\s+")


def chunks(text: str, limit: int = LIMIT_BYTES) -> tuple[Segment, ...]:
    """`text` as one segment, or several cut at sentence ends when it is too long for one call.

    No direction on any of them: this is the clear voice's path, which reads in its own manner. The
    cuts are made at whitespace after a sentence, and the whitespace stays with the sentence before
    it, so the pieces join back to `text` exactly like `tile`'s do.
    """
    if len(text.encode("utf-8")) <= limit:
        return (Segment(text=text),)
    pieces: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        pieces.append(text[start:match.end()])
        start = match.end()
    pieces.append(text[start:])
    packed: list[str] = []
    for piece in pieces:
        if packed and len((packed[-1] + piece).encode("utf-8")) <= limit:
            packed[-1] += piece
        else:
            packed.append(piece)
    return tuple(Segment(text=one) for one in packed)


class Narrator:
    def __init__(self, catalogue: Providers, candidates: Sequence[chain.Candidate], template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def segment(self, request: Mapping[str, Any]) -> tuple[Tiled, dict[str, Any]]:
        text = str(request["text"])
        prompt = f"{self.template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"

        def ask(candidate: chain.Candidate) -> call.TextResult:
            result = call.text(
                prompt, row=candidate.row, model=candidate.model, as_json=True,
                params=NARRATE_PARAMS,
            )
            if not result.text.strip():
                raise ProviderUnavailable("empty", "the model returned nothing",
                                          provider_id=candidate.row.id, model=candidate.model)
            try:
                parse_reply(result.parsed)
            except ValueError as error:
                raise ProviderUnavailable(
                    "unusable", f"the segments did not hold their shape: {error}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return result

        answered = chain.walk(
            "text", [c.named for c in self.candidates], self.catalogue, ask, chain.stamped,
            caller="story.narrate",
        )
        return tile(text, parse_reply(answered.parsed)), {
            "provider": answered.answer.provider_id,
            "model": answered.answer.model,
            "seconds": round(answered.answer.seconds, 2),
            "costUsd": answered.answer.cost_usd,
        }
