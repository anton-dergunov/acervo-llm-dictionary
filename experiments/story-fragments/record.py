"""Record the one story passage the voice finished on its own, again, exactly as it was first sent.

    .venv/bin/python experiments/story-fragments/record.py --takes 10

On 24 Sep 2026 the story narration cut «Sin mostrar ningún temor,» as a passage of its own, and the
voice read it as eleven seconds, inventing the rest of the sentence. This asks the same voice for the
same passage ten more times, and for the passage joined to the one after it ten times, on the model
that recorded it and on the model behind it in the chain. What it answers: is a second take of the
fragment usually right (so the fix is to record once more), or does the fragment invent again (so the
fix is to join it to the next passage)?

**The request is the one sent that day**, rebuilt from git at the commit then live (a3aec2f) rather
than from today's code: the story template with no accent (accents came on 4 Nov), the old catalogue's
LINEAR16 and the voice. One thing could not be kept: the bare `es`
language code the old catalogue sent is now refused ("Requested language code 'es' is not supported
for Gemini voices"), so `es-ES` is sent — what today's code sends for Spanish with no accent chosen. `PROOF` is the take key the server computed from those
parameters, and it is the name of a file in the server's take store written at 18:17:02 that day —
so these are the parameters, not a reconstruction of them.

Takes go to `out/` (ignored); one line per take to `results/takes.jsonl`, resumable.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import time
from pathlib import Path

import soundfile

from acervo.models import google_auth
from acervo.models.local import load_local

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results" / "takes.jsonl"

PROVIDER = "vertex"  # the laptop's Google Cloud row; the server's was `google-tts`, the same API
VOICE = "Fenrir"
LANGUAGE = "es"
LOCALE = "es-ES"
DIRECTION = "Calm and resolute, with a hint of defiance."
# prompts/acervo_pronounce_story.md at a3aec2f, filled the way speak.direction filled it then.
STYLE = (f"Read this Spanish passage from a short story aloud, as a storyteller would. {DIRECTION} "
         "Do not add, drop, translate or explain any words.")
FRAGMENT = "Sin mostrar ningún temor,"
NEXT = "decidió ponerse a cantar una vieja melodía popular a todo pulmón."
TEXTS = {"fragment": FRAGMENT, "joined": f"{FRAGMENT} {NEXT}"}
MODELS = ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-tts")
URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
PROOF = "835df230d449d853c2d93a8f33b13daf655a61cf5f2a9868f494bc66ad50ad46"


def proof() -> str:
    """The take key `pronunciation/takes.key` gave the original take, from the parameters above."""
    parts = (FRAGMENT, LANGUAGE, STYLE, "0", "google-tts", MODELS[0], VOICE)
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def body(text: str, model: str) -> dict:
    """`google_tts.speech`'s body at a3aec2f, but for the language code (see the docstring)."""
    return {
        "input": {"text": text, "prompt": STYLE},
        "voice": {"languageCode": LOCALE, "name": VOICE, "modelName": model},
        "audioConfig": {"audioEncoding": "LINEAR16"},
    }


def done() -> set[tuple[str, str, int]]:
    if not RESULTS.exists():
        return set()
    rows = [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line]
    return {(row["model"], row["text_kind"], row["take"]) for row in rows if "seconds" in row}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--takes", type=int, default=10)
    args = parser.parse_args(argv)
    assert proof() == PROOF, "the parameters no longer give the original take's key"

    row = load_local().find(PROVIDER)
    OUT.mkdir(parents=True, exist_ok=True)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    have = done()
    with RESULTS.open("a", encoding="utf-8") as log:
        for model in MODELS:
            for kind, text in TEXTS.items():
                for take in range(args.takes):
                    if (model, kind, take) in have:
                        continue
                    started = time.monotonic()
                    record = {"model": model, "text_kind": kind, "take": take, "text": text}
                    try:
                        response = google_auth.post(row, model, URL, body(text, model), 120)
                        data = base64.b64decode(response.json()["audioContent"])
                    except Exception as error:  # noqa: BLE001 — the sentence is the finding
                        record["error"] = f"{type(error).__name__}: {error}"
                    else:
                        path = OUT / f"{model}-{kind}-{take:02d}.wav"
                        path.write_bytes(data)
                        with soundfile.SoundFile(io.BytesIO(data)) as reading:
                            record["seconds"] = round(len(reading) / reading.samplerate, 3)
                        record["file"] = path.name
                    record["call_s"] = round(time.monotonic() - started, 2)
                    log.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log.flush()
                    print(record.get("seconds", record.get("error")), model, kind, take, flush=True)


if __name__ == "__main__":
    main()
