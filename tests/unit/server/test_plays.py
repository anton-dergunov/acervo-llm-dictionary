"""The owner's marks on loops and stories, and plays.

A mark is an ordinary field on an ordinary record. A play is a record made once on the device it
happened on, possibly long after, and never edited; what is checked here is that the server holds it
to being *of one thing this account holds* and nothing more — not that the thing is still alive.
"""

from __future__ import annotations

from graph_records import lexeme, loop, loop_item, play, story


def _pushed(server, *records_by_key):
    changes: dict = {}
    for key, record in records_by_key:
        changes.setdefault(key, []).append(record)
    answer = server.push(changes)
    assert answer.status_code == 200, answer.json()
    return answer


def _held(server, key):
    return server.pull().json()["data"]["changes"][key]


def test_a_loop_and_a_story_carry_both_marks_off_until_they_are_set(server):
    word, track, tale = lexeme(), loop(), story()
    _pushed(server, ("lexemes", word), ("loops", track), ("loopItems", loop_item(track["id"], word["id"])),
            ("stories", tale))
    (held_loop,), (held_story,) = _held(server, "loops"), _held(server, "stories")
    assert (held_loop["starred"], held_loop["archived"]) == (False, False)
    assert (held_story["starred"], held_story["archived"]) == (False, False)

    _pushed(server, ("loops", {**held_loop, "starred": True}), ("stories", {**held_story, "archived": True}))
    assert _held(server, "loops")[0]["starred"] is True
    assert _held(server, "stories")[0]["archived"] is True


def test_a_play_of_a_loop_or_of_a_story_is_kept_with_when_it_happened(server):
    track, tale = loop(), story()
    _pushed(server, ("loops", track), ("stories", tale))
    heard = play(loopId=track["id"], createdAt="2026-11-01T07:30:00.000Z")
    _pushed(server, ("plays", heard), ("plays", play(storyId=tale["id"])))
    plays = {row["id"]: row for row in _held(server, "plays")}
    assert len(plays) == 2
    assert plays[heard["id"]]["loopId"] == track["id"] and plays[heard["id"]]["storyId"] is None
    # Made offline and sent later, it keeps the moment it happened.
    assert plays[heard["id"]]["createdAt"] == "2026-11-01T07:30:00.000Z"


def test_a_play_of_a_deleted_loop_still_counts_because_it_still_happened(server):
    track = loop()
    _pushed(server, ("loops", track))
    (held,) = _held(server, "loops")
    _pushed(server, ("loops", {**held, "deleted": True}))
    _pushed(server, ("plays", play(loopId=track["id"])))
    assert len(_held(server, "plays")) == 1


def test_a_play_is_of_one_thing_never_both_or_neither(server):
    track, tale = loop(), story()
    _pushed(server, ("loops", track), ("stories", tale))
    for refused in (play(), play(loopId=track["id"], storyId=tale["id"])):
        answer = server.push({"plays": [refused]})
        assert answer.status_code == 400
        assert "one loop or one story" in answer.json()["error"]["message"]


def test_a_play_of_another_accounts_loop_is_refused(server, other):
    theirs = loop()
    assert other.push({"loops": [theirs]}).status_code == 200
    answer = server.push({"plays": [play(loopId=theirs["id"])]})
    assert answer.status_code == 400


def test_a_play_sent_twice_is_refused_the_second_time_so_the_device_can_forget_it(server):
    track = loop()
    _pushed(server, ("loops", track))
    heard = play(loopId=track["id"])
    _pushed(server, ("plays", heard))
    # The device's copy still says revision 0: the answer to the first send never arrived.
    answer = server.push({"plays": [heard]})
    assert answer.status_code == 409
    assert len(_held(server, "plays")) == 1
