"""One row, one call — and the classification that the retry contract rests on.

The exceptions here are real LiteLLM exceptions, not stand-ins. Stubbing this package's own error
types would leave `classify()` untested, and `classify()` is the thing that can change retry
behaviour without the retry code changing.
"""

from __future__ import annotations

import base64
import json

import httpx
import litellm
import pytest

from provider_rows import CLOUDFLARE as CLOUDFLARE_DOCUMENT, GEMINI as GEMINI_DOCUMENT
from provider_rows import GEMINI_KEY, GOOGLE as GOOGLE_DOCUMENT, SERVICE_ACCOUNT, VERTEX as VERTEX_DOCUMENT
from provider_rows import google_voices, provider

from acervo.models import call, listing
from acervo.models.errors import RETRYABLE, TERMINAL, ProviderRefused, ProviderUnavailable

GEMINI = provider(GEMINI_DOCUMENT)          # JSON mode: native
CLOUDFLARE = provider(CLOUDFLARE_DOCUMENT)  # JSON mode: in the prompt
VERTEX = provider(VERTEX_DOCUMENT)          # Google Cloud, signed in with a credentials file
GOOGLE = provider(GOOGLE_DOCUMENT)          # Google Cloud, signed in with a key


@pytest.fixture(autouse=True)
def listed_voices(monkeypatch):
    """Google's voice list, without the network."""
    monkeypatch.setattr(listing, "_google_voices", google_voices)
PRIVATE = "provider details that must stay private"


def reply(text: str, model: str = "gemini/gemini-3.5-flash-lite"):
    return litellm.ModelResponse(
        model=model,
        choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
    )


def response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://provider.example.com"))


def failures():
    """Every LiteLLM exception Acervo can meet, built the way its constructor wants."""
    return {
        "authentication": litellm.AuthenticationError(message=PRIVATE, llm_provider="p", model="m"),
        "permission": litellm.PermissionDeniedError(
            message=PRIVATE, llm_provider="p", model="m", response=response(403)
        ),
        "bad_request": litellm.BadRequestError(message=PRIVATE, model="m", llm_provider="p"),
        "context_window": litellm.ContextWindowExceededError(message=PRIVATE, model="m", llm_provider="p"),
        "not_found": litellm.NotFoundError(message=PRIVATE, model="m", llm_provider="p"),
        "rate_limit": litellm.RateLimitError(message=PRIVATE, llm_provider="p", model="m"),
        "internal": litellm.InternalServerError(message=PRIVATE, llm_provider="p", model="m"),
        "unavailable": litellm.ServiceUnavailableError(message=PRIVATE, llm_provider="p", model="m"),
        "teapot": litellm.APIError(status_code=418, message=PRIVATE, llm_provider="p", model="m"),
        "timeout": litellm.Timeout(message=PRIVATE, model="m", llm_provider="p"),
        "connection": litellm.APIConnectionError(message=PRIVATE, llm_provider="p", model="m"),
        "unknown": RuntimeError(PRIVATE),
    }


REASONS = {
    "authentication": "authentication",
    "permission": "authentication",
    "bad_request": "configuration",
    "context_window": "configuration",
    "not_found": "configuration",
    "rate_limit": "rate_limited",
    "internal": "unavailable",
    "unavailable": "unavailable",
    "teapot": "refused",
    "timeout": "unreachable",
    "connection": "unreachable",
    "unknown": "refused",
}


@pytest.mark.parametrize("name", sorted(REASONS), ids=sorted(REASONS))
def test_every_provider_failure_lands_on_exactly_one_reason(name):
    reason, _status = call.classify(failures()[name])
    assert reason == REASONS[name]


def test_a_timeout_and_a_dropped_connection_are_not_classified_by_their_status():
    """The two that a status-only map gets wrong, and the reason this test exists at all.

    `Timeout` carries 408 and `APIConnectionError` carries 500. Read numerically, a timeout becomes
    `refused` — which `scripts/ingest_vocabulary_file.py` does not retry. The retry behaviour would
    have changed without a line of the retry code changing.
    """
    timeout, connection = failures()["timeout"], failures()["connection"]
    assert timeout.status_code == 408 and connection.status_code == 500
    assert call.classify(timeout) == ("unreachable", 408)
    assert call.classify(connection) == ("unreachable", 500)


@pytest.mark.parametrize("name", sorted(REASONS), ids=sorted(REASONS))
def test_a_failure_is_either_retryable_at_the_next_row_or_terminal_for_the_chain(monkeypatch, name):
    monkeypatch.setattr(call, "completion", _raising(failures()[name]))
    with pytest.raises((ProviderRefused, ProviderUnavailable)) as caught:
        call.text("hello", row=GEMINI)
    expected = ProviderUnavailable if REASONS[name] in RETRYABLE else ProviderRefused
    assert isinstance(caught.value, expected)
    assert (REASONS[name] in RETRYABLE) != (REASONS[name] in TERMINAL)


def test_the_failing_row_and_model_are_carried_on_the_error(monkeypatch):
    monkeypatch.setattr(call, "completion", _raising(failures()["rate_limit"]))
    with pytest.raises(ProviderUnavailable) as caught:
        call.text("hello", row=GEMINI)
    assert caught.value.provider_id == "gemini-api"
    assert caught.value.model == "gemini-3.5-flash-lite"
    assert caught.value.status == 429


def test_a_key_echoed_back_by_a_provider_is_redacted_before_it_reaches_the_exception(monkeypatch):
    """Providers echo the request in an error, and this repository is public."""
    monkeypatch.setattr(
        call,
        "completion",
        _raising(
            litellm.BadRequestError(
                message=f"rejected x-goog-api-key={GEMINI_KEY}", model="m", llm_provider="p"
            )
        ),
    )
    with pytest.raises(ProviderRefused) as caught:
        call.text("hello", row=GEMINI)
    assert GEMINI_KEY not in caught.value.detail
    assert "«redacted»" in caught.value.detail


def test_a_native_row_is_asked_for_json_and_a_prompt_row_is_not(monkeypatch):
    """The capability declaration doing its one job: the package adapts at the call boundary."""
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply('{"a": 1}')))

    call.text("hello", row=GEMINI, as_json=True)
    assert calls[-1]["response_format"] == {"type": "json_object"}

    call.text("hello", row=CLOUDFLARE, as_json=True)
    assert "response_format" not in calls[-1]


def test_a_prompt_rows_reply_is_still_parsed(monkeypatch):
    """`prompt` means the instruction is the prompt's job, not that JSON is not expected back."""
    monkeypatch.setattr(call, "completion", _recording([], reply('{"headword": "el garfio"}')))
    assert call.text("hello", row=CLOUDFLARE, as_json=True).parsed == {"headword": "el garfio"}


def test_a_reply_that_is_not_json_parses_to_none_rather_than_raising(monkeypatch):
    """Whether an unreadable reply is an error is Acervo's question, not the provider's."""
    monkeypatch.setattr(call, "completion", _recording([], reply("not json at all")))
    result = call.text("hello", row=GEMINI, as_json=True)
    assert result.parsed is None
    assert result.text == "not json at all"


def test_a_fenced_reply_is_unwrapped(monkeypatch):
    monkeypatch.setattr(call, "completion", _recording([], reply('```json\n{"a": 1}\n```')))
    assert call.text("hello", row=GEMINI, as_json=True).parsed == {"a": 1}


def test_the_row_supplies_its_credential_its_endpoint_and_its_parameters(monkeypatch):
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))

    call.text("hello", row=GEMINI, system="be brief")
    assert calls[-1]["api_key"] == GEMINI_KEY
    assert calls[-1]["model"] == "gemini/gemini-3.5-flash-lite"
    assert calls[-1]["messages"][0] == {"role": "system", "content": "be brief"}
    # The constant, not a literal: it is set from `admin calls` against a real deployment and
    # will move again as the log says more. A test that pinned the number would make the
    # measurement the thing that has to justify itself to the test.
    assert calls[-1]["timeout"] == call.TIMEOUT_SECONDS
    assert "vertex_location" not in calls[-1]

    # Vertex is reached with the provider's own credentials file, project and location, per call:
    # nothing process-wide, so two Google Cloud providers can be two accounts.
    call.text("hello", row=VERTEX)
    assert calls[-1]["model"] == "vertex_ai/gemini-3.8-flash"
    assert calls[-1]["vertex_location"] == "global"
    assert calls[-1]["vertex_project"] == "example-project"
    assert json.loads(calls[-1]["vertex_credentials"]) == SERVICE_ACCOUNT
    assert "api_key" not in calls[-1]


def test_a_caller_may_ask_for_generation_settings_and_the_row_still_wins(monkeypatch):
    """The whole design of `params` in one test.

    A caller passes what the *task* wants — a story hot, its translation cold — and a family passes
    what the *provider* needs. When they disagree the family wins, because a value there was put
    there because something refused or misbehaved without it, and a caller's preference quietly
    undoing that would hide the mistake and spend money proving it again.
    """
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))

    # Gemini deliberately pins no temperature, so the caller's reaches the provider. This is the
    # case the argument exists for.
    assert "temperature" not in GEMINI.params_for("text")
    call.text("write me a story", row=GEMINI, params={"temperature": 1.0})
    assert calls[-1]["temperature"] == 1.0

    call.text("translate it", row=GEMINI, params={"temperature": 0.2})
    assert calls[-1]["temperature"] == 0.2

    # And a caller cannot reach past what the provider states: Vertex is sent its location, and
    # asking for another one does not move it.
    call.text("hello", row=VERTEX, params={"vertex_location": "somewhere-else", "temperature": 0.9})
    assert calls[-1]["vertex_location"] == "global"
    assert calls[-1]["temperature"] == 0.9  # untouched by the row, so it still lands

    # Passing nothing changes nothing, so every existing caller is unaffected.
    call.text("hello", row=GEMINI)
    assert "temperature" not in calls[-1]


def test_litellms_own_retries_are_switched_off_on_every_call(monkeypatch):
    """Both of them. `max_retries` is the provider SDK's and defaults to 2 when LiteLLM sets it.

    `models/chain.py` is the only fall-through in this codebase, and `acervo.client` carries no
    retries for the same reason: a retry inside the transport changes the behaviour of retry code
    that lives — and is tested — somewhere else.
    """
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))
    call.text("hello", row=GEMINI)
    assert calls[-1]["num_retries"] == 0
    assert calls[-1]["max_retries"] == 0


def test_the_answer_names_the_pair_that_answered_and_how_long_it_took(monkeypatch):
    monkeypatch.setattr(call, "completion", _recording([], reply("{}")))
    answer = call.text("hello", row=GEMINI).answer
    assert answer.provider_id == "gemini-api"
    assert answer.model == "gemini-3.5-flash-lite"  # the first, none having been named
    assert answer.seconds >= 0
    assert answer.attempts == (("gemini-api", "gemini-3.5-flash-lite"),)


def test_the_model_the_chain_chose_is_the_one_asked(monkeypatch):
    """A row offers several; the caller says which. Without this the second free-tier bucket is
    listed and never actually reached."""
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))
    result = call.text("hello", row=GEMINI, model="gemini-3.1-flash-lite")
    assert calls[-1]["model"] == "gemini/gemini-3.1-flash-lite"
    assert result.answer.model == "gemini-3.1-flash-lite"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "audio/wav"),
        (b"ID3\x04\x00", "audio/mpeg"),
        (b"\xff\xfb\x90", "audio/mpeg"),
        (b"OggS\x00", "audio/ogg"),
        (b"nothing recognisable", "application/octet-stream"),
    ],
)
def test_audio_is_labelled_by_what_it_is_rather_than_by_what_was_hoped(data, expected):
    """Gemini answers WAV and Cloudflare's Aura answers MP3, so a hardcoded type is wrong for one
    of them — and a clip stored under the wrong container is a file nothing plays, found much
    later than the call that made it."""
    assert call.audio_mime(data) == expected


def test_a_cost_the_provider_did_not_report_is_none_rather_than_a_failure(monkeypatch):
    """Cost is provenance. `completion_cost()` raises for a model absent from LiteLLM's price
    table — every Cloudflare `@cf/…` id and every local model — and provenance must not be able to
    fail a capture."""
    monkeypatch.setattr(call, "completion", _recording([], reply("{}")))
    assert call.text("hello", row=GEMINI).answer.cost_usd is None


def test_a_reported_cost_is_carried(monkeypatch):
    answered = reply("{}")
    answered._hidden_params = {"response_cost": 0.00042}
    monkeypatch.setattr(call, "completion", _recording([], answered))
    assert call.text("hello", row=GEMINI).answer.cost_usd == pytest.approx(0.00042)


def test_hidden_reasoning_is_the_librarys_problem_and_never_reaches_the_text(monkeypatch):
    """`llm.py` skipped Google's `thought` parts by hand. LiteLLM separates `reasoning_content`
    from `content`, so the hand-written skip is not ported — this asserts we read the right one."""
    answered = reply('{"headword": "el garfio"}')
    answered.choices[0].message.reasoning_content = "deliberation nobody asked for"
    monkeypatch.setattr(call, "completion", _recording([], answered))
    result = call.text("hello", row=GEMINI, as_json=True)
    assert result.parsed == {"headword": "el garfio"}
    assert "deliberation" not in result.text


def test_the_requested_size_reaches_a_row_that_says_it_chooses_its_own_resolution(monkeypatch):
    """Vertex takes `size` only as an aspect ratio — the resolution rides in `params.image` — so
    the parameter is still sent and the caller is told the pixels were not honoured."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    result = call.image("a hook", row=VERTEX, size=(512, 512))
    assert calls[-1]["size"] == "512x512"
    assert calls[-1]["imageConfig"] == {"imageSize": "1K"}
    assert any("chooses its own resolution" in warning for warning in result.answer.warnings)


def test_a_seed_a_provider_cannot_honour_is_dropped_with_a_warning_rather_than_sent(monkeypatch):
    """The companion of the style rule in `speech`, and it exists because the two ways of getting
    this wrong are both silent: LiteLLM never puts a seed in Vertex's request at all, and turns it
    into an `extra_body` field OpenAI's Images API rejects with a 400. Recording a seed that did
    nothing is worse than recording none — it claims a picture can be reproduced when it cannot."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    result = call.image("a hook", row=VERTEX, seed=17)
    assert "seed" not in calls[-1]
    assert any("not reproducible" in warning for warning in result.answer.warnings)


def test_a_seed_reaches_a_row_that_honours_it(monkeypatch):
    monkeypatch.setattr("acervo.models.cloudflare.image",
                        lambda *a, **k: (b"IMG", "image/png"))
    result = call.image("a hook", row=CLOUDFLARE, seed=17)
    assert result.answer.warnings == ()


def test_the_requested_resolution_survives_litellms_vertex_mapping():
    """A contract test against LiteLLM itself, because this failure is invisible at runtime.

    `image_size` is in LiteLLM's supported-parameter list for this model and is dropped anyway: it
    is not in `default_params`, so the non-default pass never sees it, and it *is* in
    `openai_params`, so the provider-specific pass skips it. It falls through both gates and the
    call succeeds at whatever resolution Vertex feels like. `imageConfig` is the one channel that
    survives, and this pins it so a LiteLLM upgrade that changes the mapping fails here rather than
    quietly costing a sweep its resolution.
    """
    from litellm.llms.vertex_ai.image_generation import get_vertex_ai_image_generation_config
    from litellm.utils import get_optional_params_image_gen

    row = VERTEX
    model = row.models_for("image")[0]
    mapped = get_optional_params_image_gen(
        model=model,
        custom_llm_provider="vertex_ai",
        provider_config=get_vertex_ai_image_generation_config(model),
        size="1024x1024",
        **row.params_for("image"),
    )
    assert mapped["imageConfig"] == {"imageSize": "1K"}
    assert mapped["aspectRatio"] == "1:1"


def _answered_with_a_picture():
    url = "data:image/png;base64," + base64.b64encode(b"PNGDATA").decode()
    message = litellm.Message(role="assistant", content="")
    message.images = [{"image_url": {"url": url}}]
    return litellm.ModelResponse(choices=[{"index": 0, "message": message}])


def test_reference_pictures_go_over_the_chat_route_with_the_rows_resolution(monkeypatch):
    """`image_generation` takes no image for Vertex Gemini, and `completion` with `modalities`
    does. The pictures come first and the prompt last, and `imageConfig` gains the aspect ratio
    `size` would otherwise have carried — measured to arrive, as 1024x1024 in 52 of 52."""
    calls = []
    monkeypatch.setattr(call, "image_generation", _raising(AssertionError("the text-only route")))
    monkeypatch.setattr(call, "completion", _recording(calls, _answered_with_a_picture()))
    webp = b"RIFF\x00\x00\x00\x00WEBPVP8 "
    result = call.image("a later moment", row=VERTEX, size=(1024, 1024),
                        references=[webp, webp])
    assert result.data == b"PNGDATA" and result.mime == "image/png"
    sent = calls[-1]
    assert sent["modalities"] == ["image", "text"]
    content = sent["messages"][0]["content"]
    assert [part["type"] for part in content] == ["image_url", "image_url", "text"]
    assert content[0]["image_url"]["url"].startswith("data:image/webp;base64,")
    assert content[-1]["text"] == "a later moment"
    assert sent["imageConfig"] == {"imageSize": "1K", "aspectRatio": "1:1"}
    assert sent["vertex_location"] == "global"


def test_reference_pictures_a_row_cannot_read_are_dropped_with_a_warning(monkeypatch):
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    monkeypatch.setattr(call, "completion", _raising(AssertionError("the chat route")))
    monkeypatch.setattr("acervo.models.cloudflare.image", lambda *a, **k: (b"PNG", "image/png"))
    result = call.image("a hook", row=CLOUDFLARE, references=[b"one"])
    assert result.data == b"PNG"
    assert any("no reference pictures" in warning for warning in result.answer.warnings)


def test_a_chat_reply_with_no_picture_is_a_refusal_rather_than_an_empty_image(monkeypatch):
    message = litellm.Message(role="assistant", content="I cannot draw that.")
    monkeypatch.setattr(call, "completion", _recording(
        [], litellm.ModelResponse(choices=[{"index": 0, "message": message}])))
    with pytest.raises(ProviderRefused, match="cannot draw that"):
        call.image("a hook", row=VERTEX, references=[b"one"])


def test_a_row_that_cannot_take_the_response_format_is_not_sent_it(monkeypatch):
    """Vertex refuses the parameter outright — "Setting `response_format` is not supported by
    vertex_ai" — so the row says it cannot take it and the call path has no provider branch."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNGDATA").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    call.image("a hook", row=VERTEX)
    assert "response_format" not in calls[-1]


def test_vertex_is_sent_the_providers_own_project_and_location(monkeypatch):
    """Vertex needs its project as a call argument, not read from the credentials: a setting the
    owner typed, sent with every call rather than read from a process-wide default."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    call.image("a hook", row=VERTEX)
    assert calls[-1]["vertex_project"] == "example-project"
    assert calls[-1]["vertex_location"] == "global"


def test_a_row_whose_kind_goes_through_an_adapter_does_not_reach_litellm(monkeypatch):
    """Cloudflare images are the one thing LiteLLM does not cover, and the row says so."""
    monkeypatch.setattr(call, "image_generation", _raising(AssertionError("litellm was called")))
    monkeypatch.setattr("acervo.models.cloudflare.image", lambda *a, **k: (b"IMG", "image/png"))
    result = call.image("a hook", row=CLOUDFLARE)
    assert result.data == b"IMG"
    assert result.answer.provider_id == "cloudflare"
    assert result.answer.model == "@cf/black-forest-labs/flux-2-klein-4b"


def test_a_style_a_provider_cannot_follow_is_dropped_with_a_warning_rather_than_spoken(monkeypatch):
    """An instruction sent to a voice that does not take instructions gets read aloud."""
    sent = []
    monkeypatch.setattr("acervo.models.cloudflare.speech",
                        lambda *a, **k: sent.append(k) or (b"ID3MP3", "audio/mpeg"))
    result = call.speech("hello", row=CLOUDFLARE, language="en", style="cheerful")
    assert result.answer.warnings == ("style is not supported by this provider",)
    assert sent[-1]["style"] is None




def test_style_is_decided_per_model_because_one_route_serves_voices_that_differ(monkeypatch):
    """Google's WaveNet and Gemini voices share an endpoint; only the Gemini ones take a direction."""
    sent = []
    monkeypatch.setattr("acervo.models.google_tts.speech",
                        lambda *a, **k: sent.append(k) or (b"ID3MP3", "audio/mpeg"))
    expressive = call.speech("¡Qué pica!", row=GOOGLE, model="gemini-3.1-flash-tts-preview",
                             language="es", style="exasperated")
    plain = call.speech("picar", row=GOOGLE, model="Wavenet", language="es", style="exasperated")
    assert sent[0]["style"] == "exasperated" and expressive.answer.warnings == ()
    assert sent[1]["style"] is None and plain.answer.warnings == ("style is not supported by this provider",)


def test_the_voice_that_spoke_is_the_models_default_for_the_language_unless_one_is_asked_for(monkeypatch):
    monkeypatch.setattr("acervo.models.google_tts.speech", lambda *a, **k: (b"ID3MP3", "audio/mpeg"))
    assert call.speech("picar", row=GOOGLE, model="Wavenet", language="es").voice == "es-ES-Wavenet-F"
    assert call.speech("咬", row=GOOGLE, model="Wavenet", language="zh-Hans").voice == "cmn-CN-Wavenet-A"
    assert call.speech("picar", row=GOOGLE, model="Wavenet", language="es",
                       voice="es-ES-Wavenet-E").voice == "es-ES-Wavenet-E"
    assert call.speech("pique", row=GOOGLE, model="gemini-2.5-flash-tts", language="fr").voice == "Kore"


def test_json_is_only_parsed_when_it_was_asked_for(monkeypatch):
    monkeypatch.setattr(call, "completion", _recording([], reply('{"a": 1}')))
    assert call.text("hello", row=GEMINI).parsed is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("```json\n{}\n```", "{}"),
        ("```\n{}\n```", "{}"),
        ("  {}  ", "{}"),
        ("", ""),
    ],
)
def test_unfenced(raw, expected):
    assert call.unfenced(raw) == expected


def _raising(error):
    def raise_it(**_kwargs):
        raise error

    return raise_it


def _recording(calls, answer):
    def record(**kwargs):
        calls.append(kwargs)
        return answer

    return record


def test_nothing_asks_for_constrained_decoding_anywhere(monkeypatch):
    """The rule, enforced rather than remembered: `AGENTS.md`, "Constrained decoding is not used".

    `text()` has no `schema` argument, so there is nothing to pass and no call site to police. What
    a `native` row gets is JSON *mode* — "answer with a JSON object" — and nothing about its shape.

    The history is worth keeping, because the mistake was subtle in both directions. A schema was
    first sent *bare* in `response_format`, which LiteLLM silently mapped to nothing at all: the
    shape went unstated and JSON mode went unrequested, and nobody noticed for two deployments
    because the prompts described the shape anyway. Wrapping it correctly then made it work — and
    working is what did the damage: the clip selector's translations grew from 61 characters to
    between 266 and 1039, three calls in four timed out, and the alignment schema was rejected
    outright by the provider above about a hundred tokens.
    """
    import inspect

    assert "schema" not in inspect.signature(call.text).parameters

    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply('{"a": 1}')))

    call.text("hello", row=GEMINI, as_json=True)
    assert calls[-1]["response_format"] == {"type": "json_object"}

    # And a row that cannot take even that is sent nothing; asking is the prompt's job there.
    call.text("hello", row=CLOUDFLARE, as_json=True)
    assert "response_format" not in calls[-1]


def test_no_family_reintroduces_a_schema_by_hand():
    """`response_format` is built in one place, so a family cannot smuggle a schema past the rule
    by passing one through its parameters. Cheap to assert, and the alternative is finding out in
    production the way we did the first time."""
    from acervo.models.families import FAMILIES

    for family in FAMILIES:
        for kind, params in family.params.items():
            assert "response_format" not in params, f"{family.id}/{kind}"


def test_a_row_can_state_its_own_timeout_because_rows_differ_by_twentyfold(monkeypatch):
    """One number cannot serve a chain whose providers answer 20× apart.

    Measured on one deployment, the same clip-selection call: 0.9–1.8 s on the gemini free tier,
    21–37 s on Vertex. A bound sized for the fast row cuts the slow one off before it can rescue
    anything — which is the opposite of what a fallback is for — and one sized for the slow row
    restores the two-minute hang it was meant to remove. So it is a fact about the family, recorded
    beside its other facts rather than branched on in code.
    """
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))
    fast, slow = GEMINI, VERTEX

    assert fast.timeout_for("text", call.SHORT_TIMEOUT_SECONDS) == call.SHORT_TIMEOUT_SECONDS
    assert slow.timeout_for("text", call.SHORT_TIMEOUT_SECONDS) > call.TIMEOUT_SECONDS

    call.text("hello", row=slow, model=slow.models_for("text")[0],
              timeout=call.SHORT_TIMEOUT_SECONDS)
    assert calls[-1]["timeout"] == slow.timeout_for("text", 0)

    # And a row that says nothing still takes what the caller asked for.
    call.text("hello", row=fast, timeout=call.SHORT_TIMEOUT_SECONDS)
    assert calls[-1]["timeout"] == call.SHORT_TIMEOUT_SECONDS


def test_the_timeout_is_ours_and_never_reaches_the_provider(monkeypatch):
    """`params` is spread into the provider call, so a bound kept there would be sent as an
    argument the provider never asked for. Its own field, for that reason."""
    assert "timeout" not in VERTEX.params_for("text")
    assert "timeoutSeconds" not in VERTEX.params_for("text")
    assert VERTEX.family.timeouts["text"] > 0


def test_a_refusal_names_what_actually_refused():
    """The code is shared across callers on purpose; the sentence should not be.

    "The language model is temporarily rate limited" over a drawing that an *image* model refused
    sent a real debugging session at the text chain while the image allowance was the thing that
    had run out. The code stays identical — `scripts/ingest_vocabulary_file.py` retries on exactly
    three of them and must not notice this — and only the prose changes.
    """
    from acervo.models.errors import ProviderUnavailable
    from acervo.services.models import refusal

    busy = ProviderUnavailable("rate_limited", "", provider_id="vertex", model="m")
    text, picture, speech = refusal(busy), refusal(busy, "image"), refusal(busy, "audio")

    assert text.code == picture.code == speech.code == "llm_rate_limited"
    assert "language model" in text.message
    assert "image model" in picture.message and "language model" not in picture.message
    assert "speech model" in speech.message


def test_a_walk_that_found_nobody_names_every_provider_and_why():
    """What twelve stories were waiting for on 24 Sep 2026, said rather than "the provider is busy":
    both of the free tier's models overloaded, and Cloudflare's allowance gone. One phrase a
    provider, in chain order, and the code still the last pair's, so the retry contract holds."""
    from acervo.models.errors import ChainExhausted, ProviderUnavailable
    from acervo.services.models import refusal

    last = ProviderUnavailable("rate_limited", "", provider_id="cloudflare", model="c")
    exhausted = ChainExhausted(
        (("gemini-api", "a"), ("gemini-api", "b"), ("cloudflare", "c")), last,
        ("unreachable", "unavailable", "rate_limited"),
        (("gemini-api", "a", "unreachable"), ("gemini-api", "b", "unavailable"),
         ("cloudflare", "c", "rate_limited")),
        {"gemini-api": "Gemini API", "cloudflare": "Cloudflare"},
    )
    refused = refusal(exhausted)
    assert refused.code == "llm_rate_limited"
    assert refused.waiting_on == "Gemini API is overloaded; Cloudflare is out of allowance for now"
    assert refused.message.startswith("The language model is temporarily rate limited")
    assert refused.message.endswith("Cloudflare is out of allowance for now.")
