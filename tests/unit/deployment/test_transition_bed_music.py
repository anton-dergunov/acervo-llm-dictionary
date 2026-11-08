"""The one-off converter that gave every kept bed room for its own music.

**Delete this file together with `scripts/throwaway/add_bed_music.py`**, once that has run. It is
tested against a database built the way the owner's is — today's schema without the three `beds`
columns, holding a word, a loop and a kept bed, stamped with the head from before — because the point
of a converter is that the owner's music survives it, and a test that started from an empty database
would prove nothing about that.
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
    "add_bed_music", ROOT / "scripts" / "throwaway" / "add_bed_music.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001", "revision": 3}


@pytest.fixture
def old(tmp_path) -> Path:
    """Today's schema with the bed's music taken back out, holding a word, a loop and a kept bed,
    stamped with the previous head."""
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
        connection.execute(metadata.tables["loops"].insert().values(
            id="loop00000000001", owner=OWNER, language="es", style_id="organic", seed=7,
            audio_ref="loops/es/loop00000000001-0a1b2c3d.mp3", audio_mime="audio/mpeg",
            duration_seconds=180.0, **SYNC))
        connection.execute(text(
            "INSERT INTO beds (id, owner, style_id, seed, engine_version, bed_fingerprint,"
            " source_loop, deleted, created_at, edited_at, edited_by, revision)"
            " VALUES ('bed000000000001', :owner, 'organic', 7, '1.5.0', 'f7aa8c933f9a7e8a',"
            " 'loop00000000001', 0, 'now', 'now', 'device000000001', 5)"), {"owner": OWNER})
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


def test_the_revision_it_converts_from_is_todays_schema_without_the_columns():
    """What makes `FROM_REVISION` the right one: the digest of exactly the schema it expects."""
    assert converter.FROM_REVISION == f"bootstrap_{hashlib.sha256(shape_of(converter.before()).encode()).hexdigest()[:12]}"


def test_every_kept_bed_gains_empty_music_and_the_rest_survives(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(engine) == HEAD
    engine.dispose()

    assert [dict(row) for row in _rows(
        old, "SELECT id, style_id, seed, bed_fingerprint, audio_ref, audio_mime, duration_seconds"
             " FROM beds")] == [
        {"id": "bed000000000001", "style_id": "organic", "seed": 7,
         "bed_fingerprint": "f7aa8c933f9a7e8a", "audio_ref": "", "audio_mime": "",
         "duration_seconds": 0.0}]
    assert [row["audio_ref"] for row in _rows(old, "SELECT audio_ref FROM loops")] == [
        "loops/es/loop00000000001-0a1b2c3d.mp3"]
    assert [row["lemma"] for row in _rows(old, "SELECT lemma FROM lexemes")] == ["picar"]


def test_a_dry_run_writes_nothing_and_says_what_it_would_do(old: Path, capsys) -> None:
    before = old.read_bytes()
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert old.read_bytes() == before
    said = capsys.readouterr().out
    assert "Kept music: 1 kept" in said
    assert "Words:      1 kept" in said and f"→ {HEAD}" in said


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
        connection.execute(text("ALTER TABLE beds ADD COLUMN audio_ref VARCHAR(500) NOT NULL DEFAULT ''"))
    engine.dispose()
    before = old.read_bytes()
    assert converter.main(["--database", str(old)]) == 2
    assert old.read_bytes() == before
    assert "beds.audio_ref: already exists" in capsys.readouterr().err


def test_it_is_found_by_the_transition_mechanism() -> None:
    import transition

    assert [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
            if module.FROM_REVISION == converter.FROM_REVISION] == ["add_bed_music.py"]
