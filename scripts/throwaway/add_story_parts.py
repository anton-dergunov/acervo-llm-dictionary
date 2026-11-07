"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that gave `stories` a
`parts` column, the number of parts the owner asked for — so that the owner's words, pictures,
recordings, loops and stories are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

What changes: every story gains `parts = 4`, which is true of all of them, since every story before
this change was written in four parts. Nothing else is touched. The database is first checked to be
exactly the schema before the change, table by table, and the whole new schema is checked afterwards.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, on a copy you have taken first, with the server stopped:

    python scripts/throwaway/add_story_parts.py --database PATH --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

# The one head this converts *from*. `transition.py` reads it to choose this script.
FROM_REVISION = "bootstrap_93644b4a30c8"

TABLE = "stories"
ADDED = "parts"
# Every story written before this change has four parts: the writer was always asked for four.
WRITTEN_WITH = 4


def before() -> MetaData:
    """Today's schema with the new column taken back out: the shape this script expects to find."""
    old = MetaData()
    for table in metadata.sorted_tables:
        table.to_metadata(old)
    stories = old.tables[TABLE]
    stories._columns.remove(stories.c[ADDED])
    return old


def counts(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {name: connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
                for name in ("lexemes", "stories", "story_parts", "loops", "beds")}


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

    expected = before()
    problems = schemacheck.compare(engine, expected, sorted(expected.tables))
    if ADDED in {column["name"] for column in inspect(engine).get_columns(TABLE)}:
        problems.append(f"{TABLE}.{ADDED}: already exists")
    if problems:
        print(
            "This database is not the one this script was written for:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    held = counts(engine)
    print(f"{len(expected.tables)} tables match the schema before the change exactly.")
    print(f"Stories:   {held['stories']} kept, each with {ADDED} = {WRITTEN_WITH}, as it was written")
    print(f"Parts:     {held['story_parts']} kept")
    print(f"Loops:     {held['loops']} kept, and {held['beds']} saved pieces of music")
    print(f"Words:     {held['lexemes']} kept")
    print(f"Stamp:     {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        connection.execute(text(
            f"ALTER TABLE {TABLE} ADD COLUMN {ADDED} INTEGER NOT NULL DEFAULT {WRITTEN_WITH}"))
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema, so the script proves what it claims rather than
    # reporting that it finished.
    remaining = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    after = counts(engine)
    lost = [f"{name} holds {after[name]} rows, not {held[name]}" for name in held if after[name] != held[name]]
    if remaining or lost or schemacheck.stamped(engine) != HEAD:
        print("The conversion did not land cleanly:\n  " + "\n  ".join(remaining + lost), file=sys.stderr)
        return 1

    print(f"\nDone. All {len(metadata.tables)} tables match, stamped {HEAD}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
