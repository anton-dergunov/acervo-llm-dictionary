"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that let an account keep
several vocabularies of one language, so that a word, a loop and a story name their vocabulary by id
rather than by language — and it exists so that the owner's words, pictures, recordings, loops and
stories are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

What changes, and what this does about each:

  * `lexemes`, `loops` and `stories` gain `vocabulary`, the id of the vocabulary they are in, and
    their index by language becomes one by vocabulary. Until now an account held one vocabulary per
    language, so each row is given its owner's vocabulary of its own language. SQLite cannot add a
    NOT NULL column with a foreign key in place, so the three tables are rebuilt with every row kept.
  * An owner holding two live vocabularies of one language (the server never forbade it, the device
    did) is refused by name: which one a word was in cannot be worked out, and guessing is what a
    converter must not do.
  * A language holding words but no vocabulary — a vocabulary removed while it still had words — is
    given one, with its senses defined in the language itself and the owner's usual gloss language,
    and a fresh revision from the owner's counter, so every device receives it. It is a tombstone if
    only tombstones need it. The dry run names each one.
  * Each drawn meaning map, kept beside the database as `maps/artifacts/<owner>/<language>.json`, is
    renamed for its vocabulary's id, so its region names — a model call each — are kept. This happens
    only once the database has converted and checked out.

Revisions are left as they are: every device's copy is wiped and pulled again with the release.

Every other table is checked first to be exactly what the code expects, and the whole schema is
checked again afterwards.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real.
To run it alone, on a copy you have taken first, with the server stopped:

    python scripts/throwaway/add_vocabulary_ids.py --database PATH --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import Index, MetaData, create_engine, text
from sqlalchemy.schema import CreateIndex, CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402
from acervo.domain.ids import new_record_id, now_instant  # noqa: E402
from acervo.repository.graph import allocate_revision  # noqa: E402

# The one head this converts *from*. `transition.py` reads it to choose this script.
FROM_REVISION = "bootstrap_43bc6845036e"

# Each changed table, and the index by language it had in place of today's by vocabulary.
CHANGED = {
    "lexemes": ("idx_lexemes_owner_language_headword", ("owner", "language", "headword")),
    "loops": ("idx_loops_owner_language_order", ("owner", "language", "loop_order")),
    "stories": ("idx_stories_owner_language_order", ("owner", "language", "story_order")),
}
EDITOR = "acervoconverter"


def before() -> MetaData:
    """Today's schema with the change taken back out: the shape this script expects to find."""
    old = MetaData()
    for table in metadata.sorted_tables:
        copy = table.to_metadata(old)
        if table.name not in CHANGED:
            continue
        column = copy.c.vocabulary
        for key in list(column.foreign_keys):
            copy.foreign_keys.discard(key)
            copy.constraints.discard(key.constraint)
        for index in [index for index in copy.indexes if "vocabulary" in index.columns]:
            copy.indexes.discard(index)
        copy._columns.remove(column)
        name, columns = CHANGED[table.name]
        Index(name, *[copy.c[one] for one in columns])
    return old


class Plan:
    """What the conversion will write, worked out before anything is. A plain class rather than a
    dataclass: `transition.py` loads this file without registering it as a module, and a dataclass
    looks its own module up."""

    def __init__(self) -> None:
        # (owner, language) -> the vocabulary id every row of that language takes.
        self.chosen: dict[tuple[str, str], str] = {}
        # Vocabularies to create: a row for `vocabularies` without its revision.
        self.created: list[dict] = []
        # Rows per changed table, live and removed.
        self.counts: dict[str, Counter] = {}
        # Owners with two live vocabularies of one language: (owner, language, ids).
        self.ambiguous: list[tuple[str, str, list[str]]] = []


def _gloss(rows: list[dict]) -> str:
    """The owner's usual gloss language: the first of their first vocabulary's, else English."""
    for row in sorted(rows, key=lambda one: (one["deleted"], one["vocab_order"], one["id"])):
        listed = json.loads(row["gloss_langs"]) if isinstance(row["gloss_langs"], str) else row["gloss_langs"]
        if listed:
            return listed[0]
    return "en"


def planned(connection) -> Plan:
    plan = Plan()
    vocabularies = [dict(row) for row in connection.execute(text("SELECT * FROM vocabularies")).mappings()]
    live: dict[tuple[str, str], list[dict]] = defaultdict(list)
    removed: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_owner: dict[str, list[dict]] = defaultdict(list)
    for row in vocabularies:
        (removed if row["deleted"] else live)[(row["owner"], row["language"])].append(row)
        by_owner[row["owner"]].append(row)

    needed: dict[tuple[str, str], bool] = {}   # (owner, language) -> whether a live row needs it
    for name in CHANGED:
        plan.counts[name] = Counter()
        for owner, language, deleted in connection.execute(
                text(f"SELECT owner, language, deleted FROM {name}")):
            plan.counts[name]["tombstones" if deleted else "live"] += 1
            needed[(owner, language)] = needed.get((owner, language), False) or not deleted

    at = now_instant()
    for key, alive in sorted(needed.items()):
        owner, language = key
        held = sorted(live.get(key, []), key=lambda one: (one["vocab_order"], one["id"]))
        if len(held) > 1:
            plan.ambiguous.append((owner, language, [one["id"] for one in held]))
            continue
        if held:
            plan.chosen[key] = held[0]["id"]
            continue
        gone = sorted(removed.get(key, []), key=lambda one: one["edited_at"], reverse=True)
        if not alive and gone:
            plan.chosen[key] = gone[0]["id"]
            continue
        gloss = _gloss(by_owner.get(owner, []))
        created = {
            "id": new_record_id(), "owner": owner, "language": language, "definition_lang": language,
            "gloss_langs": [gloss], "notes_lang": gloss, "display_name": "", "flag": "", "region": "",
            "level": "", "learner_note": "",
            "vocab_order": 1 + max((one["vocab_order"] for one in by_owner.get(owner, [])), default=-1),
            "deleted": not alive, "created_at": at, "edited_at": at, "edited_by": EDITOR,
        }
        by_owner[owner].append({**created, "gloss_langs": json.dumps(created["gloss_langs"])})
        plan.created.append(created)
        plan.chosen[key] = created["id"]
    return plan


def _rebuild(connection, name: str, chosen: dict[tuple[str, str], str]) -> None:
    """Replace a table by the code's own declaration of it, keeping every row and giving each its
    vocabulary. SQLite's own recipe: create the new table beside the old, copy, drop the old, rename.
    Foreign keys are off on this connection, so nothing cascades when the old table is dropped."""
    table = metadata.tables[name]
    create = str(CreateTable(table).compile(connection)).strip()
    assert create.startswith(f"CREATE TABLE {name} ")
    connection.execute(text(create.replace(f"CREATE TABLE {name} ", f"CREATE TABLE {name}_new ", 1)))
    kept = [column.name for column in table.columns if column.name != "vocabulary"]
    connection.execute(text(
        f"INSERT INTO {name}_new ({', '.join(kept)}, vocabulary) "
        f"SELECT {', '.join(kept)}, '' FROM {name}"))
    for (owner, language), vocabulary in chosen.items():
        connection.execute(
            text(f"UPDATE {name}_new SET vocabulary = :vocabulary WHERE owner = :owner AND language = :language"),
            {"vocabulary": vocabulary, "owner": owner, "language": language})
    connection.execute(text(f"DROP TABLE {name}"))
    connection.execute(text(f"ALTER TABLE {name}_new RENAME TO {name}"))
    for index in table.indexes:
        connection.execute(CreateIndex(index))


def maps_to_rename(database: Path, chosen: dict[tuple[str, str], str]) -> list[tuple[Path, Path]]:
    """Each drawn map by language that has a vocabulary to be named for, as `(from, to)`."""
    root = database.parent / "maps" / "artifacts"
    moves = []
    for path in sorted(root.glob("*/*.json")) if root.is_dir() else []:
        vocabulary = chosen.get((path.parent.name, path.stem))
        if vocabulary is not None:
            moves.append((path, path.with_name(f"{vocabulary}.json")))
    return moves


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

    problems = schemacheck.compare(engine, before(), sorted(metadata.tables))
    if problems:
        print(
            "This database is not the one this script was written for:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    with engine.connect() as connection:
        plan = planned(connection)
    if plan.ambiguous:
        print(
            "Some owners keep two vocabularies of one language, so which one each word is in cannot "
            "be worked out:\n  "
            + "\n  ".join(f"owner {owner}, {language}: vocabularies {', '.join(ids)}"
                          for owner, language, ids in plan.ambiguous)
            + "\n\nRemove all but one of each on a device running the previous release, then run this "
              "again. Nothing was written.",
            file=sys.stderr,
        )
        return 2
    moves = maps_to_rename(args.database, plan.chosen)

    print(f"{len(metadata.tables) - len(CHANGED)} other tables match the code exactly.")
    for name, counted in plan.counts.items():
        print(f"{name.capitalize()}: {counted['live']} live and {counted['tombstones']} removed, "
              "each given its owner's vocabulary of its language")
    print(f"Vocabularies named: {len(plan.chosen)}")
    for created in plan.created:
        print(f"Vocabulary created for owner {created['owner']}: {created['language']}, glossed into "
              f"{created['gloss_langs'][0]}{' (removed)' if created['deleted'] else ''}, "
              f"because it holds words and had no vocabulary")
    print(f"Meaning maps renamed for their vocabulary: {len(moves)}")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        for created in plan.created:
            connection.execute(metadata.tables["vocabularies"].insert().values(
                **created, revision=allocate_revision(connection, created["owner"])))
        for name in CHANGED:
            _rebuild(connection, name, plan.chosen)
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema and every row, so the script proves what it claims
    # rather than reporting that it finished.
    remaining = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    with engine.connect() as connection:
        unplaced = {name: connection.execute(text(
            f"SELECT COUNT(*) FROM {name} WHERE vocabulary NOT IN (SELECT id FROM vocabularies)")).scalar_one()
            for name in CHANGED}
        mismatched = {name: connection.execute(text(
            f"SELECT COUNT(*) FROM {name} JOIN vocabularies ON vocabularies.id = {name}.vocabulary "
            f"WHERE vocabularies.language != {name}.language")).scalar_one()
            for name in CHANGED}
    remaining += [f"{name}: {count} rows name no vocabulary" for name, count in unplaced.items() if count]
    remaining += [f"{name}: {count} rows are not in their vocabulary's language"
                  for name, count in mismatched.items() if count]
    if remaining or schemacheck.stamped(engine) != HEAD:
        print("The conversion did not land cleanly:\n  " + "\n  ".join(remaining), file=sys.stderr)
        return 1

    for source, target in moves:
        source.replace(target)
    print(f"\nDone. All {len(metadata.tables)} tables match, every word, loop and story is in its "
          f"vocabulary, {len(moves)} maps renamed, stamped {HEAD}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
