"""How this owner wants the spoken-usage corpus consulted. One row per owner, or none.

The same three-state doctrine as `image_settings` and `model_selection`, and for the same reason:
**no record means "use the deployment default"**. Nothing creates a row eagerly and there is no
`ensure_` function, so every read is a pure read with nothing to write when it is missing. Eager
creation would have to invent a value, and snapshotting today's default would freeze it at the
instant the account was made.

Two fields, and deliberately not more. Which channels the corpus harvests is the retrieval
service's own catalogue (`docs/features/spoken-clips.md` §2.10) and Acervo ships no copy of it; how
many candidates a call sees is a research knob that belongs in
`docs/plans/quality/clip-selection.md`, not in a settings screen.

`self_contained_only` is the first boolean that is really a *taste* — how authentic, how tidy — and
a growing list of those is the wrong shape for that question. Part 2 of
`docs/plans/quality/clip-selection.md` is where that goes next.

This module stores what it is given, exactly as `image_settings` does.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction


class ClipSettings(Mapping):
    """The owner's answer, or the deployment default when they have not given one.

    A `Mapping` so a route can return it as a document without a second shape to keep in step, and
    `chosen` is what says whether a row exists — which the settings screen needs in order to show
    "following the default" rather than showing the default as though it had been picked.
    """

    __slots__ = ("search_enabled", "self_contained_only", "chosen")

    def __init__(self, *, search_enabled: bool = True, self_contained_only: bool = False,
                 chosen: bool = False) -> None:
        self.search_enabled = bool(search_enabled)
        self.self_contained_only = bool(self_contained_only)
        self.chosen = bool(chosen)

    def __getitem__(self, key: str) -> Any:
        return {
            "searchEnabled": self.search_enabled,
            "selfContainedOnly": self.self_contained_only,
            "chosen": self.chosen,
        }[key]

    def __iter__(self):
        return iter(("searchEnabled", "selfContainedOnly", "chosen"))

    def __len__(self) -> int:
        return 3


def _read(row: Any) -> ClipSettings:
    if row is None:
        return ClipSettings()
    return ClipSettings(
        search_enabled=row["search_enabled"],
        self_contained_only=row["self_contained_only"],
        chosen=True,
    )


def settings(owner: str) -> ClipSettings:
    with reading() as connection:
        row = connection.execute(
            select(tables.clip_settings).where(tables.clip_settings.c.owner == owner)
        ).mappings().first()
    return _read(row)


def save(owner: str, *, search_enabled: bool | None = None,
         self_contained_only: bool | None = None) -> ClipSettings:
    """Change only what is named. Returns the whole stored document, so a caller echoes disk.

    Read-modify-write inside one `transaction()`, which is `BEGIN IMMEDIATE`, so check-then-insert
    cannot interleave with a second save and the unique index is never reached in anger.

    There is deliberately no way to *forget* a row, as in `image_settings`: every field has a value
    that is meaningful on its own, so following the deployment default is a state you have simply
    not left rather than one you can be trapped outside of.
    """
    with transaction() as connection:
        row = connection.execute(
            select(tables.clip_settings).where(tables.clip_settings.c.owner == owner)
        ).mappings().first()
        current = _read(row)

        wanted = ClipSettings(
            search_enabled=current.search_enabled if search_enabled is None else search_enabled,
            self_contained_only=current.self_contained_only if self_contained_only is None
            else self_contained_only,
            chosen=True,
        )
        values = {
            "search_enabled": wanted.search_enabled,
            "self_contained_only": wanted.self_contained_only,
            "edited_at": now_instant(),
        }

        if row is None:
            connection.execute(
                tables.clip_settings.insert().values(id=new_record_id(), owner=owner, **values)
            )
        else:
            connection.execute(
                tables.clip_settings.update()
                .where(tables.clip_settings.c.id == row["id"])
                .values(**values)
            )
        return wanted
