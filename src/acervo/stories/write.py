"""The story call: a few words in, a story in parts out.

One text call per story, asked hot — `WRITE_PARAMS` below. This is the only genuinely creative call
in Acervo, and it is the one place a low temperature would be actively wrong: the failure mode of a
cautious story is not an error, it is a story nobody reads twice, which is the whole mechanism.

`parse_reply` is the contract, and it is enforced twice on the happy path for `images/brief.py`'s
reason: once inside the chain's callback, so a model that cannot hold the shape is *passed over*
rather than ending the walk, and once after `walk` returns.

What it checks is what a schema could not. That every word asked for is accounted for; that a
reported surface form **actually appears in the text it was reported against**, because that string
is what the reader searches for and an invented one silently marks nothing; and that the part count
and sentence lengths are within what the prompt asked for, since a model that ignores those has not
written the thing the reader was built for.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from acervo.models import call, chain
from acervo.models.catalogue import Catalogue
from acervo.models.errors import ProviderUnavailable

# The heading the request sits under. Written here rather than ending the template, so a section
# the binding layer appends to the template — the reader, the standing rules — never lands between
# this heading and the request it introduces.
HEADING = "## The request"

# Hot, deliberately. See the module docstring. A row that pins its own temperature still wins —
# `call.text` spreads this first and the row second.
WRITE_PARAMS: Mapping[str, Any] = {"temperature": 1.0}

# What the prompt asks for, restated here because this is what refuses a reply that ignored it.
MIN_PARTS = 3
MAX_PARTS = 8
MAX_PART_CHARS = 1200


class StoryRefused(ValueError):
    """The writer refused, in its own words. Not a shape problem — do not retry another model."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Part:
    heading: str
    text: str


@dataclass(frozen=True)
class Written:
    title: str
    emoji: str
    parts: tuple[Part, ...]
    # lexeme id -> the surface forms the story used, verified to appear in the text.
    forms: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def unused(self, wanted: Sequence[str]) -> tuple[str, ...]:
        """The ids the story did not manage to use — including one it only claimed to."""
        return tuple(one for one in wanted if not self.forms.get(one))


def build_request(
    *,
    language: str,
    language_name: str,
    words: Sequence[Mapping[str, Any]],
    story_type_brief: str,
    story_type_label: str,
    parts: int,
    guidance: str = "",
) -> dict[str, Any]:
    """What the model is told. Plain data — the prompt is the template this is appended to.

    `guidance` is the owner's own note, and only sent when there is one, so a story asked for without
    it is the request it always was.
    """
    return {
        "language": {"code": language, "name": language_name},
        "kind": {"name": story_type_label, "direction": story_type_brief},
        **({"guidance": guidance} if guidance.strip() else {}),
        "parts": parts,
        "words": [
            {
                "lexemeId": word["id"],
                "headword": word.get("headword") or "",
                "lemma": word.get("lemma") or "",
                "pos": word.get("pos") or "",
                "means": word.get("gloss") or "",
                "definition": word.get("definition") or "",
            }
            for word in words
        ],
    }


def _sentences(text: str) -> int:
    return len([one for one in re.split(r"[.!?…。！？]+", text) if one.strip()])


def _plain(value: str) -> str:
    """Lowercased and stripped of accents, so `asombrosa` and `asombrosá` compare as one stem."""
    return "".join(
        one for one in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(one) != "Mn"
    )


# How much of a word a reported form has to share with it. Four is enough for regular inflection in
# the languages this is for — `ladrar`/`ladró` share `ladr`, `asombroso`/`asombrosa` share
# `asombros` — and enough to reject a synonym outright.
STEM_CHARS = 4


def is_form_of(form: str, headword: str, lemma: str) -> bool:
    """Is this plausibly a form of that word, rather than a different word entirely?

    **This exists because the first real call produced one.** Asked for a story using `asombroso`,
    the model wrote a story that never contains it, then reported `sorprende` — a synonym — as the
    form it had used. `sorprende` is in the text, so a check that only asked "does this string
    appear" passed it, and the reader would have highlighted a *different word* and taught it as
    the one being learned. That is worse than no mark at all.

    Deliberately shallow: a shared stem, or one containing the other. It is not a morphological
    analyser and must not become one — this package holds no language data, and the cost of being
    wrong is asymmetric. A form wrongly **rejected** leaves a word unmarked, which is visible, mild
    and recorded as unused. A form wrongly **accepted** silently teaches a falsehood.

    The known false negatives are suppletive forms — Spanish `ir`/`fue`, German `gehen`/`ging` —
    where no stem is shared at all. Those read as an unused word. Accepted, for the reason above.
    """
    candidate = _plain(form).strip()
    if not candidate:
        return False
    for target in (_plain(headword).strip(), _plain(lemma).strip()):
        if not target:
            continue
        # A multi-word headword, a reflexive, a separable prefix: containment either way.
        if candidate in target or target in candidate:
            return True
        need = min(STEM_CHARS, len(target), len(candidate))
        if need and candidate[:need] == target[:need]:
            return True
    return False


def parse_reply(payload: Any, wanted: Sequence[Mapping[str, Any]]) -> Written:
    """The reply, checked against what was asked for. Raises `ValueError` on anything unusable."""
    if not isinstance(payload, Mapping):
        raise ValueError("the reply was not a JSON object")

    if payload.get("refused"):
        raise StoryRefused(str(payload.get("reason") or "").strip() or "the writer refused")

    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("the story has no title")

    raw_parts = payload.get("parts")
    if not isinstance(raw_parts, list) or not MIN_PARTS <= len(raw_parts) <= MAX_PARTS:
        raise ValueError(
            f"a story has between {MIN_PARTS} and {MAX_PARTS} parts, got "
            f"{len(raw_parts) if isinstance(raw_parts, list) else 'none'}"
        )

    parts: list[Part] = []
    for index, entry in enumerate(raw_parts):
        if not isinstance(entry, Mapping):
            raise ValueError(f"part {index + 1} is not an object")
        text = str(entry.get("text") or "").strip()
        if not text:
            raise ValueError(f"part {index + 1} has no text")
        if len(text) > MAX_PART_CHARS:
            # Not a style preference: a part is drawn on one screen under a picture, and one this
            # long cannot be read without scrolling, which is the one thing the reader promises.
            raise ValueError(f"part {index + 1} is too long to fit a screen ({len(text)} characters)")
        parts.append(Part(heading=str(entry.get("heading") or "").strip(), text=text))

    whole = "\n".join(part.text for part in parts)
    forms: dict[str, tuple[str, ...]] = {}
    reported = payload.get("words")
    if not isinstance(reported, list):
        raise ValueError("the reply did not say which words it used")

    allowed = {str(word["id"]): word for word in wanted}
    for entry in reported:
        if not isinstance(entry, Mapping):
            continue
        lexeme_id = str(entry.get("lexemeId") or "").strip()
        if lexeme_id not in allowed:
            # Dropped and not fatal, for `clips/select.py`'s reason: an id nobody asked about is a
            # prompt bug to fix, and refusing the whole story would throw away a good one with it.
            continue
        raw_forms = entry.get("forms")
        if not isinstance(raw_forms, list):
            continue
        # Two checks, and both were earned. **In the text**, because this string is what the
        # reader searches for, and one that was never written marks nothing. **A form of this
        # word**, because the first real call reported a synonym — see `is_form_of`.
        word = allowed[lexeme_id]
        found = tuple(dict.fromkeys(
            one for one in (str(f).strip() for f in raw_forms)
            if one and one in whole
            and is_form_of(one, str(word.get("headword") or ""), str(word.get("lemma") or ""))
        ))
        if found:
            forms[lexeme_id] = found

    return Written(title=title, emoji=str(payload.get("emoji") or "").strip()[:8],
                   parts=tuple(parts), forms=forms)


class StoryWriter:
    """One story, over whichever pair in the chain answers."""

    def __init__(self, catalogue: Catalogue, candidates: Sequence[chain.Candidate], template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def write(self, request: Mapping[str, Any], wanted: Sequence[str]) -> tuple[Written, dict[str, Any]]:
        prompt = f"{self.template}\n\n{HEADING}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"

        def ask(candidate: chain.Candidate) -> call.TextResult:
            result = call.text(
                prompt, row=candidate.row, model=candidate.model, as_json=True,
                params=WRITE_PARAMS,
            )
            if not result.text.strip():
                raise ProviderUnavailable("empty", "the model returned nothing",
                                          provider_id=candidate.row.id, model=candidate.model)
            try:
                parse_reply(result.parsed, wanted)
            except StoryRefused:
                raise  # the writer's own judgement, not a shape failure: do not try another model
            except ValueError as error:
                raise ProviderUnavailable(
                    "unusable", f"the story did not hold its shape: {error}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return result

        answered = chain.walk(
            "text", [c.named for c in self.candidates], self.catalogue, ask, chain.stamped,
            caller="story.write",
        )
        return parse_reply(answered.parsed, wanted), {
            "provider": answered.answer.provider_id,
            "model": answered.answer.model,
            "seconds": round(answered.answer.seconds, 2),
            "costUsd": answered.answer.cost_usd,
            "passedOver": [list(one) for one in answered.answer.passed_over],
        }
