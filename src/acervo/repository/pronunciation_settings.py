"""How this owner wants words pronounced. One row per owner, or none — and none is a real answer.

The `image_settings` doctrine: **no record means "use the deployment default"**, nothing creates a
row eagerly, and every read is a pure read. Server state rather than a device preference, because the
recording happens on the server — a phone that has never opened Settings still gets the voices the
owner chose. Whether a clip is *kept on a device* is the opposite case and lives on the device.

This module stores what it is given. Which voices exist is the catalogue's question, and
`acervo.services.pronunciations` is where a document is held to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction

# What is recorded when a *word* is saved.
PREGENERATED = ("headword", "definitions", "examples")
# Whether a story is recorded when it is made. It shares the document because it is the same
# question asked of another record, but it is a different switch: it is read by the `story` job and
# never by `enrich`, and it is **on** unless the owner turns it off, where every word switch is off.
# Being read only when a story is made is what makes a recording on demand the answer when it is off.
STORIES = "stories"
SWITCHES = PREGENERATED + (STORIES,)
SWITCH_DEFAULT = {**{name: False for name in PREGENERATED}, STORIES: True}

# The three things a voice is asked to read, and the two orders it can be read by.
#
# There were two orders and they were labelled by *use* — "words and definitions", "example
# sentences" — with a separate boolean deciding whether a direction was sent. That boolean only ever
# gated the direction, so switching emotion off still spent the expensive voice on every sentence.
# Now the orders are named for their capability and each use picks one, which makes choosing the
# directed order *be* asking for emotion: one mechanism where there were two, and the cheap voice
# finally reachable for examples as well.
#
# A selection reads with the `words` order. Three uses, two orders, and deliberately no third chain:
# any voice is a legitimate answer to either question.
#
# A story is a fourth use: a narrator, so it defaults to the directed order, and it is chosen in
# Settings ▸ Stories the way loops are chosen in Settings ▸ Loops.
USES = ("words", "examples", "loops", "stories")
ORDERS = ("plain", "expressive")
DELIVERY_DEFAULT = {
    "words": "plain", "examples": "expressive", "loops": "expressive", "stories": "expressive",
}


class PronunciationSettings(Mapping):
    """The owner's answer, or the default when they have not given one. A `Mapping`, like `ImageSettings`."""

    __slots__ = ("pregenerate", "delivery", "voices", "guide_voices", "chosen")

    def __init__(
        self,
        *,
        pregenerate: Mapping[str, Any] | None = None,
        delivery: Mapping[str, Any] | None = None,
        voices: Mapping[str, Any] | None = None,
        guide_voices: Mapping[str, Any] | None = None,
        chosen: bool = False,
    ) -> None:
        given = pregenerate if isinstance(pregenerate, Mapping) else {}
        # Every key present and boolean, so a hand-edited row with a stray key or a string cannot
        # switch recording on by accident.
        self.pregenerate = {name: given.get(name, SWITCH_DEFAULT[name]) is True for name in SWITCHES}
        self.delivery = _delivery(delivery)
        self.voices = _voices(voices)
        # Who says a loop's guide lines — its translations, remarks and announcements — where the
        # owner chose someone other than the voice above. Same shape; absent means the same voice.
        self.guide_voices = _voices(guide_voices)
        self.chosen = bool(chosen)

    def __getitem__(self, key: str) -> Any:
        return {
            "pregenerate": dict(self.pregenerate),
            "delivery": dict(self.delivery),
            "voices": self.voices,
            "guideVoices": self.guide_voices,
            "chosen": self.chosen,
        }[key]

    def __iter__(self):
        return iter(("pregenerate", "delivery", "voices", "guideVoices", "chosen"))

    def __len__(self) -> int:
        return 5

    def for_guide(self) -> "PronunciationSettings":
        """These settings as a loop's guide lines read them: the guide voice wherever one is chosen,
        and the usual voice everywhere else."""
        merged = {provider: {model: dict(languages) for model, languages in models.items()}
                  for provider, models in self.voices.items()}
        for provider, models in self.guide_voices.items():
            for model, languages in models.items():
                merged.setdefault(provider, {}).setdefault(model, {}).update(languages)
        return PronunciationSettings(pregenerate=self.pregenerate, delivery=self.delivery,
                                     voices=merged, guide_voices=self.guide_voices,
                                     chosen=self.chosen)

    @property
    def words_in_advance(self) -> bool:
        """Whether saving a word should record anything. The story switch is not part of it."""
        return any(self.pregenerate[name] for name in PREGENERATED)

    def order_for(self, use: str) -> str:
        """Which order reads this use. An unknown use reads plainly, which is the cheap answer."""
        return self.delivery.get(use, DELIVERY_DEFAULT.get(use, "plain"))

    def voice(self, provider: str, model: str, language: str) -> str | None:
        """The voice chosen for this pair in this language, widening `es-MX` to `es`, or None."""
        chosen = self.voices.get(provider, {}).get(model, {})
        parts = language.split("-")
        for count in range(len(parts), 0, -1):
            if found := chosen.get("-".join(parts[:count])):
                return found
        return None


def _delivery(value: Any) -> dict[str, str]:
    """Every use present and naming a real order, so a hand-edited row cannot leave one unanswered."""
    given = value if isinstance(value, Mapping) else {}
    return {
        use: str(given.get(use)) if given.get(use) in ORDERS else DELIVERY_DEFAULT[use]
        for use in USES
    }


def _voices(value: Any) -> dict[str, dict[str, dict[str, str]]]:
    """Only the well-formed part of a stored voice document; anything else is dropped, not raised."""
    found: dict[str, dict[str, dict[str, str]]] = {}
    if not isinstance(value, Mapping):
        return found
    for provider, models in value.items():
        if not isinstance(models, Mapping):
            continue
        for model, languages in models.items():
            if not isinstance(languages, Mapping):
                continue
            kept = {
                str(language): str(voice)
                for language, voice in languages.items()
                if isinstance(voice, str) and voice.strip()
            }
            if kept:
                found.setdefault(str(provider), {})[str(model)] = kept
    return found


def _read(row: Any) -> PronunciationSettings:
    if row is None:
        return PronunciationSettings()
    return PronunciationSettings(
        pregenerate=row["pregenerate"], delivery=row["delivery"], voices=row["voices"],
        guide_voices=row["guide_voices"], chosen=True
    )


def settings(owner: str) -> PronunciationSettings:
    with reading() as connection:
        row = connection.execute(
            select(tables.pronunciation_settings).where(tables.pronunciation_settings.c.owner == owner)
        ).mappings().first()
    return _read(row)


def save(
    owner: str,
    *,
    pregenerate: Mapping[str, bool] | None = None,
    delivery: Mapping[str, str] | None = None,
    voices: Mapping[str, Any] | None = None,
    guide_voices: Mapping[str, Any] | None = None,
) -> PronunciationSettings:
    """Change only what is named, inside one `BEGIN IMMEDIATE`. Returns the whole stored document."""
    table = tables.pronunciation_settings
    with transaction() as connection:
        row = connection.execute(select(table).where(table.c.owner == owner)).mappings().first()
        current = _read(row)
        wanted = PronunciationSettings(
            pregenerate={**current.pregenerate, **(pregenerate or {})},
            delivery={**current.delivery, **(delivery or {})},
            voices=current.voices if voices is None else voices,
            guide_voices=current.guide_voices if guide_voices is None else guide_voices,
            chosen=True,
        )
        values = {
            "pregenerate": dict(wanted.pregenerate),
            "delivery": dict(wanted.delivery),
            "voices": wanted.voices,
            "guide_voices": wanted.guide_voices,
            "edited_at": now_instant(),
        }
        if row is None:
            connection.execute(table.insert().values(id=new_record_id(), owner=owner, **values))
        else:
            connection.execute(table.update().where(table.c.id == row["id"]).values(**values))
        return wanted
