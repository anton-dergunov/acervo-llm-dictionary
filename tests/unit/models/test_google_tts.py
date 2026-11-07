"""The Cloud Text-to-Speech adapter, against a stubbed transport and stubbed credentials.

What is worth pinning is what differs between the two voice families on the one route — a Gemini
voice is named by `modelName` and takes `input.prompt`, a WaveNet voice takes neither — and that the
project travels as a quota header, without which Google refuses a user login outright.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from acervo.models import google_auth, google_tts
from provider_rows import GOOGLE, GOOGLE_KEYED, VERTEX, google_voices, provider
from acervo.models.errors import ProviderRefused, ProviderUnavailable

ROW = provider(GOOGLE)


class _Credentials:
    valid = True
    token = "an-access-token-value"

    def refresh(self, request):  # pragma: no cover — valid already
        raise AssertionError("refresh was not needed")


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    from acervo.models import listing

    google_auth.forget_credentials()
    monkeypatch.setattr(listing, "_google_voices", google_voices)
    monkeypatch.setattr(google_auth, "_load", lambda info, project: _Credentials())
    yield
    google_auth.forget_credentials()


def transport(monkeypatch, response: httpx.Response, calls: list):
    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(google_auth.httpx, "post", post)


def audio(content: bytes = b"ID3-an-mp3") -> httpx.Response:
    return httpx.Response(200, json={"audioContent": base64.b64encode(content).decode()})


def test_a_wavenet_voice_is_named_by_locale_and_takes_no_model_name_and_no_prompt(monkeypatch):
    calls = []
    transport(monkeypatch, audio(), calls)
    data, mime = google_tts.speech(ROW, "Wavenet", "picar", language="es")
    body = calls[-1]["json"]
    assert (data, mime) == (b"ID3-an-mp3", "audio/wav")
    assert body["voice"] == {"languageCode": "es-ES", "name": "es-ES-Wavenet-F"}
    assert body["input"] == {"text": "picar"}
    # The master, because the compression is Acervo's: `pronunciation/encode.py`, measured in
    # `experiments/pronunciation-encoding/`. Google's own MP3 is 32 kbps for a Gemini voice.
    assert body["audioConfig"] == {"audioEncoding": "LINEAR16"}


def test_an_accent_travels_as_the_locale_each_voice_family_takes(monkeypatch):
    """A voice made for a locale goes with it; a Gemini voice is sent the nearest locale Google
    lists a voice under — US Spanish for Argentina, which shares Latin American Spanish with it —
    and is told the rest in its prompt. Measured: Gemini voices refuse `es-AR` and a bare `es`."""
    calls = []
    transport(monkeypatch, audio(), calls)
    google_tts.speech(ROW, "Wavenet", "picar", language="es-AR")
    assert calls[-1]["json"]["voice"] == {"languageCode": "es-US", "name": "es-US-Wavenet-A"}
    google_tts.speech(ROW, "Wavenet", "picar", language="es-AR", voice="es-ES-Wavenet-F")
    assert calls[-1]["json"]["voice"]["languageCode"] == "es-ES"
    google_tts.speech(ROW, "gemini-2.5-flash-tts", "picar", language="es-AR", voice="Kore")
    assert calls[-1]["json"]["voice"]["languageCode"] == "es-US"
    google_tts.speech(ROW, "gemini-2.5-flash-tts", "picar", language="es", voice="Kore")
    assert calls[-1]["json"]["voice"]["languageCode"] == "es-ES"
    google_tts.speech(ROW, "Wavenet", "lorry", language="en-GB")
    assert calls[-1]["json"]["voice"] == {"languageCode": "en-GB", "name": "en-GB-Wavenet-A"}


def test_the_locales_typed_on_a_model_are_the_ones_it_is_sent(monkeypatch):
    """Where the owner says which locales a voice takes, those win over Google's list."""
    calls = []
    transport(monkeypatch, audio(), calls)
    typed = provider(GOOGLE, models={"audio": [
        {"id": "gemini-2.5-flash-tts", "direction": True, "languages": ["es-419", "es-ES", "en-US"]}]})
    google_tts.speech(typed, "gemini-2.5-flash-tts", "picar", language="es-AR", voice="Kore")
    assert calls[-1]["json"]["voice"]["languageCode"] == "es-419"


def test_every_model_asks_for_the_uncompressed_master(monkeypatch):
    """`LINEAR16` for every Google voice: the compression is Acervo's business
    (`experiments/pronunciation-encoding/`)."""
    calls = []
    transport(monkeypatch, audio(), calls)
    for model in ("Wavenet", "Standard", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-tts"):
        google_tts.speech(ROW, model, "picar", language="es")
        assert calls[-1]["json"]["audioConfig"]["audioEncoding"] == "LINEAR16"


def test_a_gemini_voice_carries_its_model_name_and_the_direction_in_a_field_of_its_own(monkeypatch):
    calls = []
    transport(monkeypatch, audio(), calls)
    google_tts.speech(ROW, "gemini-3.1-flash-tts-preview", "¡Me pica!", language="zh-Hans",
                      voice="Puck", style="exasperated")
    body = calls[-1]["json"]
    assert body["voice"] == {
        "languageCode": "cmn-CN", "name": "Puck", "modelName": "gemini-3.1-flash-tts-preview"
    }
    assert body["input"] == {"text": "¡Me pica!", "prompt": "exasperated"}


def test_a_key_travels_as_a_header_and_never_in_the_address(monkeypatch):
    calls = []
    transport(monkeypatch, audio(), calls)
    keyed = provider(GOOGLE_KEYED)
    google_tts.speech(keyed, "Standard", "picar", language="es")
    headers = calls[-1]["headers"]
    assert headers["x-goog-api-key"] == keyed.credential.key
    assert "Authorization" not in headers
    assert keyed.credential.key not in calls[-1]["url"]


def test_with_a_credentials_file_the_project_travels_as_a_quota_header_beside_the_token(monkeypatch):
    calls = []
    transport(monkeypatch, audio(), calls)
    signed_in = provider(VERTEX, models={"audio": ["Standard"]})
    google_tts.speech(signed_in, "Standard", "picar", language="es")
    headers = calls[-1]["headers"]
    assert headers["Authorization"] == "Bearer an-access-token-value"
    assert headers["x-goog-user-project"] == "example-project"
    assert "x-goog-api-key" not in headers


@pytest.mark.parametrize(
    ("status", "failure", "reason"),
    [
        (429, ProviderUnavailable, "rate_limited"),
        (503, ProviderUnavailable, "unavailable"),
        (403, ProviderRefused, "authentication"),
        (400, ProviderRefused, "configuration"),
    ],
)
def test_failures_are_classified_like_every_other_providers(monkeypatch, status, failure, reason):
    calls = []
    transport(monkeypatch, httpx.Response(status, json={"error": {"message": "the API is not enabled"}}), calls)
    with pytest.raises(failure) as caught:
        google_tts.speech(ROW, "Wavenet", "picar", language="es")
    assert caught.value.reason == reason
    assert "the API is not enabled" in str(caught.value)


def test_an_answer_with_no_audio_is_empty_rather_than_a_crash(monkeypatch):
    transport(monkeypatch, httpx.Response(200, json={}), [])
    with pytest.raises(ProviderUnavailable) as caught:
        google_tts.speech(ROW, "Wavenet", "picar", language="es")
    assert caught.value.reason == "empty"


def test_a_language_with_no_declared_voice_is_a_configuration_mistake(monkeypatch):
    transport(monkeypatch, audio(), [])
    with pytest.raises(ProviderRefused) as caught:
        google_tts.speech(ROW, "Wavenet", "pique", language="fr")
    assert caught.value.reason == "configuration"


def test_a_credentials_file_google_cannot_read_is_a_mistake_to_fix(monkeypatch):
    import google.auth
    import google.auth.exceptions

    def unreadable(info, project):
        raise google.auth.exceptions.DefaultCredentialsError("the file is not valid")

    google_auth.forget_credentials()
    monkeypatch.setattr(google_auth, "_load", unreadable)
    signed_in = provider(VERTEX, models={"audio": ["Wavenet"]})
    with pytest.raises(ProviderRefused) as caught:
        google_tts.speech(signed_in, "Wavenet", "picar", language="es", voice="es-ES-Wavenet-F")
    assert caught.value.reason == "configuration"


def test_no_credential_at_all_says_so_rather_than_failing_somewhere_else(monkeypatch):
    transport(monkeypatch, audio(), [])
    keyless = provider(GOOGLE_KEYED, {})
    with pytest.raises(ProviderRefused) as caught:
        google_tts.speech(keyless, "Wavenet", "picar", language="es", voice="es-ES-Wavenet-F")
    assert caught.value.reason == "unconfigured"
