"""The providers' keys: one file beside the database, never in it.

`providers.secrets.json` holds, per provider id, its key or its uploaded Google credentials file:
`{"gemini-api": {"key": "…"}, "google-cloud": {"credentials": {…}}}`. Keeping it out of SQLite means
a database backup, the copy a deploy takes before a transition, and an export never carry a key. A
lost file costs typing the keys again, and keys can be made again; that is the right way round.

The file is mode 600, owned by the server's user, and written whole: a temporary file beside it,
then a rename, so a crash leaves the old file or the new one and never half of either. It is read on
every call and never cached, like the owner's orders, so a key replaced in Settings is the one the
next call uses.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping

from acervo.settings import Settings

FILE_NAME = "providers.secrets.json"

_lock = threading.Lock()


def path(settings: Settings) -> Path:
    return Path(settings.database_path).parent / FILE_NAME


def read(settings: Settings) -> dict[str, dict[str, Any]]:
    """Every provider's secret, by id. An absent file is no secrets, which is a server with none."""
    try:
        document = json.loads(path(settings).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {str(key): dict(value) for key, value in document.items() if isinstance(value, dict)} \
        if isinstance(document, dict) else {}


def put(settings: Settings, identifier: str, secret: Mapping[str, Any] | None) -> None:
    """Replace one provider's secret, or remove it with None."""
    with _lock:
        document = read(settings)
        if secret:
            document[identifier] = dict(secret)
        else:
            document.pop(identifier, None)
        _write(path(settings), document)


def _write(target: Path, document: Mapping[str, Any]) -> None:
    """Write beside the file and rename over it. The temporary name is fixed and truncated on every
    write, under the lock, so a write that failed half-way leaves nothing behind but a file the next
    write replaces."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.writing")
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(handle, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=1, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
