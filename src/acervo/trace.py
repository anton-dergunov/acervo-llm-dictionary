"""The one id that joins Acervo's logs to each other and to its companions'.

A loop render spends its minutes in the generator's container and calls home seventy-odd times; a
capture walks a chain of providers; a clip search asks the corpus. Each of those used to leave lines
in two or three files that shared nothing but a timestamp. This is the identifier they now share.

It is set in three places and read in one:

- a request is given one on the way in — its own `X-Request-ID` if it sent a well-formed one,
  otherwise a new one — and the response says which;
- a job *is* one: the runner holds the job's id for as long as the job runs, so every model call a
  job makes is filed under the job;
- a call home adopts the one that travelled in its render token, which is how a take the generator
  asks for is filed under the job that asked for the render.

And it is read where a log file is opened (`logfiles.py`), never where a line is emitted — the
provider package may not import this, and should not need to.

A leaf: it imports nothing of Acervo's, so anything may hold it.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# What a companion service is sent, and what a response carries back.
HEADER = "X-Request-ID"

# The shape of every other id in Acervo, so a job's id is a request id without translation and
# `admin log` matches one pattern.
_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_SHAPE = re.compile(r"^[a-z0-9]{15}$")

_current: ContextVar[str] = ContextVar("acervo_request_id", default="")


def mint() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(15))


def well_formed(value: object) -> bool:
    return isinstance(value, str) and bool(_SHAPE.match(value))


def current() -> str:
    """The id this work is filed under, or empty when nothing set one — a script, a test."""
    return _current.get()


def adopt(value: object) -> str:
    """Take up an id somebody else minted, if it is one. Anything else is ignored, not repaired:
    a header is a stranger's text, and it is about to be written into a log."""
    if well_formed(value):
        _current.set(value)  # type: ignore[arg-type]
    return _current.get()


def begin(supplied: object = None) -> str:
    """The id for a piece of work that is starting: the one supplied, else a new one."""
    chosen = supplied if well_formed(supplied) else mint()
    _current.set(chosen)  # type: ignore[arg-type]
    return chosen  # type: ignore[return-value]


@contextmanager
def scope(value: str) -> Iterator[str]:
    """Hold `value` for the body and put back what was there. For work that shares a thread with
    whatever comes next — the runner takes one job after another on one."""
    token = _current.set(value)
    try:
        yield value
    finally:
        _current.reset(token)


class Stamp(logging.Filter):
    """Puts the current id on a record as `rid`, in the thread that emitted it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.rid = _current.get()
        return True
