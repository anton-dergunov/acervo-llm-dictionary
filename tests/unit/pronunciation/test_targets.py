"""What gets said, in which language and by which order — pure, over wire-shaped records."""

from acervo.pronunciation.speak import direction, language_name
from acervo.pronunciation.targets import current, target_in, wanted


def records():
    return {
        "lexemes": [{"id": "lex", "language": "es", "headword": "picar", "status": "active"}],
        "senses": [
            {"id": "s1", "lexemeId": "lex", "definition": "Producir comezón.", "definitionLang": "es", "order": 0},
            {"id": "s2", "lexemeId": "lex", "definition": "To chop into pieces.", "definitionLang": "en", "order": 1},
        ],
        "examples": [
            {"id": "e1", "senseId": "s1", "text": "¡Me pica!", "textLang": "es", "emotion": "exasperated"},
            {"id": "e2", "senseId": "s2", "text": "Chop it.", "textLang": "en", "emotion": None},
            {"id": "gone", "senseId": "s1", "text": "Borrado.", "textLang": "es", "deleted": True},
        ],
        "attestations": [{"id": "a1", "lexemeId": "lex", "text": "Pica la cebolla."}],
    }


def test_each_kind_reads_its_own_text_in_its_own_language_by_its_own_order():
    changes = records()
    assert target_in(changes, "lexeme", "lex").use == "words"
    definition = target_in(changes, "sense", "s2")
    assert (definition.text, definition.language, definition.use) == ("To chop into pieces.", "en", "words")
    sentence = target_in(changes, "example", "e1")
    assert (sentence.language, sentence.emotion, sentence.use, sentence.lexeme_id) == ("es", "exasperated", "examples", "lex")
    assert target_in(changes, "attestation", "a1").language == "es"
    assert target_in(changes, "example", "gone") is None
    assert target_in(changes, "vibe", "lex") is None


def test_recording_in_advance_is_target_language_text_only():
    chosen = wanted(records(), "lex", {"headword": True, "definitions": True, "examples": True})
    assert [(target.kind, target.id) for target in chosen] == [("lexeme", "lex"), ("sense", "s1"), ("example", "e1")]
    assert wanted(records(), "lex", {"examples": True})[0].id == "e1"
    assert wanted(records(), "lex", {}) == []


def test_a_clip_is_current_only_while_its_record_says_the_same_words():
    target = target_in(records(), "example", "e1")
    clip = {"text": "¡Me pica!", "lang": "es", "audioRef": "audio/lex/x.mp3", "deleted": False}
    assert current(clip, target)
    assert not current({**clip, "text": "¡Me pica mucho!"}, target)
    assert not current({**clip, "deleted": True}, target)
    assert not current(None, target)


def test_a_direction_names_the_language_and_carries_the_emotion_verbatim():
    template = "Say this {language} sentence, sounding {emotion}."
    assert direction(template, "tender {and} warm", "es-MX") == "Say this Spanish sentence, sounding tender {and} warm."
    assert language_name("zh-Hans") == "Mandarin Chinese"
    # A language the table does not name is named by CLDR, and a tag nobody names is used as it is.
    assert language_name("pt-BR") == "Portuguese" and language_name("ka") == "Georgian"
    assert language_name("qaa") == "qaa"


def test_a_direction_carries_the_accent_only_when_one_was_chosen():
    template = "Read this {language} line as {speaker} would. {accent}Go."
    assert direction(template, "", "es") == "Read this Spanish line as a native speaker would. Go."
    assert direction(template, "", "es-AR") == (
        "Read this Spanish line as a native speaker from Argentina would. "
        "Speak with the accent of a native speaker from Argentina. Go.")
