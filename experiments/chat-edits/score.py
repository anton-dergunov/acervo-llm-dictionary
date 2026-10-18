"""Re-judge stored answers, and report what they add up to. Spends nothing.

Rescoring runs every stored answer through its own arm's shaping and `applyOps` again, then through
the case's current check — so a check corrected after the fact costs no model call, and an answer is
always judged by the code it would actually have met.

    .venv/bin/python experiments/chat-edits/score.py runs/final              # rescore and report
    .venv/bin/python experiments/chat-edits/score.py runs/final --pair before after
    .venv/bin/python experiments/chat-edits/score.py runs/final --replay-checker after-applyops

`--replay-checker` judges one arm's stored answers with another build of the device code, which is
how the change to the rewrite rule is measured without asking the model anything.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

import dataset
import run

HERE = Path(__file__).resolve().parent


def rescore(run_dir: Path, arms: dict[str, run.Arm], checker_override: Path | None) -> list[dict[str, Any]]:
    cases = dataset.by_id()
    checkers = {name: run.Checker(checker_override or arm.checker) for name, arm in arms.items()}
    records: list[dict[str, Any]] = []
    try:
        for name, arm in arms.items():
            for path in sorted((run_dir / name).glob("*.json")):
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("status") != "ok" or record["case"] not in cases:
                    continue
                case = cases[record["case"]]
                body = run.body_for(case)
                shaped = run.shape(arm, record["parsed"], body)
                proposal = (shaped.get("shaped") or {}).get("proposal")
                applied = run.apply(checkers[name], case, proposal["ops"] if proposal else None)
                verdict = run.judge(case, checkers[name], shaped, applied)
                if checker_override is None:
                    record["shaped"] = shaped
                    record["applied"] = {k: v for k, v in applied.items() if k not in ("draft", "yaml")}
                    record["verdict"] = verdict
                    record["final"] = record["repairs"][-1]["verdict"] if record.get("repairs") else verdict
                    run.write(path, record)
                records.append({**record, "verdict": verdict, "split": case.split,
                                "category": case.category})
    finally:
        for checker in checkers.values():
            checker.close()
    return records


def rate(rows: Sequence[dict[str, Any]], key: str = "verdict") -> str:
    if not rows:
        return "—"
    passed = sum(1 for row in rows if row[key]["pass"])
    return f"{passed}/{len(rows)} ({100 * passed / len(rows):.0f}%)"


def mcnemar(pairs: Sequence[tuple[bool, bool]]) -> str:
    """Exact two-sided McNemar on paired pass/fail: only the discordant pairs carry information."""
    b = sum(1 for one, other in pairs if one and not other)
    c = sum(1 for one, other in pairs if other and not one)
    n = b + c
    if n == 0:
        return "no discordant pairs"
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / 2 ** n
    return f"discordant {b} vs {c}, exact p = {min(1.0, 2 * tail):.4f}"


def report(records: Sequence[dict[str, Any]], pair: Sequence[str] | None) -> None:
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_arm[record["arm"]].append(record)
    for name, rows in by_arm.items():
        print(f"\n## {name}: first attempt {rate(rows)}")
        for split in ("replay", "dev", "held"):
            print(f"  {split:7s} {rate([r for r in rows if r['split'] == split])}")
        print("  by category:")
        for category in sorted({r["category"] for r in rows}):
            print(f"    {category:12s} {rate([r for r in rows if r['category'] == category])}")
        failures = Counter(r["verdict"].get("failure") for r in rows if not r["verdict"]["pass"])
        print("  failures:", ", ".join(f"{k} {v}" for k, v in failures.most_common()) or "none")
        minor = Counter(m.split(":")[0] for r in rows for m in r["verdict"].get("minor") or [])
        if minor:
            print("  minor:", ", ".join(f"{k} {v}" for k, v in minor.most_common()))
        repaired = [r for r in rows if r.get("repairs")]
        if repaired:
            # A turn sent back ends with its last repair's verdict; any other ends with its first,
            # as rescored just now — never a verdict stored by an older run of the code.
            final = sum(1 for r in rows if (r["repairs"][-1]["verdict"] if r.get("repairs") else r["verdict"])["pass"])
            print(f"  after repair: {final}/{len(rows)} ({100 * final / len(rows):.0f}%), "
                  f"{sum(len(r['repairs']) for r in repaired)} repair call(s) on {len(repaired)} turn(s)")
        for r in rows:
            if not r["verdict"]["pass"]:
                print(f"    ✗ {r['case']} r{r['repeat']}: {r['verdict'].get('failure')} — "
                      f"{(r['verdict'].get('why') or '')[:160]}")
    if pair:
        one, other = pair
        index = {(r["case"], r["repeat"]): r for r in by_arm.get(other, [])}
        matched = [(r["verdict"]["pass"], index[(r["case"], r["repeat"])]["verdict"]["pass"])
                   for r in by_arm.get(one, []) if (r["case"], r["repeat"]) in index]
        print(f"\n## {one} → {other}, paired on (case, repeat), n = {len(matched)}: {mcnemar(matched)}")
        for split in ("replay", "dev", "held"):
            sub = [(r["verdict"]["pass"], index[(r["case"], r["repeat"])]["verdict"]["pass"])
                   for r in by_arm.get(one, []) if r["split"] == split and (r["case"], r["repeat"]) in index]
            if sub:
                print(f"  {split:7s} {sum(a for a, _ in sub)}/{len(sub)} → {sum(b for _, b in sub)}/{len(sub)}"
                      f"  ({mcnemar(sub)})")


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--arm", action="append", dest="arms")
    parser.add_argument("--pair", nargs=2)
    parser.add_argument("--replay-checker", help="a bundle name in build/, e.g. worktree")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute() and not run_dir.exists():
        run_dir = HERE / run_dir
    names = args.arms or sorted(p.name for p in run_dir.iterdir() if p.is_dir())
    arms = {name: run.Arm(name) for name in names}
    override = run.BUILD / f"checker-{args.replay_checker}.mjs" if args.replay_checker else None
    report(rescore(run_dir, arms, override), args.pair)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
