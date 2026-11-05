"""Does a model cut a story part into passages without changing a word of it?

The narration call asks a text model to return one part as a list of segments, each with a direction
for the voice. The voice then speaks the segments and they are joined into one recording, so the one
thing that must not happen is the model quietly rewriting the story on the way. This runs the real
prompt against a real model on real stories and counts how often it does.

For each call it records:

- **strict** — the segments' `text` joined with one space equal the part exactly;
- **loose** — equal once every run of whitespace is one space (a line break turned into a space);
- **tiled** — what `narrate.tile` had to do: passages it could not find in the text (`dropped`) and
  stretches of the text no passage covered (`filled`). Zero and zero is a clean answer;
- the number of segments, their length, and whether every one carries a direction.

    set -a; . ./.env; set +a
    .venv/bin/python experiments/story-audio-segmentation/run.py --runs 5 --label v1

Stories are read from `stories_audio_followup.txt`, the five the owner generated. A run takes one
part of each story, rotating through the parts, so 5 runs × 5 stories = 25 calls covers every part.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from acervo.models.local import load_local  # noqa: E402
from acervo.models import call, chain  # noqa: E402
from acervo.stories import narrate  # noqa: E402

HERE = Path(__file__).resolve().parent
PROMPT = ROOT / "prompts" / "acervo_story_narrate.md"
SOURCE = ROOT / "stories_audio_followup.txt"
LANGUAGES = {"es": "Spanish", "en": "English"}


def stories() -> list[dict]:
    """The five stories after the `---` line in the brief: `N · Heading` then the text."""
    body = SOURCE.read_text().split("\n---\n", 1)[1]
    found = []
    for block in re.split(r"\n---\n", body):
        parts = re.findall(r"^\d+ · (.+)\n(.+)$", block.strip(), flags=re.M)
        if not parts:
            continue
        language = "en" if re.search(r"\bthe\b", parts[0][1]) else "es"
        found.append({"language": language, "parts": [{"heading": h, "text": t.strip()} for h, t in parts]})
    return found


def normal(text: str) -> str:
    return " ".join(text.split())


def once(candidate: chain.Candidate, template: str, language: str, text: str) -> dict:
    request = narrate.build_request(language_name=LANGUAGES[language], text=text)
    prompt = f"{template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"
    started = time.monotonic()
    row = {"seconds": None, "error": None}
    try:
        result = call.text(prompt, row=candidate.row, model=candidate.model, as_json=True,
                           params=narrate.NARRATE_PARAMS)
    except Exception as error:  # noqa: BLE001 - a measurement records every failure and goes on
        row["error"] = f"{type(error).__name__}: {error}"[:300]
        row["seconds"] = round(time.monotonic() - started, 1)
        return row
    row["seconds"] = round(time.monotonic() - started, 1)
    row["reply"] = result.text
    try:
        segments = narrate.parse_reply(result.parsed)
    except ValueError as error:
        row["error"] = f"unusable: {error}"
        return row
    joined = " ".join(segment.text for segment in segments)
    tiled = narrate.tile(text, segments)
    row.update(
        segments=len(segments),
        strict=joined == text,
        loose=normal(joined) == normal(text),
        dropped=tiled.dropped, filled=tiled.filled,
        directed=sum(1 for one in segments if one.direction),
        mean_words=round(sum(len(one.text.split()) for one in segments) / len(segments), 1),
        directions=[one.direction for one in segments],
        texts=[one.text for one in segments],
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--label", default="run")
    parser.add_argument("--chain", default="gemini-api")
    parser.add_argument("--pause", type=float, default=7.0, help="seconds between calls")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many calls")
    parser.add_argument("--prompt", default=str(PROMPT))
    args = parser.parse_args()

    candidates = chain.resolve("text", [one.strip() for one in args.chain.split(",")], load_local())
    if not candidates:
        print("No usable pair. Is GEMINI_API_KEY exported?", file=sys.stderr)
        return 2
    candidate = candidates[0]
    template = Path(args.prompt).read_text()

    results = []
    calls = 0
    for run in range(args.runs):
        for number, story in enumerate(stories(), 1):
            index = run % len(story["parts"])
            part = story["parts"][index]
            if args.limit and calls >= args.limit:
                break
            outcome = once(candidate, template, story["language"], part["text"])
            calls += 1
            outcome.update(run=run + 1, story=number, part=index + 1, language=story["language"],
                           words=len(part["text"].split()))
            results.append(outcome)
            verdict = ("ERROR " + outcome["error"][:70]) if outcome["error"] else (
                f"{'strict' if outcome['strict'] else 'loose ' if outcome['loose'] else 'CHANGED'}"
                f"  segs={outcome['segments']:>2} dropped={outcome['dropped']} filled={outcome['filled']}"
                f" directed={outcome['directed']}")
            print(f"run {run + 1} story {number} part {index + 1}: {verdict}  ({outcome['seconds']}s)")
            time.sleep(args.pause)

    good = [r for r in results if not r["error"]]
    print(f"\n{args.label}: {len(results)} calls, {len(results) - len(good)} errors")
    for name in ("strict", "loose"):
        print(f"  {name:<7} {sum(1 for r in good if r[name])}/{len(good)}")
    print(f"  clean tile (dropped 0, filled 0): {sum(1 for r in good if not r['dropped'] and not r['filled'])}/{len(good)}")
    print(f"  passages dropped: {sum(r['dropped'] for r in good)}   text filled: {sum(r['filled'] for r in good)}")
    (HERE / f"results-{args.label}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
