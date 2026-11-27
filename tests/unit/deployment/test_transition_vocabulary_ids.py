"""The one-off converter that gave each word, loop and story the id of its vocabulary.

**Delete this file together with `scripts/throwaway/add_vocabulary_ids.py`**, once that has run. It is
tested against a database built the way the owner's is: today's schema without the change, holding
words, a loop, a story and a drawn map, stamped with the head from before. A converter exists so the
owner's data survives it, and a test that started from an empty database would prove nothing about
that.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
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
    "add_vocabulary_ids", ROOT / "scripts" / "throwaway" / "add_vocabulary_ids.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

OWNER = "owner0000000001"
SPANISH = "vocabspanish001"
AT = "2026-09-01T00:00:00.000Z"


def sync(revision: int, deleted: bool = False) -> dict:
    return {"deleted": deleted, "created_at": AT, "edited_at": AT, "edited_by": "device000000001",
            "revision": revision}


def lexeme_row(identifier: str, language: str, revision: int, deleted: bool = False) -> dict:
    return {"id": identifier, "owner": OWNER, "headword": identifier, "lemma": identifier, "pos": "noun",
            "status": "active", "language": language, "reading": "chī" if language.startswith("zh") else "",
            **sync(revision, deleted)}


def vocabulary_row(identifier: str, language: str, revision: int, *, order: int = 0, deleted: bool = False) -> dict:
    return {"id": identifier, "owner": OWNER, "language": language, "definition_lang": language,
            "gloss_langs": ["ru"], "notes_lang": "ru", "vocab_order": order, **sync(revision, deleted)}


def build(path: Path, *, vocabularies: list[dict], lexemes: list[dict], sequence: int) -> Path:
    """Today's schema without the change, holding these rows and a loop and a story in Spanish,
    stamped with the previous head."""
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    previous = converter.before()
    previous.create_all(engine)
    with engine.begin() as connection:
        connection.execute(previous.tables["users"].insert().values(
            id=OWNER, email="learner@account.example.com", password_hash="x", token_key="k",
            created_at=AT, updated_at=AT))
        connection.execute(previous.tables["sync_state"].insert().values(
            id="syncstate000001", owner=OWNER, sequence=sequence))
        for row in vocabularies:
            connection.execute(previous.tables["vocabularies"].insert().values(**row))
        for row in lexemes:
            connection.execute(previous.tables["lexemes"].insert().values(**row))
        connection.execute(previous.tables["loops"].insert().values(
            id="loop00000000001", owner=OWNER, language="es", format="classic", **sync(sequence - 1)))
        connection.execute(previous.tables["stories"].insert().values(
            id="story0000000001", owner=OWNER, language="es", **sync(sequence)))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


@pytest.fixture
def old(tmp_path) -> Path:
    """Spanish with its words, French holding a word but no vocabulary any more, German holding only
    a word long deleted, and a drawn map of the Spanish."""
    maps = tmp_path / "maps" / "artifacts" / OWNER
    maps.mkdir(parents=True)
    (maps / "es.json").write_text(json.dumps({"language": "es", "names": "ready"}), encoding="utf-8")
    return build(
        tmp_path / "acervo.db",
        vocabularies=[vocabulary_row(SPANISH, "es", 1), vocabulary_row("vocabfrench0001", "fr", 2, deleted=True)],
        lexemes=[lexeme_row("lexemepicar0001", "es", 3), lexeme_row("lexemegone00001", "es", 4, deleted=True),
                 lexeme_row("lexemepiquer001", "fr", 5), lexeme_row("lexemelang00001", "de", 6, deleted=True)],
        sequence=8,
    )


def rows(path: Path, query: str) -> list[dict]:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    with engine.connect() as connection:
        found = [dict(row) for row in connection.execute(text(query)).mappings()]
    engine.dispose()
    return found


def test_the_revision_it_converts_from_is_todays_schema_without_the_change():
    """What makes `FROM_REVISION` the right one: the digest of exactly the schema it expects."""
    assert converter.FROM_REVISION == f"bootstrap_{hashlib.sha256(shape_of(converter.before()).encode()).hexdigest()[:12]}"


def test_every_word_loop_and_story_is_given_its_owners_vocabulary_of_its_language(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    assert schemacheck.stamped(engine) == HEAD
    engine.dispose()

    words = {row["id"]: row for row in rows(old, "SELECT id, vocabulary, revision FROM lexemes")}
    assert words["lexemepicar0001"]["vocabulary"] == SPANISH
    assert words["lexemegone00001"]["vocabulary"] == SPANISH, "a deleted word keeps its place too"
    assert [row["vocabulary"] for row in rows(old, "SELECT vocabulary FROM loops")] == [SPANISH]
    assert [row["vocabulary"] for row in rows(old, "SELECT vocabulary FROM stories")] == [SPANISH]
    assert [row["revision"] for row in words.values()] == [3, 4, 5, 6], "every device pulls again anyway"


def test_a_language_holding_words_without_a_vocabulary_is_given_one_every_device_receives(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    made = {row["language"]: row for row in rows(
        old, "SELECT * FROM vocabularies WHERE edited_by = 'acervoconverter'")}
    # A live French word gets a live French vocabulary, glossed as the owner's others are; a German
    # word long deleted gets a vocabulary that is deleted too, so nothing new appears on a device.
    assert (made["fr"]["deleted"], made["de"]["deleted"]) == (0, 1)
    assert json.loads(made["fr"]["gloss_langs"]) == ["ru"] and made["fr"]["definition_lang"] == "fr"
    assert sorted(row["revision"] for row in made.values()) == [9, 10], "after the owner's last revision"
    assert [row["sequence"] for row in rows(old, "SELECT sequence FROM sync_state")] == [10]
    french = rows(old, "SELECT vocabulary FROM lexemes WHERE id = 'lexemepiquer001'")[0]["vocabulary"]
    assert french == made["fr"]["id"]


def test_a_drawn_map_is_renamed_for_its_vocabulary_and_keeps_its_names(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0
    maps = old.parent / "maps" / "artifacts" / OWNER
    assert sorted(path.name for path in maps.iterdir()) == [f"{SPANISH}.json"]
    assert json.loads((maps / f"{SPANISH}.json").read_text(encoding="utf-8"))["names"] == "ready"


def test_a_dry_run_says_what_it_would_do_and_writes_nothing(old: Path, capsys) -> None:
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    said = capsys.readouterr().out
    assert "Lexemes: 2 live and 2 removed" in said
    assert "Vocabulary created for owner owner0000000001: fr, glossed into ru" in said
    assert "Meaning maps renamed for their vocabulary: 1" in said
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.stamped(engine) == converter.FROM_REVISION
    engine.dispose()
    assert (old.parent / "maps" / "artifacts" / OWNER / "es.json").is_file()


def test_two_vocabularies_of_one_language_are_refused_by_name_and_nothing_is_written(tmp_path, capsys) -> None:
    path = build(
        tmp_path / "acervo.db",
        vocabularies=[vocabulary_row(SPANISH, "es", 1), vocabulary_row("vocabspanish002", "es", 2, order=1)],
        lexemes=[lexeme_row("lexemepicar0001", "es", 3)],
        sequence=5,
    )
    assert converter.main(["--database", str(path)]) == 2
    said = capsys.readouterr().err
    assert f"owner {OWNER}, es: vocabularies {SPANISH}, vocabspanish002" in said
    assert "Nothing was written." in said
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    assert schemacheck.stamped(engine) == converter.FROM_REVISION
    engine.dispose()


def test_a_database_at_any_other_revision_is_refused(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    engine.dispose()
    assert converter.main(["--database", str(old)]) == 2
    assert "not bootstrap_43bc6845036e" in capsys.readouterr().err


def test_the_transition_finds_this_converter_by_the_revision_a_database_carries(old: Path) -> None:
    import transition

    found = [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
             if module.FROM_REVISION == converter.FROM_REVISION]
    assert found == ["add_vocabulary_ids.py"]
