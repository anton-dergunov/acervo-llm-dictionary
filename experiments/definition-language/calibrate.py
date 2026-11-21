#!/usr/bin/env python3
"""Free: how compose's definition check reads every definition the starter builder has stored.

    .venv/bin/python experiments/definition-language/calibrate.py

For each Latin-script definition whose vocabulary has a second language in that script, the
identifier's confidence that it is that other language, as `vet.definition_doubt` computes it. Writes
`calibration.json`: the counts per vocabulary and confidence band, and every definition from 0.5 to
0.95 with its text, the band where English and the word's language were told apart by reading
(README, "Calibration"). No call is made; `data/starter/` must hold compose files.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acervo.services.capture.vet import _base, _detector, scripts_of, wrong_script  # noqa: E402

BANDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def main() -> int:
    counts: Counter[tuple[str, str]] = Counter()
    band: list[dict] = []
    for path in sorted((ROOT / "data" / "starter").glob("*/compose/*.json")):
        if path.name.endswith(".failed.json"):
            continue
        composed = json.loads(path.read_text(encoding="utf-8"))
        vocabulary = composed["vocabulary"]
        language = _base(composed["request"]["resolution"]["language"])
        for sense in composed["draft"]["senses"]:
            target = _base(sense["definitionLang"])
            text = sense["definition"]
            if wrong_script(text, target):
                counts[(vocabulary, "other script")] += 1
                continue
            if language == target or scripts_of(language) != scripts_of(target):
                counts[(vocabulary, "not compared")] += 1
                continue
            detector = _detector((target, language))
            values = {v.language.iso_code_639_1.name.lower(): v.value
                      for v in detector.compute_language_confidence_values(text)}
            confidence = values.get(language, 0.0)
            reached = max((b for b in BANDS if confidence >= b), default=0.0)
            counts[(vocabulary, f">= {reached}" if reached else "< 0.5")] += 1
            if 0.5 <= confidence < 0.95:
                band.append({"vocabulary": vocabulary, "confidence": round(confidence, 3), "definition": text})
    table: dict[str, dict[str, int]] = {}
    for (vocabulary, which), count in sorted(counts.items()):
        table.setdefault(vocabulary, {})[which] = count
    band.sort(key=lambda item: item["confidence"])
    (HERE / "calibration.json").write_text(json.dumps({"counts": table, "band": band}, ensure_ascii=False, indent=1)
                                           + "\n", encoding="utf-8")
    for vocabulary, row in table.items():
        print(vocabulary, row)
    print(f"{len(band)} definitions between 0.5 and 0.95 written to calibration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
