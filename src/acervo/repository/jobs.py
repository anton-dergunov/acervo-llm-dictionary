"""The job record: what the server has been asked to do, and how far it has got.

Owner-scoped server state, never replicated (`docs/architecture/jobs.md`). Every function
here is a transaction of its own, except `enqueue_enrich` and `enqueue_later`, which take the
caller's connection on purpose: a word and the job it calls for are written together or not at all.

A job says *which word*. What that word still lacks is read from the graph when each step runs, so a
job run twice does nothing the second time and a job lost to a restart costs latency, not work.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Connection, delete, or_, select, update

from acervo import notify
from acervo.db import tables
from acervo.domain.ids import instant_of, new_record_id, now_instant
from acervo.repository.session import reading, transaction

OPEN = ("queued", "running")
FINISHED = ("done", "failed", "cancelled")
TRIGGERS = ("save", "import", "ingest", "manual", "schedule", "backfill")

# Kinds whose running job already answers a second request: a corpus update asked for while one is
# being followed is the same update, and a second nightly run the same night is not wanted.
WHILE_RUNNING = frozenset({"corpus.update", "nightly"})

# The error a job carries when the process that ran it went away. Nothing resumes: Try again
# enqueues a new job, and a job that resumed would have to version its half-done state.
INTERRUPTED = "interrupted"

_jobs = tables.jobs


def project(row: Mapping[str, Any]) -> dict[str, Any]:
    """The wire shape. camelCase like every other document the API returns."""
    subject = (
        {"kind": row["subject_kind"], "id": row["subject_id"]} if row["subject_kind"] else None
    )
    return {
        "id": row["id"],
        "ownerId": row["owner"],
        "parentId": row["parent"],
        "kind": row["kind"],
        "subject": subject,
        "input": dict(row["input"] or {}),
        "state": row["state"],
        "trigger": row["trigger"],
        "steps": list(row["steps"] or []),
        "rerun": bool(row["rerun"]),
        "cancelRequested": bool(row["cancel_requested"]),
        "dismissed": bool(row["dismissed"]),
        "error": row["error"],
        "message": row["message"],
        "notBefore": row["not_before"] or None,
        "createdAt": row["created_at"],
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
    }


def _row(connection: Connection, job_id: str) -> Mapping[str, Any] | None:
    return connection.execute(select(_jobs).where(_jobs.c.id == job_id)).mappings().first()


def _insert(
    connection: Connection,
    owner: str,
    kind: str,
    *,
    trigger: str,
    subject_kind: str = "",
    subject_id: str = "",
    input: Mapping[str, Any] | None = None,
    parent: str | None = None,
    not_before: str = "",
) -> dict[str, Any]:
    if trigger not in TRIGGERS:
        raise ValueError(f"Unknown job trigger {trigger!r}.")
    identifier = new_record_id()
    connection.execute(
        _jobs.insert().values(
            id=identifier,
            owner=owner,
            parent=parent,
            kind=kind,
            subject_kind=subject_kind,
            subject_id=subject_id,
            input=dict(input or {}),
            state="queued",
            trigger=trigger,
            steps=[],
            rerun=False,
            cancel_requested=False,
            dismissed=False,
            not_before=not_before,
            created_at=now_instant(),
        )
    )
    return project(_row(connection, identifier))  # type: ignore[arg-type]


def _moment(instant: str) -> datetime:
    return datetime.strptime(instant, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def enqueue_later(
    connection: Connection,
    owner: str,
    kind: str,
    *,
    trigger: str,
    subject_kind: str,
    subject_id: str,
    delay: float = 60.0,
    cap: float = 600.0,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Ask for work to happen once the writes calling for it have stopped, inside the caller's
    transaction. Returns a job to publish after commit, or None when nothing new was queued.

    A burst of edits is one request: each write moves the queued job `delay` seconds later, but never
    more than `cap` after it was first asked for, so a long session still reaches the work. A running
    job may have read the vocabulary before this write, so it is left alone and a new one queued
    behind it — at most one waits.
    """
    now = now or datetime.now(timezone.utc)
    queued = connection.execute(
        select(_jobs).where(
            _jobs.c.owner == owner, _jobs.c.kind == kind, _jobs.c.subject_id == subject_id,
            _jobs.c.state == "queued",
        )
    ).mappings().first()
    if queued is None:
        return _insert(connection, owner, kind, trigger=trigger, subject_kind=subject_kind,
                       subject_id=subject_id, not_before=instant_of(now + timedelta(seconds=delay)))
    latest = _moment(queued["created_at"]) + timedelta(seconds=cap)
    moved = instant_of(min(now + timedelta(seconds=delay), latest))
    if moved > (queued["not_before"] or ""):
        connection.execute(update(_jobs).where(_jobs.c.id == queued["id"]).values(not_before=moved))
    return None


def _open_enrich(connection: Connection, owner: str, lexeme_id: str) -> Mapping[str, Any] | None:
    return connection.execute(
        select(_jobs).where(
            _jobs.c.owner == owner,
            _jobs.c.kind == "enrich",
            _jobs.c.subject_id == lexeme_id,
            _jobs.c.state.in_(OPEN),
        )
    ).mappings().first()


def enqueue_enrich(
    connection: Connection,
    owner: str,
    lexeme_id: str,
    *,
    trigger: str,
    parent: str | None = None,
) -> dict[str, Any]:
    """Ask for a word to be enriched, inside the caller's transaction.

    A queued job already covers the request, so meeting one does nothing. A running one may have read
    the word before this write, so it is marked to run again once it finishes rather than joined by a
    second job — which the partial unique index would refuse anyway.

    The caller publishes the returned job once its transaction has committed.
    """
    existing = _open_enrich(connection, owner, lexeme_id)
    if existing is not None:
        if existing["state"] == "running" and not existing["rerun"]:
            connection.execute(
                update(_jobs).where(_jobs.c.id == existing["id"]).values(rerun=True)
            )
            existing = _row(connection, existing["id"])
        return project(existing)  # type: ignore[arg-type]
    return _insert(
        connection, owner, "enrich", trigger=trigger, subject_kind="lexeme",
        subject_id=lexeme_id, parent=parent,
    )


def enqueue(
    owner: str,
    kind: str,
    *,
    trigger: str,
    subject_kind: str = "",
    subject_id: str = "",
    input: Mapping[str, Any] | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    """Queue one job in a transaction of its own, and wake the runner."""
    with transaction() as connection:
        if kind == "enrich":
            queued = enqueue_enrich(
                connection, owner, subject_id, trigger=trigger, parent=parent
            )
        else:
            waiting = (
                _open_for(connection, owner, kind, subject_id)
                if kind in WHILE_RUNNING and subject_id
                else _queued_for(connection, owner, kind, subject_id) if subject_id else None
            )
            if waiting is not None:
                # A second request for the same thing before the first has started is the same
                # request, and the newer wording wins: pressing Draw twice draws once.
                if waiting["state"] == "queued":
                    connection.execute(
                        update(_jobs).where(_jobs.c.id == waiting["id"])
                        .values(input=dict(input or {}))
                    )
                queued = project(_row(connection, waiting["id"]))  # type: ignore[arg-type]
            else:
                queued = _insert(
                    connection, owner, kind, trigger=trigger, subject_kind=subject_kind,
                    subject_id=subject_id, input=input, parent=parent,
                )
    notify.queued(owner, queued)
    return queued


def _open_for(connection: Connection, owner: str, kind: str, subject_id: str) -> Mapping[str, Any] | None:
    return connection.execute(
        select(_jobs).where(
            _jobs.c.owner == owner, _jobs.c.kind == kind, _jobs.c.subject_id == subject_id,
            _jobs.c.state.in_(OPEN),
        )
    ).mappings().first()


def _queued_for(connection: Connection, owner: str, kind: str, subject_id: str) -> Mapping[str, Any] | None:
    return connection.execute(
        select(_jobs).where(
            _jobs.c.owner == owner, _jobs.c.kind == kind, _jobs.c.subject_id == subject_id,
            _jobs.c.state == "queued",
        )
    ).mappings().first()


def open_for(owner: str, kind: str, subject_id: str) -> dict[str, Any] | None:
    """The queued or running job of this kind about this record, if there is one."""
    with reading() as connection:
        row = _open_for(connection, owner, kind, subject_id)
        return project(row) if row is not None else None


def open_of_kind(kind: str, owner: str | None = None) -> list[dict[str, Any]]:
    with reading() as connection:
        query = select(_jobs).where(_jobs.c.kind == kind, _jobs.c.state.in_(OPEN))
        if owner is not None:
            query = query.where(_jobs.c.owner == owner)
        return [project(row) for row in connection.execute(query).mappings()]


# ── the runner's side ───────────────────────────────────────────────────────


def claim_next(now: str) -> dict[str, Any] | None:
    """Take the oldest queued job that is due, and mark it running. Oldest first, across owners."""
    with transaction() as connection:
        row = connection.execute(
            select(_jobs)
            .where(
                _jobs.c.state == "queued",
                or_(_jobs.c.not_before == "", _jobs.c.not_before <= now),
            )
            .order_by(_jobs.c.created_at, _jobs.c.id)
            .limit(1)
        ).mappings().first()
        if row is None:
            return None
        connection.execute(
            update(_jobs)
            .where(_jobs.c.id == row["id"])
            .values(state="running", started_at=row["started_at"] or now_instant(), not_before="")
        )
        return project(_row(connection, row["id"]))  # type: ignore[arg-type]


def next_due() -> str | None:
    """When the earliest resting job becomes due, or nothing."""
    with reading() as connection:
        return connection.execute(
            select(_jobs.c.not_before)
            .where(_jobs.c.state == "queued", _jobs.c.not_before != "")
            .order_by(_jobs.c.not_before)
            .limit(1)
        ).scalar()


def save_steps(job_id: str, steps: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    with transaction() as connection:
        connection.execute(
            update(_jobs).where(_jobs.c.id == job_id).values(steps=[dict(s) for s in steps])
        )
        row = _row(connection, job_id)
    return project(row) if row is not None else None


def hasten(job_id: str) -> dict[str, Any] | None:
    """Make a queued job due now: what a press of Push now means for a push still waiting for the
    writes to stop. A job already running, or finished, is left as it is."""
    with transaction() as connection:
        connection.execute(
            update(_jobs).where(_jobs.c.id == job_id, _jobs.c.state == "queued").values(not_before="")
        )
        row = _row(connection, job_id)
    job = project(row) if row is not None else None
    if job is not None and job["state"] == "queued":
        notify.queued(job["ownerId"], job)
    return job


def requeue(
    job_id: str, steps: Sequence[Mapping[str, Any]], not_before: str
) -> dict[str, Any] | None:
    """Put a running job back to wait out a rest, yielding the lane. Unless it was cancelled."""
    with transaction() as connection:
        connection.execute(
            update(_jobs)
            .where(_jobs.c.id == job_id, _jobs.c.state == "running")
            .values(state="queued", steps=[dict(s) for s in steps], not_before=not_before)
        )
        row = _row(connection, job_id)
    return project(row) if row is not None else None


def finish(
    job_id: str,
    state: str,
    *,
    steps: Sequence[Mapping[str, Any]] | None = None,
    error: str | None = None,
    message: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Close a job. Returns it, and the fresh job its `rerun` asked for, if any.

    A job somebody already cancelled stays cancelled: a late finish from the thread that was running
    it must not bring it back to life.
    """
    if state not in FINISHED:
        raise ValueError(f"{state!r} is not a finished state.")
    follow_up = None
    with transaction() as connection:
        row = _row(connection, job_id)
        if row is None:
            return None, None
        values: dict[str, Any] = {}
        if steps is not None:
            values["steps"] = [dict(s) for s in steps]
        if row["state"] in OPEN:
            values.update(state=state, error=error, message=(message or None) and message[:500],
                          finished_at=now_instant(), not_before="")
        if values:
            connection.execute(update(_jobs).where(_jobs.c.id == job_id).values(**values))
        if row["rerun"] and row["kind"] == "enrich" and row["state"] in OPEN:
            follow_up = enqueue_enrich(
                connection, row["owner"], row["subject_id"], trigger=row["trigger"]
            )
        finished = project(_row(connection, job_id))  # type: ignore[arg-type]
    return finished, follow_up


def cancel_requested(job_id: str) -> bool:
    with reading() as connection:
        row = connection.execute(
            select(_jobs.c.cancel_requested, _jobs.c.state).where(_jobs.c.id == job_id)
        ).first()
    return row is None or bool(row[0]) or row[1] not in OPEN


def _cancel(connection: Connection, row: Mapping[str, Any]) -> None:
    if row["state"] == "queued":
        connection.execute(
            update(_jobs).where(_jobs.c.id == row["id"]).values(
                state="cancelled", cancel_requested=True, finished_at=now_instant(), not_before="",
            )
        )
    elif row["state"] == "running":
        connection.execute(
            update(_jobs).where(_jobs.c.id == row["id"]).values(cancel_requested=True)
        )


def request_cancel(owner: str, job_id: str) -> dict[str, Any] | None:
    """Cancel a queued job now, and ask a running one to stop at its next check.

    Children go with their parent: a capture that is cancelled should not leave its words' enrichment
    running on behind it.
    """
    with transaction() as connection:
        row = connection.execute(
            select(_jobs).where(_jobs.c.id == job_id, _jobs.c.owner == owner)
        ).mappings().first()
        if row is None:
            return None
        _cancel(connection, row)
        for child in connection.execute(
            select(_jobs).where(_jobs.c.parent == job_id, _jobs.c.state.in_(OPEN))
        ).mappings().all():
            _cancel(connection, child)
        cancelled = project(_row(connection, job_id))  # type: ignore[arg-type]
    notify.job(owner, cancelled)
    return cancelled


def cancel_all() -> list[dict[str, Any]]:
    """Every open job of every owner. What a deploy asks for; returns what was still running."""
    with transaction() as connection:
        rows = connection.execute(select(_jobs).where(_jobs.c.state.in_(OPEN))).mappings().all()
        for row in rows:
            _cancel(connection, row)
        return [project(row) for row in rows if row["state"] == "running"]


def abandon_running() -> int:
    """Close every running job as cancelled without waiting for the runner to agree.

    The last step of a deploy's cancel, once the runner has had its chance: the process is about to
    stop anyway, and a call in flight is abandoned rather than interrupted.
    """
    with transaction() as connection:
        result = connection.execute(
            update(_jobs)
            .where(_jobs.c.state == "running")
            .values(state="cancelled", cancel_requested=True, finished_at=now_instant())
        )
        return result.rowcount or 0


def interrupt_running() -> int:
    """At startup: whatever was running when the process went away failed, and says so."""
    with transaction() as connection:
        result = connection.execute(
            update(_jobs)
            .where(_jobs.c.state == "running")
            .values(
                state="failed", error=INTERRUPTED,
                message="The server restarted while this was running.",
                finished_at=now_instant(), not_before="",
            )
        )
        return result.rowcount or 0


def prune(before: str) -> int:
    """Forget finished jobs older than `before`. An undismissed failure is kept until dismissed."""
    with transaction() as connection:
        result = connection.execute(
            delete(_jobs).where(
                _jobs.c.state.in_(FINISHED),
                _jobs.c.finished_at < before,
                or_(_jobs.c.state != "failed", _jobs.c.dismissed.is_(True)),
                # A child goes with its parent, never before it.
                or_(_jobs.c.parent.is_(None),
                    ~_jobs.c.parent.in_(select(_jobs.c.id).where(_jobs.c.state.in_(OPEN)))),
            )
        )
        return result.rowcount or 0


# ── reading ─────────────────────────────────────────────────────────────────


def get(owner: str, job_id: str) -> dict[str, Any] | None:
    """One job and its children, or nothing — including for a job that is somebody else's."""
    with reading() as connection:
        row = connection.execute(
            select(_jobs).where(_jobs.c.id == job_id, _jobs.c.owner == owner)
        ).mappings().first()
        if row is None:
            return None
        children = connection.execute(
            select(_jobs).where(_jobs.c.parent == job_id).order_by(_jobs.c.created_at, _jobs.c.id)
        ).mappings()
        return {**project(row), "children": [project(child) for child in children]}


def open_jobs(owner: str | None = None) -> list[dict[str, Any]]:
    with reading() as connection:
        query = select(_jobs).where(_jobs.c.state.in_(OPEN))
        if owner is not None:
            query = query.where(_jobs.c.owner == owner)
        rows = connection.execute(query.order_by(_jobs.c.created_at, _jobs.c.id)).mappings()
        return [project(row) for row in rows]


def latest(limit: int = 30) -> list[dict[str, Any]]:
    """Every owner's recent jobs, newest first — what `admin jobs list` reads.

    `recent` is one owner's, because Settings ▸ Activity is one account's. This is the operator's
    view, and it deliberately includes finished and failed ones: `open_jobs` alone meant a render
    that failed four minutes ago could not be seen from the command line at all.
    """
    with reading() as connection:
        rows = connection.execute(
            select(_jobs)
            .order_by(_jobs.c.created_at.desc(), _jobs.c.id)
            .limit(max(1, min(limit, 500)))
        ).mappings()
        return [project(row) for row in rows]


def recent(owner: str, limit: int = 50) -> list[dict[str, Any]]:
    """What Settings ▸ Activity lists: everything not dismissed, newest first."""
    with reading() as connection:
        rows = connection.execute(
            select(_jobs)
            .where(_jobs.c.owner == owner, _jobs.c.dismissed.is_(False))
            .order_by(_jobs.c.created_at.desc(), _jobs.c.id)
            .limit(max(1, min(limit, 500)))
        ).mappings()
        return [project(row) for row in rows]


def latest_of_kind(owner: str, kind: str) -> dict[str, Any] | None:
    with reading() as connection:
        row = connection.execute(
            select(_jobs)
            .where(_jobs.c.owner == owner, _jobs.c.kind == kind)
            .order_by(_jobs.c.created_at.desc(), _jobs.c.id)
            .limit(1)
        ).mappings().first()
    return project(row) if row is not None else None


def dismiss(owner: str, job_id: str) -> dict[str, Any] | None:
    """Hide a finished job from Activity. An open job cannot be dismissed; cancel it first."""
    with transaction() as connection:
        connection.execute(
            update(_jobs)
            .where(_jobs.c.id == job_id, _jobs.c.owner == owner, _jobs.c.state.in_(FINISHED))
            .values(dismissed=True)
        )
        row = connection.execute(
            select(_jobs).where(_jobs.c.id == job_id, _jobs.c.owner == owner)
        ).mappings().first()
    return project(row) if row is not None else None
