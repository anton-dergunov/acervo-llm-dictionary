"""The owner's labels against each rule: what it flags, how many of those are really wrong, and cost.

    experiments/take-verification/.venv/bin/python experiments/take-verification/report.py

Reads `out/labels.json` (the listening page's), `out/listen.json` (why each card was there) and the
signals, and writes `results/report.md`, `results/summary.json` and a copy of the labels as
`results/labels.json`, keyed by clip and stripped of anything but the verdict, the faults and the
note. Precision is `wrong / (wrong + right)` over the flagged clips the owner judged; an `unsure`
counts on neither side and is reported. Every clip the loosest point flags for small or base is on
the page, so for those two models every cell of the grid is fully judged; turbo listened to the
page's clips and a random sample only, and is reported on those.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from sweep import CERS, GAPS, flagged, signals

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results"


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def main() -> None:
    labels = load(OUT / "labels.json", {})
    cards = {card["key"]: card for card in load(OUT / "listen.json", [])}
    verdict = {key: label.get("verdict") for key, label in labels.items() if label.get("verdict")}
    wrong = sorted(key for key, value in verdict.items() if value == "wrong")
    lines = ["# Take verification: results", "",
             f"{len(verdict)} of {len(cards)} clips judged: "
             f"{sum(1 for v in verdict.values() if v == 'wrong')} wrong, "
             f"{sum(1 for v in verdict.values() if v == 'right')} right, "
             f"{sum(1 for v in verdict.values() if v == 'unsure')} unsure.", ""]
    controls = [key for key, card in cards.items() if card["why"] == ["control"]]
    lines += [f"Controls (random clips the loosest rule passed): {len(controls)}, of which wrong: "
              f"{sum(1 for key in controls if verdict.get(key) == 'wrong')}.", ""]
    summary: dict = {"judged": len(verdict), "wrong": wrong, "models": {}, "rule": {}}
    lines += ["## The rule: words of the direction heard around the text", "",
              "Fires when Whisper hears, outside the text's own stretch, a word of the direction that was sent "
              "(`sweep.leak`). One row per model; precision from the labels.", "",
              "| model | clips | fired | wrong | right | unsure | unjudged |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for model in ("base", "small", "turbo"):
        if not (RESULTS / f"signals-{model}.jsonl").exists():
            continue
        rows = signals(model)
        fired = [row["key"] for row in rows if row["leak"]]
        count = {v: sum(1 for k in fired if verdict.get(k) == v) for v in ("wrong", "right", "unsure")}
        lines.append(f"| {model} | {len(rows)} | {len(fired)} | {count['wrong']} | {count['right']} | {count['unsure']} | "
                     f"{len(fired) - sum(count.values())} |")
        summary["rule"][model] = {"clips": len(rows), "fired": fired, **count}
    lines += ["", "## The first rule, rejected: distance and likelihood", "",
              "`twice OR instruction OR (cer_inner > τc AND gap > τg)`. It raises what an emotional delivery does to a "
              "transcript, which the owner judged right in every case.", ""]
    for model in ("base", "small", "turbo"):
        path = RESULTS / f"signals-{model}.jsonl"
        if not path.exists():
            continue
        rows = signals(model)
        partial = model == "turbo"
        by_key = {row["key"]: row for row in rows}
        lines += [f"## {model}" + (" (reference: the page's clips and a random sample)" if partial else ""), ""]
        lines += ["Each cell: flagged loop lines · wrong / right / unsure among them · precision.", "",
                  "| τc \\ τg | " + " | ".join(str(gap) for gap in GAPS) + " |",
                  "| --- | " + " | ".join("---" for _ in GAPS) + " |"]
        cells = {}
        for cer in CERS:
            row_cells = []
            for gap in GAPS:
                hit = [r["key"] for r in rows if r["kind"] == "take" and flagged(r, cer, gap)]
                w = sum(1 for k in hit if verdict.get(k) == "wrong")
                ri = sum(1 for k in hit if verdict.get(k) == "right")
                u = sum(1 for k in hit if verdict.get(k) == "unsure")
                precision = f"{w / (w + ri):.2f}" if w + ri else "–"
                cells[f"{cer}/{gap}"] = {"flagged": len(hit), "wrong": w, "right": ri, "unsure": u}
                row_cells.append(f"{len(hit)} · {w}/{ri}/{u} · {precision}")
            lines.append(f"| {cer} | " + " | ".join(row_cells) + " |")
        ranked = sorted((r for r in rows if r["kind"] == "take"), key=lambda r: (not r["structural"], -r["score"]))
        place = {r["key"]: n + 1 for n, r in enumerate(ranked)}
        lines += ["", "Where each clip judged wrong ranks (structural flags first, then cer × gap): " +
                  (", ".join(f"`{key}` {place.get(key, '–')}" for key in wrong) or "none judged wrong"), ""]
        decode = statistics.median(r["decode_s"] for r in rows)
        score = statistics.median(r["score_s"] for r in rows)
        lines += [f"Laptop (M1, MPS): median {decode:.2f} s to transcribe, {score:.2f} s to score the text.", ""]
        summary["models"][model] = {"cells": cells, "ranks": {key: place.get(key) for key in wrong},
                                    "laptop_decode_s": decode, "laptop_score_s": score,
                                    "clips": len(rows)}
        for key in wrong:
            row = by_key.get(key)
            if row:
                summary["models"][model].setdefault("wrong_signals", {})[key] = {
                    k: row[k] for k in ("heard", "cer", "gap", "dz", "twice", "instruction", "min_expected")}
    timing = [json.loads(line) for line in (RESULTS / "nas-timing.jsonl").read_text().splitlines() if line] \
        if (RESULTS / "nas-timing.jsonl").exists() else []
    if timing:
        lines += ["## On the NAS (AMD Ryzen R1600, inside the acervo-server image)", "",
                  "| engine | model | threads | loop line | word | story passage | load |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for t in timing:
            cell = lambda kind: (f"{t[kind]['median_s']:.2f} s (p90 {t[kind]['p90_s']:.2f}; audio {t[kind]['audio_median_s']} s)"
                                 if kind in t else "–")
            lines.append(f"| {t['engine']} | {t['model']} | {t['threads']} | {cell('take')} | {cell('word')} | "
                         f"{cell('story')} | {t['load_s']} s |")
        summary["nas"] = timing
    lines += ["", "## Judged wrong", ""]
    for key in wrong:
        card, label = cards.get(key, {}), labels[key]
        lines.append(f"- `{key}` «{card.get('text', '')}» ({card.get('lang', '')}; asked: {card.get('direction') or 'nothing'}) — "
                     f"{', '.join(label.get('faults') or []) or 'no fault named'}"
                     + (f"; “{label['note']}”" if label.get("note") else "") + f"; raised by {', '.join(card.get('why', []))}")
    (RESULTS / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    kept = {key: {k: v for k, v in label.items() if k in ("verdict", "faults", "note")} | {"why": cards.get(key, {}).get("why")}
            for key, label in labels.items()}
    (RESULTS / "labels.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    print((RESULTS / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
