"""A speech server on OpenAI's route — Kokoro, Piper behind Speaches — against a stubbed transport.

What is worth pinning: the request is OpenAI's own, asking for an uncompressed master; a direction
goes in `instructions` and only to a model said to take one; and a voice's name says its language
where it follows Kokoro's or Piper's convention, so a language no voice speaks is not offered.
"""

from __future__ import annotations

import httpx
import pytest

from acervo.models import call, listing, openai_speech
from acervo.models.errors import ProviderRefused, ProviderUnavailable
from provider_rows import provider

ROW = provider({"id": "kokoro", "family": "speech-server", "models": {"audio": [
    "kokoro", {"id": "gpt-4o-mini-tts", "direction": True},
]}}, {})
VOICES = {"voices": [
    {"id": "ef_dora", "name": "ef_dora"}, {"id": "em_alex", "name": "em_alex"},
    {"id": "bf_alice", "name": "bf_alice"}, {"id": "af_heart", "name": "af_heart"},
    {"id": "en_GB-alan-medium"}, "speaches-ai/piper-de_DE-thorsten-high", "narrator",
]}


@pytest.fixture(autouse=True)
def voice_list(monkeypatch):
    listing.forget()

    def get(url, **kwargs):
        assert url == "http://localhost:8880/v1/audio/voices"
        return httpx.Response(200, json=VOICES)

    monkeypatch.setattr(listing.httpx, "get", get)
    yield
    listing.forget()


def transport(monkeypatch, response: httpx.Response, calls: list):
    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(openai_speech.httpx, "post", post)


def wav() -> httpx.Response:
    return httpx.Response(200, content=b"RIFF\xff\xff\xff\xffWAVEfmt ", headers={"content-type": "audio/wav"})


def test_the_request_is_openai_s_own_and_asks_for_the_master(monkeypatch):
    calls = []
    transport(monkeypatch, wav(), calls)
    spoken = call.speech("picar", row=ROW, model="kokoro", language="es-ES", style="Warm")
    assert calls[-1]["url"] == "http://localhost:8880/v1/audio/speech"
    assert calls[-1]["json"] == {"model": "kokoro", "input": "picar", "voice": "ef_dora", "response_format": "wav"}
    assert calls[-1]["headers"] == {}
    assert spoken.voice == "ef_dora" and spoken.answer.warnings == ("style is not supported by this provider",)
    call.speech("lorry", row=ROW, model="gpt-4o-mini-tts", language="en-GB", style="Warm")
    assert calls[-1]["json"]["instructions"] == "Warm"
    assert calls[-1]["json"]["voice"] in ("bf_alice", "en_GB-alan-medium")


def test_a_voice_s_name_says_its_language_and_gender_where_the_server_s_convention_does():
    voices = {one.name: one for one in listing.voices(ROW, "kokoro")}
    assert (voices["ef_dora"].locale, voices["ef_dora"].gender) == ("es", "female")
    assert (voices["em_alex"].locale, voices["em_alex"].gender) == ("es", "male")
    assert voices["af_heart"].locale == "en-US"
    assert voices["en_GB-alan-medium"].locale == "en-GB"
    assert voices["speaches-ai/piper-de_DE-thorsten-high"].locale == "de-DE"
    assert voices["narrator"].locale is None


def test_a_server_that_is_not_running_passes_to_the_next_voice_and_a_wrong_voice_does_not(monkeypatch):
    def refused(url, **kwargs):
        raise httpx.ConnectError("[Errno 61] Connection refused")

    monkeypatch.setattr(openai_speech.httpx, "post", refused)
    with pytest.raises(ProviderUnavailable) as down:
        openai_speech.speech(ROW, "kokoro", "picar", language="es", voice="ef_dora")
    assert down.value.reason == "unreachable"
    transport(monkeypatch, httpx.Response(400, json={"detail": {
        "error": "validation_error", "message": "Voice 'nope' not found.",
    }}), [])
    with pytest.raises(ProviderRefused) as wrong:
        openai_speech.speech(ROW, "kokoro", "picar", language="es", voice="nope")
    assert str(wrong.value).endswith("Voice 'nope' not found.")


def test_the_check_counts_the_voices_and_the_models_are_the_server_s(monkeypatch):
    assert listing.check(ROW).said == f"Works · {len(VOICES['voices'])} voices"
    monkeypatch.setattr(listing.httpx, "get", lambda url, **kwargs: httpx.Response(200, json={
        "data": [{"id": "kokoro"}, {"id": "tts-1"}]}))
    assert listing.models(ROW, "audio") == ("kokoro", "tts-1")
