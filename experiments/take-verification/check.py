"""Whisper listens to every recording; each signal a filter could use is written down per clip.

    experiments/take-verification/.venv/bin/python experiments/take-verification/check.py \
        --model small [--kind take] [--limit 50] [--manifest out/manifest.jsonl]

Per clip and model, into `results/signals-<model>.jsonl` (resumable — a clip already there is
skipped):

- `heard`: Whisper's own transcript, decoded greedily (temperature 0), told the language;
- `cer`, `wer`: that transcript against the expected text, both folded (case, accents, punctuation;
  characters for Chinese);
- `lp_expected`, `lp_heard`: the mean log-probability per token Whisper gives the expected text (the
  best of its surface forms: as stored, capitalised, with a full stop) and its own transcript, both teacher-forced through the same decoder over the same encoder output,
  end-of-text included. `gap = lp_heard - lp_expected` is the precision guard: when the asked-for
  text is about as likely as Whisper's guess, a mismatch is Whisper's, not the voice's;
- `min_expected`: the least likely token of the expected text — one swapped sound in a long line is
  diluted in a mean but not in a minimum;
- `twice`, `instruction`: the doubling and the direction read aloud, as `expressive-voice` found them;
- `decode_s`, `score_s`: wall seconds for each half, the whole cost of a check.

Imports nothing of Acervo's. The model is transformers' Whisper, the engine the server image already
carries; how fast CTranslate2 would be is `nas_timing.py`'s question, not this one's.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import unicodedata
from pathlib import Path

import numpy as np
import torch
from transformers import WhisperForConditionalGeneration, WhisperProcessor

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results"
MODELS = {"base": "openai/whisper-base", "small": "openai/whisper-small",
          "turbo": "openai/whisper-large-v3-turbo"}

# Words that say an instruction was read out, in English or the line's own language: the accent
# vocabulary `expressive-voice` collected, and the director note LexiBeat sends with every take
# ("Speak warmly, as if teaching someone, but clearly, at a natural pace, with a natural pitch range.").
GIVEAWAYS = {"acento", "accent", "argentina", "argentino", "argentine", "españa", "spain", "castilian",
             "castellano", "british", "american", "native", "speaker", "sounding", "direction", "акцент",
             "tone", "calm", "speak", "clearly", "pace", "pitch", "warmly", "teaching", "slowly", "naturally"}
STOP = {"this", "that", "with", "from", "aloud", "read", "would", "words", "sentence", "text", "keep",
        "explain", "drop", "translate", "story", "passage", "short", "like", "the", "and", "but", "someone",
        "range", "natural", "slightly", "lower", "higher", "faster"}


def decode(path: Path) -> np.ndarray:
    """16 kHz mono float32, through ffmpeg — the laptop's decoder, for FLAC, Ogg Opus and MP3 alike."""
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "f32le",
                          "-ac", "1", "-ar", "16000", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def plain(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c)).replace("ё", "е")
    return re.findall(r"[\w']+", folded)


def chars(words: list[str], language: str) -> str:
    return simplified("".join(words)) if language == "zh" else " ".join(words)


def simplified(text: str) -> str:
    """Chinese in simplified characters: Whisper writes 圖書館 for a text that says 图书馆.

    OpenCC (Apache-2.0) where it is installed; the NAS timing image has no need of it."""
    global _converter
    if _converter is None:
        try:
            from opencc import OpenCC
            _converter = OpenCC("t2s").convert
        except ImportError:
            _converter = str
    return _converter(text)


_converter = None


def twice(said: list[str], text: list[str]) -> bool:
    if not text:
        return False
    joined, wanted = " ".join(said), " ".join(text)
    if joined.count(wanted) >= 2:
        return True
    return len(text) <= 12 and len(said) >= 1.7 * len(text) and \
        sum(1 for w in set(text) if said.count(w) >= 2) >= max(1, 0.6 * len(set(text)))


def instruction(said: list[str], text: list[str], direction: str) -> list[str]:
    asked = {w for w in plain(direction) if len(w) >= 4 and w not in STOP} | GIVEAWAYS
    return sorted({w for w in said if w in asked and w not in text})


def distance(a: str, b: str) -> int:
    """Levenshtein, characters."""
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def contained(heard: str, text: str, language: str) -> dict:
    """The stretch of the transcript that is the text, and what was said around it.

    A voice asked for a feeling may wrap the word in one — «Pfff, bancarse.», «Oh, frivolous.» —
    which the owner wants, and which a whole-transcript distance counts as wrong. So the text is
    aligned to the closest run of whole words of the transcript (characters for Chinese), the
    distance is taken there, and what lies outside is kept apart as `extra`. No list of exclamations:
    the alignment does not need to know what the extra words are, so it works in every language.
    """
    pieces = list(heard.strip()) if language == "zh" else heard.split()
    folded = [chars(plain(piece), language) for piece in pieces]
    wanted = chars(plain(text), language)
    joiner = "" if language == "zh" else " "
    best = (distance(wanted, ""), 0, 0)
    # Only runs of about the text's own length can be the text: a run twice as long costs at least
    # the text's length in insertions, which the empty run already beats. Without the bound a story
    # passage, or twenty «ha»s, is thousands of alignments.
    size = len(wanted) if language == "zh" else max(1, len(wanted.split()))
    longest = 2 * size + 2
    for start in range(len(pieces)):
        for end in range(start + 1, min(len(pieces), start + longest) + 1):
            span = joiner.join(piece for piece in folded[start:end] if piece)
            best = min(best, (distance(wanted, span), start, end), key=lambda b: (b[0], -(b[2] - b[1])))
    cost, start, end = best
    extra = [piece for piece in folded[:start] + folded[end:] if piece]
    return {"cer_inner": round(cost / max(len(wanted), 1), 4), "extra": extra,
            "before": joiner.join(pieces[:start]), "after": joiner.join(pieces[end:])}


def surfaces(text: str) -> set[str]:
    text = text.strip()
    capital = text[:1].upper() + text[1:]
    forms = {text, capital}
    if text and text[-1].isalnum():
        forms |= {text + ".", capital + "."}
    return forms


class Ear:
    def __init__(self, name: str, device: str, source: str | None = None) -> None:
        source = source or MODELS[name]
        self.processor = WhisperProcessor.from_pretrained(source)
        self.model = WhisperForConditionalGeneration.from_pretrained(source).to(device).eval()
        self.device = device
        self.tokenizer = self.processor.tokenizer

    def prompt(self, language: str) -> list[int]:
        t = self.tokenizer
        return [t.convert_tokens_to_ids(x) for x in
                ("<|startoftranscript|>", f"<|{language}|>", "<|transcribe|>", "<|notimestamps|>")]

    @torch.inference_mode()
    def span_score(self, audio: np.ndarray, language: str, expected: str, before: str, after: str,
                   lp_heard: float) -> float:
        """`gap` with Whisper's own words around the text kept: only the text itself is compared."""
        features = self.processor(audio, sampling_rate=16000, return_tensors="pt").input_features
        encoded = self.model.model.encoder(features.to(self.device, self.model.dtype))
        forms = [" ".join(part for part in (before, form, after) if part) for form in sorted(surfaces(expected))]
        best = max(self.score_many(encoded, self.prompt(language), [
            self.tokenizer.encode(" " + form, add_special_tokens=False) for form in forms]))
        return round(lp_heard - best[0], 4)

    @torch.inference_mode()
    def listen(self, audio: np.ndarray, language: str, expected: str) -> dict:
        started = time.perf_counter()
        features = self.processor(audio, sampling_rate=16000, return_tensors="pt").input_features
        features = features.to(self.device, self.model.dtype)
        encoded = self.model.model.encoder(features)
        prompt = self.prompt(language)
        heard_ids = self.model.generate(
            encoder_outputs=encoded, decoder_input_ids=torch.tensor([prompt], device=self.device),
            do_sample=False, num_beams=1, max_new_tokens=200,
        )[0].tolist()
        # Whisper's generate may or may not hand the prompt back; only strip it when it is there.
        if heard_ids[: len(prompt)] == prompt:
            heard_ids = heard_ids[len(prompt):]
        eot = self.tokenizer.eos_token_id
        heard_ids = [i for i in heard_ids if i != eot and i < eot]
        heard = self.tokenizer.decode(heard_ids).strip()
        decoded = time.perf_counter()
        # The stored text is often a bare lowercase headword, and Whisper writes "Las gracias." for
        # it: scored as stored, the casing and the full stop alone would open a gap. So the expected
        # text is scored in the surface forms Whisper itself writes, and the best of them counts.
        lp_expected, min_expected = max(self.score_many(encoded, prompt, [
            self.tokenizer.encode(" " + form, add_special_tokens=False) for form in sorted(surfaces(expected))
        ]))
        lp_heard, _ = self.score(encoded, prompt, heard_ids)
        scored = time.perf_counter()
        return {"heard": heard, "lp_expected": lp_expected, "min_expected": min_expected,
                "lp_heard": lp_heard, "decode_s": round(decoded - started, 3),
                "score_s": round(scored - decoded, 3)}

    def score_many(self, encoded, prompt: list[int], forms: list[list[int]]) -> list[tuple[float, float]]:
        """`score` for several texts in one batched decoder pass over the same encoder output."""
        eot = self.tokenizer.eos_token_id
        targets = [ids + [eot] for ids in forms]
        width = max(len(target) for target in targets)
        # Teacher forcing feeds each target but its last token; shorter ones are padded, and the pad's
        # positions are never read, since each row picks only its own target's length.
        inputs = torch.tensor([prompt + target[:-1] + [eot] * (width - len(target)) for target in targets],
                              device=self.device)
        hidden = encoded.last_hidden_state.expand(len(targets), -1, -1)
        logits = self.model(encoder_outputs=(hidden,), decoder_input_ids=inputs).logits.float()
        logprobs = torch.log_softmax(logits[:, len(prompt) - 1:], dim=-1)
        scores = []
        for row, target in enumerate(targets):
            picked = logprobs[row, torch.arange(len(target)), torch.tensor(target, device=self.device)]
            scores.append((round(picked.mean().item(), 4), round(picked.min().item(), 4)))
        return scores

    def score(self, encoded, prompt: list[int], ids: list[int]) -> tuple[float, float]:
        target = ids + [self.tokenizer.eos_token_id]
        inputs = torch.tensor([prompt + target[:-1]], device=self.device)
        logits = self.model(encoder_outputs=encoded, decoder_input_ids=inputs).logits[0].float()
        logprobs = torch.log_softmax(logits[len(prompt) - 1:], dim=-1)
        picked = logprobs[torch.arange(len(target)), torch.tensor(target, device=self.device)]
        return round(picked.mean().item(), 4), round(picked.min().item(), 4)


def main() -> None:
    import jiwer  # here, not at the top: `nas_timing.py` imports `Ear` inside an image without it

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--manifest", default=str(OUT / "manifest.jsonl"))
    parser.add_argument("--output")
    parser.add_argument("--kind")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--keys", help="a file of `kind/id` keys, one a line: only these clips")
    parser.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    parser.add_argument("--rescore", action="store_true",
                        help="the span gap, for clips of this model's signals with words around the text")
    args = parser.parse_args()
    if args.rescore:
        return rescore(args)
    manifest = Path(args.manifest)
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    rows = [row for row in rows if not args.kind or row["kind"] == args.kind]
    if args.keys:
        wanted = set(Path(args.keys).read_text(encoding="utf-8").split())
        rows = [row for row in rows if f"{row['kind']}/{row['id']}" in wanted]
    rows = rows[: args.limit]
    output = Path(args.output) if args.output else RESULTS / f"signals-{args.model}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if output.exists():
        done = {json.loads(line)["key"] for line in output.read_text(encoding="utf-8").splitlines() if line}
    ear = Ear(args.model, args.device)
    base = manifest.parent
    with output.open("a", encoding="utf-8") as handle:
        for count, row in enumerate(rows, 1):
            key = f"{row['kind']}/{row['id']}"
            if key in done:
                continue
            audio = decode(base / row["path"])[: 30 * 16000]
            got = ear.listen(audio, row["lang"], row["text"])
            said, text = plain(got["heard"]), plain(row["text"])
            wanted, heard = chars(text, row["lang"]), chars(said, row["lang"])
            record = {
                "key": key, "kind": row["kind"], "lang": row["lang"], "text": row["text"], **got,
                "cer": round(jiwer.cer(wanted, heard), 4) if wanted else 1.0,
                "wer": round(jiwer.wer(" ".join(text), " ".join(said)), 4) if text and said else 1.0,
                "gap": round(got["lp_heard"] - got["lp_expected"], 4),
                "twice": twice(said, text), "instruction": instruction(said, text, row["direction"]),
                "seconds": row["seconds"],
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            if count % 100 == 0:
                print(count, "of", len(rows), flush=True)
    print("done:", output)


RESCORE_CER = 0.2


def rescore(args) -> None:
    """`gap_span` into `results/span-<model>.jsonl`, for the clips where it can change a verdict:
    words outside the text, and a whole-transcript CER past the loosest threshold tried."""
    rows = [json.loads(line) for line in (RESULTS / f"signals-{args.model}.jsonl").read_text(encoding="utf-8").splitlines() if line]
    manifest = Path(args.manifest)
    clips = {f"{row['kind']}/{row['id']}": row for row in
             (json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line)}
    output = RESULTS / f"span-{args.model}.jsonl"
    done = set()
    if output.exists():
        done = {json.loads(line)["key"] for line in output.read_text(encoding="utf-8").splitlines() if line}
    ear = Ear(args.model, args.device)
    with output.open("a", encoding="utf-8") as handle:
        for row in rows:
            if row["key"] in done or row["cer"] <= RESCORE_CER:
                continue
            span = contained(row["heard"], row["text"], row["lang"])
            if not span["extra"]:
                continue
            audio = decode(manifest.parent / clips[row["key"]]["path"])[: 30 * 16000]
            gap = ear.span_score(audio, row["lang"], row["text"], span["before"], span["after"], row["lp_heard"])
            handle.write(json.dumps({"key": row["key"], "gap_span": gap, **span}, ensure_ascii=False) + "\n")
            handle.flush()
    print("done:", output)


if __name__ == "__main__":
    main()
