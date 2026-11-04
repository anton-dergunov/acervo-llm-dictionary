#!/usr/bin/env python3
"""Spend free-tier calls: three arms of the reader section, over entries and stories, on Flash Lite.

    .venv/bin/python experiments/learner-context/run.py --dry-run
    .venv/bin/python experiments/learner-context/run.py --repeats 2
    .venv/bin/python experiments/learner-context/run.py --run <id> --repeats 3   # resume or extend

The arms differ only in what follows the prompt:

- `none`   today's prompt, with nothing about the learner;
- `light`  the shipped section, `acervo.services.reader.reader_section` — level firm, variety a
           preference, the note background;
- `plain`  the same three facts stated flatly, with none of the weighting. Here to show whether the
           weighting sentences do the work, or whether stating the note at all is what matters.

**The request is the shipped one.** An entry is `build_user_message` under `acervo_compose.md`, read
back by `draft_from`; a story is `stories.write.build_request` under `acervo_story_write.md`, laid
out as `StoryWriter` lays it out. The section is the one `with_reader` appends; the standing rules it
appends after are the owner's and are left out, so the arms differ by the section alone.

**One provider, one model, on purpose**: gemini-free's Flash Lite, the model these prompts are
written for (`docs/architecture/models.md`). Every call goes through `acervo.models.call.text`
directly, never a chain, so no answer is credited to a model that did not give it. Jobs run
repeat-major, so an interrupted run is still balanced. Replies are appended to the run's
`replies.jsonl`, one per line; a cell already there is never asked again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from acervo.models import call, load_catalogue
from acervo.models.catalogue import available, reason
from acervo.models.errors import ProviderError
from acervo.models.locales import language_name, region_name
from acervo.models.pacing import Pace
from acervo.services.capture.compose import build_user_message
from acervo.services.prompts import prompt_text
from acervo.services.reader import LEVELS, reader_section
from acervo.stories import write
from acervo.stories.types import story_types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROMPTS = ROOT / "prompts"
ARMS = ("none", "light", "plain")
PROVIDER = "gemini-free"
MODEL = "gemini/gemini-3.5-flash-lite"
STORY_TYPE = "funny"
STORY_PARTS = 4
TIMEOUT_SECONDS = 120.0
RATE_PER_MINUTE = 8
FIRST_REST = 30.0
LONGEST_REST = 600.0
MAX_RESTS = 5
RETRYABLE = ("rate_limited", "unavailable", "unreachable")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load() -> dict[str, Any]:
    return yaml.safe_load((HERE / "words.yaml").read_text(encoding="utf-8"))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def plain_section(vocabulary: dict[str, Any]) -> str:
    """The same facts as `reader_section`, said flatly: no order of weight, no caveat on the note."""
    language = language_name(vocabulary["language"])
    return "\n\n".join([
        "## The reader",
        f"Level in {language}: {vocabulary['level']} ({LEVELS[vocabulary['level']]}).\n"
        f"Variety: {language} of {region_name(vocabulary['region'])}.\n"
        f"About the reader: {vocabulary['learnerNote']}",
    ])


def section(arm: str, vocabulary: dict[str, Any]) -> str:
    if arm == "none":
        return ""
    return reader_section(vocabulary) if arm == "light" else plain_section(vocabulary)


def joined(template: str, arm: str, vocabulary: dict[str, Any]) -> str:
    """What `with_reader` makes of a template, for an owner with no standing rules."""
    text = section(arm, vocabulary)
    return f"{template}\n\n{text}" if text else template


# ── what is asked ───────────────────────────────────────────────────────────


def entry_message(word: dict[str, Any], vocabulary: dict[str, Any], topics: list[str]) -> str:
    resolution = {"language": word["language"], "headword": word["headword"], "lemma": word["lemma"],
                  "pos": word["pos"], "sentences": []}
    return build_user_message(resolution, {}, vocabulary, [{"name": name} for name in topics])


def story_request(story: dict[str, Any], words: dict[str, dict[str, Any]]) -> dict[str, Any]:
    kind = story_types()[STORY_TYPE]
    chosen = [words[word_id] for word_id in story["words"]]
    return write.build_request(
        language=story["language"], language_name=language_name(story["language"]),
        words=[{"id": word["id"], "headword": word["headword"], "lemma": word["lemma"], "pos": word["pos"],
                "gloss": "", "definition": ""} for word in chosen],
        story_type_brief=kind.brief, story_type_label=kind.label, parts=STORY_PARTS,
    )


def jobs(data: dict[str, Any], arms: list[str], repeats: int, kinds: list[str]) -> list[dict[str, Any]]:
    """Repeat-major, so an interrupted run is still balanced across arms."""
    found = []
    for repeat in range(repeats):
        if "entry" in kinds:
            found += [{"kind": "entry", "item": word, "arm": arm, "repeat": repeat}
                      for word in data["words"] for arm in arms]
        if "story" in kinds:
            found += [{"kind": "story", "item": story, "arm": arm, "repeat": repeat}
                      for story in data["stories"] for arm in arms]
    return found


# Every reply of a run, one JSON object per line, appended as it lands: one text file rather than a
# file per cell, and still diffable.
REPLIES = "replies.jsonl"


def cell(arm: str, kind: str, item_id: str, repeat: int) -> str:
    return f"{arm}/{kind}/{item_id}/r{repeat}"


def answered(run_dir: Path) -> set[str]:
    """The cells a run already holds, so a resumed run never asks them again."""
    path = run_dir / REPLIES
    if not path.exists():
        return set()
    return {cell(one["arm"], one["kind"], one["id"], one["repeat"])
            for one in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if one}


def append(run_dir: Path, record: dict[str, Any]) -> None:
    with (run_dir / REPLIES).open("a", encoding="utf-8") as replies:
        replies.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def ask(job: dict[str, Any], data: dict[str, Any], row: Any, gate: Pace) -> dict[str, Any]:
    item, arm = job["item"], job["arm"]
    vocabulary = data["vocabularies"][item["language"]]
    record: dict[str, Any] = {"kind": job["kind"], "id": item["id"], "language": item["language"],
                              "group": item["group"], "arm": arm, "repeat": job["repeat"],
                              "model": MODEL, "at": now()}
    if job["kind"] == "entry":
        record["headword"] = item["headword"]
        system = joined(prompt_text(PROMPTS, "acervo_compose"), arm, vocabulary)
        message, params = entry_message(item, vocabulary, data["topics"]), None
        kwargs: dict[str, Any] = {"system": system}
    else:
        words = {word["id"]: word for word in data["words"]}
        record["headwords"] = [words[word_id]["headword"] for word_id in item["words"]]
        template = joined(prompt_text(PROMPTS, "acervo_story_write"), arm, vocabulary)
        request = story_request(item, words)
        message = f"{template}\n\n{write.HEADING}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"
        params, kwargs = write.WRITE_PARAMS, {}
    gate.acquire()
    started = time.monotonic()
    try:
        result = call.text(message, row=row, model=MODEL, as_json=True, timeout=TIMEOUT_SECONDS,
                           **({"params": params} if params else {}), **kwargs)
    except ProviderError as failure:
        if failure.reason == "rate_limited":
            gate.penalise()
        return record | {"ok": False, "reason": failure.reason, "detail": str(failure)[:400],
                         "seconds": round(time.monotonic() - started, 2)}
    gate.succeeded()
    return record | {
        "ok": True, "seconds": round(result.answer.seconds, 2), "parsedJson": result.parsed is not None,
        "reply": result.parsed if result.parsed is not None else result.text,
        "answeredBy": f"{result.answer.provider_id}:{result.answer.model}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", action="append", dest="arms", choices=ARMS)
    parser.add_argument("--kind", action="append", dest="kinds", choices=("entry", "story"))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--run", help="an existing run id, to resume or extend")
    parser.add_argument("--dry-run", action="store_true", help="print the matrix and one prompt, spend nothing")
    args = parser.parse_args(argv)

    data = load()
    arms, kinds = args.arms or list(ARMS), args.kinds or ["entry", "story"]
    matrix = jobs(data, arms, args.repeats, kinds)
    row = load_catalogue().find(PROVIDER)
    print(f"{len(matrix)} calls to {PROVIDER}:{MODEL}, about {len(matrix) / RATE_PER_MINUTE:.0f} minutes")
    if args.dry_run:
        for arm in ARMS:
            print(f"\n── {arm} ──\n{section(arm, data['vocabularies']['es']) or '(nothing appended)'}")
        return 0
    if not available(row):
        print(f"{PROVIDER} cannot be called here: {reason(row)}", file=sys.stderr)
        return 1

    run_id = args.run or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "manifest.json"
    if not manifest.exists():
        write_json(manifest, {
            "runId": run_id, "started": now(), "model": f"{PROVIDER}:{MODEL}",
            "words": digest((HERE / "words.yaml").read_text(encoding="utf-8")),
            "prompts": {name: digest(prompt_text(PROMPTS, name)) for name in ("acervo_compose", "acervo_story_write")},
            "sections": {arm: {language: section(arm, vocabulary) for language, vocabulary in data["vocabularies"].items()}
                         for arm in ARMS},
        })

    gate = Pace(RATE_PER_MINUTE, cooldown=FIRST_REST, cap=LONGEST_REST)
    rests = done = present = 0
    held = answered(run_dir)
    for index, job in enumerate(matrix, 1):
        if cell(job["arm"], job["kind"], job["item"]["id"], job["repeat"]) in held:
            present += 1
            continue
        record = ask(job, data, row, gate)
        # A retryable failure is not written: no file lets a later pass fill the cell, where a stored
        # refusal would read as work already done.
        if record["ok"] or record.get("reason") not in RETRYABLE:
            append(run_dir, record)
        done += 1
        if record["ok"]:
            rests = 0
            mark = "ok " if record["parsedJson"] else "BAD"
        else:
            rests += 1
            mark = record["reason"][:3].upper()
            if rests >= MAX_RESTS:
                print(f"{MAX_RESTS} failures in a row; stopping. Resume with --run {run_id}", file=sys.stderr)
                break
        print(f"[{index:4d}/{len(matrix)}] {mark} {job['arm']:5s} {job['kind']:5s} {job['item']['id']:22s} "
              f"r{job['repeat']} {record.get('seconds', 0):5.1f}s", flush=True)
    print(f"\n{done} call(s), {present} already present. run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
