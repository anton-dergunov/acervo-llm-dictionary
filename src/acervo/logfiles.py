"""Opening one of Acervo's log files, the one way it is done.

Every log is a rotating text file beside the database, and they are opened identically on purpose:

- **idempotent**, because the application and the runner are built more than once in the tests and a
  second handler would double every line;
- **its own file and nothing else** — the logger stops propagating, so the lines do not also land in
  the container's stdout beside the request log, which is the noise a file exists to replace;
- **rotating**, because an unbounded file on the same volume as the database is a way to lose the
  database;
- **stamped with the request id** (`trace.py`), appended as ` rid=…` after whatever the emitter
  wrote, so the emitter does not have to know one exists.

It raises `OSError` when the file cannot be opened and leaves the sentence to the caller, who knows
which log it was. Every caller warns and carries on: a server that cannot write its log should still
do its work.

A leaf. It takes a path and two numbers rather than `Settings`, so the package that reads the
environment stays the only one that does.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from acervo import trace

# The prefix every line of every log carries, and therefore what `activity.entries` reads back.
PREFIX = "%(asctime)s %(levelname)s %(message)s"


class _Stamped(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        rid = getattr(record, "rid", "")
        return f"{line} rid={rid}" if rid else line


def open_rotating(logger_name: str, path: Path, max_bytes: int, keep: int, *,
                  stamp: bool = True) -> None:
    """Point `logger_name` at `path`. `stamp=False` for a log whose lines already name their id."""
    logger = logging.getLogger(logger_name)
    if any(getattr(handler, "acervo_log_file", False) for handler in logger.handlers):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=keep, encoding="utf-8")
    handler.acervo_log_file = True   # type: ignore[attr-defined]
    if stamp:
        handler.addFilter(trace.Stamp())
        handler.setFormatter(_Stamped(PREFIX))
    else:
        handler.setFormatter(logging.Formatter(PREFIX))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
