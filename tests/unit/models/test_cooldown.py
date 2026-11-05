"""What a refusal tells the next request.

The rule that makes this safe rather than clever: a rest reorders a chain and can never empty one.
Everything here is a check on that, from a different angle.
"""

from __future__ import annotations

import httpx
import pytest

from acervo.models import chain
from provider_rows import GEMINI, providers
from acervo.models.cooldown import LONGEST, REST, Rests, retry_after_of, rests
from acervo.models.errors import ProviderUnavailable
from acervo.models.results import Answer, TextResult

OPENAI = {"id": "openai", "family": "openai", "models": {"text": ["gpt-5.1"]}}
SHIPPED = providers(GEMINI, OPENAI)
FIRST = ("gemini-api", "gemini-3.5-flash-lite")
SECOND = ("gemini-api", "gemini-3.1-flash-lite")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    rests.forget_all()
    yield
    rests.forget_all()


def answers(candidate):
    return TextResult(
        text="{}", parsed={},
        answer=Answer(candidate.row.id, candidate.model, 0.1, None, (), (candidate.named,)),
    )


def limited():
    return ProviderUnavailable("rate_limited", "429", provider_id="gemini-api", status=429)


def test_a_rested_pair_is_asked_last_rather_than_not_at_all():
    register = Rests()
    register.note(FIRST, "rate_limited")
    assert register.resting(FIRST)
    assert register.ready([FIRST, SECOND]) == (SECOND,)


def test_when_everything_is_resting_the_chain_is_walked_as_written():
    """The rule the whole design rests on. Without it, one 429 against an owner who has chosen a
    single model would switch capture off until somebody guessed the provider's reset hour."""
    register = Rests()
    register.note(FIRST, "rate_limited")
    register.note(SECOND, "rate_limited")
    assert register.ready([FIRST, SECOND]) == (FIRST, SECOND)


def test_a_rest_expires_on_its_own(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("acervo.models.cooldown.time.monotonic", lambda: clock[0])
    register = Rests()
    register.note(FIRST, "rate_limited")
    assert register.resting(FIRST)
    clock[0] = REST["rate_limited"] + 1
    assert not register.resting(FIRST)


def test_one_overloaded_answer_is_forgiven_and_the_second_in_a_row_rests():
    """A "high demand" 503 lands on one request in three and the next is usually fine. Resting on the
    first sent the second call of the same capture to the slower fallback."""
    register = Rests()
    assert register.note(FIRST, "unavailable") == 0.0
    assert not register.resting(FIRST)
    assert register.note(FIRST, "unavailable") == REST["unavailable"]
    assert register.resting(FIRST)
    assert register.note(FIRST, "unavailable") == REST["unavailable"] * 2


def test_the_providers_own_delay_is_believed_even_on_a_forgiven_failure():
    register = Rests()
    assert register.note(FIRST, "unavailable", retry_after=12.0) == 12.0


def test_a_rate_limit_rests_longer_than_a_hiccup():
    """An allowance refills on the provider's clock; a 5xx is usually over by the time you look."""
    register = Rests()
    register.note(SECOND, "unavailable")
    assert register.note(FIRST, "rate_limited") > register.note(SECOND, "unavailable")


def test_a_pair_that_keeps_failing_is_asked_about_less_often():
    register = Rests()
    first = register.note(FIRST, "rate_limited")
    second = register.note(FIRST, "rate_limited")
    assert second == pytest.approx(first * 2)
    for _ in range(20):
        register.note(FIRST, "rate_limited")
    assert register.note(FIRST, "rate_limited") == LONGEST


def test_a_success_forgets_the_refusals_before_it():
    register = Rests()
    register.note(FIRST, "rate_limited")
    register.note(FIRST, "rate_limited")
    register.succeeded(FIRST)
    assert not register.resting(FIRST)
    # And the doubling starts over, rather than resuming where a stale streak left off.
    assert register.note(FIRST, "rate_limited") == REST["rate_limited"]


def test_a_terminal_refusal_is_not_rested():
    """It stops the chain outright, so resting it would say nothing about what to ask next."""
    register = Rests()
    assert register.note(FIRST, "authentication") == 0.0
    assert not register.resting(FIRST)


def test_the_provider_is_believed_over_the_table_when_it_says_when_to_come_back():
    """Nobody else knows when that allowance refills."""
    register = Rests()
    assert register.note(FIRST, "rate_limited", retry_after=30.0) == 30.0


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"retry-after": "42"}, 42.0),
        ({"retry-after": "  7  "}, 7.0),
        ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),  # the date form; the table is fine
        ({}, None),
        ({"retry-after": str(LONGEST * 5)}, LONGEST),
    ],
)
def test_a_retry_after_header_is_read_when_there_is_one(headers, expected):
    error = ProviderUnavailable("rate_limited", "429")
    error.response = httpx.Response(  # type: ignore[attr-defined]
        429, headers=headers, request=httpx.Request("POST", "https://p.example.com")
    )
    assert retry_after_of(error) == expected


def test_an_error_carrying_no_response_is_not_a_crash():
    assert retry_after_of(ProviderUnavailable("unavailable", "boom")) is None


# ── through the walk, which is where it matters ─────────────────────────────


def test_a_second_request_does_not_re_probe_what_just_refused():
    """The point of the whole module: an exhausted free tier costs one wasted call, not one per word."""
    asked: list[tuple[str, str]] = []

    def ask(candidate):
        asked.append(candidate.named)
        if candidate.named == FIRST:
            raise limited()
        return answers(candidate)

    chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert asked == [FIRST, SECOND]

    asked.clear()
    chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert asked == [SECOND]


def test_a_rested_pair_is_still_reached_once_everything_else_has_refused():
    """Recovery needs no reset hour to be known: the chain probes on its own once nothing is left."""
    def ask(candidate):
        raise limited()

    with pytest.raises(Exception):
        chain.walk("text", [("gemini-api", FIRST[1])], SHIPPED, ask, chain.stamped)

    asked: list[tuple[str, str]] = []

    def answering(candidate):
        asked.append(candidate.named)
        return answers(candidate)

    # Resting, and the only member of the chain — so it is asked anyway, and it works.
    result = chain.walk("text", [("gemini-api", FIRST[1])], SHIPPED, answering, chain.stamped)
    assert asked == [FIRST]
    assert result.answer.model == FIRST[1]


def test_a_success_clears_the_rest_so_the_owners_order_returns():
    asked: list[tuple[str, str]] = []
    failing = {"now": True}

    def ask(candidate):
        asked.append(candidate.named)
        if candidate.named == FIRST and failing["now"]:
            raise limited()
        return answers(candidate)

    chain.walk("text", None, SHIPPED, ask, chain.stamped)  # first rests
    failing["now"] = False
    rests.forget_all()  # as an expiry would
    asked.clear()
    chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert asked == [FIRST]


def test_resting_never_changes_which_pairs_are_in_the_chain():
    """Only the order. A rest is a hint, and a hint must not be able to refuse anything."""
    rests.note(FIRST, "rate_limited")
    resolved = {candidate.named for candidate in chain.resolve("text", None, SHIPPED)}
    assert FIRST in resolved
