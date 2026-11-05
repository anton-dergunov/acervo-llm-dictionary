"""Asking a provider what it has, and whether its key works — calls that spend nothing.

A key is checked by making one such call: a model list, or a voice list where the model list does not
prove the key (OpenRouter lists its models to anyone; Google Cloud's voices are what a key reaches).
The answer is said plainly — "Works · 52 models", or "Works as" the account a credentials file
names — or, when the provider refuses, in the provider's own words, redacted. A refused key is a
mistake to fix and is never routed around.

Voices and models change with the provider's catalogue, so they are read from the provider rather
than written down here. Google's voice list is the one that a call depends on — a voice name and
the locales the provider can be sent — so it is kept in memory for a day, per provider and
credential: a replaced key reads it again.
"""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Any

import httpx

from acervo.models.errors import RETRYABLE, ProviderError, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Checked, Provider, Voice

TIMEOUT_SECONDS = 15
DETAIL_LIMIT = 2000
VOICES_TTL_SECONDS = 24 * 3600

GOOGLE_VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/models/search"
# Workers AI's own names for the tasks a kind is.
CLOUDFLARE_TASKS = {"text": "Text Generation", "image": "Text-to-Image", "audio": "Text-to-Speech"}
GENDERS = {"FEMALE": "female", "MALE": "male", "NEUTRAL": "neutral"}

_lock = threading.Lock()
_voices: dict[tuple[str, str], tuple[float, tuple[dict[str, Any], ...]]] = {}


# ── the check ──


def check(provider: "Provider") -> "Checked":
    """One call that spends nothing, and what it says about the key."""
    from acervo.models.providers import Checked

    try:
        said, account = _CHECKS[provider.family.lister](provider)
    except ProviderError as error:
        # A check sends a request of ours that does not change, so a provider that turns it away is
        # turning away the key or the settings beside it — and some say so with a 400 rather than a
        # 401: Google answers a key that is not valid with `INVALID_ARGUMENT`.
        reason = "authentication" if error.reason in ("authentication", "configuration") else error.reason
        return Checked(False, _refusal(provider, error, reason), reason, None)
    return Checked(True, said, None, account)


def _refusal(provider: "Provider", error: ProviderError, reason: str) -> str:
    detail = f": {error.detail.strip().rstrip('.')}" if error.detail else ""
    if reason == "authentication":
        return f"{provider.label} refused this key{detail}"
    if reason in ("unreachable", "unavailable"):
        return f"{provider.label} did not answer{detail}"
    return f"{provider.label} said no{detail}"


def _check_openai(provider: "Provider") -> tuple[str, str | None]:
    if provider.family.check_url:
        _get(provider, provider.family.check_url, _bearer(provider))
        return "Works", None
    return f"Works · {_count(models(provider, 'text'))}", None


def _check_listing(provider: "Provider") -> tuple[str, str | None]:
    return f"Works · {_count(models(provider, 'text'))}", None


def _check_cloudflare(provider: "Provider") -> tuple[str, str | None]:
    _get(provider, CLOUDFLARE_URL.format(account=provider.setting("accountId")), _bearer(provider),
         params={"per_page": 1})
    return f"Works · account {provider.setting('accountId')}", None


def _check_google(provider: "Provider") -> tuple[str, str | None]:
    voices = _google_voices(provider, fresh=True)
    if provider.credential.file:
        account = provider.identity()
        return (f"Works as {account}" if account else "Works with your own sign-in"), account
    return (f"Works · Text-to-Speech answers with {len(voices)} voices. Vision is not checked, "
            "since no call to it is free"), None


def _count(found: tuple[str, ...]) -> str:
    return f"{len(found)} model{'s' if len(found) != 1 else ''}"


# ── models ──


def models(provider: "Provider", kind: str) -> tuple[str, ...]:
    """The models this provider offers for a kind, in its own spelling and order."""
    return _MODELS[provider.family.lister](provider, kind)


def _openai_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    if kind != "text":
        return ()
    base = provider.filled(provider.family.list_url) or provider.base_url()
    if not base:
        raise ProviderRefused("configuration", f"{provider.label} has no address", provider_id=provider.id)
    payload = _get(provider, f"{base}/models", _bearer(provider)).json()
    return tuple(str(one["id"]) for one in payload.get("data") or () if isinstance(one, dict) and one.get("id"))


def _gemini_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    if kind != "text":
        return ()
    payload = _get(provider, GEMINI_MODELS_URL, {"x-goog-api-key": provider.credential.key or ""},
                   params={"pageSize": 1000}).json()
    return tuple(
        str(one["name"]).removeprefix("models/") for one in payload.get("models") or ()
        if "generateContent" in (one.get("supportedGenerationMethods") or ())
    )


def _anthropic_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    if kind != "text":
        return ()
    payload = _get(provider, ANTHROPIC_MODELS_URL, {
        "x-api-key": provider.credential.key or "", "anthropic-version": "2023-06-01",
    }, params={"limit": 1000}).json()
    return tuple(str(one["id"]) for one in payload.get("data") or () if one.get("id"))


def _ollama_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    if kind != "text":
        return ()
    payload = _get(provider, f"{provider.base_url()}/api/tags", {}).json()
    return tuple(str(one["name"]) for one in payload.get("models") or () if one.get("name"))


def _cloudflare_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    task = CLOUDFLARE_TASKS.get(kind)
    if not task:
        return ()
    payload = _get(provider, CLOUDFLARE_URL.format(account=provider.setting("accountId")),
                   _bearer(provider), params={"task": task, "per_page": 100}).json()
    return tuple(str(one["name"]) for one in payload.get("result") or () if one.get("name"))


def _google_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    """Cloud TTS's voice types (`Wavenet`, `Chirp3-HD`…), and Vision's one feature. Vertex's models
    and Gemini's speech models are not listed by any call a key or a file can make cheaply, so those
    are typed."""
    if kind == "ocr":
        return ("document-text-detection",)
    if kind != "audio":
        return ()
    return tuple(dict.fromkeys(
        kind_of for kind_of in (_voice_type(one) for one in _google_voices(provider)) if kind_of
    ))


# ── voices ──


def voices(provider: "Provider", model: str) -> tuple["Voice", ...]:
    """The voices a model speaks with, from the provider's own list. Empty where it has none."""
    if provider.family.lister != "google-cloud":
        return ()
    from acervo.models.providers import Voice

    listed = _google_voices(provider)
    gemini = model.startswith("gemini-")
    found = []
    for one in listed:
        kind_of = _voice_type(one)
        # A Gemini voice is named once (`Kore`) and speaks any locale it is sent: Google lists it
        # under `en-US` alone, which is where it was made rather than all it says.
        if gemini and kind_of is None:
            found.append(Voice(one["name"], None, GENDERS.get(one.get("ssmlGender", ""))))
        elif not gemini and kind_of == model:
            code = (one.get("languageCodes") or [""])[0]
            found.append(Voice(one["name"], _bcp47(provider, code), GENDERS.get(one.get("ssmlGender", ""))))
    return tuple(found)


def locales(provider: "Provider") -> tuple[str, ...]:
    """Every locale the provider's voices are listed under, in BCP-47. For a voice that speaks any
    locale, these are the ones it can be sent — Gemini's refuse `es-AR` and accept `es-US`."""
    if provider.family.lister != "google-cloud":
        return ()
    return tuple(dict.fromkeys(
        _bcp47(provider, code) for one in _google_voices(provider) for code in one.get("languageCodes") or ()
    ))


def _voice_type(voice: dict[str, Any]) -> str | None:
    """`es-ES-Chirp3-HD-Kore` → `Chirp3-HD`; `Kore` → None."""
    name = str(voice.get("name") or "")
    code = (voice.get("languageCodes") or [""])[0]
    if not code or not name.startswith(code + "-"):
        return None
    middle = name[len(code) + 1:].rsplit("-", 1)[0]
    return middle or None


def _bcp47(provider: "Provider", code: str) -> str:
    """Google's `cmn-CN` back to `zh-Hans-CN`, by the family's own wire table."""
    wire = provider.family.audio.get("wire") or {}
    return next((tag for tag, spelled in wire.items() if spelled == code), code)


def _google_voices(provider: "Provider", *, fresh: bool = False) -> tuple[dict[str, Any], ...]:
    held = (provider.id, provider.credential.digest())
    with _lock:
        cached = _voices.get(held)
    if cached and not fresh and time.monotonic() - cached[0] < VOICES_TTL_SECONDS:
        return cached[1]
    from acervo.models import google_auth

    response = _get(provider, GOOGLE_VOICES_URL, google_auth.headers(provider, "voices"))
    listed = tuple(one for one in response.json().get("voices") or () if isinstance(one, dict) and one.get("name"))
    with _lock:
        _voices[held] = (time.monotonic(), listed)
    return listed


def forget() -> None:
    """Drop every remembered voice list. Tests use it."""
    with _lock:
        _voices.clear()


# ── one GET ──


def _bearer(provider: "Provider") -> dict[str, str]:
    return {"Authorization": f"Bearer {provider.credential.key}"} if provider.credential.key else {}


def _get(provider: "Provider", url: str, headers: dict[str, str], *,
         params: dict[str, Any] | None = None) -> httpx.Response:
    try:
        response = httpx.get(url, headers={"Accept": "application/json", **headers}, params=params,
                             timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as error:
        _fail(provider, "unreachable", str(error) or type(error).__name__, None)
    if not response.is_success:
        _fail(provider, None, _detail(response), response.status_code)
    return response


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "").strip()[:DETAIL_LIMIT] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:DETAIL_LIMIT]
        if isinstance(error, str):
            return error[:DETAIL_LIMIT]
        if payload.get("errors"):
            return json.dumps(payload["errors"], ensure_ascii=False)[:DETAIL_LIMIT]
    return json.dumps(payload, ensure_ascii=False)[:DETAIL_LIMIT]


def _fail(provider: "Provider", reason: str | None, detail: str, status: int | None):
    from acervo.models.call import status_reason

    if reason is None:
        reason = status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=provider.id, status=status)  # type: ignore[arg-type]


_CHECKS = {
    "openai": _check_openai,
    "gemini": _check_listing,
    "anthropic": _check_listing,
    "ollama": _check_listing,
    "cloudflare": _check_cloudflare,
    "google-cloud": _check_google,
}
_MODELS = {
    "openai": _openai_models,
    "gemini": _gemini_models,
    "anthropic": _anthropic_models,
    "ollama": _ollama_models,
    "cloudflare": _cloudflare_models,
    "google-cloud": _google_models,
}
