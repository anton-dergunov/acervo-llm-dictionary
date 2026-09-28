"""The review history: kept as it arrives, once, and read back as figures."""

from __future__ import annotations

from datetime import date, timezone

from graph_records import lexeme, sense, topic, vocabulary

from acervo.services.reviews import statistics


def review(word: str, number: int, **overrides) -> dict:
    """One Anki review, in the shape the worker sends. `number` is its id: its time in ms."""
    return {
        "reviewId": 1_788_000_000_000 + number, "cardId": 91, "noteId": 17, "lexemeId": word,
        "senseId": None, "cardType": "Listen", "reviewedAt": "2026-09-01T09:00:00.000Z",
        "kind": "review", "button": 3, "intervalDays": 4.0, "lastIntervalDays": 1.0,
        "durationMs": 6000, **overrides,
    }


def held(server) -> tuple[dict, dict]:
    word = lexeme(headword="picar", lemma="picar")
    meaning = sense(word["id"])
    assert server.push({"vocabularies": [vocabulary()], "lexemes": [word],
                        "senses": [meaning]}).status_code == 200
    return word, meaning


def test_a_batch_is_kept_once_however_often_it_is_sent(server):
    word, meaning = held(server)
    batch = [review(word["id"], 1), review(word["id"], 2, senseId=meaning["id"], cardType="Produce")]
    with server.api() as client:
        assert client.latest_review("anki") is None
        first = client.push_reviews("anki", batch)
        again = client.push_reviews("anki", batch)
        assert client.latest_review("anki") == 1_788_000_000_002
    assert (first["added"], first["known"]) == (2, 0)
    assert (again["added"], again["known"]) == (0, 2)


def test_reviews_of_words_the_account_does_not_hold_are_left_out_not_refused(server):
    word, meaning = held(server)
    other, other_meaning = held(server)
    batch = [
        review(word["id"], 1),
        review("lexemenowhere01", 2),
        review(word["id"], 3, senseId=other_meaning["id"]),   # a sense of another word
    ]
    answer = server.post("/reviews", {"system": "anki", "reviews": batch})
    assert answer.status_code == 200
    assert answer.json()["data"] == {"received": 3, "added": 1, "known": 0, "skipped": 2}


def test_a_malformed_review_refuses_the_batch(server):
    word, _ = held(server)
    for broken in ({"kind": "cram"}, {"button": 5}, {"reviewedAt": "2026-09-01T09:00:00+00:00"},
                   {"lexemeId": "Not-An-Id"}, {"reviewId": "17"}):
        answer = server.post("/reviews", {"system": "anki", "reviews": [review(word["id"], 1, **broken)]})
        assert answer.status_code == 400, broken
        assert answer.json()["error"]["code"] == "invalid_input"


def test_the_history_reads_back_as_figures(server):
    subject = topic(name="Kitchen")
    word = lexeme(headword="picar", lemma="picar", topicIds=[subject["id"]])
    assert server.push({"vocabularies": [vocabulary()], "topics": [subject],
                        "lexemes": [word]}).status_code == 200
    server.post("/reviews", {"system": "anki", "reviews": [
        review(word["id"], 1, button=1),
        review(word["id"], 2, button=3),
        review(word["id"], 3, kind="learn", button=1),
    ]})
    figures = server.get("/stats?days=7").json()["data"]
    assert figures["totals"]["reviews"] == 3
    assert figures["totals"]["words"] == 1
    assert len(figures["days"]) == 7
    assert figures["retention"]["answered"] == 2 and figures["retention"]["rate"] == 0.5
    assert figures["retention"]["byTopic"] == [
        {"topic": "Kitchen", "answered": 2, "passed": 1, "rate": 0.5}]
    assert server.get("/stats?language=zh").json()["data"]["totals"]["reviews"] == 0


def row(day: str, **overrides) -> dict:
    return {"reviewed_at": f"{day}T09:00:00.000Z", "kind": "review", "button": 3,
            "card_type": "Recognise", "lexeme": "lexeme000000001", "duration_ms": 60000,
            "topics": [], **overrides}


def test_retention_counts_only_scheduled_reviews_and_again_is_the_only_failure():
    figures = statistics(
        [row("2026-09-01", button=1), row("2026-09-01", button=2), row("2026-09-02", button=4),
         row("2026-09-02", kind="learn", button=1), row("2026-09-02", kind="relearn", button=1),
         row("2026-09-02", kind="manual", button=0)],
        {}, zone=timezone.utc, today=date(2026, 9, 2), days=3,
    )
    assert figures["retention"]["answered"] == 3
    assert figures["retention"]["passed"] == 2
    assert figures["answers"] == {"again": 1, "hard": 1, "good": 0, "easy": 1}
    assert figures["totals"]["minutes"] == 6.0
    assert [day["reviews"] for day in figures["days"]] == [0, 2, 4]


def test_the_streak_counts_back_from_today_or_from_yesterday_when_today_is_not_done_yet():
    rows = [row("2026-08-30"), row("2026-08-31"), row("2026-09-01")]
    assert statistics(rows, {}, zone=timezone.utc, today=date(2026, 9, 1))["totals"]["streak"] == 3
    assert statistics(rows, {}, zone=timezone.utc, today=date(2026, 9, 2))["totals"]["streak"] == 3
    assert statistics(rows, {}, zone=timezone.utc, today=date(2026, 9, 3))["totals"]["streak"] == 0


def test_weeks_run_monday_to_sunday_and_the_last_is_this_one():
    figures = statistics([row("2026-09-02", button=1)], {}, zone=timezone.utc,
                         today=date(2026, 9, 2), weeks=2)
    assert [week["week"] for week in figures["retention"]["weeks"]] == ["2026-08-24", "2026-08-31"]
    assert figures["retention"]["weeks"][1]["rate"] == 0.0
    assert figures["retention"]["weeks"][0]["rate"] is None
