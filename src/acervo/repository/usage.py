"""The daily counters behind Settings ▸ Providers ▸ Usage: one row a UTC day per (provider, model,
kind), added to once for every attempt at a model.

This module stores counts it is given. What a provider is and which reasons exist are the provider
package's to say, and the binding layer (`services/usage.py`) says them; this module cannot import
`acervo.models` and does not need to.

**A count is read and written in one `BEGIN IMMEDIATE`**, so two raced pairs finishing at once add
to the row one after the other rather than one over the other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select

from acervo.db import tables
from acervo.repository.session import reading, transaction

# The counters a row holds, each summed by `totals`.
UNITS = ("input_tokens", "output_tokens", "characters", "pictures", "photos")


def record(day: str, provider: str, model: str, kind: str, *, reason: str | None, seconds: float,
           at: str, detail: str = "", units: Mapping[str, int] | None = None,
           cost_usd: float | None = None) -> None:
    """Add one attempt to its day's row. `reason` None means it answered."""
    table = tables.model_usage
    key = (table.c.day == day) & (table.c.provider == provider) & (table.c.model == model) \
        & (table.c.kind == kind)
    units = {name: int((units or {}).get(name) or 0) for name in UNITS}
    with transaction() as connection:
        row = connection.execute(select(table).where(key)).mappings().first()
        found = dict(row) if row is not None else {
            "day": day, "provider": provider, "model": model, "kind": kind, "calls": 0,
            "succeeded": 0, "failures": {}, "seconds": 0.0, **{name: 0 for name in UNITS},
            "cost_usd": None, "last_failure": None, "last_reason": None, "last_failure_at": None,
        }
        found["calls"] += 1
        if reason is None:
            found["succeeded"] += 1
            found["seconds"] += seconds
            for name in UNITS:
                found[name] += units[name]
            if cost_usd is not None:
                found["cost_usd"] = (found["cost_usd"] or 0.0) + cost_usd
        else:
            failures = dict(found["failures"] or {})
            failures[reason] = int(failures.get(reason, 0)) + 1
            found["failures"] = failures
            found["last_failure"] = detail or None
            found["last_reason"] = reason
            found["last_failure_at"] = at
        if row is None:
            connection.execute(table.insert().values(**found))
        else:
            connection.execute(table.update().where(key).values(
                **{name: value for name, value in found.items()
                   if name not in ("day", "provider", "model", "kind")}))


def totals() -> list[dict[str, Any]]:
    """Every (provider, model, kind) ever counted, summed over all time."""
    table = tables.model_usage
    columns = [table.c.provider, table.c.model, table.c.kind]
    with reading() as connection:
        rows = connection.execute(
            select(*columns, func.sum(table.c.calls).label("calls"),
                   func.sum(table.c.succeeded).label("succeeded"),
                   *(func.sum(table.c[name]).label(name) for name in UNITS),
                   func.sum(table.c.cost_usd).label("cost_usd"))
            .group_by(*columns)
        ).mappings().all()
    return [dict(row) for row in rows]


def days(since: str) -> list[dict[str, Any]]:
    """Every row from `since` (a UTC day, inclusive) on, oldest first."""
    table = tables.model_usage
    with reading() as connection:
        rows = connection.execute(
            select(table).where(table.c.day >= since).order_by(table.c.day)
        ).mappings().all()
    return [dict(row) for row in rows]


def last_failures() -> dict[tuple[str, str, str], dict[str, Any]]:
    """The latest failure of each (provider, model, kind) that has ever failed."""
    table = tables.model_usage
    with reading() as connection:
        rows = connection.execute(
            select(table.c.provider, table.c.model, table.c.kind, table.c.last_failure,
                   table.c.last_reason, table.c.last_failure_at)
            .where(table.c.last_failure_at.is_not(None))
            .order_by(table.c.last_failure_at.desc())
        ).mappings().all()
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        latest.setdefault((row["provider"], row["model"], row["kind"]), dict(row))
    return latest
