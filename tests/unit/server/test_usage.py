"""`GET /usage`: what this server has asked of each model, counted from every attempt.

Against the real application, whose start attaches the sink, so a model call made through the
binding layer lands in the table the route reads — the path a capture takes, rather than a counter
written by hand. The periods are moved with the service's clock, because a day is a UTC day and a
test that ran at midnight would otherwise see two.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from acervo import activity
from acervo.models import usage
from acervo.models.results import Spent
from acervo.services import usage as counting
from acervo.services.models import llm_json
from provider_rows import GOOGLE

FIRST, SECOND = "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"


@pytest.fixture
def clock(monkeypatch):
    """The service's moment, settable: `clock.at("2026-11-06")`."""
    class Clock:
        moment = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)

        def at(self, day: str, hour: int = 12) -> None:
            self.moment = datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc)

    found = Clock()
    monkeypatch.setattr(counting, "_now", lambda: found.moment)
    return found


def attempt(model=FIRST, provider="gemini-api", kind="text", reason=None, **fields):
    usage.report(usage.Attempt(kind, provider, model, "test", reason, fields.pop("seconds", 1.0),
                               fields.pop("detail", ""), **fields))


def readout(server):
    answer = server.get("/usage")
    assert answer.status_code == 200, answer.text
    return answer.json()["data"]


def model_of(data, provider, model):
    group = next(group for group in data["providers"] if group["id"] == provider)
    return next(entry for entry in group["models"] if entry["model"] == model)


def test_a_fall_through_counts_the_refusal_and_the_answer(server, clock):
    """The capture path: the first model is out of allowance, the second answers. Both were calls."""
    server.model.limited = {f"gemini/{FIRST}"}
    llm_json(server.settings, server.owner, "Return a single JSON object.", "picar", caller="capture")
    data = readout(server)
    first, second = model_of(data, "gemini-api", FIRST), model_of(data, "gemini-api", SECOND)
    assert first["today"]["calls"] == 1 and first["today"]["failed"] == 1
    assert first["failures"] == {"rate_limited": 1}
    assert first["lastFailure"]["reason"] == "rate_limited"
    # The provider's own sentence survives the hand-off, rather than a constant replacing it.
    assert "provider details" in first["lastFailure"]["said"]
    assert (second["today"]["calls"], second["today"]["failed"]) == (1, 0)
    assert second["seconds"] is not None and second["lastFailure"] is None
    assert data["totals"]["today"]["calls"] == 2 and data["totals"]["today"]["failed"] == 1
    assert data["day"] == "2026-11-06"


def test_the_periods_are_utc_days_and_calendar_months(server, clock):
    clock.at("2026-10-31", hour=23)
    attempt(spent=Spent(input_tokens=10))
    clock.at("2026-11-01", hour=0)
    attempt(spent=Spent(input_tokens=20))
    clock.at("2026-11-06")
    attempt(spent=Spent(input_tokens=40, output_tokens=2))
    entry = model_of(readout(server), "gemini-api", FIRST)
    assert [entry[period]["calls"] for period in ("today", "month", "all", "window")] == [1, 2, 3, 3]
    assert entry["all"]["inputTokens"] == 70 and entry["today"]["outputTokens"] == 2
    # Thirty bars, oldest first, ending today; 31 October is one of them.
    assert len(entry["days"]) == 30 and entry["days"][-1]["day"] == "2026-11-06"
    assert {day["day"]: day["succeeded"] for day in entry["days"]}["2026-10-31"] == 1


def test_a_gauge_measures_against_its_allowances_own_unit_and_period(server, clock):
    server.add_provider({**GOOGLE, "models": {
        "audio": [{"id": "Wavenet", "allowance": {"amount": 1000, "unit": "characters", "per": "month"}}],
        "ocr": [{"id": "document-text-detection", "allowance": {"amount": 10, "unit": "calls", "per": "day"}}],
    }})
    clock.at("2026-11-02")
    attempt("Wavenet", "google-cloud", "audio", spent=Spent(characters=300))
    clock.at("2026-11-06")
    attempt("Wavenet", "google-cloud", "audio", spent=Spent(characters=200))
    attempt("document-text-detection", "google-cloud", "ocr", reason="rate_limited", detail="quota")
    attempt("document-text-detection", "google-cloud", "ocr", spent=Spent(photos=1))
    data = readout(server)
    assert model_of(data, "google-cloud", "Wavenet")["gauge"] == {
        "amount": 1000, "unit": "characters", "per": "month", "used": 500}
    # Calls are every attempt: the 429 spent a free request too.
    assert model_of(data, "google-cloud", "document-text-detection")["gauge"]["used"] == 2


def test_a_model_with_an_allowance_is_listed_before_its_first_call(server, clock):
    server.add_provider({**GOOGLE, "models": {
        "audio": ["Standard", {"id": "Wavenet", "allowance": {"amount": 4, "unit": "calls", "per": "day"}}]}})
    group = next(group for group in readout(server)["providers"] if group["id"] == "google-cloud")
    assert [(entry["model"], entry["gauge"]["used"]) for entry in group["models"]] == [("Wavenet", 0)]


def test_a_removed_provider_keeps_its_calls_under_its_id(server, clock):
    server.add_provider(GOOGLE)
    attempt("Wavenet", "google-cloud", "audio", spent=Spent(characters=5))
    server.remove_provider("google-cloud")
    data = readout(server)
    group = next(group for group in data["providers"] if group["id"] == "google-cloud")
    assert group["present"] is False and group["label"] == "google-cloud"
    assert group["models"][0]["offered"] is False and group["models"][0]["all"]["characters"] == 5
    assert data["providers"][-1]["id"] == "google-cloud"


def test_speed_is_the_mean_of_the_calls_that_answered(server, clock):
    attempt(seconds=1.0)
    attempt(seconds=3.0)
    attempt(reason="unreachable", seconds=30.0, detail="timed out")
    assert model_of(readout(server), "gemini-api", FIRST)["seconds"] == 2.0


def test_a_count_that_cannot_be_written_says_so_and_the_call_still_answers(server, clock, monkeypatch, caplog):
    """The one new way this can fail, and where `admin log --failed` finds it."""
    caplog.set_level(logging.INFO, logger=activity.LOGGER)

    def locked(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(counting.counters, "record", locked)
    parsed, answer = llm_json(server.settings, server.owner, "Return a single JSON object.", "picar")
    assert answer.model == FIRST
    [line] = [record for record in caplog.records if record.getMessage().startswith("usage not counted")]
    assert line.levelno == logging.WARNING
    assert "provider=gemini-api" in line.getMessage() and 'error="database is locked"' in line.getMessage()


def test_usage_needs_a_session(server):
    assert server.client.get("/api/acervo/v1/usage").status_code == 401
