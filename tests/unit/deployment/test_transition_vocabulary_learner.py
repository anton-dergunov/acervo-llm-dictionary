"""The one-off converter that gave a vocabulary a level and a note, and made its flag follow its variety.

**Delete this file together with `scripts/throwaway/add_vocabulary_learner.py`**, once that has run.
It is tested against a database built the way the owner's is — the vocabularies table without the
columns this change adds, stamped with the head from before — because the point of a converter is
that the owner's vocabularies survive it, and a test that started from an empty database would prove
nothing about that.
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
from acervo.domain.projection import COLLECTION_BY_NAME, projected  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "add_vocabulary_learner", ROOT / "scripts" / "throwaway" / "add_vocabulary_learner.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001", "revision": 3}
SPAIN, BRITAIN, ARGENTINA, WHITE = "🇪🇸", "🇬🇧", "🇦🇷", "🏳️"
# language, region, flag stored before → flag after
VOCABULARIES = [
    ("es", "", SPAIN, ""),            # what the device would derive: follows the variety now
    ("en", "", BRITAIN, BRITAIN),     # not the US flag English derives: the owner's own, kept
    ("fr", "", WHITE, ""),            # the placeholder: follows, and gains France's flag
    ("pt", "BR", ARGENTINA, ARGENTINA),  # an odd choice, but a choice
    ("ru", "", "", ""),
]


@pytest.fixture
def old(tmp_path) -> Path:
    """Today's schema with the new columns taken back out, holding vocabularies, stamped with the
    previous head."""
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
        for order, (language, region, flag, _) in enumerate(VOCABULARIES):
            connection.execute(text(
                "INSERT INTO vocabularies (id, owner, language, definition_lang, gloss_langs, notes_lang,"
                " display_name, flag, region, vocab_order, deleted, created_at, edited_at, edited_by, revision)"
                " VALUES (:id, :owner, :language, :language, '[\"en\"]', 'en', 'Name', :flag, :region, :order,"
                " :deleted, :created_at, :edited_at, :edited_by, :revision)"),
                {"id": f"vocabulary0000{order}", "owner": OWNER, "language": language, "flag": flag,
                 "region": region, "order": order, **SYNC})
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def _rows(path: Path) -> list[dict]:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    with engine.connect() as connection:
        rows = [dict(row) for row in connection.execute(
            text("SELECT * FROM vocabularies ORDER BY vocab_order")).mappings()]
    engine.dispose()
    return rows


def test_the_columns_are_added_the_rows_survive_and_the_schema_is_the_code_s(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(engine) == HEAD
    engine.dispose()

    rows = _rows(old)
    assert [row["flag"] for row in rows] == [after for *_, after in VOCABULARIES]
    assert all(row["level"] == "" and row["learner_note"] == "" for row in rows)
    assert [row["region"] for row in rows] == [region for _, region, *_ in VOCABULARIES]
    spanish = projected(COLLECTION_BY_NAME["vocabularies"], rows[0])
    assert spanish["level"] is None and spanish["learnerNote"] is None and spanish["flag"] is None


def test_a_dry_run_writes_nothing_and_says_which_flags_follow(old: Path, capsys) -> None:
    before = old.read_bytes()
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert old.read_bytes() == before
    said = capsys.readouterr().out
    assert f"Vocabularies: {len(VOCABULARIES)} kept" in said and f"→ {HEAD}" in said
    assert f"es: flag {SPAIN} now follows the variety" in said
    assert f"en: flag {BRITAIN} kept as the owner's own" in said


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
        connection.execute(text("ALTER TABLE vocabularies ADD COLUMN level VARCHAR(2) NOT NULL DEFAULT ''"))
    engine.dispose()
    before = old.read_bytes()
    assert converter.main(["--database", str(old)]) == 2
    assert old.read_bytes() == before
    assert "vocabularies: already has level" in capsys.readouterr().err


def test_it_is_found_by_the_transition_mechanism() -> None:
    import transition

    assert [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
            if module.FROM_REVISION == converter.FROM_REVISION] == ["add_vocabulary_learner.py"]
