"""The one way to call a model from Python: the providers the owner added, and four functions.

Four unrelated mechanisms reached a model before this package existed, and the layer that looked
like the abstraction was dead code. What made it dead is worth stating, because it is the shape this
package is built to avoid: `ImageProvider.synthesize(text, path) -> None` had nowhere to put the
cost or the model that answered, so the pipeline that needed both bypassed it. Every function here
returns an `Answer` alongside its payload.

A provider is a row the owner added — one account, one credential, its models — and its family
(`families.py`) is the code that speaks to it: the LiteLLM route, the base URL, whether JSON mode is
native, and every quirk found the hard way. There is no per-provider code except the adapters
LiteLLM leaves necessary: `cloudflare.py` for Cloudflare images and audio, and `google_tts.py` and
`google_vision.py` for Google's speech and OCR APIs, which share `google_auth.py`. What a provider
offers is asked of it (`listing.py`).

**This package stands alone.** It imports no Acervo settings, graph, database or wire vocabulary,
and `tests/unit/server/test_layering.py` enforces that. It takes providers and a chain and nothing
else, which is what lets a second project use it and what keeps `acervo.models.pacing` importable in
an image that does not carry LiteLLM. `acervo.services.models` is the separate, Acervo-specific
binding layer that reads the providers from the server's store and speaks the `llm_*` error codes;
a laptop tool reads them from `providers.local.json` (`local.py`).
"""

from __future__ import annotations

from acervo.models.providers import Provider, Providers
from acervo.models.errors import (
    ChainExhausted,
    ProviderError,
    ProviderRefused,
    ProviderUnavailable,
    Reason,
    RETRYABLE,
    TERMINAL,
)
from acervo.models import journal
from acervo.models.results import Answer, AudioResult, ImageResult, OcrResult, OcrWord, TextResult

__all__ = [
    "Answer",
    "journal",
    "AudioResult",
    "ChainExhausted",
    "ImageResult",
    "OcrResult",
    "OcrWord",
    "ProviderError",
    "ProviderRefused",
    "ProviderUnavailable",
    "RETRYABLE",
    "Reason",
    "Provider",
    "Providers",
    "TERMINAL",
    "TextResult",
    "image",
    "ocr",
    "speech",
    "text",
]


def __getattr__(name: str):
    """`text`, `image`, `speech` and `ocr` arrive only when they are asked for.

    Importing them eagerly would import `call.py`, and a reader of this module would then need
    LiteLLM to exist. `scripts/ingest_vocabulary_file.py` imports `acervo.models.pacing` and the
    worker image carries no LiteLLM, so that is not a hypothetical.
    """
    if name in ("text", "image", "speech", "ocr"):
        from acervo.models import call

        return getattr(call, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
