"""The one hand-written adapter, against a stubbed transport.

What is worth testing here is exactly what was hard about it in the benchmark runner: the multipart
body FLUX.2 Klein insists on, and the fact that Cloudflare answers with either raw bytes or a base64
field inside an envelope depending on the model.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from acervo.models import cloudflare
from provider_rows import CLOUDFLARE, CLOUDFLARE_ACCOUNT, CLOUDFLARE_TOKEN, provider
from acervo.models.errors import ProviderRefused, ProviderUnavailable

ROW = provider(CLOUDFLARE)
MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
ACCOUNT = CLOUDFLARE_ACCOUNT
TOKEN = CLOUDFLARE_TOKEN


def transport(monkeypatch, response: httpx.Response, calls: list | None = None):
    def post(url, **kwargs):
        (calls if calls is not None else []).append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(cloudflare.httpx, "post", post)


def answered(status=200, *, content=b"", headers=None, payload=None) -> httpx.Response:
    if payload is not None:
        return httpx.Response(status, json=payload)
    return httpx.Response(status, content=content, headers=headers or {})


def test_an_image_request_goes_out_as_multipart_even_though_it_is_only_text():
    """The awkward part, and the reason this adapter exists rather than a JSON POST.

    Cloudflare's FLUX.2 partner models answer a JSON body with a 400 naming a required property
    `multipart`. The `(None, value)` tuples are what make httpx emit a boundary without claiming
    the scalars are uploaded files.
    """
    request = httpx.Request(
        "POST", "https://x", files={"prompt": (None, "a hook"), "width": (None, "512")}
    )
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    body = request.read().decode()
    assert 'Content-Disposition: form-data; name="prompt"' in body
    assert "filename" not in body


def test_the_account_id_is_in_the_url_and_the_token_is_only_in_the_header(monkeypatch):
    """Workers AI has no account-less endpoint, which is why the row requires the id as well."""
    calls: list = []
    transport(monkeypatch, answered(headers={"content-type": "image/png"}, content=b"PNG"), calls)
    cloudflare.image(ROW, MODEL, "a hook", seed=7, size=(512, 512))
    assert calls[0]["url"] == f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{MODEL}"
    assert calls[0]["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in calls[0]["url"]
    fields = calls[0]["files"]
    assert fields["prompt"] == (None, "a hook")
    assert fields["seed"] == (None, "7")
    assert fields["width"] == (None, "512")


def test_an_image_answered_as_bytes_is_returned_as_bytes(monkeypatch):
    transport(monkeypatch, answered(headers={"content-type": "image/png"}, content=b"PNGDATA"))
    assert cloudflare.image(ROW, MODEL, "a hook") == (b"PNGDATA", "image/png")


def test_an_image_answered_inside_an_envelope_is_decoded(monkeypatch):
    encoded = base64.b64encode(b"PNGDATA").decode()
    transport(monkeypatch, answered(payload={"success": True, "result": {"image": encoded}}))
    assert cloudflare.image(ROW, MODEL, "a hook") == (b"PNGDATA", "image/png")


def test_a_data_uri_and_a_list_are_both_understood(monkeypatch):
    encoded = base64.b64encode(b"PNGDATA").decode()
    transport(
        monkeypatch,
        answered(payload={"result": {"image": [f"data:image/png;base64,{encoded}"]}}),
    )
    assert cloudflare.image(ROW, MODEL, "a hook")[0] == b"PNGDATA"


def test_a_failed_envelope_is_refused_with_cloudflares_own_error_code(monkeypatch):
    """"AiError 8002" is the actionable part of a Cloudflare failure; keep it."""
    transport(monkeypatch, answered(payload={"success": False, "errors": [{"code": 8002}]}))
    with pytest.raises(ProviderRefused) as caught:
        cloudflare.speech(ROW, "@cf/deepgram/aura-1", "hola")
    assert "8002" in caught.value.detail


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderRefused),
        (403, ProviderRefused),
        (400, ProviderRefused),
        (404, ProviderRefused),
        (429, ProviderUnavailable),
        (500, ProviderUnavailable),
        (503, ProviderUnavailable),
        (418, ProviderRefused),
    ],
)
def test_a_status_is_classified_the_same_way_litellms_exceptions_are(monkeypatch, status, expected):
    """One table for both paths, so a Cloudflare 429 and a Gemini 429 mean the same to the chain."""
    transport(monkeypatch, answered(status, payload={"errors": [{"message": "nope"}]}))
    with pytest.raises(expected):
        cloudflare.image(ROW, MODEL, "a hook")


def test_a_connection_that_never_opened_is_retryable_at_the_next_row(monkeypatch):
    def post(url, **_kwargs):
        raise httpx.ConnectError("no route to cloudflare")

    monkeypatch.setattr(cloudflare.httpx, "post", post)
    with pytest.raises(ProviderUnavailable) as caught:
        cloudflare.image(ROW, MODEL, "a hook")
    assert caught.value.reason == "unreachable"


def test_the_token_is_redacted_out_of_an_error_body(monkeypatch):
    transport(monkeypatch, answered(400, payload={"errors": [{"message": f"bad token {TOKEN}"}]}))
    with pytest.raises(ProviderRefused) as caught:
        cloudflare.image(ROW, MODEL, "a hook")
    assert TOKEN not in caught.value.detail
    assert "«redacted»" in caught.value.detail


def test_speech_sends_json_rather_than_multipart(monkeypatch):
    """Only the image models insist on multipart; sending it everywhere would be cargo cult."""
    calls: list = []
    transport(monkeypatch, answered(headers={"content-type": "audio/mpeg"}, content=b"MP3"), calls)
    assert cloudflare.speech(ROW, "@cf/deepgram/aura-1", "hola") == (b"MP3", "audio/mpeg")
    assert calls[0]["files"] is None
    # Deepgram's Aura takes `text`; melotts took `prompt` and refused `text`. The row says which,
    # because it is a fact about the model rather than about Cloudflare.
    assert calls[0]["json"] == {"text": "hola"}


def test_a_provider_whose_account_is_missing_is_refused_rather_than_called(monkeypatch):
    monkeypatch.setattr(
        cloudflare.httpx, "post", lambda *a, **k: pytest.fail("a call was made without an account")
    )
    with pytest.raises(ProviderRefused) as caught:
        cloudflare.image(provider(CLOUDFLARE, settings={}), MODEL, "a hook")
    assert caught.value.reason == "unconfigured"
    assert caught.value.detail == "Cloudflare needs its account ID"
