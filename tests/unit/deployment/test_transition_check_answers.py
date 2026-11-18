"""The one-off converter that gave each owner's model chains "Check what models write".

**Delete this file together with `scripts/throwaway/add_check_answers.py`**, once that has run. It is
tested against a database built the way the owner's is: today's schema without the column, holding
a word and a saved chain, stamped with the head from before. A converter exists so the owner's data
survives it, and a test that started from an empty database would prove nothing about that.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD, shape_of  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "add_check_answers", ROOT / "scripts" / "throwaway" / "add_check_answers.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001", "revision": 3}
CHAINS = {"text": [{"provider": "gemini", "model": "gemini-flash"}]}


@pytest.fixture
def old(tmp_path) -> Path:
    """Today's schema without the switch, holding a word and a saved chain, stamped with the previous head."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    previous = converter.before()
    previous.create_all(engine)
    with engine.begin() as connection:
        connection.execute(previous.tables["users"].insert().values(
            id=OWNER, email="learner@account.example.com", password_hash="x", token_key="k",
            created_at="now", updated_at="now"))
        connection.execute(previous.tables["lexemes"].insert().values(
            id="lexeme000000001", owner=OWNER, headword="picar", lemma="picar", pos="verb",
            status="active", language="es", **SYNC))
        connection.execute(previous.tables["model_selection"].insert().values(
            id="selection000001", owner=OWNER, chains=CHAINS, edited_at="2026-09-01T00:00:00.000Z"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def _rows(path: Path, query: str):
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    with engine.connect() as connection:
        found = connection.execute(text(query)).mappings().all()
    engine.dispose()
    return found


def test_the_revision_it_converts_from_is_todays_schema_without_the_change():
    """What makes `FROM_REVISION` the right one: the digest of exactly the schema it expects."""
    assert converter.FROM_REVISION == f"bootstrap_{hashlib.sha256(shape_of(converter.before()).encode()).hexdigest()[:12]}"


def test_every_saved_chain_keeps_its_order_and_checks_answers(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(engine) == HEAD
    engine.dispose()

    rows = [dict(row) for row in _rows(old, "SELECT owner, chains, check_answers FROM model_selection")]
    assert rows == [{"owner": OWNER, "chains": '{"text": [{"provider": "gemini", "model": "gemini-flash"}]}',
                     "check_answers": 1}]
    assert [row["lemma"] for row in _rows(old, "SELECT lemma FROM lexemes")] == ["picar"]


def test_a_dry_run_writes_nothing_and_says_what_it_would_do(old: Path, capsys) -> None:
    before = old.read_bytes()
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert old.read_bytes() == before
    said = capsys.readouterr().out
    assert "Model chains: 1 owner(s)" in said and "Words:        1 kept" in said
    assert f"→ {HEAD}" in said and "nothing was written" in said


def test_another_revision_is_refused_naming_both(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    engine.dispose()
    assert converter.main(["--database", str(old)]) == 2
    said = capsys.readouterr().err
    assert "bootstrap_000000000000" in said and converter.FROM_REVISION in said


def test_a_database_that_already_has_the_column_is_refused_before_anything_is_written(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE model_selection ADD COLUMN check_answers BOOLEAN NOT NULL DEFAULT 1"))
    engine.dispose()
    before = old.read_bytes()
    assert converter.main(["--database", str(old)]) == 2
    assert old.read_bytes() == before
    assert "model_selection.check_answers: already exists" in capsys.readouterr().err


def test_it_is_found_by_the_transition_mechanism() -> None:
    import transition

    assert [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
            if module.FROM_REVISION == converter.FROM_REVISION] == ["add_check_answers.py"]
