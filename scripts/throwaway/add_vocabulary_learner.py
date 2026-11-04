"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that gave a vocabulary a
level and a note about the learner, and made its flag follow its variety — so that the owner's words,
pictures and recordings are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

What changes, and what this does about each:

  * `vocabularies.level` and `vocabularies.learner_note` are added empty: no vocabulary states a level
    or says anything about its learner until the owner writes it, and the writers see what they saw.
  * `vocabularies.flag` now means the owner's own flag, and empty means "follow the variety". A flag
    that is what the device would derive anyway — the variety's, or the language's main region's —
    or the white placeholder flag, is emptied, so it follows the variety from now on. Any other flag
    is the owner's choice and is kept. Nothing anybody sees changes, except a white flag that gains
    its country's.

Every other table is checked first to be exactly what the code expects, and the whole schema is
checked again afterwards.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, on a copy you have taken first, with the server stopped:

    python scripts/throwaway/add_vocabulary_learner.py --database PATH --dry-run
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
from acervo.models import locales  # noqa: E402

# The one head this converts *from*. `transition.py` reads it to choose this script.
FROM_REVISION = "bootstrap_25651c6309bb"

# {table: [(column, DDL), ...]}: what is added, each as the code declares it.
ADDED = {
    "vocabularies": [
        ("level", "VARCHAR(2) NOT NULL DEFAULT ''"),
        ("learner_note", "VARCHAR(1000) NOT NULL DEFAULT ''"),
    ],
}

# The flag a vocabulary was given when the device had none to offer.
PLACEHOLDER = "\U0001F3F3️"


def flag_of(region: str | None) -> str | None:
    """The emoji flag of a two-letter region; None for a wider one (`419`) or none."""
    if not region or len(region) != 2 or not region.isalpha():
        return None
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in region.upper())


def derived(language: str, region: str) -> str | None:
    """The flag the device shows for a vocabulary with no flag of its own."""
    return flag_of(region or locales.likely(language).region)


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
        rows = connection.execute(text(
            "SELECT id, language, region, flag FROM vocabularies WHERE flag != ''")).mappings().all()
        vocabularies = connection.execute(text("SELECT COUNT(*) FROM vocabularies")).scalar_one()
    following = [row for row in rows if row["flag"] in (PLACEHOLDER, derived(row["language"], row["region"]))]
    kept = [row for row in rows if row not in following]

    print(f"{len(others)} other tables match the code exactly.")
    print(f"Vocabularies: {vocabularies} kept, each given no level and no note")
    for row in following:
        print(f"  {row['language']}: flag {row['flag']} now follows the variety")
    for row in kept:
        print(f"  {row['language']}: flag {row['flag']} kept as the owner's own")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        for name, added in ADDED.items():
            for column, ddl in added:
                connection.execute(text(f"ALTER TABLE {name} ADD COLUMN {column} {ddl}"))
        # The flag column is not replicated news: the replica is wiped and pulled again under the new
        # schema version, so emptying it in place needs no new revision.
        for row in following:
            connection.execute(text("UPDATE vocabularies SET flag = '' WHERE id = :id"), {"id": row["id"]})
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema, so the script proves what it claims rather than
    # reporting that it finished.
    remaining = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    with engine.connect() as connection:
        after = connection.execute(text("SELECT COUNT(*) FROM vocabularies")).scalar_one()
    if remaining or schemacheck.stamped(engine) != HEAD or after != vocabularies:
        print("The conversion did not land cleanly:\n  " + "\n  ".join(
            remaining + ([f"vocabularies holds {after} rows, not {vocabularies}"] if after != vocabularies else [])),
            file=sys.stderr)
        return 1

    print(f"\nDone. All {len(metadata.tables)} tables match, stamped {HEAD}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
