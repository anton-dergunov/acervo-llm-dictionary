"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that moved the providers
from a tracked catalogue and `llm.env` into a `providers` table and a secrets file beside the
database — so that the owner's words, pictures and recordings are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

What changes, and what this does about each:

  * `providers` is created empty. The owner adds their providers again in Settings ▸ Providers, with
    their keys; no key is carried across, and none is written by this script.
  * Every owner's chosen orders (`model_selection`) are forgotten. They name the catalogue's provider
    and model ids — `gemini-free`, `gemini/gemini-3.5-flash-lite` — which nothing offers any more, and
    a pair nobody offers refuses every call. With none chosen, the providers answer in the order they
    are added again, and the owner chooses once more.
  * Every owner's voice choices in `pronunciation_settings` — the voice per pair and language, and
    which pair reads first — are emptied for the same reason. Which uses read with which order, and
    what is recorded in advance, are kept.

Every other table is checked first to be exactly what the code expects, and the whole schema is
checked again afterwards.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, on a copy you have taken first, with the server stopped:

    python scripts/throwaway/add_providers.py --database PATH --dry-run
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
FROM_REVISION = "bootstrap_901618fed59b"

ADDED = "providers"
VOICE_COLUMNS = ("voices", "guide_voices", "first_voices", "guide_first_voices")


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

    others = sorted(name for name in metadata.tables if name != ADDED)
    problems = schemacheck.compare(engine, metadata, others)
    if ADDED in inspect(engine).get_table_names():
        problems.append(f"{ADDED}: already exists")
    if problems:
        print(
            "This database is not the one this script was written for:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    with engine.connect() as connection:
        orders = connection.execute(text("SELECT COUNT(*) FROM model_selection")).scalar_one()
        voices = connection.execute(text(
            "SELECT COUNT(*) FROM pronunciation_settings WHERE "
            + " OR ".join(f"{column} NOT IN ('{{}}', '')" for column in VOICE_COLUMNS)
        )).scalar_one()
        lexemes = connection.execute(text("SELECT COUNT(*) FROM lexemes")).scalar_one()

    print(f"{len(others)} other tables match the code exactly.")
    print("Providers: a new, empty table. Add them again in Settings ▸ Providers.")
    print(f"Orders:    {orders} account(s) forget their chosen orders, which name providers that are gone")
    print(f"Voices:    {voices} account(s) forget their chosen voices, for the same reason")
    print(f"Words:     {lexemes} kept")
    print(f"Stamp:     {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        metadata.tables[ADDED].create(connection)
        connection.execute(text("DELETE FROM model_selection"))
        connection.execute(text(
            "UPDATE pronunciation_settings SET " + ", ".join(f"{column} = '{{}}'" for column in VOICE_COLUMNS)
        ))
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema, so the script proves what it claims rather than
    # reporting that it finished.
    remaining = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    with engine.connect() as connection:
        after = connection.execute(text("SELECT COUNT(*) FROM lexemes")).scalar_one()
    if remaining or schemacheck.stamped(engine) != HEAD or after != lexemes:
        print("The conversion did not land cleanly:\n  " + "\n  ".join(
            remaining + ([f"lexemes holds {after} rows, not {lexemes}"] if after != lexemes else [])),
            file=sys.stderr)
        return 1

    print(f"\nDone. All {len(metadata.tables)} tables match, stamped {HEAD}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
