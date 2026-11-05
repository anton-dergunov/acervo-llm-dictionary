"""The translation call: the whole story at once, asked cold.

**The whole story, not a part at a time**, and that is the design rather than an optimisation. A
name, a nickname and a running joke have to read the same in every part, and a model shown one
paragraph in isolation has no way to know what it already called somebody. Per-part calls are also
where an off-by-one becomes possible at all.

Cold, because this is the opposite task to writing one. `TRANSLATE_PARAMS` asks for a low
temperature; a row that pins its own still wins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from acervo.models import call, chain
from acervo.models.providers import Providers
from acervo.models.errors import ProviderUnavailable
from acervo.stories.write import Part

# The heading the request sits under. Written here rather than ending the template, so a section
# the binding layer appends to the template — the reader, the standing rules — never lands between
# this heading and the request it introduces.
HEADING = "## The story"

TRANSLATE_PARAMS: Mapping[str, Any] = {"temperature": 0.2}


@dataclass(frozen=True)
class Translated:
    title: str
    parts: tuple[Part, ...]
    # lexeme id -> the words of *this translation* that render it, verified to appear in it. Empty
    # for a word the translator could not point to, and for every word if it did not try.
    forms: dict[str, tuple[str, ...]] = field(default_factory=dict)


def build_request(
    *, title: str, parts: Sequence[Part], source_name: str, target_name: str, target_code: str,
    words: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """What the model is told. `words` are the ones the story teaches, each with `forms`: what the
    writer used them as, which is what the translator is being asked to find the counterpart of."""
    request: dict[str, Any] = {
        "from": source_name,
        "into": {"code": target_code, "name": target_name},
        "title": title,
        "parts": [{"heading": part.heading, "text": part.text} for part in parts],
    }
    if words:
        request["words"] = [
            {"lexemeId": word["id"], "headword": word.get("headword") or "",
             "usedAs": list(word.get("forms") or ())}
            for word in words
        ]
    return request


def _forms_in(payload: Mapping[str, Any], asked: Sequence[str], whole: str) -> dict[str, tuple[str, ...]]:
    """The words the translator says render each asked-for word — **the ones it really wrote**.

    Read leniently, and that is the design: this is a garnish on a translation that is otherwise
    good, so a missing field, a malformed entry or a form that is not in the text costs the mark and
    never the translation. `write.parse_reply` is stricter about the same field for the opposite
    reason — there it decides whether a word was used at all.

    Only "is it in the text" is checked. `write.is_form_of` compares stems and is written for the
    story's own language; across two languages a translation shares no stem with its source.
    """
    reported = payload.get("words")
    if not isinstance(reported, list) or not asked:
        return {}
    found: dict[str, tuple[str, ...]] = {}
    for entry in reported:
        if not isinstance(entry, Mapping):
            continue
        lexeme_id = str(entry.get("lexemeId") or "").strip()
        raw = entry.get("forms")
        # An id nobody asked about is dropped, not fatal, for the reason `write.parse_reply` gives.
        if lexeme_id not in asked or not isinstance(raw, list):
            continue
        kept = tuple(dict.fromkeys(
            one for one in (str(form).strip() for form in raw) if one and one in whole
        ))
        if kept:
            found[lexeme_id] = kept
    return found


def parse_reply(payload: Any, parts: Sequence[Part], asked: Sequence[str] = ()) -> Translated:
    if not isinstance(payload, Mapping):
        raise ValueError("the reply was not a JSON object")
    raw = payload.get("parts")
    if not isinstance(raw, list):
        raise ValueError("the reply had no parts")
    # **Count first, and exactly.** Each translation is shown beside its own original, so one part
    # too few puts every later translation under the wrong picture — a failure that looks like a bad
    # translation rather than like a bad count, and is nearly impossible to diagnose from the page.
    if len(raw) != len(parts):
        raise ValueError(f"the story has {len(parts)} parts and the translation has {len(raw)}")

    translated: list[Part] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ValueError(f"translated part {index + 1} is not an object")
        text = str(entry.get("text") or "").strip()
        if not text:
            raise ValueError(f"translated part {index + 1} is empty")
        translated.append(Part(heading=str(entry.get("heading") or "").strip(), text=text))

    whole = "\n".join(part.text for part in translated)
    return Translated(
        title=str(payload.get("title") or "").strip(), parts=tuple(translated),
        forms=_forms_in(payload, asked, whole),
    )


class Translator:
    def __init__(self, catalogue: Providers, candidates: Sequence[chain.Candidate], template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def translate(
        self, request: Mapping[str, Any], parts: Sequence[Part]
    ) -> tuple[Translated, dict[str, Any]]:
        prompt = f"{self.template}\n\n{HEADING}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"
        asked = tuple(str(word["lexemeId"]) for word in request.get("words", ()))

        def ask(candidate: chain.Candidate) -> call.TextResult:
            result = call.text(
                prompt, row=candidate.row, model=candidate.model, as_json=True,
                params=TRANSLATE_PARAMS,
            )
            if not result.text.strip():
                raise ProviderUnavailable("empty", "the model returned nothing",
                                          provider_id=candidate.row.id, model=candidate.model)
            try:
                parse_reply(result.parsed, parts, asked)
            except ValueError as error:
                raise ProviderUnavailable(
                    "unusable", f"the translation did not hold its shape: {error}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return result

        answered = chain.walk(
            "text", [c.named for c in self.candidates], self.catalogue, ask, chain.stamped,
            caller="story.translate",
        )
        return parse_reply(answered.parsed, parts, asked), {
            "provider": answered.answer.provider_id,
            "model": answered.answer.model,
            "seconds": round(answered.answer.seconds, 2),
            "costUsd": answered.answer.cost_usd,
        }
