"""Usage: the provider package's attempts counted into a table, and read back for Settings.

`acervo.models.usage` reports every attempt at a model and stops, because the package may import
nothing of Acervo's. This module is the other half: it attaches the sink that writes the daily
counters (`repository/usage.py`), and it turns those counters into what Settings ▸ Providers ▸ Usage
shows (`docs/features/settings.md` §8).

**A day is a UTC day**, the same for every account on the server. Cloudflare's allowance resets at
00:00 UTC; Gemini's resets at midnight in California, so its gauge runs some hours off — closer than
any one owner's own midnight would be to either. "This month" is the UTC calendar month, which is how
the monthly allowances are metered.

**Counting never fails a call.** A count that cannot be written is the one new way this adds to fail,
and it is said in `activity.log` as `usage not counted`, with the sentence, so `admin log --failed`
shows it; the answer goes on to whoever asked.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from acervo import activity
from acervo.domain.ids import instant_of
from acervo.models import usage
from acervo.models.families import KINDS
from acervo.repository import usage as counters
from acervo.services import providers as stored_providers
from acervo.settings import Settings

# How many days a model's own page draws, and the window its failures and speed are read over.
WINDOW = 30

# What an allowance in each unit is measured against: every attempt for `calls`, because a refused
# request spends a free one; what was used up for the rest.
_MEASURED = {
    "calls": lambda counts: counts["calls"],
    "tokens": lambda counts: counts["inputTokens"] + counts["outputTokens"],
    "pictures": lambda counts: counts["pictures"],
    "characters": lambda counts: counts["characters"],
    "photos": lambda counts: counts["photos"],
}


def _now() -> datetime:
    """The moment, in UTC. A seam: the tests move the day."""
    return datetime.now(timezone.utc)


# ── counting ─────────────────────────────────────────────────────────────────


def sink(attempt: usage.Attempt) -> None:
    """Add one attempt to its day's counters, or say why it could not be."""
    try:
        moment = _now()
        spent = attempt.spent
        counters.record(
            moment.date().isoformat(), attempt.provider, attempt.model, attempt.kind,
            reason=attempt.reason, seconds=attempt.seconds, at=instant_of(moment),
            detail=attempt.detail,
            units={name: getattr(spent, name) for name in counters.UNITS},
            cost_usd=attempt.cost_usd,
        )
    except Exception as error:  # noqa: BLE001 — a count must never fail the call it counts
        activity.note("usage not counted", failed=True, provider=attempt.provider,
                      model=attempt.model, kind=attempt.kind, caller=attempt.caller,
                      error=str(error) or type(error).__name__)


def open_usage() -> None:
    """Hand the provider package the sink. Idempotent, like `open_call_log`."""
    usage.attach(sink)


# ── reading back ─────────────────────────────────────────────────────────────


def _empty() -> dict[str, Any]:
    return {"calls": 0, "failed": 0, "inputTokens": 0, "outputTokens": 0, "characters": 0,
            "pictures": 0, "photos": 0, "costUsd": None}


def _counts(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Counter rows (or sums of them) as the wire carries them."""
    found = _empty()
    for row in rows:
        calls = int(row.get("calls") or 0)
        succeeded = int(row.get("succeeded") or 0)
        found["calls"] += calls
        found["failed"] += calls - succeeded
        found["inputTokens"] += int(row.get("input_tokens") or 0)
        found["outputTokens"] += int(row.get("output_tokens") or 0)
        found["characters"] += int(row.get("characters") or 0)
        found["pictures"] += int(row.get("pictures") or 0)
        found["photos"] += int(row.get("photos") or 0)
        if row.get("cost_usd") is not None:
            found["costUsd"] = (found["costUsd"] or 0.0) + float(row["cost_usd"])
    return found


def _added(one: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    summed = {name: one[name] + other[name] for name in one if name != "costUsd"}
    costs = [value for value in (one["costUsd"], other["costUsd"]) if value is not None]
    summed["costUsd"] = sum(costs) if costs else None
    return summed


def view(settings: Settings) -> dict[str, Any]:
    """Everything every Usage page shows, in one answer, so switching period asks nothing again.

    A model is listed when it has ever been counted, or when it has an allowance — a gauge at nought
    still says how much is left. Providers come in the order they were added, each one's models in
    the order of their kinds and then as added; one that was counted and is no longer on the server
    follows under its id, because the calls were made and "all time" is the sum of the table.
    """
    today = _now().date()
    month = today.replace(day=1)
    window = [today - timedelta(days=offset) for offset in range(WINDOW - 1, -1, -1)]
    rows = counters.days(min(month, window[0]).isoformat())
    totals = {(row["provider"], row["model"], row["kind"]): row for row in counters.totals()}
    last = counters.last_failures()
    catalogue = stored_providers.load(settings)

    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_key.setdefault((row["provider"], row["model"], row["kind"]), []).append(row)

    present = {row.id for row in catalogue}
    groups: list[dict[str, Any]] = []
    for row in catalogue:
        offered = [(kind, model) for kind in KINDS for model in row.models_for(kind)]
        counted = sorted((kind, model) for provider, model, kind in totals
                         if provider == row.id and (kind, model) not in offered)
        listed = [(kind, model) for kind, model in offered
                  if (row.id, model, kind) in totals or _allowance_of(row.model(kind, model))] + counted
        models = [_model(row.id, model, kind, row.model(kind, model), (kind, model) in offered,
                         by_key, totals, last, today, month, window)
                  for kind, model in listed]
        if models:
            groups.append({"id": row.id, "label": row.label, "present": True, "models": models})
    for identifier in sorted({provider for provider, _, _ in totals} - present):
        models = [_model(identifier, model, kind, None, False, by_key, totals, last, today, month, window)
                  for provider, model, kind in sorted(totals, key=lambda key: (key[2], key[1]))
                  if provider == identifier]
        groups.append({"id": identifier, "label": identifier, "present": False, "models": models})

    summed = {period: _empty() for period in ("today", "month", "all")}
    for group in groups:
        for model in group["models"]:
            for period in summed:
                summed[period] = _added(summed[period], model[period])
    return {"day": today.isoformat(), "totals": summed, "providers": groups}


def _day(day: str, row: dict[str, Any] | None) -> dict[str, Any]:
    """One bar of a model's chart: what answered that day, and what did not."""
    succeeded = int(row["succeeded"]) if row else 0
    return {"day": day, "succeeded": succeeded, "failed": int(row["calls"]) - succeeded if row else 0}


def _allowance_of(stored) -> dict[str, Any] | None:
    """A stored model's free allowance, or None — for a model the provider no longer offers too."""
    return dict(stored.allowance) if stored is not None and stored.allowance else None


def _model(provider: str, model: str, kind: str, stored, offered: bool,
           by_key: dict[tuple[str, str, str], list[dict[str, Any]]],
           totals: dict[tuple[str, str, str], dict[str, Any]],
           last: dict[tuple[str, str, str], dict[str, Any]],
           today: date, month: date, window: list[date]) -> dict[str, Any]:
    key = (provider, model, kind)
    rows = by_key.get(key, [])
    on = {row["day"]: row for row in rows}
    start = window[0].isoformat()
    recent = [row for row in rows if row["day"] >= start]
    counts = {
        "today": _counts(row for row in rows if row["day"] == today.isoformat()),
        "month": _counts(row for row in rows if row["day"] >= month.isoformat()),
        "all": _counts([totals[key]] if key in totals else []),
        # The last thirty days, which the model's own page reads in.
        "window": _counts(recent),
    }
    failures: dict[str, int] = {}
    for row in recent:
        for reason, count in (row["failures"] or {}).items():
            failures[reason] = failures.get(reason, 0) + int(count)
    answered = sum(int(row["succeeded"]) for row in recent)
    allowance = _allowance_of(stored)
    gauge = None
    if allowance is not None:
        measured = _MEASURED.get(allowance["unit"], _MEASURED["calls"])
        gauge = {**allowance, "used": measured(counts["today" if allowance["per"] == "day" else "month"])}
    failure = last.get(key)
    return {
        "model": model,
        "kind": kind,
        "offered": offered,
        "allowance": allowance,
        "gauge": gauge,
        **counts,
        "days": [_day(day.isoformat(), on.get(day.isoformat())) for day in window],
        "failures": failures,
        "seconds": round(sum(float(row["seconds"]) for row in recent) / answered, 2) if answered else None,
        "lastFailure": {"said": failure["last_failure"] or "", "reason": failure["last_reason"],
                        "at": failure["last_failure_at"]} if failure else None,
    }
