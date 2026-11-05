"""The translation seam: one structured call, answered by Acervo, for the corpus to use.

`deploy/acervo/speech/serve.py` is the wiring that knows the retrieval service's prompts, schemas
and exception types, and it lives in the one image where that package is installed. What is under
test here is the half that is Acervo's — an HTTP call home to `POST /companion/text` — and it
imports nothing of that service's, which is why it can be tested from a virtualenv that does not
carry FastAPI, uvicorn, yt-dlp or Stanza. The route itself is `tests/unit/server/test_companion.py`.
"""

from __future__ import annotations

import json

import httpx
import pytest

from acervo import trace
from acervo.speech import provider as module
from acervo.speech.provider import AcervoGenerator, GenerationFailed

URL = "http://server:8000/api/acervo/v1"
TOKEN = "an-operator-token-0123456789"


@pytest.fixture
def home(monkeypatch):
    """Acervo, answering. `state["answer"]` is the response it gives, or an exception to raise."""
    calls: list[dict] = []
    state: dict = {"answer": httpx.Response(200, json={"data": {
        "payload": {"target_text": "it itches"}, "provider": "cloudflare", "model": "second",
        "seconds": 0.4}})}

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if isinstance(state["answer"], BaseException):
            raise state["answer"]
        return state["answer"]

    monkeypatch.setattr(module.httpx, "post", post)
    return calls, state


def generator(stage="clip-translate"):
    return AcervoGenerator(URL, TOKEN, stage)


# ── the cache key ───────────────────────────────────────────────────────────


def test_it_reports_the_order_and_never_the_provider_that_answered(home):
    """The service caches on `provider` and `model`, so a fall-through that moved them would miss
    the cache on every retry and re-translate work already paid for. The provider that answered
    travels in the metadata instead, where it is provenance rather than a key."""
    asked = generator()
    answer = asked.generate(instructions="translate", user_text="Me pica.", schema={})
    assert answer.provider_metadata == {"answered_by": "cloudflare:second"}
    assert (asked.provider, asked.model) == ("acervo-chain", "deployment-default")


# ── what is sent ────────────────────────────────────────────────────────────


def test_it_calls_home_with_the_operator_token_and_a_request_id(home):
    calls, _ = home
    generator("clip-align").generate(instructions="align", user_text="Me pica.", schema={},
                                     temperature=0.2)
    sent = calls[-1]
    assert sent["url"] == f"{URL}/companion/text"
    assert sent["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert trace.well_formed(sent["headers"][trace.HEADER])
    assert sent["json"]["caller"] == "clip-align"
    assert sent["json"]["text"] == "Me pica."
    assert sent["json"]["temperature"] == 0.2


def test_no_schema_is_sent_at_all(home):
    """Constrained decoding is not used here, or anywhere — docs/architecture/models.md says why,
    and the alignment measurement behind it is the strongest case that was tried and still lost."""
    calls, _ = home
    generator().generate(instructions="Translate it.", user_text="me pica",
                         schema={"type": "OBJECT", "properties": {"target_text": {"type": "STRING"}}})
    assert set(calls[-1]["json"]) <= {"instructions", "text", "caller", "temperature"}


def test_the_shape_is_stated_in_the_instructions(home):
    """With no schema sent anywhere, the instructions are the only statement of the shape. The
    retrieval service's two prompts name no field at all, so no model could answer without this."""
    calls, _ = home
    generator().generate(instructions="Translate it.", user_text="me pica",
                         schema={"type": "OBJECT", "properties": {"target_text": {"type": "STRING"}}})
    instructions = calls[-1]["json"]["instructions"]
    assert instructions.startswith("Translate it.")
    assert '"type": "object"' in instructions and "target_text" in instructions
    assert "OBJECT" not in instructions


# ── what comes back ─────────────────────────────────────────────────────────


def test_a_parsed_object_comes_back_with_how_long_it_took(home):
    answer = generator().generate(instructions="translate", user_text="Me pica.", schema={})
    assert answer.payload == {"target_text": "it itches"}
    assert json.loads(answer.raw_output) == {"target_text": "it itches"}
    assert answer.latency_ms >= 0


def test_a_payload_that_is_not_an_object_is_retryable_and_carries_the_raw_output(home):
    _calls, state = home
    state["answer"] = httpx.Response(200, json={"data": {"payload": ["a list"], "provider": "p", "model": "m"}})
    with pytest.raises(GenerationFailed) as raised:
        generator().generate(instructions="t", user_text="x", schema={})
    assert raised.value.code == "invalid_output" and raised.value.retryable is True
    assert raised.value.raw == '["a list"]'


# ── how failure is classified ───────────────────────────────────────────────


@pytest.mark.parametrize("status, code, expected, retryable", [
    (503, "llm_rate_limited", "rate_limited", True),
    (503, "llm_unavailable", "temporarily_unavailable", True),
    (502, "llm_unreachable", "temporarily_unavailable", True),
    (502, "llm_unusable", "invalid_output", True),
    (503, "llm_authentication", "provider_unavailable", False),
    (503, "llm_configuration", "provider_unavailable", False),
    (503, "capture_unavailable", "provider_unavailable", False),
    (401, "unauthenticated", "provider_unavailable", False),
])
def test_each_refusal_maps_to_what_the_service_acts_on(home, status, code, expected, retryable):
    """The service draws one distinction — wait or do not — and it is the one Acervo's codes
    already draw: a provider that is busy says nothing about the request, while a refused key, a
    server with no provider or a wrong token is a mistake to fix."""
    _calls, state = home
    state["answer"] = httpx.Response(status, json={"error": {"code": code, "message": "said so"}})
    with pytest.raises(GenerationFailed) as raised:
        generator().generate(instructions="t", user_text="x", schema={})
    assert (raised.value.code, raised.value.retryable) == (expected, retryable)
    assert str(raised.value) == "said so"


def test_acervo_out_of_reach_is_worth_waiting_for(home):
    _calls, state = home
    state["answer"] = httpx.ConnectError("refused")
    with pytest.raises(GenerationFailed) as raised:
        generator().generate(instructions="t", user_text="x", schema={})
    assert raised.value.retryable is True


def test_this_container_holds_no_key_and_reaches_no_database():
    """It imports neither the provider package nor anything that reads Acervo's state."""
    source = open(module.__file__ or "", encoding="utf-8").read()
    for name in ("acervo.models", "acervo.repository", "acervo.settings", "litellm"):
        assert name not in source


# ── the shape of the answer, said twice ─────────────────────────────────────


def test_googles_type_spelling_is_renamed_into_json_schemas():
    """The retrieval service's schemas are written in Google's GenAI dialect, which spells the type
    keywords in capitals. `acervo.models` speaks JSON Schema. Nothing else about the two differs for
    these shapes, so this is a rename — and it is applied unconditionally because it is a no-op on a
    schema that was already JSON Schema."""
    from acervo.speech.provider import json_schema

    assert json_schema({
        "type": "OBJECT",
        "properties": {
            "alignments": {
                "type": "ARRAY",
                "minItems": 2,
                "items": {
                    "type": "OBJECT",
                    "properties": {"source_id": {"type": "STRING", "enum": ["S1", "S2"]}},
                    "required": ["source_id"],
                },
            },
        },
        "required": ["alignments"],
    }) == {
        "type": "object",
        "properties": {
            "alignments": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    # An enum's *values* are data, not type keywords, and are left alone.
                    "properties": {"source_id": {"type": "string", "enum": ["S1", "S2"]}},
                    "required": ["source_id"],
                },
            },
        },
        "required": ["alignments"],
    }

    # Already JSON Schema, including a union, and unchanged.
    already = {"type": "object", "properties": {"segmentId": {"type": ["string", "null"]}}}
    assert json_schema(already) == already
