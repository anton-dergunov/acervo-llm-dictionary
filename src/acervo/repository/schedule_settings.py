"""When this owner's nightly run happens, and which of its steps run. One row per owner, or none.

The same doctrine as the other settings tables: **no row means the defaults**, nothing creates one
eagerly, and every read is a pure read. The hour is read in the deployment's zone.

This module stores what it is given; `services/schedule.py` is the one validator.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction

DEFAULT_HOUR = 2
# The nightly steps, in the order they run, and whether each is on until the owner says otherwise.
# Reading Anki back is not one of them: it runs every hour, on its own switch (`anki_settings`).
STEPS: dict[str, bool] = {"corpus.update": True}


class ScheduleSettings(Mapping):
    __slots__ = ("hour", "steps", "chosen")

    def __init__(self, *, hour: int = DEFAULT_HOUR, steps: Mapping[str, Any] | None = None,
                 chosen: bool = False) -> None:
        given = steps if isinstance(steps, Mapping) else {}
        self.hour = int(hour)
        self.steps = {name: bool(given.get(name, default)) for name, default in STEPS.items()}
        self.chosen = bool(chosen)

    def __getitem__(self, key: str) -> Any:
        return {"hour": self.hour, "steps": dict(self.steps), "chosen": self.chosen}[key]

    def __iter__(self):
        return iter(("hour", "steps", "chosen"))

    def __len__(self) -> int:
        return 3


def _read(row: Any) -> ScheduleSettings:
    if row is None:
        return ScheduleSettings()
    return ScheduleSettings(hour=row["hour"], steps=row["steps"], chosen=True)


def settings(owner: str) -> ScheduleSettings:
    with reading() as connection:
        row = connection.execute(
            select(tables.schedule_settings).where(tables.schedule_settings.c.owner == owner)
        ).mappings().first()
    return _read(row)


def save(owner: str, *, hour: int | None = None,
         steps: Mapping[str, bool] | None = None) -> ScheduleSettings:
    """Change only what is named. Returns the whole stored document."""
    with transaction() as connection:
        table = tables.schedule_settings
        row = connection.execute(select(table).where(table.c.owner == owner)).mappings().first()
        current = _read(row)
        wanted = ScheduleSettings(
            hour=current.hour if hour is None else hour,
            steps={**current.steps, **(steps or {})},
            chosen=True,
        )
        values = {"hour": wanted.hour, "steps": dict(wanted.steps), "edited_at": now_instant()}
        if row is None:
            connection.execute(table.insert().values(id=new_record_id(), owner=owner, **values))
        else:
            connection.execute(table.update().where(table.c.id == row["id"]).values(**values))
        return wanted
