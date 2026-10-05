"""What the server did that was neither a model call nor a job — the third of Acervo's logs.

`acervo.models.journal` records every model call and `acervo.work.journal` every job. Between them
was everything a *request* does: a write refused because another device got there first, a session
that stopped being accepted, a picture's file removed, the server coming up on a new version. Each
left an access-log status code and nothing else — and the sentence the owner was shown, which is the
one thing that says why, was kept nowhere.

Shaped like the other two, deliberately:

- `key=value` pairs, so `grep code=stale_record activity.log` is a question with an answer;
- this module **emits and never configures** — `api/app.py` points it at a file (`logfiles.py`), and
  a deployment that installs none loses the lines and nothing else;
- every line has a reader in mind. A refusal is here because somebody was told no; a read that
  merely came back empty is not.

It also owns the rendering the job log shares, and the reader `admin log` uses to put the three
files back into one account of what happened.

A leaf: it imports nothing of Acervo's, so a repository, a service and a route can all write here.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

# Its own logger, so a file for this captures nothing else `acervo` might log.
LOGGER = "acervo.activity"
logger = logging.getLogger(LOGGER)

# Long enough for a provider's own sentence, short enough that one bad message cannot fill the file.
EXCERPT = 400


def excerpt(value: object) -> str:
    """A bounded, single-line view of a value."""
    text = " ".join(str(value).split())
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1] + "…"


def fields(pairs: Mapping[str, Any]) -> str:
    """`name=value` pairs, in order. Empty ones are left out; text that would break a `grep` — a
    space, a quote, an equals sign — is quoted and bounded."""
    parts = []
    for name, value in pairs.items():
        if value is None or value == "":
            continue
        if isinstance(value, float):
            rendered = f"{value:.2f}"
        elif isinstance(value, str) and (not value.isprintable() or any(c in value for c in ' "=')):
            rendered = json.dumps(excerpt(value), ensure_ascii=False)
        else:
            rendered = str(value)
        parts.append(f"{name}={rendered}")
    return " ".join(parts)


def note(event: str, failed: bool = False, **pairs: Any) -> None:
    """One line: what happened, then what about it. `event` is a fixed phrase — `media removed`,
    `server start` — so it can be searched for; everything that varies is a field."""
    (logger.warning if failed else logger.info)("%s %s", event, fields(pairs))


def refused(status: int, code: str, message: str, **pairs: Any) -> None:
    """A request that was told no, with the sentence it was told.

    A warning below 500 and an error from there up, so `admin log --failed` shows both and a `grep
    ERROR` shows only the ones that were the server's doing.
    """
    (logger.error if status >= 500 else logger.warning)(
        "refused %s", fields({"status": status, "code": code, **pairs, "message": message}))


# ── reading the three logs back ─────────────────────────────────────────────
#
# Beside the writer, for the reason `models.journal.summarise` is beside its own: a format described
# in two places drifts. All three files share one prefix (`logfiles.PREFIX`), which is the only thing
# this reads.

_LINE = re.compile(r"^(?P<when>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) (?P<level>[A-Z]+) ")


def rotated(path: Path) -> list[Path]:
    """A log and its rotations, oldest first, so a reading is not silently one of the last hours."""
    backups = sorted(path.parent.glob(f"{path.name}.*"), reverse=True)
    return [*backups, *([path] if path.exists() else [])]


def entries(sources: Mapping[str, Path | None]) -> list[tuple[str, str, str, str]]:
    """Every entry of every named log as `(when, level, source, text)`, in the order it happened.

    A line that does not start with a timestamp belongs to the entry above it — a provider's message
    that kept its own line break — and is folded back into that entry rather than sorted adrift.
    """
    found: list[tuple[str, str, str, str]] = []
    for source, path in sources.items():
        if not path:
            continue
        for file in rotated(path):
            for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
                match = _LINE.match(line)
                if match:
                    found.append((match["when"], match["level"], source, line[match.end():]))
                elif found and found[-1][2] == source:
                    when, level, _, text = found[-1]
                    found[-1] = (when, level, source, f"{text} {line.strip()}")
    # Stable, so two lines of one file in the same millisecond keep the order they were written in.
    return sorted(found, key=lambda entry: entry[0])


def about(text: str, identifier: str) -> bool:
    """Whether an entry is filed under `identifier`: as the request it belongs to, the job it is,
    or the operation a companion service ran for it."""
    return any(f"{name}={identifier}" in text.split() for name in ("rid", "id", "operationId"))


def select(found: Iterable[tuple[str, str, str, str]], *, identifier: str = "",
           failed: bool = False) -> list[tuple[str, str, str, str]]:
    return [
        entry for entry in found
        if (not identifier or about(entry[3], identifier))
        and (not failed or entry[1] in ("WARNING", "ERROR", "CRITICAL"))
    ]
