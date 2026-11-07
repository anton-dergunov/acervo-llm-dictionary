"""Whisper listens back to every take, so what a voice *said* is checked against what it was given.

    experiments/expressive-voice/.venv/bin/python experiments/expressive-voice/transcribe.py

Runs in this experiment's own environment (`uv venv experiments/expressive-voice/.venv` and
`uv pip install mlx-whisper jiwer` into it), not the project's, and imports nothing of Acervo's.
Whisper large-v3-turbo on Apple silicon, told each item's language. Per take it writes the
transcript, the word error rate against the text, and three flags:

- `twice`: the text, or its words, came back twice — round 0's doubling;
- `instruction`: words of the direction that are not in the text came back — an instruction read
  aloud, in English or in the item's own language;
- `different`: the words differ from the text by more than `DIFFERENT` once a doubling is set aside.

These are a cross-check on the ear, not a verdict: round 0's transcriber missed both an instruction
read aloud and an accent. Resumable: a take already in `results/transcripts.jsonl` is skipped.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import jiwer
import mlx_whisper

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results"
MODEL = "mlx-community/whisper-large-v3-turbo"
DIFFERENT = 0.25

# Words that say an instruction was read out even in the item's own language.
GIVEAWAYS = {"acento", "accent", "argentina", "argentino", "argentine", "españa", "spain", "castilian",
             "castellano", "native", "speaker", "sounding", "direction", "акцент", "tone", "calm", "natural"}
STOP = {"this", "that", "with", "from", "aloud", "read", "would", "words", "sentence", "text", "keep",
        "pace", "explain", "drop", "translate", "story", "passage", "short", "like", "the", "and"}


def plain(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c)).replace("ё", "е")
    return re.findall(r"[\w']+", folded)


def twice(said: list[str], text: list[str]) -> bool:
    if not text:
        return False
    joined, wanted = " ".join(said), " ".join(text)
    if joined.count(wanted) >= 2:
        return True
    # A doubled text Whisper heard with one word off still comes back near twice as long.
    return len(text) <= 12 and len(said) >= 1.7 * len(text) and \
        sum(1 for w in set(text) if said.count(w) >= 2) >= max(1, 0.6 * len(set(text)))


def instruction(said: list[str], text: list[str], sent: str | None) -> list[str]:
    asked = {w for w in plain(sent or "") if len(w) >= 4 and w not in STOP} | GIVEAWAYS
    return sorted({w for w in said if w in asked and w not in text})


def main() -> None:
    items = {item["id"]: item for item in json.loads((HERE / "set.json").read_text(encoding="utf-8"))["items"]}
    takes = [json.loads(line) for line in (RESULTS / "takes.jsonl").read_text(encoding="utf-8").splitlines() if line]
    path = RESULTS / "transcripts.jsonl"
    done = set()
    if path.exists():
        done = {json.loads(line)["key"] for line in path.read_text(encoding="utf-8").splitlines() if line}
    with path.open("a", encoding="utf-8") as handle:
        for take in takes:
            key = f"{take['item']}/{take['system']}{'-' + take['variant'] if take['variant'] else ''}/{take['take']}"
            if key in done:
                continue
            item = items[take["item"]]
            audio = OUT / "masters" / f"{key.replace('/', '_')}.wav"
            heard = mlx_whisper.transcribe(str(audio), path_or_hf_repo=MODEL, language=item["language"].split("-")[0],
                                           condition_on_previous_text=False, temperature=0.0)["text"].strip()
            said, text = plain(heard), plain(item["text"])
            doubled = twice(said, text)
            error = jiwer.wer(" ".join(text), " ".join(said)) if said else 1.0
            if doubled and said:
                error = min(error, jiwer.wer(" ".join(text), " ".join(said[: len(text)])))
            read = instruction(said, text, take.get("sent"))
            row = {"key": key, "item": take["item"], "system": take["system"], "variant": take["variant"],
                   "take": take["take"], "text": heard, "wer": round(error, 3), "twice": doubled,
                   "instruction": read, "different": error > DIFFERENT}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            flags = [name for name in ("twice", "different") if row[name]] + (["read:" + ",".join(read)] if read else [])
            print(f"{key:28} {row['wer']:.2f} {' '.join(flags):24} {heard[:70]}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
