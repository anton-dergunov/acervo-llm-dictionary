"""The runner: one thread, one job at a time, in the server process (`docs/architecture/jobs.md`).

It is a thread rather than a task because everything it calls is synchronous — the same service
functions a route hands to the thread pool — and the work is a socket waiting on a remote API, not
CPU. Concurrency is one: the model allowances are the owner's own.

Nothing resumes. A job still marked running when the process starts failed, and says so; the owner
presses Try again, which queues a new one. A deploy refuses while jobs are open rather than carry
their half-done state across a version.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from acervo import notify, trace
from acervo.domain.ids import instant_of
from acervo.errors import ApiError
from acervo.repository import jobs
from acervo.settings import Settings
from acervo.work import journal, kinds, retry

log = logging.getLogger("acervo.work")

# Finished jobs are kept this long; a failure is kept until it is dismissed.
RETENTION = timedelta(days=14)
# How often the runner looks at the table when nothing woke it — which is how it finds a job queued
# or cancelled by another process.
POLL_SECONDS = 5.0


class Cancelled(Exception):
    """The owner asked this job to stop. Raised at a check, between model calls."""


class Requeue(Exception):
    """This job should wait `delay` seconds and yield the lane meanwhile."""

    def __init__(self, delay: float) -> None:
        super().__init__(delay)
        self.delay = delay


class JobFailed(Exception):
    """The job as a whole cannot go on — as opposed to one step failing, which it survives."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message


class Step:
    """The handle a step's body holds: progress, and the gate before each model call."""

    def __init__(self, context: "JobContext", record: dict[str, Any], lane: str | None) -> None:
        self._context = context
        self.record = record
        self.lane = lane

    def gate(self) -> None:
        """Call before each model call: stops a cancelled job, and yields to a resting lane."""
        self._context.check()
        if self.lane is None:
            return
        pace = self._context.runner.lanes[self.lane]
        delay = pace.delay()
        if delay > 0:
            self.record["state"] = "waiting"
            if not pace.resting():
                # Not a refusal: the lane's own allowance, kept to so as not to be refused.
                self.record["waitingOn"] = (
                    f"keeping to {pace.per_minute} {LANE_UNITS.get(self.lane, 'call')}"
                    f"{'' if pace.per_minute == 1 else 's'} a minute")
            raise Requeue(delay)
        pace.try_acquire()

    def progress(self, done: int, total: int) -> None:
        self.record["done"] = done
        self.record["total"] = total
        self._context.save()

    def note(self, **detail: Any) -> None:
        """Anything a step wants the owner to see — per-word outcomes for a capture, say."""
        self.record.setdefault("detail", {}).update(detail)
        self._context.save()


# What one call in a paced lane is, for the line that says a step is keeping to its allowance.
LANE_UNITS = {"image": "picture", "text": "call"}


class JobContext:
    def __init__(self, runner: "Runner", job: dict[str, Any], kind: kinds.Kind) -> None:
        self.runner = runner
        self.job = job
        self.kind = kind
        self.owner: str = job["ownerId"]
        self.settings: Settings = runner.settings
        self.steps: list[dict[str, Any]] = [dict(step) for step in job["steps"]]
        if not self.steps:
            self.steps = [_pending(name) for name in kind.steps]
            self.save()

    @property
    def id(self) -> str:
        return self.job["id"]

    @property
    def subject_id(self) -> str:
        subject = self.job.get("subject") or {}
        return subject.get("id", "")

    @property
    def input(self) -> dict[str, Any]:
        return self.job.get("input") or {}

    def check(self) -> None:
        if jobs.cancel_requested(self.id):
            raise Cancelled()

    def save(self) -> None:
        saved = jobs.save_steps(self.id, self.steps)
        if saved is not None:
            notify.job(self.owner, saved)

    def record(self, name: str) -> dict[str, Any]:
        for step in self.steps:
            if step["name"] == name:
                return step
        step = _pending(name)
        self.steps.append(step)
        return step

    def failed(self) -> bool:
        return any(step["state"] == "failed" for step in self.steps)

    def step(self, name: str, body: Callable[[Step], str | None], *, lane: str | None = None) -> str:
        """Run one step, unless an earlier run of this job already finished it.

        The body returns nothing for done, or `"skipped"` when there was nothing for it to do. A
        failure is recorded on the step and the job moves on: a word without a clip may still get its
        pictures. Only the three transient failures put the job back to wait — and only so many
        times.
        """
        record = self.record(name)
        if record["state"] in ("done", "skipped", "failed"):
            return record["state"]
        done_before = int(record.get("done") or 0)
        self.check()
        record["state"] = "running"
        self.save()
        handle = Step(self, record, lane)
        try:
            outcome = body(handle)
        except (Cancelled, Requeue):
            if record["state"] == "running":
                record["state"] = "pending"
            raise
        except ApiError as refusal:
            if retry.is_transient(refusal.code) and lane is not None:
                rests = int(record.get("rests", 0)) + 1
                if rests <= self.kind.rests:
                    record["rests"] = rests
                    record["state"] = "waiting"
                    record["error"] = refusal.code
                    # Who is being waited for and why, so the row can say "Gemini is overloaded;
                    # Cloudflare is out of allowance" rather than "the provider is busy".
                    record["waitingOn"] = refusal.waiting_on
                    pace = self.runner.lanes[lane]
                    if int(record.get("done") or 0) > done_before:
                        # It got somewhere before it was refused — two pictures, then a 429 — so
                        # this is an allowance refilling, not a provider failing, and the rest
                        # starts again from the first rather than doubling towards ten minutes.
                        pace.succeeded()
                    delay = pace.penalise()
                    raise Requeue(delay) from refusal
            record.pop("waitingOn", None)
            record.update(state="failed", error=refusal.code, message=refusal.message[:500])
            self.save()
            journal.step(self.id, self.kind.name, name, "failed", error=refusal.code,
                         message=refusal.message, **self._note())
            return "failed"
        except Exception as crash:  # noqa: BLE001 - a step's crash is recorded, not propagated
            log.exception("job %s step %s crashed", self.id, name)
            record.update(state="failed", error="server_error", message=str(crash)[:500])
            self.save()
            journal.step(self.id, self.kind.name, name, "failed", error="server_error",
                         message=str(crash), **self._note())
            return "failed"
        if lane is not None:
            self.runner.lanes[lane].succeeded()
        record["state"] = "skipped" if outcome == "skipped" else "done"
        record.pop("error", None)
        record.pop("waitingOn", None)
        self.save()
        journal.step(self.id, self.kind.name, name, record["state"], **self._note())
        return record["state"]


    def _note(self) -> dict[str, Any]:
        """The identifiers that join this log to somebody else's.

        `operationId` is the loop generator's own handle for a render, and until this line existed
        it lived in the database and in no log at all — so a failed render here could not be matched
        to its cause there.
        """
        detail = (self.record("loop.render").get("detail") or {}) if self.kind.name == "loop" else {}
        return {"operationId": detail.get("operationId")}


def _pending(name: str) -> dict[str, Any]:
    return {"name": name, "state": "pending"}


class Runner:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.time,
        poll: float = POLL_SECONDS,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.poll = poll
        self.lanes = retry.lanes()
        journal.open_job_log(settings)
        # When the job now running was taken, so the end line can say how long it took. A job that
        # was requeued reports the time since it was last taken, which is the honest number: the
        # rests in between are not work.
        self._began = clock()
        # Called on every pass of the loop, before looking for a job: the nightly timer hangs here.
        self.ticks: list[Callable[[], None]] = []
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self.current: str | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    def recover(self) -> None:
        """What a starting process does before it takes any work."""
        interrupted = jobs.interrupt_running()
        if interrupted:
            log.warning("%d job(s) were running when the server stopped; marked interrupted",
                        interrupted)
        jobs.prune(self._instant(self.clock() - RETENTION.total_seconds()))

    def start(self) -> None:
        if self._thread is not None:
            return
        self.recover()
        self._stopping.clear()
        self._thread = threading.Thread(target=self._loop, name="acervo-runner", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stopping.set()
        notify.work_arrived.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stopping.is_set():
            notify.work_arrived.clear()
            try:
                ran = self.run_once()
            except Exception:  # noqa: BLE001 - the loop must outlive any one failure
                log.exception("the runner failed to take a job")
                ran = False
            if not ran and not self._stopping.is_set():
                notify.work_arrived.wait(self._idle_wait())

    def _idle_wait(self) -> float:
        due = jobs.next_due()
        if due is None:
            return self.poll
        remaining = _epoch(due) - self.clock()
        return max(0.05, min(self.poll, remaining))

    # ── work ─────────────────────────────────────────────────────────────────

    def tick(self) -> None:
        for tick in self.ticks:
            try:
                tick()
            except Exception:  # noqa: BLE001
                log.exception("a runner tick failed")

    def run_once(self) -> bool:
        """Take one due job and run it to its end or its next rest. False when there was none."""
        self.tick()
        job = jobs.claim_next(self._instant(self.clock()))
        if job is None:
            return False
        self.execute(job)
        return True

    def run_until_idle(self, limit: int = 200) -> int:
        """Run every due job, including the ones jobs create. For tests and the admin CLI."""
        count = 0
        while count < limit and self.run_once():
            count += 1
        return count

    def execute(self, job: dict[str, Any]) -> None:
        # A job is its own request id: every model call it makes, and every call a companion makes
        # home on its behalf, is filed under the job (`acervo/trace.py`).
        with trace.scope(job["id"]):
            self._execute(job)

    def _execute(self, job: dict[str, Any]) -> None:
        owner = job["ownerId"]
        self.current = job["id"]
        self._began = self.clock()
        try:
            journal.started(job)
            notify.job(owner, job)
            kind = kinds.find(job["kind"])
            if kind is None:
                self._finish(owner, job["id"], "failed", None, "unknown_kind",
                             f"No job kind called {job['kind']!r}.")
                return
            context = JobContext(self, job, kind)
            try:
                kind.handler(context)
            except Requeue as rest:
                waiting = jobs.requeue(job["id"], context.steps,
                                       self._instant(self.clock() + rest.delay))
                if waiting is not None:
                    notify.job(owner, waiting)
                return
            except Cancelled:
                self._finish(owner, job["id"], "cancelled", context.steps)
                return
            except JobFailed as failure:
                self._finish(owner, job["id"], "failed", context.steps, failure.code,
                             failure.message)
                return
            except ApiError as refusal:
                self._finish(owner, job["id"], "failed", context.steps, refusal.code,
                             refusal.message)
                return
            except Exception as crash:  # noqa: BLE001
                log.exception("job %s (%s) crashed", job["id"], job["kind"])
                self._finish(owner, job["id"], "failed", context.steps, "server_error",
                             str(crash))
                return
            state = "failed" if context.failed() else "done"
            # Both, from the same step: the code is what the interface branches on and the message
            # is the only thing that says *why*. Passing the code alone left every ordinary failure
            # with a NULL message on the row and the sentence buried in the steps JSON.
            failed = next((s for s in context.steps if s["state"] == "failed"), None)
            self._finish(owner, job["id"], state, context.steps,
                         failed.get("error") if failed else None,
                         failed.get("message") if failed else None)
        finally:
            self.current = None

    def _finish(self, owner: str, job_id: str, state: str, steps: Any,
                error: str | None = None, message: str | None = None) -> None:
        finished, follow_up = jobs.finish(job_id, state, steps=steps, error=error, message=message)
        if finished is not None:
            journal.finished(finished, state, self.clock() - self._began, error, message)
        if finished is not None:
            notify.job(owner, finished)
        if follow_up is not None:
            notify.queued(owner, follow_up)

    @staticmethod
    def _instant(epoch: float) -> str:
        return instant_of(datetime.fromtimestamp(epoch, timezone.utc))


def _epoch(instant: str) -> float:
    return datetime.strptime(instant, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    ).timestamp()
