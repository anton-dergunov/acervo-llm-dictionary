"""Cloudflare images and Cloudflare audio, which LiteLLM does not reach.

LiteLLM covers Cloudflare *text* and neither of the other two, and this is the whole of the gap. The
logic is lifted from `experiments/image_benchmark/image_benchmark_runner.py`'s `run_cloudflare`, which already works
against the live service — including the awkward part: FLUX.2 Klein requires `multipart/form-data`
even for a text-only prompt, and a JSON body comes back as a 400 naming a required property
`multipart` (Cloudflare's FLUX.2 Klein launch note, 15 Jan 2026). The `(None, value)` field tuples are what
make an HTTP client send a multipart boundary without claiming the scalars are uploaded files.

It is copied rather than imported: `experiments/` is outside the distribution, and
`test_layering.py` enforces that nothing shipping reaches into it. It is on httpx rather than
`requests` because httpx emits the identical multipart body and is the one HTTP library this
service already carries.

The reverse — the benchmark calling *this* instead of keeping `run_cloudflare` — is possible and
deliberately not done. Its candidates launch under `uv run --no-project`, so `acervo` is not
importable in the child at all, and giving it one would change how every benchmark child is
launched for a set of candidates that are all `enabled: false` and whose evaluation is finished.
The duplication is one function, pinned by tests on both sides. Revisit it when a new hosted
candidate is benchmarked, which is the first moment it costs anything.

Failures go through `call.classify()`, the same table LiteLLM's exceptions go through, so a
Cloudflare 429 and a Gemini 429 are the same kind of thing to the chain above.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import httpx
from PIL import Image

from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Provider as Row

RUN_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
DETAIL_LIMIT = 2000


def image(
    row: Row,
    model: str,
    prompt: str,
    *,
    seed: int | None = None,
    size: tuple[int, int] | None = None,
    references: Sequence[bytes] = (),
    timeout: float = 120.0,
) -> tuple[bytes, str]:
    width, height = size or (512, 512)
    fields: dict[str, Any] = {
        "prompt": (None, prompt),
        "width": (None, str(int(width))),
        "height": (None, str(int(height))),
        "guidance": (None, str(float(row.params_for("image").get("guidance", 1.0)))),
    }
    if seed is not None:
        fields["seed"] = (None, str(int(seed)))
    side = int(row.image_capabilities().get("referenceSide") or 511)
    for index, data in enumerate(references):
        fields[f"input_image_{index}"] = (f"input_image_{index}.png", _fitted(data, side), "image/png")
    payload = _run(row, model, fields=fields, timeout=timeout)
    return _image_bytes(row, model, payload)


def _fitted(data: bytes, side: int) -> bytes:
    """A reference picture as a PNG no larger than `side` either way, its aspect ratio kept.

    Klein refuses an input picture of 512×512 or more, and a story's pictures are 1024 wide.
    """
    with Image.open(io.BytesIO(data)) as picture:
        picture = picture.convert("RGB")
        picture.thumbnail((side, side), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        picture.save(out, format="PNG")
        return out.getvalue()


def speech(
    row: Row,
    model: str,
    words: str,
    *,
    language: str | None = None,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = 120.0,
) -> tuple[bytes, str]:
    # `language` and `style` are accepted for the adapter signature and not sent: Aura is one
    # language per model, and the model says which through `languages`; it takes no direction.
    # Cloudflare's text-to-speech models disagree about what the field is called: MeloTTS takes
    # `prompt` (plus a `lang`), Deepgram's Aura takes `text` and refuses `prompt`.
    body: dict[str, Any] = {str(row.family.audio.get("inputField") or "prompt"): words}
    chosen = voice
    if chosen:
        body["speaker"] = chosen
    payload = _run(row, model, json_body=body, timeout=timeout)
    return _audio_bytes(row, model, payload)


def _run(
    row: Row,
    model: str,
    *,
    fields: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float,
) -> httpx.Response:
    account = row.setting("accountId")
    token = row.credential.key
    if not account or not token:
        # Reaching here means the chain called a provider it had already been told was unavailable.
        raise ProviderRefused("unconfigured", row.reason() or f"{row.label} cannot be asked",
                              provider_id=row.id, model=model)

    try:
        response = httpx.post(
            RUN_URL.format(account=account, model=model),
            headers={"Authorization": f"Bearer {token}"},
            files=fields,
            json=json_body,
            timeout=timeout,
        )
    except httpx.HTTPError as error:
        _fail(row, model, "unreachable", str(error), None)

    if not response.is_success:
        _fail(row, model, None, _detail(response), response.status_code)
    return response


def _image_bytes(row: Row, model: str, response: httpx.Response) -> tuple[bytes, str]:
    """Cloudflare answers with the image itself, or with a base64 field inside its envelope."""
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        return response.content, content_type.split(";")[0].strip()
    result = _result(row, model, response)
    encoded = result.get("image") if isinstance(result, dict) else result
    if isinstance(encoded, list):
        encoded = encoded[0] if encoded else None
    if not isinstance(encoded, str):
        _fail(row, model, "refused", "the response contained no image data", response.status_code)
    return base64.b64decode(encoded.split(",", 1)[-1]), "image/png"


def _audio_bytes(row: Row, model: str, response: httpx.Response) -> tuple[bytes, str]:
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("audio/"):
        return response.content, content_type.split(";")[0].strip()
    result = _result(row, model, response)
    encoded = result.get("audio") if isinstance(result, dict) else result
    if not isinstance(encoded, str):
        _fail(row, model, "refused", "the response contained no audio data", response.status_code)
    return base64.b64decode(encoded.split(",", 1)[-1]), "audio/mpeg"


def _result(row: Row, model: str, response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        _fail(row, model, "refused", "the response was not JSON", response.status_code)
    if isinstance(payload, dict) and not payload.get("success", True):
        _fail(row, model, "refused", json.dumps(payload.get("errors")), response.status_code)
    return payload.get("result", payload) if isinstance(payload, dict) else payload


def _detail(response: httpx.Response) -> str:
    """Cloudflare's own error code, which is the only actionable part of a failure here."""
    try:
        return json.dumps(response.json(), ensure_ascii=False)[:DETAIL_LIMIT]
    except ValueError:
        return (response.text or "").strip()[:DETAIL_LIMIT] or "empty response body"


def _fail(row: Row, model: str, reason: str | None, detail: str, status: int | None) -> None:
    from acervo.models.call import status_reason

    if reason is None:
        reason = status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=row.id, model=model, status=status)  # type: ignore[arg-type]
