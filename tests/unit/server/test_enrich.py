"""A saved word is enriched by the server, with no client involved (`docs/architecture/jobs.md`).

A word goes in through `POST /graph` — the route every writer uses — and the runner is driven by
hand. What is stubbed is the corpus at its HTTP boundary and the providers, exactly as in the route
tests; the services, the runner and the graph are real.
"""

from __future__ import annotations

import litellm
import pytest

from acervo import admin
from acervo.domain import SCHEMA_VERSION
from acervo.images.ids import image_prompt_id
from acervo.pronunciation.ids import pronunciation_id
from acervo.repository import jobs
from acervo.work.runner import Runner

from conftest import OWNER_EMAIL
from graph_records import example, lexeme, sense, vocabulary
from test_clips import SPEECH_URL, CorpusStub, recorded
from test_pronunciations import wav
from provider_rows import GOOGLE, VERTEX_IMAGE


@pytest.fixture
def corpus(server, monkeypatch) -> CorpusStub:
    from acervo.clips import corpus as corpus_module

    stub = CorpusStub()
    monkeypatch.setattr(corpus_module.httpx, "get", stub)
    monkeypatch.setattr(server.settings, "speech_url", SPEECH_URL)
    return stub


@pytest.fixture
def voice(server, monkeypatch):
    server.add_provider(GOOGLE)
    said: list[str] = []

    def speech(row, model, words, **kwargs):
        said.append(words)
        return wav(words), "audio/wav"

    monkeypatch.setattr("acervo.models.google_tts.speech", speech)
    return said


@pytest.fixture(autouse=True)
def providers(server, monkeypatch):
    server.add_provider(VERTEX_IMAGE)


@pytest.fixture
def runner(server) -> Runner:
    return Runner(server.settings)


@pytest.fixture
def everything(server, corpus, voice):
    """Every switch on, including recording in advance, which is off until chosen."""
    answer = server.put(
        "/pronunciations/settings",
        {"pregenerate": {"headword": True, "definitions": True, "examples": True}},
    )
    assert answer.status_code == 200, answer.json()
    return corpus, voice


def save(server):
    entry = lexeme(headword="picar", lemma="picar")
    itch = sense(entry["id"], definition="Causar picor.", order=0)
    chop = sense(entry["id"], definition="Cortar en trozos.", order=1)
    sentence = example(itch["id"], text="Me pica la espalda.", textLang="es")
    answer = server.push({
        "vocabularies": [vocabulary()], "lexemes": [entry], "senses": [itch, chop],
        "examples": [sentence],
    })
    assert answer.status_code == 200, answer.json()
    return entry, itch, chop, sentence, answer.json()["data"]


def answers(server, itch, chop):
    segment = recorded()["results"][0]["segment_id"]
    server.model.selection = {"senses": [
        {"senseId": itch["id"], "segmentId": segment,
         "translation": "My back itches.", "matchedTranslationForm": "itches"},
        {"senseId": chop["id"], "segmentId": None},
    ]}
    server.model.brief = {"senses": [
        {"senseId": one["id"], "styleId": "oil-painting", "anchorExampleId": None,
         "situation": "a kitchen", "subject": "an onion", "brief": f"A picture for {one['id']}"}
        for one in (itch, chop)
    ]}


def held(server, key):
    return [row for row in server.pull().json()["data"]["changes"][key] if not row["deleted"]]


# ── a save starts it ────────────────────────────────────────────────────────


def test_a_save_queues_one_enrich_in_the_same_write(server):
    entry, *_, written = save(server)
    open_jobs = jobs.open_jobs(server.owner)
    assert [(job["kind"], job["subject"], job["trigger"]) for job in open_jobs] == [
        ("enrich", {"kind": "lexeme", "id": entry["id"]}, "save")
    ]
    assert written["enrich"] == {entry["id"]: open_jobs[0]["id"]}


def test_a_refused_save_leaves_no_job(server):
    entry = lexeme()
    broken = sense(entry["id"], definition="")  # refused by validation
    answer = server.push({"vocabularies": [vocabulary()], "lexemes": [entry], "senses": [broken]})
    assert answer.status_code == 400
    assert jobs.open_jobs(server.owner) == []


def test_editing_a_word_queues_nothing(server, runner, corpus):
    entry, itch, chop, _, _ = save(server)
    runner.run_until_idle()
    stored = next(row for row in held(server, "lexemes") if row["id"] == entry["id"])
    renamed = next(row for row in held(server, "senses") if row["id"] == itch["id"])
    answer = server.push({
        "lexemes": [{**stored, "shortGloss": "to sting"}],
        "senses": [{**renamed, "definition": "Producir picor."}],
    })
    assert answer.status_code == 200, answer.json()
    assert jobs.open_jobs(server.owner) == []


def test_a_new_sense_on_a_held_word_queues_it_again(server, runner, corpus):
    entry, *_ = save(server)
    runner.run_until_idle()
    answer = server.push({"senses": [sense(entry["id"], definition="Morder un pez.", order=2)]})
    assert answer.status_code == 200, answer.json()
    assert [job["subject"]["id"] for job in jobs.open_jobs(server.owner)] == [entry["id"]]


def test_a_writer_that_will_ask_later_queues_nothing(server):
    """A bundle import restores its pictures first, then asks for the rest."""
    entry = lexeme()
    answer = server.post("/graph", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": "device000000001", "enrich": False,
        "changes": {"vocabularies": [vocabulary()], "lexemes": [entry], "senses": [sense(entry["id"])]},
    })
    assert answer.status_code == 200, answer.json()
    assert answer.json()["data"]["enrich"] == {}
    assert jobs.open_jobs(server.owner) == []


def test_a_word_saved_as_a_tombstone_queues_nothing(server):
    entry = lexeme(deleted=True)
    answer = server.push({"vocabularies": [vocabulary()], "lexemes": [entry]})
    assert answer.status_code == 200, answer.json()
    assert jobs.open_jobs(server.owner) == []


# ── the steps ───────────────────────────────────────────────────────────────


def test_a_saved_word_gets_clips_pictures_and_recordings_with_no_client(
    server, runner, everything
):
    corpus, said = everything
    entry, itch, chop, sentence, written = save(server)
    answers(server, itch, chop)

    assert runner.run_until_idle() == 1
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert job["state"] == "done", job
    assert [(step["name"], step["state"]) for step in job["steps"]] == [
        ("clips", "done"), ("pictures", "done"), ("pronunciations", "done"),
    ]
    assert job["steps"][0]["detail"] == {"found": 1}
    assert (job["steps"][1]["done"], job["steps"][1]["total"]) == (2, 2)

    word = next(row for row in held(server, "lexemes") if row["id"] == entry["id"])
    assert word["clipsSearchedAt"] is not None
    assert [row["origin"] for row in held(server, "examples")].count("subtitle") == 1

    pictures = {row["senseId"]: row for row in held(server, "imagePrompts")}
    assert set(pictures) == {itch["id"], chop["id"]}
    assert all(row["imageRef"] for row in pictures.values())
    assert (server.media / pictures[itch["id"]]["imageRef"]).exists()

    # The headword, both definitions and the owner's example — never the clip, which is already
    # recorded speech.
    recorded_ids = {row["id"] for row in held(server, "pronunciations")}
    assert recorded_ids == {
        pronunciation_id("lexeme", entry["id"]),
        pronunciation_id("sense", itch["id"]),
        pronunciation_id("sense", chop["id"]),
        pronunciation_id("example", sentence["id"]),
    }
    assert "picar" in said


def test_the_steps_run_in_order_clips_pictures_recordings(
    server, runner, everything, monkeypatch
):
    entry, itch, chop, *_ = save(server)
    answers(server, itch, chop)
    order: list[str] = []
    from acervo.services import clips, images, pronunciations

    for module, name in ((clips, "find_clips"), (images, "brief_lexeme"),
                         (images, "render_prompt"), (pronunciations, "pronounce")):
        original = getattr(module, name)

        def traced(*args, _original=original, _name=name, **kwargs):
            order.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, traced)
    runner.run_until_idle()
    first = {name: order.index(name) for name in dict.fromkeys(order)}
    assert first["find_clips"] < first["brief_lexeme"] < first["render_prompt"] < first["pronounce"]


def test_a_second_job_for_the_same_word_writes_nothing(server, runner, everything):
    entry, itch, chop, *_ = save(server)
    answers(server, itch, chop)
    runner.run_until_idle()
    cursor = server.pull().json()["data"]["cursor"]
    calls = len(server.model.calls), len(server.painter.calls)

    again = jobs.enqueue(server.owner, "enrich", trigger="manual", subject_kind="lexeme",
                         subject_id=entry["id"])
    runner.run_until_idle()
    finished = jobs.get(server.owner, again["id"])
    assert finished["state"] == "done"
    assert all(step["state"] == "skipped" for step in finished["steps"]), finished["steps"]
    assert server.pull().json()["data"]["cursor"] == cursor
    assert (len(server.model.calls), len(server.painter.calls)) == calls


def test_a_failed_clip_search_still_leaves_the_word_its_pictures(server, runner, everything):
    corpus, _ = everything
    corpus.status = (500, {"detail": "down"})
    entry, itch, chop, _, written = save(server)
    answers(server, itch, chop)
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert job["state"] == "failed"
    assert job["steps"][0]["state"] == "failed"
    assert job["steps"][0]["error"] == "corpus_unavailable"
    assert job["steps"][1]["state"] == "done"
    assert all(row["imageRef"] for row in held(server, "imagePrompts"))
    # Unconsulted, so Try again will find it.
    word = next(row for row in held(server, "lexemes") if row["id"] == entry["id"])
    assert word["clipsSearchedAt"] is None


def test_a_busy_image_provider_rests_the_job_and_nothing_is_counted(server, runner, everything):
    entry, itch, chop, _, written = save(server)
    answers(server, itch, chop)
    server.painter.error = litellm.RateLimitError(
        message="quota", llm_provider="openai", model="gpt-image-1"
    )
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert job["state"] == "queued"
    assert job["steps"][0]["state"] == "done"
    assert job["steps"][1]["state"] == "waiting"
    assert job["steps"][1]["error"] == "llm_rate_limited"
    assert job["steps"][2]["state"] == "pending"
    assert all(row["attempts"] == 0 and not row["imageRef"] for row in held(server, "imagePrompts"))


def test_a_declined_picture_is_recorded_and_not_drawn_again_on_its_own(server, runner, everything):
    entry, itch, chop, _, written = save(server)
    answers(server, itch, chop)
    server.painter.data = None  # no image data: `call.image` reads this as a refusal
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert job["steps"][1]["state"] == "failed"
    assert job["steps"][1]["error"] == "image_refused"
    assert job["steps"][1]["detail"] == {"refused": 2}
    assert job["steps"][2]["state"] == "done", "a declined picture does not stop the recordings"
    drawn = len(server.painter.calls)

    jobs.enqueue(server.owner, "enrich", trigger="manual", subject_kind="lexeme",
                 subject_id=entry["id"])
    runner.run_until_idle()
    assert len(server.painter.calls) == drawn


def test_switches_that_are_off_skip_their_steps(server, runner, corpus):
    assert server.put("/clips/settings", {"searchEnabled": False}).status_code == 200
    assert server.put("/images/settings", {"drawEnabled": False}).status_code == 200
    corpus.calls.clear()  # the settings readout asks the corpus how it is; the job must not
    entry, itch, chop, _, written = save(server)
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert job["state"] == "done"
    assert [step["state"] for step in job["steps"]] == ["skipped", "skipped", "skipped"]
    assert server.model.calls == [] and server.painter.calls == [] and corpus.calls == []


def test_a_deployment_without_a_corpus_skips_the_clip_step(server, runner):
    entry, itch, chop, _, written = save(server)
    answers(server, itch, chop)
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert job["steps"][0]["state"] == "skipped"
    assert job["state"] == "done"


def test_a_word_deleted_before_its_job_ran_is_left_alone(server, runner, corpus):
    entry, *_ , written = save(server)
    stored = next(row for row in held(server, "lexemes") if row["id"] == entry["id"])
    assert server.push({"lexemes": [{**stored, "deleted": True}]}).status_code == 200
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert [step["state"] for step in job["steps"]] == ["skipped", "skipped", "skipped"]
    assert server.model.calls == []


def test_a_word_set_aside_before_its_job_ran_is_left_alone(server, runner, corpus):
    entry, *_ , written = save(server)
    stored = next(row for row in held(server, "lexemes") if row["id"] == entry["id"])
    assert server.push({"lexemes": [{**stored, "status": "aside"}]}).status_code == 200
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert [step["state"] for step in job["steps"]] == ["skipped", "skipped", "skipped"]
    assert server.model.calls == [] and corpus.calls == []


def test_a_brief_the_writer_refuses_suppresses_the_sense_rather_than_failing(
    server, runner, corpus
):
    entry, itch, chop, _, written = save(server)
    server.model.selection = {"senses": []}
    server.model.brief = {"senses": [
        {"senseId": itch["id"], "refused": True, "refusalReason": "nothing to picture"},
        {"senseId": chop["id"], "styleId": "oil-painting", "anchorExampleId": None,
         "situation": "a kitchen", "subject": "an onion", "brief": "An onion."},
    ]}
    runner.run_until_idle()
    job = jobs.get(server.owner, written["enrich"][entry["id"]])
    assert job["steps"][1]["state"] == "done", job["steps"][1]
    pictures = {row["senseId"]: row for row in held(server, "imagePrompts")}
    assert pictures[itch["id"]]["suppressed"] is True
    assert pictures[chop["id"]]["imageRef"]
    assert image_prompt_id(itch["id"]) == pictures[itch["id"]]["id"]


# ── backfill ────────────────────────────────────────────────────────────────


def test_the_backfill_queues_an_ordinary_enrich_for_what_is_missing(server, runner, everything, capsys):
    """Words that predate the design, or an import that asked for nothing. The same job a save
    queues, so it is not a second pipeline."""
    entry, itch, chop, sentence, written = save(server)
    answers(server, itch, chop)
    runner.run_until_idle()  # this one is complete
    jobs.request_cancel(server.owner, written["enrich"][entry["id"]])

    second = lexeme(headword="toalla", lemma="toalla")
    assert server.push({"lexemes": [second], "senses": [sense(second["id"])]}).status_code == 200
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])

    assert admin.main(["jobs", "enqueue", "enrich", "--missing",
                       "--owner-email", OWNER_EMAIL]) == 0
    printed = capsys.readouterr().out
    assert "toalla" in printed and "picar" not in printed
    assert "1 word(s) queued." in printed
    queued = jobs.open_jobs(server.owner)
    assert [(job["kind"], job["subject"]["id"], job["trigger"]) for job in queued] == [
        ("enrich", second["id"], "backfill")
    ]


def test_the_backfill_can_be_looked_at_first_and_bounded(server, everything, capsys):
    for headword in ("toalla", "sobremesa"):
        word = lexeme(headword=headword, lemma=headword)
        assert server.push({"lexemes": [word], "senses": [sense(word["id"])]}).status_code == 200
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])

    assert admin.main(["jobs", "enqueue", "enrich", "--missing", "--owner-email", OWNER_EMAIL,
                       "--dry-run"]) == 0
    assert "would be enriched" in capsys.readouterr().out
    assert jobs.open_jobs(server.owner) == []

    assert admin.main(["jobs", "enqueue", "enrich", "--missing", "--owner-email", OWNER_EMAIL,
                       "--limit", "1"]) == 0
    assert len(jobs.open_jobs(server.owner)) == 1


def test_the_backfill_leaves_out_a_word_set_aside(server, everything, capsys):
    word = lexeme(headword="toalla", lemma="toalla", status="aside")
    assert server.push({"lexemes": [word], "senses": [sense(word["id"])]}).status_code == 200
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])

    assert admin.main(["jobs", "enqueue", "enrich", "--missing", "--owner-email", OWNER_EMAIL]) == 0
    assert "toalla" not in capsys.readouterr().out
    assert jobs.open_jobs(server.owner) == []


def test_the_backfill_takes_one_vocabulary_at_a_time(server, everything, capsys):
    assert server.push({"vocabularies": [vocabulary(language="en", definitionLang="en", order=1)]}).status_code == 200
    english = lexeme(language="en", headword="towel", lemma="towel", reading=None)
    assert server.push({"lexemes": [english], "senses": [sense(english["id"], definitionLang="en")]}).status_code == 200
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])

    assert admin.main(["jobs", "enqueue", "enrich", "--missing", "--owner-email", OWNER_EMAIL,
                       "--language", "es"]) == 0
    assert jobs.open_jobs(server.owner) == []
    assert admin.main(["jobs", "enqueue", "enrich", "--missing", "--owner-email", OWNER_EMAIL,
                       "--language", "en"]) == 0
    assert [job["subject"]["id"] for job in jobs.open_jobs(server.owner)] == [english["id"]]


def test_the_backfill_says_when_the_account_is_not_one(server, capsys):
    assert admin.main(["jobs", "enqueue", "enrich", "--missing",
                       "--owner-email", "nobody@account.example.com"]) == 2
