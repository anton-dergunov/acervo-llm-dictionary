"""Acervo's binding to the provider package: the server's providers in, `llm_*` error codes out.

Not to be confused with `acervo.models`, which is the provider package itself and knows nothing
about Acervo. This module is the other half of that split, and the split is deliberate:

- `acervo.models` decides **what kind of thing went wrong** — a closed seven-value `Reason`.
- This module decides **what Acervo's API calls that** — the table below.

`llm_rate_limited` and its siblings carry Acervo's HTTP statuses and prose written for the owner, so
they do not belong in a package meant to stand alone; conversely, "429 means try the next one" is
provider knowledge and does not belong in every caller. The table is the seam.

**The mapping is a contract, not an implementation detail.** `scripts/ingest_vocabulary_file.py`
retries on exactly `llm_rate_limited`, `llm_unavailable` and `llm_unreachable`. A change here
changes the retry behaviour without changing a line of the retry code.

`refusal()` is public for the same reason: `services/images.py` binds the *same* provider package
and must speak the *same* codes, so a picture that could not be drawn and an entry that could not be
written fail alike. A second mapping would be a second contract.

The call journal is bound here for the same reason it is mapped here. `acervo.models.journal` writes
to a logger and stops, because the package may not read `Settings`; this module knows where the
deployment keeps its files, so this module is where the handler is attached.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from typing import Any, Callable, Mapping

from acervo import logfiles
from acervo.errors import ApiError
from acervo.models import Answer, ChainExhausted, ProviderError, Providers, TextResult, chain, journal
from acervo.models.errors import ProviderUnavailable
from acervo.models.families import EXPRESSIVE_CHAIN
from acervo.models import call as provider
from acervo.repository import model_selection
from acervo.services import providers as stored_providers
from acervo.services.providers import ORDER_KINDS
from acervo.settings import Settings

KINDS = tuple(ORDER_KINDS)

# Which kind each order draws its pairs from (`services/providers.ORDER_KINDS`). Two orders share
# `audio` because they are two answers to one question asked twice: what should read a headword,
# which wants a clear free voice held stable, and what should read an example, which wants a voice
# that can take the sentence's emotion. `quick` shares `text` for the same reason: it is the look-up
# a photo tap makes while a finger is still on the glass, and measured in `experiments/photo-capture/`
# a flash-lite model answered in 1.02 s at the median and the strongest text model took 4.4.


def catalogue_kind(kind: str) -> str:
    """The kind a provider offers that this order draws on."""
    return ORDER_KINDS.get(kind, kind)


def load(settings: Settings) -> Providers:
    """The server's providers, read now. Never cached: see `services/providers.load`."""
    return stored_providers.load(settings)

# reason -> (status, code, what the owner is told). Total over `acervo.models.Reason`; the test that
# pairs every reason with a row here is what stops an eighth reason arriving unmapped.
REFUSALS: dict[str, tuple[int, str, str]] = {
    "unconfigured": (
        503,
        "capture_unavailable",
        "This Acervo server has no language model configured, so it cannot build entries.",
    ),
    "authentication": (
        503,
        "llm_authentication",
        "The language model credential was rejected, so nothing was created.",
    ),
    "configuration": (
        503,
        "llm_configuration",
        "The language model configuration was rejected, so nothing was created.",
    ),
    "rate_limited": (
        503,
        "llm_rate_limited",
        "The language model is temporarily rate limited, so nothing was created.",
    ),
    "unavailable": (
        503,
        "llm_unavailable",
        "The language model is temporarily unavailable, so nothing was created.",
    ),
    "unreachable": (
        502,
        "llm_unreachable",
        "The language model could not be reached, so nothing was created.",
    ),
    "refused": (502, "llm_failed", "The language model refused the request, so nothing was created."),
    # Every pair answered with nothing at all.
    "empty": (
        502,
        "llm_empty",
        "The language model returned nothing, so nothing was created.",
    ),
    # Every pair in the chain answered, and none of them answered in the shape that was asked for.
    "unusable": (
        502,
        "llm_unusable",
        "The language model did not return a usable answer, so nothing was created.",
    ),
}


def chain_for(
    settings: Settings, owner: str | None, kind: str = "text"
) -> list[chain.Choice] | None:
    """The chain this request walks: the owner's order, or None for the providers' own order.

    Read per call and never cached — that is what makes a change in Settings ▸ Providers take effect
    on the next capture with nothing restarted. It is one indexed read against a local SQLite file.

    Three answers, not two. A list is an order to walk — and an **empty** one means every model was
    switched off on purpose. `None` means nobody has chosen, and the providers are walked in the
    order they were added.
    """
    if owner is not None:
        stored = model_selection.chains(owner)
        if kind in stored:
            # Including an empty one: switching every model off is a choice.
            return list(stored[kind])
    return None


def speech_chain(
    settings: Settings, owner: str | None, kind: str
) -> tuple[list[chain.Choice] | None, list[str]]:
    """A speech order as far as the providers still offer it, and the pairs that were left out.

    **A pair no provider offers for speech is left out rather than refused.** A saved order is a
    preference, and the voices behind a stale pair in the same order can still read the words.
    Removing a provider or a model takes it out of every order, so this should find nothing; it is
    the readout below and the walk agreeing about the same order that matters.

    An order left with nothing reads as though none had been chosen. One the owner saved empty is
    still every voice switched off.
    """
    chosen = chain_for(settings, owner, kind)
    if not chosen:
        return chosen, []
    catalogue = load(settings)
    offered: list[chain.Choice] = []
    skipped: list[str] = []
    for choice in chosen:
        identifier, model = (choice, None) if isinstance(choice, str) else choice
        try:
            row = catalogue.find(identifier)
        except KeyError:
            row = None
        if row is None or not row.serves("audio") or (model and model not in row.models_for("audio")):
            skipped.append(f"{identifier}:{model or '*'}")
            continue
        offered.append(choice)
    return offered or None, skipped


def chain_readout(settings: Settings, owner: str | None, kind: str = "text") -> dict[str, Any]:
    """Which pair would be asked first for this kind, and why none can be.

    One producer, two readers: `/health` and `GET /models` both answer "can this build entries", and
    two separate computations of that would drift. Never a key, an endpoint or a project id.

    `reason` exists because a bare "capture is unavailable" is what let a real outage stay invisible:
    false could equally mean no provider, no key, a refused key or a missing setting, and nobody
    could tell which. It names what is missing and never a value — health serves it unauthenticated.

    `provider` and `model` name the pair that would be asked *first*. Which pair actually answers is
    only known after a call, and that is what lands in `modelId`.
    """
    catalogue = load(settings)
    if catalogue_kind(kind) == "audio":
        chosen, _ = speech_chain(settings, owner, kind)
    else:
        chosen = chain_for(settings, owner, kind)
    try:
        candidates = chain.resolve(catalogue_kind(kind), chosen, catalogue,
                                   expressive=kind == EXPRESSIVE_CHAIN)
    except ProviderError as error:
        return {"available": False, "provider": None, "model": None, "reason": error.detail}
    if not candidates:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "reason": chain.unconfigured(catalogue_kind(kind), chosen, catalogue).detail,
        }
    return {
        "available": True,
        "provider": candidates[0].row.id,
        "model": candidates[0].model,
        "reason": None,
    }


def capture_health(settings: Settings) -> dict[str, Any]:
    """What `/health` says about capture — this *server's* answer, deliberately owner-independent.

    `/health` is the container's liveness probe and the readout shown before anyone signs in, so it
    has no owner to read and must not grow one: an unauthenticated body that varied by caller would
    be wrong behind any cache and would put owner state on an open route. What the *owner's* chain
    will do is `GET /models`, which is also where the provider line moved to in Settings.
    """
    return chain_readout(settings, None, "text")


class Unusable(ValueError):
    """A caller's check refusing one model's answer: that pair is passed over and the next is asked.

    `str()` is the sentence the call log keeps — "the glosses are in Latin script, and the vocabulary
    glosses into Russian first" — and it never reaches the owner. `refusal` is what the owner reads
    when *every* pair failed a check and the last one failed this one: the refusal the caller would
    have raised had there been no chain, so a capture that cannot be built says why in the words it
    always used, rather than a generic "the model did not answer usably".
    """

    def __init__(self, sentence: str, refusal: ApiError | None = None) -> None:
        super().__init__(sentence)
        self.refusal = refusal


class Demoted(Unusable):
    """A caller's check doubting one model's answer, not refusing it: the pair is passed over, and
    the answer is kept aside in case no pair does better.

    For a judgement that can be wrong about a right answer — a dictionary disagreeing with a model
    (`services/capture/vet.py`) is right far more often than not, but not always. So a disagreement
    asks the next pair, and if every pair is passed over and at least one was only demoted, the first
    of those in chain order is what `llm_json` returns, rather than a capture refused over a doubt.
    `checked` is what the check would have returned had it passed; `by` names the check, for the
    `kept=` field of the outcome line.
    """

    def __init__(self, sentence: str, checked: Any, by: str) -> None:
        super().__init__(sentence)
        self.checked = checked
        self.by = by


def llm_json(settings: Settings, owner: str | None, system: str, user: str,
             caller: str = "text", hedge_after: float | None = None,
             params: Mapping[str, Any] | None = None, kind: str = "text",
             timeout: float | None = None,
             check: Callable[[Any], Any] | None = None) -> tuple[Any, Answer]:
    """One constrained call: pass text, get JSON and the model that produced it, or a code saying why not.

    Returning the `Answer` rather than a model id is not decoration. The locked contract is that the
    entry records the model that *answered*, which under a chain is not knowable before the call —
    and the answer also carries who was passed over on the way, which is the only record that a
    fall-through happened at all.

    `owner` is required and has no default, so an omitted argument is a loud `TypeError` at the call
    site rather than a silent fall back to the deployment default. It is an owner id and never a
    chain: a caller that could assert a chain of its own would be the "an iOS Shortcut must not pick
    a model" non-goal reappearing one layer down.

    `caller` names the job in the call journal, and it is worth passing. Three different jobs come
    through here, and a log that calls all of them "text" cannot answer the first question anybody
    asks of it — which of them was slow.

    `hedge_after` is for a caller with somebody waiting: see `chain.walk`.

    `params` is what this task wants of the generation — a story hot, its translation cold. It is
    passed straight through to `call.text`, where the row's own settings still win; see there.

    `kind` is which chain is walked, and only text-drawing chains make sense here: `text`, or the
    `quick` order a photo tap asks. `timeout` bounds each pair when the caller has a tighter budget
    than a whole article's.

    `check` judges the parsed reply **inside** the walk, so a model whose answer fails it is passed
    over and the next pair answers, exactly as a reply that is not JSON is. It is called once per
    pair on that pair's own reply (raced pairs each check their own, so it must be pure), raises
    `ValueError` — `Unusable` to carry a refusal for the owner — to pass the pair over, and returns
    what `llm_json` returns in place of the parsed reply: a check may hand back a corrected answer
    and a note of what it corrected. A check that raises `Demoted` passes the pair over too, but its
    answer is kept: when every pair is passed over, the first demoted one in chain order is returned
    and the outcome line says `kept=`.
    """
    # (pair, the result as checked, the sentence, the check's name) for every demoted answer. Raced
    # pairs call `ask` from worker threads, hence the lock.
    demoted: list[tuple[tuple[str, str], TextResult, str, str]] = []
    holding = threading.Lock()

    def ask(candidate: chain.Candidate) -> TextResult:
        result = provider.text(
            user, row=candidate.row, model=candidate.model, system=system, as_json=True,
            params=params, **({"timeout": timeout} if timeout is not None else {}),
        )
        # Checked *here*, inside the chain's own callback, rather than after `walk` returns. An
        # answer in the wrong shape used to end the whole chain, so a weak model at the head made
        # every stronger row behind it unreachable — which is the opposite of what an order is for.
        if not result.text.strip():
            raise ProviderUnavailable(
                "empty", "the model returned nothing",
                provider_id=candidate.row.id, model=candidate.model,
            )
        if result.parsed is None:
            raise ProviderUnavailable(
                "unusable", "the model did not answer with JSON: " + journal.excerpt(result.text),
                provider_id=candidate.row.id, model=candidate.model,
            )
        if check is None:
            return result
        try:
            checked = check(result.parsed)
        except Demoted as doubted:
            with holding:
                demoted.append((candidate.named, replace(result, parsed=doubted.checked), str(doubted),
                                doubted.by))
            raise ProviderUnavailable(
                "unusable", str(doubted), provider_id=candidate.row.id, model=candidate.model,
            ) from doubted
        except ValueError as unusable:
            # `from unusable`, not `from None`: the cause is how the walk's last failure still knows,
            # after the walk, which refusal the owner should read.
            raise ProviderUnavailable(
                "unusable", str(unusable), provider_id=candidate.row.id, model=candidate.model,
            ) from unusable
        return replace(result, parsed=checked)

    try:
        result: TextResult = chain.walk(
            catalogue_kind(kind), chain_for(settings, owner, kind), load(settings), ask,
            chain.stamped, caller=caller, hedge_after=hedge_after,
        )
    except ChainExhausted as exhausted:
        if demoted:
            return _kept(caller, exhausted, demoted)
        cause = exhausted.last.__cause__
        if isinstance(cause, Unusable) and cause.refusal is not None:
            # The last pair failed the caller's own check, so the owner reads the caller's sentence;
            # a 429 at the last pair still reads as one, which is what the retry contract needs.
            refused = cause.refusal
            raise ApiError(refused.status, refused.code, refused.message, refused.waiting_on,
                           {**refused.noted, "detail": str(cause),
                            "passedOver": waiting_on(exhausted)}) from None
        raise refusal(exhausted, kind) from None
    except ProviderError as error:
        raise refusal(error, kind) from None

    assert result.parsed is not None  # `ask` refuses anything else, so the chain cannot return one
    return result.parsed, result.answer


def _kept(caller: str, exhausted: ChainExhausted,
          demoted: list[tuple[tuple[str, str], TextResult, str, str]]) -> tuple[Any, Answer]:
    """The first demoted answer in chain order, stamped as the answer, with its outcome line.

    Chain order rather than the order the answers arrived in, so a raced walk keeps what a sequential
    one would have. Every other pair stays in `passed_over`, so the entry's provenance still says a
    fall-through happened.
    """
    order = {pair: index for index, pair in enumerate(exhausted.attempts)}
    pair, result, sentence, by = min(demoted, key=lambda item: order.get(item[0], len(order)))
    others = tuple(item for item in exhausted.passed_over if (item[0], item[1]) != pair)
    result = chain.stamped(result, exhausted.attempts, others)
    journal.outcome(caller, kept=by, pair=f"{pair[0]}:{pair[1]}", detail=sentence)
    assert result.parsed is not None
    return result.parsed, result.answer


def llm_text(settings: Settings, owner: str, user: str, caller: str = "text",
             params: Mapping[str, Any] | None = None, timeout: float | None = None,
             ) -> tuple[str, Answer]:
    """One call for **text**, with no JSON asked of it: the words, and the model that wrote them.

    For a caller that reads the reply itself — the loop generator's writer, whose parser is in the
    other repository and deliberately reads a plain reply rather than a JSON-mode one. An empty reply
    passes to the next pair, as it does in `llm_json`; anything else is the caller's to judge.
    """
    def ask(candidate: chain.Candidate) -> TextResult:
        result = provider.text(
            user, row=candidate.row, model=candidate.model, params=params,
            **({"timeout": timeout} if timeout is not None else {}),
        )
        if not result.text.strip():
            raise ProviderUnavailable(
                "empty", "the model returned nothing",
                provider_id=candidate.row.id, model=candidate.model,
            )
        return result

    try:
        result: TextResult = chain.walk(
            catalogue_kind("text"), chain_for(settings, owner, "text"), load(settings), ask,
            chain.stamped, caller=caller,
        )
    except ChainExhausted as exhausted:
        raise refusal(exhausted, "text") from None
    except ProviderError as error:
        raise refusal(error, "text") from None
    return result.text, result.answer


# The callers a companion may name in the call log, and how long each pair may take. The clip
# service's two stages are a translation and a word alignment of one clip: a whole answer, not a
# quick one, and the sixty seconds its own chain always had.
COMPANION_CALLERS = ("clip-translate", "clip-align")
COMPANION_TIMEOUT_SECONDS = 60


def companion_text(settings: Settings, body: Mapping[str, Any]) -> dict[str, Any]:
    """One JSON call for a companion service, on the providers' own order.

    No owner: the call comes from the clip service's own job rather than from anybody's request, and
    walking the providers in the order they were added is what its text order always was. The shape
    is the caller's to state in the instructions, and the answer is held to being JSON here, inside
    the walk, so a model that cannot answer in JSON passes to the next one.
    """
    instructions = body.get("instructions")
    text = body.get("text")
    if not isinstance(instructions, str) or not instructions.strip() or not isinstance(text, str):
        raise ApiError(400, "invalid_input", "Send the instructions and the text.")
    caller = body.get("caller") if body.get("caller") in COMPANION_CALLERS else "companion"
    temperature = body.get("temperature")
    params = {"temperature": float(temperature)} if isinstance(temperature, (int, float)) \
        and not isinstance(temperature, bool) else None
    parsed, answer = llm_json(settings, None, instructions, text, caller=caller, params=params,
                              timeout=COMPANION_TIMEOUT_SECONDS)
    return {
        "payload": parsed,
        "provider": answer.provider_id,
        "model": answer.model,
        "seconds": round(answer.seconds, 3),
    }


# What each passing reason means to the owner, said of a provider. Ordered by how much it tells:
# when two of one provider's models refused differently, the first reason here is the one said.
WAITING_ON: dict[str, str] = {
    "rate_limited": "is out of allowance for now",
    "unavailable": "is overloaded",
    "unreachable": "is not answering",
    "unusable": "answered in a shape that could not be used",
    "empty": "answered with nothing",
}


def waiting_on(exhausted: ChainExhausted) -> str:
    """Every provider that refused, by the name the owner knows it by, and why, in chain order.

    One phrase a provider rather than a model, because two models of one free tier refusing alike is
    one fact. This exists because "the provider is busy" was the whole of what a story said while
    Gemini's free tier answered 503 and Cloudflare's daily allowance had run out — two causes that
    pass at very different speeds, and only one of which the owner could have done anything about.
    """
    order: list[str] = []
    reasons: dict[str, list[str]] = {}
    for named, _model, reason in exhausted.passed_over:
        if named not in reasons:
            order.append(named)
        reasons.setdefault(named, []).append(reason)
    phrases = []
    for named in order:
        label = exhausted.labels.get(named) or named or "A model"
        said = next((WAITING_ON[one] for one in WAITING_ON if one in reasons[named]),
                    "is unavailable")
        phrases.append(f"{label} {said}")
    return "; ".join(phrases)


def refusal(error: ProviderError | ChainExhausted, kind: str = "text") -> ApiError:
    """The same code for every caller, and prose that names what actually refused.

    The **code** is shared deliberately — a picture that could not be drawn and an entry that could
    not be written fail alike, and `scripts/ingest_vocabulary_file.py` retries on exactly three of
    them. The **sentence** is not the code, and saying "the language model is temporarily rate
    limited" over a drawing that an image model refused sent a real debugging session looking at the
    text chain. `kind` is what the chain was walked for, so the sentence can say so.

    Given a whole walk (`ChainExhausted`), the code is still its last pair's — which is what keeps
    the retry contract — and the sentence goes on to name every provider that refused, and why.
    """
    if isinstance(error, ChainExhausted):
        refused = refusal(error.last, kind)
        summary = waiting_on(error)
        if not summary:
            return refused
        return ApiError(refused.status, refused.code, f"{refused.message} {summary}.", summary,
                        refused.noted)
    status, code, message = REFUSALS[error.reason]
    if kind == "image":
        message = message.replace("The language model", "The image model")
    elif catalogue_kind(kind) == "audio":
        message = message.replace("The language model", "The speech model")
    elif kind == "ocr":
        message = message.replace("The language model", "The photo reader").replace(
            "so nothing was created", "so the photo was not read"
        )
    # "Unconfigured" is the one refusal whose *particular* cause the owner can act on, and it is
    # already safe to show: it names what is missing or says every model is switched off, never a
    # value. `/health` shows exactly this string.
    # What the provider package itself said — which pair, which field — goes to the log and never to
    # the owner. Without it a refusal was written down as its code alone, and "configuration" names
    # a dozen different mistakes. It is redacted where the error is made (`models/errors.py`).
    return ApiError(
        status, code, error.detail or message if error.reason == "unconfigured" else message,
        noted={"detail": error.detail} if error.detail else None,
    )


# ── what the owner is shown, and what they may choose ───────────────────────
# The providers as the interface sees them, and the one place a submitted chain is held to them. The
# repository stores what it is given and deliberately knows nothing about providers, so this is the
# only validator; `chain.resolve` checks the same things in the same order at walk time, and the two
# agreeing about which mistake is reported is what makes the refusal codes worth reading.


def _chain_view(settings: Settings, owner: str, kind: str, catalogue: Providers) -> dict[str, Any]:
    """One kind's chain: whose it is, what is in it, and why nothing in it can be asked.

    `pairs` is what is *stored*, not what will be walked. A pair whose provider cannot be asked keeps
    its place, so a refused key does not quietly destroy an ordering the owner chose;
    `providers[].available` is how the interface shows that pair will be skipped. With nothing
    stored, `pairs` is the providers' own order, which is what will be walked.
    """
    stored = model_selection.chains(owner)
    if kind in stored:
        pairs = [{"provider": provider, "model": model} for provider, model in stored[kind]]
        source = "owner"
    else:
        source = "default"
        pairs = [
            {"provider": candidate.row.id, "model": candidate.model}
            for candidate in chain.resolve(catalogue_kind(kind), None, catalogue,
                                           expressive=kind == EXPRESSIVE_CHAIN)
        ]
    return {"source": source, "reason": chain_readout(settings, owner, kind)["reason"], "pairs": pairs}


def catalogue_view(settings: Settings, owner: str) -> dict[str, Any]:
    """Everything Settings ▸ Providers renders: the families a provider can be added from, the
    providers, this owner's chains, and whether compose checks what they write."""
    catalogue = load(settings)
    return {
        "families": stored_providers.families_view(),
        "providers": [stored_providers.provider_view(row) for row in catalogue],
        "chains": {kind: _chain_view(settings, owner, kind, catalogue) for kind in KINDS},
        "checkAnswers": model_selection.check_answers(owner),
    }


def _submitted(kind: str, value: Any, catalogue: Providers) -> list[tuple[str, str]]:
    """One kind's submitted chain, checked against the providers.

    The order of checks matches `chain.resolve`'s, so the mistake reported here is the mistake that
    would be reported at capture time. There is deliberately no availability check: a chain is an
    owner preference and a working key is a fact about the provider, and refusing a pair whose key
    was refused would lock the owner out of reordering that kind at all. `chain.resolve` skips it
    when walking, and the interface marks it.
    """
    if not isinstance(value, list):
        raise ApiError(400, "invalid_input", f"The {kind} chain must be a list of providers.")
    # An empty list is allowed and means "switch this off". Refusing it left no way to say so.
    pairs: list[tuple[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ApiError(400, "invalid_input", f"Every {kind} entry needs a provider and a model.")
        identifier = str(entry.get("provider") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not identifier or not model:
            raise ApiError(400, "invalid_input", f"Every {kind} entry needs a provider and a model.")
        try:
            row = catalogue.find(identifier)
        except KeyError:
            raise ApiError(
                400, "unknown_provider", f"This server has no provider called {identifier}."
            ) from None
        if not row.serves(catalogue_kind(kind)):
            raise ApiError(400, "unsupported_kind", f"{row.label} does not do {kind}.")
        if model not in row.models_for(catalogue_kind(kind)):
            raise ApiError(
                400, "unknown_model", f"{row.label} does not offer {model} for {kind}."
            )
        if (identifier, model) in pairs:
            raise ApiError(400, "duplicate_pair", f"{model} is listed twice for {kind}.")
        pairs.append((identifier, model))
    return pairs


def apply_selection(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    """Store the chains this request names, and the checks when it names them, then answer with what
    `GET /models` would say.

    Everything is validated before anything is written, so a bad second kind cannot leave the first
    one stored. Answering with the full view means the interface renders the server's answer instead
    of its own optimism.
    """
    submitted = body.get("chains")
    checking = body.get("checkAnswers")
    if submitted is None and checking is None:
        raise ApiError(400, "invalid_input", "Say which chains to change, or whether to check answers.")
    if submitted is not None and (not isinstance(submitted, dict) or not submitted):
        raise ApiError(400, "invalid_input", "Say which chains to change.")
    if checking is not None and not isinstance(checking, bool):
        raise ApiError(400, "invalid_input", "Checking answers is either on or off.")

    catalogue = load(settings)
    changes: dict[str, list[tuple[str, str]] | None] = {}
    for kind, value in (submitted or {}).items():
        if kind not in KINDS:
            raise ApiError(400, "unsupported_kind", f"There is no {kind} chain.")
        # `null` forgets a kind and returns it to the providers' own order.
        changes[kind] = None if value is None else _submitted(kind, value, catalogue)

    model_selection.save(owner, changes, check_answers=checking)
    return catalogue_view(settings, owner)


def open_call_log(settings: Settings) -> None:
    """Point the provider package's journal at a file, if this deployment wants one.

    Idempotent, because `create_app` is called more than once in the tests and a second handler
    would double every line. An empty path means no file: the lines are emitted and nothing listens,
    which is the right default for a laptop and costs nothing.

    Rotating rather than growing: this writes on every model call, and an unbounded file on the same
    volume as the database is a way to lose the database. Failing to open it is *not* fatal — a
    server that cannot write its log should still serve words.
    """
    if not settings.call_log_path:
        return
    try:
        # Stamped with the request id where the file is opened, because the package that writes the
        # lines may not know one exists (`acervo/trace.py`).
        logfiles.open_rotating(journal.LOGGER, settings.call_log_path, settings.call_log_bytes,
                               settings.call_log_keep)
    except OSError as unwritable:   # noqa: BLE001 — a log nobody can write must not stop the server
        logging.getLogger("acervo.api").warning(
            "Acervo: the model call log could not be opened (%s); calls will not be recorded",
            unwritable,
        )
