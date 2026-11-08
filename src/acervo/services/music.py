"""Music on its own: the minute a kept bed is heard by, and each style's sample.

Both are the generator's `POST /music` — a bed with nothing spoken over it — and both are made ahead
of the tap rather than on it, because the generator renders one thing at a time and a tap made while
a loop is being rendered would wait minutes behind it (`docs/features/loops.md` §2.18).

- **A kept bed's music is media.** The `music` job renders a minute of it once, writes the file under
  a name carrying a digest of its bytes, and gives the `beds` row its `audioRef`, as a loop's track
  is written: the file first, then the row, through `graph.merge_graph`. A device keeps it like any
  other track and it plays offline. The bed is replayed from its family and seed, and the render is
  stored only if it *is* that bed: an engine that has moved on since it was kept, or a fingerprint
  that comes back different, is refused by name rather than kept as different music under the old
  name.
- **A style's sample is a cache** (`acervo.loops.samples`), rendered once per engine and bundle by the
  `music.samples` job a deploy sets off, and on the spot for a tap that gets there first.

Every operation is read → render (no transaction) → write, for `services/loops.py`'s reason.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any

from acervo.domain.ids import now_instant
from acervo.errors import ApiError
from acervo.loops import samples
from acervo.loops.client import LoopError, Music, Operation, Schema
from acervo.repository import graph
from acervo.services import loops
from acervo.services import media as media_files
from acervo.settings import Settings

# What a kept bed is heard for: long enough to listen to, short enough to be a sample of a loop's
# music rather than a second loop. The generator rounds it to whole bars.
BED_SECONDS = 60.0
# A style's sample: a couple of phrases at the slowest tempo, and its fade out.
SAMPLE_SECONDS = 24.0
# One fixed point in each family's range of tempi and keys, so every device hears the same sample
# and a new one is made only when the engine or the bundle changes.
SAMPLE_SEED = 1
# The palette every loop is rendered with (`LoopService.start`), so a kept bed replays as its loop
# had it.
PALETTE = "hybrid"

# How long a tap waits for a sample the warming job has not reached yet, and how often it looks.
SAMPLE_WAIT_SECONDS = 90.0
SAMPLE_POLL_SECONDS = 1.0


# ── a kept bed ──────────────────────────────────────────────────────────────


def unheard(owner: str, bed_id: str) -> dict[str, Any] | None:
    """The kept bed, if it is still kept and has no music of its own yet; else nothing to do."""
    bed = graph.owned_records(owner, "beds", [bed_id]).get(bed_id)
    if bed is None or bed.get("deleted") or bed.get("audioRef"):
        return None
    return bed


def start_bed(settings: Settings, bed: dict[str, Any]) -> Operation:
    """Ask for a minute of this bed, after checking the engine would replay it."""
    found = _schema(settings)
    kept_under = (bed.get("engineVersion") or "").strip()
    if kept_under and kept_under != found.engine_version:
        raise ApiError(
            409, "music_engine_changed",
            f"This music was kept under LexiBeat engine {kept_under}, and the server now runs "
            f"{found.engine_version}, which would compose something else from the same seed.",
            noted={"bed": bed["id"], "kept": kept_under, "running": found.engine_version})
    return _start(settings, bed["styleId"], int(bed.get("seed") or 0), BED_SECONDS)


def follow(settings: Settings, operation_id: str) -> Operation:
    try:
        return loops.service(settings).operation(operation_id, music=True)
    except LoopError as error:
        raise loops.refusal(error) from None


def store_bed(settings: Settings, owner: str, device: str, bed_id: str,
              rendered: Music) -> dict[str, Any] | None:
    """Fetch the minute, write the file, then the row. None when the bed has gone meanwhile."""
    bed = unheard(owner, bed_id)
    if bed is None:
        return None
    kept = (bed.get("bedFingerprint") or "").strip()
    if kept and rendered.bed_fingerprint != kept:
        raise ApiError(
            502, "music_differs",
            "LexiBeat composed different music from this bed's family and seed, so it was not "
            "kept under its name.",
            noted={"bed": bed_id, "kept": kept, "rendered": rendered.bed_fingerprint})
    audio, mime = _track(settings, rendered)

    digest = hashlib.sha256(audio).hexdigest()[:8]
    reference = f"music/{bed_id}-{digest}.mp3"
    destination = Path(settings.media_path) / reference
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(audio)
    os.replace(partial, destination)

    at = now_instant()
    try:
        graph.merge_graph(owner, device, {"beds": [{
            **bed, "audioRef": reference, "audioMime": mime or samples.MIME,
            "durationSeconds": rendered.duration_seconds, "editedAt": at, "editedBy": device,
        }]}, enqueue=None)
    except Exception:
        media_files.remove(settings.media_path, reference, "rollback")
        raise
    return graph.owned_records(owner, "beds", [bed_id])[bed_id]


def remove_bed(settings: Settings, owner: str, device: str, bed_id: str) -> dict[str, Any]:
    """Let a kept bed go: its row, and its music.

    A route rather than a client-side delete for `services/loops.remove`'s reason: the row and the
    file are written by the same party, the row first, so a merge that raises keeps both.
    """
    bed = graph.owned_records(owner, "beds", [bed_id]).get(bed_id)
    if bed is None or bed.get("deleted"):
        raise ApiError(404, "not_found", "That music is not among what you kept.")
    at = now_instant()
    graph.merge_graph(owner, device, {"beds": [{
        **bed, "deleted": True, "editedAt": at, "editedBy": device,
    }]}, enqueue=None)
    if bed.get("audioRef"):
        media_files.remove(settings.media_path, bed["audioRef"], "deleted")
    return graph.owned_records(owner, "beds", [bed_id])[bed_id]


# ── a style's sample ────────────────────────────────────────────────────────


def sample_names(settings: Settings, found: Schema) -> dict[str, str | None]:
    """Each family's sample, by the name it is served under, or None where none is made yet."""
    return {one.id: samples.find(settings.samples_path, _key(found, one.id))
            for one in found.families}


def missing(settings: Settings) -> list[str]:
    """The families with no sample for the engine and bundle that answer now."""
    found = _schema(settings)
    if not found.production_bundle:
        return []
    return [family for family, name in sample_names(settings, found).items() if name is None]


def start_sample(settings: Settings, family: str) -> Operation:
    return _start(settings, family, SAMPLE_SEED, SAMPLE_SECONDS)


def store_sample(settings: Settings, family: str, rendered: Music) -> str:
    """Keep a finished sample under what it records, and say what it is served as."""
    found = _schema(settings)
    if rendered.engine_version and rendered.engine_version != found.engine_version:
        raise ApiError(502, "loops_failed",
                       "LexiBeat changed engine while the sample was being made; it was not kept.")
    audio, _ = _track(settings, rendered)
    return samples.store(settings.samples_path, _key(found, family), family, audio)


_making: dict[str, threading.Lock] = {}
_making_guard = threading.Lock()


def sample_now(settings: Settings, family: str) -> str:
    """A style's sample for a tap that got there before the warming job: made now, and waited for.

    One render a family at a time in this process: a second tap waits for the first and finds what
    it made.
    """
    found = _schema(settings)
    if family not in {one.id for one in found.families}:
        raise ApiError(400, "invalid_input", f"The generator has no “{family}” music.")
    with _making_guard:
        lock = _making.setdefault(family, threading.Lock())
    with lock:
        name = samples.find(settings.samples_path, _key(found, family))
        if name:
            return name
        if not found.production_bundle:
            raise ApiError(409, "loops_no_samples", loops.NO_SAMPLES)
        operation = start_sample(settings, family)
        deadline = time.monotonic() + SAMPLE_WAIT_SECONDS
        while not operation.finished:
            if time.monotonic() > deadline:
                raise ApiError(504, "loops_timeout",
                               "LexiBeat is still making this style's sample, probably behind a "
                               "loop; try again in a minute.",
                               noted={"family": family, "operation": operation.id})
            time.sleep(SAMPLE_POLL_SECONDS)
            operation = follow(settings, operation.id)
        if operation.status != "completed" or not isinstance(operation.result, Music):
            raise ApiError(502, "loops_failed",
                           operation.error or f"The sample's render was {operation.status}.")
        return store_sample(settings, family, operation.result)


def sample_file(settings: Settings, name: str) -> Path:
    path = samples.path_of(settings.samples_path, name)
    if path is None:
        raise ApiError(404, "not_found", "There is no such sample.")
    return path


# ── the generator ───────────────────────────────────────────────────────────


def _schema(settings: Settings) -> Schema:
    try:
        return loops.service(settings).schema()
    except LoopError as error:
        raise loops.refusal(error) from None


def _start(settings: Settings, family: str, seed: int, seconds: float) -> Operation:
    try:
        return loops.service(settings).music(family=family, seed=seed, seconds=seconds,
                                             palette=PALETTE)
    except LoopError as error:
        raise loops.refusal(error) from None


def _track(settings: Settings, rendered: Music) -> tuple[bytes, str]:
    try:
        audio, mime = loops.service(settings).track(rendered.audio_url)
    except LoopError as error:
        raise loops.refusal(error) from None
    if not audio or len(audio) > loops.TRACK_LIMIT:
        raise ApiError(502, "loops_failed", "LexiBeat's music could not be stored.")
    return audio, mime


def _key(found: Schema, family: str) -> str:
    return samples.key(family=family, seed=SAMPLE_SEED, seconds=SAMPLE_SECONDS, palette=PALETTE,
                       engine_version=found.engine_version, bundle_version=found.bundle_version)
