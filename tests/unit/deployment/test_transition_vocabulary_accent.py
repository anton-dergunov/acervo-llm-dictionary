"""The one-off converter that gave a vocabulary an accent and a language its first voice.

**Delete this file together with `scripts/throwaway/add_vocabulary_accent.py`**, once that has run.
It is tested against a database built the way the owner's is — the two changed tables without the
columns this change adds, stamped with the head from before — because the point of a converter is
that the owner's words and chosen voices survive it, and a test that started from an empty database
would prove nothing about that.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402
from acervo.domain.projection import COLLECTION_BY_NAME, projected  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "add_vocabulary_accent", ROOT / "scripts" / "throwaway" / "add_vocabulary_accent.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001", "revision": 3}
VOICES = {"google-tts": {"wavenet": {"es": "es-ES-Wavenet-E"}}}


@pytest.fixture
def old(tmp_path) -> Path:
    """Today's schema with the three new columns taken back out, holding a vocabulary and the
    owner's chosen voices, stamped with the previous head."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    metadata.create_all(engine)
    with engine.begin() as connection:
        for table, added in converter.ADDED.items():
            for column, _ in added:
                connection.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        connection.execute(metadata.tables["users"].insert().values(
            id=OWNER, email="learner@account.example.com", password_hash="x", token_key="k",
            created_at="now", updated_at="now"))
        connection.execute(text(
            "INSERT INTO vocabularies (id, owner, language, definition_lang, gloss_langs, notes_lang,"
            " display_name, flag, vocab_order, deleted, created_at, edited_at, edited_by, revision)"
            " VALUES ('vocabulary00001', :owner, 'es', 'es', '[\"en\"]', 'en', 'Spanish', '', 0,"
            " :deleted, :created_at, :edited_at, :edited_by, :revision)"), {"owner": OWNER, **SYNC})
        connection.execute(text(
            "INSERT INTO pronunciation_settings (id, owner, pregenerate, delivery, voices, guide_voices,"
            " edited_at) VALUES ('settings0000001', :owner, '{}', '{}', :voices, '{}', 'now')"),
            {"owner": OWNER, "voices": json.dumps(VOICES)})
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def _one(path: Path, sql: str) -> dict:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    with engine.connect() as connection:
        row = dict(connection.execute(text(sql)).mappings().one())
    engine.dispose()
    return row


def test_the_columns_are_added_the_rows_survive_and_the_schema_is_the_code_s(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(engine) == HEAD
    engine.dispose()

    vocabulary = _one(old, "SELECT * FROM vocabularies")
    assert vocabulary["region"] == "" and vocabulary["display_name"] == "Spanish"
    assert projected(COLLECTION_BY_NAME["vocabularies"], vocabulary)["region"] is None
    settings = _one(old, "SELECT * FROM pronunciation_settings")
    assert json.loads(settings["voices"]) == VOICES, "the voices already chosen are kept"
    assert json.loads(settings["first_voices"]) == {} and json.loads(settings["guide_first_voices"]) == {}


def test_a_dry_run_writes_nothing(old: Path, capsys) -> None:
    before = old.read_bytes()
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert old.read_bytes() == before
    said = capsys.readouterr().out
    assert "Vocabularies: 1 kept" in said and f"→ {HEAD}" in said


def test_another_revision_is_refused_naming_both(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    engine.dispose()
    assert converter.main(["--database", str(old)]) == 2
    said = capsys.readouterr().err
    assert "bootstrap_000000000000" in said and converter.FROM_REVISION in said


def test_a_database_that_already_has_a_column_is_refused_before_anything_is_written(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE vocabularies ADD COLUMN region VARCHAR(8) NOT NULL DEFAULT ''"))
    engine.dispose()
    before = old.read_bytes()
    assert converter.main(["--database", str(old)]) == 2
    assert old.read_bytes() == before
    assert "vocabularies: already has region" in capsys.readouterr().err


def test_it_is_found_by_the_transition_mechanism() -> None:
    import transition

    assert [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
            if module.FROM_REVISION == converter.FROM_REVISION] == ["add_vocabulary_accent.py"]
