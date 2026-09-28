"""Keeping Anki up to date by itself: the push a change queues, the hourly read, and the panel.

The robot is replaced by a stand-in that records what it was asked; what the robot does with a
collection is `tests/unit/consumers/anki/`. What is tested here is what the server decides — when a
push is queued and how long it waits, what a read writes back, and what the owner is told.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from graph_records import DEVICE, lexeme, sense, vocabulary

from acervo.consumers.anki.robot import RobotBusy, SyncSafetyError
from acervo.repository import anki_settings, graph, jobs, reviews
from acervo.repository.session import transaction
from acervo.services import anki as service
from acervo.work import anki as anki_jobs
from acervo.work.runner import Runner


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Robot:
    """What the service is handed instead of a headless Anki client."""

    def __init__(self) -> None:
        self.pushed: list[int] = []
        self.backups: list[bool] = []
        self.exported: dict = {"notes": [], "reviews": []}
        self.failure: BaseException | None = None

    def push(self, manifest, manifest_dir, *, backup=True):
        if self.failure:
            raise self.failure
        self.pushed.append(len(manifest.notes))
        self.backups.append(backup)
        return {"operation": "push", "created": len(manifest.notes), "updated": 0, "notes": [{}]}

    def export_state(self, *, reviews_since=None):
        if self.failure:
            raise self.failure
        return self.exported


@pytest.fixture
def robot(server, monkeypatch) -> Robot:
    stand_in = Robot()
    for name, value in (("anki_sync_endpoint", "http://anki-sync-server:8080/"),
                        ("anki_sync_username", "anki"), ("anki_sync_password", "secret")):
        monkeypatch.setattr(server.settings, name, value)
    monkeypatch.setattr(server.settings, "anki_data_path", server.media.parent / "anki")
    monkeypatch.setattr(service, "robot", lambda settings, progress=None: stand_in)
    return stand_in


def word(server, *, status="active"):
    """A word the cards are made from, written the way an enrichment writes: queuing no enrich."""
    held = lexeme(status=status)
    meaning = sense(held["id"])
    graph.merge_graph(server.owner, DEVICE, {"vocabularies": [vocabulary()], "lexemes": [held],
                                             "senses": [meaning]}, enqueue=None)
    return held, meaning


def pushes(owner: str) -> list[dict]:
    return [job for job in jobs.open_of_kind(anki_settings.PUSH, owner)]


def moment(instant: str) -> datetime:
    return datetime.strptime(instant, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


# ── when a push is queued ───────────────────────────────────────────────────


def test_a_change_to_the_vocabulary_queues_one_push_a_minute_later(server):
    anki_settings.save(server.owner, push=True)
    before = datetime.now(timezone.utc)
    word(server)
    word(server)
    queued = pushes(server.owner)
    assert len(queued) == 1, "a burst of writes is one push"
    wait = moment(queued[0]["notBefore"]) - before
    assert timedelta(seconds=55) < wait < timedelta(seconds=65)


def test_nothing_is_queued_while_the_switch_is_off(server):
    word(server)
    assert pushes(server.owner) == []


def test_a_read_writing_study_states_never_queues_a_push(server):
    held, meaning = word(server)
    anki_settings.save(server.owner, push=True)
    graph.merge_graph(server.owner, "acervoanki", {"studyStates": [{
        "id": "studyaaaaaaaaaa", "lexemeId": held["id"], "senseId": meaning["id"], "system": "anki",
        "noteId": 1, "cardIds": [2], "reps": 0, "lapses": 0, "stability": 0.0, "difficulty": 0.0,
        "retrievability": 0.0, "lastReview": None, "syncedAt": held["createdAt"], "deleted": False,
        "createdAt": held["createdAt"], "editedAt": held["createdAt"], "editedBy": "acervoanki",
        "revision": 0}]}, enqueue=None)
    assert pushes(server.owner) == []


def test_each_write_moves_the_push_later_but_never_past_the_cap(server):
    anki_settings.save(server.owner, push=True)
    start = datetime.now(timezone.utc)
    with transaction() as connection:
        jobs.enqueue_later(connection, server.owner, "anki.push", trigger="save", subject_kind="anki",
                           subject_id="push", now=start)
    for minutes in (1, 5, 9, 12):
        with transaction() as connection:
            assert jobs.enqueue_later(connection, server.owner, "anki.push", trigger="save",
                                      subject_kind="anki", subject_id="push",
                                      now=start + timedelta(minutes=minutes)) is None
    (queued,) = pushes(server.owner)
    created = moment(queued["createdAt"])
    assert moment(queued["notBefore"]) <= created + timedelta(seconds=600, milliseconds=1)
    assert moment(queued["notBefore"]) > start + timedelta(minutes=9)


def test_a_write_while_a_push_runs_queues_one_more_behind_it(server):
    anki_settings.save(server.owner, push=True)
    word(server)
    jobs.claim_next("9999-12-31T00:00:00.000Z")  # the push is now running
    word(server)
    word(server)
    states = sorted(job["state"] for job in pushes(server.owner))
    assert states == ["queued", "running"]


# ── the jobs ────────────────────────────────────────────────────────────────


def test_a_push_runs_once_the_writes_stop_and_reads_back_after(server, robot):
    anki_settings.save(server.owner, push=True)
    word(server)
    clock = Clock()
    runner = Runner(server.settings, clock=clock)
    runner.run_until_idle()
    assert robot.pushed == [], "it waits for the writes to stop"
    clock.advance(61)
    runner.run_until_idle()
    (done,) = [jobs.latest_of_kind(server.owner, anki_settings.PUSH)]
    assert done["state"] == "done", done
    assert [(step["name"], step["state"]) for step in done["steps"]] == [
        ("anki.push", "done"), ("anki.pull", "done")]
    assert robot.pushed == [1], "one word, one sense, no example: one note"
    assert robot.backups == [False], "an automatic push leaves the backup to Anki's own interval"


def test_a_busy_robot_is_waited_for_rather_than_failed(server, robot):
    robot.failure = RobotBusy("The Anki robot is already running")
    queued = jobs.enqueue(server.owner, anki_settings.PULL, trigger="manual", subject_kind="anki",
                          subject_id="pull")
    Runner(server.settings).run_until_idle()
    job = jobs.get(server.owner, queued["id"])
    assert job["state"] == "queued" and job["notBefore"]


def test_a_refusal_reaches_the_owner_in_the_robots_own_words(server, robot):
    anki_settings.save(server.owner, push=True)
    word(server)
    robot.failure = SyncSafetyError("pre-mutation sync requires FULL_SYNC; the robot will never choose")
    queued = pushes(server.owner)[0]
    jobs.hasten(queued["id"])
    Runner(server.settings).run_until_idle()
    job = jobs.get(server.owner, queued["id"])
    assert job["state"] == "failed"
    assert job["error"] == "anki_refused"
    assert "requires FULL_SYNC" in job["message"]


def test_a_push_switched_off_after_it_was_queued_does_nothing(server, robot):
    anki_settings.save(server.owner, push=True)
    word(server)
    anki_settings.save(server.owner, push=False)
    jobs.hasten(pushes(server.owner)[0]["id"])
    Runner(server.settings).run_until_idle()
    assert robot.pushed == []


# ── a read ──────────────────────────────────────────────────────────────────


def exported(held, meaning, **card) -> dict:
    return {"notes": [{"note_id": meaning["id"], "kind": "meaning", "lexeme_id": held["id"],
                       "sense_id": meaning["id"], "anki_note_id": 17, "card_ids": [18],
                       "cards": [{"reps": 3, "lapses": 0, "stability": 4.0, "difficulty": 5.0,
                                  "retrievability": 0.9, "last_review": "2026-09-01T09:00:00.000Z",
                                  **card}]}],
            "reviews": [{"reviewId": 1_788_000_000_001, "cardId": 18, "noteId": 17,
                         "lexemeId": held["id"], "senseId": meaning["id"], "cardType": "Produce",
                         "reviewedAt": "2026-09-01T09:00:00.000Z", "kind": "review", "button": 3,
                         "intervalDays": 4.0, "lastIntervalDays": 1.0, "durationMs": 6000}]}


def study(owner: str) -> list[dict]:
    return [row for row in graph.pull(owner, 0)["changes"].get("studyStates") or []]


def test_a_read_writes_the_state_and_the_history_and_a_second_read_writes_nothing(server, robot):
    held, meaning = word(server)
    robot.exported = exported(held, meaning)

    first = service.pull(server.settings, server.owner)
    cursor = graph.pull(server.owner, 0)["cursor"]
    second = service.pull(server.settings, server.owner)

    assert (first["written"], first["reviewsAdded"]) == (1, 1)
    assert (second["written"], second["reviewsAdded"]) == (0, 0)
    assert graph.pull(server.owner, 0)["cursor"] == cursor, "a quiet read allocates no revision"
    assert [row["reps"] for row in study(server.owner)] == [3]
    assert reviews.latest(server.owner, "anki") == 1_788_000_000_001


def test_the_hourly_read_is_queued_an_hour_after_the_last(server, robot):
    anki_settings.save(server.owner, pull=True)
    clock = Clock()
    tick = anki_jobs.timer(server.settings, clock)
    tick()
    assert len(jobs.open_of_kind(anki_settings.PULL, server.owner)) == 1
    Runner(server.settings, clock=clock).run_until_idle()
    clock.advance(30 * 60)
    tick()
    assert jobs.open_of_kind(anki_settings.PULL, server.owner) == [], "not yet an hour"
    clock.advance(31 * 60)
    tick()
    assert len(jobs.open_of_kind(anki_settings.PULL, server.owner)) == 1, "an hour on, the next"


def test_no_read_is_queued_for_an_owner_who_has_it_off(server, robot):
    tick = anki_jobs.timer(server.settings, Clock())
    tick()
    assert jobs.open_of_kind(anki_settings.PULL, server.owner) == []


# ── Settings ▸ Anki ─────────────────────────────────────────────────────────


def test_a_server_with_no_anki_says_so_and_cannot_be_switched_on(server):
    view = server.get("/anki").json()["data"]
    assert (view["configured"], view["push"], view["pull"]) == (False, False, False)
    refused = server.put("/anki/settings", {"push": True})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "anki_unconfigured"
    assert server.post("/anki/push", {}).status_code == 409


def test_the_switches_are_saved_and_push_now_is_due_at_once(server, robot):
    saved = server.put("/anki/settings", {"push": True, "pull": True})
    assert saved.status_code == 200, saved.json()
    assert (saved.json()["data"]["push"], saved.json()["data"]["pull"]) == (True, True)
    word(server)
    assert pushes(server.owner)[0]["notBefore"]

    answer = server.post("/anki/push", {})
    assert answer.status_code == 202, answer.json()
    assert answer.json()["data"]["notBefore"] is None
    assert len(pushes(server.owner)) == 1, "Push now joins the waiting push rather than adding one"
    assert server.get("/anki").json()["data"]["lastPush"]["id"] == answer.json()["data"]["id"]


@pytest.mark.parametrize("body", [{}, {"push": "yes"}, {"pull": 1}])
def test_switches_that_are_not_switches_are_refused(server, robot, body):
    assert server.put("/anki/settings", body).status_code == 400


def test_a_push_while_another_builds_the_payload_is_told_the_robot_is_busy(server, robot):
    word(server)
    with service._building(service._payload_directory(server.settings)):
        with pytest.raises(RobotBusy):
            service.push(server.settings, server.owner)
    assert robot.pushed == []
    service.push(server.settings, server.owner)
    assert robot.pushed == [1]
