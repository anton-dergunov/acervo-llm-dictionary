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
import re
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
GEMINI_VOICES_URL = "https://generativelanguage.googleapis.com/v1beta/voices"
ELEVENLABS_URL = "https://api.elevenlabs.io"
# Gemini lists about 2,100 voices, a thousand to a page. A bound on pages, so a token that never ends
# cannot hold a request open.
VOICE_PAGES = 10
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
        reason, said = refusal(provider, error)
        return Checked(False, said, reason, None)
    return Checked(True, said, None, account)


def refusal(provider: "Provider", error: ProviderError) -> tuple[str, str]:
    """Why a listing or a check was turned away, and the sentence that says so.

    A listing sends a request of ours that does not change, so a provider that turns it away is
    turning away the key or the settings beside it — and some say so with a 400 rather than a 401:
    Google answers a key that is not valid with `INVALID_ARGUMENT`.
    """
    reason = "authentication" if error.reason in ("authentication", "configuration") else error.reason
    detail = f": {error.detail.strip().rstrip('.')}" if error.detail else ""
    if reason == "authentication":
        return reason, f"{provider.label} refused this key{detail}"
    if reason in ("unreachable", "unavailable"):
        return reason, f"{provider.label} did not answer{detail}"
    return reason, f"{provider.label} said no{detail}"


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


def _check_elevenlabs(provider: "Provider") -> tuple[str, str | None]:
    """The account's plan and what it has spent this month, from `/v1/user`, which spends nothing."""
    subscription = _get(provider, f"{ELEVENLABS_URL}/v1/user", _xi(provider)).json().get("subscription") or {}
    used, limit = subscription.get("character_count"), subscription.get("character_limit")
    plan = f" · {subscription['tier']} plan" if subscription.get("tier") else ""
    spent = f" · {used:,} of {limit:,} credits used this month" if isinstance(used, int) and isinstance(limit, int) else ""
    return f"Works{plan}{spent}", None


def _check_speech_server(provider: "Provider") -> tuple[str, str | None]:
    return f"Works · {len(_speech_server_voices(provider, fresh=True))} voices", None


def _count(found: tuple[str, ...]) -> str:
    return f"{len(found)} model{'s' if len(found) != 1 else ''}"


# ── models ──


def lists(provider: "Provider", kind: str) -> bool:
    """Whether this provider can say which models it has for a kind. Where it cannot — Vertex, or
    Gemini's voices on Cloud Text-to-Speech — the owner types the model's name."""
    return kind in _LISTS[provider.family.lister]


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
    """Every model that answers `generateContent`, split by Gemini's own naming: a speech model is
    `…-tts`, a picture model `…-image`, and neither writes text."""
    if kind not in ("text", "audio"):
        return ()
    payload = _get(provider, GEMINI_MODELS_URL, {"x-goog-api-key": provider.credential.key or ""},
                   params={"pageSize": 1000}).json()
    names = [
        str(one["name"]).removeprefix("models/") for one in payload.get("models") or ()
        if "generateContent" in (one.get("supportedGenerationMethods") or ())
    ]
    speech = [name for name in names if "-tts" in name]
    if kind == "audio":
        return tuple(speech)
    return tuple(name for name in names if name not in speech and "-image" not in name)


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


def _elevenlabs_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    if kind != "audio":
        return ()
    listed = _get(provider, f"{ELEVENLABS_URL}/v1/models", _xi(provider)).json()
    return tuple(str(one["model_id"]) for one in listed if isinstance(one, dict) and one.get("model_id")
                 and one.get("can_do_text_to_speech"))


def _speech_server_models(provider: "Provider", kind: str) -> tuple[str, ...]:
    if kind != "audio":
        return ()
    payload = _get(provider, f"{_address(provider)}/models", _bearer(provider)).json()
    return tuple(str(one["id"]) for one in payload.get("data") or () if isinstance(one, dict) and one.get("id"))


def _address(provider: "Provider") -> str:
    base = provider.filled(provider.family.list_url) or provider.base_url()
    if not base:
        raise ProviderRefused("configuration", f"{provider.label} has no address", provider_id=provider.id)
    return base


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


def lists_voices(provider: "Provider") -> bool:
    """Whether this provider can say which voices a model has. Where it cannot, they are typed."""
    return provider.family.lister in _VOICES


def voices(provider: "Provider", model: str) -> tuple["Voice", ...]:
    """The voices a model speaks with, from the provider's own list. Empty where it has none."""
    if not lists_voices(provider):
        return ()
    return _VOICES[provider.family.lister](provider, model)


def _google_voice_list(provider: "Provider", model: str) -> tuple["Voice", ...]:
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


def _gemini_voice_list(provider: "Provider", model: str) -> tuple["Voice", ...]:
    """The Gemini API's voices, the same for every speech model.

    Two kinds, told apart the way Google Cloud's are. The thirty voices named once (`kore`) are
    listed under `en-US` and speak any language they are told. The rest are made for a locale and
    carry it in their id (`es-419-advisor-1`). Latin American Spanish is one locale on the wire, and
    the voice's `accent` names the country ("Argentina Spanish"), so the voice is offered as `es-AR`.
    """
    from acervo.models.providers import Voice

    found = []
    for one in _cached_voices(provider, _gemini_voices):
        identifier = str(one["id"])
        code = str(one.get("language_code") or "")
        gender = one.get("gender") if one.get("gender") in GENDERS.values() else None
        label = str(one.get("display_name") or "") or None
        if not code or not identifier.lower().startswith(code.lower() + "-"):
            found.append(Voice(identifier, None, gender, label=label))
            continue
        accent = str(one.get("accent") or "") or None
        found.append(Voice(identifier, _named_country(code, accent), gender, accent, label))
    return tuple(found)


def _elevenlabs_voice_list(provider: "Provider", model: str) -> tuple["Voice", ...]:
    """The account's voices: the premade ones and any it made. Each speaks every language its model
    has, so none is given a locale. ElevenLabs names one "Sarah - Mature, Reassuring, Confident":
    the name before the dash, and the words after it are its character."""
    from acervo.models.providers import Voice

    found = []
    for one in _cached_voices(provider, _elevenlabs_voices):
        name, _, character = str(one.get("name") or one["voice_id"]).partition(" - ")
        gender = (one.get("labels") or {}).get("gender")
        found.append(Voice(str(one["voice_id"]), None, gender if gender in GENDERS.values() else None,
                           character.strip() or None, name.strip() or None))
    return tuple(found)


# Kokoro names a voice by language and gender: `ef_dora` is a woman speaking Spanish. Its own table
# (`VOICES.md` in hexgrad/Kokoro-82M); Spanish and Chinese say no region, so none is claimed.
KOKORO_LANGUAGES = {"a": "en-US", "b": "en-GB", "e": "es", "f": "fr-FR", "h": "hi-IN", "i": "it-IT",
                    "j": "ja-JP", "p": "pt-BR", "z": "zh"}
_KOKORO = re.compile(r"^([abefhijpz])([fm])_[a-z0-9_]+$")
# Piper names a voice by its locale: `en_US-amy-medium`, sometimes behind a path.
_PIPER = re.compile(r"(?:^|[/_-])([a-z]{2,3})_([A-Z]{2})(?=[-_.]|$)")


def _speech_server_voice_list(provider: "Provider", model: str) -> tuple["Voice", ...]:
    """A speech server's voices, with the locale and gender their names carry where they follow
    Kokoro's or Piper's convention. A name that follows neither speaks any locale it is told."""
    from acervo.models.providers import Voice

    found = []
    for name in _speech_server_voices(provider):
        if kokoro := _KOKORO.match(name):
            found.append(Voice(name, KOKORO_LANGUAGES[kokoro.group(1)],
                               "female" if kokoro.group(2) == "f" else "male"))
        elif piper := _PIPER.search(name):
            found.append(Voice(name, f"{piper.group(1)}-{piper.group(2)}"))
        else:
            found.append(Voice(name))
    return tuple(found)


def _speech_server_voices(provider: "Provider", *, fresh: bool = False) -> tuple[str, ...]:
    def read(provider: "Provider") -> tuple[str, ...]:
        payload = _get(provider, f"{_address(provider)}/audio/voices", _bearer(provider)).json()
        listed = payload.get("voices") if isinstance(payload, dict) else payload
        names = []
        for one in listed or ():
            name = one.get("id") or one.get("name") if isinstance(one, dict) else one
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        return tuple(names)

    return _cached_voices(provider, read, fresh=fresh)


def _elevenlabs_voices(provider: "Provider") -> tuple[dict[str, Any], ...]:
    listed: list[dict[str, Any]] = []
    token = None
    for _ in range(VOICE_PAGES):
        params: dict[str, Any] = {"page_size": 100}
        if token:
            params["next_page_token"] = token
        payload = _get(provider, f"{ELEVENLABS_URL}/v2/voices", _xi(provider), params=params).json()
        listed.extend(one for one in payload.get("voices") or () if isinstance(one, dict) and one.get("voice_id"))
        token = payload.get("next_page_token")
        if not payload.get("has_more") or not token:
            break
    return tuple(listed)


def _named_country(code: str, accent: str | None) -> str:
    """`es-419` with "Argentina Spanish" → `es-AR`. Any other locale is kept as listed."""
    from acervo.models import locales as tags

    parsed = tags.parse(code)
    if not accent or not parsed.region or not parsed.region.isdigit():
        return code
    for region in tags.accents(parsed.language):
        name = tags.region_name(region)
        if len(region) == 2 and name and accent.startswith(name + " "):
            return tags.with_region(code, region)
    return code


def _gemini_voices(provider: "Provider") -> tuple[dict[str, Any], ...]:
    listed: list[dict[str, Any]] = []
    token = None
    for _ in range(VOICE_PAGES):
        params: dict[str, Any] = {"page_size": 1000}
        if token:
            params["page_token"] = token
        payload = _get(provider, GEMINI_VOICES_URL, {"x-goog-api-key": provider.credential.key or ""},
                       params=params).json()
        listed.extend(one for one in payload.get("voices") or () if isinstance(one, dict) and one.get("id"))
        token = payload.get("next_page_token")
        if not token:
            break
    return tuple(listed)


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
    return _cached_voices(provider, _read_google_voices, fresh=fresh)


def _read_google_voices(provider: "Provider") -> tuple[dict[str, Any], ...]:
    from acervo.models import google_auth

    response = _get(provider, GOOGLE_VOICES_URL, google_auth.headers(provider, "voices"))
    return tuple(one for one in response.json().get("voices") or () if isinstance(one, dict) and one.get("name"))


def _cached_voices(provider: "Provider", read, *, fresh: bool = False) -> tuple[dict[str, Any], ...]:
    """A provider's voice list, read at most once a day per provider and credential."""
    held = (provider.id, provider.credential.digest())
    with _lock:
        cached = _voices.get(held)
    if cached and not fresh and time.monotonic() - cached[0] < VOICES_TTL_SECONDS:
        return cached[1]
    listed = read(provider)
    with _lock:
        _voices[held] = (time.monotonic(), listed)
    return listed


def forget() -> None:
    """Drop every remembered voice list. Tests use it."""
    with _lock:
        _voices.clear()


# ── one GET ──


def _xi(provider: "Provider") -> dict[str, str]:
    return {"xi-api-key": provider.credential.key or ""}


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
        _fail(provider, None, response_detail(response), response.status_code)
    return response


def response_detail(response: httpx.Response) -> str:
    """A provider's own sentence for a failed response, whichever of the usual shapes it takes."""
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
        # ElevenLabs: `{"detail": {"code": …, "message": …}}`.
        detail = payload.get("detail")
        if isinstance(detail, dict) and detail.get("message"):
            return str(detail["message"])[:DETAIL_LIMIT]
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
    "elevenlabs": _check_elevenlabs,
    "speech-server": _check_speech_server,
}
# The kinds each listing code can list, and the ones whose voices it can.
_LISTS = {
    "openai": {"text"},
    "gemini": {"text", "audio"},
    "anthropic": {"text"},
    "ollama": {"text"},
    "cloudflare": {"text", "image", "audio"},
    "google-cloud": {"audio", "ocr"},
    "elevenlabs": {"audio"},
    "speech-server": {"audio"},
}
_VOICES = {
    "google-cloud": _google_voice_list,
    "gemini": _gemini_voice_list,
    "elevenlabs": _elevenlabs_voice_list,
    "speech-server": _speech_server_voice_list,
}
_MODELS = {
    "openai": _openai_models,
    "gemini": _gemini_models,
    "anthropic": _anthropic_models,
    "ollama": _ollama_models,
    "cloudflare": _cloudflare_models,
    "google-cloud": _google_models,
    "elevenlabs": _elevenlabs_models,
    "speech-server": _speech_server_models,
}
