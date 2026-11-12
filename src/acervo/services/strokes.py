"""How Chinese characters are written: the pinned stroke data, read by character.

Reference data, consulted and never replicated — like a dictionary, and for the same reason it is
not in the database: it is somebody else's, it is the same for every owner, and it is rebuilt from a
pin rather than backed up (`docs/features/writing.md`). One file per character, as the dataset ships
it, so a lookup is a file read and the directory is exactly what `deploy/acervo/strokes/fetch.py`
wrote; nothing here understands the strokes, which are the interface's to draw and check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MANIFEST = "dataset.json"
# Below this every code point is Latin, Greek, punctuation and the like: nothing with strokes in the
# dataset, and nothing a file name should be built from.
FIRST_HAN = 0x2E80


def dataset(directory: Path) -> str | None:
    """The dataset the directory holds, as `package@version`, or None when it holds none."""
    try:
        manifest = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = manifest.get("dataset")
    return name if isinstance(name, str) and name else None


def is_han(character: str) -> bool:
    return len(character) == 1 and ord(character) >= FIRST_HAN


def read(directory: Path, characters: list[str]) -> tuple[dict[str, Any], list[str]]:
    """The stroke data for each character the dataset has, and the characters it has not.

    Only `strokes`, `medians` and `radStrokes` are passed on: what the interface draws with, and
    nothing a later version of the dataset might add that it would then come to rely on unpinned.
    """
    found: dict[str, Any] = {}
    missing: list[str] = []
    for character in characters:
        try:
            raw = json.loads((directory / f"{character}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            missing.append(character)
            continue
        entry = {"strokes": raw.get("strokes"), "medians": raw.get("medians")}
        if raw.get("radStrokes"):
            entry["radStrokes"] = raw["radStrokes"]
        found[character] = entry
    return found, missing
