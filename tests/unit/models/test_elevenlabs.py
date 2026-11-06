"""ElevenLabs speech, against a stubbed transport.

What is worth pinning: a direction travels as one leading tag and only to a model that takes one; the
voice is sent by id and shown by name; and a month's credits spent passes to the next voice, where
the bare status would have stopped the order.
"""

from __future__ import annotations

import httpx
import pytest

from acervo.models import call, elevenlabs, listing
from acervo.models.errors import ProviderRefused, ProviderUnavailable
from provider_rows import provider

KEY = "sk_" + "a1b2c3d4" * 6
ROW = provider({"id": "elevenlabs", "family": "elevenlabs", "models": {"audio": [
    {"id": "eleven_v4", "direction": True}, "eleven_multilingual_v2",
]}}, {"key": KEY})

VOICES = {"voices": [
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah - Mature, Reassuring, Confident",
     "category": "premade", "labels": {"gender": "female", "accent": "american"}},
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George - Warm, Captivating Storyteller",
     "category": "premade", "labels": {"gender": "male", "accent": "british"}},
], "has_more": False, "next_page_token": None}


@pytest.fixture(autouse=True)
def voice_list(monkeypatch):
    listing.forget()
    monkeypatch.setattr(listing.httpx, "get", lambda url, **kwargs: httpx.Response(200, json=VOICES))
    yield
    listing.forget()


def transport(monkeypatch, response: httpx.Response, calls: list):
    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(elevenlabs.httpx, "post", post)


def wav() -> httpx.Response:
    return httpx.Response(200, content=b"RIFF....WAVEfmt ", headers={"content-type": "audio/wav"})


def test_a_direction_is_one_leading_tag_and_the_language_goes_bare(monkeypatch):
    calls = []
    transport(monkeypatch, wav(), calls)
    spoken = call.speech("No me digas.", row=ROW, model="eleven_v4", language="es-AR",
                         style="Surprised [and] amused")
    sent = calls[-1]
    assert sent["url"] == "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"
    assert sent["params"] == {"output_format": "wav_24000"}
    assert sent["headers"] == {"xi-api-key": KEY}
    # A bracket inside the direction would close the tag early and the rest would be read aloud.
    assert sent["json"] == {"text": "[Surprised (and) amused] No me digas.", "model_id": "eleven_v4",
                            "language_code": "es"}
    assert (spoken.data, spoken.mime, spoken.voice) == (b"RIFF....WAVEfmt ", "audio/wav", "EXAVITQu4vr4xnSDxMaL")


def test_a_model_that_takes_no_direction_is_never_sent_a_tag(monkeypatch):
    calls = []
    transport(monkeypatch, wav(), calls)
    spoken = call.speech("picar", row=ROW, model="eleven_multilingual_v2", language="es", style="Warm")
    assert calls[-1]["json"]["text"] == "picar"
    assert spoken.answer.warnings == ("style is not supported by this provider",)


def test_a_month_s_credits_spent_passes_to_the_next_voice_and_a_bad_key_does_not(monkeypatch):
    transport(monkeypatch, httpx.Response(402, json={"detail": {
        "type": "payment_required", "code": "insufficient_credits",
        "message": "This request exceeds your quota of 10000.",
    }}), [])
    with pytest.raises(ProviderUnavailable) as spent:
        elevenlabs.speech(ROW, "eleven_v4", "picar", language="es")
    assert spent.value.reason == "rate_limited" and "exceeds your quota" in str(spent.value)
    transport(monkeypatch, httpx.Response(401, json={"detail": {
        "type": "authentication_error", "code": "invalid_api_key", "message": "API key is invalid",
    }}), [])
    with pytest.raises(ProviderRefused) as refused:
        elevenlabs.speech(ROW, "eleven_v4", "picar", language="es")
    assert refused.value.reason == "authentication" and str(refused.value).endswith("API key is invalid")
    # A format the plan does not allow is a mistake to fix, not an allowance spent.
    transport(monkeypatch, httpx.Response(403, json={"detail": {
        "code": "subscription_required", "message": "Output format 'pcm_44100' is only available on the Pro tier and above.",
    }}), [])
    with pytest.raises(ProviderRefused):
        elevenlabs.speech(ROW, "eleven_v4", "picar", language="es")


def test_voices_are_sent_by_id_and_shown_by_name_and_speak_any_language():
    voices = listing.voices(ROW, "eleven_v4")
    assert [(one.name, one.label, one.note, one.gender, one.locale) for one in voices] == [
        ("EXAVITQu4vr4xnSDxMaL", "Sarah", "Mature, Reassuring, Confident", "female", None),
        ("JBFqnCBsd6RMkjVDRZzb", "George", "Warm, Captivating Storyteller", "male", None),
    ]
    assert ROW.voices_for("eleven_v4", "sv-SE") == ("EXAVITQu4vr4xnSDxMaL", "JBFqnCBsd6RMkjVDRZzb")


def test_the_key_check_says_the_plan_and_the_month_s_spend(monkeypatch):
    monkeypatch.setattr(listing.httpx, "get", lambda url, **kwargs: httpx.Response(200, json={
        "subscription": {"tier": "free", "character_count": 1234, "character_limit": 10000},
    }))
    checked = listing.check(ROW)
    assert checked.ok and checked.said == "Works · free plan · 1,234 of 10,000 credits used this month"


def test_only_models_that_speak_are_offered(monkeypatch):
    monkeypatch.setattr(listing.httpx, "get", lambda url, **kwargs: httpx.Response(200, json=[
        {"model_id": "eleven_v4", "can_do_text_to_speech": True},
        {"model_id": "eleven_english_sts_v2", "can_do_text_to_speech": False},
    ]))
    assert listing.models(ROW, "audio") == ("eleven_v4",)
