"""The one-off converter for the Anki switches: one new, empty table.

**Delete this file together with `scripts/throwaway/anki_settings.py`**, once that has run. It is
tested against a database built the way the owner's is — every table but the new one, holding a word,
stamped with the head from before — because the point of a converter is that what is held survives it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "anki_settings", ROOT / "scripts" / "throwaway" / "anki_settings.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
LEXEME = "lexeme000000001"
SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001"}


def _insert(connection, table: str, row: dict) -> None:
    connection.execute(text(
        f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join(':' + k for k in row)})"), row)


def _required(table: str, **values) -> dict:
    """A row of `table` with every required column given something plausible."""
    row = {}
    for column in metadata.tables[table].columns:
        if column.name in values:
            row[column.name] = values[column.name]
        elif column.nullable:
            continue
        elif "JSON" in str(column.type):
            row[column.name] = "[]"
        elif any(kind in str(column.type).upper() for kind in ("INT", "BOOL", "FLOAT")):
            row[column.name] = 0
        else:
            row[column.name] = "x"
    return row


def _engine(path: Path):
    return create_engine(f"sqlite+pysqlite:///{path}")


def _rows(path: Path, sql: str) -> list[dict]:
    engine = _engine(path)
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(sql)).mappings()]
    finally:
        engine.dispose()


@pytest.fixture
def old(tmp_path) -> Path:
    """The owner's database as it is: everything but the new table, and a word in it."""
    path = tmp_path / "acervo.db"
    engine = _engine(path)
    metadata.create_all(engine, tables=[table for name, table in metadata.tables.items()
                                        if name not in converter.CREATED])
    with engine.begin() as connection:
        _insert(connection, "users", _required("users", id=OWNER, email="learner@account.example.com"))
        _insert(connection, "lexemes", _required("lexemes", id=LEXEME, owner=OWNER, **SYNC))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def test_the_table_is_created_empty_and_what_is_held_survives(old: Path) -> None:
    before = _rows(old, "SELECT * FROM lexemes")
    assert converter.main(["--database", str(old)]) == 0
    assert _rows(old, "SELECT * FROM lexemes") == before
    assert _rows(old, "SELECT * FROM anki_settings") == []
    assert schemacheck.compare(_engine(old), metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(_engine(old)) == HEAD


def test_a_dry_run_writes_nothing(old: Path) -> None:
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert schemacheck.stamped(_engine(old)) == converter.FROM_REVISION
    assert _rows(old, "SELECT name FROM sqlite_master WHERE name = 'anki_settings'") == []


def test_a_database_already_converted_is_left_alone(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    assert converter.main(["--database", str(old)]) == 0


def test_any_other_stamp_is_refused(old: Path) -> None:
    with _engine(old).begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    assert converter.main(["--database", str(old)]) == 2


def test_a_table_it_was_not_written_for_is_refused(old: Path) -> None:
    engine = _engine(old)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE lexemes ADD COLUMN surprise INTEGER"))
    assert converter.main(["--database", str(old)]) == 2
    assert schemacheck.stamped(engine) == converter.FROM_REVISION


def test_the_new_table_already_there_is_refused(old: Path) -> None:
    with _engine(old).begin() as connection:
        metadata.tables["anki_settings"].create(connection)
    assert converter.main(["--database", str(old)]) == 2
