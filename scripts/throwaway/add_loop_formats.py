"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that made loops
programme formats, with every spoken line stored — and it exists so that the owner's words, pictures,
recordings and loops are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

What changes, and what this does about each:

  * `loops.pattern` becomes `format`. Every loop made so far is a drill: `retrieval` was the drill
    now called `classic`, and `alternating` keeps its name. `switches` and `fallback_from` are added
    empty, which is what a loop made with a format's defaults, that did not fall back, stores.
  * `loop_items` loses `repeats` and `repeat_seconds`, and its two reveal times may now be empty.
    SQLite cannot relax a NOT NULL in place, so the table is rebuilt with every row copied.
  * `loop_cues` is new, and **every rendered loop gets its lines back**. They are rebuilt from the
    times its items already store, by the rule the player used to read them with: the word at the
    item's start, its translation at the target reveal, and then the pair again, `repeat_seconds`
    apart, `repeats` times in all. A line ends where the next begins. Each row takes a fresh id and
    a fresh revision from its owner's counter, as every writer's does.
  * `loop_scripts` is new and starts empty: no loop made so far had a writer.
  * `pronunciation_settings.guide_voices` is added empty: no guide voice is chosen.

Every other table is checked first to be exactly what the code expects, and the whole schema is
checked again afterwards.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, on a copy you have taken first, with the server stopped:

    python scripts/throwaway/add_loop_formats.py --database PATH --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import CreateIndex, CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402
from acervo.domain.ids import new_record_id, now_instant  # noqa: E402
from acervo.repository.graph import allocate_revision  # noqa: E402

# The one head this converts *from*. `transition.py` reads it to choose this script.
FROM_REVISION = "bootstrap_3c552a5b22ba"

CHANGED = ("loops", "loop_items", "pronunciation_settings")
CREATED = ("loop_cues", "loop_scripts")
# What the changed tables held before, by the columns this script moves.
BEFORE = {
    "loops": {"has": {"pattern"}, "lacks": {"format", "switches", "fallback_from"}},
    "loop_items": {"has": {"repeats", "repeat_seconds"}, "lacks": set()},
    "pronunciation_settings": {"has": set(), "lacks": {"guide_voices"}},
}
FORMATS = {"retrieval": "classic", "alternating": "alternating", "": "classic"}


def utterances(item: dict) -> list[tuple[str, float]]:
    """A drill item's lines as `(side, start)`, by the rule the player read them with."""
    heard = 2 * int(item["repeats"]) if item["repeats"] > 0 and item["repeat_seconds"] > 0 else 2
    starts = [float(item["start_seconds"]), float(item["target_reveal_seconds"])]
    starts += [float(item["target_reveal_seconds"]) + (n - 1) * float(item["repeat_seconds"])
               for n in range(2, heard)]
    return [("source" if n % 2 == 0 else "target", start) for n, start in enumerate(starts)]


def cues_for(loop: dict, items: list[dict], gloss: str) -> list[dict]:
    """Every line of one rendered drill, as `loop_cues` rows without id, stamp or revision."""
    rows: list[dict] = []
    for group, item in enumerate(items):
        lines = utterances(item)
        for n, (side, start) in enumerate(lines):
            end = lines[n + 1][1] if n + 1 < len(lines) else float(item["end_seconds"])
            rows.append({
                "owner": loop["owner"], "loop": loop["id"], "cue_order": len(rows),
                "cue_group": group, "kind": "say", "section": "words", "loop_item": item["id"],
                "side": side, "role": "native" if side == "source" else "guide",
                "language": loop["language"] if side == "source" else gloss,
                "text": item["source_text"] if side == "source" else item["target_text"],
                "take": n // 2, "start_seconds": start, "end_seconds": max(end, start),
            })
    return rows


def _gloss_languages(connection) -> dict[tuple[str, str], str]:
    """The first gloss language of each owner's vocabulary, by language: a loop's translations are
    in it, as its renders were asked for them. English where a vocabulary names none."""
    found: dict[tuple[str, str], str] = {}
    for owner, language, glosses in connection.execute(text(
            "SELECT owner, language, gloss_langs FROM vocabularies WHERE deleted = 0")):
        listed = json.loads(glosses) if isinstance(glosses, str) else glosses
        found.setdefault((owner, language), (listed or ["en"])[0])
    return found


def _planned(connection) -> tuple[list[dict], dict[str, list[dict]], dict[tuple[str, str], str]]:
    loops = [dict(row) for row in connection.execute(text("SELECT * FROM loops")).mappings()]
    items: dict[str, list[dict]] = {}
    for row in connection.execute(text(
            "SELECT * FROM loop_items WHERE deleted = 0 ORDER BY loop, item_order")).mappings():
        items.setdefault(row["loop"], []).append(dict(row))
    return loops, items, _gloss_languages(connection)


def _rendered(loop: dict) -> bool:
    return not loop["deleted"] and bool(loop["audio_ref"])


def _rebuild(connection, name: str) -> None:
    """Replace a table by the code's own declaration of it, keeping every row.

    SQLite's own recipe: create the new table beside the old, copy, drop the old, rename. Foreign
    keys are off on this connection, so nothing cascades when the old table is dropped.
    """
    table = metadata.tables[name]
    create = str(CreateTable(table).compile(connection)).strip()
    assert create.startswith(f"CREATE TABLE {name} ")
    connection.execute(text(create.replace(f"CREATE TABLE {name} ", f"CREATE TABLE {name}_new ", 1)))
    kept = ", ".join(column.name for column in table.columns)
    connection.execute(text(f"INSERT INTO {name}_new ({kept}) SELECT {kept} FROM {name}"))
    connection.execute(text(f"DROP TABLE {name}"))
    connection.execute(text(f"ALTER TABLE {name}_new RENAME TO {name}"))
    for index in table.indexes:
        connection.execute(CreateIndex(index))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--database", required=True, type=Path, help="the acervo.db to convert")
    parser.add_argument("--dry-run", action="store_true", help="check everything, write nothing")
    args = parser.parse_args(argv)

    if not args.database.exists():
        print(f"There is no database at {args.database}.", file=sys.stderr)
        return 2

    engine = create_engine(f"sqlite+pysqlite:///{args.database}")
    stamped = schemacheck.stamped(engine)

    if stamped == HEAD:
        print(f"Already at {HEAD}. Nothing to do.")
        return 0
    # Refused by name: a database stamped with anything but the one head this script was written
    # against is one it has not been reasoned about, and guessing is what a converter must not do.
    if stamped != FROM_REVISION:
        print(
            f"This database is stamped {stamped or 'nothing'}, not {FROM_REVISION}.\n"
            "This script converts one specific schema change and refuses any other. Rebuild with "
            "./deploy.sh --reset-database instead.",
            file=sys.stderr,
        )
        return 2

    others = sorted(name for name in metadata.tables if name not in (*CHANGED, *CREATED))
    problems = schemacheck.compare(engine, metadata, others)
    inspector = inspect(engine)
    for name, shape in BEFORE.items():
        columns = {column["name"] for column in inspector.get_columns(name)}
        problems += [f"{name}: has no {column}" for column in sorted(shape["has"] - columns)]
        problems += [f"{name}: already has {column}" for column in sorted(shape["lacks"] & columns)]
    problems += [f"{name}: already exists" for name in CREATED if inspector.has_table(name)]
    if problems:
        print(
            "This database is not the one this script was written for:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    with engine.connect() as connection:
        loops, items, glosses = _planned(connection)
    unknown = sorted({loop["pattern"] for loop in loops} - set(FORMATS))
    if unknown:
        print(f"Some loops have a pattern this script does not know: {', '.join(unknown)}.\n"
              "Nothing was written.", file=sys.stderr)
        return 2
    lines = {loop["id"]: cues_for(loop, items.get(loop["id"], []),
                                  glosses.get((loop["owner"], loop["language"]), "en"))
             for loop in loops if _rendered(loop)}

    print(f"{len(others)} other tables match the code exactly.")
    for (before, after), count in sorted(Counter(
            (loop["pattern"] or "(none)", FORMATS[loop["pattern"]]) for loop in loops).items()):
        print(f"Loops: {count} {before} → format {after}")
    print(f"Rendered loops: {len(lines)}, given {sum(map(len, lines.values()))} lines between them")
    print(f"Loop items: {sum(map(len, items.values()))} kept, without repeats and repeat_seconds")
    print(f"Creating: {', '.join(CREATED)}; adding pronunciation_settings.guide_voices")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE loops RENAME COLUMN pattern TO format"))
        for before, after in FORMATS.items():
            connection.execute(text("UPDATE loops SET format = :after WHERE format = :before"),
                               {"before": before, "after": after})
        connection.execute(text("ALTER TABLE loops ADD COLUMN switches JSON NOT NULL DEFAULT '{}'"))
        connection.execute(text(
            "ALTER TABLE loops ADD COLUMN fallback_from VARCHAR(64) NOT NULL DEFAULT ''"))
        connection.execute(text(
            "ALTER TABLE pronunciation_settings ADD COLUMN guide_voices JSON NOT NULL DEFAULT '{}'"))
        _rebuild(connection, "loop_items")
        for name in CREATED:
            metadata.tables[name].create(connection)
        at = now_instant()
        by = {loop["id"]: loop["edited_by"] for loop in loops}
        for loop_id, rows in lines.items():
            for row in rows:
                connection.execute(metadata.tables["loop_cues"].insert().values(
                    **row, id=new_record_id(), deleted=False, created_at=at, edited_at=at,
                    edited_by=by[loop_id], revision=allocate_revision(connection, row["owner"])))
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema and the lines written, so the script proves what it
    # claims rather than reporting that it finished.
    remaining = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    with engine.connect() as connection:
        written = connection.execute(text("SELECT COUNT(*) FROM loop_cues")).scalar_one()
    wanted = sum(map(len, lines.values()))
    if remaining or schemacheck.stamped(engine) != HEAD or written != wanted:
        print("The conversion did not land cleanly:\n  "
              + "\n  ".join(remaining + ([f"loop_cues holds {written} lines, not {wanted}"]
                                         if written != wanted else [])), file=sys.stderr)
        return 1

    print(f"\nDone. All {len(metadata.tables)} tables match, {written} lines written, stamped {HEAD}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
