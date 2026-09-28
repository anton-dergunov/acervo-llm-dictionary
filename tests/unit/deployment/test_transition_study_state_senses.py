"""The one-off converter that gave a study state the sense its cards test.

**Delete this file together with `scripts/throwaway/study_state_senses.py`**, once that has run. It is
tested against a database built the way the owner's was — `study_states` exactly as the previous
schema created it, stamped with the head from before — because the point of a converter is that what
is held survives it, and a test that started from an empty database would prove nothing about that.
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
    "study_state_senses", ROOT / "scripts" / "throwaway" / "study_state_senses.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
LEXEME = "lexeme000000001"

# The table as the previous schema created it, captured from it verbatim.
BEFORE = """
CREATE TABLE study_states (
	id VARCHAR(15) NOT NULL, owner VARCHAR(15) NOT NULL, lexeme VARCHAR(15) NOT NULL,
	system VARCHAR(80) NOT NULL, note_id INTEGER NOT NULL, card_ids JSON NOT NULL,
	reps INTEGER NOT NULL, lapses INTEGER NOT NULL, stability FLOAT NOT NULL,
	difficulty FLOAT NOT NULL, retrievability FLOAT NOT NULL, last_review VARCHAR(24) NOT NULL,
	synced_at VARCHAR(24) NOT NULL, deleted BOOLEAN NOT NULL, created_at VARCHAR(24) NOT NULL,
	edited_at VARCHAR(24) NOT NULL, edited_by VARCHAR(32) NOT NULL, revision INTEGER NOT NULL,
	PRIMARY KEY (id), FOREIGN KEY(owner) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(lexeme) REFERENCES lexemes (id) ON DELETE CASCADE
);
CREATE INDEX idx_study_states_owner_lexeme_system ON study_states (owner, lexeme, system);
CREATE INDEX idx_study_states_owner_revision ON study_states (owner, revision);
"""

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


def _study(identifier: str, **values) -> dict:
    return {"id": identifier, "owner": OWNER, "lexeme": LEXEME, "system": "anki", "note_id": 17,
            "card_ids": "[18]", "reps": 21, "lapses": 4, "stability": 18.3, "difficulty": 8.4,
            "retrievability": 0.71, "last_review": "2026-08-22T10:00:00.000Z",
            "synced_at": "2026-09-01T00:00:00.000Z", **SYNC, "revision": 5, **values}


@pytest.fixture
def old(tmp_path) -> Path:
    """The owner's database as it was: one word with a live report and a tombstoned one."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    untouched = [table for name, table in metadata.tables.items() if name != converter.CHANGED]
    metadata.create_all(engine, tables=untouched)
    with engine.begin() as connection:
        for statement in BEFORE.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        _insert(connection, "users", _required("users", id=OWNER, email="learner@account.example.com"))
        _insert(connection, "lexemes", _required("lexemes", id=LEXEME, owner=OWNER, **SYNC))
        _insert(connection, "study_states", _study("studylive000001"))
        _insert(connection, "study_states", _study("studygone000001", deleted=True, revision=6))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def _rows(path: Path, sql: str) -> list[dict]:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(sql)).mappings()]
    finally:
        engine.dispose()


def _engine(path: Path):
    return create_engine(f"sqlite+pysqlite:///{path}")


def test_every_study_state_survives_reporting_on_its_word(old: Path) -> None:
    before = _rows(old, "SELECT * FROM study_states ORDER BY id")
    assert converter.main(["--database", str(old)]) == 0

    after = _rows(old, "SELECT * FROM study_states ORDER BY id")
    assert [row.pop("sense") for row in after] == [None, None]
    assert after == before
    assert schemacheck.compare(_engine(old), metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(_engine(old)) == HEAD


def test_a_dry_run_writes_nothing(old: Path, capsys) -> None:
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert "2 kept" in capsys.readouterr().out
    assert schemacheck.stamped(_engine(old)) == converter.FROM_REVISION
    assert "sense" not in _rows(old, "SELECT * FROM study_states")[0]


def test_a_database_already_converted_is_left_alone(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    assert converter.main(["--database", str(old)]) == 0
    assert len(_rows(old, "SELECT * FROM study_states")) == 2


def test_any_other_stamp_is_refused(old: Path) -> None:
    engine = _engine(old)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    assert converter.main(["--database", str(old)]) == 2


def test_a_table_it_was_not_written_for_is_refused(old: Path) -> None:
    engine = _engine(old)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE study_states ADD COLUMN surprise INTEGER"))
    assert converter.main(["--database", str(old)]) == 2
    assert schemacheck.stamped(engine) == converter.FROM_REVISION
