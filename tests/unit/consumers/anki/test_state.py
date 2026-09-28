"""Anki's review state as Acervo records it.

The pure half: how a note's cards collapse into one row, what the graph is told, and what is left
out. The robot's own read side is covered by `test_robot.py`.
"""

from __future__ import annotations

import re

import pytest

from acervo.consumers.anki.state import SYSTEM, collapse, held_by_key, study_states

INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def card(**overrides):
    return {
        "anki_card_id": 91, "reps": 4, "lapses": 1, "stability": 12.5, "difficulty": 5.2,
        "retrievability": 0.9, "last_review": "2026-09-01T00:00:00.000Z", **overrides,
    }


LEXEME = "lexeme000000001"
SENSE = "sense0000000001"
SENSES = {SENSE: LEXEME}


def note(**overrides):
    return {
        "note_id": LEXEME, "kind": "word", "lexeme_id": LEXEME, "sense_id": None,
        "anki_note_id": 17, "card_ids": [91], "cards": [card()], **overrides,
    }


def meaning(note_id=SENSE, **overrides):
    return note(**{"note_id": note_id, "kind": "meaning", "sense_id": SENSE, **overrides})


def test_a_note_with_one_card_carries_that_cards_numbers():
    assert collapse([card()]) == {
        "reps": 4, "lapses": 1, "stability": 12.5, "difficulty": 5.2,
        "retrievability": 0.9, "lastReview": "2026-09-01T00:00:00.000Z",
    }


def test_several_cards_collapse_by_counting_up_and_taking_the_weakest():
    """Counts add up because every review was a review of this word. The memory state comes from the
    least stable card, because that is the one coming up next and the one that says how well the word
    is actually known."""
    numbers = collapse(
        [
            card(stability=12.5, difficulty=5.0, retrievability=0.91, reps=4, lapses=1),
            card(stability=3.0, difficulty=7.0, retrievability=0.55, reps=2, lapses=0,
                 last_review="2026-09-05T00:00:00.000Z"),
        ]
    )
    assert numbers["reps"] == 6
    assert numbers["lapses"] == 1
    assert (numbers["stability"], numbers["difficulty"]) == (3.0, 7.0)
    assert numbers["retrievability"] == 0.55
    assert numbers["lastReview"] == "2026-09-05T00:00:00.000Z"


def test_a_note_never_reviewed_collapses_to_zeroes_rather_than_to_nothing():
    assert collapse([])["reps"] == 0
    assert collapse([])["lastReview"] is None


@pytest.mark.parametrize("value", [None, "", 1.4, -0.2])
def test_retrievability_is_held_inside_the_range_the_column_allows(value):
    """The column is bounded to (0, 1); an absent value must not become something out of range."""
    assert 0.0 <= collapse([card(retrievability=value)])["retrievability"] <= 1.0


def test_a_first_write_mints_an_id_and_claims_revision_zero():
    rows, skipped = study_states(
        {"notes": [note()]}, {}, {LEXEME}, SENSES, device_id="ankiworker0001"
    )
    assert skipped == []
    (row,) = rows
    assert re.match(r"^[a-z0-9]{15}$", row["id"])
    assert row["revision"] == 0
    assert row["system"] == SYSTEM
    assert row["lexemeId"] == "lexeme000000001"
    assert row["noteId"] == 17
    assert row["cardIds"] == [91]
    assert row["editedBy"] == "ankiworker0001"
    assert INSTANT.match(row["syncedAt"])
    assert INSTANT.match(row["editedAt"])
    assert INSTANT.match(row["createdAt"])


def test_the_wire_timestamps_are_the_shape_the_graph_route_accepts():
    """`.isoformat()` gives `+00:00` and six fractional digits, and the route refuses both."""
    rows, _ = study_states(
        {"notes": [note()]}, {}, {LEXEME}, SENSES, device_id="ankiworker0001"
    )
    assert INSTANT.match(rows[0]["lastReview"])


def test_a_second_write_updates_the_row_it_already_has():
    """A record the graph holds must state the revision it was edited from, and keep its own id."""
    held = {
        (LEXEME, None): {
            "id": "studyaaaaaaaaaa", "lexemeId": LEXEME, "system": SYSTEM,
            "revision": 42, "createdAt": "2026-08-01T00:00:00.000Z",
        }
    }
    rows, _ = study_states(
        {"notes": [note()]}, held, {LEXEME}, SENSES, device_id="ankiworker0001"
    )
    assert rows[0]["id"] == "studyaaaaaaaaaa"
    assert rows[0]["revision"] == 42
    assert rows[0]["createdAt"] == "2026-08-01T00:00:00.000Z"


def test_a_note_whose_word_is_gone_is_skipped_rather_than_refused():
    """An ordinary state, not a mismatch: a word removed in Acervo keeps its card in the collection
    until someone deletes it there, and one such note must not stop the rest from being written."""
    rows, skipped = study_states(
        {"notes": [note(), note(note_id="note00000000002", lexeme_id="goneaway0000001"),
                   meaning(note_id="note00000000003", sense_id="sensegone000001")]},
        {},
        {LEXEME},
        SENSES,
        device_id="ankiworker0001",
    )
    assert [row["lexemeId"] for row in rows] == [LEXEME]
    assert skipped == ["note00000000002", "note00000000003"]


def test_only_this_systems_rows_are_treated_as_ours():
    """Keyed by system so a second learning tool never collides with Anki."""
    changes = {
        "studyStates": [
            {"id": "aaaaaaaaaaaaaaa", "lexemeId": "lexeme000000001", "system": "anki", "revision": 1},
            {"id": "bbbbbbbbbbbbbbb", "lexemeId": "lexeme000000001", "system": "mochi", "revision": 1},
        ]
    }
    assert list(held_by_key(changes)) == [(LEXEME, None)]
    assert held_by_key(changes)[(LEXEME, None)]["id"] == "aaaaaaaaaaaaaaa"


def test_what_anki_exports_and_acervo_does_not_store():
    """`queue`, `suspended` and `flag` have no columns, and giving them some means rebuilding the
    database for information nothing reads."""
    rows, _ = study_states(
        {"notes": [note(cards=[card(queue=-1, suspended=True, flag=3)])]},
        {},
        {LEXEME},
        SENSES,
        device_id="ankiworker0001",
    )
    assert not {"queue", "suspended", "flag"} & set(rows[0])


def test_a_senses_own_note_and_its_examples_make_one_row_and_the_word_another():
    rows, _ = study_states(
        {"notes": [
            meaning(note_id="example00000001", anki_note_id=30, card_ids=[301],
                    cards=[card(anki_card_id=301, stability=40.0, reps=3)]),
            meaning(anki_note_id=31, card_ids=[311], cards=[card(anki_card_id=311, stability=2.0, reps=1)]),
            note(),
        ]},
        {}, {LEXEME}, SENSES, device_id="ankiworker0001",
    )
    word, sense = rows
    assert (word["senseId"], word["noteId"], word["cardIds"]) == (None, 17, [91])
    # The row points at the sense's own note, lists every card, and knows the weakest of them.
    assert (sense["senseId"], sense["noteId"], sense["cardIds"]) == (SENSE, 31, [311, 301])
    assert (sense["reps"], sense["stability"]) == (4, 2.0)


def test_a_row_no_note_reports_on_any_more_is_tombstoned():
    """A collection wiped and rebuilt, or cards deleted by hand: the numbers describe nothing now."""
    held = {
        (LEXEME, None): {"id": "studyword000001", "lexemeId": LEXEME, "senseId": None,
                         "system": SYSTEM, "revision": 7, "deleted": False,
                         "createdAt": "2026-08-01T00:00:00.000Z"},
        (LEXEME, SENSE): {"id": "studysense00001", "lexemeId": LEXEME, "senseId": SENSE,
                          "system": SYSTEM, "revision": 8, "deleted": False,
                          "createdAt": "2026-08-01T00:00:00.000Z"},
    }
    rows, _ = study_states({"notes": [meaning()]}, held, {LEXEME}, SENSES, device_id="ankiworker0001")
    kept, retired = rows
    assert (kept["id"], kept["deleted"]) == ("studysense00001", False)
    assert (retired["id"], retired["deleted"], retired["revision"]) == ("studyword000001", True, 7)
    assert retired["editedBy"] == "ankiworker0001"
    held[(LEXEME, None)]["deleted"] = True
    assert len(study_states({"notes": [meaning()]}, held, {LEXEME}, SENSES,
                            device_id="ankiworker0001")[0]) == 1


def test_where_a_key_holds_two_rows_the_live_one_is_kept():
    changes = {"studyStates": [
        {"id": "aaaaaaaaaaaaaaa", "lexemeId": LEXEME, "senseId": None, "system": "anki", "deleted": True},
        {"id": "bbbbbbbbbbbbbbb", "lexemeId": LEXEME, "senseId": None, "system": "anki", "deleted": False},
        {"id": "ccccccccccccccc", "lexemeId": LEXEME, "senseId": SENSE, "system": "anki", "deleted": False},
    ]}
    held = held_by_key(changes)
    assert held[(LEXEME, None)]["id"] == "bbbbbbbbbbbbbbb"
    assert held[(LEXEME, SENSE)]["id"] == "ccccccccccccccc"
