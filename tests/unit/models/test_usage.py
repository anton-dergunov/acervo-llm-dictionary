"""Every attempt at a model reaches the sink, with what it used up.

Usage is only as true as these reports: a 429 that went uncounted would show a free tier with room
in it while every call is refused, and a refused key that went uncounted would show a quiet model
rather than a broken one. So these assert one report per pair asked — the winner, every pair passed
over, a refusal that ends the walk, and a raced loser that finishes after the walk returned.
"""

from __future__ import annotations

import base64
import logging
import threading

import litellm
import pytest

from acervo.models import call, chain, journal, usage
from acervo.models.cooldown import rests
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable
from acervo.models.results import Answer, Spent, TextResult
from provider_rows import CLOUDFLARE, GEMINI, GOOGLE, google_voices, provider, providers

from acervo.models import listing

SHIPPED = providers(GEMINI, CLOUDFLARE)
FIRST = ("gemini-api", "gemini-3.5-flash-lite")
SECOND = ("gemini-api", "gemini-3.1-flash-lite")


@pytest.fixture(autouse=True)
def heard():
    rests.forget_all()
    found: list[usage.Attempt] = []
    usage.attach(found.append)
    yield found
    usage.detach(found.append)
    rests.forget_all()


def answered(candidate, spent=Spent(input_tokens=120, output_tokens=30), cost=0.0002):
    return TextResult(text="{}", parsed={}, answer=Answer(
        candidate.row.id, candidate.model, 0.1, cost, (), (candidate.named,), spent=spent))


def test_the_pair_that_answered_is_reported_with_what_it_used_up(heard):
    chain.walk("text", None, SHIPPED, answered, chain.stamped, caller="brief")
    [one] = heard
    assert (one.kind, one.provider, one.model, one.caller) == ("text", *FIRST, "brief")
    assert one.answered and one.reason is None
    assert one.spent == Spent(input_tokens=120, output_tokens=30) and one.cost_usd == 0.0002


def test_every_pair_passed_over_is_counted_because_a_refused_request_spends_one_too(heard):
    script = [ProviderUnavailable("rate_limited", "quota exhausted for today")]

    def ask(candidate):
        if script:
            raise script.pop()
        return answered(candidate)

    chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert [(one.model, one.reason) for one in heard] == [(FIRST[1], "rate_limited"), (SECOND[1], None)]
    assert heard[0].detail == "quota exhausted for today" and heard[0].spent == Spent()


def test_a_refusal_that_ends_the_walk_is_counted_and_still_raised(heard, caplog):
    caplog.set_level(logging.INFO, logger=journal.LOGGER)

    def ask(candidate):
        raise ProviderRefused("authentication", "API key not valid")

    with pytest.raises(ProviderRefused):
        chain.walk("text", None, SHIPPED, ask, chain.stamped, caller="capture")
    assert [(one.model, one.reason, one.detail) for one in heard] == [
        (FIRST[1], "authentication", "API key not valid")]
    # And it is in the call log now, where it used to leave nothing.
    assert "capture gemini-api:gemini-3.5-flash-lite authentication after" in caplog.text


def test_an_exhausted_walk_counts_every_pair(heard):
    def ask(candidate):
        raise ProviderUnavailable("unavailable", "503")

    with pytest.raises(ChainExhausted):
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert len(heard) == 3 and {one.reason for one in heard} == {"unavailable"}


def test_a_raced_loser_that_answers_late_is_counted_with_its_tokens(heard):
    held = threading.Event()

    def ask(candidate):
        if candidate.named == FIRST:
            assert held.wait(10)
        return answered(candidate)

    try:
        result = chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=0.01)
    finally:
        held.set()
    assert result.answer.model == SECOND[1]
    for _ in range(500):
        if len(heard) == 2:
            break
        threading.Event().wait(0.01)
    assert [one.model for one in heard] == [SECOND[1], FIRST[1]]
    assert heard[1].answered and heard[1].spent.input_tokens == 120


def test_a_sink_that_raises_never_fails_the_call(heard, caplog):
    caplog.set_level(logging.INFO, logger=journal.LOGGER)

    def broken(attempt):
        raise RuntimeError("database is locked")

    usage.attach(broken)
    try:
        result = chain.walk("text", None, SHIPPED, answered, chain.stamped)
    finally:
        usage.detach(broken)
    assert result.answer.model == FIRST[1] and len(heard) == 1
    assert "not counted — database is locked" in caplog.text


def test_attaching_twice_counts_once(heard):
    usage.attach(heard.append)
    chain.walk("text", None, SHIPPED, answered, chain.stamped)
    assert len(heard) == 1


def test_the_call_log_carries_the_units_and_the_timings_still_read_it(caplog):
    caplog.set_level(logging.INFO, logger=journal.LOGGER)
    chain.walk("text", None, SHIPPED, answered, chain.stamped, caller="brief")
    [line] = [record.getMessage() for record in caplog.records if " ok in " in record.getMessage()]
    assert line.endswith(" in=120 out=30 cost=0.0002")
    [timing] = journal.summarise([f"2026-11-06 10:00:00,000 INFO {line}"])
    assert timing.answered == 1 and timing.pair == "gemini-api:gemini-3.5-flash-lite"


# ── what each kind used up ──────────────────────────────────────────────────


def test_text_reads_its_tokens_from_the_providers_usage(monkeypatch):
    reply = litellm.ModelResponse(
        choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}],
        usage={"prompt_tokens": 812, "completion_tokens": 95, "total_tokens": 907},
    )
    monkeypatch.setattr(call, "completion", lambda **_: reply)
    assert call.text("hello", row=provider(GEMINI)).answer.spent == Spent(input_tokens=812, output_tokens=95)


def test_a_picture_is_one_picture(monkeypatch):
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", lambda **_: payload)
    monkeypatch.setattr("acervo.models.cloudflare.image", lambda *a, **k: (b"IMG", "image/png"))
    assert call.image("a hook", row=provider(CLOUDFLARE)).answer.spent.pictures == 1


def test_a_voice_counts_the_characters_it_was_sent(monkeypatch):
    monkeypatch.setattr(listing, "_google_voices", google_voices)
    monkeypatch.setattr("acervo.models.google_tts.speech", lambda *a, **k: (b"ID3MP3", "audio/mpeg"))
    result = call.speech("¡Qué pica!", row=provider(GOOGLE), model="Wavenet", language="es")
    assert result.answer.spent == Spent(characters=len("¡Qué pica!"))


def test_a_photo_read_is_one_photo(monkeypatch):
    monkeypatch.setattr("acervo.models.google_vision.read", lambda *a, **k: ([], 10, 10, None))
    assert call.ocr(b"JPEG", row=provider(GOOGLE)).answer.spent == Spent(photos=1)
