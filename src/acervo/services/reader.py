"""Who a text is written for: one vocabulary's learner, said to the writers that write for them.

A vocabulary carries three facts about its learner — a level, a variety and a note in their own words
— and the calls that write what they will read in that language are told all three: an entry, the
article conversation, and a story. A loop's written lines are told the first two only: a loop writes
one short line for each word, which is where the note most often pulls an example off its word. Each
is said with its own weight, firmest first:

- **the level** steers every sentence, because a sentence out of reach teaches nothing;
- **the variety** is a preference where the language differs by region, never a filter: the other
  varieties are the language too, and a note may say what is said elsewhere;
- **the note** is background, never material. Told "preparing for a trip to Argentina", a writer
  asked for *cactus* must still write about cacti, and a story's hero must not become a programmer
  on holiday — the note may shape one example of a word that belongs to it, and no more.

The weights are measured, not argued: `experiments/learner-context/`.

Not the picture brief or the clip choice, whose subject is the word and never the learner, and not
the resolver or narration, which write nothing the learner reads as new. Like the standing rules
(`services/rules.py`), the section is joined here, in the binding layer, after the prompt and before
the rules, so a pipeline package is handed a prompt and never learns where part of it came from.
With nothing set the prompt is byte-for-byte what it was.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from acervo.models import locales
from acervo.services.rules import with_rules

LEVELS = {
    "A1": "beginner", "A2": "elementary", "B1": "intermediate",
    "B2": "upper intermediate", "C1": "advanced", "C2": "proficient",
}

_HEADING = "## The reader"


def reader_section(vocabulary: Mapping[str, Any] | None, *, note: bool = True) -> str:
    """The section for one vocabulary's learner, or "" when it says nothing about them.

    `note=False` leaves the learner's note out and says the rest in the same words.
    """
    if not vocabulary:
        return ""
    language = locales.language_name(str(vocabulary.get("language") or ""))
    level = str(vocabulary.get("level") or "").strip().upper()
    region = str(vocabulary.get("region") or "").strip().upper()
    place = locales.region_name(region) if region else None
    said = str(vocabulary.get("learnerNote") or "").strip() if note else ""
    lines: list[str] = []
    if level in LEVELS:
        lines.append(
            f"- **Their level in {language} is {level}, {LEVELS[level]}.** Keep what you write within "
            "reach of it: the examples, the notes, a story's sentences. A harder sentence is right when "
            "the word itself needs one."
        )
    if place:
        lines.append(
            f"- **They are learning the {language} of {place}.** Where words, forms or grammar differ "
            f"from region to region, use {place}'s in what you write. Do not hide the others: they are "
            f"{language} too, and where the learner will meet them, say what is said elsewhere. A word "
            f"that is the same everywhere needs no word about {place}: mark a word as regional, or "
            f"mention {place}, only when the word itself differs there. The variety decides the words, "
            "not the setting: nothing you write needs to happen there."
        )
    if said:
        quoted = "\n".join(f"  > {line}" if line.strip() else "  >" for line in said.splitlines())
        lines.append(
            "- **What they say about themselves**, in their own words:\n\n"
            f"{quoted}\n\n"
            "  This is background about the person, not material for what you write. Do not give it to a "
            "character, a setting or an example: no character shares their job, their plans or their "
            "interests, and nothing is set where they are going. Use it only where the word itself "
            "belongs to it — a word about travel, for someone about to travel — and then in one example "
            "at most. Never mention it, and never bend a word's meaning toward it."
        )
    if not lines:
        return ""
    return "\n\n".join([
        _HEADING,
        f"You are writing for one person learning {language}. What they have told you, firmest first:",
        "\n".join(lines),
    ])


def with_reader(text: str, owner: str, vocabulary: Mapping[str, Any] | None, *, note: bool = True) -> str:
    """The prompt with the learner's section, then the owner's standing rules, each only if set."""
    section = reader_section(vocabulary, note=note)
    return with_rules(f"{text}\n\n{section}" if section else text, owner)


def vocabulary_for(vocabularies: list[dict[str, Any]], vocabulary_id: str | None) -> dict[str, Any] | None:
    """The owner's vocabulary with this id, or None — one they have since removed."""
    return next((one for one in vocabularies if vocabulary_id and one["id"] == vocabulary_id), None)
