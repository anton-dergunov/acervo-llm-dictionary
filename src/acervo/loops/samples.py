"""The style samples: one short render of each kind of music, so a style can be heard before it is
chosen.

A style is a direction to a generator, not a recording (`docs/features/loops.md` §2.18), so what is
played is one bed it composes at a fixed seed: one point in the family's range of tempi and keys,
enough to hear its instruments and its feel. It is a **cache, not a record**: nothing references a
sample, nothing replicates it, and it is rebuilt from nothing by asking again. It lives beside the
database for the take cache's reasons and is emptied by hand (`admin samples clear`).

**Two names, for two jobs.** A sample is *looked up* by what it records — the family, the seed, the
length, the palette, and the engine and bundle that render it — so a new engine or a new bundle
misses and renders afresh, with nothing to invalidate. It is *served* under a name carrying a digest
of its own bytes, `<key>/<family>-<digest>.mp3`, which is the rule every client media cache lives by:
a device keeps a sample under that name for as long as it likes and is never wrong about it.

This module stands alone, like `pronunciation/takes.py`: no settings, no errors, no graph.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

EXTENSION = "mp3"
MIME = "audio/mpeg"
# What a served name may look like: a key directory and one file in it. Checked before any path is
# built from one, so a name a client sends can never reach outside the cache.
NAME = re.compile(r"^[0-9a-f]{32}/[a-z0-9-]{1,120}-[0-9a-f]{8}\.mp3$")


def key(*, family: str, seed: int, seconds: float, palette: str, engine_version: str,
        bundle_version: str) -> str:
    """What makes two samples the same recording. Everything that changes the audio."""
    parts = (family, str(int(seed)), f"{float(seconds):g}", palette, engine_version, bundle_version)
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def find(root: Path, digest: str) -> str | None:
    """The served name of the sample under this key, or nothing."""
    folder = root / digest
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob(f"*.{EXTENSION}")):
        name = f"{digest}/{path.name}"
        if NAME.match(name):
            return name
    return None


def store(root: Path, digest: str, family: str, data: bytes) -> str:
    """Write one sample, atomically, and return the name it is served under."""
    name = f"{digest}/{family}-{hashlib.sha256(data).hexdigest()[:8]}.{EXTENSION}"
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.part")
    partial.write_bytes(data)
    os.replace(partial, path)
    return name


def path_of(root: Path, name: str) -> Path | None:
    """The file behind a served name, or nothing for a name that is not one."""
    if not NAME.match(name):
        return None
    path = root / name
    return path if path.is_file() else None


def usage(root: Path) -> tuple[int, int]:
    """How many samples are kept and what they weigh."""
    if not root.is_dir():
        return 0, 0
    kept = [path for path in root.rglob(f"*.{EXTENSION}") if path.is_file()]
    return len(kept), sum(path.stat().st_size for path in kept)


def clear(root: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Empty the cache. Returns how many samples went and how many bytes with them."""
    count, size = usage(root)
    if not dry_run and root.is_dir():
        shutil.rmtree(root)
    return count, size
