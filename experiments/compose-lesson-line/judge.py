#!/usr/bin/env python3
"""Layer 2: a model reads two articles for the same word and says which is better.

Blind and **position-swapped**. Each pair is asked twice, once each way round, because a judge that
prefers whichever article it saw first is measuring the ordering rather than the articles. Where the
two orderings disagree the pair counts as *no difference*, and the flip rate is reported: it is this
instrument's own noise, and a high one invalidates the layer.

The judge is a Pro model and **not one of the arms**. Grading a model's own output is the strong
documented self-preference case, and one of the arm pairs is Vertex Flash. Family preference may
remain — every comparison is within one arm-model, both sides from the same one, so it largely
cancels — and `--judge` exists so a second family can check that.

A **cost pilot** runs first: ten calls, the real per-call cost printed, before the other three
hundred and fifty. A preview model's published rate is an assumption; `costUsd` is not.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import dataset
import render

from acervo.errors import ApiError
from acervo.models.local import load_local
from acervo.models import call
from acervo.models.errors import ProviderError
from acervo.models.pacing import Pace
from acervo.services.capture.draft import draft_from

HERE = Path(__file__).resolve().parent
COST_PILOT = 10

# Measured on 17 Sep 2026: five of sixteen unpaced calls at concurrency 2 came back 429. A preview
# Pro model has a small per-minute allowance, and overnight throughput is worth nothing, so the gate
# is set well under it and the retries are long.
JUDGE_PER_MINUTE = 6
RETRYABLE = ("rate_limited", "unavailable", "unreachable")
ATTEMPTS = 4

SYSTEM = """You compare two vocabulary articles written for the same word, for a learner who already
speaks the gloss language and is learning the word's language.

Judge only what is there to read. Which article would teach this word better?

Weigh, roughly in this order:
- whether the meanings that matter are covered, and whether a meaning is missing or invented
- whether the usage notes say something a dictionary would not, or are filler
- whether the examples are natural sentences a person would say, and earn their place
- whether the glosses and the definition are accurate and well chosen

Ignore: formatting, key order, field presence for its own sake, and length as such. A shorter article
that teaches better is better.

Answer with one JSON object and nothing else:

{"winner": "A" | "B" | "same",
 "magnitude": 1 | 2 | 3,
 "decidedBy": "senses" | "notes" | "examples" | "glosses" | "definitions",
 "reason": "one sentence, at most 25 words"}

`same` is a real answer and often the right one; use magnitude 1 for a slight difference, 3 for a
clear one, and 1 with `same` when they are equivalent."""


def draft_of(record: dict[str, Any], word: dict[str, Any]) -> dict[str, Any] | None:
    if not record.get("parsedJson") or not isinstance(record.get("reply"), dict):
        return None
    try:
        return draft_from(record["reply"], dataset.resolution_for(word), dataset.request_for(word),
                          dataset.vocabulary_for(word), dataset.topics(), record["model"])
    except ApiError:
        return None


def comparisons(run_dir: Path) -> list[dict[str, Any]]:
    """Every (word, repeat, pair) where both arms produced a readable article."""
    by_id = {word["id"]: word for word in dataset.words()}
    found: dict[tuple, dict[str, Any]] = {}
    for path in sorted(run_dir.rglob("*.json")):
        # `judged/<pair>/<file>.json`, so the parent is the pair directory and not "judged" — a
        # check on the parent's name passed on the first pass only because nothing was judged yet.
        if path.name in ("manifest.json", "summary.json") or "judged" in path.parts:
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if "wordId" not in record:
            continue
        key = (record["wordId"], record["repeat"], record["provider"], record["model"])
        found.setdefault(key, {})[record["arm"]] = record

    out = []
    for key, arms in sorted(found.items()):
        if set(arms) != {"before", "after"}:
            continue
        word = by_id[key[0]]
        drafts = {arm: draft_of(record, word) for arm, record in arms.items()}
        if not all(drafts.values()):
            continue
        out.append({
            "wordId": key[0], "repeat": key[1], "provider": key[2], "model": key[3],
            "headword": word["headword"], "language": word["language"],
            "text": {arm: render.as_yaml(drafts[arm], arms[arm].get("reply"), blind=True)
                     for arm in ("before", "after")},
        })
    return out


def jobs_for(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Both orderings of every comparison, so position bias is measured rather than assumed."""
    return [{**row, "order": order} for row in rows for order in ("ba", "ab")]


def judged_path(run_dir: Path, job: dict[str, Any]) -> Path:
    slug = job["model"].replace("/", "--").replace("@", "").replace(":", "-")
    return (run_dir / "judged" / f"{job['provider']}--{slug}"
            / f"{job['wordId']}--r{job['repeat']}--{job['order']}.json")


def ask(job: dict[str, Any], row: Any, model: str, timeout: float, gate: Pace) -> dict[str, Any]:
    left, right = ("before", "after") if job["order"] == "ba" else ("after", "before")
    message = (f"Word: {job['headword']} ({job['language']})\n\n"
               f"## Article A\n```yaml\n{job['text'][left]}\n```\n\n"
               f"## Article B\n```yaml\n{job['text'][right]}\n```")
    record = {k: job[k] for k in ("wordId", "repeat", "provider", "model", "order")}
    record |= {"leftArm": left, "rightArm": right}
    for attempt in range(ATTEMPTS):
        gate.acquire()
        try:
            result = call.text(message, row=row, model=model, system=SYSTEM,
                               as_json=True, timeout=timeout)
            gate.succeeded()
            break
        except ProviderError as failure:
            if failure.reason not in RETRYABLE or attempt == ATTEMPTS - 1:
                return record | {"ok": False, "retryable": failure.reason in RETRYABLE,
                                 "reason": failure.reason, "detail": str(failure)[:300]}
            time.sleep(gate.penalise())
    reply = result.parsed if isinstance(result.parsed, dict) else {}
    winner = str(reply.get("winner", "")).strip().upper()
    arm = {"A": left, "B": right}.get(winner) if winner in ("A", "B") else "same"
    return record | {
        "ok": True, "winnerSide": winner or None, "winnerArm": arm,
        "magnitude": reply.get("magnitude"), "decidedBy": reply.get("decidedBy"),
        "reason": reply.get("reason"), "seconds": round(result.answer.seconds, 2),
        "costUsd": result.answer.cost_usd,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--judge", default="gemini-3.1-pro-preview")
    parser.add_argument("--row", default="vertex", help="the provider in providers.local.json whose credential is used")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-cost-usd", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run)
    if not run_dir.is_absolute() and not run_dir.exists():
        run_dir = HERE / args.run
    rows = comparisons(run_dir)
    jobs = jobs_for(rows)
    pending = [job for job in jobs if not judged_path(run_dir, job).exists()]
    print(f"{len(rows)} comparison(s) x 2 orderings = {len(jobs)} calls; {len(pending)} still to make")
    print(f"judge: {args.judge} on the {args.row} row")
    if args.dry_run:
        return 0
    if not pending:
        return 0

    row = load_local().find(args.row)
    gate = Pace(JUDGE_PER_MINUTE, cooldown=30.0, cap=600.0)
    random.Random(7).shuffle(pending)
    spent, lock, stop = 0.0, threading.Lock(), threading.Event()
    done = 0

    def work(job: dict[str, Any]) -> None:
        nonlocal spent, done
        if stop.is_set():
            return
        record = ask(job, row, args.judge, args.timeout, gate)
        # A retryable failure is deliberately not written: leaving no file is what lets a second
        # pass pick it up, where a stored failure would be mistaken for work already done.
        if record["ok"] or not record.get("retryable"):
            path = judged_path(run_dir, job)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with lock:
            spent += record.get("costUsd") or 0.0
            done += 1
            mark = (record.get("winnerArm") or "?")[:6] if record["ok"] else record["reason"][:6]
            print(f"[{done:4d}/{len(pending)}] {mark:7s} {job['wordId']:14s} r{job['repeat']} "
                  f"{job['order']} ${spent:.4f}")
            if spent > args.max_cost_usd:
                print(f"stopping: ${spent:.4f} over ceiling ${args.max_cost_usd:.2f}", file=sys.stderr)
                stop.set()

    pilot, rest = pending[:COST_PILOT], pending[COST_PILOT:]
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(work, pilot))
    if done:
        each = spent / done
        print(f"\ncost pilot: ${each:.5f} a call, so {len(jobs)} calls project to ${each * len(jobs):.2f}")
        if each * len(jobs) > args.max_cost_usd:
            print("that is over the ceiling; raise --max-cost-usd deliberately or pick a cheaper judge",
                  file=sys.stderr)
            return 2
    if rest and not stop.is_set():
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            list(pool.map(work, rest))
    print(f"\n{done} judgement(s), ${spent:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
