"""`nightly`: the one timed run, and the timer that queues it (`docs/architecture/jobs.md`).

Steps in sequence, each behind its own switch in Settings ▸ Schedule, and a failed step never stops
the next. Today there is one, `corpus.update`; reading Anki back runs every hour instead
(`work/anki.py`). The timer is a tick of the runner's
loop: at most once a minute it asks, for each account, whether a run is due, and queues one if so.

Due means "no run since the most recent scheduled hour, and none open". That is what makes a night
the server was down for run once when it comes back, and what keeps missed nights from piling up.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from acervo.domain.ids import instant_of
from acervo.repository import accounts, jobs, schedule_settings
from acervo.services import schedule
from acervo.settings import Settings
from acervo.work import corpus
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Step

log = logging.getLogger("acervo.work.nightly")

STEPS = tuple(schedule_settings.STEPS)
CHECK_EVERY_SECONDS = 60.0


def due(settings: Settings, owner: str, now: datetime) -> bool:
    chosen = schedule_settings.settings(owner)
    if not any(chosen.steps.values()):
        return False
    if jobs.open_of_kind("nightly", owner):
        return False
    latest = jobs.latest_of_kind(owner, "nightly")
    struck = instant_of(schedule.last_scheduled(settings, chosen.hour, now))
    return latest is None or latest["createdAt"] < struck


def timer(settings: Settings, clock: Callable[[], float]) -> Callable[[], None]:
    """The runner tick that queues nightly runs. Looks at most once a minute."""
    last: list[float] = []

    def tick() -> None:
        now = clock()
        if last and now - last[0] < CHECK_EVERY_SECONDS:
            return
        last[:] = [now]
        moment = datetime.fromtimestamp(now, timezone.utc)
        for owner in accounts.all_ids():
            if due(settings, owner, moment):
                queued = jobs.enqueue(owner, "nightly", trigger="schedule",
                                      subject_kind="schedule", subject_id="nightly")
                log.info("queued the nightly run %s", queued["id"])

    return tick


def corpus_update(context: JobContext, step: Step) -> str | None:
    if not schedule_settings.settings(context.owner).steps["corpus.update"]:
        return "skipped"
    return corpus.follow(context, step)


def nightly(context: JobContext) -> None:
    context.step("corpus.update", lambda step: corpus_update(context, step), lane="corpus")


register(Kind("nightly", STEPS, nightly))
