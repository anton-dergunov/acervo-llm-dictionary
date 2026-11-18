"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change: the one that gave each owner's
model chains the switch "Check what models write" (`model_selection.check_answers`). The owner's
words, pictures, recordings, loops and stories are kept rather than rebuilt with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids. By then `FROM_REVISION` below will match no
database at all, which is how a stale one shows itself.

What changes: every stored `model_selection` row gains `check_answers`, on, which is what every owner
had before: compose always checked. An owner with no row reads as on already. Nothing else is
touched. Before anything is written, the database is checked table by table against exactly the
schema before the change, and afterwards the whole new schema is checked.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, with the server stopped, on a copy you have taken first:

    python scripts/throwaway/add_check_answers.py --database PATH --dry-run
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
FROM_REVISION = "bootstrap_bd9162f70d66"

TABLE = "model_selection"
COLUMN = "check_answers"
DECLARATION = "BOOLEAN NOT NULL DEFAULT 1"


def before() -> MetaData:
    """Today's schema with the switch taken back out: the shape this script expects to find."""
    old = MetaData()
    for table in metadata.sorted_tables:
        table.to_metadata(old)
    table = old.tables[TABLE]
    table._columns.remove(table.c[COLUMN])
    return old


def counts(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {name: connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
                for name in ("lexemes", TABLE)}


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
    # Refused by name: this script was written against one head only. A database stamped with
    # anything else has not been reasoned about, and a converter must not guess.
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
    if COLUMN in {column["name"] for column in inspect(engine).get_columns(TABLE)}:
        problems.append(f"{TABLE}.{COLUMN}: already exists")
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
    print(f"Model chains: {held[TABLE]} owner(s) with saved chains, each now checking what models write")
    print(f"Words:        {held['lexemes']} kept")
    print(f"Stamp:        {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} {DECLARATION}"))
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Checked against the *whole* new schema, so the script proves what it claims rather than only
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
