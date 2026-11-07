"""`GET /words/rarity`: how common each of the owner's words is, for the make dialogs' "Rare" order —
and a language with no frequency list refused by name, and written down."""

from __future__ import annotations

import logging

import pytest
from graph_records import lexeme, vocabulary

from acervo import activity, frequency


def test_each_live_word_in_the_language_gets_a_figure_and_a_rarer_word_a_lower_one(server):
    common = lexeme(headword="la casa", lemma="casa", status="active")
    rare = lexeme(headword="el alforfón", lemma="alforfón", status="active")
    gone = lexeme(headword="el perro", lemma="perro", status="active", deleted=True)
    other = lexeme(headword="the house", lemma="house", language="en", status="active")
    server.push({"vocabularies": [vocabulary(), vocabulary(language="en", displayName="English")],
                 "lexemes": [common, rare, gone, other]})

    answer = server.get("/words/rarity?language=es")
    assert answer.status_code == 200
    figures = answer.json()["data"]["zipf"]
    assert set(figures) == {common["id"], rare["id"]}
    assert figures[rare["id"]] < figures[common["id"]]


def test_an_article_does_not_move_the_figure():
    assert frequency.zipf("el muro", "es") == frequency.zipf("muro", "es")


def test_a_regional_tag_reads_its_languages_list():
    assert frequency.covers("es-AR")
    assert frequency.zipf("casa", "es-AR") == frequency.zipf("casa", "es")


def test_a_word_no_list_has_seen_is_the_rarest_there_is():
    assert frequency.zipf("xyzzyqwv", "es") == 0


@pytest.fixture
def activity_log(tmp_path, monkeypatch):
    path = tmp_path / "activity.log"
    monkeypatch.setenv("ACERVO_ACTIVITY_LOG_PATH", str(path))
    yield path
    logger = logging.getLogger(activity.LOGGER)
    for handler in list(logger.handlers):
        if getattr(handler, "acervo_log_file", False):
            handler.close()
            logger.removeHandler(handler)
    logger.propagate = True


def test_a_language_with_no_list_is_refused_by_name_and_written_down(activity_log, server):
    answer = server.get("/words/rarity?language=ja")
    assert answer.status_code == 422
    error = answer.json()["error"]
    assert error["code"] == "rarity_unavailable"
    assert "Japanese" in error["message"]
    for handler in logging.getLogger(activity.LOGGER).handlers:
        handler.flush()
    line = next(line for line in activity_log.read_text(encoding="utf-8").splitlines() if "rarity_unavailable" in line)
    assert "language=ja" in line and "Japanese" in line


def test_a_request_naming_no_language_is_refused(server):
    assert server.get("/words/rarity").json()["error"]["code"] == "invalid_input"
