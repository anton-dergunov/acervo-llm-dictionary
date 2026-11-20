"""The IPA guide's table (web/src/ipa/symbols.json) held to what Acervo writes, and its recordings
to their files and credits.

1. Each Pinyin initial and final row states the IPA `acervo/mandarin_ipa.py` writes for its example
   syllable, so the guide never explains a letter differently from the transcription beside it, and
   every final the server can cut a syllable into has a row.
2. Every character of every Mandarin syllable's IPA (the whole inventory, with and without erhua) is
   a symbol, alias, diacritic or tone letter in the table, so the panel never meets one it cannot
   explain.
3. Every `sound` is a file in web/src/ipa/sounds/, every file there is played by some row, and every
   file carries the credit its licence asks for (docs/plans/languages/ipa-guide.md, "Data").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from acervo.mandarin_ipa import INITIALS, _initial_and_final, mandarin_ipa
from acervo.pinyin import INVENTORY, pinyin_syllables

GUIDE = Path(__file__).resolve().parents[2] / "web" / "src" / "ipa"
TABLE = json.loads((GUIDE / "symbols.json").read_text(encoding="utf-8"))
TONE_LETTERS = "˥˦˧˨˩"
# The finals the table writes as the learner sees them, for the ones the server spells out in full.
SPELT = {"iou": "iu", "uei": "ui", "uen": "un"}
FREE = {"Public domain", "CC0", "CC BY 2.0 fr", "CC BY-SA 3.0", "CC BY-SA 3.0 us", "CC BY-SA 4.0"}


def bare(ipa: str) -> str:
    return "".join(ch for ch in ipa if ch not in TONE_LETTERS).strip("/")


def test_every_pinyin_initial_states_the_ipa_the_server_writes():
    for row in TABLE["pinyin"]["initials"]:
        derived = bare(mandarin_ipa(row["example"]) or "")
        assert INITIALS.get(row["letters"]) == row["ipa"], row["letters"]
        assert derived.startswith(row["ipa"]), (row["letters"], derived)


def test_every_pinyin_final_states_the_ipa_the_server_writes():
    for row in TABLE["pinyin"]["finals"]:
        derived = bare(mandarin_ipa(row["example"]) or "")
        assert derived.endswith(row["ipa"]) or row["ipa"] in derived, (row["letters"], derived)


def test_every_final_the_server_cuts_has_a_row():
    rows = {row["letters"] for row in TABLE["pinyin"]["finals"]}
    for syllable in INVENTORY:
        initial, final = _initial_and_final(syllable)
        if final == "i" and initial in ("zh", "ch", "sh", "r", "z", "c", "s"):
            continue  # the two apical rows, "-i (…)"
        assert SPELT.get(final, final) in rows, (syllable, final)


def test_every_character_mandarin_ipa_writes_is_in_the_table():
    known: set[str] = set(TONE_LETTERS) | set(" /")
    for section in ("consonants", "affricates", "vowels", "diacritics", "suprasegmentals"):
        for entry in TABLE[section]:
            for written in [entry["symbol"], *entry.get("aliases", [])]:
                known.update(written)
    for syllable in INVENTORY:
        for reading in (f"{syllable}1", f"{syllable}r1"):
            if pinyin_syllables(reading) is None:
                continue
            missing = set(mandarin_ipa(reading) or "") - known
            assert not missing, (reading, missing)


def sounds(value) -> list[str]:
    if isinstance(value, dict):
        return ([value["sound"]] if "sound" in value else []) + [s for v in value.values() for s in sounds(v)]
    if isinstance(value, list):
        return [s for v in value for s in sounds(v)]
    return []


def test_every_sound_is_a_file_and_every_file_is_played():
    played = set(sounds({k: v for k, v in TABLE.items() if k not in ("fields", "recordings")}))
    files = {path.name for path in (GUIDE / "sounds").glob("*")}
    assert played == files == set(TABLE["recordings"])


def test_every_file_is_named_by_a_digest():
    for name in TABLE["recordings"]:
        assert re.fullmatch(r"[0-9a-f]{16}\.ogg", name), name


def test_every_recording_carries_its_credit():
    for name, credit in TABLE["recordings"].items():
        assert credit["author"].strip(), name
        assert credit["licence"] in FREE, (name, credit["licence"])
        assert credit["licenceUrl"] or credit["licence"] == "Public domain", name
        assert credit["page"].startswith("https://commons.wikimedia.org/wiki/File:"), name
        assert credit["changes"].startswith("trimmed"), name
