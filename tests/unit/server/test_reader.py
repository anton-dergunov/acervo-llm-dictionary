"""The reader section: a vocabulary's level, variety and note, said to the writers that write for them."""

from __future__ import annotations

from acervo.services.reader import reader_section, with_reader

from graph_records import vocabulary
from test_prompt_rules import RULES, systems_of

NOTE = "Preparing for a trip to Argentina in March.\nThe subjunctive is my weak spot."
LEARNER = {"language": "es", "level": "B1", "region": "AR", "learnerNote": NOTE}


def test_a_vocabulary_that_says_nothing_about_its_learner_leaves_the_prompt_untouched(server):
    assert reader_section(None) == ""
    assert reader_section({"language": "es", "level": None, "region": None, "learnerNote": None}) == ""
    assert with_reader("The prompt.", server.owner, {"language": "es"}) == "The prompt."


def test_each_fact_is_said_in_words_firmest_first():
    section = reader_section(LEARNER)
    assert section.startswith("## The reader\n\nYou are writing for one person learning Spanish.")
    level, variety, note = (section.index(mark) for mark in ("B1, intermediate", "Spanish of Argentina",
                                                             "in their own words"))
    assert level < variety < note
    assert "Do not hide the others" in section, "a variety is a preference, never a filter"
    assert "  > Preparing for a trip to Argentina in March.\n  > The subjunctive is my weak spot." in section
    assert "not material for what you write" in section


def test_only_what_is_set_is_said():
    section = reader_section({"language": "es", "region": "419"})
    assert "Spanish of Latin America" in section
    assert "level" not in section and "own words" not in section


def test_the_reader_comes_before_the_standing_rules(server):
    assert server.put("/rules", {"rules": RULES}).status_code == 200
    joined = with_reader("The prompt.", server.owner, LEARNER)
    assert joined.startswith("The prompt.\n\n## The reader\n\n")
    assert joined.index("## The reader\n") < joined.index("## The reader's standing rules")
    assert joined.endswith(RULES)


def test_capture_writes_the_entry_for_the_reader_and_resolves_the_word_without(server):
    from test_capture import ARTICLE, RESOLUTION

    server.push({"vocabularies": [vocabulary(level="B1", region="AR", learnerNote=NOTE)]})
    server.model.resolution = dict(RESOLUTION)
    server.model.article = dict(ARTICLE)
    assert server.capture().status_code == 200

    resolve, compose = systems_of(server)
    assert "## The reader" not in resolve, "naming the word is not writing for the reader"
    assert compose.endswith(reader_section({**LEARNER}))


def test_the_article_conversation_is_had_with_the_reader_of_its_language(server):
    server.push({"vocabularies": [vocabulary(level="B1", region="AR", learnerNote=NOTE),
                                  vocabulary(language="ru", level="A1")]})
    server.model.chat = {"reply": "Una respuesta.", "followUps": []}
    subject = {"kind": "article", "lexemeId": "", "language": "es",
               "document": "headword: picar\nlanguage: es\n", "focus": None}
    assert server.chat(subject=subject).status_code == 200
    system = systems_of(server)[0]
    assert "learning Spanish" in system and "A1" not in system

    assert server.chat(subject={**subject, "language": None}).status_code == 200
    assert "## The reader" not in systems_of(server)[1], "a draft that names no language has no reader"
