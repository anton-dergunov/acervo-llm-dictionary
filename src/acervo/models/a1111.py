"""Pictures drawn on your own machine, through A1111's route: `POST {base}/sdapi/v1/txt2img`.

Draw Things on a Mac answers it, and so do Forge and A1111 on a GPU machine. They agree on the
request and the answer (base64 PNGs in `images`) and disagree on choosing the model, which the
family states (`image.modelField`):

- **Draw Things** takes `model`, the file name, and refuses any key it does not know with a 422
  ("Unrecognized keys: [\"override_settings\"]"), measured on 6 Nov 2026.
- **A1111 and Forge** take `override_settings.sd_model_checkpoint`.

Anything the request does not say, the server takes from its own settings, and Draw Things' are
whatever its window shows: 16 steps and guidance 5 when SDXL Turbo was loaded. A distilled model —
Turbo, Lightning, schnell, Hyper, LCM, klein — is made for a few steps and almost no guidance, and is
slower and burnt at those settings, so such a model is sent 4 steps and guidance 1. Anything else is
left to the server's settings for it, and the owner's `extra` wins over both.

Measured with SDXL Turbo (8-bit) on an M1 with 16 GB: 512² at 4 steps in 10 s, 20 s for the first
picture after the model loads.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import httpx

from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Provider as Row

DISTILLED = ("turbo", "lightning", "schnell", "hyper", "lcm", "klein")
FEW_STEPS = {"steps": 4, "cfg_scale": 1.0}
DEFAULT_SIZE = (512, 512)


def request(row: Row, model: str, prompt: str, *, seed: int | None,
            size: tuple[int, int] | None) -> dict[str, Any]:
    width, height = size or DEFAULT_SIZE
    body: dict[str, Any] = {"prompt": prompt, "width": int(width), "height": int(height), "batch_size": 1}
    if seed is not None:
        body["seed"] = int(seed)
    if any(word in model.lower() for word in DISTILLED):
        body.update(FEW_STEPS)
    if row.family.image.get("modelField") == "override":
        body["override_settings"] = {"sd_model_checkpoint": model}
    else:
        body["model"] = model
    body.update(row.params_for("image"))
    return body


def image(
    row: Row,
    model: str,
    prompt: str,
    *,
    seed: int | None = None,
    size: tuple[int, int] | None = None,
    timeout: float = 300.0,
) -> tuple[bytes, str]:
    from acervo.models import listing

    base = row.base_url()
    if not base:
        raise ProviderRefused("configuration", f"{row.label} has no address", provider_id=row.id, model=model)
    try:
        response = httpx.post(f"{base}/sdapi/v1/txt2img", json=request(row, model, prompt, seed=seed, size=size),
                              timeout=timeout)
    except httpx.HTTPError as error:
        _fail(row, model, "unreachable", str(error) or type(error).__name__, None)
    if not response.is_success:
        _fail(row, model, None, listing.response_detail(response), response.status_code)
    try:
        images = response.json().get("images") or []
    except (ValueError, AttributeError):
        images = []
    if not images or not isinstance(images[0], str):
        _fail(row, model, "empty", "the response contained no picture", response.status_code)
    data = base64.b64decode(images[0].split(",", 1)[-1])
    return data, "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _fail(row: Row, model: str, reason: str | None, detail: str, status: int | None) -> None:
    from acervo.models.call import status_reason

    if reason is None:
        # A server that cannot use what it was sent says so with a 422.
        reason = "configuration" if status == 422 else status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=row.id, model=model, status=status)  # type: ignore[arg-type]
