"""Whisper base, pinned, transcribing one recording on the CPU.

`models/hearing.json` names the CTranslate2 conversion and the exact revision, the way
`models/encoder.json` does for the meaning map: the server image downloads it once at build time, and
at run time the hub is offline, so a check never reaches the network. The model is loaded on the first
take that needs a check and kept for the life of the process (about 150 MB of memory).

The settings are the ones timed on the NAS in `experiments/take-verification/` — int8, four threads,
greedy, told the language — at 2.0 s a take. Whisper encodes a padded 30-second window whatever the
clip's length, so a one-word take costs what a long line does.

Anything with `hear(audio, language)` can stand in, which is how the tests run without the weights.
"""

from __future__ import annotations

import io
import json
import threading
from dataclasses import dataclass
from math import gcd
from pathlib import Path
from typing import Protocol

import numpy as np

PIN_PATH = Path(__file__).resolve().parents[3] / "models" / "hearing.json"
SAMPLE_RATE = 16_000
WINDOW_SECONDS = 30
THREADS = 4


@dataclass(frozen=True)
class Pin:
    model: str
    revision: str
    files: tuple[str, ...]


def load_pin(path: Path = PIN_PATH) -> Pin:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Pin(model=raw["model"], revision=raw["revision"], files=tuple(raw["files"]))


class Transcriber(Protocol):
    def hear(self, audio: bytes, language: str) -> str:
        """What was said in `audio` (any of FLAC, Ogg, MP3, WAV), told it is in `language`, a
        primary subtag. Raises when it cannot listen at all."""
        ...


class WhisperEar:
    def __init__(self, pin: Pin) -> None:
        self.pin = pin
        self._model = None
        self._lock = threading.Lock()

    def _loaded(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            from huggingface_hub import snapshot_download

            path = snapshot_download(self.pin.model, revision=self.pin.revision,
                                     allow_patterns=list(self.pin.files), local_files_only=True)
            self._model = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=THREADS)
        return self._model

    def hear(self, audio: bytes, language: str) -> str:
        samples = decode(audio)
        # One check at a time: each already has the four threads, and two at once on the NAS's four
        # cores would only make both slower.
        with self._lock:
            segments, _ = self._loaded().transcribe(
                samples, language=language, beam_size=1, temperature=0.0,
                condition_on_previous_text=False, without_timestamps=True, vad_filter=False,
            )
            return "".join(segment.text for segment in segments).strip()


def decode(audio: bytes) -> np.ndarray:
    """16 kHz mono float32, the first thirty seconds.

    Read with soundfile (FLAC, Ogg, MP3, WAV — every type a take is kept as) and resampled with
    scipy, which is how the check was timed on the NAS. Not faster-whisper's own decoder: it passes
    PyAV an argument PyAV 19 no longer takes.
    """
    import soundfile
    from scipy.signal import resample_poly

    data, rate = soundfile.read(io.BytesIO(audio), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != SAMPLE_RATE:
        factor = gcd(rate, SAMPLE_RATE)
        mono = resample_poly(mono, SAMPLE_RATE // factor, rate // factor).astype(np.float32)
    return mono[: WINDOW_SECONDS * SAMPLE_RATE]


_shared: Transcriber | None = None
_shared_lock = threading.Lock()


def shared() -> Transcriber:
    """The process's one transcriber, built from the pin on first use."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = WhisperEar(load_pin())
        return _shared


def use(transcriber: Transcriber | None) -> None:
    """Replace the process's transcriber. Tests use it; None goes back to the pinned model."""
    global _shared
    with _shared_lock:
        _shared = transcriber
