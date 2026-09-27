"""The narrow loop client, against recorded responses from the real service.

`fixtures/*.json` were captured from lexibeat 0.2.0 in-process (`schema.json` from 0.6.0; 0.4.0
added the `bundle` identity and 0.5.0 `family_details`) — the contract in the only shape
Acervo consumes. Re-record them when `deploy/acervo/lexibeat/pin.json` moves; the recorder is in
that commit's message and takes half a minute.

Offline by construction, as `tests/unit/clips/test_corpus.py` is: `httpx.MockTransport` serves the
recordings, so this is a test of the *client* and never of the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from acervo.loops.client import Item, LoopError, LoopService

FIXTURES = Path(__file__).parent / "fixtures"


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def serving(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def answering(payload, status: int = 200, *, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return handler


def service(handler) -> LoopService:
    return LoopService("http://lexibeat:8000/api/v1", http=serving(handler))


# ── what it can be asked for ────────────────────────────────────────────────


def test_the_catalogues_are_read_from_the_service_and_never_copied_here():
    """A family or a format added in a later version must appear with nothing changing on this
    side, which is only true while nothing here lists them."""
    schema = service(answering(recorded("schema"))).schema()
    assert schema.api_version == "2.0.0"
    formats = {one.id: one for one in schema.formats}
    assert {"classic", "radio-lesson", "story"} <= set(formats)
    assert all(one.label and one.description for one in schema.formats)
    radio = formats["radio-lesson"]
    assert radio.requires == ("writer", "multilingual_voice")
    assert radio.fallback == "classic"
    assert formats["story"].fallback is None
    assert radio.switches["repetitions"].choices == ("2", "3", "4")
    assert radio.switches["repetitions"].default == "3"
    assert radio.switches["remarks"].default is True
    assert radio.switches["remarks"].accepts(False) and not radio.switches["remarks"].accepts("no")
    assert len(schema.families) > 5 and "auto" not in [one.id for one in schema.families]
    assert all(one.label and one.description for one in schema.families)
    assert schema.max_items > 0
    assert schema.bundle_version == "3"


def test_a_deployment_with_no_samples_says_so_rather_than_failing():
    """Not an error: the service serves, and that is why its healthcheck asserts liveness. Worth
    saying, because the difference is recorded instruments against oscillators."""
    payload = {**recorded("schema"), "production_bundle": False, "palette": ["electronic"]}
    assert service(answering(payload)).schema().sample_free is True
    assert service(answering(recorded("schema"))).schema().sample_free is False


def test_liveness_is_a_question_that_answers_false_rather_than_raising():
    assert service(answering(recorded("health"))).alive() is True
    assert service(answering({"error": {"code": "x", "message": "y"}}, 503)).alive() is False


# ── a render ────────────────────────────────────────────────────────────────


def test_starting_a_render_sends_the_words_and_the_render_token():
    seen: list[httpx.Request] = []
    operation = service(answering(recorded("queued"), 202, seen=seen)).start(
        items=[Item("asco", "disgust", "repulsed, recoiling slightly")],
        source_language={"code": "es", "name": "Spanish"},
        target_language={"code": "en", "name": "English"},
        token="a-render-scoped-token", delivery="plain", seed=11,
        format="radio-lesson", switches={"repetitions": "4"}, script={"order": [0]},
    )
    body = json.loads(seen[0].content)
    assert body["format"] == "radio-lesson" and body["switches"] == {"repetitions": "4"}
    # A previous render's lines, sent back so new music says the same ones.
    assert body["script"] == {"order": [0]}
    assert body["items"] == [{"source": "asco", "target": "disgust",
                              "direction": "repulsed, recoiling slightly"}]
    assert body["source_language"] == {"code": "es", "name": "Spanish"}
    # The whole of what the generator is given to speak with: it holds no provider key of its own,
    # and no way of its own to find out what that voice can do.
    assert body["speech"] == {"token": "a-render-scoped-token", "delivery": "plain"}
    assert operation.status == "queued" and not operation.finished


def test_a_completed_operation_carries_the_loop_its_words_and_its_lines():
    operation = service(answering(recorded("completed"))).operation("whatever")
    assert operation.finished and operation.successful is True
    loop = operation.result
    assert loop is not None
    # §2.9's `loops` row...
    assert loop.style_id and loop.seed and loop.engine_version and loop.bed_fingerprint
    assert loop.format == "classic" and loop.fallback_from is None and loop.script is None
    assert loop.duration_seconds > 0 and loop.bpm > 0 and loop.audio_mime == "audio/mpeg"
    # ...its `loopItems`, with what was *said* and when each side is first heard...
    assert len(loop.items) == 2
    first = loop.items[0]
    assert first["source"] == "asco" and first["target"] == "disgust"
    assert first["start"] <= first["source_reveal"] <= first["target_reveal"] <= first["end"]
    # ...and its `loopCues`: every line, a word's drill one group, in the order heard.
    assert len(loop.cues) == 12
    assert [cue["group"] for cue in loop.cues] == [0] * 6 + [1] * 6
    assert [cue["side"] for cue in loop.cues[:6]] == ["source", "target"] * 3
    assert {cue["role"] for cue in loop.cues} == {"native", "guide"}
    assert loop.cues == tuple(sorted(loop.cues, key=lambda cue: cue["start"]))


def test_the_resolved_bed_is_not_in_the_answer_and_is_not_wanted():
    """Style, seed and engine version replay it; the fingerprint proves the replay. Nothing here
    stores opaque JSON."""
    assert "bed_spec" not in recorded("completed")["result"]


def test_an_unfinished_operation_reports_progress_rather_than_a_result():
    payload = {**recorded("queued"), "status": "running",
               "progress": {"fraction": 0.42, "message": "Synthesizing 7 of 12"}}
    operation = service(answering(payload)).operation("x")
    assert not operation.finished and operation.result is None
    assert operation.fraction == pytest.approx(0.42)
    assert operation.message == "Synthesizing 7 of 12"


def test_a_failed_render_is_an_answer_with_a_reason_rather_than_an_exception():
    payload = {**recorded("queued"), "status": "failed", "successful": False,
               "error": "RuntimeError: the voice refused"}
    operation = service(answering(payload)).operation("x")
    assert operation.finished and operation.successful is False
    assert "refused" in (operation.error or "")


# ── the track ───────────────────────────────────────────────────────────────


def test_the_track_is_fetched_from_the_url_the_service_gave_and_stored_as_it_arrives():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ID3mp3bytes", headers={"content-type": "audio/mpeg"})

    url = recorded("completed")["result"]["audio_url"]
    data, mime = LoopService("http://lexibeat:8000/api/v1", http=serving(handler)).track(url)
    assert data == b"ID3mp3bytes" and mime == "audio/mpeg"
    # Resolved against the service's own root, and never concatenated from anything a client sent:
    # this path came out of an answer this module parsed.
    assert str(seen[0].url) == f"http://lexibeat:8000{url}"


# ── what it refuses ─────────────────────────────────────────────────────────


def test_a_service_that_cannot_be_reached_is_its_own_refusal():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(LoopError) as refused:
        service(handler).schema()
    assert refused.value.code == "unreachable"


def test_a_busy_queue_is_told_apart_from_a_refusal():
    busy = {"error": {"code": "queue_full", "message": "The render queue is full."}}
    with pytest.raises(LoopError) as refused:
        service(answering(busy, 429)).operation("x")
    assert refused.value.code == "busy"
    assert "queue is full" in refused.value.message


def test_an_answer_that_describes_no_operation_is_refused_rather_than_half_read():
    for payload in ({}, {"status": "completed"}, ["not", "a", "mapping"]):
        with pytest.raises(LoopError):
            service(answering(payload)).operation("x")


def test_a_written_loop_carries_its_lines_and_the_script_to_say_them_again():
    loop = service(answering(recorded("completed-radio"))).operation("whatever").result
    assert loop is not None
    assert loop.format == "radio-lesson" and loop.fallback_from is None
    kinds = {cue["kind"] for cue in loop.cues}
    assert {"intro", "header", "example", "translation", "announce", "outro"} <= kinds
    # A line of no word says so, and a word's own line names the word by its index.
    intro = next(cue for cue in loop.cues if cue["kind"] == "intro")
    assert intro["item"] is None and intro["side"] is None and intro["role"] == "guide"
    assert {cue["item"] for cue in loop.cues if cue["kind"] == "say"} == {0, 1}
    # Kept whole and unread, to send back with the next render.
    assert isinstance(loop.script, dict) and loop.script.get("order") == [1, 0]


def test_a_render_that_fell_back_says_what_was_asked_for():
    loop = service(answering(recorded("completed-fallback"))).operation("whatever").result
    assert loop is not None
    assert (loop.format, loop.fallback_from) == ("classic", "radio-lesson")


def test_nothing_of_the_service_s_own_shape_escapes():
    loop = service(answering(recorded("completed"))).operation("whatever").result
    assert loop is not None
    assert set(loop.items[0]) == {"index", "source", "target", "start", "end",
                                  "source_reveal", "target_reveal"}
    assert set(loop.cues[0]) == {"kind", "section", "group", "item", "side", "role", "language",
                                 "text", "take", "start", "end"}
