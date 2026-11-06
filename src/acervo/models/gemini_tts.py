"""Gemini API speech: the Interactions API, reached with an AI Studio key, which LiteLLM does not reach.

One route, `POST /v1beta/interactions`, with a TTS model. The words go in a `text` item and the
direction in that item's `speech_metadata` annotation, a field of its own, so it shapes the reading
without being read out. The voice is named in `generation_config.speech_config`.

The request has **no language field**: the model guesses the language from the text. A sentence is
guessed right; a single word is not. Measured on 6 Nov 2026 with Flash-Lite TTS and a transcriber
listening back: "picar" came back as English ("Picard") and "pie" as Hindi. With "Say this in
Spanish." as the direction, "picar" was Spanish. So the language always travels at the head of the
direction. A voice made for an accent (`es-419-advisor-1`) still gets the line, because a word in it
is as ambiguous as in any other.

The answer is a RIFF WAV, 24 kHz mono 16-bit PCM: an uncompressed master, which is what
`pronunciation/encode.py` wants to compress from. Failures go through `call.status_reason`, the same
table every other provider's do, and Google's "Please retry in 59s" reaches the cooldown in the
detail.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import httpx

from acervo.models import locales
from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Provider as Row

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DETAIL_LIMIT = 2000


def direction(language: str, style: str | None) -> str:
    """The language the words are in, then the delivery asked for."""
    said = f"Say this in {locales.language_name(language)}."
    return f"{said} {style.strip()}" if style and style.strip() else said


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
        # A voice list that could not be read fails here with Google's own sentence.
        row.voices(model, strict=True)
        raise ProviderRefused(
            "configuration", f"{model} names no voice for {language}", provider_id=row.id, model=model
        )
    body: dict[str, Any] = {
        "model": model,
        "input": [{"type": "user_input", "content": [{
            "type": "text",
            "text": words,
            "annotations": [{"type": "speech_metadata", "style": direction(language, style)}],
        }]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": chosen}]},
    }
    try:
        response = httpx.post(
            INTERACTIONS_URL, headers={"x-goog-api-key": row.credential.key or ""}, json=body,
            timeout=timeout,
        )
    except httpx.HTTPError as error:
        _fail(row, model, "unreachable", str(error) or type(error).__name__, None)
    if not response.is_success:
        _fail(row, model, None, _detail(response), response.status_code)
    try:
        steps = response.json().get("steps") or []
    except (ValueError, AttributeError):
        steps = []
    found = [
        item.get("data") for step in steps if isinstance(step, dict) and step.get("type") == "model_output"
        for item in step.get("content") or () if isinstance(item, dict) and item.get("type") == "audio"
    ]
    encoded = found[-1] if found else None
    if not isinstance(encoded, str) or not encoded:
        _fail(row, model, "empty", "the response contained no audio", response.status_code)
    return base64.b64decode(encoded), "audio/wav"


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "").strip()[:DETAIL_LIMIT] or f"HTTP {response.status_code}"
    # A refused key comes back as a list holding one error (measured), any other refusal as one.
    if isinstance(payload, list) and payload:
        payload = payload[0]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])[:DETAIL_LIMIT]
    return str(payload)[:DETAIL_LIMIT]


def _fail(row: Row, model: str, reason: str | None, detail: str, status: int | None) -> None:
    from acervo.models.call import status_reason

    if reason is None:
        reason = status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=row.id, model=model, status=status)  # type: ignore[arg-type]
