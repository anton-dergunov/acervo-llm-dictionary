"""The one-off converter that made loops programme formats and gave every rendered loop its lines.

**Delete this file together with `scripts/throwaway/add_loop_formats.py`**, once that has run. It is
tested against a database built the way the owner's was — the three changed tables exactly as the
previous schema created them, stamped with the head from before — because the point of a converter
is that words, pictures, recordings and loops survive it, and a test that started from an empty
database would prove nothing about that.
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
from acervo.domain.validation import validate  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "add_loop_formats", ROOT / "scripts" / "throwaway" / "add_loop_formats.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

RECORDED = ROOT / "tests" / "unit" / "loops" / "fixtures" / "completed.json"
OWNER = "owner0000000001"

# The three tables as the previous schema created them, captured from it verbatim.
BEFORE = """
CREATE TABLE loops (
	id VARCHAR(15) NOT NULL, owner VARCHAR(15) NOT NULL, language VARCHAR(35) NOT NULL,
	style_id VARCHAR(120) NOT NULL, seed INTEGER NOT NULL, engine_version VARCHAR(64) NOT NULL,
	bed_fingerprint VARCHAR(64) NOT NULL, pattern VARCHAR(64) NOT NULL,
	audio_ref VARCHAR(500) NOT NULL, audio_mime VARCHAR(80) NOT NULL,
	duration_seconds FLOAT NOT NULL, loop_order INTEGER NOT NULL, deleted BOOLEAN NOT NULL,
	created_at VARCHAR(24) NOT NULL, edited_at VARCHAR(24) NOT NULL,
	edited_by VARCHAR(32) NOT NULL, revision INTEGER NOT NULL,
	PRIMARY KEY (id), FOREIGN KEY(owner) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX idx_loops_owner_language_order ON loops (owner, language, loop_order);
CREATE INDEX idx_loops_owner_revision ON loops (owner, revision);
CREATE TABLE loop_items (
	id VARCHAR(15) NOT NULL, owner VARCHAR(15) NOT NULL, loop VARCHAR(15) NOT NULL,
	lexeme VARCHAR(15) NOT NULL, item_order INTEGER NOT NULL, source_text VARCHAR(240) NOT NULL,
	target_text VARCHAR(240) NOT NULL, emotion VARCHAR(300) NOT NULL,
	start_seconds FLOAT NOT NULL, source_reveal_seconds FLOAT NOT NULL,
	target_reveal_seconds FLOAT NOT NULL, end_seconds FLOAT NOT NULL, repeats INTEGER NOT NULL,
	repeat_seconds FLOAT NOT NULL, deleted BOOLEAN NOT NULL, created_at VARCHAR(24) NOT NULL,
	edited_at VARCHAR(24) NOT NULL, edited_by VARCHAR(32) NOT NULL, revision INTEGER NOT NULL,
	PRIMARY KEY (id), FOREIGN KEY(owner) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(loop) REFERENCES loops (id) ON DELETE CASCADE,
	FOREIGN KEY(lexeme) REFERENCES lexemes (id) ON DELETE CASCADE
);
CREATE INDEX idx_loop_items_owner_lexeme ON loop_items (owner, lexeme);
CREATE INDEX idx_loop_items_owner_loop_order ON loop_items (owner, loop, item_order);
CREATE INDEX idx_loop_items_owner_revision ON loop_items (owner, revision);
CREATE TABLE pronunciation_settings (
	id VARCHAR(15) NOT NULL, owner VARCHAR(15) NOT NULL, pregenerate JSON NOT NULL,
	delivery JSON NOT NULL, voices JSON NOT NULL, edited_at VARCHAR(24) NOT NULL,
	PRIMARY KEY (id), FOREIGN KEY(owner) REFERENCES users (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX idx_pronunciation_settings_owner ON pronunciation_settings (owner);
"""

SYNC = {"deleted": False, "created_at": "2026-09-01T00:00:00.000Z",
        "edited_at": "2026-09-01T00:00:00.000Z", "edited_by": "device000000001"}


def _insert(connection, table: str, row: dict) -> None:
    connection.execute(text(
        f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join(':' + k for k in row)})"), row)


def _loop(identifier: str, pattern: str, *, audio: str = "", deleted: bool = False,
          revision: int = 1) -> dict:
    return {"id": identifier, "owner": OWNER, "language": "es", "style_id": "lofi", "seed": 1,
            "engine_version": "0.6.1", "bed_fingerprint": "", "pattern": pattern,
            "audio_ref": audio, "audio_mime": "audio/mpeg" if audio else "",
            "duration_seconds": 60.0 if audio else 0.0, "loop_order": 0,
            **SYNC, "deleted": deleted, "revision": revision}


def _item(identifier: str, loop: str, order: int, recorded: dict, *, repeats: int,
          repeat_seconds: float) -> dict:
    return {"id": identifier, "owner": OWNER, "loop": loop, "lexeme": f"lexeme00000000{order}",
            "item_order": order, "source_text": recorded["source"],
            "target_text": recorded["target"], "emotion": recorded["direction"],
            "start_seconds": recorded["start"], "source_reveal_seconds": recorded["source_reveal"],
            "target_reveal_seconds": recorded["target_reveal"], "end_seconds": recorded["end"],
            "repeats": repeats, "repeat_seconds": repeat_seconds, **SYNC, "revision": 2}


def recorded() -> dict:
    return json.loads(RECORDED.read_text(encoding="utf-8"))["result"]


def spacing(result: dict) -> float:
    """What 0.6.1 stored as `repeat_seconds`: one line to the next, after the first translation."""
    return result["cues"][2]["start"] - result["cues"][1]["start"]


@pytest.fixture
def old(tmp_path) -> Path:
    """The owner's database as it was: a classic loop rendered by LexiBeat, an alternating one whose
    render reported no cadence, one never rendered, one deleted, and a guide-less voice setting."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    untouched = [table for name, table in metadata.tables.items()
                 if name not in (*converter.CHANGED, *converter.CREATED)]
    metadata.create_all(engine, tables=untouched)
    result = recorded()
    with engine.begin() as connection:
        for statement in BEFORE.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        _insert(connection, "users", _required("users", id=OWNER,
                                               email="learner@account.example.com"))
        _insert(connection, "sync_state", {"id": "sequence0000001", "owner": OWNER, "sequence": 40})
        _insert(connection, "vocabularies", _vocabulary())
        _insert(connection, "loops", _loop("loopclassic0001", "retrieval", audio="loops/a.mp3"))
        _insert(connection, "loops", _loop("loopalternate01", "alternating", audio="loops/b.mp3"))
        _insert(connection, "loops", _loop("loopunrendered1", "retrieval"))
        _insert(connection, "loops", _loop("loopdeleted0001", "retrieval", audio="loops/c.mp3",
                                           deleted=True))
        for order, row in enumerate(result["items"]):
            _insert(connection, "loop_items", _item(f"itemclassic000{order}", "loopclassic0001",
                                                    order, row, repeats=3,
                                                    repeat_seconds=spacing(result)))
        _insert(connection, "loop_items", _item("itemalternate00", "loopalternate01", 0,
                                                result["items"][0], repeats=0, repeat_seconds=0.0))
        _insert(connection, "loop_items", _item("itemdeleted0000", "loopdeleted0001", 0,
                                                result["items"][0], repeats=3, repeat_seconds=3.0))
        _insert(connection, "pronunciation_settings", {
            "id": "settings0000001", "owner": OWNER, "pregenerate": "{}", "delivery": "{}",
            "voices": '{"google": {"m": {"es": "Kore"}}}', "edited_at": SYNC["edited_at"]})
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


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


def _vocabulary() -> dict:
    return _required("vocabularies", id="vocabulary00001", owner=OWNER, language="es",
                     definition_lang="es", gloss_langs='["en"]', notes_lang="en", **SYNC,
                     revision=3)


def _rows(path: Path, sql: str, **params) -> list[dict]:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(sql), params).mappings()]
    finally:
        engine.dispose()


def _stamp(path: Path) -> str | None:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    try:
        return schemacheck.stamped(engine)
    finally:
        engine.dispose()


def test_a_converted_drill_has_the_lines_lexibeat_reports_for_it(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0

    heard = recorded()["cues"]
    cues = _rows(old, "SELECT * FROM loop_cues WHERE loop = 'loopclassic0001' ORDER BY cue_order")
    fields = ("kind", "section", "side", "role", "language", "text", "take")
    assert [tuple(row[f] for f in fields) for row in cues] == \
        [tuple(cue[f] for f in fields) for cue in heard]
    assert [row["cue_group"] for row in cues] == [cue["group"] for cue in heard]
    assert [row["loop_item"] for row in cues] == [f"itemclassic000{cue['item']}" for cue in heard]
    assert [row["start_seconds"] for row in cues] == pytest.approx([cue["start"] for cue in heard])
    # A line runs until the next begins, which is how the player read the old times.
    assert all(row["end_seconds"] >= row["start_seconds"] for row in cues)


def test_every_record_it_writes_is_one_the_server_would_accept(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0

    def lookup(table: str, identifier: str):
        found = _rows(old, f"SELECT * FROM {table} WHERE id = :id", id=identifier)
        return found[0] if found else None

    # The loops it altered and the lines it wrote; items are copied, not written.
    for table in ("loops", "loop_cues"):
        for row in _rows(old, f"SELECT * FROM {table} WHERE deleted = 0"):
            if table == "loops":
                row["switches"] = json.loads(row["switches"])
            validate(table, row, lookup)


def test_formats_are_named_and_revisions_come_from_the_owner_s_counter(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0

    loops = {row["id"]: row for row in _rows(old, "SELECT * FROM loops")}
    assert {key: row["format"] for key, row in loops.items()} == {
        "loopclassic0001": "classic", "loopalternate01": "alternating",
        "loopunrendered1": "classic", "loopdeleted0001": "classic"}
    assert all((row["switches"], row["fallback_from"]) == ("{}", "") for row in loops.values())

    revisions = [row["revision"] for row in _rows(old, "SELECT revision FROM loop_cues")]
    assert sorted(revisions) == list(range(41, 41 + len(revisions)))
    assert _rows(old, "SELECT sequence FROM sync_state")[0]["sequence"] == 40 + len(revisions)


def test_only_a_rendered_live_loop_gets_lines(old: Path) -> None:
    assert converter.main(["--database", str(old)]) == 0

    counts = {row["loop"]: row["n"] for row in _rows(
        old, "SELECT loop, COUNT(*) AS n FROM loop_cues GROUP BY loop")}
    # The alternating loop's render reported no cadence: its first pair, and nothing invented.
    assert counts == {"loopclassic0001": len(recorded()["cues"]), "loopalternate01": 2}


def test_items_and_settings_survive_and_the_schema_is_the_code_s(old: Path) -> None:
    before = _rows(old, "SELECT id, source_text, start_seconds, end_seconds FROM loop_items "
                        "ORDER BY id")
    assert converter.main(["--database", str(old)]) == 0

    assert _rows(old, "SELECT id, source_text, start_seconds, end_seconds FROM loop_items "
                      "ORDER BY id") == before
    settings = _rows(old, "SELECT voices, guide_voices FROM pronunciation_settings")[0]
    assert (json.loads(settings["voices"]), settings["guide_voices"]) == \
        ({"google": {"m": {"es": "Kore"}}}, "{}")
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    try:
        assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    finally:
        engine.dispose()
    assert _stamp(old) == HEAD
    assert _rows(old, "SELECT COUNT(*) AS n FROM loop_scripts")[0]["n"] == 0


def test_a_dry_run_writes_nothing(old: Path, capsys) -> None:
    before = old.read_bytes()
    assert converter.main(["--database", str(old), "--dry-run"]) == 0
    assert old.read_bytes() == before
    said = capsys.readouterr().out
    assert "Rendered loops: 2, given 14 lines between them" in said
    assert "3 retrieval → format classic" in said


def test_another_revision_is_refused_naming_both(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    engine.dispose()
    assert converter.main(["--database", str(old)]) == 2
    said = capsys.readouterr().err
    assert "bootstrap_000000000000" in said and converter.FROM_REVISION in said


def test_an_unknown_pattern_is_refused_before_anything_is_written(old: Path, capsys) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE loops SET pattern = 'shuffle' WHERE id = 'loopunrendered1'"))
    engine.dispose()
    before = old.read_bytes()
    assert converter.main(["--database", str(old)]) == 2
    assert old.read_bytes() == before
    assert "shuffle" in capsys.readouterr().err


def test_it_is_found_by_the_transition_mechanism() -> None:
    import transition

    assert [name for name, module in transition.converters(ROOT / "scripts" / "throwaway")
            if module.FROM_REVISION == converter.FROM_REVISION] == ["add_loop_formats.py"]
