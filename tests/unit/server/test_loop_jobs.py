"""The `loop` job: start a render, follow it, store what comes back.

The generator is faked at the HTTP boundary with the responses recorded from the real one. What is
pinned here is the half `work/corpus.py` already established — a long-running thing followed by
requeue rather than held in the runner's lane — plus the two things a loop adds: a track written as
it arrived, and times written onto rows that already existed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from graph_records import lexeme, sense, vocabulary

from acervo.repository import jobs
from acervo.work import kinds
from acervo.work.loop import POLL_SECONDS
from acervo.work.runner import Runner

FIXTURES = Path(__file__).resolve().parents[1] / "loops" / "fixtures"
LEXIBEAT_URL = "http://lexibeat:8000/api/v1"
TRACK = b"ID3" + b"a-finished-mp3" * 40


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
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.polls = 0
        # How many looks before it reports finished, so a test can exercise the requeue.
        self.finish_after = 0
        self.completed = recorded("completed")
        self.tracks = 0

    def request(self, method: str, url: str, **kwargs):
        path = httpx.URL(url).path
        if path.endswith("/schema"):
            return httpx.Response(200, json=recorded("schema"))
        if method == "POST":
            self.started.append(kwargs.get("json") or {})
            return httpx.Response(202, json=recorded("queued"))
        self.polls += 1
        if self.polls > self.finish_after:
            return httpx.Response(200, json=self._for_words_asked())
        return httpx.Response(200, json={**recorded("queued"), "status": "running",
                                         "progress": {"fraction": 0.3, "message": "Synthesizing"}})

    def _for_words_asked(self) -> dict:
        """The recorded render, cut to as many words as the loop asked for, as the real one is."""
        asked = len((self.started[-1] if self.started else {}).get("items") or [])
        result = self.completed.get("result")
        if not asked or not isinstance(result, dict):
            return self.completed
        return {**self.completed, "result": {
            **result,
            "items": [row for row in result["items"] if row["index"] < asked],
            "cues": [cue for cue in result["cues"] if cue["item"] is None or cue["item"] < asked],
        }}

    def get(self, url: str, **kwargs):
        self.tracks += 1
        return httpx.Response(200, content=TRACK, headers={"content-type": "audio/mpeg"})


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
    return stub


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def runner(server, clock) -> Runner:
    return Runner(server.settings, clock=clock)


def a_loop(server, count: int = 2) -> dict:
    server.push({"vocabularies": [vocabulary()]})
    ids = []
    for index in range(count):
        entry = lexeme(headword=f"palabra{index}", lemma=f"palabra{index}", status="active",
                       primaryGloss=f"word {index}", emotion="plainly")
        server.push({"lexemes": [entry], "senses": [sense(entry["id"])]})
        ids.append(entry["id"])
    answer = server.post("/loops", {"deviceId": "device000000001", "language": "es",
                                    "lexemeIds": ids})
    assert answer.status_code == 202, answer.text
    return answer.json()["data"]["loop"]


def stored(server, key):
    return server.pull().json()["data"]["changes"][key]


def drive(runner, clock, rounds: int = 6) -> None:
    """Run until the job is waiting, move time past its rest, run again — for as long as it asks.

    A render is followed by requeue rather than held in the lane, so reaching the end of one takes
    as many passes as it takes looks. Real time never moves in a test; the clock is the runner's.
    """
    for _ in range(rounds):
        runner.run_until_idle()
        clock.advance(POLL_SECONDS * 4)


# ── the render ──────────────────────────────────────────────────────────────


def test_a_render_is_started_with_the_words_and_a_render_scoped_token(server, generator, runner, clock):
    a_loop(server, 2)
    drive(runner, clock)
    assert len(generator.started) == 1
    body = generator.started[0]
    assert [item["source"] for item in body["items"]] == ["palabra0", "palabra1"]
    assert body["source_language"]["code"] == "es"
    # The whole of what the generator is given to speak with. It is a JWT, not the owner's session.
    assert body["speech"]["token"] and body["speech"]["token"].count(".") == 2


def test_a_render_and_every_call_home_it_causes_are_filed_under_the_job(server, generator, runner, clock, monkeypatch):
    """The join the two containers lacked. The job's id goes out as the request's id, and comes
    home inside the token every take is asked with — so the generator carries nothing it has to
    know about, and a take is filed under the job that asked for the render."""
    import jwt

    from acervo.repository import jobs

    sent: list[dict] = []
    real = generator.request
    monkeypatch.setattr(generator, "request",
                        lambda method, url, **kwargs: sent.append(kwargs.get("headers") or {})
                        or real(method, url, **kwargs))
    a_loop(server, 2)
    drive(runner, clock)

    (job,) = [one for one in jobs.latest(5) if one["kind"] == "loop"]
    assert sent and all(headers.get("X-Request-ID") == job["id"] for headers in sent[1:]), sent
    claims = jwt.decode(generator.started[0]["speech"]["token"], options={"verify_signature": False})
    assert claims["rid"] == job["id"]


def test_the_track_and_the_times_land_together_when_it_finishes(server, generator, runner, clock):
    loop = a_loop(server, 2)
    drive(runner, clock)

    written = [row for row in stored(server, "loops") if row["id"] == loop["id"]][0]
    assert written["audioRef"].startswith("loops/es/") and written["audioRef"].endswith(".mp3")
    assert written["audioMime"] == "audio/mpeg"
    assert written["durationSeconds"] > 0
    assert written["styleId"] and written["engineVersion"] and written["bedFingerprint"]

    # Stored exactly as it arrived: the generator wrote MP3 and Acervo re-encodes nothing.
    assert (server.media / written["audioRef"]).read_bytes() == TRACK
    # A digest of the bytes, so a re-render is a new reference and a cached device simply misses.
    assert written["audioRef"].rsplit("-", 1)[1][:8] != "00000000"

    items = sorted(stored(server, "loopItems"), key=lambda row: row["position"])
    assert all(row["endSeconds"] > 0 for row in items)
    first = items[0]
    assert first["startSeconds"] <= first["sourceRevealSeconds"] <= first["targetRevealSeconds"] <= first["endSeconds"]
    # The words are the ones written when the loop was asked for, untouched by the render.
    assert [row["sourceText"] for row in items] == ["palabra0", "palabra1"]


def test_an_unfinished_render_waits_and_yields_the_lane_rather_than_holding_it(server, generator, runner, clock):
    generator.finish_after = 2
    a_loop(server, 1)

    runner.run_until_idle()
    open_jobs = jobs.open_jobs(server.owner)
    assert len(open_jobs) == 1
    step = open_jobs[0]["steps"][0]
    # Waiting rather than running: the lane is free for other work while the generator renders.
    assert step["state"] == "waiting"
    assert step["detail"]["operationId"]
    assert step["detail"]["polls"] == 1
    # Nothing stored yet: the loop is still what it was when it was asked for.
    assert stored(server, "loops")[0]["audioRef"] is None

    clock.advance(POLL_SECONDS * 4)
    runner.run_until_idle()
    step = jobs.open_jobs(server.owner)[0]["steps"][0]
    assert step["detail"]["progress"] == pytest.approx(0.3)
    assert step["detail"]["doing"] == "Synthesizing"

    drive(runner, clock)
    assert stored(server, "loops")[0]["audioRef"] is not None


def test_a_render_the_generator_failed_leaves_the_loop_asked_for_and_unmade(server, generator, runner, clock):
    generator.completed = {**recorded("completed"), "status": "failed", "successful": False,
                           "error": "the voice refused", "result": None}
    loop = a_loop(server, 1)
    drive(runner, clock)

    written = [row for row in stored(server, "loops") if row["id"] == loop["id"]][0]
    # Derived state doing its job: no status column to disagree with, and Try again queues another.
    assert written["audioRef"] is None
    assert not written["deleted"]
    assert stored(server, "loopItems")
    assert generator.tracks == 0


def test_an_unreachable_generator_is_rested_rather_than_failed(server, generator, runner, clock, monkeypatch):
    """A container that is not there this second is a condition that passes, not a fact to record.

    It joins the three model-call codes in `retry.TRANSIENT` for that reason, and the step goes to
    waiting with the code on it rather than failing on the first refusal. How long the ladder runs
    before it gives up is `retry`'s and is tested there.
    """
    def refuse(*args, **kwargs):
        raise httpx.ConnectError("no route to host")

    a_loop(server, 1)
    monkeypatch.setattr(GeneratorStub, "request", refuse)
    runner.run_until_idle()

    step = jobs.open_jobs(server.owner)[0]["steps"][0]
    assert step["state"] == "waiting"
    assert step["error"] == "loops_unreachable"
    assert step["rests"] == 1
    # Nothing was written on the way, so a later attempt starts from the same place.
    assert stored(server, "loops")[0]["audioRef"] is None


def test_the_kind_declares_its_phases_up_front(server, generator, runner, clock):
    """Declared steps are what the progress strip draws, in order, from the first reading."""
    assert kinds.find("loop").steps == ("loop.render", "loop.store")
    a_loop(server, 1)
    drive(runner, clock)
    done = [job for job in jobs.recent(server.owner, 50) if job["kind"] == "loop"][0]
    assert [step["name"] for step in done["steps"]] == ["loop.render", "loop.store"]
    assert [step["state"] for step in done["steps"]] == ["done", "done"]


# ── new music for a loop ────────────────────────────────────────────────────


def test_new_music_renders_again_and_leaves_the_row_until_the_track_lands(server, generator, runner, clock):
    loop = a_loop(server, 1)
    drive(runner, clock)
    before = [row for row in stored(server, "loops") if row["id"] == loop["id"]][0]

    answer = server.post(f"/loops/{loop['id']}/music", {"family": "meditative", "seed": 777})
    assert answer.status_code == 202, answer.text
    assert answer.json()["data"]["job"]["input"] == {"family": "meditative", "seed": "777"}
    # Nothing written yet: the row still describes the track it holds.
    now = [row for row in stored(server, "loops") if row["id"] == loop["id"]][0]
    assert (now["seed"], now["styleId"], now["audioRef"]) == (
        before["seed"], before["styleId"], before["audioRef"])

    drive(runner, clock)
    asked = generator.started[-1]
    assert (asked["family"], asked["seed"]) == ("meditative", 777)


def test_new_music_in_the_same_style_keeps_the_family_and_draws_a_new_seed(server, generator, runner, clock):
    loop = a_loop(server, 1)
    drive(runner, clock)
    answer = server.post(f"/loops/{loop['id']}/music", {})
    assert answer.status_code == 202, answer.text
    given = answer.json()["data"]["job"]["input"]
    assert given["family"] == recorded("completed")["result"]["style_id"]
    assert given["seed"].isdigit()


def test_new_music_waits_for_the_render_already_under_way(server, generator, runner, clock):
    loop = a_loop(server, 1)
    # The render asked for when the loop was made is still queued.
    busy = server.post(f"/loops/{loop['id']}/music", {})
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "loop_busy"


def test_new_music_is_only_music_the_generator_offers(server, generator, runner, clock):
    loop = a_loop(server, 1)
    drive(runner, clock)
    assert server.post(f"/loops/{loop['id']}/music", {"family": "polka"}).status_code == 400
    assert server.post(f"/loops/{loop['id']}/music", {"seed": -3}).status_code == 400
    assert server.post("/loops/zzzzzzzzzzzzzzz/music", {}).status_code == 404


def test_try_again_on_a_change_of_music_asks_for_the_same_music(server, generator, runner, clock):
    loop = a_loop(server, 1)
    drive(runner, clock)
    server.post(f"/loops/{loop['id']}/music", {"family": "meditative", "seed": 31})
    again = server.post("/jobs", {"kind": "loop", "subject": {"kind": "loop", "id": loop["id"]},
                                  "input": {"family": "meditative", "seed": "31"}})
    assert again.status_code == 202, again.text
    assert again.json()["data"]["input"] == {"family": "meditative", "seed": "31"}


# ── lines, scripts and fallbacks ────────────────────────────────────────────


def a_radio_lesson(server) -> dict:
    server.push({"vocabularies": [vocabulary()]})
    ids = []
    for index in range(2):
        entry = lexeme(headword=f"palabra{index}", lemma=f"palabra{index}", status="active",
                       primaryGloss=f"word {index}", emotion="plainly")
        server.push({"lexemes": [entry], "senses": [sense(entry["id"])]})
        ids.append(entry["id"])
    answer = server.post("/loops", {"deviceId": "device000000001", "language": "es",
                                    "lexemeIds": ids, "format": "radio-lesson"})
    assert answer.status_code == 202, answer.text
    return answer.json()["data"]["loop"]


def test_every_line_is_stored_with_the_word_it_belongs_to(server, generator, runner, clock):
    generator.completed = recorded("completed-radio")
    loop = a_radio_lesson(server)
    drive(runner, clock)

    items = {row["id"]: row for row in stored(server, "loopItems")}
    cues = sorted((row for row in stored(server, "loopCues") if not row["deleted"]),
                  key=lambda row: row["position"])
    heard = recorded("completed-radio")["result"]["cues"]
    assert [row["text"] for row in cues] == [cue["text"] for cue in heard]
    assert [row["group"] for row in cues] == [cue["group"] for cue in heard]
    assert all(row["loopId"] == loop["id"] for row in cues)
    # A word's own line names its word by id; a line of no word names none.
    for row, cue in zip(cues, heard):
        if cue["item"] is None:
            assert row["loopItemId"] is None
        else:
            assert items[row["loopItemId"]]["position"] == cue["item"]
    written = [row for row in stored(server, "loops") if row["id"] == loop["id"]][0]
    assert (written["format"], written["fallbackFrom"]) == ("radio-lesson", None)


def test_new_music_sends_the_lines_back_so_they_are_said_again(server, generator, runner, clock):
    generator.completed = recorded("completed-radio")
    loop = a_radio_lesson(server)
    drive(runner, clock)
    assert "script" not in generator.started[0]

    server.post(f"/loops/{loop['id']}/music", {})
    drive(runner, clock)
    # The script the first render returned, whole: no writing call, and every take in the cache.
    assert generator.started[-1]["script"] == recorded("completed-radio")["result"]["script"]
    # And the second render's lines replace the first's rather than joining them.
    live = [row for row in stored(server, "loopCues") if not row["deleted"]]
    assert len(live) == len(recorded("completed-radio")["result"]["cues"])


def test_a_render_that_fell_back_is_recorded_as_what_it_is(server, generator, runner, clock):
    generator.completed = recorded("completed-fallback")
    loop = a_radio_lesson(server)
    drive(runner, clock)
    written = [row for row in stored(server, "loops") if row["id"] == loop["id"]][0]
    assert (written["format"], written["fallbackFrom"]) == ("classic", "radio-lesson")
    # The loop still asks for what the listener chose; the track says what it got.
    assert written["switches"] == {}


def test_deleting_a_loop_takes_its_lines_and_its_script(server, generator, runner, clock):
    from acervo.repository import loop_scripts

    generator.completed = recorded("completed-radio")
    loop = a_radio_lesson(server)
    drive(runner, clock)
    assert loop_scripts.script(server.owner, loop["id"]) is not None

    assert server.delete(f"/loops/{loop['id']}").status_code == 200
    assert all(row["deleted"] for row in stored(server, "loopCues"))
    assert loop_scripts.script(server.owner, loop["id"]) is None


def test_a_render_that_speaks_a_word_the_loop_does_not_have_is_not_stored(server, generator, runner, clock):
    generator.completed = recorded("completed-radio")
    loop = a_radio_lesson(server)
    # Answer for more words than were asked, as a mismatched render would.
    generator._for_words_asked = lambda: recorded("completed-radio") | {
        "result": {**recorded("completed-radio")["result"],
                   "cues": recorded("completed-radio")["result"]["cues"]
                   + [{**recorded("completed-radio")["result"]["cues"][-1], "item": 7}]}}
    drive(runner, clock)
    done = [job for job in jobs.recent(server.owner, 50) if job["kind"] == "loop"][0]
    assert done["state"] == "failed"
    assert "does not have" in (done.get("message") or done["steps"][-1].get("message") or "")
    assert [row for row in stored(server, "loops") if row["id"] == loop["id"]][0]["audioRef"] is None
