"""Gemini API speech, against a stubbed transport.

What is worth pinning: the language always travels at the head of the direction, because the
request has no field for it and a single word is otherwise read in whatever language the model
guesses; the voice list's two kinds of voice; and that a failure keeps Google's own sentence.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from acervo.models import call, gemini_tts, listing
from acervo.models.errors import ProviderRefused, ProviderUnavailable
from provider_rows import GEMINI, provider

MODEL = "gemini-3.8-flash-lite-tts"
ROW = provider({**GEMINI, "models": {**GEMINI["models"], "audio": [{"id": MODEL, "direction": True}]}})

# The voice list, cut down: two voices named once, and voices made for a locale.
VOICES = [
    {"id": "kore", "type": "prebuilt", "display_name": "Kore", "language_code": "en-US",
     "accent": "General American", "gender": "female"},
    {"id": "puck", "type": "prebuilt", "display_name": "Puck", "language_code": "en-US",
     "accent": "General American", "gender": "male"},
    {"id": "es-419-advisor-1", "type": "prebuilt", "language_code": "es-419",
     "accent": "Argentina Spanish", "gender": "female"},
    {"id": "es-419-advisor-4", "type": "prebuilt", "language_code": "es-419",
     "accent": "Mexico Spanish", "gender": "female"},
    {"id": "es-es-advisor-2", "type": "prebuilt", "language_code": "es-ES",
     "accent": "Castilian Spanish", "gender": "male"},
    {"id": "en-gb-narrator-3", "type": "prebuilt", "language_code": "en-GB",
     "accent": "Glasgow English", "gender": "male"},
]


@pytest.fixture(autouse=True)
def voice_list(monkeypatch):
    listing.forget()
    pages = {None: {"voices": VOICES[:3], "next_page_token": "second"}, "second": {"voices": VOICES[3:]}}

    def get(url, **kwargs):
        assert url == listing.GEMINI_VOICES_URL
        return httpx.Response(200, json=pages[(kwargs.get("params") or {}).get("page_token")])

    monkeypatch.setattr(listing.httpx, "get", get)
    yield
    listing.forget()


def transport(monkeypatch, response: httpx.Response, calls: list):
    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(gemini_tts.httpx, "post", post)


def answered(content: bytes = b"RIFF....WAVEfmt ") -> httpx.Response:
    return httpx.Response(200, json={"steps": [{"type": "model_output", "content": [
        {"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(content).decode()},
    ]}]})


def test_the_language_heads_every_direction_and_the_voice_is_named_in_the_speech_config(monkeypatch):
    calls = []
    transport(monkeypatch, answered(), calls)
    data, mime = gemini_tts.speech(ROW, MODEL, "picar", language="es", voice="kore")
    body = calls[-1]["json"]
    assert (data, mime) == (b"RIFF....WAVEfmt ", "audio/wav")
    assert calls[-1]["headers"] == {"x-goog-api-key": ROW.credential.key}
    assert body["model"] == MODEL
    assert body["generation_config"] == {"speech_config": [{"voice": "kore"}]}
    assert body["input"] == [{"type": "user_input", "content": [{
        "type": "text", "text": "picar",
        "annotations": [{"type": "speech_metadata", "style": "Say this in Spanish."}],
    }]}]
    gemini_tts.speech(ROW, MODEL, "picar", language="es-AR", voice="kore", style="Warm and amused.")
    annotation = calls[-1]["json"]["input"][0]["content"][0]["annotations"][0]
    assert annotation["style"] == "Say this in Spanish. Warm and amused."


def test_an_answer_with_no_audio_is_empty_and_passes_to_the_next_pair(monkeypatch):
    transport(monkeypatch, httpx.Response(200, json={"steps": [{"type": "model_output", "content": []}]}), [])
    with pytest.raises(ProviderUnavailable) as raised:
        gemini_tts.speech(ROW, MODEL, "picar", language="es", voice="kore")
    assert raised.value.reason == "empty"


def test_the_free_tier_s_limit_keeps_google_s_sentence_and_a_bad_key_is_refused(monkeypatch):
    said = ("Rate limit exceeded for model gemini-3.8-flash-lite-tts (limit: 3 requests per minute "
            "on Free Tier). Please retry in 59s or upgrade your tier at https://ai.dev/rate-limit.")
    transport(monkeypatch, httpx.Response(429, json={"error": {"message": said, "code": "too_many_requests"}}), [])
    with pytest.raises(ProviderUnavailable) as raised:
        gemini_tts.speech(ROW, MODEL, "picar", language="es", voice="kore")
    assert raised.value.reason == "rate_limited" and "retry in 59s" in str(raised.value)
    # Google refuses a key with a 400 and a list holding one error.
    transport(monkeypatch, httpx.Response(400, json=[{"error": {
        "code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT",
    }}]), [])
    with pytest.raises(ProviderRefused) as refused:
        gemini_tts.speech(ROW, MODEL, "picar", language="es", voice="kore")
    assert str(refused.value).endswith("API key not valid. Please pass a valid API key.")


def test_voices_named_once_speak_any_language_and_the_rest_keep_their_locale_and_accent():
    voices = {voice.name: voice for voice in listing.voices(ROW, MODEL)}
    assert len(voices) == len(VOICES)  # both pages
    assert voices["kore"].locale is None and voices["kore"].gender == "female"
    assert voices["es-es-advisor-2"].locale == "es-ES"
    assert voices["en-gb-narrator-3"].note == "Glasgow English"
    # Latin American Spanish is one locale on the wire; the accent names the country.
    assert voices["es-419-advisor-1"].locale == "es-AR"
    assert voices["es-419-advisor-4"].locale == "es-MX"


def test_an_accent_is_served_by_voices_made_for_it_first_and_a_bare_language_by_any(monkeypatch):
    calls = []
    transport(monkeypatch, answered(), calls)
    assert ROW.voices_for(MODEL, "es-AR")[0] == "es-419-advisor-1"
    assert ROW.voices_for(MODEL, "es-ES")[0] == "es-es-advisor-2"
    assert set(ROW.voices_for(MODEL, "sv-SE")) == {"kore", "puck"}
    spoken = call.speech("picar", row=ROW, language="es-AR")
    assert spoken.voice == "es-419-advisor-1"
    assert calls[-1]["json"]["generation_config"]["speech_config"] == [{"voice": "es-419-advisor-1"}]


def test_the_model_list_says_which_models_speak_and_keeps_them_out_of_text(monkeypatch):
    monkeypatch.setattr(listing.httpx, "get", lambda url, **kwargs: httpx.Response(200, json={"models": [
        {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-flash-lite-tts", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-lite-image", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-2.5-flash-native-audio-latest", "supportedGenerationMethods": ["bidiGenerateContent"]},
    ]}))
    assert listing.models(ROW, "text") == ("gemini-3.5-flash-lite",)
    assert listing.models(ROW, "audio") == ("gemini-3.8-flash-lite-tts",)
    assert listing.lists(ROW, "audio") and listing.lists_voices(ROW)
