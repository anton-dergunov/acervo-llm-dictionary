"""Photo capture's binding layer: a photo in, a page a finger can tap out, and the photo kept.

`acervo.ocr` knows how to turn an engine's words into a page and nothing about Acervo; this module
knows the rest — which engine the owner's chain names, which languages the owner studies, where the
media root is, and what happens to a photo nobody adds.

**Who writes the file and who writes the row.** A media file and the row naming it must be written
by the same party, or one of them is a lie — and here the photo arrives long before any row. So:

1. `read` stores the photo, EXIF-free, content-addressed, as `photos/{owner}/pending/{digest}.jpg`,
   and answers the reference it will have *once kept*: `photos/{owner}/{digest}.jpg`.
2. A save whose attestation names that reference hands `place` to `merge_graph`, which moves the
   file out of `pending/` inside the write's transaction and moves it back if the write fails. A row
   can therefore never name a missing file, and there is still one writer of the graph.
3. `sweep` removes pending photos older than a day. A photo nobody added costs nothing.

Because the reference names the final place from the start, nothing ever rewrites one, and a second
word saved from the same photo finds the file already kept. A kept photo is not removed when its
attestation is tombstoned: undo restores the tombstone, and one photo may back several words.
"""

from __future__ import annotations

import hashlib
import io
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from acervo.domain.validation import PHOTO_REF
from acervo.errors import ApiError
from acervo.models import ChainExhausted, ProviderError, chain, journal, load_catalogue
from acervo.models import call as provider
from acervo.models.results import OcrResult
from acervo.ocr import layout, segment
from acervo.repository import graph
from acervo.services import media as media_files
from acervo.services.models import chain_for, refusal
from acervo.settings import Settings

# The long edge a photo is kept and read at. Measured in `experiments/photo-capture/`: at 2048 px
# Vision's character error on a book photo is 0.4%, at 1280 px it is 2.3%, and the full sensor buys
# a little more at three times the bytes. The interface sends this size already; this is the guard.
LONG_EDGE = 2048
QUALITY = 85
# How long a photo waits for a save to name it.
PENDING_SECONDS = 24 * 60 * 60
# Metadata a JPEG can carry that says where and when it was taken.
_REVEALING = ("exif", "xmp", "XML:com.adobe.xmp", "photoshop", "comment", "icc_profile")


def prepare(data: bytes) -> tuple[bytes, int, int]:
    """The photo as it is kept and read: upright, at most 2048 px, a JPEG carrying nothing but pixels.

    The interface already sends exactly that, drawn through a canvas, and then it is kept byte for
    byte — a second JPEG generation would cost detail for nothing. Anything else is re-encoded, which
    is also what strips the camera's EXIF, location included.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ApiError(400, "unreadable_image", "That file is not a picture this server can read.") from None

    clean = (
        image.format == "JPEG"
        and not any(image.info.get(key) for key in _REVEALING)
        and not image.getexif()
        and max(image.size) <= LONG_EDGE
        and image.mode in ("RGB", "L")
    )
    if clean:
        return data, image.width, image.height

    upright = ImageOps.exif_transpose(image).convert("RGB")
    upright.thumbnail((LONG_EDGE, LONG_EDGE), Image.Resampling.LANCZOS)
    encoded = io.BytesIO()
    upright.save(encoded, "JPEG", quality=QUALITY, optimize=True)
    return encoded.getvalue(), upright.width, upright.height


def reference_for(owner: str, data: bytes) -> str:
    return f"photos/{owner}/{hashlib.sha256(data).hexdigest()[:16]}.jpg"


def pending_path(media: Path, reference: str) -> Path:
    kept = media / reference
    return kept.parent / "pending" / kept.name


def store(settings: Settings, owner: str, data: bytes) -> dict[str, Any]:
    """Keep a photo pending without reading it, and say what it will be called once kept.

    What a scrolled screenshot is kept as: the device crops it to the square that was on screen and
    sends that. It is a clean JPEG, so `prepare` keeps it byte for byte, and the reference names the
    very bytes the device holds — which is what lets it put them in its own cache under that name.
    """
    photo, width, height = prepare(data)
    reference = reference_for(owner, photo)
    media = Path(settings.media_path)
    if not (media / reference).is_file():
        _place(pending_path(media, reference), photo)
    return {"photoRef": reference, "width": width, "height": height}


def read(settings: Settings, owner: str, data: bytes) -> dict[str, Any]:
    """Read one photo: store it pending, ask the owner's `ocr` chain, and lay the page out."""
    warm()
    photo, width, height = prepare(data)
    reference = reference_for(owner, photo)
    vocabularies = graph.owner_vocabularies(owner)

    reading = _ocr(settings, owner, photo, _hints(vocabularies))
    started = time.monotonic()
    page = layout.page(reading.words, width, height, segment.shared().split)
    segmented = time.monotonic() - started

    store(settings, owner, photo)
    language = _vocabulary_language(reading.language, vocabularies)
    journal.outcome(
        "photo-read",
        provider=reading.answer.provider_id,
        ocr_s=round(reading.answer.seconds, 3),
        segment_s=round(segmented, 3),
        words=len(page["words"]),
        sentences=len(page["sentences"]),
        bytes=len(photo),
        language=reading.language,
    )
    return {
        "photoRef": reference,
        "width": width,
        "height": height,
        # The owner's vocabulary for what Vision detected, when there is one — `zh-Hans` rather than
        # `zh` — else whatever it detected, so the interface can say which language is missing.
        "language": language or reading.language,
        "vocabulary": language is not None,
        "readBy": {"provider": reading.answer.provider_id, "model": reading.answer.model},
        **page,
    }


def _ocr(settings: Settings, owner: str, photo: bytes, hints: list[str]) -> OcrResult:
    def ask(candidate: chain.Candidate) -> OcrResult:
        return provider.ocr(photo, row=candidate.row, model=candidate.model, language_hints=hints)

    try:
        return chain.walk(
            "ocr", chain_for(settings, owner, "ocr"), load_catalogue(), ask, chain.stamped,
            caller="photo-read",
        )
    except ChainExhausted as exhausted:
        raise refusal(exhausted, "ocr") from None
    except ProviderError as error:
        raise refusal(error, "ocr") from None


def _hints(vocabularies: list[dict[str, Any]]) -> list[str]:
    """The owner's languages as an engine takes them: the primary tag, except where script matters."""
    hints: dict[str, None] = {}
    for vocabulary in vocabularies:
        language = str(vocabulary["language"])
        hints["zh-Hant" if language.lower().startswith("zh-hant") else language.split("-")[0]] = None
    return list(hints)


def _vocabulary_language(detected: str | None, vocabularies: list[dict[str, Any]]) -> str | None:
    """The owner's vocabulary for the language an engine detected: exactly, else by primary tag."""
    if not detected:
        return None
    languages = [str(vocabulary["language"]) for vocabulary in vocabularies]
    for language in languages:
        if language.lower() == detected.lower():
            return language
    primary = detected.lower().split("-")[0]
    for language in languages:
        if language.lower().split("-")[0] == primary:
            return language
    return None


def _place(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, destination)


def require(settings: Settings, owner: str, reference: str) -> None:
    """Refuse a reference that is not this owner's photo, or whose photo is no longer here."""
    match = PHOTO_REF.match(reference or "")
    if match is None or match["owner"] != owner:
        raise ApiError(400, "invalid_input", "That is not a photo this server stored for you.")
    media = Path(settings.media_path)
    if not (media / reference).is_file() and not pending_path(media, reference).is_file():
        raise ApiError(
            400, "photo_missing",
            "That photo is no longer on the server — a photo is kept for a day until it is added. "
            "Take it again.",
        )


def placer(settings: Settings) -> Callable[[str, str], Callable[[], None]]:
    """What `merge_graph` calls for an attestation naming a photo it did not name before."""
    media = Path(settings.media_path)

    def place(owner: str, reference: str) -> Callable[[], None]:
        require(settings, owner, reference)
        kept = media / reference
        if kept.is_file():
            return lambda: None
        waiting = pending_path(media, reference)
        os.replace(waiting, kept)

        def undo() -> None:
            if kept.is_file() and not waiting.exists():
                os.replace(kept, waiting)

        return undo

    return place


def sweep(settings: Settings, *, older_than: float = PENDING_SECONDS, now: float | None = None) -> int:
    """Remove every pending photo older than `older_than` seconds. Returns how many went."""
    root = Path(settings.media_path) / "photos"
    if not root.is_dir():
        return 0
    cutoff = (time.time() if now is None else now) - older_than
    removed = 0
    for path in root.glob("*/pending/*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                removed += media_files.remove(
                    settings.media_path, str(path.relative_to(settings.media_path)), "unclaimed")
        except OSError:
            continue
    return removed


_warming = threading.Lock()


def warm() -> None:
    """Load the sentence splitter in the background, once, if it is not loaded yet.

    Called when the interface opens the Photo tab, so the first photo does not wait for a 400 MB
    model: the owner takes the picture in the seconds it takes to load. Nothing loads it at startup,
    because a feature used now and then should not hold its memory on the NAS all day.
    """
    warmer = getattr(segment.shared(), "warm", None)
    if warmer is None or not _warming.acquire(blocking=False):
        return

    def run() -> None:
        try:
            warmer()
        finally:
            _warming.release()

    threading.Thread(target=run, name="acervo-photo-warm", daemon=True).start()
