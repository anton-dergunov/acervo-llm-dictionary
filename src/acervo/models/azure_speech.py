"""Azure Speech: `POST https://{region}.tts.speech.microsoft.com/cognitiveservices/v1`, with SSML.

Written from Microsoft's REST reference (`learn.microsoft.com/azure/ai-services/speech-service/
rest-text-to-speech`) and not yet tried against the service, which is what the family's `tried`
says. The voice is named in the SSML with its locale. `riff-24khz-16bit-mono-pcm` is the uncompressed
master, like every other voice's. Azure takes no free-text direction (its styles are a fixed list),
so these are plain voices, and the words are escaped rather than read as markup.

Azure often answers a failure with an empty body, so the status is the sentence: 401 is a wrong key
or a key for another region, 429 the free tier's quota.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.sax.saxutils import escape, quoteattr

import httpx

from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Provider as Row

SPEECH_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
STATUSES = {
    400: "Azure refused the request",
    401: "Azure refused this key: it is wrong, or for another region",
    415: "Azure refused the request's format",
    429: "Azure's quota for this resource is spent for now",
}


def ssml(words: str, voice: str, locale: str) -> str:
    return (f"<speak version='1.0' xml:lang={quoteattr(locale)}>"
            f"<voice xml:lang={quoteattr(locale)} name={quoteattr(voice)}>{escape(words)}</voice></speak>")


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
    from acervo.models import listing

    region = row.setting("region")
    chosen = voice or next(iter(row.voices_for(model, language)), None)
    if not chosen:
        row.voices(model, strict=True)
        raise ProviderRefused(
            "configuration", f"{row.label} names no voice for {language}", provider_id=row.id, model=model
        )
    locale = row.locale_for(model, language, chosen)
    try:
        response = httpx.post(
            SPEECH_URL.format(region=region),
            headers={
                "Ocp-Apim-Subscription-Key": row.credential.key or "",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": str(row.family.audio.get("format") or "riff-24khz-16bit-mono-pcm"),
                "User-Agent": "acervo",
            },
            content=ssml(words, chosen, locale).encode("utf-8"),
            timeout=timeout,
        )
    except httpx.HTTPError as error:
        _fail(row, model, "unreachable", str(error) or type(error).__name__, None)
    if not response.is_success:
        said = listing.response_detail(response) if response.content else ""
        _fail(row, model, None, said or STATUSES.get(response.status_code, f"HTTP {response.status_code}"),
              response.status_code)
    if not response.content:
        _fail(row, model, "empty", "the response contained no audio", response.status_code)
    return response.content, "audio/wav"


def _fail(row: Row, model: str, reason: str | None, detail: str, status: int | None) -> None:
    from acervo.models.call import status_reason

    if reason is None:
        reason = status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=row.id, model=model, status=status)  # type: ignore[arg-type]
