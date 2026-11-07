"""The one-off converter that gave every story its `parts`.

**Delete this file together with `scripts/throwaway/add_story_parts.py`**, once that has run. It is
tested against a database built the way the owner's is — today's schema without `stories.parts`,
holding a word and a story, stamped with the head from before — because the point of a converter is
that the owner's stories survive it, and a test that started from an empty database would prove
nothing about that.
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
    "add_story_parts", ROOT / "scripts" / "throwaway" / "add_story_parts.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001", "revision": 3}


@pytest.fixture
def old(tmp_path) -> Path:
    """Today's schema with `stories.parts` taken back out, holding a word and a story, stamped with
    the previous head."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    converter.before().create_all(engine)
    with engine.begin() as connection:
        connection.execute(metadata.tables["users"].insert().values(
            id=OWNER, email="learner@account.example.com", password_hash="x", token_key="k",
            created_at="now", updated_at="now"))
        connection.execute(metadata.tables["lexemes"].insert().values(
            id="lexeme000000001", owner=OWNER, headword="picar", lemma="picar", pos="verb",
            status="active", language="es", **SYNC))
        connection.execute(text(
            "INSERT INTO stories (id, owner, language, type_id, style_id, title, title_translation, emoji,"
            " model_id, story_order, deleted, created_at, edited_at, edited_by, revision, guidance)"
            " VALUES ('story0000000001', :owner, 'es', 'mystery', 'film-noir', 'La balsa', '', '',"
            " '', 0, 0, 'now', 'now', 'device000000001', 4, '')"), {"owner": OWNER})
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


def test_the_revision_it_converts_from_is_todays_schema_without_the_column():
    """What makes `FROM_REVISION` the right one: the digest of exactly the schema it expects."""
    assert converter.FROM_REVISION == f"bootstrap_{hashlib.sha256(shape_of(converter.before()).encode()).hexdigest()[:12]}"


def test_every_story_gains_four_parts_and_the_words_and_stories_survive(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(engine) == HEAD
    engine.dispose()

    assert [dict(row) for row in _rows(old, "SELECT id, title, parts FROM stories")] == [
        {"id": "story0000000001", "title": "La balsa", "parts": 4}]
    assert [row["lemma"] for row in _rows(old, "SELECT lemma FROM lexemes")] == ["picar"]


def test_a_dry_run_writes_nothing_and_says_what_it_would_do(old: Path, capsys) -> None:
    before = old.read_bytes()
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert old.read_bytes() == before
    said = capsys.readouterr().out
    assert "Stories:   1 kept, each with parts = 4" in said
    assert "Words:     1 kept" in said and f"→ {HEAD}" in said


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
        connection.execute(text("ALTER TABLE stories ADD COLUMN parts INTEGER NOT NULL DEFAULT 4"))
    engine.dispose()
    before = old.read_bytes()
    assert converter.main(["--database", str(old)]) == 2
    assert old.read_bytes() == before
    assert "stories.parts: already exists" in capsys.readouterr().err


def test_it_is_found_by_the_transition_mechanism() -> None:
    import transition

    assert [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
            if module.FROM_REVISION == converter.FROM_REVISION] == ["add_story_parts.py"]
