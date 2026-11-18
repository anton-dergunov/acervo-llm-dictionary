"""The installed dictionaries' articles for one word, for the server's own checks.

The interface reads dictionaries itself (`web/src/dictionary.ts`); the server reads them only to judge
what a model wrote (`services/capture/dictionary_check.py`). Only `fields`-tier artifacts are read,
since an `html` payload carries no field to compare, and only those whose `sourceLang` is the word's
language. A dictionary is matched by the language's primary subtag, so `es-AR` is checked against a
Spanish dictionary and `zh-Hans` against a Chinese one.

Nothing here can fail a caller. With no dictionary installed, an unreadable one, or no entry for the
word, the answer is empty and so the check says nothing. An artifact that cannot be opened writes
one activity line naming it, until it changes on disk.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acervo import activity
from acervo.dictionaries.container import Artifact
from acervo.services.dictionaries.listing import installed


@dataclass(frozen=True)
class Found:
    """What one dictionary says about the word: its id, the key it was found under, and its articles."""

    dictionary_id: str
    key: str
    articles: list[dict[str, Any]]


_lock = threading.Lock()
# id -> (the metadata file's mtime, the artifact, or None when it would not open)
_open: dict[str, tuple[float, Artifact | None]] = {}


def primary(language: str) -> str:
    return language.split("-", 1)[0].lower()


def _artifact(directory: Path, dictionary_id: str) -> Artifact | None:
    metadata = directory / f"{dictionary_id}.json"
    try:
        stamp = metadata.stat().st_mtime
    except OSError:
        return None
    with _lock:
        cached = _open.get(dictionary_id)
        if cached and cached[0] == stamp:
            return cached[1]
        try:
            artifact: Artifact | None = Artifact(directory / f"{dictionary_id}.dict",
                                                 directory / f"{dictionary_id}.idx")
        except (OSError, ValueError, IndexError) as error:
            activity.note("dictionary_unreadable", failed=True, dictionary=dictionary_id,
                          reason=f"{type(error).__name__}: {error}")
            artifact = None
        _open[dictionary_id] = (stamp, artifact)
        return artifact


def articles_for(directory: Path, language: str, words: list[str]) -> list[Found]:
    """Every installed dictionary's articles for the first of `words` it holds, tried in order."""
    wanted = primary(language)
    found: list[Found] = []
    for metadata in installed(Path(directory)):
        if metadata.get("tier") != "fields" or primary(str(metadata.get("sourceLang") or "")) != wanted:
            continue
        artifact = _artifact(Path(directory), str(metadata["id"]))
        if artifact is None:
            continue
        for word in dict.fromkeys(word for word in words if word):
            try:
                payload = artifact.payload(word)
                articles = json.loads(payload) if payload else None
            except (ValueError, IndexError) as error:
                activity.note("dictionary_unreadable", failed=True, dictionary=metadata["id"], word=word,
                              reason=f"{type(error).__name__}: {error}")
                break
            if articles:
                found.append(Found(str(metadata["id"]), word,
                                   [item for item in articles if isinstance(item, dict)]))
                break
    return found
