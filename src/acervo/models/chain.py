"""A chain of (provider, model) pairs, walked in order.

It falls through on 429 and 5xx and never on anything else. That rule is the locked one and it is
the whole of this module's judgement: an authentication failure or a rejected configuration is a
mistake to fix, not a condition to route around, and falling through on it hides the mistake and
spends money at the next provider.

**The unit is a pair, not a provider.** A free tier is metered per model, so two models with 500
requests a day each are a thousand requests a day and the second is reached by the first one's 429.
The default walk is therefore provider by provider in the order they were added and, inside each,
model by model in the order they were added.

A refusal is also remembered, in `cooldown.py`: a pair that has just been rate limited goes to
the back of the queue for a while, so an exhausted free tier is not re-probed on every entry. It is
only ever an ordering hint — when every pair is resting the hints are ignored and the chain is
walked as written, which is what makes recovery automatic without knowing anyone's reset hour.

**A caller with somebody waiting may race.** Given `hedge_after`, a pair that has been silent for
longer than a healthy answer takes is not waited out to its timeout: the next pair is asked beside
it and the first usable answer wins. Measured against the free Gemini tier, the same model that
answers a resolve in 0.8 s sometimes takes 23 s, and a connection that never opens costs the whole
bound — two failures the walk used to serve in sequence, one after another, to a person watching a
spinner. Everything else about the walk holds: at most two pairs are in flight, a retryable failure
starts the next pair, a terminal one still stops, and the answer names the pair that answered.

The other contract here is provenance. `Answer.provider_id` and `Answer.model` name the pair that
*answered*, and `attempts` names every pair tried, oldest first. A fall-through that left `modelId`
naming the first choice would be a bug, so the answer is rewritten as it comes back out rather than
assembled by the caller from what it asked for.
"""

from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from typing import Callable, Sequence, TypeVar

from acervo.models import journal
from acervo.models.providers import Provider as Row, Providers
from acervo.models.cooldown import rests, retry_after_of
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable

Result = TypeVar("Result")

Choice = str | tuple[str, str]
"""One entry in a chain: a whole row, or one of its models.

A bare id is shorthand for "this provider, every model it offers for this kind, in the order they
were added" — the shape a laptop tool's `--image-chain` flag takes. A pair is "this provider, exactly
this model" — the shape the owner's record stores, because a free tier is metered per model and the
owner is choosing buckets rather than vendors.

A widening rather than an overload: an id names a *group* of pairs, not a second kind of thing.
`Candidate.named` and `Answer.attempts` are already this tuple, so a stored choice and a recorded
attempt are the same shape and can be compared without a mapping layer.
"""


@dataclass(frozen=True)
class Candidate:
    """One thing that can be asked: a provider and one of its models for a kind."""

    row: Row
    model: str

    @property
    def named(self) -> tuple[str, str]:
        return (self.row.id, self.model)


def _named(choice: Choice) -> tuple[str, str | None]:
    """A choice as (provider id, model or None). None means "every model this provider offers"."""
    return (choice, None) if isinstance(choice, str) else (choice[0], choice[1])


def resolve(
    kind: str, chosen: Sequence[Choice] | None, catalogue: Providers, *, expressive: bool = False,
) -> tuple[Candidate, ...]:
    """The pairs that will be tried, in order.

    `None` means nothing has been chosen: every provider that can be asked and serves this kind, in
    the order they were added, each one's models in the order they were added — so a server with one
    provider needs no order at all. `expressive` keeps only the voices that take a direction, which
    is what the expressive order exists to carry.

    An **empty** sequence is not the same thing. It means every model was switched off deliberately,
    and it resolves to nothing at all. The distinction is the whole reason this takes a `Sequence |
    None` rather than a list: "I have not chosen" and "I choose none" look identical in a list and
    mean opposite things, and conflating them made unticking the last model silently fall back to
    the server's order.

    Otherwise, exactly the choices given, in that order.

    **A model the provider does not offer is refused; a provider that cannot be asked is skipped.**
    The line is whether the state is legitimate. A missing or refused key is expected — ordering
    three providers when one of them has no key is the entire point of a chain. A pair naming a
    model nobody offers is a state nothing is supposed to produce, because removing a model or a
    provider removes it from every order, and skipping it would quietly walk half the chain the
    owner configured, forever, with no symptom.
    """
    if chosen is None:
        return tuple(
            Candidate(row, model)
            for row in catalogue.serving(kind)
            if row.available
            for model in row.models_for(kind)
            if not expressive or row.takes_direction(model)
        )

    found: list[Candidate] = []
    for choice in chosen:
        identifier, model = _named(choice)
        try:
            row = catalogue.find(identifier)
        except KeyError:
            raise ProviderRefused(
                "configuration", f"there is no provider called {identifier!r}"
            ) from None
        if not row.serves(kind):
            raise ProviderRefused("configuration", f"provider {identifier!r} does not serve {kind}")
        offered = row.models_for(kind)
        # Before the credential check, deliberately: otherwise the same stored record is a refusal
        # on a server holding the key and a silent skip on one that does not, so the error would
        # depend on the environment rather than on the record.
        if model is not None and model not in offered:
            raise ProviderRefused(
                "configuration", f"provider {identifier!r} does not offer {model!r} for {kind}"
            )
        if not row.available:
            continue
        found.extend(Candidate(row, one) for one in ((model,) if model else offered))
    # A pair named twice would fail twice, double the latency of an exhausted chain and appear twice
    # in `attempts`. First occurrence wins, so the owner's order is untouched.
    return tuple({candidate.named: candidate for candidate in found}.values())


def unconfigured(
    kind: str, chosen: Sequence[Choice] | None, catalogue: Providers
) -> ProviderRefused:
    """Why nothing can serve this kind: what is missing, and never a value.

    It reports the *first* provider that would have served, so the message is about the one the
    server is closest to being able to ask.
    """
    if chosen is not None and not chosen:
        return ProviderRefused("unconfigured", f"no model is switched on for {kind}")
    rows = (
        [catalogue.find(_named(choice)[0]) for choice in chosen]
        if chosen
        else list(catalogue.serving(kind))
    )
    detail = next(
        (row.reason() for row in rows if row.reason() is not None),
        f"no provider is added for {_KIND_NAMES.get(kind, kind)}",
    )
    return ProviderRefused("unconfigured", detail or "")


_KIND_NAMES = {"text": "text", "image": "pictures", "audio": "voices", "ocr": "reading photos"}


def walk(
    kind: str,
    chosen: Sequence[Choice] | None,
    catalogue: Providers,
    ask: Callable[[Candidate], Result],
    stamp: Callable[[Result, tuple[tuple[str, str], ...], tuple[tuple[str, str, str], ...]], Result],
    caller: str = "text",
    hedge_after: float | None = None,
) -> Result:
    """Ask each pair in turn until one answers.

    `stamp` writes the attempt list into whatever `ask` returned, because only this function knows
    how many pairs were tried and only the caller knows the shape of its own result.

    `caller` names the job for the journal — "brief", "clips", "capture". This is the one place that
    sees every attempt and its outcome, so it is the one place worth writing them down from; without
    it a chain that walked nine pairs left no trace but a `passedOver` array in a reply that may
    never have come.

    `hedge_after`, when given, is how long a pair may stay silent before the next one is asked
    beside it. `ask` is then called from worker threads, so it must not hold anything tied to the
    calling thread.
    """
    candidates = resolve(kind, chosen, catalogue)
    if not candidates:
        raise unconfigured(kind, chosen, catalogue)

    # Rested pairs go last rather than away: `ready` hands back everything when everything is
    # resting, so a remembered refusal can never empty a chain that has members.
    awake = rests.ready([candidate.named for candidate in candidates])
    order = sorted(candidates, key=lambda candidate: candidate.named not in awake)

    walked = _Walk(caller)
    if hedge_after is None:
        for candidate in order:
            walked.attempts.append(candidate.named)
            started = time.monotonic()
            try:
                result = ask(candidate)
            except ProviderUnavailable as error:
                walked.failed(candidate, error, started)
            else:
                return walked.answered(candidate, result, started, stamp)
        walked.exhaust()

    return _raced(order, ask, stamp, walked, hedge_after)


IN_FLIGHT = 2
"""Pairs asked at once in a race. Two covers one slow model; more would spend quota to cover two."""


class _Walk:
    """What one walk has tried, what passed it over, and the journal lines for both."""

    def __init__(self, caller: str) -> None:
        self.caller = caller
        self.attempts: list[tuple[str, str]] = []
        self.passed_over: list[tuple[str, str, str]] = []
        self.labels: dict[str, str] = {}
        self.last: ProviderUnavailable | None = None

    def failed(self, candidate: Candidate, error: ProviderUnavailable, started: float) -> None:
        self.labels[candidate.row.id] = candidate.row.label
        rests.note(candidate.named, error.reason, retry_after=retry_after_of(error))
        self.passed_over.append((*candidate.named, error.reason))
        journal.passed(self.caller, *candidate.named, error.reason, str(error), time.monotonic() - started)
        self.last = error

    def answered(self, candidate: Candidate, result: Result, started: float, stamp) -> Result:
        rests.succeeded(candidate.named)
        journal.answered(self.caller, *candidate.named, time.monotonic() - started)
        return stamp(result, tuple(self.attempts), tuple(self.passed_over))

    def exhaust(self) -> None:
        assert self.last is not None
        reasons = tuple(reason for _, _, reason in self.passed_over)
        journal.exhausted(self.caller, len(self.attempts), reasons)
        raise ChainExhausted(tuple(self.attempts), self.last, reasons, tuple(self.passed_over),
                             self.labels)


def _raced(
    order: Sequence[Candidate],
    ask: Callable[[Candidate], Result],
    stamp,
    walked: _Walk,
    hedge_after: float,
) -> Result:
    waiting = list(order)
    running: dict[Future, tuple[Candidate, float]] = {}
    pool = ThreadPoolExecutor(max_workers=IN_FLIGHT, thread_name_prefix=f"chain-{walked.caller}")

    def start() -> None:
        candidate = waiting.pop(0)
        walked.attempts.append(candidate.named)
        running[pool.submit(ask, candidate)] = (candidate, time.monotonic())

    try:
        start()
        while running:
            patience = None
            if waiting and len(running) < IN_FLIGHT:
                newest = max(started for _, started in running.values())
                patience = max(0.0, newest + hedge_after - time.monotonic())
            done, _ = wait(running, timeout=patience, return_when=FIRST_COMPLETED)
            if not done:
                start()
                continue
            for future in done:
                candidate, started = running.pop(future)
                try:
                    result = future.result()
                except ProviderUnavailable as error:
                    walked.failed(candidate, error, started)
                    continue
                except BaseException:
                    _abandon(running, walked.caller)
                    raise
                _abandon(running, walked.caller)
                return walked.answered(candidate, result, started, stamp)
            if waiting and not running:
                start()
        walked.exhaust()
        raise AssertionError("unreachable")  # exhaust always raises
    finally:
        # Never wait: a LiteLLM call cannot be cancelled, and the loser finishes on its own bound.
        pool.shutdown(wait=False)


def _abandon(running: dict[Future, tuple[Candidate, float]], caller: str) -> None:
    """Let the losers finish in the background. What they say later is noted, never returned."""
    for future, (candidate, started) in running.items():
        def settle(done: Future, candidate: Candidate = candidate, started: float = started) -> None:
            seconds = time.monotonic() - started
            error = done.exception()
            if error is None:
                journal.late(caller, *candidate.named, "ok", seconds)
                return
            reason = getattr(error, "reason", type(error).__name__)
            if isinstance(error, ProviderUnavailable):
                rests.note(candidate.named, error.reason, retry_after=retry_after_of(error))
            journal.late(caller, *candidate.named, str(reason), seconds)

        future.add_done_callback(settle)
    running.clear()


def stamped(
    result,
    attempts: tuple[tuple[str, str], ...],
    passed_over: tuple[tuple[str, str, str], ...] = (),
):
    """Rewrite a result's answer with what was tried, and what was passed over on the way.

    The provenance contract, applied — and the passed-over list is what lets a caller say a
    fall-through happened at all. Without it, a provider that is quietly broken is indistinguishable
    from one nobody chose.
    """
    return replace(
        result, answer=replace(result.answer, attempts=attempts, passed_over=passed_over)
    )
