"""`anki.push` and `anki.pull`: keeping Anki up to date, and reading it back (`docs/features/anki.md`).

A push is queued by the write that changed the vocabulary (`repository/graph.py`), a minute after
the writes stop, and reads the review state back as its second step, since the collection has just
synced down. A pull is queued by the timer below, every hour, for each owner who has it on. Both are
the functions `services/anki.py` gives the hand-run commands too.

A push is seconds once the first one has run: the pictures are already scaled and the notes already
match, so the runner is not held up for long.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from acervo.consumers.anki.progress import Progress
from acervo.consumers.anki.robot import RobotBusy, SyncSafetyError
from acervo.errors import ApiError
from acervo.repository import anki_settings, jobs
from acervo.services import anki
from acervo.settings import Settings
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Requeue, Step

log = logging.getLogger("acervo.work.anki")

# How long a busy robot — a command run by hand — is waited for before the job tries again.
BUSY_SECONDS = 60.0
PULL_EVERY = timedelta(hours=1)
CHECK_EVERY_SECONDS = 60.0


class _Log:
    """Where a job's progress lines go: the server log, a line each."""

    def write(self, text: str) -> None:
        if text.strip():
            log.info("%s", text.strip())

    def flush(self) -> None:
        pass


def _progress() -> Progress:
    return Progress(_Log())  # type: ignore[arg-type]


def _run(step: Step, work: Callable[[], dict]) -> None:
    try:
        report = work()
    except RobotBusy as busy:
        raise Requeue(BUSY_SECONDS) from busy
    except SyncSafetyError as refusal:
        # The robot's own sentence — "requires FULL_SYNC; the robot will never choose…" — is what the
        # owner needs to read, so it is carried whole rather than replaced with a constant.
        raise ApiError(409, "anki_refused", str(refusal)) from refusal
    step.note(**{key: value for key, value in report.items() if isinstance(value, (int, str))})


def _push_step(context: JobContext, step: Step) -> str | None:
    if not anki_settings.settings(context.owner).push:
        return "skipped"
    _run(step, lambda: anki.push(context.settings, context.owner, _progress(), backup=False))
    return None


def _pull_step(context: JobContext, step: Step) -> str | None:
    if not context.settings.anki_configured:
        return "skipped"
    _run(step, lambda: anki.pull(context.settings, context.owner, _progress()))
    return None


def push(context: JobContext) -> None:
    context.step(anki_settings.PUSH, lambda step: _push_step(context, step))
    context.step(anki_settings.PULL, lambda step: _pull_step(context, step))


def pull(context: JobContext) -> None:
    context.step(anki_settings.PULL, lambda step: _pull_step(context, step))


def _moment(instant: str | None) -> datetime | None:
    if not instant:
        return None
    return datetime.strptime(instant, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def due(owner: str, now: datetime) -> bool:
    """A pull is due when none is open and none has run, on its own or after a push, for an hour."""
    if jobs.open_of_kind(anki_settings.PULL, owner) or jobs.open_of_kind(anki_settings.PUSH, owner):
        return False
    last = [_moment(job["createdAt"]) for job in (jobs.latest_of_kind(owner, anki_settings.PULL),
                                                  jobs.latest_of_kind(owner, anki_settings.PUSH)) if job]
    last = [moment for moment in last if moment is not None]
    return not last or now - max(last) >= PULL_EVERY


def timer(settings: Settings, clock: Callable[[], float]) -> Callable[[], None]:
    """The runner tick that queues the hourly pull. Looks at most once a minute."""
    last: list[float] = []

    def tick() -> None:
        now = clock()
        if last and now - last[0] < CHECK_EVERY_SECONDS:
            return
        last[:] = [now]
        if not settings.anki_configured:
            return
        moment = datetime.fromtimestamp(now, timezone.utc)
        for owner in anki_settings.pulling_owners():
            if due(owner, moment):
                queued = jobs.enqueue(owner, anki_settings.PULL, trigger="schedule",
                                      subject_kind=anki_settings.SUBJECT, subject_id="pull")
                log.info("queued the hourly Anki pull %s", queued["id"])

    return tick


register(Kind(anki_settings.PUSH, (anki_settings.PUSH, anki_settings.PULL), push))
register(Kind(anki_settings.PULL, (anki_settings.PULL,), pull))
