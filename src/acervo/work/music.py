"""`music` and `music.samples`: music on its own, made before anyone presses play.

- **`music`** gives a kept bed its own minute of music (`services/music.py`). It is queued in the
  same transaction as the bed arrives, and follows the generator's operation exactly as `work/loop.py`
  does: the render writes the operation's id down, requeues while it runs, and the store reads it
  back. A bed let go of meanwhile, or one already given its music, is nothing to do.
- **`music.samples`** makes every style's sample the engine and bundle now answering lack. It is set
  off by a runner tick after each start — a deploy is what changes the engine — and renders one
  family at a time, so a loop asked for meanwhile waits behind one sample rather than all of them.
  A sample a tap made first is simply not missing any more.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from acervo import activity
from acervo.errors import ApiError
from acervo.loops.client import Music
from acervo.repository import accounts, jobs
from acervo.services import loops, music
from acervo.settings import Settings
from acervo.work.kinds import Kind, register
from acervo.work.loop import DEVICE
from acervo.work.runner import JobContext, Requeue, Step

log = logging.getLogger("acervo.work")

# A bed alone takes seconds rather than minutes: a two-second look is a fraction of one.
POLL_SECONDS = 2.0
# Ten minutes of looks for one render, which is ten loops' worth of waiting behind the generator's
# one worker. The render carries on there either way.
MAX_POLLS = 300

# How soon after a start the tick looks, so the server is serving before it asks the generator for
# anything, and how often it looks again while samples are missing or the generator is away.
FIRST_LOOK_SECONDS = 60
LOOK_EVERY_SECONDS = 60 * 60

SAMPLES = "music.samples"


def _finished(operation, polls: int) -> bool:
    if operation.finished:
        return True
    if polls > MAX_POLLS:
        raise ApiError(504, "loops_timeout",
                       "The music has not finished after ten minutes; stopped following it.")
    return False


# ── a kept bed's minute ─────────────────────────────────────────────────────


def _render(context: JobContext, step: Step, bed_id: str) -> str | None:
    step.gate()
    detail = step.record.get("detail") or {}
    operation_id = detail.get("operationId")
    if operation_id:
        operation = music.follow(context.settings, operation_id)
    else:
        bed = music.unheard(context.owner, bed_id)
        if bed is None:
            return "skipped"
        operation = music.start_bed(context.settings, bed)
        step.note(operationId=operation.id, family=bed["styleId"])

    polls = int(detail.get("polls") or 0) + 1
    if not _finished(operation, polls):
        step.record["state"] = "waiting"
        step.note(operationId=operation.id, status=operation.status, polls=polls,
                  progress=round(operation.fraction, 3), doing=operation.message)
        raise Requeue(POLL_SECONDS)

    step.note(status=operation.status, successful=operation.successful)
    if operation.status != "completed" or not isinstance(operation.result, Music):
        raise ApiError(502, "loops_failed", operation.error or f"The render was {operation.status}.")
    return None


def _store(context: JobContext, step: Step, bed_id: str) -> str | None:
    rendered = context.record("music.render")
    # Nothing to keep after a render that had nothing to do, or failed with its own sentence.
    if rendered.get("state") != "done":
        return "skipped"
    operation_id = (rendered.get("detail") or {}).get("operationId")
    if not operation_id:
        raise ApiError(502, "loops_failed", "The render did not say which operation it started.")
    operation = music.follow(context.settings, operation_id)
    if not isinstance(operation.result, Music):
        raise ApiError(502, "loops_failed", operation.error or "The render produced no music.")
    stored = music.store_bed(context.settings, context.owner, DEVICE, bed_id, operation.result)
    if stored is None:
        return "skipped"
    step.note(audioRef=stored.get("audioRef"))
    return None


def bed(context: JobContext) -> None:
    bed_id = context.subject_id
    context.step("music.render", lambda step: _render(context, step, bed_id), lane="audio")
    context.step("music.store", lambda step: _store(context, step, bed_id))


# ── every style's sample ────────────────────────────────────────────────────


def _samples(context: JobContext, step: Step) -> str | None:
    """One family at a time: follow the one in hand, keep it, then start the next one missing."""
    step.gate()
    detail = step.record.get("detail") or {}
    operation_id = detail.get("operationId")
    family = detail.get("family")
    made = int(detail.get("made") or 0)
    if operation_id and family:
        operation = music.follow(context.settings, operation_id)
        polls = int(detail.get("polls") or 0) + 1
        if not _finished(operation, polls):
            step.record["state"] = "waiting"
            step.note(polls=polls, progress=round(operation.fraction, 3), doing=operation.message)
            raise Requeue(POLL_SECONDS)
        if operation.status != "completed" or not isinstance(operation.result, Music):
            raise ApiError(502, "loops_failed", f"The {family} sample was not made: "
                           f"{operation.error or operation.status}")
        music.store_sample(context.settings, family, operation.result)
        made += 1
        step.record["done"] = int(step.record.get("done") or 0) + 1

    left = music.missing(context.settings)
    if not left:
        step.note(operationId=None, family=None, polls=0, made=made, left=0)
        return None if made else "skipped"
    operation = music.start_sample(context.settings, left[0])
    step.record["state"] = "waiting"
    step.note(operationId=operation.id, family=left[0], polls=0, made=made, left=len(left),
              doing=f"Making the {left[0]} sample")
    raise Requeue(POLL_SECONDS)


def warm(context: JobContext) -> None:
    context.step(SAMPLES, lambda step: _samples(context, step), lane="audio")


register(Kind("music", ("music.render", "music.store"), bed))
register(Kind(SAMPLES, (SAMPLES,), warm))


def timer(settings: Settings, clock: Callable[[], float]) -> Callable[[], None]:
    """The runner tick that sets the samples off: once a minute after a start, then hourly while any
    are missing. Queued for every account, since `jobs.enqueue` joins an open one and a job finds
    nothing missing once another has made them."""
    started: list[float] = []
    last: list[float] = []

    def tick() -> None:
        now = clock()
        if not started:
            started.append(now)
        if now - started[0] < FIRST_LOOK_SECONDS or (last and now - last[0] < LOOK_EVERY_SECONDS):
            return
        last[:] = [now]
        if not loops.configured(settings):
            return
        try:
            left = music.missing(settings)
        except ApiError as refusal:
            # Unattended, so it says so itself: no request and no job would otherwise carry this.
            activity.note("samples not checked", failed=True, code=refusal.code,
                          message=refusal.message)
            return
        if not left:
            return
        for owner in accounts.all_ids():
            if jobs.open_of_kind(SAMPLES, owner):
                continue
            queued = jobs.enqueue(owner, SAMPLES, trigger="schedule", subject_kind="samples",
                                  subject_id="samples")
            log.info("queued the style samples %s (%d missing)", queued["id"], len(left))

    return tick
