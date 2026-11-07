"""Providers for tests: the ones the owner runs today, built without a store or a network.

`provider(...)` builds one from a document, as `providers.parse` does; the named documents are the
three providers the owner re-adds — the Gemini API, Google Cloud and Cloudflare — plus Google Cloud
signed in with a credentials file, which is what reaches Vertex. `GOOGLE_VOICES` stands in for
Google's own voice list, which `listing.voices` reads over the network: a test that needs voices
patches `listing._google_voices` with `google_voices`.
"""

from __future__ import annotations

import copy
from typing import Any

from acervo.models.providers import Provider, Providers, parse

GEMINI_KEY = "test-gemini-key-abcdefghijklmnop"
CLOUDFLARE_TOKEN = "cf-test-token-0123456789abcdef"
CLOUDFLARE_ACCOUNT = "0123456789abcdef0123456789abcdef"
GOOGLE_KEY = "test-google-cloud-key-qrstuvwx"
SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "example-project",
    "client_email": "acervo@project.example.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\ntest-private-key-material\n-----END PRIVATE KEY-----\n",
    "private_key_id": "pkid-9f8e7d6c5b4a3210",
    "token_uri": "https://oauth2.googleapis.com/token",
}

GEMINI: dict[str, Any] = {
    "id": "gemini-api", "family": "gemini-api",
    "models": {"text": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]},
}
CLOUDFLARE: dict[str, Any] = {
    "id": "cloudflare", "family": "cloudflare",
    "settings": {"accountId": CLOUDFLARE_ACCOUNT},
    "models": {
        "text": ["@cf/meta/llama-3.3-70b-instruct-fp8-fast"],
        "image": ["@cf/black-forest-labs/flux-2-klein-4b"],
        "audio": [{"id": "@cf/deepgram/aura-1", "languages": ["en"]}],
    },
}
# Signed in with a credentials file, as the owner runs it: a Gemini voice on Cloud TTS needs one.
GOOGLE: dict[str, Any] = {
    "id": "google-cloud", "family": "google-cloud",
    "settings": {"project": "example-project"},
    "models": {
        "audio": [
            "Wavenet", "Standard",
            {"id": "gemini-3.1-flash-tts-preview", "direction": True},
            {"id": "gemini-2.5-flash-tts", "direction": True},
        ],
        "ocr": ["document-text-detection"],
    },
}
# Google Cloud with a key, which reaches WaveNet, Chirp 3 HD and Vision and nothing on Vertex.
GOOGLE_KEYED: dict[str, Any] = {
    "id": "google-keyed", "family": "google-cloud",
    "models": {"audio": ["Wavenet", "Standard"], "ocr": ["document-text-detection"]},
}
VERTEX: dict[str, Any] = {
    "id": "vertex", "family": "google-cloud",
    "settings": {"project": "example-project"},
    "models": {
        "text": ["gemini-3.8-flash", "gemini-3.5-flash"],
        "image": ["gemini-3.1-flash-lite-image"],
    },
}
# Vertex drawing and nothing else, for a test about pictures that must not also change the text order.
VERTEX_IMAGE: dict[str, Any] = {**VERTEX, "models": {"image": ["gemini-3.1-flash-lite-image"]}}

SECRETS: dict[str, dict[str, Any]] = {
    "gemini-api": {"key": GEMINI_KEY},
    "openai": {"key": "test-openai-key-0123456789abcdef"},
    "cloudflare": {"key": CLOUDFLARE_TOKEN},
    "google-cloud": {"credentials": SERVICE_ACCOUNT},
    "google-keyed": {"key": GOOGLE_KEY},
    "vertex": {"credentials": SERVICE_ACCOUNT},
}


def provider(document: dict[str, Any], secret: dict[str, Any] | None = None, **changes: Any) -> Provider:
    """One provider from a document, with its usual secret unless another is given."""
    found = {**copy.deepcopy(document), **changes}
    if secret is None:
        secret = SECRETS.get(document["id"], {})
    return parse(found, secret)


def providers(*documents: dict[str, Any], keyless: tuple[str, ...] = ()) -> Providers:
    """Several, in the order given — which is the order they were added. `keyless` ids have none."""
    return Providers(tuple(
        provider({**document, "position": position}, {} if document["id"] in keyless else None)
        for position, document in enumerate(documents)
    ))


# Google's `voices.list`, cut down: per-locale voices of two types, and Gemini voices named once.
GOOGLE_VOICES: tuple[dict[str, Any], ...] = (
    {"name": "es-ES-Wavenet-F", "languageCodes": ["es-ES"], "ssmlGender": "FEMALE"},
    {"name": "es-ES-Wavenet-E", "languageCodes": ["es-ES"], "ssmlGender": "MALE"},
    {"name": "es-US-Wavenet-A", "languageCodes": ["es-US"], "ssmlGender": "FEMALE"},
    {"name": "en-GB-Wavenet-A", "languageCodes": ["en-GB"], "ssmlGender": "FEMALE"},
    {"name": "en-US-Wavenet-C", "languageCodes": ["en-US"], "ssmlGender": "FEMALE"},
    {"name": "ru-RU-Wavenet-A", "languageCodes": ["ru-RU"], "ssmlGender": "FEMALE"},
    {"name": "cmn-CN-Wavenet-A", "languageCodes": ["cmn-CN"], "ssmlGender": "FEMALE"},
    {"name": "cmn-TW-Wavenet-A", "languageCodes": ["cmn-TW"], "ssmlGender": "FEMALE"},
    {"name": "es-ES-Standard-F", "languageCodes": ["es-ES"], "ssmlGender": "FEMALE"},
    {"name": "es-ES-Standard-E", "languageCodes": ["es-ES"], "ssmlGender": "MALE"},
    {"name": "en-US-Standard-C", "languageCodes": ["en-US"], "ssmlGender": "FEMALE"},
    {"name": "es-ES-Chirp3-HD-Kore", "languageCodes": ["es-ES"], "ssmlGender": "FEMALE"},
    {"name": "Kore", "languageCodes": ["en-US"], "ssmlGender": "FEMALE"},
    {"name": "Puck", "languageCodes": ["en-US"], "ssmlGender": "MALE"},
    {"name": "Charon", "languageCodes": ["en-US"], "ssmlGender": "MALE"},
)


def google_voices(provider: Provider, *, fresh: bool = False) -> tuple[dict[str, Any], ...]:
    """A stand-in for `listing._google_voices`."""
    return GOOGLE_VOICES
