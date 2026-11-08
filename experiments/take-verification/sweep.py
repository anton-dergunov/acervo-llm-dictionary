"""Thresholds against what they would flag, and the set of clips to listen to.

    experiments/take-verification/.venv/bin/python experiments/take-verification/sweep.py grid --model small
    experiments/take-verification/.venv/bin/python experiments/take-verification/sweep.py listen

The rule under test, per clip:

    flag = twice OR instruction OR (cer_inner > τc AND gap > τg)

`twice` and `instruction` are structural — the text came back doubled, or the direction was read
out — and fire whatever the scores. The pair is the precision guard: a transcript far from the text
only counts when Whisper also finds its own reading clearly likelier than the asked-for text
(`gap`), which is what an accent, a homophone or an emotional delivery does not do.

Both halves look only at the text's own stretch of the transcript (`check.contained`): a voice that
wraps the word in an exclamation — «Pfff, bancarse.», «Oh, frivolous.» — is doing what the owner
wants, so `cer_inner` is the distance from the closest run of the transcript's words, and the gap is
`gap_span`, scored with Whisper's own words around the text kept, where `check.py --rescore` has
computed it (every clip it could change). What lies outside is `extra`; `long_extra` — more added
words than the text has, and at least four — is tried as a separate term, for an addition that is
neither a doubling nor the direction. A duration
outlier (`dz`, the clip's seconds per expected character as a robust z-score within its kind and
language) is reported beside it and tried as a fourth term.

`grid` prints what each threshold flags, per kind. `listen` writes `out/listen.json`, the cards for
the page, shuffled, with why each is there kept out of it (see `listen`).
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from check import GIVEAWAYS, STOP, contained, plain

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results"
CERS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8)
GAPS = (0.25, 0.5, 0.75, 1.0, 1.5)
DURATIONS = (3.0, 4.0, 5.0)


def manifest() -> dict[str, dict]:
    rows = [json.loads(line) for line in (OUT / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return {f"{row['kind']}/{row['id']}": row for row in rows}


@functools.lru_cache(maxsize=None)
def signals(model: str) -> list[dict]:
    path = RESULTS / f"signals-{model}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    directions = {key: clip["direction"] for key, clip in manifest().items()}
    span_path = RESULTS / f"span-{model}.jsonl"
    spans = {json.loads(line)["key"]: json.loads(line) for line in
             (span_path.read_text(encoding="utf-8").splitlines() if span_path.exists() else []) if line}
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        row["pace"] = math.log(max(row["seconds"], 0.05) / max(len("".join(plain(row["text"]))), 1))
        groups[(row["kind"], row["lang"])].append(row["pace"])
    centre = {group: (statistics.median(values), statistics.median(abs(v - statistics.median(values)) for v in values) or 0.1)
              for group, values in groups.items()}
    for row in rows:
        middle, spread = centre[(row["kind"], row["lang"])]
        row["dz"] = round((row["pace"] - middle) / (1.4826 * spread), 2)
        said, text = set(plain(row["heard"])), set(plain(row["text"]))
        row["added"] = sorted(said - text)
        row["structural"] = bool(row["twice"] or row["instruction"])
        span = spans.get(row["key"]) or contained(row["heard"], row["text"], row["lang"])
        row["cer_inner"], row["extra"] = span["cer_inner"], span["extra"]
        row["gap_whole"] = row["gap"]
        if row["key"] in spans:
            row["gap"] = spans[row["key"]]["gap_span"]
        row["long_extra"] = len(row["extra"]) >= 4 and len(row["extra"]) > len(plain(row["text"]))
        row["leak"] = leak(row["extra"], row["text"], directions.get(row["key"], ""))
        row["score"] = round(min(row["cer_inner"], 1.5) * max(row["gap"], 0.0), 4)
    return rows


def leak(extra: list[str], text: str, direction: str) -> list[str]:
    """**The rule the owner's labels settled**: words heard around the text that came from its
    direction — the direction read out («Seek relief from irritation in the throat») or one word of
    it said after the text («to provide more», asked as "a helpful host offering more food"). An
    exclamation, a laugh or an emotional delivery is never in the direction, so it never fires; and
    it needs no list of exclamations in any language, only the direction that was sent."""
    asked = {word for word in plain(direction) if len(word) >= 3 and word not in STOP} | GIVEAWAYS
    said = set(plain(text))
    return sorted({word for word in extra if word in asked and word not in said})


def flagged(row: dict, cer: float, gap: float, duration: float | None = None, extra: bool = False) -> bool:
    return row["structural"] or (row["cer_inner"] > cer and row["gap"] > gap) or \
        (duration is not None and abs(row["dz"]) > duration) or (extra and row["long_extra"])


def flagged_whole(row: dict, cer: float, gap: float) -> bool:
    """The first rule, before exclamations were allowed: the whole transcript, the whole gap."""
    return row["structural"] or (row["cer"] > cer and row["gap_whole"] > gap)


def grid(model: str) -> None:
    rows = signals(model)
    kinds = sorted({row["kind"] for row in rows})
    print(f"{model}: {len(rows)} clips", {kind: sum(1 for r in rows if r["kind"] == kind) for kind in kinds})
    print("structural:", {kind: sum(1 for r in rows if r["kind"] == kind and r["structural"]) for kind in kinds})
    print("τc \\ τg  " + "  ".join(f"{gap:>14}" for gap in GAPS))
    for cer in CERS:
        cells = []
        for gap in GAPS:
            counts = [sum(1 for r in rows if r["kind"] == kind and flagged(r, cer, gap)) for kind in kinds]
            cells.append("/".join(str(c) for c in counts))
        print(f"{cer:<8} " + "  ".join(f"{cell:>14}" for cell in cells))
    print("(counts are " + "/".join(kinds) + ")")
    print("long extra:", {kind: sum(1 for r in rows if r["kind"] == kind and r["long_extra"] and not r["structural"]) for kind in kinds})
    print("whole-transcript rule at the loosest point:",
          {kind: sum(1 for r in rows if r["kind"] == kind and flagged_whole(r, CERS[0], GAPS[0])) for kind in kinds})
    for duration in DURATIONS:
        print(f"|dz| > {duration}:", {kind: sum(1 for r in rows if r["kind"] == kind and abs(r["dz"]) > duration) for kind in kinds})


def listen() -> None:
    """The cards. Every clip the loosest point raises is too many to hear (a few hundred), so the page
    holds what each cheap model raises at a middle point, everything structural or long-extra, the
    duration outliers, six exclamation cases the first rule raised and this one passes (expected
    right, which is the owner's ruling being checked), and random controls both rules passed."""
    clips = manifest()
    chosen: dict[str, set[str]] = defaultdict(set)
    passed: set[str] = set()
    exclaimed: list[str] = []
    for model, (cer, gap) in (("small", (0.4, 0.75)), ("base", (0.5, 1.0))):
        rows = signals(model)
        for row in rows:
            if flagged(row, cer, gap, extra=True):
                chosen[row["key"]].add(f"{model}:{cer}/{gap}")
            elif model == "small" and row["extra"] and flagged_whole(row, CERS[0], GAPS[0]) and row["cer_inner"] == 0:
                exclaimed.append(row["key"])
        for kind in ("take", "word", "story"):
            for row in sorted((r for r in rows if r["kind"] == kind), key=lambda r: -abs(r["dz"]))[:3]:
                chosen[row["key"]].add(f"{model}:duration")
        passed |= {row["key"] for row in rows if row["kind"] == "take" and not flagged(row, CERS[0], GAPS[0], extra=True)
                   and not flagged_whole(row, CERS[0], GAPS[0])}
    for key in random.Random(3).sample(sorted(set(exclaimed) - set(chosen)), 6):
        chosen[key].add("exclamation")
    passed -= set(chosen)
    for key in random.Random(11).sample(sorted(passed), 12):
        chosen[key].add("control")
    cards = []
    for key, why in chosen.items():
        clip = clips[key]
        cards.append({"key": key, "kind": clip["kind"], "path": clip["path"], "text": clip["text"],
                      "lang": clip["tag"], "direction": clip["direction"], "why": sorted(why)})
    random.Random(5).shuffle(cards)
    (OUT / "listen.json").write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "listen-keys.txt").write_text("\n".join(card["key"] for card in cards) + "\n", encoding="utf-8")
    print(len(cards), "cards:", dict(Counter(tag.split(":")[-1] for card in cards for tag in card["why"])))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=("grid", "listen", "rule"))
    parser.add_argument("--model", default="small")
    args = parser.parse_args()
    {"grid": lambda: grid(args.model), "listen": listen, "rule": lambda: rule(args.model)}[args.what]()


def rule(model: str) -> None:
    rows = signals(model)
    hits = [row for row in rows if row["leak"]]
    print(f"{model}: the direction-leak rule fires on {len(hits)} of {len(rows)} clips")
    for row in hits:
        print(f"  {row['kind']} {row['leak']} | {row['text']} | {row['heard'][:80]}")


if __name__ == "__main__":
    main()
