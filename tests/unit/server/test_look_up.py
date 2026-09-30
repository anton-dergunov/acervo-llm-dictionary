"""A word tapped while reading — a story, a loop's line, an example — looked up and added.

The same quick look-up a photo tap makes, told the sentence is finished text rather than notes to
correct; and an Add that files the word in the Inbox through the headless capture job, carrying the
look-up's answer so the job writes the word the owner saw without resolving it again.
"""

from __future__ import annotations

import pytest

from acervo.domain import SCHEMA_VERSION
from acervo.repository import jobs
from acervo.work.runner import Runner

from graph_records import DEVICE, lexeme, vocabulary
from test_capture import ARTICLE

SENTENCE = "Camina con paso firme hacia el mostrador y espera su turno."

RESOLUTION = {
    "language": "es", "headword": "con paso firme", "lemma": "con paso firme", "pos": "phrase",
    "sentences": [{"text": SENTENCE, "translation": "He walks firmly up to the counter."}],
    "gloss": "with a firm step", "note": "",
}


@pytest.fixture
def reading(server):
    server.push({"vocabularies": [vocabulary()]})
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])
    server.model.resolution = dict(RESOLUTION)
    server.model.article = {**ARTICLE, "headword": "con paso firme", "lemma": "con paso firme"}
    return server


def look_up(server, **overrides):
    return server.post("/capture/resolve", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "source": "reading", "text": SENTENCE,
        "selection": {"start": 11, "end": 15}, **overrides,
    })


def messages(call):
    said = call.get("messages") or []
    system = next((str(m["content"]) for m in said if m["role"] == "system"), "")
    user = next((str(m["content"]) for m in said if m["role"] == "user"), "")
    return system, user


def test_a_tap_while_reading_is_a_quick_look_up_that_keeps_the_sentence_as_written(reading):
    answer = look_up(reading)
    assert answer.status_code == 200, answer.json()
    assert answer.json()["data"]["resolution"]["gloss"] == "with a firm step"

    call = reading.model.calls[-1]
    system, user = messages(call)
    assert "*paso*" in user, "the tapped word is pointed at"
    assert "something the learner was reading" in user
    assert "A quick look-up" in system and "A sentence the learner was reading" in system
    assert "Text from a photograph" not in system
    assert call["model"] == "gemini/gemini-3.5-flash-lite", "the quick chain answers it"


def test_reading_is_a_quick_look_up_only(reading):
    reading.capture(text=SENTENCE, source="reading")
    system, _ = messages(reading.model.calls[0])
    assert "A sentence the learner was reading" not in system


def test_a_word_already_held_comes_back_as_the_word_you_have(reading):
    reading.push({"lexemes": [lexeme(headword="con paso firme", lemma="con paso firme")]})
    body = look_up(reading).json()["data"]
    assert [d["headword"] for d in body["duplicates"]] == ["con paso firme"]


def test_add_files_the_word_in_the_inbox_without_resolving_it_again(reading):
    resolution = look_up(reading).json()["data"]["resolution"]
    reading.model.calls.clear()
    answer = reading.post("/captures", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "mode": "single", "text": SENTENCE,
        "headword": resolution["headword"], "language": "es", "resolution": resolution,
        "sourceTitle": "El perro de la panadería",
    })
    assert answer.status_code == 202, answer.json()
    job = answer.json()["data"]

    Runner(reading.settings).run_until_idle()
    finished = jobs.get(reading.owner, job["id"])
    assert finished["state"] == "done", finished
    [word] = finished["steps"][0]["detail"]["words"]
    assert word["outcome"] == "saved"
    systems = [messages(call)[0] for call in reading.model.calls]
    assert systems and not any("## Fixing the input" in system for system in systems), \
        "the look-up was not asked again"

    changes = reading.pull().json()["data"]["changes"]
    created = next(row for row in changes["lexemes"] if row["id"] == word["lexemeId"])
    assert (created["headword"], created["status"]) == ("con paso firme", "inbox")
    [attestation] = changes["attestations"]
    assert attestation["text"] == SENTENCE, "the sentence is kept exactly as it was read"
    assert attestation["sourceTitle"] == "El perro de la panadería"


def test_add_refuses_a_look_up_whose_sentence_the_text_does_not_hold(reading):
    resolution = {**RESOLUTION, "sentences": [{"text": "Camina firme hacia el mostrador."}]}
    answer = reading.post("/captures", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "mode": "single", "text": SENTENCE,
        "resolution": resolution,
    })
    job = answer.json()["data"]
    Runner(reading.settings).run_until_idle()
    finished = jobs.get(reading.owner, job["id"])
    assert (finished["state"], finished["error"]) == ("failed", "invalid_input"), finished
