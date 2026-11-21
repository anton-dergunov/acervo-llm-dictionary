"""Replace the starter drafts with the judge's corrected entries, where they pass compose's checks.

    cd experiments/compose-judge
    ../../.venv/bin/python apply.py --run full --dry-run   # what would change, and what is refused
    ../../.venv/bin/python apply.py --run full

For every article the run corrected (`runs/<run>/results.json`, `corrected` not null):

1. The corrected entry is completed with what the judge does not write: the word's emoji, emotion,
   lemma and topics, each sense's emoji (from the sense it `was`), an example's emotion where its
   text is unchanged.
2. It is checked as compose checks a model's answer (`compose_parts`, the same check the builder
   uses). A refusal keeps the original, and so does a doubt about the definitions' language: the
   translate step already put the original's definitions in the right language. A dictionary's
   doubt is accepted, as compose accepts it, and counted. How much the correction grew is recorded,
   never limited: the short originals are the ones a correction rightly lengthens
   (experiments/compose-judge/README.md, "Full run").
3. The draft is rebuilt by `draft_from`; a sense that `was` an original one keeps that sense's id, so
   the matches that name it stand. An unchanged example keeps its id and the model that wrote it;
   a new or changed one is credited to the judge's model.
4. The compose file keeps the draft it replaced (`draftBefore`) and the run's faults (`corrected`),
   so the raw model output, the correction and its reasons stay three separate layers (starter plan
   step 5). Each topic's match file has the senses' new definitions; a sense that is gone leaves it,
   a new sense joins it unmatched.

Applying twice is harmless: an article already corrected by the same run is skipped.
"""

from __future__ import annotations

import argparse
import collections
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import judge

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("starter_build", judge.ROOT / "scripts" / "starter" / "build.py")
build = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = build
_spec.loader.exec_module(build)

from acervo.services.models import Demoted, Unusable  # noqa: E402

CORRECTOR = f"vertex:{judge.MODEL}"


def prose_size(entry: dict[str, Any]) -> int:
    """Characters of everything a learner reads: the measure the growth limit is held to."""
    parts = [entry.get("shortGloss") or "", *(entry.get("notes") or [])]
    for sense in entry.get("senses") or []:
        parts.append(sense.get("definition") or "")
        parts += [term for gloss in sense.get("glosses") or [] for term in gloss.get("terms") or []]
        for example in sense.get("examples") or []:
            parts += [example.get("text") or "", example.get("translation") or "", example.get("note") or ""]
    return sum(len(str(part)) for part in parts)


def completed(corrected: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """The corrected entry in compose's answer shape, with the fields the judge does not write."""
    answer = copy.deepcopy(corrected)
    answer["headword"] = draft["headword"]
    answer["lemma"] = draft.get("lemma")
    answer.setdefault("dialect", draft.get("dialect"))
    answer["emoji"] = draft.get("emoji")
    answer["emotion"] = draft.get("emotion")
    answer["topics"] = list(draft.get("topics") or [])
    before = draft["senses"]
    spoken = {e["text"]: e for s in before for e in s.get("examples") or []}
    for sense in answer.get("senses") or []:
        was = sense.get("was")
        original = before[was] if isinstance(was, int) and 0 <= was < len(before) else None
        sense["emoji"] = original.get("emoji") if original else None
        if not sense.get("domain") and original:
            sense["domain"] = original.get("domain")
        for example in sense.get("examples") or []:
            kept = spoken.get(example.get("text"))
            example.setdefault("emotion", kept.get("emotion") if kept else None)
            example.setdefault("fromSentence", None)
            example.setdefault("note", None)
    return answer


def rebuilt(composed: dict[str, Any], answer: dict[str, Any], vocabulary: dict[str, Any]) -> dict[str, Any]:
    """`draft_from` on the checked answer, with the ids and credits that must carry over."""
    resolution = composed["request"]["resolution"]
    draft = build.draft_from(answer, resolution, composed["request"]["request"], build.record_for(vocabulary),
                             [], CORRECTOR)
    before = composed["draft"]
    draft["topics"] = list(before.get("topics") or [])
    examples_before = {e["text"]: e for s in before["senses"] for e in s.get("examples") or []}
    used: set[int] = set()
    for sense, raw in zip(draft["senses"], [s for s in answer["senses"] if str(s.get("definition") or "").strip()]):
        was = raw.get("was")
        if isinstance(was, int) and 0 <= was < len(before["senses"]) and was not in used:
            sense["id"] = before["senses"][was]["id"]
            used.add(was)
        for example in sense["examples"]:
            kept = examples_before.get(example["text"])
            if kept and kept.get("translation") == example.get("translation"):
                example["id"], example["modelId"] = kept["id"], kept.get("modelId")
    return draft


def update_matches(folder: Path, before: dict[str, Any], after: dict[str, Any], topic: str) -> None:
    """The topic's match file: new definitions for kept senses, none for gone ones, new ones unmatched."""
    path = folder / "match" / f"{topic}.json"
    if not path.exists():
        return  # matched by the next build run
    matched = json.loads(path.read_text(encoding="utf-8"))
    old_ids = {s["id"] for s in before["senses"]}
    now = {s["id"]: s for s in after["senses"]}
    kept = []
    for entry in matched["matches"]:
        if entry["id"] not in old_ids:
            kept.append(entry)
        elif entry["id"] in now:
            sense = now[entry["id"]]
            kept.append({**entry, "headword": after["headword"], "definition": sense["definition"],
                         "glosses": "; ".join(", ".join(g["terms"]) for g in sense["glosses"])})
    known = {entry["id"] for entry in kept}
    for sense in after["senses"]:
        if sense["id"] not in known:
            kept.append({"id": sense["id"], "headword": after["headword"], "pos": after["pos"],
                         "definition": sense["definition"],
                         "glosses": "; ".join(", ".join(g["terms"]) for g in sense["glosses"]), "concept": None})
    matched["matches"] = kept
    build.write_json(path, matched)


def apply(run: str, dry_run: bool) -> dict[str, Any]:
    results = judge.done_keys(run)
    manifest = json.loads((judge.run_dir(run) / "manifest.json").read_text())
    vocabularies = {v["id"]: v for v in build.load_vocabularies()[0]}
    concepts = {c.id: c for items in build.load_concepts().values() for c in items}
    outcome = collections.Counter()
    refused: list[dict[str, str]] = []
    doubts: collections.Counter[str] = collections.Counter()
    growth: list[float] = []
    for path in sorted(judge.CORPUS.glob("*/compose/*.json")):
        result = results.get(judge.ident(path.parent.parent.name, path.stem))
        if not result or not result["corrected"]:
            continue
        composed = json.loads(path.read_text(encoding="utf-8"))
        if (composed.get("corrected") or {}).get("run") == run:
            outcome["already"] += 1
            continue
        vocabulary = vocabularies[composed["vocabulary"]]
        before = composed["draft"]  # what the judge read
        answer = completed(result["corrected"], before)
        _, _, check = build.compose_parts(build.APP_PROMPTS, build.DICTIONARIES, composed["request"]["resolution"],
                                          composed["request"]["request"], build.record_for(vocabulary), [])
        try:
            checked = check(answer).answer
        except Demoted as doubt:
            if doubt.by == "language":
                refused.append({"key": path.stem, "vocabulary": composed["vocabulary"], "why": str(doubt)})
                outcome["refusedByLanguage"] += 1
                continue
            doubts[doubt.by] += 1
            checked = doubt.checked.answer  # a dictionary's doubt: compose would keep it too
        except Unusable as refusal:
            refused.append({"key": path.stem, "vocabulary": composed["vocabulary"], "why": str(refusal)})
            outcome["refusedByCheck"] += 1
            continue
        ratio = prose_size(checked) / max(1, prose_size(before))
        growth.append(ratio)
        after = rebuilt(composed, checked, vocabulary)
        outcome["applied"] += 1
        if dry_run:
            continue
        composed.setdefault("draftBefore", before)  # the composer's own draft, kept once
        composed["draft"] = after
        composed["corrected"] = {"run": run, "model": CORRECTOR, "rubric": manifest["rubric"], "at": judge.now(),
                                 "faults": result["faults"], "growth": round(ratio, 3)}
        build.write_json(path, composed)
        topic = concepts[composed["word"]["concepts"][0]].topic
        update_matches(path.parent.parent, before, after, topic)
    growth.sort()
    summary = {"run": run, **outcome, "acceptedWithDoubt": dict(doubts), "refused": refused,
               "growthMedian": round(growth[len(growth) // 2], 3) if growth else None,
               "growthMax": round(growth[-1], 3) if growth else None}
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    summary = apply(args.run, args.dry_run)
    if not args.dry_run:
        (judge.run_dir(args.run) / "applied.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "refused"}, ensure_ascii=False))
    for item in summary["refused"]:
        print(f"  kept the original: {item['vocabulary']} {item['key']}: {item['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
