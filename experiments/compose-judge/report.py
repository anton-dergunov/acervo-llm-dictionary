"""Aggregate a judge run into the failure inventory a later session designs fixes from.

    cd experiments/compose-judge
    ../../.venv/bin/python judge.py export --run full     # runs/full/faults.jsonl
    ../../.venv/bin/python report.py --run full           # runs/full/report.md, runs/full/report.json

`report.md` is written to be read first, top to bottom: how much is wrong, which kinds of fault
weigh most (the severities summed, so a 3 counts as 3 and a 2 as 2), where (per vocabulary, per
composing model), what each looks like (quoted), and the kinds the judge named itself (`new:`). `report.json` holds the article keys behind every number, so a fix can be tried on
exactly the articles that show a fault: `report.json["keys"][category][vocabulary]`.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path
from typing import Any

import judge

EXAMPLES = 6


def load(run: str) -> list[dict[str, Any]]:
    path = judge.run_dir(run) / "faults.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def table(header: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] + ["---:"] * (len(header) - 1)) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def report(run: str) -> tuple[str, dict[str, Any]]:
    articles = load(run)
    rng = random.Random(1)
    per_vocabulary = collections.Counter(a["vocabulary"] for a in articles)
    per_model = collections.Counter(a["composer"] for a in articles)
    weight: collections.Counter[str] = collections.Counter()
    severe: collections.Counter[str] = collections.Counter()
    count: collections.Counter[str] = collections.Counter()
    by_vocabulary: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    by_model: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    keys: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    quotes: dict[str, list[str]] = collections.defaultdict(list)
    for article in articles:
        seen = set()
        for fault in article["faults"]:
            category = str(fault.get("category"))
            severity = fault.get("severity") if fault.get("severity") in (2, 3) else 2
            weight[category] += severity
            severe[category] += severity == 3
            count[category] += 1
            quotes[category].append(f"{article['vocabulary']} **{article['headword']}** ({fault.get('path')}, "
                                    f"{severity}): “{fault.get('quote', '')}” — {fault.get('why', '')}")
            if category not in seen:
                by_vocabulary[category][article["vocabulary"]] += 1
                by_model[category][article["composer"]] += 1
                keys[category][article["vocabulary"]].append(article["key"])
                seen.add(category)

    total = len(articles)
    with_severe = sum(1 for a in articles if any(f.get("severity") == 3 for f in a["faults"]))
    with_any = sum(1 for a in articles if a["faults"])
    corrected = sum(1 for a in articles if a["corrected"])
    lines = [f"# Judge run `{run}`: the failure inventory", "",
             f"{total} articles judged. **{with_severe} ({100 * with_severe / max(1, total):.0f}%) have a "
             f"severity-3 fault** (a learner would learn something false, or misses an everyday meaning); "
             f"{with_any} ({100 * with_any / max(1, total):.0f}%) have a listed fault of severity 2 or 3; "
             f"{corrected} ({100 * corrected / max(1, total):.0f}%) were corrected at all, minor polish included.",
             "", "## Per vocabulary", ""]
    rows = []
    for vocabulary in sorted(per_vocabulary):
        mine = [a for a in articles if a["vocabulary"] == vocabulary]
        rows.append([vocabulary, len(mine),
                     f"{100 * sum(any(f.get('severity') == 3 for f in a['faults']) for a in mine) / len(mine):.0f}%",
                     f"{100 * sum(bool(a['faults']) for a in mine) / len(mine):.0f}%",
                     f"{sum(len(a['faults']) for a in mine) / len(mine):.2f}"])
    lines += table(["vocabulary", "articles", "with a 3", "with a 2 or 3", "faults an article"], rows)
    lines += ["", "## Per composing model", ""]
    rows = []
    for model in sorted(per_model):
        mine = [a for a in articles if a["composer"] == model]
        rows.append([model, len(mine),
                     f"{100 * sum(any(f.get('severity') == 3 for f in a['faults']) for a in mine) / len(mine):.0f}%",
                     f"{sum(len(a['faults']) for a in mine) / len(mine):.2f}"])
    lines += table(["model", "articles", "with a 3", "faults an article"], rows)

    ranked = [c for c, _ in weight.most_common()]
    known = [c for c in ranked if not c.startswith("new:")]
    lines += ["", "## Kinds of fault, by weight (severity summed)", ""]
    rows = []
    for category in known:
        worst = sorted(by_vocabulary[category].items(), key=lambda kv: -kv[1] / per_vocabulary[kv[0]])[:4]
        rows.append([f"`{category}`", weight[category], count[category], severe[category],
                     f"{100 * sum(by_vocabulary[category].values()) / max(1, total):.1f}%",
                     ", ".join(f"{v} {100 * n / per_vocabulary[v]:.0f}%" for v, n in worst),
                     " / ".join(f"{m.replace('gemini-', '')} {100 * by_model[category][m] / per_model[m]:.0f}%"
                                for m in sorted(per_model))])
    lines += table(["kind", "weight", "faults", "of them 3", "articles", "worst vocabularies (share of their articles)",
                    "per composer (share)"], rows)

    lines += ["", "## Each kind, quoted", ""]
    for category in known:
        lines += [f"### `{category}` — {count[category]} faults, {severe[category]} of them severity 3", ""]
        lines += [f"- {quote}" for quote in rng.sample(quotes[category], min(EXAMPLES, len(quotes[category])))]
        lines.append("")

    new = [c for c in ranked if c.startswith("new:")]
    lines += ["## Kinds the judge named itself", "",
              "Not in the closed set. Similar names are the same kind under different words; merge them by reading.", ""]
    rows = [[f"`{c}`", count[c], severe[c], quotes[c][0]] for c in new]
    lines += table(["name", "faults", "of them 3", "first instance"], rows) if rows else ["None."]

    data = {"run": run, "articles": total, "withSevere": with_severe, "withAny": with_any, "corrected": corrected,
            "weight": dict(weight), "count": dict(count), "severe": dict(severe),
            "keys": {c: dict(per) for c, per in keys.items()}}
    return "\n".join(lines) + "\n", data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    text, data = report(args.run)
    (judge.run_dir(args.run) / "report.md").write_text(text, encoding="utf-8")
    (judge.run_dir(args.run) / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
