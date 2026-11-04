#!/usr/bin/env python3
"""Score a run: what each arm wrote, measured without a judge.

    .venv/bin/python experiments/learner-context/score.py runs/<id>

Writes `summary.json` and `report.md` into the run directory. Every number is computed from the
stored replies, so scoring again costs nothing. The hand labels that check the keyword measure are
`review.py`'s, scored there.

What is measured, per arm:

- **Leakage** — the share of examples on *unrelated* words, and of story parts in unrelated stories,
  that are about the learner's note (a stem from the vocabulary's `leak` list appears in the sentence
  or its translation). The gate: `light` no more than 10%, and no more than 5 points above `none`.
  Also: entries with more than one such example, and notes that mention it.
- **Uptake** — the same on *related* words: here the note may show, and `light` should not suppress it.
- **Variety** (Spanish, Argentina) — of examples addressed to "you", the share in *vos* forms; whether
  an entry for a word that differs by region names Argentina's form; whether it still says what is
  said elsewhere; examples that swap the headword for Argentina's word (the headword erased from its
  own entry); and `dialect` set on a word that is not regional.
- **Level** — words per example, and the share longer than 14 words.
- **Format** — replies that parse and that the shipped reader (`draft_from`) accepts.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from acervo.services.capture.draft import draft_from

HERE = Path(__file__).resolve().parent
ARMS = ("none", "light", "plain")

# Addressed to "you" in Argentina's forms, and in the forms Argentina does not use. Matched on the
# text as written, accents and case kept: folding would make `sabés` and `sabes` one word, and
# lower-casing would make the name Tomás a verb. `tomás` is left out for that reason.
VOS = re.compile(r"\b(vos|sos|tenés|querés|sabés|podés|hacés|decís|venís|vivís|comés|hablás|"
                 r"mirá|vení|decime|escuchame|fijate|andá|tomá|poné|salí|dormís|pintás|cogés|agarrás|"
                 r"manejás|necesitás|pensás|llevás|traés|ponés)\b")
TU = re.compile(r"\b(tú|tienes|quieres|sabes|puedes|eres|haces|dices|vienes|vives|comes|hablas|"
                r"dime|escúchame|fíjate|duermes|pintas|coges|agarras|conduces|necesitas|piensas|"
                r"llevas|traes|pones|vosotros|vosotras|tenéis|queréis|sabéis|podéis)\b")
ELSEWHERE = ("spain", "espana", "peninsul", "castil", "latin america", "elsewhere", "other countries",
             "mexico", "most of", "regional", "rioplatense", "argentin")


def fold(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(ch) != "Mn")


def leaks(text: str, stems: list[str]) -> bool:
    folded = fold(text)
    return any(fold(stem) in folded for stem in stems)


def records(run: Path) -> list[dict[str, Any]]:
    """Every reply of a run, from its `replies.jsonl`, in a fixed order."""
    lines = (run / "replies.jsonl").read_text(encoding="utf-8").splitlines()
    return sorted((json.loads(line) for line in lines if line.strip()),
                  key=lambda one: (one["arm"], one["kind"], one["id"], one["repeat"]))


def examples_of(reply: dict[str, Any]) -> list[dict[str, Any]]:
    return [example for sense in reply.get("senses") or [] if isinstance(sense, dict)
            for example in sense.get("examples") or [] if isinstance(example, dict) and example.get("text")]


def whole_text(reply: dict[str, Any]) -> str:
    """Everything an entry says, for "does it mention …" questions."""
    parts = [*map(str, reply.get("notes") or [])]
    for sense in reply.get("senses") or []:
        if not isinstance(sense, dict):
            continue
        parts.append(str(sense.get("definition") or ""))
        parts += [term for gloss in sense.get("glosses") or [] for term in (gloss.get("terms") or [])]
        for example in sense.get("examples") or []:
            parts += [str(example.get("text") or ""), str(example.get("translation") or ""), str(example.get("note") or "")]
    return "\n".join(parts)


def accepted(record: dict[str, Any], data: dict[str, Any]) -> bool:
    """Whether the shipped reader takes the reply as an entry."""
    word = next(word for word in data["words"] if word["id"] == record["id"])
    vocabulary = data["vocabularies"][word["language"]]
    resolution = {"language": word["language"], "headword": word["headword"], "lemma": word["lemma"],
                  "pos": word["pos"], "sentences": []}
    try:
        draft_from(record["reply"], resolution, {}, vocabulary, [{"name": name} for name in data["topics"]], "experiment")
    except Exception:  # noqa: BLE001 — any refusal is a reply the pipeline would not keep
        return False
    return True


def share(hits: int, total: int) -> dict[str, Any]:
    return {"hits": hits, "of": total, "share": round(hits / total, 3) if total else None}


def score(run: Path) -> dict[str, Any]:
    data = yaml.safe_load((HERE / "words.yaml").read_text(encoding="utf-8"))
    words = {word["id"]: word for word in data["words"]}
    tallies: dict[str, dict[str, list[int]]] = {arm: defaultdict(lambda: [0, 0]) for arm in ARMS}
    lengths: dict[str, dict[str, list[int]]] = {arm: defaultdict(list) for arm in ARMS}
    stories: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def count(arm: str, key: str, hit: bool) -> None:
        tallies[arm][key][0] += int(hit)
        tallies[arm][key][1] += 1

    for record in records(run):
        arm = record["arm"]
        language = record["language"]
        stems = data["vocabularies"][language]["leak"]
        count(arm, f"format.{record['kind']}.answered", bool(record.get("ok") and record.get("parsedJson")))
        if not (record.get("ok") and isinstance(record.get("reply"), dict)):
            continue
        reply = record["reply"]
        if record["kind"] == "story":
            parts = [str(part.get("text") or "") for part in reply.get("parts") or [] if isinstance(part, dict)]
            leaked = [leaks(part, stems) for part in parts]
            for hit in leaked:
                count(arm, f"story.{record['group']}.{language}.parts", hit)
            count(arm, f"story.{record['group']}.{language}.stories", any(leaked))
            if language == "es":
                for part in parts:
                    if VOS.search(part) or TU.search(part):
                        count(arm, "variety.story.vos", bool(VOS.search(part)) and not TU.search(part))
            stories[arm].append({"id": record["id"], "repeat": record["repeat"], "parts": parts})
            continue

        word = words[record["id"]]
        group = word["group"]
        count(arm, "format.entry.accepted", accepted(record, data))
        examples = examples_of(reply)
        flagged = [leaks(f"{one.get('text', '')} {one.get('translation', '')}", stems) for one in examples]
        for hit in flagged:
            count(arm, f"leak.{group}.{language}.examples", hit)
        count(arm, f"leak.{group}.{language}.entries-any", any(flagged))
        count(arm, f"leak.{group}.{language}.entries-over-one", sum(flagged) > 1)
        count(arm, f"leak.{group}.{language}.notes", any(leaks(str(note), stems) for note in reply.get("notes") or []))
        for one in examples:
            lengths[arm][language].append(len(str(one["text"]).split()))
        # A word that is not regional, marked as if it were.
        if group != "variety":
            count(arm, f"variety.false-dialect.{language}", bool(reply.get("dialect")))
        if language == "es":
            for one in examples:
                sentence = str(one["text"])
                if VOS.search(sentence) or TU.search(sentence):
                    count(arm, "variety.examples.vos", bool(VOS.search(sentence)) and not TU.search(sentence))
        if group == "variety":
            everything = fold(whole_text(reply))
            count(arm, "variety.names-argentina-form", any(fold(form) in everything for form in word["variety_forms"]))
            notes = fold(" ".join(map(str, reply.get("notes") or [])) + " " + " ".join(
                str(one.get("note") or "") for one in examples))
            count(arm, "variety.says-what-is-said-elsewhere", any(mark in notes for mark in ELSEWHERE))
            for one in examples:
                text, matched = fold(str(one["text"])), fold(str(one.get("matchedForm") or ""))
                swapped = any(fold(form) in text for form in word["variety_forms"]) and not (matched and matched in text)
                count(arm, "variety.headword-swapped-out", swapped)

    summary: dict[str, Any] = {"run": run.name, "arms": {}}
    for arm in ARMS:
        measured = {key: share(*value) for key, value in sorted(tallies[arm].items())}
        for language, values in lengths[arm].items():
            if values:
                measured[f"level.{language}.words-per-example"] = round(sum(values) / len(values), 1)
                measured[f"level.{language}.over-14-words"] = share(sum(v > 14 for v in values), len(values))
        if measured:
            summary["arms"][arm] = measured

    return summary


def hand_labels(labels: dict[str, Any], key: dict[str, Any]) -> dict[str, Any]:
    """The reviewer's labels, unblinded: their leak rate per arm, and agreement with the keywords."""
    per_arm: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    slang: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    both = [[0, 0], [0, 0]]  # [keyword][person]
    for item_id, label in labels.items():
        item = key.get(item_id)
        if not item or label.get("about") is None:
            continue
        person = bool(label["about"])
        per_arm[item["arm"]][0] += int(person)
        per_arm[item["arm"]][1] += 1
        both[int(item["keyword"])][int(person)] += 1
        if label.get("slang") is not None:
            slang[item["arm"]][0] += int(bool(label["slang"]))
            slang[item["arm"]][1] += 1
    total = sum(map(sum, both))
    agree = (both[0][0] + both[1][1]) / total if total else None
    expected = (((both[0][0] + both[0][1]) * (both[0][0] + both[1][0]) + (both[1][0] + both[1][1]) * (both[0][1] + both[1][1]))
                / total ** 2) if total else None
    kappa = round((agree - expected) / (1 - expected), 3) if total and expected != 1 else None
    return {
        "aboutTheNote": {arm: share(*value) for arm, value in per_arm.items()},
        "slangWhereItDoesNotBelong": {arm: share(*value) for arm, value in slang.items()},
        "keywordAgainstPerson": {"table[keyword][person]": both, "agreement": round(agree, 3) if agree is not None else None,
                                 "kappa": kappa},
    }


def report(summary: dict[str, Any]) -> str:
    arms = [arm for arm in ARMS if arm in summary["arms"]]
    keys = sorted({key for arm in arms for key in summary["arms"][arm]})

    def cell(value: Any) -> str:
        if isinstance(value, dict):
            return "—" if value["share"] is None else f"{value['share'] * 100:.0f}% ({value['hits']}/{value['of']})"
        return str(value)

    lines = [f"# Run {summary['run']}", "", "| Measure | " + " | ".join(arms) + " |", "| --- |" + " --- |" * len(arms)]
    for key in keys:
        lines.append(f"| {key} | " + " | ".join(cell(summary["arms"][arm].get(key, "")) for arm in arms) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(__doc__.splitlines()[2].strip(), file=sys.stderr)
        return 2
    run = Path(args[0])
    run = run if run.is_absolute() or run.exists() else HERE / run
    summary = score(run)
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run / "report.md").write_text(report(summary), encoding="utf-8")
    print(report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
