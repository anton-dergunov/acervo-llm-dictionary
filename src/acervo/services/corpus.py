"""Acervo's binding to the corpus's update route: settings in, an operation to follow out.

The corpus is deployment-wide and its operator token is deployment configuration, so this is the
one place that token is attached to an update request. What the corpus says goes through
`clips/corpus.py`, the only module that reads its wire shape.
"""

from __future__ import annotations

from acervo.clips.corpus import Corpus, CorpusError, Operation
from acervo import trace
from acervo.errors import ApiError
from acervo.services.clips import CORPUS_REFUSALS
from acervo.settings import Settings


def configured(settings: Settings) -> bool:
    return bool(settings.speech_url)


def _corpus(settings: Settings) -> Corpus:
    if not settings.speech_url:
        raise ApiError(
            503, "corpus_unconfigured",
            "This Acervo server has no spoken-usage corpus configured, so it cannot be updated.",
        )
    if not settings.speech_operator_token:
        raise ApiError(
            503, "corpus_unmanaged",
            "This Acervo server holds no operator token for the spoken-usage corpus, "
            "so it cannot ask for an update.",
        )
    return Corpus(settings.speech_url, operator_token=settings.speech_operator_token,
                  request_id=trace.current())


def _refusal(error: CorpusError) -> ApiError:
    status, code, message = CORPUS_REFUSALS.get(error.reason, CORPUS_REFUSALS["refused"])
    return ApiError(status, code, message.replace(", so nothing was added", ""))


def start_update(settings: Settings) -> Operation:
    """Start an update, or join the one the corpus is already running."""
    try:
        return _corpus(settings).start_update()
    except CorpusError as error:
        raise _refusal(error) from None


def operation(settings: Settings, operation_id: str) -> Operation:
    try:
        return _corpus(settings).operation(operation_id)
    except CorpusError as error:
        raise _refusal(error) from None
