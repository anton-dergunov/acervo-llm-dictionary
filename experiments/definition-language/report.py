#!/usr/bin/env python3
"""Summarise a run: definitions in the wrong language per arm, model and set, into `<run>/report.md`.

    .venv/bin/python experiments/definition-language/report.py [--run runs/1]

A word counts as wrong when any of its senses is doubted or refused by `vet.definition_doubt`.
Arms are compared on the same words with an exact McNemar test on that per-word outcome.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent


def mcnemar(b: int, c: int) -> float:
    """Two-sided exact p for b and c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="runs/1")
    args = parser.parse_args(argv)
    run = HERE / args.run
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(run.glob("*/*/*.json"))]
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        groups[(record["set"], record["model"], record["arm"])].append(record)

    lines = [f"# Definition language: {args.run}", "",
             "| Set | Model | Arm | Words | Senses | Wrong senses (certain) | Words with one wrong | Cost |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for (which, model, arm), items in sorted(groups.items()):
        senses = sum(r["score"]["senses"] for r in items)
        wrong = sum(r["score"]["wrong"] for r in items)
        certain = sum(r["score"]["certain"] for r in items)
        words = sum(1 for r in items if r["score"]["wrong"])
        cost = sum(r.get("costUsd") or 0 for r in items)
        lines.append(f"| {which} | {model} | {arm} | {len(items)} | {senses} | {wrong} ({certain}) | "
                     f"{words} ({100 * words / max(1, len(items)):.0f}%) | ${cost:.3f} |")

    lines += ["", "## Per vocabulary (sample, words with one wrong)", ""]
    per: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
    for record in records:
        if record["set"] == "sample":
            cell = per[(record["model"], record["arm"], record["vocabulary"])]
            cell[0] += bool(record["score"]["wrong"])
            cell[1] += 1
    vocabularies = sorted({key[2] for key in per})
    lines.append("| Model | Arm | " + " | ".join(vocabularies) + " |")
    lines.append("| --- | --- | " + " | ".join("---:" for _ in vocabularies) + " |")
    for model, arm in sorted({key[:2] for key in per}):
        cells = [per.get((model, arm, v), [0, 0]) for v in vocabularies]
        lines.append(f"| {model} | {arm} | " + " | ".join(f"{a}/{b}" for a, b in cells) + " |")

    lines += ["", "## Paired comparisons (same words, per-word outcome)", ""]
    outcome = {(r["set"], r["model"], r["arm"], r["vocabulary"], r["headword"]): bool(r["score"]["wrong"])
               for r in records}
    for (which, model, arm) in sorted(groups):
        if arm == "before":
            continue
        pairs = [(outcome[k], outcome.get((which, model, "before", *k[3:])))
                 for k in outcome if k[:3] == (which, model, arm)]
        pairs = [(after, before) for after, before in pairs if before is not None]
        if not pairs:
            continue
        fixed = sum(1 for after, before in pairs if before and not after)
        broke = sum(1 for after, before in pairs if after and not before)
        lines.append(f"- {which}, {model}, before → {arm}: {fixed} fixed, {broke} broken over {len(pairs)} "
                     f"words; McNemar p = {mcnemar(fixed, broke):.2g}")

    (run / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
