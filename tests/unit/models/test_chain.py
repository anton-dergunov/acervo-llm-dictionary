"""The locked fall-through rule, and the provenance that goes with it.

The unit walked is a (provider, model) pair, not a provider: a free tier is metered per model, so a
row's second model is a second bucket reached by the first one's 429 rather than a spare.

Several of these assert a *call count* rather than an exception. That is deliberate: "never fallen
through" is a claim about what did not happen, and an exception type alone cannot tell the
difference between a pair that was skipped and one that was tried and refused.
"""

from __future__ import annotations

import pytest

from acervo.models import call, chain
from acervo.models.cooldown import rests
from acervo.models.catalogue import load_catalogue
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable
from acervo.models.results import Answer, TextResult

SHIPPED = load_catalogue()

# What the fixture below credentials, as (provider, model) pairs in the order they are walked:
# gemini-free offers two text models, so it is asked twice before cloudflare is asked at all.
DEFAULT_WALK = [
    ("gemini-free", "gemini/gemini-3.5-flash-lite"),
    ("gemini-free", "gemini/gemini-3.1-flash-lite"),
    ("cloudflare", "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
    ("openai", "openai/gpt-5.1"),
]


@pytest.fixture(autouse=True)
def no_remembered_refusals():
    """Each test starts as a fresh process would. Rests are in-process and deliberately not stored,
    so leaking one between tests would be leaking state the server never carries either."""
    rests.forget_all()
    yield
    rests.forget_all()


@pytest.fixture(autouse=True)
def three_credentialed_rows(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a-gemini-key")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "a-cloudflare-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("OPENAI_API_KEY", "an-openai-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ACERVO_OLLAMA_URL", raising=False)
    monkeypatch.delenv("ACERVO_VERTEX_PROJECT", raising=False)


def answers(candidate):
    return TextResult(
        text="{}",
        parsed={},
        answer=Answer(candidate.row.id, candidate.model, 0.1, None, (), (candidate.named,)),
    )


def refusing(*errors):
    """A script of one outcome per pair, and a record of which pairs were reached."""
    tried: list[tuple[str, str]] = []
    script = list(errors)

    def ask(candidate):
        tried.append(candidate.named)
        outcome = script.pop(0) if script else None
        if isinstance(outcome, BaseException):
            raise outcome
        return answers(candidate)

    return ask, tried


def unavailable(reason="rate_limited"):
    return ProviderUnavailable(reason, "429 from the provider", provider_id="x", status=429)


def refused(reason="authentication"):
    return ProviderRefused(reason, "the credential was rejected", provider_id="x", status=401)


def test_a_rate_limited_model_falls_through_to_the_next_model_of_the_same_provider():
    """The reason a row lists several models at all: they are separate free-tier buckets."""
    ask, tried = refusing(unavailable())
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert tried == DEFAULT_WALK[:2]
    assert result.answer.provider_id == "gemini-free"
    assert result.answer.model == "gemini/gemini-3.1-flash-lite"
    assert result.answer.attempts == tuple(DEFAULT_WALK[:2])


def test_a_provider_is_exhausted_before_the_next_provider_is_asked():
    ask, tried = refusing(unavailable(), unavailable())
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert tried == DEFAULT_WALK[:3]
    assert result.answer.provider_id == "cloudflare"


def test_the_answer_names_the_pair_that_answered_and_not_the_one_that_was_asked_first():
    """The locked provenance contract: a fall-through that leaves `modelId` naming the first
    choice is a bug, so `modelId` is read from here rather than from the configuration."""
    ask, _tried = refusing(unavailable(), unavailable(), unavailable())
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert (result.answer.provider_id, result.answer.model) == DEFAULT_WALK[3]


def test_an_authentication_failure_stops_the_chain_and_nothing_else_is_called():
    """A mistake to fix, not a condition to route around. The call count is the assertion, and it
    covers the row's own second model as well as the next provider: a rejected key is not fixed by
    asking the same provider for a different model."""
    ask, tried = refusing(refused())
    with pytest.raises(ProviderRefused):
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert tried == DEFAULT_WALK[:1]


@pytest.mark.parametrize("reason", ["authentication", "configuration", "refused", "unconfigured"])
def test_no_terminal_reason_is_ever_routed_around(reason):
    ask, tried = refusing(refused(reason))
    with pytest.raises(ProviderRefused):
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert len(tried) == 1


@pytest.mark.parametrize(
    "reason", ["rate_limited", "unavailable", "unreachable", "unusable", "empty"]
)
def test_every_retryable_reason_moves_to_the_next_pair(reason):
    """`unusable` and `empty` are raised by the *caller*, from inside `ask`, when a model answered
    but not in the shape that was asked for. They are retryable for the same argument the rule
    rests on: that is a fact about the model rather than a mistake in the deployment, and it is
    precisely what a chain of alternatives exists for. Terminal, a weak row at the head made every
    stronger row behind it unreachable."""
    ask, tried = refusing(unavailable(reason))
    chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert tried == DEFAULT_WALK[:2]


def test_every_pair_unavailable_raises_chain_exhausted_carrying_the_last_error():
    """The last one is the actionable one, and it is what keeps the retry contract: a chain whose
    final pair was rate limited must still be reported as rate limiting."""
    ask, tried = refusing(
        unavailable("unavailable"),
        unavailable("unreachable"),
        unavailable("unavailable"),
        unavailable("rate_limited"),
    )
    with pytest.raises(ChainExhausted) as caught:
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert caught.value.attempts == tuple(DEFAULT_WALK)
    assert caught.value.last.reason == "rate_limited"
    assert tried == DEFAULT_WALK


def test_an_unset_chain_is_every_credentialed_pair_in_catalogue_order():
    assert [c.named for c in chain.resolve("text", None, SHIPPED)] == DEFAULT_WALK


def test_a_row_without_credentials_is_left_out_rather_than_tried(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert [c.row.id for c in chain.resolve("text", None, SHIPPED)] == ["cloudflare", "openai"]
    assert [c.row.id for c in chain.resolve("text", ["gemini-free", "openai"], SHIPPED)] == ["openai"]


def test_a_stated_chain_is_asked_in_the_order_it_states_with_each_rows_models_in_turn():
    ask, tried = refusing(unavailable())
    chain.walk("text", ["openai", "gemini-free"], SHIPPED, ask, chain.stamped)
    assert tried == [DEFAULT_WALK[3], DEFAULT_WALK[0]]


def test_a_single_model_row_still_names_its_model_as_a_list():
    """Always a list, even of one: "which model" is as much a choice as "which provider", and a
    scalar would make the one-model case a different shape from the two-model case."""
    assert SHIPPED.find("openai").models_for("text") == ("openai/gpt-5.1",)
    assert len(SHIPPED.find("gemini-free").models_for("text")) == 2


def test_an_unknown_provider_id_is_a_mistake_to_fix_rather_than_a_row_to_skip():
    with pytest.raises(ProviderRefused, match="nonesuch"):
        chain.resolve("text", ["nonesuch"], SHIPPED)


def test_a_row_asked_for_a_kind_it_does_not_serve_is_refused():
    with pytest.raises(ProviderRefused, match="does not serve image"):
        chain.resolve("image", ["openrouter"], SHIPPED)


def test_nothing_credentialed_names_the_first_unmet_requirement(monkeypatch):
    """What `GET /health` shows, and it must be a variable name rather than a value."""
    for name in ("GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(name)
    with pytest.raises(ProviderRefused) as caught:
        chain.walk("text", None, SHIPPED, lambda c: pytest.fail("called"), chain.stamped)
    assert caught.value.reason == "unconfigured"
    assert caught.value.detail == "GEMINI_API_KEY is not set"


def test_a_stated_chain_with_no_credentials_reports_that_chains_own_first_requirement(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    with pytest.raises(ProviderRefused) as caught:
        chain.walk("text", ["cloudflare"], SHIPPED, lambda c: pytest.fail("called"), chain.stamped)
    assert caught.value.detail == "CLOUDFLARE_API_TOKEN is not set"


def test_the_walk_calls_the_real_text_function_with_the_model_it_chose(monkeypatch):
    """The chain and the call fit together: this is the only test that runs both, and it is what
    proves the chain's choice of model actually reaches the request."""
    import litellm

    seen: list[str] = []

    def completion(**kwargs):
        seen.append(kwargs["model"])
        if len(seen) == 1:
            raise litellm.RateLimitError(message="429", llm_provider="p", model="m")
        return litellm.ModelResponse(
            model=kwargs["model"],
            choices=[{"index": 0, "finish_reason": "stop",
                      "message": {"role": "assistant", "content": "{}"}}],
        )

    monkeypatch.setattr(call, "completion", completion)
    result = chain.walk(
        "text",
        None,
        SHIPPED,
        lambda c: call.text("hello", row=c.row, model=c.model, as_json=True),
        chain.stamped,
    )
    assert seen == [pair[1] for pair in DEFAULT_WALK[:2]]
    assert result.answer.model == "gemini/gemini-3.1-flash-lite"
    assert result.answer.attempts == tuple(DEFAULT_WALK[:2])


# ── choosing one model of a row ─────────────────────────────────────────────
# A chain entry is a bare row id or an explicit (provider, model) pair. The id is what
# `ACERVO_TEXT_CHAIN` writes — a deploy-time flag pins a provider and leaves the models to the
# catalogue. The pair is what the owner's record stores, because a free tier is metered per model.


GEMINI_MODELS = ("gemini/gemini-3.5-flash-lite", "gemini/gemini-3.1-flash-lite")


def test_a_pair_resolves_to_that_model_alone_even_though_the_row_offers_two():
    chosen = [("gemini-free", "gemini/gemini-3.1-flash-lite")]
    assert [c.named for c in chain.resolve("text", chosen, SHIPPED)] == [
        ("gemini-free", "gemini/gemini-3.1-flash-lite")
    ]


def test_a_bare_id_still_means_every_model_that_row_offers():
    assert [c.model for c in chain.resolve("text", ["gemini-free"], SHIPPED)] == list(GEMINI_MODELS)


def test_ids_and_pairs_mix_in_the_order_they_are_stated():
    """The env var writes ids and the owner's record writes pairs; both reach one resolver."""
    chosen = [("cloudflare", "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast"), "gemini-free"]
    assert [c.named for c in chain.resolve("text", chosen, SHIPPED)] == [
        ("cloudflare", "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
        ("gemini-free", GEMINI_MODELS[0]),
        ("gemini-free", GEMINI_MODELS[1]),
    ]


def test_a_model_the_row_does_not_offer_is_refused_rather_than_skipped():
    """Not holding a key is a legitimate state; naming a model the catalogue does not offer is not.

    Skipping it would be silently wrong twice: retire both of a row's models and `unconfigured`
    reports a key as missing when it is plainly set, and retire one and capture quietly walks half
    the chain the owner configured, forever, with no symptom.
    """
    with pytest.raises(ProviderRefused, match="does not offer") as caught:
        chain.resolve("text", [("gemini-free", "gemini/retired-last-year")], SHIPPED)
    assert caught.value.reason == "configuration"
    assert "gemini-free" in caught.value.detail and "retired-last-year" in caught.value.detail


def test_a_model_the_row_offers_for_another_kind_is_still_refused_for_this_one():
    image = SHIPPED.find("vertex").models_for("image")[0]
    with pytest.raises(ProviderRefused, match="does not offer"):
        chain.resolve("text", [("vertex", image)], SHIPPED)


def test_an_unknown_model_is_refused_even_when_that_rows_key_is_also_missing(monkeypatch):
    """The model check comes before the credential check, deliberately.

    Otherwise the identical stored record is a refusal on a server holding the key and a silent skip
    on one that does not — the error would depend on the environment rather than on the record, and
    a test asserting it would be flaky by configuration.
    """
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ProviderRefused, match="does not offer"):
        chain.resolve("text", [("gemini-free", "gemini/retired-last-year")], SHIPPED)


def test_a_pair_on_an_uncredentialed_row_is_skipped_like_a_bare_id(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    chosen = [("gemini-free", GEMINI_MODELS[0]), ("openai", "openai/gpt-5.1")]
    assert [c.row.id for c in chain.resolve("text", chosen, SHIPPED)] == ["openai"]


def test_the_same_pair_twice_is_asked_once_and_keeps_its_first_place():
    """Asked twice it would fail twice, double the latency of an exhausted chain, and appear twice
    in `attempts`."""
    chosen = [("gemini-free", GEMINI_MODELS[1]), "openai", ("gemini-free", GEMINI_MODELS[1])]
    assert [c.named for c in chain.resolve("text", chosen, SHIPPED)] == [
        ("gemini-free", GEMINI_MODELS[1]),
        ("openai", "openai/gpt-5.1"),
    ]


def test_walking_a_pinned_chain_asks_only_what_was_pinned():
    ask, tried = refusing()
    result = chain.walk("text", [("gemini-free", GEMINI_MODELS[1])], SHIPPED, ask, chain.stamped)
    assert tried == [("gemini-free", GEMINI_MODELS[1])]
    assert result.answer.attempts == (("gemini-free", GEMINI_MODELS[1]),)


def test_unconfigured_reads_the_stated_chain_when_it_is_written_as_pairs(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    with pytest.raises(ProviderRefused) as caught:
        chain.walk(
            "text",
            [("cloudflare", "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast")],
            SHIPPED,
            lambda c: pytest.fail("called"),
            chain.stamped,
        )
    assert caught.value.detail == "CLOUDFLARE_API_TOKEN is not set"



def test_the_exhausted_chain_says_why_each_pair_failed():
    """The last error alone cannot answer the question a retry loop has.

    "Is there anything to wait for?" is not the same question as "what went wrong last?". A chain
    whose final pair was rate limited but whose first three answered with the wrong shape is mostly
    a shape problem, and a caller that sleeps four minutes on it is sleeping for nothing.
    """
    ask, _ = refusing(
        unavailable("unusable"),
        unavailable("unusable"),
        unavailable("unusable"),
        unavailable("rate_limited"),
    )
    with pytest.raises(ChainExhausted) as caught:
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert caught.value.reasons[:3] == ("unusable", "unusable", "unusable")
    # One pair that time could cure is enough to make waiting worth it.
    assert caught.value.waited_on_nothing is False


def test_a_chain_that_only_ever_answered_badly_is_waiting_for_nothing():
    ask, _ = refusing(*[unavailable("unusable")] * len(DEFAULT_WALK))
    with pytest.raises(ChainExhausted) as caught:
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert caught.value.waited_on_nothing is True


# ── racing a silent pair ────────────────────────────────────────────────────
# With `hedge_after`, a pair silent past a healthy answer's time is not waited out to its timeout:
# the next is asked beside it and the first usable answer wins. Driven by events, not sleeps, so
# "slow" means "has not been released" and nothing depends on the machine's speed.


def released_when(gates):
    """An `ask` that holds each pair named in `gates` until its event is set, then runs `then`."""
    tried: list[tuple[str, str]] = []
    lock = __import__("threading").Lock()

    def ask(candidate):
        with lock:
            tried.append(candidate.named)
        gate = gates.get(candidate.named)
        if gate is not None:
            event, then = gate
            assert event.wait(10), "the test never released this pair"
            if isinstance(then, BaseException):
                raise then
        return answers(candidate)

    return ask, tried


def eventually(condition):
    import time

    for _ in range(500):
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_a_silent_pair_is_raced_and_the_first_answer_wins():
    import threading

    held = threading.Event()
    ask, tried = released_when({DEFAULT_WALK[0]: (held, None)})
    try:
        result = chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=0.01)
    finally:
        held.set()
    assert tried == DEFAULT_WALK[:2]
    assert result.answer.model == DEFAULT_WALK[1][1]
    assert result.answer.attempts == tuple(DEFAULT_WALK[:2])


def test_a_pair_that_answers_in_time_is_never_raced():
    ask, tried = refusing()
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=60)
    assert tried == DEFAULT_WALK[:1]
    assert result.answer.attempts == tuple(DEFAULT_WALK[:1])


def test_a_fast_failure_starts_the_next_pair_without_waiting_for_the_hedge():
    import time

    ask, tried = refusing(unavailable("unavailable"))
    started = time.monotonic()
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=60)
    assert time.monotonic() - started < 5
    assert tried == DEFAULT_WALK[:2]
    assert result.answer.passed_over == ((*DEFAULT_WALK[0], "unavailable"),)


def test_a_terminal_refusal_still_stops_a_race():
    ask, tried = refusing(refused())
    with pytest.raises(ProviderRefused):
        chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=60)
    assert tried == DEFAULT_WALK[:1]


def test_a_race_that_nobody_wins_is_exhausted_like_a_walk():
    ask, tried = refusing(*[unavailable("rate_limited")] * len(DEFAULT_WALK))
    with pytest.raises(ChainExhausted) as caught:
        chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=0.01)
    assert sorted(caught.value.attempts) == sorted(DEFAULT_WALK)
    assert sorted(tried) == sorted(DEFAULT_WALK)


def test_a_loser_that_fails_later_is_rested_and_changes_nothing_returned():
    import threading

    held = threading.Event()
    ask, _ = released_when({DEFAULT_WALK[0]: (held, unavailable("rate_limited"))})
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=0.01)
    assert not rests.resting(DEFAULT_WALK[0])
    held.set()
    assert eventually(lambda: rests.resting(DEFAULT_WALK[0]))
    assert result.answer.model == DEFAULT_WALK[1][1]


def test_a_loser_that_answers_later_is_not_demoted_for_being_slow():
    import threading

    held = threading.Event()
    ask, _ = released_when({DEFAULT_WALK[0]: (held, None)})
    chain.walk("text", None, SHIPPED, ask, chain.stamped, hedge_after=0.01)
    held.set()
    assert not rests.resting(DEFAULT_WALK[0])
    assert rests.ready([DEFAULT_WALK[0], DEFAULT_WALK[1]]) == (DEFAULT_WALK[0], DEFAULT_WALK[1])
