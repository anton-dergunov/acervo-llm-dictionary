"""Music on its own: a kept bed's minute (`music`), each style's sample (`music.samples`), and the
routes a device hears them through.

The generator is faked at the HTTP boundary with the recorded schema, as `test_loop_jobs.py` fakes it.
What is pinned here: a kept bed asks for its music as it lands; the music is the bed it says it is or
nothing; a sample is a cache found under what it records and served under a digest of its bytes; and
the warming job makes what is missing one family at a time.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from graph_records import loop, stamp

from acervo.domain.ids import new_record_id
from acervo.loops import samples
from acervo.repository import jobs
from acervo.services import music as music_service
from acervo.work import music as music_jobs
from acervo.work.runner import Runner

FIXTURES = Path(__file__).resolve().parents[1] / "loops" / "fixtures"
LEXIBEAT_URL = "http://lexibeat:8000/api/v1"
TRACK = b"ID3" + b"music-on-its-own" * 40
FINGERPRINT = "f7aa8c933f9a7e8a"


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class GeneratorStub:
    """`POST /music` answers an operation; a look at it answers finished after `finish_after`."""

    def __init__(self) -> None:
        self.schema = recorded("schema")
        self.started: list[dict] = []
        self.polls = 0
        self.finish_after = 0
        self.fingerprint = FINGERPRINT
        self.status = "completed"
        self.tracks = 0

    def request(self, method: str, url: str, **kwargs):
        path = httpx.URL(url).path
        if path.endswith("/schema"):
            return httpx.Response(200, json=self.schema)
        if method == "POST" and path.endswith("/music"):
            self.started.append(kwargs.get("json") or {})
            return httpx.Response(202, json=self._operation("queued"))
        self.polls += 1
        if self.polls > self.finish_after:
            return httpx.Response(200, json=self._operation(self.status))
        return httpx.Response(200, json=self._operation("running"))

    def _operation(self, status: str) -> dict:
        asked = self.started[-1] if self.started else {}
        done = status == "completed"
        return {
            "operation_id": f"op{len(self.started)}", "status": status,
            "successful": True if done else (False if status == "failed" else None),
            "error": "the bed would not render" if status == "failed" else None,
            "progress": {"fraction": 1.0 if done else 0.4, "message": "Rendering"},
            "result": {
                "audio_url": f"/api/v1/music/op{len(self.started)}/audio",
                "audio_mime": "audio/mpeg", "duration_seconds": float(asked.get("seconds") or 0) + 1,
                "style_id": asked.get("family"), "seed": asked.get("seed"),
                "engine_version": self.schema["engine_version"],
                "bed_fingerprint": self.fingerprint, "bpm": 68.0, "total_bars": 17,
            } if done else None,
        }

    def get(self, url: str, **kwargs):
        self.tracks += 1
        return httpx.Response(200, content=TRACK + str(self.tracks).encode(),
                              headers={"content-type": "audio/mpeg"})


@pytest.fixture
def generator(server, monkeypatch) -> GeneratorStub:
    stub = GeneratorStub()
    monkeypatch.setattr(server.settings, "lexibeat_url", LEXIBEAT_URL)

    class Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def request(self, method, url, **kwargs):
            return stub.request(method, url, **kwargs)

        def get(self, url, **kwargs):
            return stub.get(url, **kwargs)

    monkeypatch.setattr("acervo.loops.client.httpx.Client", Client)
    monkeypatch.setattr(music_service, "SAMPLE_POLL_SECONDS", 0.0)
    return stub


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def runner(server, clock) -> Runner:
    return Runner(server.settings, clock=clock)


def drive(runner, clock, rounds: int = 30) -> None:
    for _ in range(rounds):
        runner.run_until_idle()
        clock.advance(music_jobs.POLL_SECONDS * 4)


def keep(server, **overrides) -> dict:
    """A rendered loop and the bed the owner kept from it, written as the player's star writes it."""
    source = loop(styleId="organic", seed=7, engineVersion="1.5.0", bedFingerprint=FINGERPRINT,
                  format="classic")
    bed = {"id": new_record_id(), "styleId": "organic", "seed": 7, "engineVersion": "1.5.0",
           "bedFingerprint": FINGERPRINT, "sourceLoopId": source["id"], **stamp(), **overrides}
    answer = server.push({"loops": [source], "beds": [bed]})
    assert answer.status_code == 200, answer.text
    return bed


def held(server, bed_id: str) -> dict:
    return next(row for row in server.pull().json()["data"]["changes"]["beds"] if row["id"] == bed_id)


def steps(job: dict) -> dict[str, dict]:
    return {step["name"]: step for step in job["steps"]}


# ── a kept bed ──────────────────────────────────────────────────────────────


def test_keeping_a_bed_asks_for_its_music_in_the_same_write(server, generator):
    bed = keep(server)
    (queued,) = [one for one in jobs.open_jobs(server.owner) if one["kind"] == "music"]
    assert queued["subject"] == {"kind": "bed", "id": bed["id"]}
    # Nothing has played yet: the row says no music, not a zero-second track.
    row = held(server, bed["id"])
    assert row["audioRef"] is None and row["audioMime"] is None and row["durationSeconds"] is None


def test_the_music_is_a_minute_of_the_bed_written_file_first_then_the_row(server, generator, runner, clock):
    bed = keep(server)
    drive(runner, clock)

    (asked,) = generator.started
    # A loop's palette, so the same family and seed resolve to the bed the loop was made over.
    assert asked == {"family": "organic", "seed": 7, "seconds": music_service.BED_SECONDS,
                     "palette": "hybrid"}
    row = held(server, bed["id"])
    assert row["audioRef"].startswith(f"music/{bed['id']}-") and row["audioRef"].endswith(".mp3")
    assert row["audioMime"] == "audio/mpeg" and row["durationSeconds"] > 0
    # Stored as it arrived, under a digest of those bytes.
    assert (server.media / row["audioRef"]).read_bytes().startswith(TRACK)
    assert row["styleId"] == "organic" and row["bedFingerprint"] == FINGERPRINT


def test_a_kept_bed_already_given_its_music_is_nothing_to_do(server, generator, runner, clock):
    bed = keep(server)
    drive(runner, clock)
    jobs.enqueue(server.owner, "music", trigger="manual", subject_kind="bed", subject_id=bed["id"])
    drive(runner, clock)

    assert len(generator.started) == 1
    (again,) = [one for one in jobs.recent(server.owner) if one["kind"] == "music"
                and one["trigger"] == "manual"]
    assert {name: step["state"] for name, step in steps(again).items()} == {
        "music.render": "skipped", "music.store": "skipped"}


def test_an_engine_that_moved_on_is_refused_by_name_and_nothing_is_asked_for(server, generator, runner, clock):
    bed = keep(server, engineVersion="1.4.0")
    drive(runner, clock)

    assert generator.started == []
    (job,) = [one for one in jobs.recent(server.owner) if one["kind"] == "music"]
    render = steps(job)["music.render"]
    assert render["state"] == "failed" and render["error"] == "music_engine_changed"
    assert "1.4.0" in render["message"] and "1.5.0" in render["message"]
    # The store has nothing to keep, and says so rather than failing a second time.
    assert steps(job)["music.store"]["state"] == "skipped"
    assert held(server, bed["id"])["audioRef"] is None


def test_different_music_from_the_same_seed_is_not_kept_under_the_beds_name(server, generator, runner, clock):
    bed = keep(server)
    generator.fingerprint = "0000000000000000"
    drive(runner, clock)

    (job,) = [one for one in jobs.recent(server.owner) if one["kind"] == "music"]
    store = steps(job)["music.store"]
    assert store["state"] == "failed" and store["error"] == "music_differs"
    assert held(server, bed["id"])["audioRef"] is None
    assert not (server.media / "music").exists() or not any((server.media / "music").iterdir())


def test_a_bed_let_go_of_while_it_renders_is_not_given_music(server, generator, runner, clock):
    bed = keep(server)
    generator.finish_after = 2
    runner.run_until_idle()
    assert server.delete(f"/beds/{bed['id']}").status_code == 200
    drive(runner, clock)

    (job,) = [one for one in jobs.recent(server.owner) if one["kind"] == "music"]
    assert steps(job)["music.store"]["state"] == "skipped"
    assert held(server, bed["id"])["deleted"] is True
    assert held(server, bed["id"])["audioRef"] is None


def test_letting_a_bed_go_takes_its_music_with_it(server, generator, runner, clock):
    bed = keep(server)
    drive(runner, clock)
    reference = held(server, bed["id"])["audioRef"]
    assert (server.media / reference).is_file()

    answer = server.delete(f"/beds/{bed['id']}")
    assert answer.status_code == 200, answer.text
    assert answer.json()["data"]["deleted"] is True
    assert not (server.media / reference).exists()
    assert server.delete(f"/beds/{bed['id']}").status_code == 404


def test_a_music_job_can_be_asked_for_again(server, generator, runner, clock):
    bed = keep(server, engineVersion="1.4.0")
    drive(runner, clock)
    answer = server.post("/jobs", {"kind": "music", "subject": {"kind": "bed", "id": bed["id"]}})
    assert answer.status_code in (200, 202), answer.text
    assert answer.json()["data"]["kind"] == "music"


# ── a style's sample ────────────────────────────────────────────────────────


def test_the_schema_names_no_sample_until_one_is_made(server, generator):
    families = server.get("/loops/schema").json()["data"]["families"]
    assert families and all(row["sample"] is None for row in families)


def test_a_tap_before_the_warming_job_makes_the_sample_and_names_it(server, generator):
    answer = server.post("/loops/samples/organic", {})
    assert answer.status_code == 200, answer.text
    name = answer.json()["data"]["sample"]
    assert samples.NAME.match(name) and name.split("/")[1].startswith("organic-")
    (asked,) = generator.started
    assert asked == {"family": "organic", "seed": music_service.SAMPLE_SEED,
                     "seconds": music_service.SAMPLE_SECONDS, "palette": "hybrid"}

    served = server.get(f"/loops/samples/{name}")
    assert served.status_code == 200 and served.content.startswith(TRACK)
    assert served.headers["content-type"] == "audio/mpeg"
    families = {row["id"]: row["sample"] for row in server.get("/loops/schema").json()["data"]["families"]}
    assert families["organic"] == name and families["meditative"] is None

    # Found under what it records the second time: nothing is rendered again.
    assert server.post("/loops/samples/organic", {}).json()["data"]["sample"] == name
    assert len(generator.started) == 1


def test_a_new_engine_misses_every_sample_and_makes_them_afresh(server, generator):
    first = server.post("/loops/samples/organic", {}).json()["data"]["sample"]
    generator.schema = {**generator.schema, "engine_version": "1.6.0"}
    families = {row["id"]: row["sample"] for row in server.get("/loops/schema").json()["data"]["families"]}
    assert families["organic"] is None
    second = server.post("/loops/samples/organic", {}).json()["data"]["sample"]
    assert second != first


def test_a_sample_of_no_family_and_a_name_that_is_not_one_are_refused(server, generator):
    assert server.post("/loops/samples/waltz", {}).status_code == 400
    # A name is checked before any path is built from it, so none reaches outside the cache.
    assert samples.path_of(server.settings.samples_path, "../acervo.db") is None
    assert samples.path_of(server.settings.samples_path, "0123456789abcdef0123456789abcdef/../../x.mp3") is None
    assert server.get("/loops/samples/0123456789abcdef0123456789abcdef/organic-00000000.mp3").status_code == 404


def test_a_render_that_failed_is_said_in_its_own_words(server, generator):
    generator.status = "failed"
    answer = server.post("/loops/samples/organic", {})
    assert answer.status_code == 502
    assert "the bed would not render" in answer.json()["error"]["message"]


# ── warming ─────────────────────────────────────────────────────────────────


def test_the_warming_job_makes_every_missing_sample_one_at_a_time(server, generator, runner, clock):
    server.post("/loops/samples/organic", {})
    jobs.enqueue(server.owner, music_jobs.SAMPLES, trigger="schedule", subject_kind="samples",
                 subject_id="samples")
    drive(runner, clock, rounds=80)

    families = [row["id"] for row in generator.schema["family_details"]]
    # One render a family, the one a tap already made among them, and never two at once.
    assert sorted(one["family"] for one in generator.started) == sorted(families)
    assert music_service.missing(server.settings) == []
    (job,) = [one for one in jobs.recent(server.owner) if one["kind"] == music_jobs.SAMPLES]
    assert job["state"] == "done"
    assert steps(job)[music_jobs.SAMPLES]["detail"]["made"] == len(families) - 1


def test_the_tick_sets_the_samples_off_after_a_start_and_not_before(server, generator, clock):
    tick = music_jobs.timer(server.settings, clock)
    tick()
    assert not jobs.open_of_kind(music_jobs.SAMPLES, server.owner)
    clock.advance(music_jobs.FIRST_LOOK_SECONDS + 1)
    tick()
    assert jobs.open_of_kind(music_jobs.SAMPLES, server.owner)


def test_an_absent_generator_is_said_by_the_tick_itself(server, generator, clock, monkeypatch, caplog):
    def refuse(*args, **kwargs):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(GeneratorStub, "request", refuse)
    tick = music_jobs.timer(server.settings, clock)
    tick()
    clock.advance(music_jobs.FIRST_LOOK_SECONDS + 1)
    with caplog.at_level("WARNING", logger="acervo.activity"):
        tick()
    assert any("samples not checked" in record.getMessage() and "loops_unreachable" in record.getMessage()
               for record in caplog.records)
    assert not jobs.open_of_kind(music_jobs.SAMPLES, server.owner)
