"""How long a check takes on the server's own CPU, inside the server's own image.

Run by `nas_timing.sh`, never by hand: in a throwaway container of the acervo-server image, with
the weights and a sample of takes mounted at `/work`. Per engine, model and thread count it times
each clip after a warm-up and prints one JSON line:

- `transformers`: `check.Ear`, the very code that produced this experiment's signals — the free
  decode and the teacher-forced score of the expected text, over one encoder pass;
- `ctranslate2`: faster-whisper's greedy transcript alone, which is the cheaper engine but has no
  teacher-forced score of the text, so it can run the structural rules and the CER, not the gap.

Audio is read with soundfile and resampled with scipy, both already in the image, as the server
would do it; the laptop's ffmpeg is not there.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from math import gcd
from pathlib import Path

import numpy as np
import soundfile
from scipy.signal import resample_poly

WORK = Path("/work")


def load(path: Path) -> np.ndarray:
    data, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != 16000:
        factor = gcd(rate, 16000)
        mono = resample_poly(mono, 16000 // factor, rate // factor).astype(np.float32)
    return mono[: 30 * 16000]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("transformers", "ctranslate2"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--threads", type=int, required=True)
    args = parser.parse_args()
    clips = [json.loads(line) for line in (WORK / "clips.jsonl").read_text(encoding="utf-8").splitlines() if line]
    audio = [(clip, load(WORK / clip["file"])) for clip in clips]
    started = time.perf_counter()
    if args.engine == "transformers":
        import torch
        torch.set_num_threads(args.threads)
        sys.path.insert(0, str(WORK))
        from check import Ear
        ear = Ear(args.model, "cpu", source=str(WORK / "weights" / f"tf-{args.model}"))

        def one(clip, samples):
            ear.listen(samples, clip["lang"], clip["text"])
    else:
        sys.path.insert(0, str(WORK / "pylib"))
        from faster_whisper import WhisperModel
        model = WhisperModel(str(WORK / "weights" / f"ct2-{args.model}"), device="cpu",
                             compute_type="int8", cpu_threads=args.threads)

        def one(clip, samples):
            segments, _ = model.transcribe(samples, language=clip["lang"], beam_size=1, temperature=0.0,
                                           condition_on_previous_text=False, without_timestamps=True,
                                           vad_filter=False)
            "".join(segment.text for segment in segments)
    loaded = time.perf_counter() - started
    for clip, samples in audio[:2]:
        one(clip, samples)
    times = {"take": [], "word": [], "story": []}
    lengths = {"take": [], "word": [], "story": []}
    for clip, samples in audio:
        begun = time.perf_counter()
        one(clip, samples)
        times[clip["kind"]].append(time.perf_counter() - begun)
        lengths[clip["kind"]].append(len(samples) / 16000)
    summary = {"engine": args.engine, "model": args.model, "threads": args.threads, "load_s": round(loaded, 2)}
    for kind, spent in times.items():
        if spent:
            summary[kind] = {"n": len(spent), "median_s": round(statistics.median(spent), 3),
                             "p90_s": round(sorted(spent)[int(0.9 * (len(spent) - 1))], 3),
                             "audio_median_s": round(statistics.median(lengths[kind]), 2)}
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
