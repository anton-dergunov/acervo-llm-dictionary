"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that gave a vocabulary an
accent and let the owner choose which voice reads each language first — so that the owner's words,
pictures and recordings are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

What changes, and what this does about each:

  * `vocabularies.region` is added empty: no vocabulary has an accent until the owner chooses one,
    and a vocabulary without one sounds exactly as it did.
  * `pronunciation_settings.first_voices` and `guide_first_voices` are added empty: each language is
    read first by its order's first voice, as before, until the owner chooses another.

The voices already chosen (`voices`, `guide_voices`) keep their shape and are not touched. Every
other table is checked first to be exactly what the code expects, and the whole schema is checked
again afterwards.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, on a copy you have taken first, with the server stopped:

    python scripts/throwaway/add_vocabulary_accent.py --database PATH --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

# The one head this converts *from*. `transition.py` reads it to choose this script.
FROM_REVISION = "bootstrap_c0882c2bd8dd"

# {table: [(column, DDL), ...]}: what is added, each as the code declares it.
ADDED = {
    "vocabularies": [("region", "VARCHAR(8) NOT NULL DEFAULT ''")],
    "pronunciation_settings": [
        ("first_voices", "JSON NOT NULL DEFAULT '{}'"),
        ("guide_first_voices", "JSON NOT NULL DEFAULT '{}'"),
    ],
}


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

    others = sorted(name for name in metadata.tables if name not in ADDED)
    problems = schemacheck.compare(engine, metadata, others)
    inspector = inspect(engine)
    for name, added in ADDED.items():
        columns = {column["name"] for column in inspector.get_columns(name)}
        wanted = {column.name for column in metadata.tables[name].columns}
        new = {column for column, _ in added}
        problems += [f"{name}: already has {column}" for column in sorted(new & columns)]
        problems += [f"{name}: has no {column}" for column in sorted(wanted - new - columns)]
        problems += [f"{name}: has {column}, which the code does not" for column in sorted(columns - wanted)]
    if problems:
        print(
            "This database is not the one this script was written for:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    with engine.connect() as connection:
        vocabularies = connection.execute(text("SELECT COUNT(*) FROM vocabularies")).scalar_one()
        settings = connection.execute(text("SELECT COUNT(*) FROM pronunciation_settings")).scalar_one()

    print(f"{len(others)} other tables match the code exactly.")
    print(f"Vocabularies: {vocabularies} kept, each given an empty accent")
    print(f"Pronunciation settings: {settings} kept, each given no first voice; chosen voices untouched")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        for name, added in ADDED.items():
            for column, ddl in added:
                connection.execute(text(f"ALTER TABLE {name} ADD COLUMN {column} {ddl}"))
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema, so the script proves what it claims rather than
    # reporting that it finished.
    remaining = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    with engine.connect() as connection:
        kept = connection.execute(text("SELECT COUNT(*) FROM vocabularies")).scalar_one()
    if remaining or schemacheck.stamped(engine) != HEAD or kept != vocabularies:
        print("The conversion did not land cleanly:\n  " + "\n  ".join(
            remaining + ([f"vocabularies holds {kept} rows, not {vocabularies}"] if kept != vocabularies else [])),
            file=sys.stderr)
        return 1

    print(f"\nDone. All {len(metadata.tables)} tables match, stamped {HEAD}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
