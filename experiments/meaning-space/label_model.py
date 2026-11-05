"""Name each region of the map once, with a model, so the prototype can compare those names with
the deterministic ones.

Runs in the application's `.venv`, through `acervo.models` — the call the server would make if a
model-written label is ever adopted. One call per language, every region and neighbourhood in it,
so the model can keep sibling names distinct. `build.py` must have run first; run it again
afterwards to merge the names into the fixture.

    set -a; . ./.env; set +a
    .venv/bin/python experiments/meaning-space/label_model.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acervo.models.local import load_local  # noqa: E402
from acervo.models import call, chain  # noqa: E402

LANGUAGE_NAMES = {"es": "Spanish", "en": "English"}

PROMPT = """You are naming the regions of a map of one learner's vocabulary. Each region below is a
group of words that sit together because their meanings are related; neighbourhoods ("hood") are
smaller groups inside the larger regions ("region"). Words are listed most central first, each with
a short gloss.

Give every group a name of one to three words, in {language}, that a learner would recognise as a
topic — like the name of a region on a printed map. Prefer a concrete theme ("clothes and
fabrics", "money and paying") to an abstract one ("actions", "qualities"). Lower case, no
punctuation, no articles unless the language needs one. Names must be distinct from each other.

Answer with a JSON object mapping each group id to its name, and nothing else:
{{"r0": "...", "h0": "...", ...}}

{groups}
"""


def fingerprint(regions: list[dict]) -> str:
    """The same digest `build.py` computes, so labels written for one layout are never merged into
    another."""
    ids = [(r["id"], r["ids"]) for r in regions]
    return hashlib.sha1(json.dumps(sorted(ids)).encode()).hexdigest()[:16]


def groups_text(regions: list[dict]) -> str:
    lines = []
    for region in regions:
        parent = f" (inside r{region['region']})" if region["level"] == "hood" else ""
        lines.append(f"## {region['id']} — {region['level']}{parent}")
        lines.extend(f"- {member}" for member in region["members"])
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--chain", default="gemini-api")
    parser.add_argument("--lang", action="append", default=[])
    args = parser.parse_args()

    candidates = chain.resolve("text", [c.strip() for c in args.chain.split(",")], load_local())
    if not candidates:
        print("No usable pair. Is GEMINI_API_KEY exported?", file=sys.stderr)
        return 2
    for path in sorted((HERE / "out").glob("regions-*.json")):
        summary = json.loads(path.read_text())
        lang = summary["language"]
        if args.lang and lang not in args.lang:
            continue
        language = LANGUAGE_NAMES.get(summary["definitionLang"], summary["definitionLang"])
        prompt = PROMPT.format(language=language, groups=groups_text(summary["regions"]))
        for candidate in candidates:
            try:
                result = call.text(prompt, row=candidate.row, model=candidate.model, as_json=True)
            except Exception as error:  # noqa: BLE001 - try the next pair, as a chain would
                print(f"{lang}: {candidate.row.id}/{candidate.model} failed: {error}"[:300], file=sys.stderr)
                continue
            labels = {k: str(v).strip() for k, v in (result.parsed or {}).items() if isinstance(v, str)}
            wanted = {r["id"] for r in summary["regions"]}
            print(f"{lang}: {len(set(labels) & wanted)}/{len(wanted)} named by "
                  f"{candidate.row.id}/{candidate.model}")
            (HERE / "out" / f"model-labels-{lang}.json").write_text(
                json.dumps({**labels, "_model": f"{candidate.row.id}/{candidate.model}",
                            "_fingerprint": fingerprint(summary["regions"])},
                           ensure_ascii=False, indent=1))
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
