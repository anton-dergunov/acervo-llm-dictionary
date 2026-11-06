"""One provider, one call, over LiteLLM or the family's own adapter.

Four functions, and each returns what it did. The chain lives next door in `chain.py`; this module
knows only how to ask one provider and how to read what came back.

Two things here are contract rather than implementation.

**The classification is type-first, then status.** `litellm.Timeout` carries status 408 and
`litellm.APIConnectionError` carries 500, so a map written on `status_code` alone would send a
timeout to "refused" — and `scripts/ingest_vocabulary_file.py` does not retry a refusal. The retry
behaviour would have changed without a line of the retry code changing, which is the specific
failure this package was asked to avoid.

**LiteLLM's own retries are switched off, twice.** `num_retries` is its loop and `max_retries` is
the provider SDK's, which LiteLLM otherwise sets to 2. `acervo.client` carries no retries for the
same reason: a retry layer inside the transport changes the behaviour of retry code that lives
somewhere else and is tested there.
"""

from __future__ import annotations

import base64
import json
import math
import re
import time
from typing import Any, Mapping, Sequence

from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable, Reason
from acervo.models.providers import Provider as Row
from acervo.models.results import Answer, AudioResult, ImageResult, OcrResult, Spent, TextResult

# **Both of these are set from the call log, not from feel** — run `python -m acervo.admin calls`
# and they can be argued with. Across every call that deployment has recorded, the slowest answer of
# any kind was **6.74 s**, and the slowest brief 2.29 s. The 120 seconds this file used to carry for
# everything was a guess, and it was wrong by more than an order of magnitude: one connection that
# never opened cost two minutes of "Writing a brief…" for a brief that took 1.97 s once the chain
# moved on.
#
# Being wrong on the short side is cheap and self-announcing. A call past the bound is not slow, it
# is gone — the chain asks the next pair immediately, `cooldown` demotes the one that hung, and the
# log records the timeout with the job named. So if either number is too tight, the evidence arrives
# as a line saying exactly that, rather than as a page nobody can explain.
TIMEOUT_SECONDS = 30
"""Capture, which writes a whole article. Slowest recorded: 6.74 s."""

SHORT_TIMEOUT_SECONDS = 20
"""A short structured answer with somebody watching a page. Slowest recorded: 2.29 s."""

# How long a pair may stay silent before the next one is asked beside it (`chain.walk`'s
# `hedge_after`). Not a timeout — the first call keeps running and still wins if it answers first.
# Measured on 2026-09-15 against the free Gemini tier with the real prompts: a healthy compose took
# 1.5–3 s with one at 7.7 s, and a healthy resolve under 3 s — while the same models sometimes took
# 19–23 s or never opened a connection. Set just above the healthy tail, so a race is rare and costs
# one extra free-tier request when it happens.
HEDGE_SECONDS = 8
"""Capture's compose, and chat: a whole article or a proposed revision of one."""

SHORT_HEDGE_SECONDS = 4
"""Capture's resolve: a few fields about what a scrap of text is."""

_FENCED = re.compile(r"^```[a-zA-Z]*\s*\n([\s\S]*?)\n?```$")

# Classified by type, in this order, before any status is looked at.
_BY_TYPE: tuple[tuple[str, Reason], ...] = (
    ("Timeout", "unreachable"),
    ("APIConnectionError", "unreachable"),
    ("RateLimitError", "rate_limited"),
    ("AuthenticationError", "authentication"),
    ("PermissionDeniedError", "authentication"),
    ("NotFoundError", "configuration"),
    ("BadRequestError", "configuration"),  # after its subclasses, which are all configuration too
)


def _litellm():
    """LiteLLM, imported the first time something actually calls a model.

    Importing it at module scope would make `acervo.models.pacing` — which the file ingestion and
    the worker image both use — depend on a library neither of them calls.
    """
    import litellm

    # It prints provider request context on some error paths. Health refuses to name a key or a
    # project; stdout must not undo that.
    litellm.suppress_debug_info = True
    return litellm


def completion(**kwargs: Any) -> Any:
    """The seam. Tests replace this attribute; nothing else wraps it."""
    return _litellm().completion(**kwargs)


def image_generation(**kwargs: Any) -> Any:
    return _litellm().image_generation(**kwargs)


_AUDIO_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"RIFF", "audio/wav"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
)


def audio_mime(data: bytes) -> str:
    """What these bytes actually are, rather than what the caller hoped.

    Gemini's speech models answer WAV and Cloudflare's Aura answers MP3, so a hardcoded type is
    wrong for one of them — and a stored clip labelled as the wrong container is a file nothing will
    play, discovered long after the call that made it.
    """
    for signature, mime in _AUDIO_SIGNATURES:
        if data.startswith(signature):
            return mime
    return "application/octet-stream"


def unfenced(text: str) -> str:
    """Models wrap JSON in ``` often enough that not handling it would be the top cause of failure."""
    value = (text or "").strip()
    fenced = _FENCED.match(value)
    return fenced.group(1).strip() if fenced else value


def classify(error: BaseException) -> tuple[Reason, int | None]:
    """What kind of thing went wrong, in this package's own vocabulary.

    Total by construction: an exception LiteLLM adds in a later version lands on `refused`, which is
    terminal. Falling through on something unrecognised would spend money on a mistake.
    """
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        status = None
    names = {base.__name__ for base in type(error).__mro__}
    for name, reason in _BY_TYPE:
        if name in names:
            return reason, status
    return status_reason(status), status


def status_reason(status: int | None) -> Reason:
    """What a bare HTTP status means, for an adapter that has nothing but the status to go on."""
    if status is not None:
        if status == 429:
            return "rate_limited"
        if status in (401, 403):
            return "authentication"
        if status in (400, 404):
            return "configuration"
        if status >= 500:
            return "unavailable"
    return "refused"


def _raise(row: Row, model: str, error: BaseException) -> None:
    reason, status = classify(error)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, str(error), provider_id=row.id, model=model, status=status) from None


def _transport(row: Row, kind: str) -> dict[str, Any]:
    """What every call to this provider carries: the credential, the endpoint, and no retries."""
    return {"num_retries": 0, "max_retries": 0, **row.transport(kind)}


def _answer(row: Row, model: str, started: float, response: Any, warnings: Sequence[str] = (),
            spent: Spent = Spent()) -> Answer:
    return Answer(
        provider_id=row.id,
        model=model,
        seconds=time.monotonic() - started,
        cost_usd=_cost(response),
        warnings=tuple(warnings),
        attempts=((row.id, model),),
        spent=spent,
    )


def _tokens(response: Any, **counted: int) -> Spent:
    """The tokens LiteLLM's `usage` reports, beside whatever the caller counted itself.

    Read defensively, like `_cost`: a local model or a Cloudflare adapter reports no usage at all,
    and a count that cannot be read is zero rather than a failed call.
    """
    usage = getattr(response, "usage", None)

    def read(name: str) -> int:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0

    return Spent(input_tokens=read("prompt_tokens") or read("input_tokens"),
                 output_tokens=read("completion_tokens") or read("output_tokens"), **counted)


def _cost(response: Any) -> float | None:
    """Cost is provenance, and provenance must not be able to fail a capture.

    `litellm.completion_cost()` raises for a model absent from its price table, which every
    Cloudflare `@cf/…` id and every local model is. `cost_usd` is declared optional precisely so
    that "unknown" is a legal answer.
    """
    hidden = getattr(response, "_hidden_params", None) or {}
    value = hidden.get("response_cost") if isinstance(hidden, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def text(
    prompt: str,
    *,
    row: Row,
    model: str | None = None,
    system: str | None = None,
    as_json: bool = False,
    params: Mapping[str, Any] | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> TextResult:
    """One text call against one provider.

    `model` is the one the chain chose from this provider's list; without it the first is used.

    `params` is what the **caller** wants of the generation — a story asks for a high temperature
    and the translation of that story asks for a low one, which is a fact about the two tasks and
    not about any provider. It is spread *before* `row.params_for("text")` and therefore **loses**
    to it, which is the whole design: a value in a family was put there because a provider refused
    something or behaved badly without it, and a caller's preference must not quietly undo a fact
    somebody discovered the hard way. A family that says nothing about temperature lets the
    caller's through, which is the case this exists for.

    `as_json` asks for a JSON object **without naming its shape**, which is the only thing this
    package asks for and the only thing it will ask for. Where the row says it understands that
    natively, `{"type": "json_object"}` is sent; where the row says `prompt`, asking is the prompt's
    job. Either way the reply is parsed and validated afterwards by the caller, and `parsed` is None
    when it was not readable as JSON — deciding whether that is an error belongs to the caller.

    **There is deliberately no `schema` argument.** Sending a JSON Schema turns generation into
    constrained decoding, and this repository measured what that costs rather than assuming it was
    free: see `AGENTS.md`, "Constrained decoding is not used". A schema guarantees a shape, never a
    meaning, and the validation that catches a wrong meaning has to exist regardless — so the
    guarantee bought nothing that was not already being checked, while the constraint degraded the
    answers and, at realistic input sizes, was rejected by the provider outright.
    """
    model = model or row.models_for("text")[0]
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": prompt})

    request: dict[str, Any] = {
        "model": row.wire_model("text", model),
        "messages": messages,
        "timeout": row.timeout_for("text", timeout),
        # The caller's wish first, the family's facts second: the family wins. See the docstring.
        **(params or {}),
        **row.params_for("text"),
        **_transport(row, "text"),
    }
    if as_json and row.json_mode == "native":
        request["response_format"] = {"type": "json_object"}

    started = time.monotonic()
    try:
        response = completion(**request)
    except Exception as error:  # noqa: BLE001 — classified, then re-raised as one of two types
        _raise(row, model, error)
        raise  # unreachable; _raise always raises

    body = unfenced(str(response.choices[0].message.content or ""))
    parsed = None
    if as_json and body:
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
    return TextResult(text=body, parsed=parsed,
                      answer=_answer(row, model, started, response, spent=_tokens(response)))


def image(
    prompt: str,
    *,
    row: Row,
    model: str | None = None,
    seed: int | None = None,
    size: tuple[int, int] | None = None,
    references: Sequence[bytes] = (),
    timeout: float = TIMEOUT_SECONDS,
) -> ImageResult:
    """One image call against one provider, through LiteLLM or through the family's own adapter.

    `references` are earlier pictures the model should draw from, sent only where the family says
    its image models take them; elsewhere they are dropped with a warning, the rule `speech`
    follows for a `style`. The prompt is the caller's to word so that it says what each one is for.
    """
    model = model or row.models_for("image")[0]
    started = time.monotonic()
    warnings: list[str] = []
    if references:
        allowed = row.image_references()
        if not allowed:
            warnings.append("this provider takes no reference pictures, so none were sent")
            references = ()
        elif len(references) > allowed:
            warnings.append(f"this provider takes {allowed} reference pictures; the rest were not sent")
            references = tuple(references)[-allowed:]
    if references:
        return _image_with_references(prompt, row, model, size, references, timeout, started, warnings)
    if row.route("image").via == "cloudflare":
        from acervo.models import cloudflare

        data, mime = cloudflare.image(row, model, prompt, seed=seed, size=size, timeout=timeout)
        return ImageResult(data=data, mime=mime,
                           answer=_answer(row, model, started, None, warnings, Spent(pictures=1)))

    request: dict[str, Any] = {
        "prompt": prompt,
        "model": row.wire_model("image", model),
        "timeout": row.timeout_for("image", timeout),
        **row.params_for("image"),
        **_transport(row, "image"),
    }
    # Asking for bytes rather than a URL is a per-provider fact and the family states it: OpenAI
    # answers with a URL unless told otherwise, and Vertex refuses the parameter outright
    # ("Setting `response_format` is not supported by vertex_ai"). It defaults to the answer that
    # needs no second fetch, so a family only speaks up to say it cannot take the parameter.
    image_capabilities = row.image_capabilities()
    if image_capabilities.get("responseFormat", "b64_json"):
        request["response_format"] = image_capabilities.get("responseFormat", "b64_json")
    # Size and seed are declared, not assumed, for the same reason `speech` declares `style`: what
    # a provider does with a parameter it does not support is not uniform. Vertex drops both
    # silently — `size` becomes an aspect ratio and nothing else, and its transformer never reads
    # `seed` at all — while OpenAI turns `seed` into an `extra_body` field the Images API rejects.
    # Sending anyway would mean a recorded seed that never reproduced anything, and a 400.
    if size is not None:
        if image_capabilities.get("size", "native") == "native":
            request["size"] = f"{size[0]}x{size[1]}"
        else:
            # Still sent: for Vertex it is the only channel that carries the aspect ratio, and the
            # resolution rides in the family's `imageConfig` parameter instead.
            request["size"] = f"{size[0]}x{size[1]}"
            warnings.append(f"this provider chooses its own resolution, not {size[0]}x{size[1]}")
    if seed is not None:
        if image_capabilities.get("seed", "native") == "native":
            request["seed"] = seed
        else:
            warnings.append("seed is not supported by this provider, so this is not reproducible")
    try:
        response = image_generation(**request)
    except Exception as error:  # noqa: BLE001
        _raise(row, model, error)
        raise

    # An answer with no picture in it is said as one, not left to fail as an index out of range:
    # a model that declines a prompt answers successfully with nothing to show.
    encoded = response.data[0].b64_json if getattr(response, "data", None) else None
    if not encoded:
        raise ProviderRefused(
            "refused", "the provider returned no image data", provider_id=row.id, model=model
        )
    return ImageResult(
        data=base64.b64decode(encoded),
        mime="image/png",
        answer=_answer(row, model, started, response, warnings, _tokens(response, pictures=1)),
    )


def _image_with_references(prompt: str, row: Row, model: str, size: tuple[int, int] | None,
                           references: Sequence[bytes], timeout: float, started: float,
                           warnings: list[str]) -> ImageResult:
    """The same picture asked for over the chat route, where a message can carry images.

    LiteLLM's `image_generation` takes no image for Vertex Gemini, and `completion` with
    `modalities` does. The family's image parameters travel unchanged — `imageConfig` included, which on
    this route is copied into `generationConfig` — with the aspect ratio added from `size`, because
    here there is no `size` parameter to carry it.
    """
    params = row.params_for("image")
    if size is not None:
        divisor = math.gcd(size[0], size[1]) or 1
        params["imageConfig"] = {**(params.get("imageConfig") or {}),
                                 "aspectRatio": f"{size[0] // divisor}:{size[1] // divisor}"}
        warnings.append(f"this provider chooses its own resolution, not {size[0]}x{size[1]}")
    content: list[dict[str, Any]] = [
        {"type": "image_url",
         "image_url": {"url": f"data:{_picture_mime(data)};base64,{base64.b64encode(data).decode()}"}}
        for data in references
    ]
    content.append({"type": "text", "text": prompt})
    try:
        response = completion(
            model=row.wire_model("image", model),
            messages=[{"role": "user", "content": content}],
            modalities=["image", "text"],
            timeout=row.timeout_for("image", timeout),
            **params,
            **_transport(row, "image"),
        )
    except Exception as error:  # noqa: BLE001
        _raise(row, model, error)
        raise
    message = response.choices[0].message
    images = getattr(message, "images", None) or []
    url = ((images[0] or {}).get("image_url") or {}).get("url", "") if images else ""
    if "," not in url:
        said = (getattr(message, "content", None) or "").strip()[:200]
        raise ProviderRefused(
            "refused", f"the provider returned no image{': ' + said if said else ''}",
            provider_id=row.id, model=model,
        )
    header, encoded = url.split(",", 1)
    mime = header.removeprefix("data:").split(";", 1)[0] or "image/png"
    return ImageResult(
        data=base64.b64decode(encoded), mime=mime,
        answer=_answer(row, model, started, response, warnings, _tokens(response, pictures=1)),
    )


def _picture_mime(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def _audio_adapter(name: str):
    """The speech adapters, by the route a family gives `audio`. None of them is LiteLLM's: reached
    through LiteLLM a Gemini voice drops its direction before the request is built."""
    if name == "cloudflare":
        from acervo.models import cloudflare

        return cloudflare.speech
    if name == "google-tts":
        from acervo.models import google_tts

        return google_tts.speech
    if name == "gemini-tts":
        from acervo.models import gemini_tts

        return gemini_tts.speech
    raise ProviderRefused("configuration", f"no audio adapter named {name!r}")


def speech(
    words: str,
    *,
    row: Row,
    language: str,
    model: str | None = None,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> AudioResult:
    """One speech call against one provider, in a BCP-47 `language`.

    `voice` is the caller's choice, and without one the model's first voice for the language is
    used. `style` is a free-text delivery direction, carried only where the *model* takes one —
    elsewhere it is dropped with a warning rather than sent to a voice that would read it aloud. The
    answer names the voice that actually spoke.
    """
    model = model or row.models_for("audio")[0]
    # Voice names do not carry across providers: Google's per-language voices carry the language in
    # the name, and a Gemini voice is named once. The provider says which.
    voice = voice or next(iter(row.voices_for(model, language)), None)
    warnings: list[str] = []
    if style and not row.takes_direction(model):
        warnings.append("style is not supported by this provider")
        style = None
    timeout = row.timeout_for("audio", timeout)
    started = time.monotonic()
    data, _declared = _audio_adapter(row.route("audio").via)(
        row, model, words, language=language, voice=voice, style=style, timeout=timeout
    )
    return AudioResult(
        data=data, mime=audio_mime(data),
        answer=_answer(row, model, started, None, warnings, Spent(characters=len(words))),
        voice=voice,
    )


OCR_TIMEOUT_SECONDS = 15
"""Reading a photo with somebody holding the phone. Measured: 0.5–1.2 s from Vision at 2048 px."""


def _ocr_adapter(name: str):
    """The OCR engines, by the route a family gives `ocr`. None of them is in LiteLLM."""
    if name == "google-vision":
        from acervo.models import google_vision

        return google_vision.read
    raise ProviderRefused("configuration", f"no ocr adapter named {name!r}")


def ocr(
    data: bytes,
    *,
    row: Row,
    model: str | None = None,
    language_hints: Sequence[str] = (),
    timeout: float = OCR_TIMEOUT_SECONDS,
) -> OcrResult:
    """The words on one image, with their outlines, from one row.

    `language_hints` are BCP-47 tags the text is likely to be in — the owner's vocabularies — which an
    engine may use to choose a script and never has to obey.
    """
    model = model or row.models_for("ocr")[0]
    started = time.monotonic()
    words, width, height, language = _ocr_adapter(row.route("ocr").via)(
        row, model, data, language_hints=language_hints, timeout=row.timeout_for("ocr", timeout)
    )
    return OcrResult(
        words=tuple(words), width=width, height=height, language=language,
        answer=_answer(row, model, started, None, spent=Spent(photos=1)),
    )
