"""Take the credentials back out of a provider's error text.

Providers routinely echo the request back in an error — the URL, the headers, sometimes the key
itself — and this repository is public. Every `detail` on every `ProviderError` goes through here at
construction, so there is no path that reaches a log or a response without it.

It redacts **values**. A provider is built with its credential, and building it tells this module
every value that credential could leak (`Provider.__post_init__`), so no list of names has to be kept
in step with the providers that exist. A replaced key stays remembered: it was a secret yesterday, and
an old error quoting it is no less a leak for the key having been rotated since.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterable

LIMIT = 2000
REDACTED = "«redacted»"

# A short value is a word, not a secret, and cutting a four-letter word out of every message that
# used it reads as a bug rather than as discretion.
MINIMUM = 8

_lock = threading.Lock()
_known: set[str] = set()


def remember(values: Iterable[str]) -> None:
    """Values that must never appear in an error. Called whenever a provider is built."""
    fresh = {value.strip() for value in values if value and len(value.strip()) >= MINIMUM}
    if fresh - _known:
        with _lock:
            _known.update(fresh)


def redactor(values: Iterable[str] = ()) -> Callable[[str], str]:
    """A redactor over every remembered value and `values`. Longest first, so a value that contains
    another is not left half-replaced."""
    with _lock:
        secrets = sorted(_known | {v for v in values if v and len(v) >= MINIMUM}, key=len, reverse=True)

    def redact(text: str) -> str:
        cleaned = text or ""
        for secret in secrets:
            cleaned = cleaned.replace(secret, REDACTED)
        return cleaned[:LIMIT]

    return redact


def redact(text: str) -> str:
    return redactor()(text)
