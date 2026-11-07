"""Pictures through A1111's route — Draw Things, Forge, A1111 — against a stubbed transport.

What is worth pinning: the two dialects of choosing a model (Draw Things refuses the key A1111
reads), a distilled model sent the few steps it was made for, the owner's `extra` winning over both,
and a server's own sentence when it cannot use what it was sent.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from acervo.models import a1111, call, listing
from acervo.models.errors import ProviderRefused, ProviderUnavailable
from provider_rows import provider

PNG = b"\x89PNG\r\n\x1a\n-a-picture"
TURBO = "sd_xl_turbo_q6p_q8p.ckpt"
DRAW_THINGS = provider({"id": "draw-things", "family": "draw-things", "models": {"image": [TURBO]}}, {})
FORGE = provider({"id": "forge", "family": "a1111", "settings": {"baseUrl": "http://gpu.example.com:7860"},
                  "models": {"image": ["juggernautXL_v9.safetensors [c9e3e68f89]"]}}, {})


def transport(monkeypatch, response: httpx.Response, calls: list):
    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(a1111.httpx, "post", post)


def drawn() -> httpx.Response:
    return httpx.Response(200, json={"images": [base64.b64encode(PNG).decode()]})


def test_draw_things_is_told_the_model_by_name_and_a_distilled_one_its_few_steps(monkeypatch):
    calls = []
    transport(monkeypatch, drawn(), calls)
    result = call.image("a fox", row=DRAW_THINGS, size=(512, 768), seed=7)
    assert calls[-1]["url"] == "http://localhost:7860/sdapi/v1/txt2img"
    assert calls[-1]["json"] == {"prompt": "a fox", "width": 512, "height": 768, "batch_size": 1, "seed": 7,
                                 "steps": 4, "cfg_scale": 1.0, "model": TURBO}
    assert calls[-1]["timeout"] == 300
    assert (result.data, result.mime, result.answer.warnings) == (PNG, "image/png", ())


def test_forge_is_told_the_model_in_its_settings_and_a_full_model_keeps_the_server_s_steps(monkeypatch):
    calls = []
    transport(monkeypatch, drawn(), calls)
    call.image("a fox", row=FORGE, size=(1024, 1024))
    sent = calls[-1]["json"]
    assert calls[-1]["url"] == "http://gpu.example.com:7860/sdapi/v1/txt2img"
    assert sent["override_settings"] == {"sd_model_checkpoint": "juggernautXL_v9.safetensors [c9e3e68f89]"}
    assert "model" not in sent and "steps" not in sent and "cfg_scale" not in sent


def test_the_owner_s_extra_wins_over_the_few_steps(monkeypatch):
    calls = []
    transport(monkeypatch, drawn(), calls)
    row = provider({"id": "draw-things", "family": "draw-things", "models": {"image": [TURBO]},
                    "extra": {"steps": 2, "sampler_name": "Euler A Trailing"}}, {})
    call.image("a fox", row=row)
    assert calls[-1]["json"]["steps"] == 2 and calls[-1]["json"]["sampler_name"] == "Euler A Trailing"
    assert (calls[-1]["json"]["width"], calls[-1]["json"]["height"]) == (512, 512)


def test_a_model_the_server_does_not_have_is_said_in_its_words_and_a_server_that_is_off_passes(monkeypatch):
    transport(monkeypatch, httpx.Response(422, json={
        "errors": "", "error": "HTTPException", "body": "",
        "detail": "Unrecognized model name \"missing.ckpt\" (see --help for a list of available models)",
    }), [])
    with pytest.raises(ProviderRefused) as refused:
        a1111.image(DRAW_THINGS, "missing.ckpt", "a fox")
    assert refused.value.reason == "configuration"
    assert str(refused.value).endswith('Unrecognized model name "missing.ckpt" (see --help for a list of available models)')

    def off(url, **kwargs):
        raise httpx.ConnectError("[Errno 61] Connection refused")

    monkeypatch.setattr(a1111.httpx, "post", off)
    with pytest.raises(ProviderUnavailable) as down:
        a1111.image(DRAW_THINGS, TURBO, "a fox")
    assert down.value.reason == "unreachable"


def test_draw_things_offers_the_model_it_has_loaded_and_forge_its_list(monkeypatch):
    def get(url, **kwargs):
        if url.endswith("/sdapi/v1/options"):
            return httpx.Response(200, json={"model": TURBO, "steps": 16})
        assert url == "http://gpu.example.com:7860/sdapi/v1/sd-models"
        return httpx.Response(200, json=[{"title": "juggernautXL_v9.safetensors [c9e3e68f89]",
                                          "model_name": "juggernautXL_v9"}])

    monkeypatch.setattr(listing.httpx, "get", get)
    assert listing.models(DRAW_THINGS, "image") == (TURBO,)
    assert listing.check(DRAW_THINGS).said == f"Works · {TURBO} is loaded"
    assert listing.models(FORGE, "image") == ("juggernautXL_v9.safetensors [c9e3e68f89]",)
    assert listing.check(FORGE).said == "Works · 1 model"
