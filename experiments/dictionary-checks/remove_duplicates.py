#!/usr/bin/env python3
"""Remove the words the store holds twice, keeping in each pair the copy with history.

Found by this experiment (`README.md`): 227 English words were stored twice on 19 Sep 2026, by two
bundle imports running at once in one browser. This script was run once, by hand, to remove them.
It writes through `POST /graph` as the owner, the route a device writes through, so revisions,
validation and the Anki push treat the result as an ordinary delete.

**Nothing is written without `--apply`.** A dry run pulls, groups and prints what it would do.

- **A duplicate** is two or more live lexemes with the same language, headword and part of speech.
- **The copy kept** is the one with the most history: loop items, story words, recordings, clips,
  attestations and study-state repetitions. On a tie, the copy whose `emotion`/`primaryGloss` are
  filled in wins, then the older one. **Where more than one copy carries loop, story, recording or
  review history, nothing is chosen**: the group is listed for the owner and left alone.
- **The copy dropped is tombstoned as the app's own delete does** (`repository.ts`, `delete`): the
  lexeme, its senses, attestations, examples, image prompts, pronunciations and study states, in one
  change set per word. Loop items and story words are left alone, as the app leaves them. Each record
  is resent whole as pulled, because an incoming change replaces every column. Tombstones are never
  collected, so a wrong choice can be undone.

    set -a; . ./credentials.env; set +a
    .venv/bin/python experiments/dictionary-checks/remove_duplicates.py            # dry run
    .venv/bin/python experiments/dictionary-checks/remove_duplicates.py --apply

Reads `ACERVO_SERVER_URL`, `ACERVO_OWNER_EMAIL` and `ACERVO_OWNER_PASSWORD` from the environment.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

from acervo.client import AcervoClient, AcervoError
from acervo.domain.ids import now_instant

DEVICE_ID = "dedupewordsscript"  # ^[a-z0-9]{1,32}$ (domain/ids.py)
# What the app's own delete tombstones with a word, in the order a change set is merged.
DEPENDENTS = ("senses", "attestations", "examples", "imagePrompts", "pronunciations", "studyStates")


def live(records: list[dict]) -> list[dict]:
    return [record for record in records if not record["deleted"]]


def by(records: list[dict], field: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for record in live(records):
        if record.get(field):
            out[record[field]].append(record)
    return out


class Graph:
    def __init__(self, changes: dict[str, list[dict]]) -> None:
        self.changes = changes
        self.senses = by(changes.get("senses", []), "lexemeId")
        self.examples = by(changes.get("examples", []), "senseId")
        self.per_lexeme = {
            kind: by(changes.get(kind, []), "lexemeId")
            for kind in ("attestations", "imagePrompts", "pronunciations", "studyStates", "loopItems", "storyWords")
        }

    def dependents(self, lexeme_id: str) -> dict[str, list[dict]]:
        senses = self.senses.get(lexeme_id, [])
        return {
            "senses": senses,
            "attestations": self.per_lexeme["attestations"].get(lexeme_id, []),
            "examples": [example for sense in senses for example in self.examples.get(sense["id"], [])],
            "imagePrompts": self.per_lexeme["imagePrompts"].get(lexeme_id, []),
            "pronunciations": self.per_lexeme["pronunciations"].get(lexeme_id, []),
            "studyStates": self.per_lexeme["studyStates"].get(lexeme_id, []),
        }

    def history(self, lexeme: dict) -> dict[str, int]:
        lexeme_id = lexeme["id"]
        own = self.dependents(lexeme_id)
        return {
            "loops": len(self.per_lexeme["loopItems"].get(lexeme_id, [])),
            "stories": len(self.per_lexeme["storyWords"].get(lexeme_id, [])),
            "recordings": sum(1 for record in own["pronunciations"] if record.get("audioRef")),
            "clips": sum(1 for record in own["examples"] if record.get("clipRef")),
            "attestations": len(own["attestations"]),
            "reps": sum(int(record.get("reps") or 0) for record in own["studyStates"]),
        }


# Kinds of history that only one copy can rightly own: a choice between two copies holding them is
# the owner's. Attestations and clips came with the bundle, so both copies hold the same ones.
EXCLUSIVE = ("loops", "stories", "recordings", "reps")


def choose(group: list[dict], graph: Graph) -> tuple[dict | None, str]:
    histories = {lexeme["id"]: graph.history(lexeme) for lexeme in group}
    carrying = [lexeme for lexeme in group if any(histories[lexeme["id"]][kind] for kind in EXCLUSIVE)]
    if len(carrying) > 1:
        return None, "history on more than one copy: " + "; ".join(
            f"{lexeme['id']} {describe(histories[lexeme['id']])}" for lexeme in carrying)

    def rank(lexeme: dict) -> tuple:
        history = histories[lexeme["id"]]
        filled = bool(lexeme.get("emotion")) + bool(lexeme.get("primaryGloss"))
        return (-sum(history.values()), -filled, lexeme["createdAt"], lexeme["id"])

    kept = min(group, key=rank)
    history = histories[kept["id"]]
    if carrying:
        return kept, f"only copy with {describe(history, EXCLUSIVE)}"
    others = [histories[lexeme["id"]] for lexeme in group if lexeme is not kept]
    if all(other == history for other in others):
        filled = [bool(lexeme.get("emotion")) + bool(lexeme.get("primaryGloss")) for lexeme in group]
        if len(set(filled)) > 1:
            return kept, "same history; emotion/primary gloss filled in"
        return kept, "same history; older"
    return kept, f"more history ({describe(history)})"


def describe(history: dict[str, int], kinds: tuple[str, ...] | None = None) -> str:
    shown = [f"{kind} {count}" for kind, count in history.items() if count and (kinds is None or kind in kinds)]
    return ", ".join(shown) or "none"


def tombstones(lexeme: dict, graph: Graph) -> dict[str, list[dict]]:
    stamp = {"deleted": True, "editedAt": now_instant(), "editedBy": DEVICE_ID}
    dependents = graph.dependents(lexeme["id"])
    changes = {"lexemes": [{**lexeme, **stamp}]}
    for kind in DEPENDENTS:
        if dependents[kind]:
            changes[kind] = [{**record, **stamp} for record in dependents[kind]]
    return changes


def duplicates(changes: dict[str, list[dict]]) -> list[list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for lexeme in live(changes.get("lexemes", [])):
        groups[(lexeme["language"], lexeme["headword"], lexeme["pos"])].append(lexeme)
    return sorted((group for group in groups.values() if len(group) > 1),
                  key=lambda group: (group[0]["language"], group[0]["headword"].lower()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write for real (default: dry run)")
    args = parser.parse_args(argv)

    client = AcervoClient(os.environ["ACERVO_SERVER_URL"])
    client.sign_in(os.environ["ACERVO_OWNER_EMAIL"], os.environ["ACERVO_OWNER_PASSWORD"])
    changes = client.pull_graph(since=0)["changes"]
    graph = Graph(changes)
    groups = duplicates(changes)

    plan: list[tuple[dict, dict]] = []  # (dropped lexeme, its change set)
    for_owner = []
    reasons: dict[str, int] = defaultdict(int)
    print(f"{len(groups)} duplicated word(s), {sum(len(group) for group in groups)} live copies\n")
    for group in groups:
        kept, reason = choose(group, graph)
        first = group[0]
        label = f"{first['language']} {first['headword']} ({first['pos']})"
        if kept is None:
            for_owner.append(label)
            print(f"OWNER  {label}: {reason}")
            continue
        reasons[reason.split(" (")[0]] += 1
        dropped = [lexeme for lexeme in group if lexeme is not kept]
        counts = defaultdict(int)
        for lexeme in dropped:
            change_set = tombstones(lexeme, graph)
            plan.append((lexeme, change_set))
            for kind, records in change_set.items():
                counts[kind] += len(records)
        print(f"keep {kept['id']}  drop {', '.join(lexeme['id'] for lexeme in dropped)}  {label}: {reason}; "
              + ", ".join(f"{kind} {count}" for kind, count in counts.items()))

    totals: dict[str, int] = defaultdict(int)
    for _, change_set in plan:
        for kind, records in change_set.items():
            totals[kind] += len(records)
    print(f"\nwords to drop: {len(plan)}; left for the owner: {len(for_owner)}")
    print("why kept: " + "; ".join(f"{reason} {count}" for reason, count in sorted(reasons.items())))
    print("records to tombstone: " + ", ".join(f"{kind} {count}" for kind, count in totals.items()))
    dropped_ids = {lexeme["id"] for lexeme, _ in plan}
    orphaned = sum(1 for lexeme_id in dropped_ids
                   for kind in ("loopItems", "storyWords") for _ in graph.per_lexeme[kind].get(lexeme_id, []))
    print(f"loop items and story words left naming a dropped copy: {orphaned}")
    dropped_reps = sum(graph.history(lexeme)["reps"] for lexeme, _ in plan)
    print(f"Anki repetitions on dropped copies: {dropped_reps} (their notes go on the next Anki push)")

    if not args.apply:
        print("\nDry run: nothing written. Add --apply to write.")
        return 0

    written, refused = 0, []
    for lexeme, change_set in plan:
        try:
            client.push_graph(change_set, device_id=DEVICE_ID)
            written += 1
        except AcervoError as failure:
            refused.append(f"{lexeme['id']} {lexeme['headword']}: {failure.code} {failure}")
    print(f"\ndropped {written} word(s); refused {len(refused)}")
    for line in refused:
        print(f"  refused {line}", file=sys.stderr)

    remaining = duplicates(client.pull_graph(since=0)["changes"])
    print(f"duplicated words left after re-pull: {len(remaining)}")
    return 0 if not refused else 1


if __name__ == "__main__":
    raise SystemExit(main())
