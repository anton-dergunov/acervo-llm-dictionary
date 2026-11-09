"""What each take of `record.py` actually said, by Whisper, into `results/heard-<model>.jsonl`.

    experiments/take-verification/.venv/bin/python experiments/story-fragments/hear.py [--model base]

Uses the take-verification experiment's environment (transformers' Whisper), and imports nothing of
Acervo's. A take *invented* when Whisper hears words past the end of the text it was given — the
judgement this experiment needs, and the one the length rule stands in for. Also hears the original
take from 24 Sep (`out/original-24sep.flac`, copied from the server's take store).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np
import torch
from transformers import WhisperForConditionalGeneration, WhisperProcessor

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
TAKES = HERE / "results" / "takes.jsonl"


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "f32le",
                          "-ac", "1", "-ar", "16000", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    return re.findall(r"\w+", "".join(c for c in folded if not unicodedata.combining(c)))


def extra(text: str, heard: str) -> int:
    """How many words Whisper heard beyond the text's own count — invented words, give or take one."""
    return max(0, len(words(heard)) - len(words(text)))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # base is the size the server listens with (models/hearing.json); small is the laptop's.
    parser.add_argument("--model", choices=("base", "small"), default="small")
    args = parser.parse_args(argv)
    source = f"openai/whisper-{args.model}"
    heard_path = HERE / "results" / f"heard-{args.model}.jsonl"
    processor = WhisperProcessor.from_pretrained(source)
    model = WhisperForConditionalGeneration.from_pretrained(source).eval()
    rows = [json.loads(line) for line in TAKES.read_text(encoding="utf-8").splitlines() if line]
    rows = [row for row in rows if "seconds" in row]
    original = {"model": "gemini-3.1-flash-tts-preview", "text_kind": "fragment", "take": "24sep",
                "text": "Sin mostrar ningún temor,", "seconds": 10.96, "file": "original-24sep.flac"}
    with heard_path.open("w", encoding="utf-8") as log:
        for row in [original, *rows]:
            features = processor(decode(OUT / row["file"]), sampling_rate=16000, return_tensors="pt").input_features
            with torch.inference_mode():
                ids = model.generate(features, language="es", task="transcribe", max_new_tokens=200)
            heard = processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
            out = {k: row[k] for k in ("model", "text_kind", "take", "seconds")}
            out.update(heard=heard, extra_words=extra(row["text"], heard))
            log.write(json.dumps(out, ensure_ascii=False) + "\n")
            print(out["seconds"], out["extra_words"], row["model"][:10], row["text_kind"], heard, flush=True)


if __name__ == "__main__":
    main()
