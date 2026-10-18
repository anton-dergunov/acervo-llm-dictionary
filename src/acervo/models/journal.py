"""What was asked of which model, and what came back.

There was no record of any of this. A chain could walk nine pairs, be refused by every one for the
same reason, sleep four minutes and walk them again — and leave behind a `passedOver` array inside
whichever response eventually succeeded, or nothing at all if none did. Working out *why* a picture
took six minutes meant reading the code and guessing, which is how a schema that asked for one field
out of eight survived two deployments.

So: **one line per attempt**, written where `chain.walk` already knows the outcome. The line names
the caller, the pair, what happened, how long it took, and — when the answer was refused for its
shape — the reason it was refused. That last part is the one that pays: it is the difference between
"unusable" and "it returned only senseId".

**The package emits; it does not configure.** `acervo.models` may not import `Settings`
(`test_layering.py`), and it should not care where a log lives in any case. It writes to an ordinary
logger and stops there; `services/models.py`, which already reads `Settings`, decides whether that
goes to a file and where. A deployment that installs no handler loses the lines and nothing else.

Nothing here formats a credential. Every detail on a `ProviderError` is redacted at construction
(`redact.py`), which is the property this module leans on rather than re-implements — a message
cleaned only on its way to a log has a path that skips the cleaning, and this repository is public.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable

# The name a handler attaches to. Deliberately not `acervo.models`, so installing a file for this
# does not also capture whatever else the package might one day log.
LOGGER = "acervo.models.calls"

logger = logging.getLogger(LOGGER)

# How much of a rejected answer is worth keeping. Enough to see the shape of what came back —
# whether it was prose, an empty object, or an object with one field of eight — and not so much
# that a chatty model fills the file. A reply is truncated rather than summarised: a summary of
# malformed output is one more thing that can be wrong.
EXCERPT = 400


def excerpt(text: str, limit: int = EXCERPT) -> str:
    """A bounded, single-line view of a reply, for the detail of a shape refusal.

    `limit` is for a caller whose failures are only legible whole — a chat proposal names the
    operation that was wrong somewhere past the first four hundred characters.
    """
    flattened = " ".join((text or "").split())
    return flattened if len(flattened) <= limit else flattened[:limit] + "…"


def answered(caller: str, provider: str, model: str, seconds: float) -> None:
    logger.info("%s %s:%s ok in %.2fs", caller, provider, model, seconds)


def passed(caller: str, provider: str, model: str, reason: str, detail: str, seconds: float) -> None:
    """One pair that did not answer, and the reason the next one is being asked.

    At `warning`, because every one of these costs a call and some of them cost a minute. A run that
    is quietly walking the whole chain on every word should be visible at the default level rather
    than only to somebody who thought to turn logging up.

    The duration is the part that answers "where did the forty seconds go": a 503 back in half a
    second and a timeout at the bound are the same reason code and very different costs.
    """
    logger.warning("%s %s:%s %s after %.2fs — %s", caller, provider, model, reason, seconds, detail)


def late(caller: str, provider: str, model: str, outcome: str, seconds: float) -> None:
    """A raced pair that finished after another had already answered. Its outcome changed nothing."""
    logger.info("%s %s:%s late %s after %.2fs", caller, provider, model, outcome, seconds)


def exhausted(caller: str, attempts: int, reasons: tuple[str, ...]) -> None:
    logger.error("%s exhausted after %d attempt(s): %s", caller, attempts, ", ".join(reasons))


def outcome(caller: str, failed: bool = False, **fields: object) -> None:
    """What a request did with its answer, one line, beside the attempts `chain.walk` wrote.

    The attempt lines say which pair answered and how fast; they cannot say whether the answer was
    used, reused from last time, stored, or thrown away because the write after it failed. This line
    is that, as `key=value` pairs, so `grep 'pronounce-sentence outcome' | grep result=refused` is a
    question with an answer. Text values are quoted and bounded with `excerpt`, and the shape
    deliberately matches neither `_OK` nor `_BAD` — its second token has no colon — so `summarise`
    reads straight past it.
    """
    parts = []
    for name, value in fields.items():
        if value is None or value == "":
            continue
        if isinstance(value, float):
            rendered = f"{value:.2f}"
        elif isinstance(value, str) and (not value.isprintable() or any(c in value for c in ' "=')):
            rendered = json.dumps(excerpt(value), ensure_ascii=False)
        else:
            rendered = str(value)
        parts.append(f"{name}={rendered}")
    (logger.warning if failed else logger.info)("%s outcome %s", caller, " ".join(parts))


# ── reading it back ─────────────────────────────────────────────────────────
#
# The reader lives beside the writer on purpose. A log format described in two places drifts, and
# this one is the answer to a question worth asking often: how long does each job actually take, and
# therefore what is a sensible bound to give up at? Timeouts set from a guess are either so long
# that a dead connection reads as a hung page, or so short that a legitimately slow answer is thrown
# away. Neither is necessary when the durations are right here.

_OK = re.compile(r"^(?P<when>\S+ \S+) \w+ (?P<caller>\S+) (?P<pair>\S+:\S+) ok in (?P<seconds>[\d.]+)s")
_BAD = re.compile(
    r"^(?P<when>\S+ \S+) \w+ (?P<caller>\S+) (?P<pair>\S+:\S+) (?P<reason>\S+)"
    r"(?: after (?P<seconds>[\d.]+)s)? — "
)


@dataclass(frozen=True)
class Timing:
    """What one (caller, pair) did, over every call in the log."""

    caller: str
    pair: str
    answered: int
    failed: int
    seconds: tuple[float, ...]
    lost: float = 0.0
    """Seconds spent on attempts that did not answer — what a fall-through cost the person waiting."""

    def at(self, share: float) -> float:
        """The duration at a share of the calls, nearest-rank. `at(1.0)` is the slowest seen."""
        if not self.seconds:
            return 0.0
        ordered = sorted(self.seconds)
        index = max(0, min(len(ordered) - 1, round(share * len(ordered) + 0.5) - 1))
        return ordered[index]


def summarise(lines: Iterable[str]) -> list[Timing]:
    """Every (caller, pair) in the log, slowest first by its worst call.

    Failures are counted and kept out of the percentiles: a call that timed out took exactly as long
    as the bound allowed, so averaging it in would measure the bound rather than the provider. Their
    durations are totalled apart, as `lost`, which is the number a latency complaint is really about.
    """
    answered: dict[tuple[str, str], list[float]] = {}
    failed: dict[tuple[str, str], int] = {}
    lost: dict[tuple[str, str], float] = {}
    for line in lines:
        if match := _OK.match(line):
            key = (match["caller"], match["pair"])
            answered.setdefault(key, []).append(float(match["seconds"]))
        elif match := _BAD.match(line):
            key = (match["caller"], match["pair"])
            failed[key] = failed.get(key, 0) + 1
            lost[key] = lost.get(key, 0.0) + float(match["seconds"] or 0)
    keys = set(answered) | set(failed)
    rows = [
        Timing(caller, pair, len(answered.get((caller, pair), ())), failed.get((caller, pair), 0),
               tuple(answered.get((caller, pair), ())), lost.get((caller, pair), 0.0))
        for caller, pair in keys
    ]
    return sorted(rows, key=lambda row: (row.at(1.0), row.answered), reverse=True)
