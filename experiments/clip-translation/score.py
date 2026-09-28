"""How much of a passage a translation actually carries, computed rather than judged.

Two metrics that check each other.

**Anchor coverage** is hand-written but disciplined: the source is partitioned into clauses whose
texts concatenate back to it exactly, each clause carries one disjunction of acceptable renderings,
and coverage is weighted by how many characters of the source each clause is. That is what separates
"dropped the whole first sentence" (≈0.45) from "skipped one adjective" (≈0.96); a plain
fraction-of-anchors-found scores both near 0.67 and is useless for the failure this experiment
exists to measure.

Each clause is matched to **its own occurrence**: a clause may take any position in the translation,
but no two clauses may take the same one. That is a maximum-weight bipartite matching, and both
halves of it are load-bearing. Without the one-occurrence-each rule, *picaba mucho, picaba mucho* is
two clauses that one "itched a lot" would satisfy twice, and a dropped repetition would score full.
With an order rule instead, every clause a target language legitimately reorders starves the next
one — English puts *posh* before *castle* and Chinese puts the relative clause before its head, and
an in-order walk scored both of those as missing.

**Relative length** is the anchor-free cross-check, and it is what makes this fair across scripts: a
row's length ratio over the median ratio of *complete* rows in the same target language. A faithful
translation sits near 1.0 whether it is English or Japanese; one that dropped half its source sits
near 0.5 in both. Nothing here hard-codes a per-language constant.

Scoring never spends a model call, so correcting an anchor set and re-scoring a whole run is free.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import dataset
from dataset import Clause

DENSE_RANGES = (("一", "鿿"), ("぀", "ヿ"), ("가", "힯"),
                ("㐀", "䶿"), ("豈", "﫿"))


def dense(text: str) -> bool:
    """True when enough of the text is Han, Kana or Hangul that one character carries a word.

    Read off the text's own codepoints rather than a language tag, so a language nobody listed still
    lands in the right class.
    """
    letters = [c for c in text if not c.isspace() and not c.isdigit() and c.isalnum()]
    if not letters:
        return False
    hits = sum(any(low <= c <= high for low, high in DENSE_RANGES) for c in letters)
    return hits / len(letters) > 0.2


# What a target language's own characters look like, for the one question a length ratio cannot
# answer: was this written in the language that was asked for at all? Discovered rather than
# anticipated — Cloudflare's llama answered three Japanese requests in fluent English, which is a
# complete translation of the passage and a total failure of the request, and coverage reported it
# as 0.00 with no way to say why.
SCRIPTS = {
    "ja": ("\u3040", "\u30ff", "\u4e00", "\u9fff"),
    "zh": ("\u4e00", "\u9fff"),
    "ko": ("\uac00", "\ud7af"),
    "ru": ("\u0400", "\u04ff"),
    "uk": ("\u0400", "\u04ff"),
    "el": ("\u0370", "\u03ff"),
}


def in_target_script(translation: str, target_lang: str) -> bool | None:
    """Whether the reply is written in the script the target language uses.

    None where the target uses the Latin alphabet, because sharing an alphabet is not evidence of
    sharing a language and this check would claim more than it knows. For the scripts it does cover,
    a reply with none of their characters was not written in that language.
    """
    ranges = SCRIPTS.get(target_lang.split("-")[0])
    if not ranges:
        return None
    pairs = list(zip(ranges[::2], ranges[1::2]))
    return any(any(low <= c <= high for low, high in pairs) for c in (translation or ""))


def fold(text: str) -> str:
    """Case- and accent-folded, so `gris`/`grís` and `Castle`/`castle` are one thing."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def anchor_hit(folded: str, anchor: str, start: int) -> int | None:
    """Where an anchor occurs at or after `start`, or None.

    Anchors are **stems**: bounded at the word start and open at the end, so `itch` finds *itched*
    and *itching* without listing them, while `at` cannot find *nature*. A dense script has no word
    boundaries to bound, so there it is a plain substring.
    """
    needle = fold(anchor)
    if not needle:
        return None
    if dense(anchor):
        found = folded.find(needle, start)
        return found if found >= 0 else None
    for match in re.finditer(rf"(?<!\w){re.escape(needle)}", folded[start:]):
        return start + match.start()
    return None


@dataclass(frozen=True)
class Coverage:
    score: float                  # character-weighted, one occurrence per clause
    loose: float                  # the same, letting clauses share an occurrence
    full: bool
    covered: tuple[bool, ...]
    hits: tuple[int | None, ...]
    opening_dropped: bool
    trailing_dropped: int
    interior_dropped: int
    shared: bool                  # a clause only scored by sharing: a repetition was dropped


def occurrences(folded: str, anchors: Sequence[str]) -> list[int]:
    """Every distinct position in the translation where any of a clause's anchors starts.

    Distinct by position, so `itch` and `itching` listed together do not count one word twice.
    """
    found: set[int] = set()
    for anchor in anchors:
        start = 0
        while True:
            hit = anchor_hit(folded, anchor, start)
            if hit is None:
                break
            found.add(hit)
            start = hit + 1
    return sorted(found)


def _assign(options: Sequence[Sequence[int]], weights: Sequence[int]) -> list[int | None]:
    """Give each clause an occurrence of its own, heaviest clauses first.

    Maximum-weight bipartite matching. Taking clauses in descending weight and augmenting is exact
    here rather than merely greedy — one side carries the weights, which makes this a transversal
    matroid — so a heavy clause is never starved by a light one that got in first.
    """
    taken: dict[int, int] = {}          # position -> clause

    def augment(clause: int, seen: set[int]) -> bool:
        for position in options[clause]:
            if position in seen:
                continue
            seen.add(position)
            holder = taken.get(position)
            if holder is None or augment(holder, seen):
                taken[position] = clause
                return True
        return False

    for clause in sorted(range(len(options)), key=lambda i: -weights[i]):
        augment(clause, set())
    assigned: list[int | None] = [None] * len(options)
    for position, clause in taken.items():
        assigned[clause] = position
    return assigned


def coverage(translation: str, clauses: Sequence[Clause]) -> Coverage:
    total = sum(clause.weight for clause in clauses) or 1
    folded = fold(translation or "")
    weights = [clause.weight for clause in clauses]

    options = [occurrences(folded, clause.anchors) for clause in clauses]
    hits = _assign(options, weights)
    covered = tuple(hit is not None for hit in hits)
    score = sum(w for w, ok in zip(weights, covered) if ok) / total

    # The same question with the one-occurrence-each rule lifted: if this is higher, some clause was
    # only satisfied by a word another clause had already used, which is what a dropped repetition
    # looks like.
    loose_covered = tuple(bool(option) for option in options)
    loose = sum(w for w, ok in zip(weights, loose_covered) if ok) / total

    leading = 0
    for ok in covered:
        if ok:
            break
        leading += 1
    trailing = 0
    for ok in reversed(covered):
        if ok:
            break
        trailing += 1
    interior = sum(1 for ok in covered[leading:len(covered) - trailing] if not ok)

    return Coverage(
        score=round(score, 4), loose=round(loose, 4), full=all(covered),
        covered=covered, hits=tuple(hits),
        opening_dropped=bool(covered) and not covered[0],
        trailing_dropped=trailing if not all(covered) else 0,
        interior_dropped=interior,
        shared=round(loose, 4) > round(score, 4),
    )


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def length_ratio(translation: str, source: str) -> float:
    source = collapse(source)
    return round(len(collapse(translation)) / len(source), 4) if source else 0.0


def reference_ratios(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """The median ratio of the rows that are complete, per target language.

    Over every arm and pair together: this is a property of the language pair, not of a prompt or a
    model, and computing it per arm would move the yardstick with the thing being measured.
    """
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if row.get("full") and row.get("ratio"):
            grouped.setdefault(row["targetLang"], []).append(row["ratio"])
    return {lang: round(statistics.median(values), 4) for lang, values in grouped.items() if values}


def relative_length(ratio: float, target_lang: str, reference: Mapping[str, float]) -> float | None:
    base = reference.get(target_lang)
    return round(ratio / base, 4) if base else None


def matched_form_state(raw: str | None, translation: str | None) -> str:
    """`omitted` is a legitimate answer; `invalid` is the model claiming a span it did not write."""
    if not raw:
        return "omitted"
    return "verbatim" if translation and raw in translation else "invalid"


def numerals_kept(source: str, translation: str) -> bool:
    """Every digit run in the source occurs in the translation. Free, and script-independent."""
    return all(run in (translation or "") for run in re.findall(r"\d+", source or ""))


# ── scoring a run directory ─────────────────────────────────────────────────


def score_call(record: Mapping[str, Any], passages: Mapping[str, dataset.Passage]) -> dict[str, Any]:
    passage = passages[record["passageId"]]
    target = record["targetLang"]
    picked = next((s for s in record.get("selections", [])
                   if s.get("segmentId") == passage.raw["provenance"]["segmentId"]), None)
    row = {
        "mode": record.get("mode", "translate"),
        "arm": record["arm"], "provider": record["provider"], "model": record["model"],
        "passageId": record["passageId"], "targetLang": target, "repeat": record["repeat"],
        "status": record["status"], "expect": passage.expect,
        "picked": picked is not None,
        "seconds": (record.get("answer") or {}).get("seconds"),
        "costUsd": (record.get("answer") or {}).get("costUsd"),
        "promptChars": record.get("promptChars"), "replyChars": record.get("replyChars"),
        "parseOk": (record.get("parseReply") or {}).get("ok"),
        "dropped": (record.get("parseReply") or {}).get("dropped"),
    }
    if not picked:
        return row
    translation = picked.get("translation") or ""
    cover = coverage(translation, passage.clauses(target))
    row.update(asdict(cover))
    row.update({
        "translation": translation,
        "ratio": length_ratio(translation, passage.sentence),
        "dense": dense(translation),
        "matchedForm": matched_form_state(picked.get("matchedTranslationFormRaw"), translation),
        "numeralsKept": numerals_kept(passage.sentence, translation),
        "inTargetScript": in_target_script(translation, target),
        # **The passage handed back instead of translated.** Added after a rewrite of this prompt
        # shipped and did exactly that in production: it is exact, costs nothing, and had it been
        # here from the start the class could not have been invisible. It is *not* the completeness
        # check deferred to docs/plans/quality/translation-completeness-check.md — that one needs a
        # threshold and this one needs none.
        "copiedSource": translation.strip() == passage.sentence.strip(),
    })
    return row


def score_run(run_dir: Path) -> dict[str, Any]:
    passages = dataset.by_id()
    rows = [score_call(json.loads(path.read_text(encoding="utf-8")), passages)
            for path in sorted(run_dir.rglob("*.json"))
            if path.name not in {"manifest.json", "summary.json"}]
    scored = [row for row in rows if row["status"] == "ok"]
    reference = reference_ratios(scored)
    for row in scored:
        if "ratio" in row:
            row["relativeLength"] = relative_length(row["ratio"], row["targetLang"], reference)
    return {
        "runDir": str(run_dir), "referenceRatios": reference,
        "rows": rows,
    }


def main(argv: Sequence[str]) -> int:
    if argv and argv[0] == "--selftest":
        return selftest()
    if not argv:
        print(__doc__)
        print("usage: score.py <run directory> | --selftest")
        return 2
    run_dir = Path(argv[0])
    summary = score_run(run_dir)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = [r for r in summary["rows"] if r["status"] == "ok" and r.get("picked")]
    full = sum(1 for r in ok if r.get("full"))
    print(f"{len(summary['rows'])} calls, {len(ok)} with a selection, "
          f"{full} fully covered ({full / len(ok):.0%})" if ok else "no selections")
    print("reference ratios:", summary["referenceRatios"])
    return 0


def selftest() -> int:
    """The metric, against the failure that prompted all of this — before any money is spent."""
    passage = dataset.by_id()["castillo-picar"]
    clauses = passage.clauses("en")
    stored = ("And at the castle they gave us an outfit that itched a lot, it itched a lot and it "
              "was gray with")
    complete = ("it was a bit of a posh castle, but yes, she worked as a waitress at a castle that "
                "hosted weddings. And at the castle they gave us an outfit that itched a lot, it "
                "itched a lot and it was gray with")
    one_itch = ("it was a bit of a posh castle, but yes, she worked as a waitress at a castle that "
                "hosted weddings. And at the castle they gave us an outfit that itched a lot and it "
                "was gray with")
    zh_complete = ("那是一座有点高档的城堡，不过是的，她在一座举办婚礼的城堡里当服务员。"
                   "在城堡里他们发给我们一套很扎人的衣服，很扎人，而且是灰色的，配着")
    zh_stored = "在城堡里他们发给我们一套很扎人的衣服，很扎人，而且是灰色的，配着"

    failures = []

    def check(name: str, got: Any, want: Any) -> None:
        if got != want:
            failures.append(f"{name}: expected {want!r}, got {got!r}")
        print(f"  {'ok  ' if got == want else 'FAIL'} {name}: {got!r}")

    print("a complete translation of the passage:")
    good = coverage(complete, clauses)
    check("full", good.full, True)
    check("coverage", good.score, 1.0)

    print("the translation that was actually stored, with its first sentence gone:")
    bad = coverage(stored, clauses)
    check("full", bad.full, False)
    check("coverage", round(bad.score, 2), 0.57)
    check("four clauses missing", bad.interior_dropped, 4)
    # Not asserted, and the write-up says why: `castillo` occurs three times in this passage, so the
    # one `castle` left in the truncated translation satisfies the first clause. An anchor cannot
    # tell which occurrence it is. Coverage still separates the two cleanly, which is the number
    # this experiment reports.
    print(f"       openingDropped is {bad.opening_dropped} here, and cannot be otherwise: "
          f"'castillo' occurs three times")

    print("the same, with one half of the repetition dropped:")
    once = coverage(one_itch, clauses)
    check("full", once.full, False)
    check("one clause missing", once.interior_dropped, 1)
    check("scored only by sharing an occurrence", once.shared, True)

    print("Chinese, complete and truncated — the class the anchors must still separate:")
    zh = passage.clauses("zh")
    check("complete is full", coverage(zh_complete, zh).full, True)
    check("truncated is not", coverage(zh_stored, zh).full, False)
    check("truncated scores the same as in English", coverage(zh_stored, zh).score, bad.score)
    check("dense() sees Han", dense(zh_complete), True)
    check("dense() does not see English", dense(complete), False)

    ratio_zh = length_ratio(zh_complete, passage.sentence)
    ratio_en = length_ratio(complete, passage.sentence)
    print(f"       complete length ratios: en {ratio_en:.2f}, zh {ratio_zh:.2f} — "
          f"no single absolute floor could serve both")
    reference = reference_ratios([{"targetLang": "en", "full": True, "ratio": ratio_en},
                                  {"targetLang": "zh", "full": True, "ratio": ratio_zh}])
    rel_en = relative_length(length_ratio(stored, passage.sentence), "en", reference)
    rel_zh = relative_length(length_ratio(zh_stored, passage.sentence), "zh", reference)
    print(f"       the same two truncations, as relative length: en {rel_en:.2f}, zh {rel_zh:.2f} — "
          f"which is one number in both scripts")
    if not (0.4 <= rel_en <= 0.6 and 0.4 <= rel_zh <= 0.6):
        failures.append("relative length does not normalise the two scripts onto one number")

    print("numeral parity, on the passage that carries numbers:")
    numbers = dataset.by_id()["subir-precios"]
    check("kept", numerals_kept(numbers.sentence, "the rent went from 600 to 850 euros in two "
                                "years, so 40 percent, and the salary is the same, of course"), True)
    check("dropped", numerals_kept(numbers.sentence, "the rent went up a lot in two years"), False)

    print("every passage's clause partition reconstructs its source:")
    for one in dataset.load():
        for lang in one.targets:
            one.clauses(lang)
    check("partitions", True, True)

    print()
    if failures:
        print(f"FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("The metric separates the real failure from the real fix, identically in both scripts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
