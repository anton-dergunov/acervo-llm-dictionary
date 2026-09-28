"""Ask real models, one (provider, model) pair at a time, and write down what came back.

Two modes over one prompt, both through the shipped `build_request` and `parse_reply`, so what is
measured is the pipeline rather than a copy of it:

- **translate** — one sense, one candidate. The passage is almost certainly picked, so there is a
  translation to score. This is where coverage is measured.
- **select** — two senses and a pool of candidates. Nothing is scored for coverage here; the
  question is only whether the rewrite made the selector *pick more*, since the prompt's first rule
  is that refusing is a success and a wordier translation section must not cost that.

**Every pair is called directly rather than through `chain.walk`.** The chain exists to fall
through, and a fall-through would attribute one pair's answer to another and destroy the per-pair
measurement — which is the whole comparison.

Jobs run **repeat-major**: every arm and pair once, then again. A run that dies half way through
therefore has both arms equally sampled and still compares something.

    .venv/bin/python experiments/clip-translation/run.py --dry-run
    .venv/bin/python experiments/clip-translation/run.py --arm before
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import dataset

from acervo.clips.select import build_request, parse_reply
from acervo.models import call, load_catalogue
from acervo.models.catalogue import available, reason
from acervo.models.errors import ProviderError, ProviderUnavailable
from acervo.services.prompts import sections

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
ARMS = HERE / "arms"

# The shipped default. `selfContainedOnly` is the other experiment's knob
# (`docs/plans/quality/clip-selection.md`) and is deliberately not varied here.
OPTIONS = {"selfContainedOnly": False}


def slug(model: str) -> str:
    return model.replace("/", "-").replace("@", "").strip("-")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def arm_text(arm: str) -> str:
    raw = (ARMS / f"{arm}.md").read_text(encoding="utf-8")
    return sections(raw, OPTIONS)


def pairs() -> list[dict[str, Any]]:
    """Every (row, model) the catalogue offers for text, with why a row cannot be called.

    Per pair rather than per row, for the reason `tests/integration/test_models_live.py` gives: a
    row's second model is listed so the first one's 429 has somewhere to go, and it is measured here
    for the same reason it is tested there.
    """
    catalogue = load_catalogue()
    out = []
    for row in catalogue.serving("text"):
        for model in row.models_for("text"):
            out.append({"provider": row.id, "model": model, "row": row,
                        "available": available(row), "reason": reason(row)})
    return out


def jobs(mode: str, arms: Sequence[str], repeats: int,
         only: Sequence[str] | None) -> list[dict[str, Any]]:
    passages = [p for p in dataset.load() if not only or p.id in only]
    out = []
    for repeat in range(1, repeats + 1):
        for arm in arms:
            for passage in passages:
                for target in passage.targets:
                    if mode == "select" and target != passage.targets[0]:
                        continue        # one target is enough to ask "did it pick?"
                    out.append({"mode": mode, "arm": arm, "passageId": passage.id,
                                "targetLang": target, "repeat": repeat})
    return out


def request_for(job: dict[str, Any], passages: dict[str, dataset.Passage],
                everything: Sequence[dataset.Passage]) -> tuple[Any, list, str]:
    passage = passages[job["passageId"]]
    target = job["targetLang"]
    if job["mode"] == "translate":
        article = dataset.article_for(passage, target, with_decoy=False)
        candidates = [dataset.candidate_for(passage)]
    else:
        article = dataset.article_for(passage, target, with_decoy=True)
        candidates = dataset.pool_for(passage, everything)
    return article, candidates, target


def path_for(run_dir: Path, job: dict[str, Any], pair: dict[str, Any]) -> Path:
    return (run_dir / job["mode"] / job["arm"] / f"{pair['provider']}--{slug(pair['model'])}"
            / f"{job['passageId']}--{job['targetLang']}--r{job['repeat']}.json")


def write(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def ask(prompt: str, pair: dict[str, Any], article, candidates,
        attempts: int = 3) -> dict[str, Any]:
    """One pair, one call, with the same backoff curve `ClipSelector.select` uses.

    A pair that is still rate limited after three tries is reported as such and **parked** by the
    caller: dribbling a biased subsample of one pair's answers into the comparison is worse than a
    smaller n that says so.
    """
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result = call.text(prompt, row=pair["row"], model=pair["model"], as_json=True,
                               timeout=call.SHORT_TIMEOUT_SECONDS)
        except ProviderUnavailable as unavailable:
            if unavailable.reason == "rate_limited" and attempt < attempts:
                time.sleep(min(15.0 * 2 ** (attempt - 1), 240.0))
                continue
            return {"status": "rate_limited" if unavailable.reason == "rate_limited" else "error",
                    "reason": unavailable.reason, "detail": str(unavailable),
                    "seconds": round(time.perf_counter() - started, 2)}
        except ProviderError as error:
            return {"status": "error", "reason": getattr(error, "reason", "refused"),
                    "detail": str(error), "seconds": round(time.perf_counter() - started, 2)}

        record: dict[str, Any] = {
            "status": "ok",
            "replyChars": len(result.text or ""),
            "reply": {"text": result.text, "parsed": result.parsed},
            "answer": {"seconds": round(result.answer.seconds, 2),
                       "costUsd": result.answer.cost_usd,
                       "warnings": list(result.answer.warnings),
                       "model": result.answer.model, "provider": result.answer.provider_id},
        }
        # `parse_reply` is a *measurement* here, never allowed to abort the row: what the shipped
        # chain would call unusable is one of the things being compared between arms.
        try:
            selections, dropped = parse_reply(result.parsed, article, candidates)
            record["parseReply"] = {"ok": True, "error": None, "dropped": dropped}
        except ValueError as unusable:
            record["parseReply"] = {"ok": False, "error": str(unusable), "dropped": None}
            selections = []
        # Taken from the raw payload rather than from `parse_reply`, which silently nulls a
        # `matchedTranslationForm` that is not verbatim — and how often that happens is a number
        # this experiment wants rather than a detail it can afford to lose.
        raw = result.parsed if isinstance(result.parsed, dict) else {}
        by_sense = {str(entry.get("senseId")): entry for entry in (raw.get("senses") or [])
                    if isinstance(entry, dict)}
        record["selections"] = [{
            "senseId": selection.sense_id,
            "segmentId": selection.candidate.segment_id,
            "translation": selection.translation,
            "matchedTranslationForm": selection.matched_translation_form,
            "matchedTranslationFormRaw": (by_sense.get(selection.sense_id) or {})
                .get("matchedTranslationForm"),
        } for selection in selections]
        return record
    return {"status": "rate_limited", "reason": "rate_limited", "detail": "out of attempts"}


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("translate", "select"), default="translate")
    parser.add_argument("--arm", action="append", dest="arms",
                        help="repeatable; defaults to before and after")
    parser.add_argument("--pair", action="append", dest="only_pairs",
                        help="provider or provider:model; repeatable")
    parser.add_argument("--passage", action="append", dest="only_passages", help="repeatable")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run", help="an existing run id, to resume or extend")
    parser.add_argument("--dry-run", action="store_true", help="print the job matrix, spend nothing")
    parser.add_argument("--max-cost-usd", type=float, default=2.0)
    args = parser.parse_args(argv)

    arms = args.arms or ["before", "after"]
    for arm in arms:
        if not (ARMS / f"{arm}.md").exists():
            print(f"no such arm: {arm}", file=sys.stderr)
            return 2

    available_pairs = pairs()
    chosen = available_pairs
    if args.only_pairs:
        wanted = set(args.only_pairs)
        chosen = [p for p in available_pairs
                  if p["provider"] in wanted or f"{p['provider']}:{p['model']}" in wanted]
    live = [p for p in chosen if p["available"]]
    skipped = [p for p in chosen if not p["available"]]

    matrix = jobs(args.mode, arms, args.repeats, args.only_passages)
    print(f"{len(matrix)} jobs × {len(live)} credentialed pairs = {len(matrix) * len(live)} calls")
    for pair in live:
        print(f"  call  {pair['provider']:14s} {pair['model']}")
    for pair in skipped:
        print(f"  skip  {pair['provider']:14s} {pair['model']}  — {pair['reason']}")
    if args.dry_run:
        return 0
    if not live:
        print("nothing to call: no row in the catalogue has a credential here", file=sys.stderr)
        return 1

    run_id = args.run or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    templates = {arm: arm_text(arm) for arm in arms}
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "runId": run_id, "started": datetime.now(timezone.utc).isoformat(),
        "options": OPTIONS, "modes": [],
    }
    manifest["modes"] = sorted(set(manifest.get("modes", []) + [args.mode]))
    manifest["arms"] = {arm: {"sha256": digest((ARMS / f"{arm}.md").read_text(encoding="utf-8")),
                              "renderedChars": len(templates[arm])} for arm in arms}
    manifest["shippedPromptSha256"] = digest(
        (HERE.parents[1] / "prompts/acervo_clip_select.md").read_text(encoding="utf-8"))
    manifest["datasetSha256"] = digest(dataset.PASSAGES.read_text(encoding="utf-8"))
    manifest["pairs"] = [{k: v for k, v in pair.items() if k != "row"} for pair in chosen]
    manifest["repeats"] = args.repeats
    write(manifest_path, manifest)

    passages = dataset.by_id()
    everything = dataset.load()
    parked: set[str] = set()
    spent = 0.0
    done = failed = 0

    for job in matrix:
        article, candidates, target = request_for(job, passages, everything)
        request = build_request(article, candidates, target)
        for pair in live:
            key = f"{pair['provider']}:{pair['model']}"
            if key in parked:
                continue
            path = path_for(run_dir, job, pair)
            if path.exists():
                try:
                    if json.loads(path.read_text())["status"] in {"ok", "error"}:
                        continue        # resume; a rate-limited job is retried
                except (ValueError, KeyError):
                    pass
            prompt = (f"{templates[job['arm']]}\n\n"
                      f"{json.dumps(request, ensure_ascii=False, indent=2)}\n")
            outcome = ask(prompt, pair, article, candidates)
            record = {"schema": 1, "runId": run_id, **job,
                      "provider": pair["provider"], "model": pair["model"],
                      "armSha256": manifest["arms"][job["arm"]]["sha256"],
                      "promptChars": len(prompt), **outcome}
            write(path, record)
            cost = ((outcome.get("answer") or {}).get("costUsd")) or 0.0
            spent += cost
            if outcome["status"] == "ok":
                done += 1
                picked = len(outcome.get("selections", []))
                print(f"  {job['arm']:6s} {pair['provider']:11s} {job['passageId']:22s} "
                      f"{target} r{job['repeat']} — {picked} picked, "
                      f"{outcome['answer']['seconds']}s")
            else:
                failed += 1
                print(f"  {job['arm']:6s} {pair['provider']:11s} {job['passageId']:22s} "
                      f"{target} r{job['repeat']} — {outcome['status']}: {outcome['reason']}")
                if outcome["status"] == "rate_limited":
                    parked.add(key)
                    print(f"       parking {key} for the rest of this run")
            if spent > args.max_cost_usd:
                print(f"stopping: ${spent:.2f} spent, over the ${args.max_cost_usd:.2f} ceiling")
                return 1

    print(f"\n{done} answered, {failed} did not, ${spent:.4f} reported spent")
    print(f"run: {run_dir}")
    print(f"next: .venv/bin/python {Path(__file__).name} --mode select   # the refusal guard")
    print(f"      PYTHONPATH={HERE} .venv/bin/python {HERE}/score.py {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
