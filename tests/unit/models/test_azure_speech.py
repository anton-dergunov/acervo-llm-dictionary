"""Azure Speech, against a stubbed transport and the shapes in Microsoft's REST reference.

No real call has answered through this family yet (`families.find("azure-speech").tried` is false),
so these pin what the reference says: SSML naming the voice and its locale, the words escaped rather
than read as markup, the region in both addresses, and a failure said by its status when Azure sends
no body.
"""

from __future__ import annotations

import httpx
import pytest

from acervo.models import azure_speech, call, families, listing
from acervo.models.errors import ProviderRefused, ProviderUnavailable
from provider_rows import provider

KEY = "0123456789abcdef0123456789abcdef"
ROW = provider({"id": "azure", "family": "azure-speech", "settings": {"region": "westeurope"},
                "models": {"audio": ["neural"]}}, {"key": KEY})
VOICES = [
    {"Name": "Microsoft Server Speech Text to Speech Voice (es-ES, ElviraNeural)", "DisplayName": "Elvira",
     "ShortName": "es-ES-ElviraNeural", "Gender": "Female", "Locale": "es-ES", "VoiceType": "Neural"},
    {"Name": "Microsoft Server Speech Text to Speech Voice (es-AR, TomasNeural)", "DisplayName": "Tomas",
     "ShortName": "es-AR-TomasNeural", "Gender": "Male", "Locale": "es-AR", "VoiceType": "Neural"},
    {"Name": "Microsoft Server Speech Text to Speech Voice (en-GB, SoniaNeural)", "DisplayName": "Sonia",
     "ShortName": "en-GB-SoniaNeural", "Gender": "Female", "Locale": "en-GB", "VoiceType": "Neural"},
]


@pytest.fixture(autouse=True)
def voice_list(monkeypatch):
    listing.forget()

    def get(url, **kwargs):
        assert url == "https://westeurope.tts.speech.microsoft.com/cognitiveservices/voices/list"
        assert kwargs["headers"]["Ocp-Apim-Subscription-Key"] == KEY
        return httpx.Response(200, json=VOICES)

    monkeypatch.setattr(listing.httpx, "get", get)
    yield
    listing.forget()


def transport(monkeypatch, response: httpx.Response, calls: list):
    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(azure_speech.httpx, "post", post)


def test_it_is_offered_as_not_yet_tried():
    assert families.find("azure-speech").tried is False


def test_the_voice_and_its_locale_are_named_in_the_ssml_and_the_words_are_escaped(monkeypatch):
    calls = []
    transport(monkeypatch, httpx.Response(200, content=b"RIFF....WAVEfmt "), calls)
    spoken = call.speech("<b>picar</b> & 'más'", row=ROW, language="es-AR", style="Warm")
    sent = calls[-1]
    assert sent["url"] == "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1"
    assert sent["headers"]["X-Microsoft-OutputFormat"] == "riff-24khz-16bit-mono-pcm"
    assert sent["headers"]["Content-Type"] == "application/ssml+xml"
    assert sent["content"].decode() == (
        "<speak version='1.0' xml:lang=\"es-AR\"><voice xml:lang=\"es-AR\" name=\"es-AR-TomasNeural\">"
        "&lt;b&gt;picar&lt;/b&gt; &amp; 'más'</voice></speak>"
    )
    assert spoken.voice == "es-AR-TomasNeural"
    assert spoken.answer.warnings == ("style is not supported by this provider",)


def test_voices_keep_their_locale_and_are_shown_by_their_display_name():
    voices = {one.name: one for one in listing.voices(ROW, "neural")}
    assert (voices["es-ES-ElviraNeural"].label, voices["es-ES-ElviraNeural"].locale,
            voices["es-ES-ElviraNeural"].gender) == ("Elvira", "es-ES", "female")
    assert ROW.voices_for("neural", "es-ES")[0] == "es-ES-ElviraNeural"
    assert not ROW.speaks("neural", "de-DE")
    assert listing.models(ROW, "audio") == ("neural",)
    assert listing.check(ROW).said == "Works · 3 voices"


def test_a_failure_with_no_body_is_said_by_its_status(monkeypatch):
    transport(monkeypatch, httpx.Response(401), [])
    with pytest.raises(ProviderRefused) as refused:
        azure_speech.speech(ROW, "neural", "picar", language="es-ES")
    assert refused.value.reason == "authentication" and "another region" in str(refused.value)
    transport(monkeypatch, httpx.Response(429), [])
    with pytest.raises(ProviderUnavailable) as spent:
        azure_speech.speech(ROW, "neural", "picar", language="es-ES")
    assert spent.value.reason == "rate_limited"


def test_it_needs_its_region():
    unplaced = provider({"id": "azure", "family": "azure-speech", "models": {"audio": ["neural"]}}, {"key": KEY})
    assert unplaced.reason() == "Azure Speech needs its region"
