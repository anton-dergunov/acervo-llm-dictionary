"""What the review history says: validation on the way in, statistics on the way out.

Anki keeps no statistics either — its own screen is computed from the same history every time it is
opened — so nothing here is stored twice. The history is kept whole (`repository/reviews.py`) and
read into figures when asked.

**Retention is true retention**: of the answers to scheduled reviews (`kind: review`), the share not
answered Again. Learning steps are left out, because a card still being learned is not a test of
memory, and neither are cram sessions, manual reschedules or Anki's own rescheduling.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Iterable, Mapping

from acervo.domain.ids import is_instant
from acervo.errors import ApiError

KINDS = ("learn", "review", "relearn", "filtered", "manual", "rescheduled")
BUTTONS = {1: "again", 2: "hard", 3: "good", 4: "easy"}
BATCH_LIMIT = 5000
RECORD_ID = 15


def _refuse(message: str) -> None:
    raise ApiError(400, "invalid_input", message)


def _whole(value: Any, label: str, low: int, high: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < low or (high is not None and value > high):
        _refuse(f"{label} must be a whole number from {low}{f' to {high}' if high is not None else ''}.")
    return value


def _days(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value:
        _refuse(f"{label} must be a number of days.")
    return float(value)


def _identifier(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) != RECORD_ID or not value.isalnum() or value != value.lower():
        _refuse(f"{label} must be a record id.")
    return value


def parse(body: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """A batch of reviews as the repository keeps them, or a refusal naming what is wrong."""
    system = body.get("system")
    if not isinstance(system, str) or not system.strip() or len(system) > 80:
        _refuse("system names the learning system the reviews come from.")
    reviews = body.get("reviews")
    if not isinstance(reviews, list):
        _refuse("reviews must be a list.")
    if len(reviews) > BATCH_LIMIT:
        _refuse(f"Send at most {BATCH_LIMIT} reviews at a time.")
    rows = []
    for review in reviews:
        if not isinstance(review, dict):
            _refuse("Each review must be an object.")
        kind = review.get("kind")
        if kind not in KINDS:
            _refuse(f"kind must be one of {', '.join(KINDS)}.")
        reviewed_at = review.get("reviewedAt")
        if not isinstance(reviewed_at, str) or not is_instant(reviewed_at):
            _refuse("reviewedAt must be an ISO-8601 UTC instant with milliseconds.")
        card_type = review.get("cardType")
        if not isinstance(card_type, str) or not card_type.strip() or len(card_type) > 32:
            _refuse("cardType names the card that was reviewed.")
        rows.append({
            "review_id": _whole(review.get("reviewId"), "reviewId", 1),
            "card_id": _whole(review.get("cardId"), "cardId", 1),
            "note_id": _whole(review.get("noteId"), "noteId", 1),
            "lexeme": _identifier(review.get("lexemeId"), "lexemeId"),
            "sense": _identifier(review.get("senseId"), "senseId", optional=True),
            "card_type": card_type.strip(),
            "reviewed_at": reviewed_at,
            "kind": kind,
            "button": _whole(review.get("button"), "button", 0, 4),
            "interval_days": _days(review.get("intervalDays"), "intervalDays"),
            "last_interval_days": _days(review.get("lastIntervalDays"), "lastIntervalDays"),
            "duration_ms": _whole(review.get("durationMs"), "durationMs", 0, 3_600_000),
        })
    return system.strip(), rows


def _rate(answered: int, passed: int) -> dict[str, Any]:
    return {"answered": answered, "passed": passed,
            "rate": round(passed / answered, 4) if answered else None}


def _local_day(instant: str, zone: tzinfo) -> date:
    return datetime.fromisoformat(instant.replace("Z", "+00:00")).astimezone(zone).date()


def statistics(
    rows: Iterable[Mapping[str, Any]],
    topics: Mapping[str, str],
    *,
    zone: tzinfo,
    today: date,
    days: int = 365,
    weeks: int = 12,
) -> dict[str, Any]:
    """The history as figures: totals, a day-by-day count for the last `days`, and retention overall,
    by week, by card type and by topic. Days are the owner's own, in `zone`."""
    per_day: Counter[date] = Counter()
    minutes_per_day: Counter[date] = Counter()
    words: set[str] = set()
    total_ms = 0
    count = 0
    answers: Counter[str] = Counter()
    by_week: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_topic: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    overall = [0, 0]
    for row in rows:
        day = _local_day(row["reviewed_at"], zone)
        count += 1
        per_day[day] += 1
        minutes_per_day[day] += row["duration_ms"] / 60000
        total_ms += row["duration_ms"]
        words.add(row["lexeme"])
        if row["kind"] != "review" or row["button"] not in BUTTONS:
            continue
        passed = int(row["button"] > 1)
        answers[BUTTONS[row["button"]]] += 1
        week = day - timedelta(days=day.weekday())
        for bucket in (overall, by_week[week], by_type[row["card_type"]],
                       *(by_topic[topics[topic]] for topic in row.get("topics") or [] if topic in topics)):
            bucket[0] += 1
            bucket[1] += passed

    streak = 0
    cursor = today if per_day.get(today) else today - timedelta(days=1)
    while per_day.get(cursor):
        streak += 1
        cursor -= timedelta(days=1)
    first_week = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    return {
        "totals": {
            "reviews": count,
            "words": len(words),
            "minutes": round(total_ms / 60000, 1),
            "daysStudied": len(per_day),
            "streak": streak,
        },
        "days": [
            {"date": day.isoformat(), "reviews": per_day.get(day, 0),
             "minutes": round(minutes_per_day.get(day, 0.0), 1)}
            for day in (today - timedelta(days=offset) for offset in range(days - 1, -1, -1))
        ],
        "retention": {
            **_rate(*overall),
            "weeks": [
                {"week": week.isoformat(), **_rate(*by_week.get(week, [0, 0]))}
                for week in (first_week + timedelta(weeks=offset) for offset in range(weeks))
            ],
            "byCardType": {name: _rate(*bucket) for name, bucket in sorted(by_type.items())},
            "byTopic": [
                {"topic": name, **_rate(*bucket)}
                for name, bucket in sorted(by_topic.items(), key=lambda item: (-item[1][0], item[0]))
            ],
        },
        "answers": {name: answers.get(name, 0) for name in BUTTONS.values()},
    }
