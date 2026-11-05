#!/usr/bin/env python3
"""Spend money: two arms of one prompt, over a fixed word list, on real providers.

**Every pair is called directly rather than through `chain.walk`.** The chain exists to fall
through, and a fall-through would attribute one pair's answer to another and destroy the per-pair
measurement, which is the whole comparison.

**The request is the shipped one.** `build_user_message` assembles it and `draft_from` reads the
reply, so an arm is measured against the pipeline rather than against a copy of it. Only the system
prompt differs between arms, and each is read from `arms/` through the shipped section reader.

Jobs run **repeat-major**: every arm, pair and word once, then again. A run that dies half way
therefore has both arms equally sampled and still compares something.

Pacing is deliberately slack — well under every published ceiling — because this runs overnight,
where throughput is worth nothing and a tripped quota costs the night.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
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

# Well under what each provider publishes. Gemini's free tier documents 15/min and meters the
# credential rather than the model, so the gate is per ROW and set at eight.
RATE_PER_MINUTE = {"gemini-api": 8, "vertex": 6, "cloudflare": 4}
DEFAULT_RATE = 10

# A refused pair rests, doubling, and then parks: dribbling a biased subsample of one pair's answers
# into a comparison is worse than a smaller n that says so.
FIRST_REST = 30.0
LONGEST_REST = 600.0
MAX_RESTS = 5
RETRYABLE = ("rate_limited", "unavailable", "unreachable")

# The account this experiment is allowed to spend. Checked before anything is called, because
# `ACERVO_VERTEX_ACCOUNT` cannot do it: a user's application-default credentials do not say whose
# they are, and the organisation policy blocks the service-account key that would.
EXPECT_ACCOUNT = "REDACTED"
EXPECT_PROJECT = "REDACTED"


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
    """Every (row, model) the catalogue offers for text, with why a row cannot be called."""
    catalogue = load_local()
    out: list[dict[str, Any]] = []
    for row in catalogue.serving("text"):
        for model in row.models_for("text"):
            out.append({
                "provider": row.id, "model": model, "row": row,
                "available": row.available, "reason": row.reason(),
            })
    return out


def chosen_pairs(only: list[str] | None) -> list[dict[str, Any]]:
    everything = pairs()
    if not only:
        return everything
    picked: list[dict[str, Any]] = []
    for want in only:
        provider, _, model = want.partition(":")
        matches = [p for p in everything if p["provider"] == provider and (not model or p["model"] == model)]
        if not matches:
            raise SystemExit(f"no catalogue pair matches {want!r}")
        picked.extend(m for m in matches if m not in picked)
    return picked


def preflight(live: list[dict[str, Any]]) -> dict[str, Any]:
    """Refuse to spend on the wrong account. Returns what it checked, for the manifest."""
    checked: dict[str, Any] = {"expectedAccount": EXPECT_ACCOUNT, "expectedProject": EXPECT_PROJECT}
    if not any(p["provider"] in ("vertex", "google-cloud") for p in live):
        checked["skipped"] = "no Google row in this run"
        return checked
    if not shutil.which("gcloud"):
        raise SystemExit("gcloud is not on PATH, so the account cannot be verified")
    account = subprocess.run(["gcloud", "config", "get-value", "account"],
                             capture_output=True, text=True).stdout.strip()
    project = os.environ.get("ACERVO_VERTEX_PROJECT", "")
    token = subprocess.run(["gcloud", "auth", "application-default", "print-access-token"],
                           capture_output=True, text=True)
    checked |= {"account": account, "project": project, "adc": token.returncode == 0}
    if account != EXPECT_ACCOUNT:
        raise SystemExit(f"gcloud account is {account!r}, expected {EXPECT_ACCOUNT!r}")
    if project != EXPECT_PROJECT:
        raise SystemExit(f"ACERVO_VERTEX_PROJECT is {project!r}, expected {EXPECT_PROJECT!r}")
    if token.returncode != 0:
        raise SystemExit("no application-default credentials; run gcloud auth application-default login")
    return checked


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
    parser.add_argument("--pair", action="append", dest="only_pairs",
                        help="provider or provider:model; repeatable")
    parser.add_argument("--word", action="append", dest="only_words", help="word id; repeatable")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run", help="an existing run id, to resume or extend")
    parser.add_argument("--dry-run", action="store_true", help="print the matrix, spend nothing")
    parser.add_argument("--max-cost-usd", type=float, default=2.0)
    args = parser.parse_args()

    arms = args.arms or list(ARMS)
    words = dataset.words(args.only_words)
    selected = chosen_pairs(args.only_pairs)
    live = [p for p in selected if p["available"]]
    skipped = [p for p in selected if not p["available"]]
    jobs = matrix(words, arms, args.repeats)

    print(f"{len(jobs)} job(s) x {len(live)} credentialed pair(s) = {len(jobs) * len(live)} calls")
    for pair in live:
        print(f"  call  {pair['provider']:14s} {pair['model']}")
    for pair in skipped:
        print(f"  skip  {pair['provider']:14s} {pair['model']}  — {pair['reason']}")
    if args.dry_run:
        if live:
            print("preflight:", json.dumps(preflight(live), ensure_ascii=False))
        return 0
    if not live:
        print("nothing to call: no row in the catalogue has a credential here", file=sys.stderr)
        return 1

    checked = preflight(live)
    run_id = args.run or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write(run_dir / "manifest.json", {
        "runId": run_id, "started": now(),
        "options": {"arms": arms, "repeats": args.repeats,
                    "words": [w["id"] for w in words], "maxCostUsd": args.max_cost_usd},
        "arms": {name: {"sha256": arm_digest(name), "chars": len(arm_text(name))} for name in ARMS},
        "datasetSha256": dataset.digest(),
        "pairs": [{"provider": p["provider"], "model": p["model"], "available": p["available"],
                   "reason": p["reason"]} for p in selected],
        "preflight": checked,
    })

    gates = {p["provider"]: Pace(RATE_PER_MINUTE.get(p["provider"], DEFAULT_RATE),
                                cooldown=FIRST_REST, cap=LONGEST_REST) for p in live}
    system = {name: arm_text(name) for name in arms}
    parked: dict[str, int] = {}
    spent = 0.0
    done = skipped_existing = 0
    total = len(jobs) * len(live)

    for index, job in enumerate(jobs, start=1):
        for pair in live:
            key = f"{pair['provider']}:{pair['model']}"
            if parked.get(key, 0) >= MAX_RESTS:
                continue
            path = path_for(run_dir, job, pair)
            if path.exists():
                skipped_existing += 1
                continue
            record = ask(job, pair, system[job["arm"]], gates[pair["provider"]])
            # A retryable failure is deliberately NOT written: leaving no file is what lets a later
            # pass fill the cell, where a stored refusal would be mistaken for work already done and
            # the comparison would quietly lose that word on that pair.
            if record["ok"] or record.get("reason") not in RETRYABLE:
                write(path, record)
            done += 1
            spent += record.get("costUsd") or 0.0
            if record["ok"]:
                parked.pop(key, None)
                mark = "ok " if record["parsedJson"] else "BAD"
            else:
                parked[key] = parked.get(key, 0) + 1
                mark = record["reason"][:3].upper()
            print(f"[{done + skipped_existing:4d}/{total}] {mark} {job['arm']:6s} "
                  f"{job['wordId']:14s} r{job['repeat']} {key:44s} {record.get('seconds', 0):5.1f}s")
            if spent > args.max_cost_usd:
                print(f"\nstopping: ${spent:.4f} spent, ceiling ${args.max_cost_usd:.2f}", file=sys.stderr)
                return 2

    print(f"\n{done} call(s), {skipped_existing} already present, ${spent:.4f}")
    print(f"run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
