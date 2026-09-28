import json

import pytest
from pydantic import ValidationError

from acervo.consumers.anki.manifest import SyncManifest


NOTE_ID = "example00000001"
LEXEME_ID = "lexeme000000001"
SENSE_ID = "sense0000000001"


def meaning(**overrides):
    note = {
        "kind": "meaning",
        "note_id": NOTE_ID,
        "lexeme_id": LEXEME_ID,
        "sense_id": SENSE_ID,
        "deck": "Spanish::Vocabulary",
        "fields": {"Recognise": "y", "Headword": "balsa", "Sentence": "La <mark>balsa</mark>."},
        "tags": ["acervo::topic::travel"],
    }
    note.update(overrides)
    return note


def payload(*notes):
    return {"schema_version": 2, "notes": list(notes) or [meaning()]}


def test_manifest_accepts_the_versioned_contract():
    manifest = SyncManifest.model_validate(payload())
    assert manifest.notes[0].note_id == NOTE_ID


@pytest.mark.parametrize(
    "change,match",
    [
        ({"tags": ["travel"]}, "acervo::"),
        ({"tags": ["acervo::x", "acervo::x"]}, "unique"),
        ({"sense_id": None}, "names its sense"),
        ({"kind": "word"}, "names its sense"),
        ({"fields": {"Recognise": "y", "Comment": "x"}}, "no content field Comment"),
        ({"fields": {"Recognise": "y", "AcervoNoteId": "x"}}, "no content field AcervoNoteId"),
        ({"media": {"Sentence": "media/x.mp3"}}, "no media field Sentence"),
        ({"fields": {"Headword": "balsa"}}, "would make no card"),
    ],
)
def test_manifest_rejects_what_the_note_type_cannot_hold(change, match):
    with pytest.raises(ValidationError, match=match):
        SyncManifest.model_validate(payload(meaning(**change)))


def test_a_word_note_needs_its_recording_to_make_a_card():
    word = {"kind": "word", "note_id": LEXEME_ID, "lexeme_id": LEXEME_ID, "deck": "D",
            "fields": {"Headword": "balsa"}}
    with pytest.raises(ValidationError, match="would make no card"):
        SyncManifest.model_validate(payload(word))
    word["media"] = {"HeadwordAudio": "media/balsa.mp3"}
    assert SyncManifest.model_validate(payload(word)).notes[0].kind == "word"


def test_version_one_is_refused():
    value = payload()
    value["schema_version"] = 1
    with pytest.raises(ValidationError, match="schema_version"):
        SyncManifest.model_validate(value)


def test_manifest_rejects_duplicate_note_ids():
    with pytest.raises(ValidationError, match="note_id values must be unique"):
        SyncManifest.model_validate(payload(meaning(), meaning()))


def test_manifest_resolves_media_and_embedded_files_inside_its_directory(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "image.webp").write_bytes(b"image")
    (media / "thumb.webp").write_bytes(b"thumb")
    manifest_path = tmp_path / "manifest.json"
    note = meaning(media={"Picture": "media/image.webp"},
                   fields={"Recognise": "y", "Senses": '<img src="media/thumb.webp">'})
    manifest_path.write_text(json.dumps(payload(note)), encoding="utf-8")

    manifest, root = SyncManifest.load(manifest_path)
    assert manifest.notes[0].media_sources(root) == {"Picture": media / "image.webp"}
    assert manifest.notes[0].embedded_sources(root) == {"media/thumb.webp": media / "thumb.webp"}


@pytest.mark.parametrize("unsafe", ["../outside.webp", "/tmp/outside.webp", "https://x.example/a.webp"])
def test_manifest_rejects_media_path_escape(tmp_path, unsafe):
    for note in (meaning(media={"Picture": unsafe}),
                 meaning(fields={"Recognise": "y", "Senses": f'<img src="{unsafe}">'})):
        manifest = SyncManifest.model_validate(payload(note))
        with pytest.raises((ValueError, FileNotFoundError), match="relative|escapes"):
            manifest.validate_media(tmp_path)
