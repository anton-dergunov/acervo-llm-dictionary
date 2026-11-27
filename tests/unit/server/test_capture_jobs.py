"""Headless capture as a job: one submission in, Inbox entries and their enrichment out.

See `docs/architecture/jobs.md`.

The end-to-end case runs the real pipeline over the stubbed provider. The walk itself — where each
entry ends, what a duplicate or an unreadable block does, how a rest resumes — is driven with a
scripted proposal, because the stub answers every call the same way.
"""

from __future__ import annotations

import pytest

from acervo.domain import SCHEMA_VERSION
from acervo.errors import ApiError
from acervo.repository import jobs
from acervo.work import capture as capture_kind
from acervo.work.runner import Runner

from graph_records import DEVICE, lexeme, topic, vocabulary, vocabulary_id
from test_capture import ARTICLE, RESOLUTION


@pytest.fixture
def seeded(server):
    server.push({
        "vocabularies": [vocabulary()],
        "topics": [topic(name="Food", order=0), topic(name="Culture", order=1)],
        "lexemes": [lexeme(headword="picar", lemma="picar", status="active")],
    })
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])
    server.model.resolution = dict(RESOLUTION)
    server.model.article = dict(ARTICLE)
    return server


@pytest.fixture
def runner(server) -> Runner:
    return Runner(server.settings)


def submit(server, **overrides):
    answer = server.post("/captures", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "mode": "single",
        "text": "El disfraz de pirata viene con un garfio.", **overrides,
    })
    assert answer.status_code == 202, answer.json()
    return answer.json()["data"]


def detail(server, job_id):
    return jobs.get(server.owner, job_id)["steps"][0].get("detail") or {}


class Script:
    """A proposal per window, in order: a headword and how many lines it took, or an error."""

    def __init__(self, monkeypatch, *answers):
        self.answers = list(answers)
        self.windows: list[str] = []
        monkeypatch.setattr(capture_kind, "propose", self)

    def __call__(self, settings, owner, request):
        self.windows.append(request["text"])
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        headword, consumed, *duplicate = answer
        draft = {
            "id": None, "language": "es", "headword": headword, "lemma": headword, "reading": None,
            "ipa": None, "pos": "noun", "gender": None, "register": None, "dialect": None,
            "emoji": None, "topics": [], "status": "active", "shortGloss": None, "notes": [],
            "images": [], "attestations": [],
            "senses": [{"id": None, "order": 0, "definition": f"Definición de {headword}.",
                        "definitionLang": "es", "glosses": [{"lang": "en", "terms": [headword]}],
                        "domain": None, "emoji": None, "examples": [], "images": []}],
        }
        return {
            "resolution": {**RESOLUTION, "headword": headword, "consumedLines": consumed},
            "duplicates": [{"id": "x" * 15, "headword": headword}] if duplicate else [],
            "draft": None if duplicate else draft,
            "vocabularyId": vocabulary_id("es"),
        }


NOTES = "garfio - hook\nun ejemplo\n\n---\n\ntoalla - towel\nsobremesa - chat\n"


# ── end to end ──────────────────────────────────────────────────────────────


def test_a_submission_is_saved_to_the_inbox_and_its_word_enriched(seeded, runner):
    job = submit(seeded)
    assert (job["kind"], job["state"], job["trigger"]) == ("capture", "queued", "ingest")

    runner.run_until_idle()
    finished = jobs.get(seeded.owner, job["id"])
    assert finished["state"] == "done", finished
    [word] = finished["steps"][0]["detail"]["words"]
    assert word["outcome"] == "saved"

    changes = seeded.pull().json()["data"]["changes"]
    created = next(row for row in changes["lexemes"] if row["id"] == word["lexemeId"])
    assert (created["headword"], created["status"]) == ("el garfio", "inbox")
    drawn = next(row for row in changes["examples"] if row["origin"] == "attestation")
    assert drawn["sourceAttestationId"] == changes["attestations"][0]["id"]

    # The word's enrichment is a child of the capture, so the whole tree reads as one.
    [child] = finished["children"]
    assert (child["kind"], child["subject"]["id"], child["trigger"]) == (
        "enrich", word["lexemeId"], "ingest"
    )


def test_a_word_already_held_is_reported_and_nothing_is_written(seeded, runner):
    seeded.model.resolution = {**RESOLUTION, "headword": "picar", "lemma": "picar"}
    job = submit(seeded, text="picar")
    runner.run_until_idle()
    [word] = detail(seeded, job["id"])["words"]
    assert (word["outcome"], word["existing"]) == ("duplicate", ["picar"])
    assert len(seeded.pull().json()["data"]["changes"]["lexemes"]) == 1


def test_a_language_hint_with_no_vocabulary_fails_before_any_model_call(seeded, runner):
    job = submit(seeded, language="fr")
    runner.run_until_idle()
    finished = jobs.get(seeded.owner, job["id"])
    assert (finished["state"], finished["error"]) == ("failed", "language_not_configured")
    assert seeded.model.calls == []


def test_a_topic_that_does_not_exist_fails_before_any_model_call(seeded, runner):
    job = submit(seeded, topics=["Culture", "Actions"])
    runner.run_until_idle()
    finished = jobs.get(seeded.owner, job["id"])
    assert (finished["state"], finished["error"]) == ("failed", "topic_not_configured")
    assert "Actions" in finished["message"]
    assert seeded.model.calls == []


def test_a_resolved_language_the_owner_does_not_keep_is_the_jobs_error(seeded, runner):
    seeded.model.resolution = {**RESOLUTION, "language": "fr"}
    job = submit(seeded)
    runner.run_until_idle()
    finished = jobs.get(seeded.owner, job["id"])
    assert (finished["state"], finished["error"]) == ("failed", "language_not_configured")


def test_the_route_refuses_nothing_to_capture_and_needs_an_account(seeded):
    answer = seeded.post("/captures", {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "text": " "})
    assert answer.status_code == 400
    assert seeded.client.post("/api/acervo/v1/captures", json={}).status_code == 401
    assert jobs.open_jobs(seeded.owner) == []


def test_only_what_a_capture_needs_is_kept_on_the_job(seeded):
    job = submit(seeded, apply=True, secret="nope", topics=["Food"])
    assert set(job["input"]) == {"text", "mode", "topics"}


# ── the walk ────────────────────────────────────────────────────────────────


def test_a_stream_walks_entry_by_entry_skipping_rules_for_free(seeded, runner, monkeypatch):
    script = Script(monkeypatch, ("garfio", 2), ("toalla", 1), ("sobremesa", 1))
    job = submit(seeded, mode="stream", text=NOTES, window=3)
    runner.run_until_idle()

    assert [window.split("\n")[0] for window in script.windows] == [
        "garfio - hook", "toalla - towel", "sobremesa - chat"
    ]
    progress = detail(seeded, job["id"])
    assert [(word["headword"], word["outcome"]) for word in progress["words"]] == [
        ("garfio", "saved"), ("toalla", "saved"), ("sobremesa", "saved")
    ]
    assert progress["consumedLines"] == len(NOTES.split("\n"))
    assert len(jobs.get(seeded.owner, job["id"])["children"]) == 3


def test_an_unreadable_block_is_skipped_rather_than_stalling_the_walk(seeded, runner, monkeypatch):
    unreadable = ApiError(422, "unreadable_input", "Not a word.")
    script = Script(monkeypatch, unreadable, ("toalla", 1), ("sobremesa", 1))
    job = submit(seeded, mode="stream", text=NOTES, window=3)
    runner.run_until_idle()

    assert script.windows[1].startswith("toalla")
    words = detail(seeded, job["id"])["words"]
    assert words[0]["outcome"] == "failed" and words[0]["error"] == "unreadable_input"
    assert jobs.get(seeded.owner, job["id"])["state"] == "done"


def test_a_duplicate_in_a_stream_is_passed_over_and_the_walk_goes_on(seeded, runner, monkeypatch):
    Script(monkeypatch, ("garfio", 2, "held"), ("toalla", 1), ("sobremesa", 1))
    job = submit(seeded, mode="stream", text=NOTES, window=3)
    runner.run_until_idle()
    assert [word["outcome"] for word in detail(seeded, job["id"])["words"]] == [
        "duplicate", "saved", "saved"
    ]


def test_a_busy_provider_rests_the_job_and_it_resumes_on_the_entry_it_was_on(seeded, monkeypatch):
    clock = [1_000_000.0]
    runner = Runner(seeded.settings, clock=lambda: clock[0])
    busy = ApiError(503, "llm_rate_limited", "Quota.")
    script = Script(monkeypatch, ("garfio", 2), busy, ("toalla", 1), ("sobremesa", 1))
    job = submit(seeded, mode="stream", text=NOTES, window=3)

    runner.run_until_idle()
    resting = jobs.get(seeded.owner, job["id"])
    assert resting["state"] == "queued"
    assert [word["headword"] for word in resting["steps"][0]["detail"]["words"]] == ["garfio"]

    # The gate before each call honours the lane's rest, which runs on the real clock.
    runner.lanes["text"] = type(runner.lanes["text"])(0)
    clock[0] += 3600
    runner.run_until_idle()
    finished = jobs.get(seeded.owner, job["id"])
    assert finished["state"] == "done"
    assert [word["headword"] for word in finished["steps"][0]["detail"]["words"]] == [
        "garfio", "toalla", "sobremesa"
    ]
    # The window that was refused is asked again, and nothing before it is.
    assert [window.split("\n")[0] for window in script.windows] == [
        "garfio - hook", "toalla - towel", "toalla - towel", "sobremesa - chat"
    ]


def test_a_failure_says_how_far_it_got(seeded, runner, monkeypatch):
    Script(monkeypatch, ("garfio", 2), ApiError(502, "stream_boundary_mismatch", "Unsafe."))
    job = submit(seeded, mode="stream", text=NOTES, window=3)
    runner.run_until_idle()
    finished = jobs.get(seeded.owner, job["id"])
    assert (finished["state"], finished["error"]) == ("failed", "stream_boundary_mismatch")
    # Two lines of the entry, then the blank and the rule it skipped before the refused window.
    assert finished["steps"][0]["detail"]["consumedLines"] == 5


def test_an_incomplete_submission_leaves_its_tail_for_the_next_one(seeded, runner, monkeypatch):
    script = Script(monkeypatch, ("garfio", 2), ("toalla", 1))
    job = submit(seeded, mode="stream", text=NOTES, window=3, complete=False)
    runner.run_until_idle()
    progress = detail(seeded, job["id"])
    assert len(script.windows) == 2
    # `sobremesa` and the trailing blank are not a full window, so they wait for the next submission.
    assert progress["consumedLines"] == 6


def test_a_limit_stops_the_walk_after_so_many_entries(seeded, runner, monkeypatch):
    Script(monkeypatch, ("garfio", 2), ("toalla", 1), ("sobremesa", 1))
    job = submit(seeded, mode="stream", text=NOTES, window=3, limit=1)
    runner.run_until_idle()
    progress = detail(seeded, job["id"])
    assert [word["headword"] for word in progress["words"]] == ["garfio"]
    assert progress["consumedLines"] == 2
