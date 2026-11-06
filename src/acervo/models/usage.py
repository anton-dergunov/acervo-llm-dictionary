"""Every attempt at a model, handed to whoever counts them.

Usage — Settings ▸ Providers ▸ Usage — answers how many calls each model took, how many failed and
why, and what they used up against a free allowance. **Every attempt is counted, not only the one
that answered**, because a 429 spends a free request too; so the report is made where every attempt
is seen, in `chain.walk`, one per pair asked.

**The package emits; it does not count.** Counting means a table, and `acervo.models` may import
nothing of Acervo's (`test_layering.py`). So this is the journal's rule again: the package reports an
`Attempt` to the sinks it has been handed and stops, and the binding layer (`services/usage.py`)
attaches the one that writes the counters. A laptop tool attaches none, and its calls are counted by
nobody, which is right — they are not the server's.

A sink that fails must never fail a model call: the answer was had, and losing a count is the
smaller loss. The binding layer's sink writes its own failure down; one that raises anyway is caught
here and logged on the call log's logger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from acervo.models.journal import LOGGER
from acervo.models.results import Spent

logger = logging.getLogger(LOGGER)


@dataclass(frozen=True)
class Attempt:
    """One pair asked once, and what came of it."""

    kind: str          # what the provider offers this model as: text, image, audio or ocr
    provider: str
    model: str
    caller: str        # the job, as the call log names it
    reason: str | None  # None when it answered; otherwise the `Reason` it failed for
    seconds: float
    detail: str = ""   # the failure's sentence, redacted where the error was made
    spent: Spent = Spent()  # what an answer used up; a failure carries none
    cost_usd: float | None = None

    @property
    def answered(self) -> bool:
        return self.reason is None


Sink = Callable[[Attempt], None]

_sinks: list[Sink] = []


def attach(sink: Sink) -> None:
    """Hand the package a sink. Idempotent, because an application is built more than once in tests."""
    if sink not in _sinks:
        _sinks.append(sink)


def detach(sink: Sink) -> None:
    if sink in _sinks:
        _sinks.remove(sink)


def report(attempt: Attempt) -> None:
    for sink in tuple(_sinks):
        try:
            sink(attempt)
        except Exception as error:  # noqa: BLE001 — a count must never fail the call it counts
            logger.warning("usage %s:%s not counted — %s", attempt.provider, attempt.model, error)
