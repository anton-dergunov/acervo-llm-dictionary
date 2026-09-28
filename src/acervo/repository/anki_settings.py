"""Whether this owner's Anki is kept up to date by the server. One row per owner, or none.

The same doctrine as the other settings tables: **no row means the defaults**, and here the defaults
are both off, so a server with no Anki behind it queues nothing. Bootstrapping the collection is what
turns them on; the owner turns them off and on again in Settings ▸ Anki.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction

# The two jobs, named here because the write that queues a push is in `repository/graph.py`, which
# may not reach into `work/` where they run.
PUSH = "anki.push"
PULL = "anki.pull"
SUBJECT = "anki"

# What the cards are made from (`consumers/anki/build.py`). A write to any of these may change a
# card; study states are what a pull writes, and counting them would make every pull queue a push.
READ_BY_CARDS = frozenset({
    "vocabularies", "topics", "lexemes", "senses", "attestations", "examples", "imagePrompts",
    "pronunciations",
})


@dataclass(frozen=True)
class AnkiSettings:
    push: bool = False
    pull: bool = False


def _read(row) -> AnkiSettings:
    return AnkiSettings() if row is None else AnkiSettings(push=bool(row["push"]), pull=bool(row["pull"]))


def _row(connection, owner: str):
    table = tables.anki_settings
    return connection.execute(select(table).where(table.c.owner == owner)).mappings().first()


def settings(owner: str) -> AnkiSettings:
    with reading() as connection:
        return _read(_row(connection, owner))


def pushing(connection, owner: str) -> bool:
    """Whether a change to this owner's vocabulary should reach Anki, read inside the caller's
    transaction so the write and the push it queues are one decision."""
    return _read(_row(connection, owner)).push


def pulling_owners() -> list[str]:
    table = tables.anki_settings
    with reading() as connection:
        return [row.owner for row in connection.execute(
            select(table.c.owner).where(table.c.pull.is_(True)).order_by(table.c.owner))]


def save(owner: str, *, push: bool | None = None, pull: bool | None = None) -> AnkiSettings:
    """Change only what is named. Returns the whole stored document."""
    with transaction() as connection:
        table = tables.anki_settings
        row = _row(connection, owner)
        current = _read(row)
        wanted = AnkiSettings(push=current.push if push is None else bool(push),
                              pull=current.pull if pull is None else bool(pull))
        values = {"push": wanted.push, "pull": wanted.pull, "edited_at": now_instant()}
        if row is None:
            connection.execute(table.insert().values(id=new_record_id(), owner=owner, **values))
        else:
            connection.execute(table.update().where(table.c.id == row["id"]).values(**values))
        return wanted
