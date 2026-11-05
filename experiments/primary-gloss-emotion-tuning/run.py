#!/usr/bin/env python3
"""Spend free-tier calls: two arms of one prompt, over a real+synthetic word list, on gemini-free.

**Single provider, on purpose.** This is a wording-tuning pass on `primaryGloss` and `emotion`, not
the ship/no-ship risk study `experiments/compose-lesson-line/` already ran and closed. It doesn't
need a paid pair or a blind judge — `pairs()` below is hard-restricted to `gemini-free` so a laptop
that also holds Vertex credentials never spends there by accident.

**Every call goes through `acervo.models.call.text` directly, never `chain.walk`.** The chain exists
to fall through to a different pair, which would attribute one arm's answer to a different model and
break the per-arm comparison — moot with one provider, but kept for consistency with
`compose-lesson-line/run.py`, which this file is adapted from.

**The request is the shipped one.** `build_user_message` assembles it and `draft_from` reads the
reply, so an arm is measured against the pipeline rather than a copy of it. Only the system prompt
differs between arms, read from `arms/` through the shipped section reader.

Jobs run **repeat-major**: every arm, pair and word once, then again, so an interrupted run is still
balanced.
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

import dataset

from acervo.models.local import load_local
from acervo.models import call
from acervo.models.errors import ProviderError
from acervo.models.pacing import Pace
from acervo.services.capture.compose import build_user_message

HERE = Path(__file__).resolve().parent
ARMS = ("before", "after")
TIMEOUT_SECONDS = 90.0
PROVIDER = "gemini-api"

# Gemini's free tier documents 15/min and meters the credential rather than the model.
RATE_PER_MINUTE = 8
FIRST_REST = 30.0
LONGEST_REST = 600.0
MAX_RESTS = 5
RETRYABLE = ("rate_limited", "unavailable", "unreachable")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def arm_text(name: str) -> str:
    """One arm, read as a whole file through the shipped reader.

    Read from `arms/` rather than through `prompt_text`, which caches by name: two arms cannot both
    be `acervo_compose` in one process.
    """
    from acervo.services.prompts import sections

    return sections((HERE / "arms" / f"{name}.md").read_text(encoding="utf-8").strip(), {}, name)


def arm_digest(name: str) -> str:
    return hashlib.sha256((HERE / "arms" / f"{name}.md").read_bytes()).hexdigest()


def pairs() -> list[dict[str, Any]]:
    """Only `gemini-free`'s text models — this experiment never calls a second provider."""
    catalogue = load_local()
    row = catalogue.find(PROVIDER)
    return [
        {"provider": row.id, "model": model, "row": row,
         "available": row.available, "reason": row.reason()}
        for model in row.models_for("text")
    ]


def chosen_pairs(only_model: str | None) -> list[dict[str, Any]]:
    everything = pairs()
    if not only_model:
        return everything[:1]  # the steadier of the two listed models, per the catalogue's own note
    matches = [p for p in everything if p["model"] == only_model]
    if not matches:
        raise SystemExit(f"gemini-free has no model {only_model!r}")
    return matches


def matrix(words: list[dict[str, Any]], arms: list[str], repeats: int) -> list[dict[str, Any]]:
    """Repeat-major, so an interrupted run is still balanced across arms."""
    jobs = []
    for repeat in range(repeats):
        for word in words:
            for arm in arms:
                jobs.append({"wordId": word["id"], "arm": arm, "repeat": repeat, "word": word})
    return jobs


def path_for(run_dir: Path, job: dict[str, Any], pair: dict[str, Any]) -> Path:
    slug = pair["model"].replace("/", "--").replace("@", "").replace(":", "-")
    return run_dir / job["arm"] / f"{pair['provider']}--{slug}" / f"{job['wordId']}--r{job['repeat']}.json"


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def ask(job: dict[str, Any], pair: dict[str, Any], system: str, gate: Pace) -> dict[str, Any]:
    """One call. Returns the record to store, whether it answered or not."""
    word = job["word"]
    resolution = dataset.resolution_for(word)
    request = dataset.request_for(word)
    vocabulary = dataset.vocabulary_for(word)
    message = build_user_message(resolution, request, vocabulary, dataset.topics())

    record: dict[str, Any] = {
        "wordId": word["id"], "language": word["language"], "headword": word["headword"],
        "category": word.get("category"), "source": word.get("source"),
        "arm": job["arm"], "repeat": job["repeat"],
        "provider": pair["provider"], "model": pair["model"],
        "requestChars": len(message) + len(system), "at": now(),
    }
    gate.acquire()
    started = time.monotonic()
    try:
        result = call.text(message, row=pair["row"], model=pair["model"], system=system,
                           as_json=True, timeout=TIMEOUT_SECONDS)
    except ProviderError as failure:
        if failure.reason == "rate_limited":
            gate.penalise()
        record |= {"ok": False, "reason": failure.reason, "detail": str(failure)[:400],
                   "seconds": round(time.monotonic() - started, 2)}
        return record
    gate.succeeded()
    record |= {
        "ok": True,
        "seconds": round(result.answer.seconds, 2),
        "costUsd": result.answer.cost_usd,
        "replyChars": len(result.text),
        "parsedJson": result.parsed is not None,
        "reply": result.parsed if result.parsed is not None else result.text,
        "warnings": list(result.answer.warnings),
        "answeredBy": f"{result.answer.provider_id}:{result.answer.model}",
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", dest="arms", choices=ARMS)
    parser.add_argument("--model", help="a specific gemini-free model id; default the first listed")
    parser.add_argument("--word", action="append", dest="only_words", help="word id; repeatable")
    parser.add_argument("--category", help="only words in this words.yaml category")
    parser.add_argument("--id-prefix", help="only word ids starting with this prefix")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--run", help="an existing run id, to resume or extend")
    parser.add_argument("--dry-run", action="store_true", help="print the matrix, spend nothing")
    args = parser.parse_args()

    arms = args.arms or list(ARMS)
    words = dataset.words(args.only_words, category=args.category)
    if args.id_prefix:
        words = [w for w in words if w["id"].startswith(args.id_prefix)]
    live = [p for p in chosen_pairs(args.model) if p["available"]]
    skipped = [p for p in chosen_pairs(args.model) if not p["available"]]
    jobs = matrix(words, arms, args.repeats)

    print(f"{len(jobs)} job(s) x {len(live)} credentialed pair(s) = {len(jobs) * len(live)} calls")
    for pair in live:
        print(f"  call  {pair['provider']:14s} {pair['model']}")
    for pair in skipped:
        print(f"  skip  {pair['provider']:14s} {pair['model']}  — {pair['reason']}")
    if args.dry_run:
        return 0
    if not live:
        print("nothing to call: gemini-free has no credential here", file=sys.stderr)
        return 1

    run_id = args.run or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write(run_dir / "manifest.json", {
        "runId": run_id, "started": now(),
        "options": {"arms": arms, "repeats": args.repeats,
                    "words": [w["id"] for w in words], "category": args.category},
        "arms": {name: {"sha256": arm_digest(name), "chars": len(arm_text(name))} for name in ARMS},
        "datasetSha256": dataset.digest(),
        "pairs": [{"provider": p["provider"], "model": p["model"], "available": p["available"],
                   "reason": p["reason"]} for p in live + skipped],
    })

    gates = {p["model"]: Pace(RATE_PER_MINUTE, cooldown=FIRST_REST, cap=LONGEST_REST) for p in live}
    system = {name: arm_text(name) for name in arms}
    parked: dict[str, int] = {}
    done = skipped_existing = 0
    total = len(jobs) * len(live)

    for job in jobs:
        for pair in live:
            key = f"{pair['provider']}:{pair['model']}"
            if parked.get(key, 0) >= MAX_RESTS:
                continue
            path = path_for(run_dir, job, pair)
            if path.exists():
                skipped_existing += 1
                continue
            record = ask(job, pair, system[job["arm"]], gates[pair["model"]])
            # A retryable failure is deliberately NOT written: leaving no file lets a later pass fill
            # the cell, where a stored refusal would be mistaken for work already done.
            if record["ok"] or record.get("reason") not in RETRYABLE:
                write(path, record)
            done += 1
            if record["ok"]:
                parked.pop(key, None)
                mark = "ok " if record["parsedJson"] else "BAD"
            else:
                parked[key] = parked.get(key, 0) + 1
                mark = record["reason"][:3].upper()
            print(f"[{done + skipped_existing:4d}/{total}] {mark} {job['arm']:6s} "
                  f"{job['wordId']:20s} r{job['repeat']} {key:32s} {record.get('seconds', 0):5.1f}s")

    print(f"\n{done} call(s), {skipped_existing} already present")
    print(f"run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
