"""The nightly run, its timer, and the corpus update it starts (`docs/architecture/jobs.md`)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import pytest

from acervo.repository import jobs, schedule_settings
from acervo.services import schedule
from acervo.work import corpus as corpus_kind
from acervo.work import nightly
from acervo.work.runner import Runner

SPEECH_URL = "http://speech-retrieval:8000/api/v1"


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(timezone.utc)


class Clock:
    def __init__(self, moment: str | None = None) -> None:
        # A job is stamped with the real time, so a test comparing runs against "now" uses it too.
        self.now = at(moment).timestamp() if moment else time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CorpusOperations:
    """The retrieval service's operation routes, at the HTTP boundary."""

    def __init__(self) -> None:
        # What each look after the start answers; the last one repeats.
        self.states = ["completed"]
        self.successful = True
        self.started = 0
        self.headers: list[dict] = []

    def _answer(self, url, status):
        request = httpx.Request("GET", url)
        body = {"operation_id": "op-1", "operation": "update", "status": status,
                "successful": self.successful if status == "completed" else None,
                "created_at": "2026-09-17T02:00:00+00:00"}
        return httpx.Response(202 if status == "queued" else 200, json=body, request=request)

    def post(self, url, *, json=None, timeout=None, headers=None, **kwargs):
        assert url.endswith("/corpus/operations")
        self.started += 1
        self.headers.append(headers or {})
        return self._answer(url, "queued")

    def get(self, url, *, params=None, timeout=None, headers=None, **kwargs):
        assert url.endswith("/corpus/operations/op-1")
        self.headers.append(headers or {})
        return self._answer(url, self.states.pop(0) if len(self.states) > 1 else self.states[0])


@pytest.fixture
def corpus(server, monkeypatch) -> CorpusOperations:
    from acervo.clips import corpus as corpus_module

    stub = CorpusOperations()
    monkeypatch.setattr(corpus_module.httpx, "post", stub.post)
    monkeypatch.setattr(corpus_module.httpx, "get", stub.get)
    monkeypatch.setattr(server.settings, "speech_url", SPEECH_URL)
    monkeypatch.setattr(server.settings, "speech_operator_token", "operator-token")
    return stub


def settle(runner: Runner, clock: Clock, rounds: int = 5) -> None:
    """Run, and let every poll interval pass, until nothing is left waiting."""
    for _ in range(rounds):
        runner.run_until_idle()
        clock.advance(corpus_kind.POLL_SECONDS + 1)


@pytest.fixture
def madrid(server, monkeypatch):
    monkeypatch.setattr(server.settings, "timezone", "Europe/Madrid")
    return server.settings


# ── when ────────────────────────────────────────────────────────────────────


def test_the_hour_is_read_in_the_deployments_zone(madrid):
    # 01:30 in Madrid in September is 23:30 UTC the day before; the last 02:00 was the night before.
    assert schedule.last_scheduled(madrid, 2, at("2026-09-17T01:30:00+02:00")) == at(
        "2026-09-16T02:00:00+02:00"
    )
    assert schedule.last_scheduled(madrid, 2, at("2026-09-17T02:00:00+02:00")) == at(
        "2026-09-17T02:00:00+02:00"
    )
    assert schedule.next_scheduled(madrid, 2, at("2026-09-17T02:30:00+02:00")) == at(
        "2026-09-18T02:00:00+02:00"
    )


def test_a_run_is_due_once_after_the_hour_and_not_again_that_night(server, madrid):
    before = at("2026-09-17T01:59:00+02:00")
    after = at("2026-09-17T02:01:00+02:00")
    assert nightly.due(madrid, server.owner, before) is True  # never run: the missed night runs once

    queued = jobs.enqueue(server.owner, "nightly", trigger="schedule",
                          subject_kind="schedule", subject_id="nightly")
    assert nightly.due(madrid, server.owner, after) is False  # one is open
    jobs.request_cancel(server.owner, queued["id"])
    # It was created now, which is after last night's hour — so tonight's is still due only once
    # tonight's hour has struck.
    assert nightly.due(madrid, server.owner, at("2026-09-17T01:00:00+02:00")) is False


def test_nothing_is_due_when_every_step_is_off(server, madrid):
    schedule_settings.save(server.owner, steps={"corpus.update": False})
    assert nightly.due(madrid, server.owner, at("2026-09-17T03:00:00+02:00")) is False


def test_the_timer_queues_one_run_and_looks_at_most_once_a_minute(server, madrid, monkeypatch):
    clock = Clock("2026-09-17T02:00:30+02:00")
    looks = []
    real = nightly.due
    monkeypatch.setattr(nightly, "due", lambda *args: looks.append(1) or real(*args))
    tick = nightly.timer(madrid, clock)

    tick()
    tick()  # within the minute: not even asked
    assert len(looks) == 1
    assert [job["trigger"] for job in jobs.open_jobs(server.owner)] == ["schedule"]

    clock.advance(61)
    tick()
    assert len(looks) == 2
    assert len(jobs.open_jobs(server.owner)) == 1, "an open run is not queued twice"


def test_missed_nights_do_not_pile_up(server, madrid):
    clock = Clock()  # nothing has ever run: every night so far was missed
    # **The hour is pinned two hours behind now, and it has to be.** A job is stamped with the real
    # time while the timer reads this clock, so advancing an hour past the scheduled hour makes a
    # genuinely new night due — correctly. With the default hour of 2 this test therefore failed
    # for the whole of 01:00–02:00 in the deployment's zone and passed the other 23 hours, which is
    # a time bomb rather than a test. Two hours back keeps `last_scheduled` on the same instant
    # before and after the advance, so what is measured is repeat queueing *within* one window.
    local_hour = datetime.fromtimestamp(clock.now, timezone.utc).astimezone(
        schedule.zone(madrid)
    ).hour
    schedule_settings.save(server.owner, hour=(local_hour - 2) % 24)

    runner = Runner(madrid, clock=clock)
    runner.ticks.append(nightly.timer(madrid, clock))
    runner.run_until_idle()
    runs = [job for job in jobs.recent(server.owner) if job["kind"] == "nightly"]
    assert len(runs) == 1
    clock.advance(3600)
    runner.run_until_idle()
    assert len([job for job in jobs.recent(server.owner) if job["kind"] == "nightly"]) == 1


def test_the_next_night_is_due_once_its_hour_has_struck(server, madrid):
    """The other half, and the behaviour the test above used to trip over by accident.

    Not piling up must not mean never running again: once the scheduled hour passes, the next
    night's run is due even though the previous one was queued only an hour earlier.
    """
    clock = Clock()
    local = datetime.fromtimestamp(clock.now, timezone.utc).astimezone(schedule.zone(madrid))
    # The hour strikes one hour from now, so the advance below crosses it.
    schedule_settings.save(server.owner, hour=(local.hour + 1) % 24)

    runner = Runner(madrid, clock=clock)
    runner.ticks.append(nightly.timer(madrid, clock))
    runner.run_until_idle()
    assert len([job for job in jobs.recent(server.owner) if job["kind"] == "nightly"]) == 1

    clock.advance(3600 * 2)
    runner.run_until_idle()
    assert len([job for job in jobs.recent(server.owner) if job["kind"] == "nightly"]) == 2


def test_a_runner_built_outside_the_application_queues_no_nights(server):
    Runner(server.settings).run_until_idle()
    assert jobs.open_jobs(server.owner) == []


def test_the_served_application_carries_the_timer(server):
    """The nightly timer, the hourly Anki read, and the sweep of photos nobody added."""
    assert len(server.client.app.state.runner.ticks) == 3


# ── the nightly run ─────────────────────────────────────────────────────────


def test_the_nightly_run_updates_the_corpus_and_skips_what_is_off(server, corpus, madrid):
    corpus.states = ["running", "completed"]
    clock = Clock()
    runner = Runner(madrid, clock=clock)
    job = jobs.enqueue(server.owner, "nightly", trigger="schedule",
                       subject_kind="schedule", subject_id="nightly")

    runner.run_until_idle()
    following = jobs.get(server.owner, job["id"])
    assert following["state"] == "queued", "it waits while the corpus works, rather than blocking"
    assert following["steps"][0]["state"] == "waiting"
    assert following["steps"][0]["detail"]["operationId"] == "op-1"

    settle(runner, clock)
    finished = jobs.get(server.owner, job["id"])
    assert finished["state"] == "done"
    assert [(step["name"], step["state"]) for step in finished["steps"]] == [
        ("corpus.update", "done")
    ]
    assert corpus.started == 1
    # The operator token goes to the corpus and nowhere else.
    assert all(headers.get("Authorization") == "Bearer operator-token" for headers in corpus.headers)


def test_a_failed_step_fails_the_run_and_says_why(server, corpus, madrid):
    corpus.states = ["failed"]
    job = jobs.enqueue(server.owner, "nightly", trigger="schedule",
                       subject_kind="schedule", subject_id="nightly")
    clock = Clock()
    settle(Runner(madrid, clock=clock), clock)
    finished = jobs.get(server.owner, job["id"])
    assert finished["state"] == "failed"
    assert [(step["name"], step["state"], step.get("error")) for step in finished["steps"]] == [
        ("corpus.update", "failed", "corpus_failed"),
    ]


def test_an_update_that_left_channels_out_says_so(server, corpus, madrid):
    corpus.states = ["completed"]
    corpus.successful = False
    job = jobs.enqueue(server.owner, "corpus.update", trigger="manual",
                       subject_kind="corpus", subject_id="corpus")
    clock = Clock()
    settle(Runner(madrid, clock=clock), clock)
    assert jobs.get(server.owner, job["id"])["error"] == "corpus_incomplete"


def test_a_deployment_without_a_corpus_skips_the_step(server, madrid):
    job = jobs.enqueue(server.owner, "nightly", trigger="schedule",
                       subject_kind="schedule", subject_id="nightly")
    Runner(madrid).run_until_idle()
    finished = jobs.get(server.owner, job["id"])
    assert finished["state"] == "done"
    assert finished["steps"][0]["state"] == "skipped"


def test_a_corpus_without_an_operator_token_cannot_be_updated(server, corpus, madrid, monkeypatch):
    monkeypatch.setattr(server.settings, "speech_operator_token", "")
    job = jobs.enqueue(server.owner, "corpus.update", trigger="manual",
                       subject_kind="corpus", subject_id="corpus")
    Runner(madrid).run_until_idle()
    assert jobs.get(server.owner, job["id"])["error"] == "corpus_unmanaged"
    assert corpus.started == 0


def test_an_update_that_never_ends_is_no_longer_followed(server, corpus, madrid, monkeypatch):
    monkeypatch.setattr(corpus_kind, "MAX_POLLS", 2)
    corpus.states = ["running"]
    clock = Clock()
    runner = Runner(madrid, clock=clock)
    job = jobs.enqueue(server.owner, "corpus.update", trigger="manual",
                       subject_kind="corpus", subject_id="corpus")
    settle(runner, clock)
    assert jobs.get(server.owner, job["id"])["error"] == "corpus_timeout"


# ── Update now ──────────────────────────────────────────────────────────────


def test_update_now_is_one_job_however_often_it_is_pressed(server, corpus):
    first = server.post("/jobs", {"kind": "corpus.update"})
    assert first.status_code == 202, first.json()
    assert first.json()["data"]["subject"] == {"kind": "corpus", "id": "corpus"}
    jobs.claim_next("9999-12-31T00:00:00.000Z")  # now running
    second = server.post("/jobs", {"kind": "corpus.update"})
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


# ── Settings ▸ Schedule ─────────────────────────────────────────────────────


def test_the_schedule_follows_the_defaults_until_chosen(server, madrid):
    view = server.get("/schedule/settings").json()["data"]
    assert (view["hour"], view["steps"], view["chosen"]) == (
        2, {"corpus.update": True}, False
    )
    assert view["timezone"] == "Europe/Madrid"
    assert view["nextRunAt"].endswith("Z")
    assert view["lastRun"] is None


def test_the_hour_and_the_switches_are_saved(server, madrid):
    saved = server.put("/schedule/settings", {"hour": 5, "steps": {"corpus.update": False}})
    assert saved.status_code == 200, saved.json()
    view = saved.json()["data"]
    assert (view["hour"], view["steps"]["corpus.update"], view["chosen"]) == (5, False, True)
    assert server.get("/schedule/settings").json()["data"]["hour"] == 5


@pytest.mark.parametrize("body", [
    {"hour": 24}, {"hour": -1}, {"hour": "2"}, {"hour": True},
    {"steps": {"sweep": True}}, {"steps": {"corpus.update": "yes"}}, {"steps": []},
])
def test_a_schedule_that_is_not_one_is_refused(server, body):
    assert server.put("/schedule/settings", body).status_code == 400


def test_the_last_run_is_reported(server, madrid):
    job = jobs.enqueue(server.owner, "nightly", trigger="schedule",
                       subject_kind="schedule", subject_id="nightly")
    Runner(madrid).run_until_idle()
    assert server.get("/schedule/settings").json()["data"]["lastRun"]["id"] == job["id"]
