"""Job reads, job requests, and the event stream (`docs/architecture/jobs.md`).

The stream is driven directly rather than through the test client, which buffers a whole response
before returning it and so cannot read one that is meant never to end. The route around it is a
single line and is checked for what it adds: the owner, and the refusal without one.
"""

from __future__ import annotations

import asyncio
import json

from acervo.api.routes.events import frame, stream
from acervo.repository import jobs

from graph_records import lexeme, sense, vocabulary


def save(server, **overrides):
    entry = lexeme(**overrides)
    answer = server.push({
        "vocabularies": [vocabulary()], "lexemes": [entry],
        "senses": [sense(entry["id"])],
    })
    assert answer.status_code == 200, answer.json()
    return entry, answer.json()["data"]["enrich"][entry["id"]]


def ask(server, entry, **overrides):
    return server.post("/jobs", {
        "kind": "enrich", "subject": {"kind": "lexeme", "id": entry["id"]}, **overrides,
    })


# ── reading ─────────────────────────────────────────────────────────────────


def test_open_jobs_are_what_a_client_rebuilds_its_map_from(server):
    entry, job_id = save(server)
    answer = server.get("/jobs?open=true")
    assert answer.status_code == 200
    listed = answer.json()["data"]["jobs"]
    assert [(job["id"], job["kind"], job["subject"], job["state"]) for job in listed] == [
        (job_id, "enrich", {"kind": "lexeme", "id": entry["id"]}, "queued")
    ]


def test_a_job_reads_with_its_steps_and_children(server):
    entry, job_id = save(server)
    answer = server.get(f"/jobs/{job_id}")
    assert answer.status_code == 200
    assert answer.json()["data"]["children"] == []


def test_somebody_elses_job_is_not_found(server, other):
    _, job_id = save(server)
    assert other.get(f"/jobs/{job_id}").status_code == 404
    assert other.get("/jobs?open=true").json()["data"]["jobs"] == []
    assert other.post(f"/jobs/{job_id}/cancel", {}).status_code == 404


def test_recent_jobs_leave_out_dismissed_ones(server):
    _, job_id = save(server)
    jobs.request_cancel(server.owner, job_id)
    assert [job["id"] for job in server.get("/jobs").json()["data"]["jobs"]] == [job_id]
    assert server.post(f"/jobs/{job_id}/dismiss", {}).json()["data"]["dismissed"] is True
    assert server.get("/jobs").json()["data"]["jobs"] == []


def test_the_routes_need_an_account(server):
    for path in ("/api/acervo/v1/jobs", "/api/acervo/v1/events"):
        answer = server.client.get(path)
        assert answer.status_code == 401
        assert answer.json()["error"]["code"] == "unauthenticated"


# ── asking ──────────────────────────────────────────────────────────────────


def test_try_again_queues_an_enrich_for_a_held_word(server):
    entry, job_id = save(server)
    jobs.request_cancel(server.owner, job_id)
    answer = ask(server, entry)
    assert answer.status_code == 202, answer.json()
    queued = answer.json()["data"]
    assert (queued["kind"], queued["trigger"], queued["state"]) == ("enrich", "manual", "queued")


def test_asking_while_one_is_queued_returns_that_one(server):
    entry, job_id = save(server)
    assert ask(server, entry).json()["data"]["id"] == job_id


def test_a_job_is_asked_for_only_by_hand(server):
    """An import asks for nothing (`docs/features/export.md`), so there is no other trigger to name."""
    entry, job_id = save(server)
    jobs.request_cancel(server.owner, job_id)
    answer = ask(server, entry, trigger="import")
    assert answer.status_code == 400, answer.json()


def test_a_word_that_is_not_held_cannot_be_enriched(server, other):
    entry, _ = save(server)
    assert ask(other, entry).status_code == 404
    assert ask(server, lexeme()).status_code == 404


def test_only_the_kinds_a_person_asks_for_are_accepted(server):
    entry, _ = save(server)
    for body in (
        {"kind": "capture"},
        {"kind": "enrich", "subject": {"kind": "sense", "id": entry["id"]}},
        {"kind": "enrich", "subject": {"kind": "lexeme", "id": "not an id"}},
        {"kind": "enrich", "subject": {"kind": "lexeme", "id": entry["id"]}, "trigger": "schedule"},
    ):
        answer = server.post("/jobs", body)
        assert answer.status_code == 400, body


def test_a_job_is_cancelled_through_its_route(server):
    _, job_id = save(server)
    answer = server.post(f"/jobs/{job_id}/cancel", {})
    assert answer.status_code == 200
    assert answer.json()["data"]["state"] == "cancelled"


# ── the stream ──────────────────────────────────────────────────────────────


def parse(chunk: str) -> dict | None:
    for line in chunk.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    return None


def collect(server, action, *, count: int, heartbeat: float = 5.0, owner: str | None = None):
    """Run `action` in a thread once the stream is live, and return the first `count` chunks."""

    async def main():
        stop = asyncio.Event()

        async def disconnected():
            return stop.is_set()

        chunks = []
        body = stream(owner or server.owner, disconnected, heartbeat=heartbeat)
        chunks.append(await body.__anext__())
        acting = asyncio.create_task(asyncio.to_thread(action))
        try:
            while len(chunks) < count:
                chunks.append(await asyncio.wait_for(body.__anext__(), timeout=5))
        finally:
            stop.set()
            await acting
            await body.aclose()
        return chunks

    return asyncio.run(main())


def test_the_stream_says_it_is_live_before_anything_happens(server):
    chunks = collect(server, lambda: None, count=1)
    assert parse(chunks[0]) == {"type": "ready"}
    assert chunks[0].startswith("event: ready\n")


def test_a_save_is_told_as_a_queued_job_and_a_revision(server):
    chunks = collect(server, lambda: save(server), count=3)
    messages = [parse(chunk) for chunk in chunks[1:]]
    assert messages[0]["type"] == "job"
    assert messages[0]["job"]["kind"] == "enrich" and messages[0]["job"]["state"] == "queued"
    assert messages[1]["type"] == "revision"
    assert messages[1]["cursor"] == server.pull().json()["data"]["cursor"]


def test_the_stream_carries_no_records(server):
    chunks = collect(server, lambda: save(server), count=3)
    assert all("records" not in (parse(chunk) or {}) for chunk in chunks)


def test_a_job_that_runs_is_told_step_by_step(server):
    _, job_id = save(server)
    runner = server.client.app.state.runner
    chunks = collect(server, runner.run_until_idle, count=8)
    # This word's job among whatever else the server was doing — the nightly timer ticks here too.
    states = [
        message["job"]["state"] for message in (parse(chunk) for chunk in chunks[1:])
        if message and message.get("type") == "job" and message["job"]["id"] == job_id
    ]
    assert states[0] == "running"


def test_another_owner_hears_nothing(server, other):
    chunks = collect(server, lambda: save(other), count=2, heartbeat=0.2)
    assert parse(chunks[0]) == {"type": "ready"}
    assert chunks[1] == ": still here\n\n"


def test_an_idle_stream_is_kept_alive_and_ends_when_the_client_goes(server):
    async def main():
        gone = False

        async def disconnected():
            return gone

        body = stream(server.owner, disconnected, heartbeat=0.05)
        assert parse(await body.__anext__()) == {"type": "ready"}
        assert await body.__anext__() == ": still here\n\n"
        gone = True
        remaining = [chunk async for chunk in body]
        assert remaining == []

    asyncio.run(main())


def test_a_frame_names_its_event():
    assert frame({"type": "revision", "cursor": 3}) == (
        'event: revision\ndata: {"type":"revision","cursor":3}\n\n'
    )
