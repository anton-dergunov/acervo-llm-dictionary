"""OpenAI-style speech: `POST {base}/audio/speech`, which Kokoro-FastAPI, Speaches (Piper) and
OpenAI itself all answer.

The request is the same for all of them: a model, the words as `input`, a voice, and the format.
`wav` is asked for, an uncompressed master, because `pronunciation/encode.py` does the compressing.
Kokoro streams its WAV with a placeholder length in the header, and `soundfile` reads it.

The request has no language: Kokoro speaks the language of its voice, which is in the voice's name
(`listing.voices`), and the voice chosen for a language is one made for it. A direction goes in
`instructions`, which only OpenAI's own speech model reads; `call.speech` sends one only to a model
said to take one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Provider as Row


def speech(
    row: Row,
    model: str,
    words: str,
    *,
    language: str,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = 60.0,
) -> tuple[bytes, str]:
    from acervo.models import listing

    base = row.base_url()
    if not base:
        raise ProviderRefused("configuration", f"{row.label} has no address", provider_id=row.id, model=model)
    chosen = voice or next(iter(row.voices_for(model, language)), None)
    if not chosen:
        row.voices(model, strict=True)
        raise ProviderRefused(
            "configuration", f"{model} names no voice for {language}", provider_id=row.id, model=model
        )
    body: dict[str, Any] = {
        "model": model,
        "input": words,
        "voice": chosen,
        "response_format": str(row.family.audio.get("format") or "wav"),
    }
    if style:
        body["instructions"] = style
    headers = {"Authorization": f"Bearer {row.credential.key}"} if row.credential.key else {}
    try:
        response = httpx.post(f"{base}/audio/speech", headers=headers, json=body, timeout=timeout)
    except httpx.HTTPError as error:
        _fail(row, model, "unreachable", str(error) or type(error).__name__, None)
    if not response.is_success:
        _fail(row, model, None, listing.response_detail(response), response.status_code)
    if not response.content:
        _fail(row, model, "empty", "the response contained no audio", response.status_code)
    return response.content, response.headers.get("content-type", "audio/wav").split(";")[0].strip()


def _fail(row: Row, model: str, reason: str | None, detail: str, status: int | None) -> None:
    from acervo.models.call import status_reason

    if reason is None:
        reason = status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=row.id, model=model, status=status)  # type: ignore[arg-type]
