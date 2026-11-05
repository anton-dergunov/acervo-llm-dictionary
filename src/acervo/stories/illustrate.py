"""The pictures: one brief call for the whole story, then one draw call per part.

**The brief covers every part at once**, which is the same argument `images/brief.py` makes for
batching a word's senses and matters more here. Each picture is drawn by a model that has never
seen the others, so anything that must stay the same across them — a man's jacket, a dog's collar —
has to be restated in every brief. Deciding those descriptions once, with all the parts in view, is
the only way four pictures read as four parts of one story. Since `continuity.py`, a later picture
may also be handed the earlier pictures of the people and places it shows again — but only where
the pair can read them, so the restated description is still what every picture stands on.

The draw call is `images/`-shaped on purpose: the style text is appended here rather than asked for
in the brief, so the same brief in another style is one substitution, and a `FRAME` states the
things every picture must obey.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from acervo.images.render import Rendered, Renderer
from acervo.images.styles import Style
from acervo.models import call, chain
from acervo.models.providers import Providers
from acervo.models.errors import ProviderUnavailable
from acervo.stories.write import Part

# The heading the request sits under. Written here rather than ending the template, so a section
# the binding layer appends to the template — the reader, the standing rules — never lands between
# this heading and the request it introduces.
HEADING = "## The story"

# Warm: a brief is a creative act with a fixed job, between the story and the translation.
BRIEF_PARAMS: Mapping[str, Any] = {"temperature": 0.7}

# Appended to every story picture, as `images/compose.py`'s own FRAME is to every sense picture.
# The text prohibition is stated twice — here and in the prompt — because a story is far more likely
# than a word to contain a sign, a note or a headline, and a model asked for one renders gibberish.
FRAME = (
    "A single illustration, fully rendered and fully inhabited. Absolutely no text anywhere in the "
    "image: no letters, words, numbers, captions, labels, signage, logos, watermarks or pseudo-text."
)


@dataclass(frozen=True)
class Briefed:
    cast: str
    world: str
    briefs: tuple[str, ...]


def compose(brief: str, style: Style) -> str:
    """The brief, the style, the frame — in that order, and never stored. See `images/compose.py`."""
    return f"{brief.strip().rstrip('.')}. {style.brief.strip().rstrip('.')}. {FRAME}"


def build_request(
    *, title: str, parts: Sequence[Part], language_name: str
) -> dict[str, Any]:
    return {
        "title": title,
        "language": language_name,
        "parts": [{"heading": part.heading, "text": part.text} for part in parts],
    }


def parse_reply(payload: Any, parts: Sequence[Part]) -> Briefed:
    if not isinstance(payload, Mapping):
        raise ValueError("the reply was not a JSON object")
    if payload.get("refused"):
        raise ValueError(str(payload.get("reason") or "the brief writer refused"))
    raw = payload.get("parts")
    if not isinstance(raw, list) or len(raw) != len(parts):
        raise ValueError(
            f"the story has {len(parts)} parts and the briefs have "
            f"{len(raw) if isinstance(raw, list) else 'none'}"
        )
    briefs: list[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ValueError(f"brief {index + 1} is not an object")
        brief = str(entry.get("brief") or "").strip()
        if not brief:
            raise ValueError(f"brief {index + 1} is empty")
        briefs.append(brief)
    return Briefed(
        cast=str(payload.get("cast") or "").strip(),
        world=str(payload.get("world") or "").strip(),
        briefs=tuple(briefs),
    )


class BriefWriter:
    def __init__(self, catalogue: Providers, candidates: Sequence[chain.Candidate], template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def write(self, request: Mapping[str, Any], parts: Sequence[Part]) -> tuple[Briefed, dict[str, Any]]:
        prompt = f"{self.template}\n\n{HEADING}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"

        def ask(candidate: chain.Candidate) -> call.TextResult:
            result = call.text(
                prompt, row=candidate.row, model=candidate.model, as_json=True, params=BRIEF_PARAMS,
            )
            if not result.text.strip():
                raise ProviderUnavailable("empty", "the model returned nothing",
                                          provider_id=candidate.row.id, model=candidate.model)
            try:
                parse_reply(result.parsed, parts)
            except ValueError as error:
                raise ProviderUnavailable(
                    "unusable", f"the briefs did not hold their shape: {error}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return result

        answered = chain.walk(
            "text", [c.named for c in self.candidates], self.catalogue, ask, chain.stamped,
            caller="story.brief",
        )
        return parse_reply(answered.parsed, parts), {
            "provider": answered.answer.provider_id,
            "model": answered.answer.model,
            "seconds": round(answered.answer.seconds, 2),
            "costUsd": answered.answer.cost_usd,
        }


def draw(brief: str, style: Style, *, seed: int, candidates: Sequence[chain.Candidate],
         catalogue: Providers, references: Sequence[bytes] = (),
         with_references: str | None = None) -> Rendered:
    """One part's picture, in the story's one style.

    Through `chain.walk` even with a single pair, for the reason `services/images._draw` gives:
    `walk` is what remembers a refusal, and skipping it would re-probe an exhausted allowance on
    every part of every story.

    `with_references` is the whole prompt to send *with* `references` (`continuity.compose`), and it
    is decided per pair: a pair whose row takes reference pictures gets both, and any other gets the
    plain brief — so a fall-through to such a row draws exactly what it drew before references
    existed, rather than a prompt describing pictures it was never shown.
    """
    renderer = Renderer()
    plain = compose(brief, style)
    sent = tuple(references)

    def ask(candidate: chain.Candidate) -> Rendered:
        if sent and with_references and candidate.row.image_references() >= len(sent):
            return renderer.draw(with_references, seed, candidate, sent)
        return renderer.draw(plain, seed, candidate)

    return chain.walk(
        "image",
        [candidate.named for candidate in candidates],
        catalogue,
        ask,
        chain.stamped,
        caller="story.draw",
    )
