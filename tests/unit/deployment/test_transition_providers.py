"""The one-off converter that added the `providers` table and forgot the orders naming the catalogue.

**Delete this file together with `scripts/throwaway/add_providers.py`**, once that has run. It is
tested against a database built the way the owner's is — today's schema without `providers`, holding
words, orders and voice choices, stamped with the head from before — because the point of a
converter is that the owner's words survive it, and a test that started from an empty database would
prove nothing about that.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD, shape_of  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "add_providers", ROOT / "scripts" / "throwaway" / "add_providers.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001", "revision": 3}
ORDERS = {"text": [{"provider": "gemini-free", "model": "gemini/gemini-3.5-flash-lite"}]}
VOICES = {"google-tts": {"wavenet": {"es": "es-ES-Wavenet-F"}}}
DELIVERY = {"words": "plain", "examples": "plain"}


@pytest.fixture
def old(tmp_path) -> Path:
    """Today's schema with `providers` taken back out, holding a word, an order and a voice choice,
    stamped with the previous head."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE providers"))
        connection.execute(metadata.tables["users"].insert().values(
            id=OWNER, email="learner@account.example.com", password_hash="x", token_key="k",
            created_at="now", updated_at="now"))
        connection.execute(metadata.tables["model_selection"].insert().values(
            id="selection000001", owner=OWNER, chains=ORDERS, edited_at="now"))
        connection.execute(metadata.tables["pronunciation_settings"].insert().values(
            id="pronounce000001", owner=OWNER, pregenerate={"headword": True}, delivery=DELIVERY,
            voices=VOICES, guide_voices=VOICES, first_voices={"plain": {"es": ["google-tts", "wavenet"]}},
            guide_first_voices={}, edited_at="now"))
        connection.execute(metadata.tables["lexemes"].insert().values(
            id="lexeme000000001", owner=OWNER, headword="picar", lemma="picar", pos="verb", status="active", language="es", **SYNC))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def _one(path: Path, query: str):
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    with engine.connect() as connection:
        found = connection.execute(text(query)).mappings().all()
    engine.dispose()
    return found


def test_the_revision_it_converts_from_is_todays_schema_without_providers():
    """What makes `FROM_REVISION` the right one: the digest of exactly the schema it expects."""
    before = MetaData()
    for name, table in metadata.tables.items():
        if name != "providers":
            table.to_metadata(before)
    assert converter.FROM_REVISION == f"bootstrap_{hashlib.sha256(shape_of(before).encode()).hexdigest()[:12]}"


def test_the_table_is_added_the_words_survive_and_the_orders_are_forgotten(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(engine) == HEAD
    engine.dispose()

    assert _one(old, "SELECT COUNT(*) AS n FROM providers")[0]["n"] == 0
    assert _one(old, "SELECT COUNT(*) AS n FROM model_selection")[0]["n"] == 0
    assert [row["lemma"] for row in _one(old, "SELECT lemma FROM lexemes")] == ["picar"]
    settings = _one(old, "SELECT * FROM pronunciation_settings")[0]
    for column in converter.VOICE_COLUMNS:
        assert json.loads(settings[column]) == {}
    # What is not about a provider is kept.
    assert json.loads(settings["delivery"]) == DELIVERY
    assert json.loads(settings["pregenerate"]) == {"headword": True}


def test_a_dry_run_writes_nothing_and_says_what_it_would_forget(old: Path, capsys) -> None:
    before = old.read_bytes()
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert old.read_bytes() == before
    said = capsys.readouterr().out
    assert "Orders:    1 account(s)" in said and "Voices:    1 account(s)" in said
    assert "Words:     1 kept" in said and f"→ {HEAD}" in said


def test_another_revision_is_refused_naming_both(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    engine.dispose()
    assert converter.main(["--database", str(old)]) == 2
    said = capsys.readouterr().err
    assert "bootstrap_000000000000" in said and converter.FROM_REVISION in said


def test_a_database_that_already_has_the_table_is_refused_before_anything_is_written(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        metadata.tables["providers"].create(connection)
    engine.dispose()
    before = old.read_bytes()
    assert converter.main(["--database", str(old)]) == 2
    assert old.read_bytes() == before
    assert "providers: already exists" in capsys.readouterr().err


def test_it_is_found_by_the_transition_mechanism() -> None:
    import transition

    assert [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
            if module.FROM_REVISION == converter.FROM_REVISION] == ["add_providers.py"]
