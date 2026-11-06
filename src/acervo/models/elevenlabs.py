"""ElevenLabs speech, which LiteLLM does not reach.

One route, `POST /v1/text-to-speech/{voice_id}`. A voice is sent by its id (`EXAVITQu4vr4xnSDxMaL`)
and shown by the name ElevenLabs gives it (`listing.voices`). Every premade voice speaks every
language its model has, so the language goes as `language_code`, the bare language: ElevenLabs
takes no region.

A direction is a tag: Eleven v3 and v4 read free text in square brackets at the head of the words
as how to say them, and do not say it. `call.speech` sends a direction only to a model said to take
one, so an older model never hears its tag read out.

Failures keep ElevenLabs' own sentence (`detail.message`) and are classified by its `detail.code`
where the status alone says the wrong thing. The one that matters is a month's credits spent: a 402
`insufficient_credits`, which the bare status table calls a refusal. It is an allowance spent, like a
429 from a free tier, so it is said as one and the order passes to the next voice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from acervo.models import locales
from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Provider as Row

SPEECH_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
DETAIL_LIMIT = 2000
# ElevenLabs' codes that say more than their status (`elevenlabs.io/docs/developers/resources/errors`).
CODES = {"insufficient_credits": "rate_limited"}


def worded(words: str, style: str | None) -> str:
    """The words, with the direction as one leading tag where there is one."""
    direction = " ".join((style or "").replace("[", "(").replace("]", ")").split())
    return f"[{direction}] {words}" if direction else words


def speech(
    row: Row,
    model: str,
    words: str,
    *,
    language: str,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = 30.0,
) -> tuple[bytes, str]:
    chosen = voice or next(iter(row.voices_for(model, language)), None)
    if not chosen:
        row.voices(model, strict=True)
        raise ProviderRefused(
            "configuration", f"{model} names no voice for {language}", provider_id=row.id, model=model
        )
    output = str(row.family.audio.get("format") or "mp3_44100_128")
    body: dict[str, Any] = {
        "text": worded(words, style),
        "model_id": model,
        "language_code": locales.parse(language).language,
    }
    try:
        response = httpx.post(
            SPEECH_URL.format(voice=chosen), params={"output_format": output},
            headers={"xi-api-key": row.credential.key or ""}, json=body, timeout=timeout,
        )
    except httpx.HTTPError as error:
        fail(row, model, "unreachable", str(error) or type(error).__name__, None)
    if not response.is_success:
        fail(row, model, None, *said(response))
    if not response.content:
        fail(row, model, "empty", "the response contained no audio", response.status_code)
    return response.content, response.headers.get("content-type", "audio/wav").split(";")[0].strip()


def said(response: httpx.Response) -> tuple[str, int | None, str | None]:
    """ElevenLabs' sentence for a failure, its status, and its code."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("status") or f"HTTP {response.status_code}")
        return message[:DETAIL_LIMIT], response.status_code, detail.get("code")
    if isinstance(detail, str):
        return detail[:DETAIL_LIMIT], response.status_code, None
    return (response.text or "").strip()[:DETAIL_LIMIT] or f"HTTP {response.status_code}", response.status_code, None


def fail(row: Row, model: str | None, reason: str | None, detail: str, status: int | None,
         code: str | None = None) -> None:
    from acervo.models.call import status_reason

    if reason is None:
        reason = CODES.get(code or "") or status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=row.id, model=model, status=status)  # type: ignore[arg-type]
