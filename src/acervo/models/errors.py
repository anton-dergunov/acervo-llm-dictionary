"""What went wrong, in a vocabulary that knows nothing about Acervo's wire.

The split matters and is the plan's acceptance boundary. This package decides *what kind of thing*
went wrong — a closed seven-value `Reason`. `acervo.services.models` decides what Acervo's API calls
that, because `llm_rate_limited` and its siblings carry Acervo's HTTP statuses and prose written for
the owner, and shipping those into a package meant to stand alone would defeat the point.

The division that carries the locked fall-through rule is between the two exception classes, not
between reasons: `ProviderUnavailable` is retried at the next row, `ProviderRefused` never is. An
authentication failure or a rejected configuration is a mistake to fix, not a condition to route
around; falling through on it hides the mistake and spends money elsewhere.

`unusable` and `empty` are the two reasons a *caller* raises rather than `classify`, and it is retryable for the
same argument the rule rests on. A model that answers with the wrong shape has not revealed a
mistake in the deployment — it has revealed that this model cannot do this job, which is exactly
what a chain of alternatives is for. It is also the only failure the owner can do nothing about: a
key can be rotated and a project can be fixed, but "this model does not follow a schema" is a fact
about the model. Falling through records the pair in `passed_over` like any other, so nothing is
hidden; refusing outright meant a weaker head of the chain made every stronger row behind it
unreachable.
"""

from __future__ import annotations

from typing import Literal

Reason = Literal[
    "unconfigured",    # no provider in the chain can be asked
    "authentication",  # 401, 403 — the credential was rejected
    "configuration",   # 400, 404, an unknown provider, one that cannot serve this kind
    "refused",         # any other terminal answer, including one with no status at all
    "rate_limited",    # 429
    "unavailable",     # 5xx
    "unreachable",     # a timeout or a connection failure
    "unusable",        # it answered, and the answer was not the shape the caller asked for
    "empty",           # it answered with nothing at all
]

TERMINAL: frozenset[str] = frozenset({"unconfigured", "authentication", "configuration", "refused"})
RETRYABLE: frozenset[str] = frozenset({
    "rate_limited", "unavailable", "unreachable", "unusable", "empty"
})
# Retryable at the next *pair*, but never worth waiting for: the two reasons that say something
# about a model rather than about a moment. `TRANSIENT` is the rest of `RETRYABLE` — a quota that
# refills, a service that comes back, a connection that can be made again — and only those are
# worth sleeping on.
SHAPE: frozenset[str] = frozenset({"unusable", "empty"})
TRANSIENT: frozenset[str] = RETRYABLE - SHAPE

# How many times a whole chain of malformed answers is worth asking again. Two, because the only
# thing a retry can change here is the sample: the prompt, the schema and the models are identical,
# so a second draw is worth having and a third says the same thing as the second. Kept beside the
# taxonomy because both callers that retry want the same number for the same reason.
SHAPE_TRIES = 2


def _clean(detail: str) -> str:
    """`detail`, with every credential any provider was built with taken out of it.

    Imported inside the function: `errors.py` is the bottom of this package.
    """
    if not detail:
        return detail
    from acervo.models.redact import redact

    return redact(detail)


class ProviderError(Exception):
    """A provider did not answer, and why.

    `detail` is redacted at construction rather than at logging: a message that is only cleaned on
    its way to a log has a path that skips the cleaning, and provider errors routinely echo the
    request — including the key — back at you. This repository is public.

    It is redacted **here**, and that is a correction rather than a restatement. This is what the
    docstring always claimed, but the cleaning actually lived in `call.py` on the way in — so it
    covered errors classified from a provider's response and nothing else. Every error a *caller*
    raises by hand went through unwashed, which was harmless while nobody wrote them down and stopped
    being harmless the moment `journal.py` did. Against every credential any provider was built with
    rather than one provider's, because the error does not reliably know whose call it was.
    """

    reason: Reason

    def __init__(
        self,
        reason: Reason,
        detail: str,
        *,
        provider_id: str | None = None,
        model: str | None = None,
        status: int | None = None,
    ) -> None:
        detail = _clean(detail)
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.provider_id = provider_id
        self.model = model
        self.status = status


class ProviderRefused(ProviderError):
    """Terminal for this row and for the chain: auth, a bad request, an unknown model.

    Never fallen through — it is a mistake to fix, not a condition to route around.
    """


class ProviderUnavailable(ProviderError):
    """Retryable at the next row: 429, 5xx, a timeout, a connection failure."""


class ChainExhausted(Exception):
    """Every (provider, model) pair was unavailable.

    Carries the last error because that is the actionable one, and because it is what preserves the
    retry contract: a chain whose final row was rate limited must still be reported as rate
    limiting, or the file ingestion stops retrying something it should retry.

    It also carries **why each pair failed**, which the last error alone cannot say. A caller
    deciding whether to try again needs to know whether it is waiting for anything: a rate limit or
    a 5xx passes with time, and a malformed answer does not, so backing off from one is a strategy
    and backing off from the other is only delay. `walk` has always had these reasons to hand.
    """

    def __init__(self, attempts: tuple[tuple[str, str], ...], last: ProviderUnavailable,
                 reasons: tuple[str, ...] = (),
                 passed_over: tuple[tuple[str, str, str], ...] = (),
                 labels: dict[str, str] | None = None) -> None:
        listed = ", ".join(f"{provider} {model}" for provider, model in attempts)
        super().__init__(f"every provider was unavailable: {listed}")
        self.attempts = attempts
        self.last = last
        self.reasons = reasons or (last.reason,)
        # (provider, model, reason) for every pair that did not answer, so the owner can be told
        # *which* of their models refused and why — "Gemini is overloaded, Cloudflare is out of
        # allowance" — rather than only the last one's reason as though it were the whole story.
        self.passed_over = passed_over or ((last.provider_id or "", last.model or "", last.reason),)
        # The name the owner knows each provider by, so a sentence about them needs nothing else.
        self.labels = dict(labels or {})

    @property
    def waited_on_nothing(self) -> bool:
        """True when no failure here is one that time can cure.

        The question a retry loop actually has. Every pair answering with the wrong shape is a fact
        about those models; sleeping four minutes and asking them again changes nothing.
        """
        return bool(self.reasons) and all(reason in SHAPE for reason in self.reasons)
