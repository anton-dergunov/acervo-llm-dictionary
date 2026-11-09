"""Which story voice prompt keeps a Gemini voice from saying more than its passage?

    .venv/bin/python experiments/story-fragments/variants.py record --takes 10
    .venv/bin/python experiments/story-fragments/variants.py record --takes 10 --language es \
        --model gemini-2.5-flash-tts --variant current --variant no-guard --variant say-only
    .venv/bin/python experiments/story-fragments/variants.py report

`record.py` found that the fallback voice, `gemini-2.5-flash-tts`, reads its instructions aloud: the
fragment «Sin mostrar ningún temor,» came back wrong in 8 takes of 10, mostly as the direction and the
template's own last sentence («… drop, translate o explain any words»), and a whole sentence in 3 of
10. This asks both Gemini voices for four passages under each template in `VARIANTS`, ten takes each,
and listens to every take with the server's own ear (`acervo.hearing`, Whisper base on CTranslate2,
pinned in `models/hearing.json`).

**Everything goes through today's request path**: `speak.direction` fills the template the way the
server does, `speak.speak` sends it pinned to the `vertex` row and voice Fenrir, for `es-AR` — what
the server sends for Spanish now that the vocabulary's accent is Argentina, accent sentence included.

A take is scored by the words Whisper hears **outside the text's own stretch** (`hearing.rule.around`)
— the rule this experiment is choosing for stories — and, for comparison, by the loop rule
(`hearing.rule.leaked`). `recall` is the share of the text's words heard at all, which catches a take
that drops the passage for its direction. Takes go to `out/variants/` (ignored); one line per take to
`results/variants.jsonl`, resumable.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from acervo import hearing
from acervo.hearing.rule import around, leaked, plain
from acervo.models.local import load_local
from acervo.pronunciation import speak

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "variants"
RESULTS = HERE / "results" / "variants.jsonl"

PROVIDER = "vertex"
VOICE = "Fenrir"
LANGUAGE = "es-AR"  # `--language es` for a vocabulary with no accent chosen
MODELS = ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-tts")

# The shipped template first. The blanks are the ones `speak.direction` fills.
VARIANTS = {
    "current": "Read this {language} passage from a short story aloud, as a storyteller would. "
               "{accent}{direction} Do not add, drop, translate or explain any words.",
    "no-guard": "Read this {language} passage from a short story aloud, as a storyteller would. "
                "{accent}{direction}",
    "bare": "{accent}{direction}",
    "say-following": "You are a storyteller reading a short story aloud, as {speaker}. "
                     "Say the following in this manner: {direction}",
    "say-only": "Read this {language} passage from a short story aloud, as a storyteller would. "
                "{accent}{direction} Say only the passage.",
}

# Passages from the stored stories, with the directions they were recorded with: two fragments the
# segmenter cut mid-sentence, and two whole sentences.
TEXTS = {
    "fragment": ("Sin mostrar ningún temor,", "Calm and resolute, with a hint of defiance."),
    "quote": ('"¡Esto es una estafa!",', "Loud and furious, with an outraged tone."),
    "sentence-1": ("Pero el hombre, confundido por el cansancio y la noche, pensó que era una broma de los "
                   "vecinos del pueblo.",
                   "Slightly amused and weary, speaking at a relaxed, conversational pace."),
    "sentence-2": ("El viajero alzó la vista y vio el rostro ardiente y furioso del espectro, esperando que "
                   "él temblara de miedo.",
                   "Tense and dramatic, with a touch of eerie anticipation."),
}

# Words heard outside the text from which a take counts as saying more than its passage: the shipped
# `hearing.rule.MORE_WORDS`. Run first at 4; three wrong takes at exactly 3 moved it down.
OUTSIDE = 3

_lock = threading.Lock()


def score(heard: str, text: str, style: str) -> dict:
    outside = around(heard, text, "es")
    wanted = plain(text)
    got = set(plain(heard))
    return {
        "outside": len(outside), "outside_words": outside,
        "leaked": leaked(heard, text, style, "es"),
        "recall": round(sum(1 for word in wanted if word in got) / max(len(wanted), 1), 3),
    }


def done() -> set[tuple[str, str, str, int]]:
    if not RESULTS.exists():
        return set()
    rows = [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line]
    return {(r.get("language", "es-AR"), r["model"], r["variant"], r["text_kind"], r["take"])
            for r in rows if "heard" in r}


def one(providers, language: str, model: str, variant: str, kind: str, take: int) -> dict:
    text, note = TEXTS[kind]
    style = speak.direction(VARIANTS[variant], note, language)
    row = {"language": language, "model": model, "variant": variant, "text_kind": kind, "take": take,
           "text": text, "style": str(style)}
    for attempt in range(8):
        started = time.monotonic()
        try:
            spoken = speak.speak(text, language, chosen=[(PROVIDER, model)], catalogue=providers,
                                 style=style, voice=lambda *_: VOICE, caller="pronounce-preview")
        except Exception as error:  # noqa: BLE001 — a quota passes; anything else is the finding
            message = f"{type(error).__name__}: {error}"
            if "rate_limited" in str(getattr(error, "reasons", "")) or "Quota exceeded" in message:
                time.sleep(15 * (attempt + 1))
                continue
            # Vertex now and then refuses a story passage as against its usage guidelines and lets
            # the same request through a moment later; counted in the report, then tried again.
            if "usage guidelines" in message and attempt < 2:
                row["refused_once"] = row.get("refused_once", 0) + 1
                continue
            return {**row, "error": message}
        data = spoken.result.data
        path = OUT / f"{language}-{model}-{variant}-{kind}-{take:02d}.{speak.extension_for(spoken.result.mime)}"
        path.write_bytes(data)
        row.update(call_s=round(time.monotonic() - started, 2), file=path.name, sent=spoken.direction)
        heard = hearing.shared().hear(data, "es")
        row.update(heard=heard, seconds=seconds_of(data), **score(heard, text, str(style)))
        return row
    return {**row, "error": "quota: gave up after 8 attempts"}


def seconds_of(data: bytes) -> float:
    import io

    import soundfile

    with soundfile.SoundFile(io.BytesIO(data)) as reading:
        return round(len(reading) / reading.samplerate, 3)


def record(args: argparse.Namespace) -> None:
    providers = load_local()
    OUT.mkdir(parents=True, exist_ok=True)
    have = done()
    models = [m for m in MODELS if not args.model or m == args.model]
    variants = args.variant or list(VARIANTS)
    kinds = args.text or list(TEXTS)
    jobs = [(args.language, model, variant, kind, take) for take in range(args.takes) for variant in variants
            for kind in kinds for model in models if (args.language, model, variant, kind, take) not in have]
    print(f"{len(jobs)} takes to record", flush=True)
    with RESULTS.open("a", encoding="utf-8") as log, ThreadPoolExecutor(args.workers) as pool:
        for row in pool.map(lambda job: one(providers, *job), jobs):
            with _lock:
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
                log.flush()
            print(row["language"], row["model"][7:10], row["variant"], row["text_kind"], row["take"],
                  row.get("outside", row.get("error")), flush=True)


def report(_args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line]
    rows = [r for r in rows if "heard" in r]
    table: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        table[(r.get("language", "es-AR"), r["model"], r["variant"])].append(r)
    kinds = list(TEXTS)
    print(f"| language | model | variant | wrong (outside ≥ {OUTSIDE}) | " + " | ".join(kinds) + " | loop rule | recall < 1 |")
    print("|" + " --- |" * (6 + len(kinds)))
    for language, model, variant in sorted(table, key=lambda k: (k[0] != "es-AR", MODELS.index(k[1]), list(VARIANTS).index(k[2]))):
        if True:
            group = table[(language, model, variant)]
            if not group:
                continue
            wrong = [r for r in group if r["outside"] >= OUTSIDE]
            per = [f"{sum(1 for r in group if r['text_kind'] == k and r['outside'] >= OUTSIDE)}/"
                   f"{sum(1 for r in group if r['text_kind'] == k)}" for k in kinds]
            print(f"| {language} | {model} | {variant} | {len(wrong)}/{len(group)} | " + " | ".join(per)
                  + f" | {sum(1 for r in group if r['leaked'])} | {sum(1 for r in group if r['recall'] < 1)} |")
    every = [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line]
    def key(r):
        return (r.get("language", "es-AR"), r["model"], r["variant"], r["text_kind"], r["take"])
    kept = {key(r) for r in rows}
    errors = [r for r in every if "error" in r and key(r) not in kept]
    refused = sum(r.get("refused_once", 0) for r in rows)
    if refused:
        print(f"\n{refused} usage-guideline refusals that passed on a retry", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} errors, e.g. {errors[0]['error'][:200]}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--takes", type=int, default=10)
    rec.add_argument("--workers", type=int, default=3)
    rec.add_argument("--language", default=LANGUAGE)
    rec.add_argument("--model", choices=MODELS)
    rec.add_argument("--variant", action="append", choices=list(VARIANTS))
    rec.add_argument("--text", action="append", choices=list(TEXTS))
    rec.set_defaults(run=record)
    sub.add_parser("report").set_defaults(run=report)
    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
