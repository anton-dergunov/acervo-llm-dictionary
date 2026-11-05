"""Who and where each picture of a story shows, and which earlier pictures a later one is drawn from.

**References are chosen by identity, never by position.** A text call labels every part's brief with
the characters it puts in frame and the one place it is set in, as stable ids. Part k is then given
the *first* picture of each character it shows and the *last* picture of its place, if either
appeared before — and nothing when nothing recurs. The case this exists for is *La invención
del Post-it*: part 1 is one man in a laboratory and part 2, years later, is a different man in a
church. Handing part 2 the first picture would have painted the first man's face onto the second.

The labels are a separate call over the briefs `illustrate.BriefWriter` already wrote, rather than
more fields in that prompt. `experiments/story-picture-reference` tried both: asked for ids as well,
the brief writer stopped restating the cast in every brief, which is its most important rule and the
one a part with no references relies on entirely. This call reads the briefs and changes none of them.

**At most two references.** A story has four pictures, so the last part could otherwise be handed all
three before it; two is the owner's choice and costs nothing that matters. The references are
explained in the prompt one by one — who in it to keep, whether its place is this one, who in it must
not be drawn — under `prompts/acervo_story_reference.md`, which puts the picture first: the run that
measured this found conditioned pictures that matched their references and were stiffer for it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from acervo.models import call, chain
from acervo.models.providers import Providers
from acervo.models.errors import ProviderUnavailable
from acervo.stories.write import Part

# The heading the request sits under. Written here rather than ending the template, so a section
# the binding layer appends to the template — the reader, the standing rules — never lands between
# this heading and the request it introduces.
HEADING = "## The story"

MAX_REFERENCES = 2

# Cool: this call names what is in each picture and invents nothing.
LABEL_PARAMS: Mapping[str, Any] = {"temperature": 0.2}

_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_SCENE = "scene:"


@dataclass(frozen=True)
class Shown:
    """What one part's picture shows: the characters in frame, its one place, what changed since."""

    characters: tuple[str, ...]
    scene: str
    change: str


@dataclass(frozen=True)
class Continuity:
    characters: Mapping[str, str]
    scenes: Mapping[str, str]
    parts: tuple[Shown, ...]


@dataclass(frozen=True)
class Reference:
    """One earlier picture to send, and the ids it was chosen for (a place as `scene:<id>`)."""

    part: int
    keeps: tuple[str, ...]


def build_request(*, title: str, parts: Sequence[Part], briefs: Sequence[str]) -> dict[str, Any]:
    return {
        "title": title,
        "parts": [{"heading": part.heading, "text": part.text, "brief": brief}
                  for part, brief in zip(parts, briefs)],
    }


def _declared(entries: Any, kind: str) -> dict[str, str]:
    declared: dict[str, str] = {}
    for entry in entries or []:
        if not isinstance(entry, Mapping):
            raise ValueError(f"a {kind} is not an object")
        identifier = str(entry.get("id") or "").strip()
        if not _SLUG.match(identifier):
            raise ValueError(f"{kind} id {identifier!r} is not a lowercase slug")
        declared[identifier] = str(entry.get("description") or "").strip()
    return declared


def parse_reply(payload: Any, count: int) -> Continuity:
    """The labels, or ValueError saying what is wrong with them. Strict, because an id that names
    nothing would quietly choose no reference, and a scene id missing would choose the wrong one."""
    if not isinstance(payload, Mapping):
        raise ValueError("the reply was not a JSON object")
    characters = _declared(payload.get("characters"), "character")
    scenes = _declared(payload.get("scenes"), "scene")
    raw = payload.get("parts")
    if not isinstance(raw, list) or len(raw) != count:
        raise ValueError(f"the story has {count} parts and the labels have "
                         f"{len(raw) if isinstance(raw, list) else 'none'}")
    parts = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ValueError(f"part {index + 1} is not an object")
        who = tuple(dict.fromkeys(str(one).strip() for one in entry.get("characters") or []))
        unknown = [one for one in who if one not in characters]
        if unknown:
            raise ValueError(f"part {index + 1} names characters it never declared: {unknown}")
        scene = str(entry.get("scene") or "").strip()
        if scene not in scenes:
            raise ValueError(f"part {index + 1} is set in a scene it never declared: {scene!r}")
        parts.append(Shown(who, scene, str(entry.get("change") or "").strip()))
    return Continuity(characters=characters, scenes=scenes, parts=tuple(parts))


def references(continuity: Continuity, index: int,
               drawn: Callable[[int], bool] = lambda _part: True,
               characters: str = "first") -> tuple[Reference, ...]:
    """The earlier pictures part `index` (0-based) is drawn from, in reading order.

    **A returning character is drawn from the first picture that showed them; a returning place from
    the last.** Anchoring a person to the most recent picture let a face drift: part 2 drew a
    slightly different profile, part 3 took that as the truth and pushed it further, and by part 4
    the man was someone else. The first picture is the one the reader met him in. A place, by
    contrast, is meant to carry what has happened to it, so its latest picture is the right one.
    `characters="last"` is the earlier rule, kept so `experiments/story-picture-reference` can
    compare the two.

    Only a part that *has* a picture counts — a part whose drawing failed is passed over. A picture
    that serves several ids is sent once. Past `MAX_REFERENCES`, the characters are kept before the
    place, since who someone is matters more than where; what that drops is carried by the brief
    alone, which is what every picture relied on before references existed.
    """
    shown = continuity.parts[index]

    def served_by(identifier: str, first: bool) -> int | None:
        for earlier in (range(index) if first else range(index - 1, -1, -1)):
            other = continuity.parts[earlier]
            present = identifier == _SCENE + other.scene or identifier in other.characters
            if present and drawn(earlier):
                return earlier
        return None

    wanted = [(person, characters == "first") for person in shown.characters]
    wanted.append((_SCENE + shown.scene, False))
    chosen: dict[int, list[str]] = {}
    for identifier, first in wanted:
        earlier = served_by(identifier, first)
        if earlier is not None:
            chosen.setdefault(earlier, []).append(identifier)
    # Insertion order is priority — characters as the part lists them, then the place — for the
    # anchored rule; the older one keeps the most recent pictures, as it always did.
    kept = list(chosen)[:MAX_REFERENCES] if characters == "first" else sorted(chosen)[-MAX_REFERENCES:]
    return tuple(Reference(earlier, tuple(chosen[earlier])) for earlier in sorted(kept))


def _name(identifier: str) -> str:
    return identifier.replace("_", " ").upper()


def reference_lines(continuity: Continuity, index: int, chosen: Sequence[Reference]) -> str:
    """One paragraph per reference: who to keep, whether its place is this one, who to leave out."""
    shown = continuity.parts[index]
    paragraphs = []
    for number, reference in enumerate(chosen, start=1):
        other = continuity.parts[reference.part]
        sentences = [f"Reference {number} is the picture from part {reference.part + 1}."]
        for person in (one for one in reference.keeps if not one.startswith(_SCENE)):
            sentences.append(f"It shows {_name(person)} — {continuity.characters[person]}. Keep "
                             f"{_name(person)} recognisable: the same face, build and features.")
        if any(one.startswith(_SCENE) for one in reference.keeps):
            sentences.append(
                f"It shows the place {_name(shown.scene)} as it was last seen — "
                f"{continuity.scenes[shown.scene]}. This moment is in the same place: keep it "
                f"recognisable, and show it from a new viewpoint.")
        elif other.scene == shown.scene:
            # The same place at an earlier time, sent for a person: the place as it is now comes
            # from another reference, and telling the model this one is elsewhere would be false.
            sentences.append("It is the same place at an earlier time; take the place as it is now "
                             "from the description.")
        else:
            sentences.append("Its setting is not where this moment happens: do not reuse it.")
        absent = [one for one in other.characters if one not in shown.characters]
        if absent:
            sentences.append(f"It also shows {', '.join(_name(one) for one in absent)}, who "
                             f"{'is' if len(absent) == 1 else 'are'} not in this moment: do not "
                             f"draw them.")
        paragraphs.append(" ".join(sentences))
    if shown.change:
        paragraphs.append(f"What has changed since those pictures: {shown.change}. Where this "
                          f"differs from a reference, follow this and not the reference.")
    return "\n\n".join(paragraphs)


def compose(template: str, continuity: Continuity, index: int, chosen: Sequence[Reference],
            picture: str) -> str:
    """The reference prompt around `picture`, which is `illustrate.compose`'s brief-style-frame."""
    return (template.replace("{references}", reference_lines(continuity, index, chosen))
            .replace("{picture}", picture))


class Labeller:
    def __init__(self, catalogue: Providers, candidates: Sequence[chain.Candidate], template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def label(self, request: Mapping[str, Any], count: int) -> tuple[Continuity, dict[str, Any]]:
        prompt = f"{self.template}\n\n{HEADING}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"

        def ask(candidate: chain.Candidate) -> call.TextResult:
            result = call.text(prompt, row=candidate.row, model=candidate.model, as_json=True,
                               params=LABEL_PARAMS)
            try:
                parse_reply(result.parsed, count)
            except ValueError as error:
                raise ProviderUnavailable(
                    "unusable", f"the labels did not hold their shape: {error}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return result

        answered = chain.walk(
            "text", [c.named for c in self.candidates], self.catalogue, ask, chain.stamped,
            caller="story.continuity",
        )
        return parse_reply(answered.parsed, count), {
            "provider": answered.answer.provider_id,
            "model": answered.answer.model,
            "seconds": round(answered.answer.seconds, 2),
        }
