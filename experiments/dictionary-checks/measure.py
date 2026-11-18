"""How often do installed dictionaries disagree with the owner's stored words, and in what way?

    .venv/bin/python experiments/dictionary-checks/measure.py \
        --words experiments/dictionary-checks/out/words.json \
        --dictionaries data/dictionaries/out \
        --chinese data/dictionaries/src/kaikki.org-dictionary-Chinese.jsonl

Free: no model is called. Every stored word is looked up through the shipped reader
(`services/dictionaries/lookup.py`) and sorted by the shipped comparisons
(`services/capture/dictionary_check.py`), so these counts are what the check would see:

- `reading`, for Mandarin words, against every dictionary reading that is Pinyin;
- `ipa`, for every other word, against the dictionary's first transcription and against any of them;
- `gender`, for nouns, against the dictionary's genders.

The stored words were written by models and some corrected by hand, so they are mostly right: a
disagreement here is mostly a false alarm the check would raise. With only a handful of Chinese
words stored, `--chinese` adds a second comparison of two published sources, Wiktionary's Mandarin
Pinyin against CC-CEDICT's, word for word: how often two right answers disagree, and how.

Writes `results.json` (one row per word) and `report.md` beside this file.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

from acervo.dictionaries.container import Artifact
from acervo.pinyin import is_mandarin
from acervo.services.capture.dictionary_check import (
    IPA_CLASSES,
    READING_CLASSES,
    attested,
    gender_verdict,
    keys_for,
    transcription_to_judge,
    ipa_verdict,
    per,
    reading_verdict,
)
from acervo.services.dictionaries.lookup import articles_for

HERE = Path(__file__).resolve().parent


def measure_words(words: list[dict], directory: Path) -> list[dict]:
    rows = []
    seen: set[tuple[str, str, str]] = set()
    for word in words:
        # The English vocabulary holds 227 words twice, identical; a word is counted once.
        identity = (word["language"], word["headword"], word["ipa"])
        if identity in seen:
            continue
        seen.add(identity)
        language = word["language"]
        found = articles_for(directory, language, keys_for(word["headword"], word["lemma"]))
        readings, _, genders = attested(article for item in found for article in item.articles)
        row = {"id": word["id"], "language": language, "headword": word["headword"], "lemma": word["lemma"],
               "pos": word["pos"], "model": word.get("model_id") or "(none recorded)",
               "found": {item.dictionary_id: item.key for item in found}}
        if is_mandarin(language):
            verdict = reading_verdict(word["reading"], readings)
            row["reading"] = {"stored": word["reading"], "kind": verdict.kind, "nearest": verdict.nearest,
                              "attested": readings}
        elif word["ipa"]:
            judged = transcription_to_judge(word["headword"], word["ipa"], found)
            if judged is None:
                row["ipa"] = {"stored": word["ipa"], "first": "other-form", "any": "other-form"}
            else:
                said, ipas = judged
                first = ipa_verdict(said, ipas, first_only=True)
                best = ipa_verdict(said, ipas)
                row["ipa"] = {"stored": word["ipa"], "compared": said, "first": first.kind, "any": best.kind,
                              "nearest": best.nearest, "per": round(per(said, best.nearest), 3)
                              if best.nearest else None, "attested": ipas}
        if word["pos"] == "noun":
            verdict = gender_verdict(word["gender"] or None, genders)
            row["gender"] = {"stored": word["gender"] or None, "kind": verdict.kind, "attested": genders}
        rows.append(row)
    return rows


_PRON = re.compile(r"^(.*?)\s*\(")


def wiktionary_pinyin(path: Path) -> dict[str, list[str]]:
    """Every Mandarin Standard Pinyin the English Wiktionary gives a Chinese word, by word."""
    found: dict[str, list[str]] = collections.defaultdict(list)
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if '"Pinyin"' not in line:
                continue
            record = json.loads(line)
            for sound in record.get("sounds") or []:
                tags = sound.get("tags") or []
                pron = sound.get("zh_pron")
                if not pron or not {"Mandarin", "Pinyin"} <= set(tags) or "Standard" not in tags:
                    continue
                match = _PRON.match(pron)
                reading = (match.group(1) if match else pron).strip()
                if reading and reading not in found[record["word"]]:
                    found[record["word"]].append(reading)
    return found


def measure_sources(chinese: Path, directory: Path) -> dict:
    """Wiktionary's Pinyin against CC-CEDICT's, for every word both hold."""
    cedict = Artifact(directory / "cc-cedict.dict", directory / "cc-cedict.idx")
    counts: collections.Counter[str] = collections.Counter()
    by_word: collections.Counter[str] = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for word, readings in wiktionary_pinyin(chinese).items():
        payload = cedict.payload(word)
        if not payload:
            continue
        held = [article.get("reading") for article in json.loads(payload) if article.get("reading")]
        kinds = []
        for reading in readings:
            verdict = reading_verdict(reading, held)
            counts[verdict.kind] += 1
            kinds.append(verdict.kind)
            if verdict.kind != "match" and len(examples[verdict.kind]) < 25:
                examples[verdict.kind].append(f"{word}: Wiktionary {reading}; CC-CEDICT {' | '.join(held)}")
        # A word whose Wiktionary entry gives several readings (mainland and Taiwan, say) is as good
        # as its best one: that is what the check would do with a model's single reading.
        order = [*READING_CLASSES, "unparsed", "no-entry"]
        by_word[min(kinds, key=order.index)] += 1
    return {"counts": dict(counts), "byWord": dict(by_word), "examples": dict(examples)}


# ── the report ───────────────────────────────────────────────────────────────────────────────

def _table(counter: collections.Counter, order: tuple[str, ...], total_label: str) -> list[str]:
    total = sum(counter.values())
    lines = [f"| class | words | share of {total_label} |", "| --- | ---: | ---: |"]
    for kind in [*order, *sorted(set(counter) - set(order))]:
        if counter[kind]:
            lines.append(f"| `{kind}` | {counter[kind]} | {100 * counter[kind] / total:.1f}% |")
    lines.append(f"| **all** | {total} | |")
    return lines


def report(rows: list[dict], sources: dict | None) -> str:
    out = ["# Dictionary checks · the measurement", "",
           "Generated by `measure.py`; the reading of it is in `README.md`.", ""]

    readings = [row for row in rows if "reading" in row]
    out += ["## Readings (Mandarin, stored words)", ""]
    out += _table(collections.Counter(row["reading"]["kind"] for row in readings), READING_CLASSES, "words")
    out += [""] + [f"- {row['headword']}: stored `{row['reading']['stored']}`, dictionary "
                   f"`{' | '.join(row['reading']['attested']) or '—'}` → `{row['reading']['kind']}`"
                   for row in readings] + [""]

    if sources:
        out += ["## Readings (two published sources: Wiktionary against CC-CEDICT)", "",
                "Per word, its best Wiktionary reading:", ""]
        out += _table(collections.Counter(sources["byWord"]), READING_CLASSES, "words")
        out += ["", "Per reading (Wiktionary often gives a mainland and a Taiwan reading):", ""]
        out += _table(collections.Counter(sources["counts"]), READING_CLASSES, "readings")
        for kind, items in sources["examples"].items():
            out += ["", f"`{kind}`, first {len(items)}:", ""] + [f"- {item}" for item in items]
        out += [""]

    ipas = [row for row in rows if "ipa" in row]
    for language in sorted({row["language"] for row in ipas}):
        subset = [row for row in ipas if row["language"] == language]
        held = [row for row in subset if row["ipa"]["any"] not in ("no-entry", "model-none", "other-form")]
        other = sum(row["ipa"]["any"] == "other-form" for row in subset)
        out += [f"## Transcriptions · `{language}`", "",
                f"{len(subset)} stored words with an `ipa` (each counted once); {len(held)} found under the "
                f"headword (or the headword without its first word) in a dictionary with a transcription; {other} found only under "
                f"another form (the lemma), so not compared.", "",
                "Against the dictionary's **first** transcription:", ""]
        out += _table(collections.Counter(row["ipa"]["first"] for row in held), IPA_CLASSES, "words found")
        out += ["", "Against **any** of its transcriptions:", ""]
        out += _table(collections.Counter(row["ipa"]["any"] for row in held), IPA_CLASSES, "words found")
        by_model: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for row in held:
            by_model[row["model"]][row["ipa"]["any"]] += 1
        out += ["", "By the model that wrote the word (any transcription):", "",
                "| model | words | " + " | ".join(f"`{kind}`" for kind in IPA_CLASSES) + " |",
                "| --- | ---: | " + " | ".join("---:" for _ in IPA_CLASSES) + " |"]
        for model, counter in sorted(by_model.items(), key=lambda item: -sum(item[1].values())):
            out.append(f"| {model} | {sum(counter.values())} | "
                       + " | ".join(str(counter[kind]) for kind in IPA_CLASSES) + " |")
        for kind in IPA_CLASSES[1:]:
            listed = sorted((row for row in held if row["ipa"]["any"] == kind), key=lambda row: row["lemma"])
            if listed:
                out += ["", f"Every `{kind}` (any transcription):", ""]
                out += [f"- {row['headword']}: compared `{row['ipa']['compared']}`, nearest "
                        f"`{row['ipa']['nearest']}` (PER {row['ipa']['per']})" for row in listed]
        out += [""]

    genders = [row for row in rows if "gender" in row]
    for language in sorted({row["language"] for row in genders}):
        subset = [row for row in genders if row["language"] == language]
        held = [row for row in subset if row["gender"]["kind"] != "no-entry"]
        if not held:
            continue
        out += [f"## Gender · `{language}` nouns", "",
                f"{len(subset)} stored nouns; {len(held)} with a gender in a dictionary.", ""]
        out += _table(collections.Counter(row["gender"]["kind"] for row in held),
                      ("match", "mismatch", "model-none"), "nouns found")
        listed = [row for row in held if row["gender"]["kind"] != "match"]
        if listed:
            out += ["", "Every disagreement:", ""]
            out += [f"- {row['headword']}: stored `{row['gender']['stored']}`, dictionary "
                    f"`{' / '.join(row['gender']['attested'])}` → `{row['gender']['kind']}`"
                    for row in sorted(listed, key=lambda row: row["lemma"])]
        out += [""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--words", type=Path, required=True)
    parser.add_argument("--dictionaries", type=Path, required=True)
    parser.add_argument("--chinese", type=Path, help="kaikki's English-edition Chinese JSONL, for the two-source comparison")
    args = parser.parse_args()
    document = json.loads(args.words.read_text(encoding="utf-8"))
    rows = measure_words(document["lexemes"], args.dictionaries)
    sources = measure_sources(args.chinese, args.dictionaries) if args.chinese else None
    (HERE / "results.json").write_text(json.dumps({"words": rows, "sources": sources}, ensure_ascii=False,
                                                  indent=1) + "\n", encoding="utf-8")
    (HERE / "report.md").write_text(report(rows, sources) + "\n", encoding="utf-8")
    print((HERE / "report.md").read_text(encoding="utf-8")[:3000])


if __name__ == "__main__":
    main()
