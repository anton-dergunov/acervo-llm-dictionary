"""Count what can be found wrong in composed articles without asking any model.

    .venv/bin/python experiments/compose-audit/audit.py              # data/starter → audit.json, report.md
    .venv/bin/python experiments/compose-audit/audit.py --selftest   # each counter on cases it must and must not flag

Reads every `data/starter/<vocabulary>/compose/*.json` (the starter builder's raw layer: request,
replies, verdicts, draft) and counts, per vocabulary and per model, the failures a rule can decide:
the ones compose's checks now refuse or coerce (`services/capture/vet.py`), and signals that only
point a judge at an article (no examples, an example whose word is not marked, a note that restates
the gloss). `audit.json` lists the flagged word keys per counter; `report.md` is the table.

The README says what each counter found the first time, and which of them compose now prevents.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acervo.grammatical_gender import gender_for  # noqa: E402
from acervo.services.capture.vet import (  # noqa: E402
    GENDERED_POS, garbled, ipa_of_lemma, reading_for, wrong_script,
)

CORPUS = ROOT / "data" / "starter"

# What a note says when it only restates the gender or the gloss. Signals for a judge, not checks:
# "el mapa is masculine even though it ends in -a" is worth saying and matches too.
RESTATES_GENDER = re.compile(r"\b(is|are) (masculine|feminine|neuter)\b|\bso (you )?(use|say) ['‘\"]?"
                             r"(el|la|le|der|die|das|il|o|a|het|de)\b", re.I)
RESTATES_MEANING = re.compile(r"^(note that )?(\S+ )?(means|is the (standard|most common|common|basic)"
                              r"( way| word| term| verb)?)\b", re.I)

COUNTERS = {
    # what compose now prevents
    "garbled": "a word written in two scripts (prose fields)",
    "example-script": "an example not in the word's script",
    "headword-rewritten": "the draft's headword is not the one compose was given",
    "reading-form": "a reading compose would now drop or rewrite",
    "ipa-article": "ipa transcribes the article as well as the lemma",
    "gender-misplaced": "a gender the language or the part of speech does not have",
    # signals for the judge
    "single-sense": "one sense",
    "no-examples": "no example at all",
    "example-unmarked": "an example with no marked word (matchedForm null)",
    "note-gender": "a note restating the gender",
    "note-meaning": "a note restating the meaning",
    "no-notes": "no notes",
    "ipa-null": "no ipa (Mandarin excluded: it is derived)",
}


def prose(draft: dict[str, Any]) -> Iterable[str]:
    yield draft.get("headword") or ""
    yield from draft.get("notes") or []
    for sense in draft.get("senses") or []:
        yield sense.get("definition") or ""
        for gloss in sense.get("glosses") or []:
            yield from gloss.get("terms") or []
        for example in sense.get("examples") or []:
            for key in ("text", "translation", "note"):
                yield example.get(key) or ""


def flags(composed: dict[str, Any]) -> list[str]:
    """The counters one composed word trips."""
    draft = composed["draft"]
    asked = composed["request"]["resolution"]
    language = draft["language"]
    base = language.split("-")[0]
    headword, lemma = draft["headword"], draft.get("lemma") or draft["headword"]
    found: list[str] = []
    if any(garbled(text) for text in prose(draft)):
        found.append("garbled")
    examples = [e for s in draft["senses"] for e in s.get("examples") or []]
    if any(wrong_script(e.get("text") or "", language) for e in examples):
        found.append("example-script")
    if headword != asked["headword"]:
        found.append("headword-rewritten")
    if draft.get("reading") and reading_for(language, headword, draft["reading"]) != draft["reading"]:
        found.append("reading-form")
    if base != "zh" and draft.get("ipa") and ipa_of_lemma(headword, lemma, draft["ipa"]) != draft["ipa"]:
        found.append("ipa-article")
    gender = draft.get("gender")
    if gender and (draft["pos"] not in GENDERED_POS or gender_for(language, gender) != gender):
        found.append("gender-misplaced")
    if len(draft["senses"]) == 1:
        found.append("single-sense")
    if not examples:
        found.append("no-examples")
    if any(not e.get("matchedForm") for e in examples):
        found.append("example-unmarked")
    notes = draft.get("notes") or []
    if any(RESTATES_GENDER.search(n) for n in notes):
        found.append("note-gender")
    if any(RESTATES_MEANING.search(n) for n in notes):
        found.append("note-meaning")
    if not notes:
        found.append("no-notes")
    if base != "zh" and not draft.get("ipa"):
        found.append("ipa-null")
    return found


def model_of(composed: dict[str, Any]) -> str:
    return composed["model"].split(":", 1)[-1].replace("gemini-", "")


def audit(corpus: Path) -> dict[str, Any]:
    cells: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(collections.Counter)
    sizes: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    flagged: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for path in sorted(corpus.glob("*/compose/*.json")):
        if path.name.endswith(".failed.json"):
            continue
        composed = json.loads(path.read_text(encoding="utf-8"))
        cell = (composed["vocabulary"], model_of(composed))
        cells[cell]["articles"] += 1
        sizes[cell].append(len(composed["draft"]["senses"]))
        for name in flags(composed):
            cells[cell][name] += 1
            flagged[name][composed["vocabulary"]].append(composed["word"]["key"])
    return {
        "cells": {f"{v}|{m}": {**counts, "meanSenses": round(statistics.mean(sizes[(v, m)]), 2)}
                  for (v, m), counts in sorted(cells.items())},
        "flagged": {name: dict(sorted(per.items())) for name, per in sorted(flagged.items())},
    }


def report(result: dict[str, Any]) -> str:
    by_vocabulary: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    senses: dict[str, list[tuple[float, int]]] = collections.defaultdict(list)
    for cell, counts in result["cells"].items():
        vocabulary = cell.split("|")[0]
        by_vocabulary[vocabulary].update({k: v for k, v in counts.items() if k != "meanSenses"})
        senses[vocabulary].append((counts["meanSenses"], counts["articles"]))
    total = collections.Counter()
    for counts in by_vocabulary.values():
        total.update(counts)
    names = list(COUNTERS)
    lines = ["# Compose audit", "",
             "Articles tripping each counter, per vocabulary (`audit.py`; the counters are in its "
             "`COUNTERS`). The first six are what compose now prevents; the rest point a judge at an article.", "",
             "| vocabulary | articles | senses | " + " | ".join(names) + " |",
             "| --- | ---: | ---: | " + " | ".join("---:" for _ in names) + " |"]
    for vocabulary, counts in sorted(by_vocabulary.items()):
        mean = sum(m * n for m, n in senses[vocabulary]) / sum(n for _, n in senses[vocabulary])
        lines.append(f"| {vocabulary} | {counts['articles']} | {mean:.2f} | "
                     + " | ".join(str(counts[name]) for name in names) + " |")
    lines.append(f"| **all** | {total['articles']} | | " + " | ".join(str(total[name]) for name in names) + " |")
    lines += ["", "Per model (every vocabulary together):", "",
              "| model | articles | senses | " + " | ".join(names) + " |",
              "| --- | ---: | ---: | " + " | ".join("---:" for _ in names) + " |"]
    models: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    model_senses: dict[str, list[tuple[float, int]]] = collections.defaultdict(list)
    for cell, counts in result["cells"].items():
        model = cell.split("|")[1]
        models[model].update({k: v for k, v in counts.items() if k != "meanSenses"})
        model_senses[model].append((counts["meanSenses"], counts["articles"]))
    for model, counts in sorted(models.items()):
        mean = sum(m * n for m, n in model_senses[model]) / sum(n for _, n in model_senses[model])
        lines.append(f"| {model} | {counts['articles']} | {mean:.2f} | "
                     + " | ".join(str(counts[name]) for name in names) + " |")
    lines += ["", "Counters:", ""] + [f"- `{name}`: {text}" for name, text in COUNTERS.items()]
    return "\n".join(lines) + "\n"


def selftest() -> None:
    def composed(language: str, headword: str, *, lemma: str | None = None, asked: str | None = None,
                 **draft: Any) -> dict[str, Any]:
        sense = {"definition": "A thing.", "glosses": [{"lang": "en", "terms": ["thing"]}],
                 "examples": draft.pop("examples", [])}
        return {"request": {"resolution": {"headword": asked or headword}},
                "draft": {"language": language, "headword": headword, "lemma": lemma or headword,
                          "pos": draft.pop("pos", "noun"), "notes": draft.pop("notes", ["A real note."]),
                          "senses": draft.pop("senses", [sense, sense]), "ipa": draft.pop("ipa", "/x/"), **draft}}

    cases = [
        (composed("el", "το σπίτι", examples=[{"text": "Πάμε σπίti.", "matchedForm": "σπίti"}]), "garbled"),
        (composed("ja", "時々", examples=[{"text": "時々行く。", "matchedForm": "時々"}]), None),
        (composed("th", "ใส่", examples=[{"text": "The learner did not provide a sentence.", "matchedForm": "x"}]),
         "example-script"),
        (composed("hi", "denā", asked="देना"), "headword-rewritten"),
        (composed("ja", "同僚", reading="dō ryō"), "reading-form"),
        (composed("ja", "同僚", reading="どうりょう"), None),
        (composed("ko", "마시다", reading="mā si da"), "reading-form"),
        (composed("zh-CN", "麻烦", reading="má fan"), None),
        (composed("de", "der Stern", lemma="Stern", ipa="/deːɐ̯ ʃtɛʁn/"), "ipa-article"),
        (composed("de", "der Stern", lemma="Stern", ipa="/ʃtɛʁn/"), None),
        (composed("en", "box", gender="neuter"), "gender-misplaced"),
        (composed("es", "barato", pos="adj", gender="masculine"), "gender-misplaced"),
        (composed("es", "el arroz", gender="masculine"), None),
        (composed("es", "el arroz", notes=["Note that arroz is masculine, so you say el arroz."]), "note-gender"),
        (composed("es", "barato", notes=["Barato means cheap."]), "note-meaning"),
    ]
    failures = []
    for item, expected in cases:
        got = set(flags(item)) - {"no-examples", "example-unmarked", "single-sense", "no-notes", "ipa-null"}
        want = {expected} if expected else set()
        if got != want:
            failures.append(f"{item['draft']['language']} {item['draft']['headword']}: expected {want}, got {got}")
    if failures:
        raise SystemExit("selftest failed:\n  " + "\n  ".join(failures))
    print(f"selftest: {len(cases)} cases, all as expected")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--out", type=Path, default=HERE)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    result = audit(args.corpus)
    (args.out / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = report(result)
    (args.out / "report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
