"""Hold symbols.yaml to what Acervo writes: every Pinyin row's IPA, and every character it can emit.

    .venv/bin/python experiments/ipa-sounds/check.py

1. Each Pinyin initial and final row states the IPA `acervo/mandarin_ipa.py` writes for its example
   syllable, so the guide can never explain a letter differently from the transcription beside it.
2. Every character of every Mandarin syllable's IPA (the whole inventory, with and without erhua) is
   a symbol, alias, diacritic or tone letter in the table, so the panel never meets one it cannot
   explain.

Prints what disagrees and exits 1, or prints a one-line summary.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import yaml

from acervo.mandarin_ipa import INITIALS, mandarin_ipa
from acervo.pinyin import pinyin_syllables

HERE = Path(__file__).resolve().parent
TONE_LETTERS = "˥˦˧˨˩"


def known_characters(table: dict) -> set[str]:
    known: set[str] = set()
    for section in ("consonants", "affricates", "vowels", "diacritics", "suprasegmentals"):
        for entry in table[section]:
            for written in [entry["symbol"], *entry.get("aliases", [])]:
                known.update(written)
    known.update(TONE_LETTERS)
    known.update(" /")
    return known


def bare(ipa: str) -> str:
    return "".join(ch for ch in ipa if ch not in TONE_LETTERS).strip("/")


def main() -> int:
    table = yaml.safe_load((HERE / "symbols.yaml").read_text(encoding="utf-8"))
    problems: list[str] = []

    for row in table["pinyin"]["initials"]:
        derived = bare(mandarin_ipa(row["example"]) or "")
        if INITIALS.get(row["letters"]) != row["ipa"] or not derived.startswith(row["ipa"]):
            problems.append(f"initial {row['letters']}: table {row['ipa']}, mandarin_ipa {derived}")
    for row in table["pinyin"]["finals"]:
        derived = bare(mandarin_ipa(row["example"]) or "")
        if not derived.endswith(row["ipa"]) and row["ipa"] not in derived:
            problems.append(f"final {row['letters']} ({row['example']}): table {row['ipa']}, mandarin_ipa {derived}")

    known = known_characters(table)
    inventory = __import__("json").loads(
        (HERE.parents[1] / "web/src/testFixtures/pinyinSyllableVectors.json").read_text(encoding="utf-8")
    )["inventory"]
    unknown: dict[str, str] = {}
    for syllable in inventory:
        for reading in (syllable + "1", syllable + "r1"):
            if pinyin_syllables(reading) is None:
                continue
            for ch in mandarin_ipa(reading) or "":
                if ch not in known:
                    unknown.setdefault(ch, reading)
    for ch, reading in unknown.items():
        problems.append(f"U+{ord(ch):04X} {unicodedata.name(ch, '?')} (from {reading}) is not in the table")

    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"ok: {len(table['pinyin']['initials'])} initials, {len(table['pinyin']['finals'])} finals, "
          f"{len(inventory)} syllables covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
