import fcntl
from pathlib import Path

import pytest
from anki.collection import Collection

from acervo.consumers.anki.manifest import SyncManifest
from acervo.consumers.anki.model import create_notetypes
from acervo.consumers.anki.robot import (
    AnkiRobot,
    DuplicateIdentityError,
    RobotSettings,
    SyncSafetyError,
)


TEMPLATES = Path(__file__).resolve().parents[4] / "templates"
EXAMPLE_ID = "example00000001"
SENSE_ID = "sense0000000001"
LEXEME_ID = "lexeme000000001"


def make_robot(tmp_path: Path) -> AnkiRobot:
    (tmp_path / "robot").mkdir()
    return AnkiRobot(
        RobotSettings(
            endpoint="http://example.invalid/",
            username="user",
            password="password",
            collection_path=tmp_path / "robot" / "collection.anki2",
            backup_dir=tmp_path / "backups",
            template_dir=TEMPLATES,
        )
    )


def example(**overrides) -> dict:
    note = {
        "kind": "meaning",
        "note_id": EXAMPLE_ID,
        "lexeme_id": LEXEME_ID,
        "sense_id": SENSE_ID,
        "deck": "Spanish::Vocabulary",
        "fields": {"Recognise": "y", "Headword": "balsa", "Sentence": "La <mark>balsa</mark>."},
        "tags": ["acervo::topic::travel"],
    }
    note.update(overrides)
    return note


def sense(**overrides) -> dict:
    return example(**{"note_id": SENSE_ID, "fields": {"Produce": "y", "Headword": "balsa"}, **overrides})


def word(**overrides) -> dict:
    return {"kind": "word", "note_id": LEXEME_ID, "lexeme_id": LEXEME_ID,
            "deck": "Spanish::Vocabulary", "fields": {"Headword": "balsa"},
            "media": {"HeadwordAudio": "voice.mp3"}, **overrides}


def manifest(*notes: dict) -> SyncManifest:
    return SyncManifest.model_validate({"schema_version": 2, "notes": list(notes) or [example()]})


@pytest.fixture
def robot(tmp_path):
    return make_robot(tmp_path)


@pytest.fixture
def collection(robot):
    opened = Collection(str(robot.settings.collection_path))
    create_notetypes(opened, robot.design)
    yield opened
    opened.close()


def test_upsert_creates_updates_and_then_becomes_noop(robot, collection, tmp_path):
    first = robot._upsert(collection, manifest(), tmp_path)
    note_id = first["notes"][0]["anki_note_id"]
    card_ids = first["notes"][0]["card_ids"]
    note = collection.get_note(note_id)
    note.add_tag("marked")
    collection.update_note(note)
    card = note.cards()[0]
    card.reps = 7
    card.lapses = 2
    collection.update_card(card)

    changed = example(fields={"Recognise": "y", "Headword": "balsa", "Sentence": "Otra balsa."},
                      tags=["acervo::topic::nature"])
    second = robot._upsert(collection, manifest(changed), tmp_path)
    third = robot._upsert(collection, manifest(changed), tmp_path)

    updated = collection.get_note(note_id)
    assert first["created"] == 1
    assert second["updated"] == 1
    assert third["unchanged"] == 1
    assert [int(value) for value in updated.card_ids()] == card_ids
    assert updated["Sentence"] == "Otra balsa."
    assert updated["AcervoSenseId"] == SENSE_ID
    assert set(updated.tags) == {"marked", "acervo::topic::nature"}
    assert updated.cards()[0].reps == 7
    assert updated.cards()[0].lapses == 2


def test_each_note_makes_the_cards_its_gates_ask_for_in_manifest_order(robot, collection, tmp_path):
    (tmp_path / "voice.mp3").write_bytes(b"voice")
    both = sense(fields={"Produce": "y", "Recognise": "y", "Headword": "balsa"})
    report = robot._upsert(collection, manifest(example(), both, word()), tmp_path)

    cards = [collection.get_card(card) for note in report["notes"] for card in note["card_ids"]]
    assert [card.template()["name"] for card in cards] == ["Recognise", "Recognise", "Produce", "Listen"]
    # New cards come up in the order the manifest lists their notes.
    dues = [card.due for card in cards]
    assert dues[0] < dues[1] <= dues[2] < dues[3]


def test_a_gate_closed_since_the_last_push_removes_that_card_only(robot, collection, tmp_path):
    both = sense(fields={"Produce": "y", "Recognise": "y", "Headword": "balsa"})
    before = robot._upsert(collection, manifest(both), tmp_path)["notes"][0]["card_ids"]
    after = robot._upsert(collection, manifest(sense()), tmp_path)

    assert after["cards_removed"] == 1
    kept = after["notes"][0]["card_ids"]
    assert len(kept) == 1 and kept[0] in before
    assert collection.get_card(kept[0]).template()["name"] == "Produce"


def test_upsert_moves_existing_card_without_recreating_it(robot, collection, tmp_path):
    first = robot._upsert(collection, manifest(), tmp_path)
    card_id = first["notes"][0]["card_ids"][0]
    robot._upsert(collection, manifest(example(deck="Spanish::Updated")), tmp_path)
    card = collection.get_card(card_id)
    assert card.did == collection.decks.id("Spanish::Updated", create=False)


def test_upsert_imports_content_addressed_media(robot, collection, tmp_path):
    (tmp_path / "picture.webp").write_bytes(b"picture")
    (tmp_path / "voice.mp3").write_bytes(b"voice")
    (tmp_path / "thumb.webp").write_bytes(b"thumb")
    note = example(
        media={"Picture": "picture.webp", "SentenceAudio": "voice.mp3"},
        fields={"Recognise": "y", "Senses": '<div><img src="thumb.webp" alt=""></div>'},
    )
    report = robot._upsert(collection, manifest(note), tmp_path)
    stored = collection.get_note(report["notes"][0]["anki_note_id"])

    assert report["media_added"] == 3
    assert stored["Picture"].startswith('<img src="acervo-')
    assert stored["SentenceAudio"].startswith('<audio src="acervo-')
    assert 'src="acervo-' in stored["Senses"] and "thumb.webp" in stored["Senses"]
    assert list(collection.media.check().unused) == []
    assert robot._upsert(collection, manifest(note), tmp_path)["media_added"] == 0


def test_upsert_refuses_duplicate_collection_identity(robot, collection, tmp_path):
    notetype = collection.models.by_name("Acervo Meaning")
    for sentence in ("one", "two"):
        note = collection.new_note(notetype)
        note["AcervoNoteId"] = "example00000003"
        note["Recognise"] = "y"
        note["Sentence"] = sentence
        collection.add_note(note, collection.decks.id("Spanish"))
    with pytest.raises(DuplicateIdentityError, match="occurs"):
        robot._upsert(collection, manifest(), tmp_path)


def test_upsert_refuses_an_identity_held_by_the_other_note_type(robot, collection, tmp_path):
    (tmp_path / "voice.mp3").write_bytes(b"voice")
    robot._upsert(collection, manifest(word()), tmp_path)
    as_meaning = example(note_id=LEXEME_ID)
    with pytest.raises(DuplicateIdentityError, match="unexpected note type"):
        robot._upsert(collection, manifest(as_meaning), tmp_path)


def test_notes_state_says_what_each_note_reports_on(robot, collection, tmp_path):
    (tmp_path / "voice.mp3").write_bytes(b"voice")
    robot._upsert(collection, manifest(example(), sense(), word()), tmp_path)
    states = {note["note_id"]: note for note in robot._notes_state(collection)}

    assert states[EXAMPLE_ID]["kind"] == "meaning" and states[EXAMPLE_ID]["sense_id"] == SENSE_ID
    assert states[SENSE_ID]["sense_id"] == SENSE_ID
    assert states[LEXEME_ID]["kind"] == "word" and states[LEXEME_ID]["sense_id"] is None
    assert [card["card_type"] for card in states[LEXEME_ID]["cards"]] == ["Listen"]


def test_card_state_exports_review_and_flag_values(robot, collection, tmp_path):
    report = robot._upsert(collection, manifest(), tmp_path)
    card = collection.get_card(report["notes"][0]["card_ids"][0])
    card.reps = 4
    card.lapses = 1
    card.flags = 3
    collection.update_card(card)
    state = robot._card_state(collection, collection.get_card(card.id))
    assert state["reps"] == 4
    assert state["lapses"] == 1
    assert state["flag"] == 3
    assert state["card_type"] == "Recognise"
    # FSRS knows nothing about this card's scheduling, so there is no retrievability to report.
    # Anki answers `0.0` for it, which would read as "certainly forgotten".
    assert state["retrievability"] is None
    assert state["stability"] is None


def test_card_state_reports_the_retrievability_anki_computes(robot, collection, tmp_path):
    """Not re-derived here: the forgetting curve is Anki's, it changes with the FSRS version, and a
    subtly wrong reimplementation would look exactly like a right answer."""
    import re
    import time

    from anki.cards_pb2 import FsrsMemoryState

    robot._upsert(collection, manifest(), tmp_path)
    card = collection.get_card(collection.find_cards("")[0])
    card.memory_state = FsrsMemoryState(stability=30.0, difficulty=5.0)
    card.reps = 4
    card.last_review_time = int(time.time()) - 86400
    collection.update_card(card)

    state = robot._card_state(collection, collection.get_card(card.id))
    assert 0.0 < state["retrievability"] <= 1.0
    assert state["stability"] == pytest.approx(30.0)
    # And the timestamp is the shape the graph route accepts, not `isoformat()`'s.
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", state["last_review"])


def test_robot_collection_lock_refuses_concurrent_process(robot):
    lock_path = robot.settings.collection_path.parent / ".acervo-anki-robot.lock"
    with lock_path.open("a+", encoding="utf-8") as held_lock:
        fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SyncSafetyError, match="already running"):
            with robot._exclusive_collection():
                pass
