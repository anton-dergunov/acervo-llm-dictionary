"""What the writer wrote for each loop, kept on the server to render the same lines again.

A loop made in a format that takes text from a writer — a radio lesson, a story — gets that text
from one model call during its render. The generator returns the text it read (`script`), and this
keeps it, one row per loop, so that new music sends it back and the loop says the same lines rather
than asking for new ones: the same words, the same examples, the same story, and every take already
in the cache.

**Never replicated.** It is the generator's shape, read by nothing on this side and needed by no
device, so it lives beside `jobs` rather than in the graph: one row per loop, replaced whole by the
next render and removed with the loop.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from acervo.db import tables
from acervo.domain.ids import now_instant
from acervo.repository.session import reading, transaction


def script(owner: str, loop_id: str) -> dict[str, Any] | None:
    """The script this loop's last render returned, or None when it had none."""
    table = tables.loop_scripts
    with reading() as connection:
        row = connection.execute(
            select(table.c.script).where(table.c.loop == loop_id, table.c.owner == owner)
        ).first()
    return dict(row.script) if row is not None and isinstance(row.script, dict) else None


def keep(owner: str, loop_id: str, format_id: str, written: dict[str, Any] | None) -> None:
    """Replace this loop's script with the one its render just returned, or remove it for none."""
    table = tables.loop_scripts
    with transaction() as connection:
        connection.execute(delete(table).where(table.c.loop == loop_id, table.c.owner == owner))
        if written is not None:
            connection.execute(table.insert().values(
                loop=loop_id, owner=owner, format=format_id, script=written,
                written_at=now_instant()))


def forget(owner: str, loop_id: str) -> None:
    """Remove this loop's script: the loop is gone, and nothing will render it again."""
    table = tables.loop_scripts
    with transaction() as connection:
        connection.execute(delete(table).where(table.c.loop == loop_id, table.c.owner == owner))
