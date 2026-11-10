"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that gave loops and stories
the owner's two marks, `starred` and `archived`, and added `plays`, one record per play of a loop or
read of a story — so that the owner's words, pictures, recordings, loops and stories are not rebuilt
along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

What changes: every loop and every story gains both marks, off, which is true of all of them — nothing
could set them before. `plays` is created empty: nothing was counted before, so every loop and story
starts with none. Nothing else is touched. The database is first checked to be exactly the schema
before the change, table by table, and the whole new schema is checked afterwards.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, on a copy you have taken first, with the server stopped:

    python scripts/throwaway/add_marks_and_plays.py --database PATH --dry-run
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
FROM_REVISION = "bootstrap_a4cd9ee540f7"

# In the order each table declares them, which is the order `ALTER TABLE` appends them in.
ADDED = {
    "loops": (("starred", "BOOLEAN NOT NULL DEFAULT 0"), ("archived", "BOOLEAN NOT NULL DEFAULT 0")),
    "stories": (("starred", "BOOLEAN NOT NULL DEFAULT 0"), ("archived", "BOOLEAN NOT NULL DEFAULT 0")),
}
CREATED = "plays"


def before() -> MetaData:
    """Today's schema with the marks and `plays` taken back out: the shape this script expects to find."""
    old = MetaData()
    for table in metadata.sorted_tables:
        if table.name != CREATED:
            table.to_metadata(old)
    for name, columns in ADDED.items():
        table = old.tables[name]
        for column, _ in columns:
            table._columns.remove(table.c[column])
    return old


def counts(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {name: connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
                for name in ("lexemes", "loops", "stories", "beds")}


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
    inspector = inspect(engine)
    for name, columns in ADDED.items():
        present = {column["name"] for column in inspector.get_columns(name)}
        problems += [f"{name}.{column}: already exists" for column, _ in columns if column in present]
    if inspector.has_table(CREATED):
        problems.append(f"{CREATED}: already exists")
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
    print(f"Loops:      {held['loops']} kept, none starred or archived yet")
    print(f"Stories:    {held['stories']} kept, none starred or archived yet")
    print(f"Plays:      a new, empty table — nothing was counted before")
    print(f"Kept music: {held['beds']} kept")
    print(f"Words:      {held['lexemes']} kept")
    print(f"Stamp:      {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        for name, columns in ADDED.items():
            for column, declaration in columns:
                connection.execute(text(f"ALTER TABLE {name} ADD COLUMN {column} {declaration}"))
        metadata.tables[CREATED].create(connection)
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
