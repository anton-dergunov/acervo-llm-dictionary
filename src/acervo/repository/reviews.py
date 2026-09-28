"""Every review a learning system recorded, kept on the server.

Append-only and never replicated (see `db/tables.py`, `reviews`). A review is written once and never
changed: the same review sent again, under the same id, adds nothing — which is what lets a nightly
pull send a generous window rather than track exactly what it sent last time.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, select

from acervo.db import tables
from acervo.domain.ids import now_instant
from acervo.repository.session import reading, transaction

COLUMNS = (
    "review_id", "card_id", "note_id", "lexeme", "sense", "card_type", "reviewed_at", "kind",
    "button", "interval_days", "last_interval_days", "duration_ms",
)


def latest(owner: str, system: str) -> int | None:
    """The newest review id held for this system, or None before the first."""
    table = tables.reviews
    with reading() as connection:
        return connection.execute(
            select(func.max(table.c.review_id)).where(table.c.owner == owner, table.c.system == system)
        ).scalar()


def record(owner: str, system: str, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Keep the reviews this owner's words account for; answer how many were new.

    A review of a word the owner does not hold — another account's id, or one never held — is left
    out and counted, not refused: the scheduler keeps cards Acervo has forgotten, and one of those
    must not stop a year of history from being written. A word Acervo has since deleted still
    counts: its history happened.
    """
    rows = list(rows)
    lexemes, senses = tables.lexemes, tables.senses
    table = tables.reviews
    at = now_instant()
    with transaction() as connection:
        held = set(connection.execute(
            select(lexemes.c.id).where(lexemes.c.owner == owner,
                                       lexemes.c.id.in_({row["lexeme"] for row in rows}))
        ).scalars())
        meanings = dict(connection.execute(
            select(senses.c.id, senses.c.lexeme).where(
                senses.c.owner == owner, senses.c.id.in_({row["sense"] for row in rows if row["sense"]}))
        ).all())
        kept = [
            row for row in rows
            if row["lexeme"] in held and (not row["sense"] or meanings.get(row["sense"]) == row["lexeme"])
        ]
        before = _count(connection, owner, system)
        if kept:
            connection.execute(
                table.insert().prefix_with("OR IGNORE"),
                [{**{name: row[name] for name in COLUMNS}, "owner": owner, "system": system,
                  "received_at": at} for row in kept],
            )
        added = _count(connection, owner, system) - before
    return {"received": len(rows), "added": added, "known": len(kept) - added,
            "skipped": len(rows) - len(kept)}


def _count(connection, owner: str, system: str) -> int:
    table = tables.reviews
    return connection.execute(
        select(func.count()).select_from(table).where(table.c.owner == owner, table.c.system == system)
    ).scalar_one()


def history(owner: str, *, language: str | None = None, since: str | None = None) -> list[dict[str, Any]]:
    """This owner's reviews, oldest first, each with its word's language and topics."""
    table, lexemes = tables.reviews, tables.lexemes
    query = (
        select(table.c.system, table.c.review_id, table.c.lexeme, table.c.sense, table.c.card_type,
               table.c.reviewed_at, table.c.kind, table.c.button, table.c.interval_days,
               table.c.duration_ms, lexemes.c.language, lexemes.c.topics)
        .join(lexemes, lexemes.c.id == table.c.lexeme)
        .where(table.c.owner == owner)
        .order_by(table.c.reviewed_at, table.c.review_id)
    )
    if language:
        query = query.where(lexemes.c.language == language)
    if since:
        query = query.where(table.c.reviewed_at >= since)
    with reading() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def topic_names(owner: str) -> dict[str, str]:
    """This owner's live topics, by id: what a review's word is filed under, by name."""
    table = tables.topics
    with reading() as connection:
        return dict(connection.execute(
            select(table.c.id, table.c.name).where(table.c.owner == owner, table.c.deleted.is_(False))
        ).all())
