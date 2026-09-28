from pathlib import Path

import pytest
from anki.collection import Collection

from acervo.consumers.anki.model import (
    KINDS,
    MEANING,
    WORD,
    CardDesign,
    ModelMismatchError,
    create_notetypes,
    install_fonts,
    require_notetype,
)

TEMPLATES = Path(__file__).resolve().parents[4] / "templates"


@pytest.fixture
def design() -> CardDesign:
    return CardDesign.load(TEMPLATES)


@pytest.fixture
def collection(tmp_path):
    opened = Collection(str(tmp_path / "collection.anki2"))
    yield opened
    opened.close()


def test_both_note_types_are_created_with_their_fields_and_cards(collection, design):
    created = create_notetypes(collection, design)
    for key, kind in KINDS.items():
        assert [field["name"] for field in created[key]["flds"]] == list(kind.fields)
        assert [template["name"] for template in created[key]["tmpls"]] == [
            card.name for card in kind.cards]
    assert [card.name for card in MEANING.cards] == ["Recognise", "Produce"]
    assert [card.name for card in WORD.cards] == ["Listen"]


def test_every_face_carries_the_card_script_and_no_marker(design):
    for face in design.faces.values():
        assert "<script>" in face
        assert "acervo:script" not in face


def test_every_front_is_behind_a_gate_so_a_note_makes_only_the_cards_it_asks_for(design):
    for kind in KINDS.values():
        for card in kind.cards:
            front = design.faces[card.front]
            assert front.startswith("{{#") and front.rstrip().endswith("}}"), card.front


def test_a_new_look_is_an_ordinary_change_and_is_applied(collection, design):
    create_notetypes(collection, design)
    notetype = collection.models.by_name(WORD.name)
    notetype["css"] = ".card { color: red; }"
    collection.models.update_dict(notetype)
    schema = collection.db.scalar("select scm from col")

    with pytest.raises(ModelMismatchError, match="look different"):
        require_notetype(collection, WORD, design, update_design=False)
    updated, changed = require_notetype(collection, WORD, design, update_design=True)

    assert changed and updated["css"] == design.css
    # The point of keeping look and shape apart: no full sync is asked for.
    assert collection.db.scalar("select scm from col") == schema
    assert require_notetype(collection, WORD, design, update_design=True)[1] is False


def test_a_different_shape_is_refused(collection, design):
    create_notetypes(collection, design)
    notetype = collection.models.by_name(MEANING.name)
    collection.models.add_field(notetype, collection.models.new_field("Extra"))
    collection.models.update_dict(notetype)
    with pytest.raises(ModelMismatchError, match="full sync"):
        require_notetype(collection, MEANING, design, update_design=True)


def test_fonts_are_installed_once_under_names_check_media_keeps(collection, design):
    assert install_fonts(collection, design) == len(design.fonts) > 0
    assert install_fonts(collection, design) == 0
    assert all(font.name.startswith("_") for font in design.fonts)
    assert list(collection.media.check().unused) == []


def test_a_card_names_no_sound_it_does_not_have(collection, design):
    """Anki reads sound tags anywhere in a card's HTML, a script's comments included: one comment that
    showed the tag by example made every card ask to play a file called "…", and AnkiDroid said so on
    every card. A note with no recording must render with no sound at all."""
    notetypes = create_notetypes(collection, design)
    for key, gates in (("meaning", {"Recognise": "y", "Produce": "y"}), ("word", {})):
        note = collection.new_note(notetypes[key])
        for name, value in {"AcervoNoteId": f"{key}0000000001", "AcervoLexemeId": "lexeme000000001",
                            "Headword": "asco", **gates}.items():
            note[name] = value
        if key == "word":
            note["HeadwordAudio"] = '<audio src="acervo-asco.ogg" preload="auto"></audio>'
        collection.add_note(note, collection.decks.id("Spanish::Vocabulary"))
        for card in note.cards():
            assert card.question_av_tags() == [] and card.answer_av_tags() == [], card.template()["name"]
