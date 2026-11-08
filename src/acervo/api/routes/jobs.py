"""Reading the work the server is doing, and asking for more (`docs/architecture/jobs.md`).

A route queues a job and reads its record; it never runs one. That is `acervo.work`'s, which this
package reaches only through `repository.jobs`.

Only the kinds a person can ask for directly are accepted here. A save queues `enrich` on its own;
this is for Try again, and for a bundle import that restores pictures before it asks for the rest.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.domain.ids import is_record_id
from acervo.errors import ApiError
from acervo.repository import graph, jobs

router = APIRouter()

# kind → what its subject must be. Grows as the interface gains a way to ask for each.
ENQUEUEABLE: dict[str, str] = {
    "enrich": "lexeme",
    "image.redraw": "imagePrompt",
    "image.rebrief": "lexeme",
    # Update now. The corpus is the deployment's, so the job is about it rather than a record.
    "corpus.update": "corpus",
    # Try again on a loop that was never rendered, or was rendered badly. Its row already exists —
    # an empty `audioRef` is what says it has not been made — so this re-renders rather than creates.
    "loop": "loop",
    "story": "story",
    # Try again on a kept bed whose music was not made.
    "music": "bed",
}
# Kinds about one fixed thing rather than a record the request names.
FIXED_SUBJECTS: dict[str, str] = {"corpus.update": "corpus"}
# What a request may carry into its job, per kind. Edit-and-draw is a redraw with its own wording.
INPUTS: dict[str, tuple[str, ...]] = {
    "image.redraw": ("prompt", "styleId"),
    # The sense whose picture dialog asked, so a sense ruled out there is briefed again.
    "image.rebrief": ("senseId",),
    # Try again on a loop keeps the music that was asked for, which the interface re-sends from the
    # job it is retrying. Without it here the field would be dropped and the retry would differ from
    # the original in a way nobody asked for. `seed` is a change of music's (`POST /loops/{id}/music`).
    "loop": ("family", "seed"),
}
TRIGGERS = ("manual", "import")

NOT_FOUND = ApiError(404, "not_found", "There is no such job.")


def _subject(owner: str, kind: str, body: dict[str, Any]) -> str:
    if kind in FIXED_SUBJECTS:
        return FIXED_SUBJECTS[kind]
    expected = ENQUEUEABLE[kind]
    subject = body.get("subject") if isinstance(body.get("subject"), dict) else {}
    identifier = str(subject.get("id") or "").strip()
    if subject.get("kind") != expected or not is_record_id(identifier):
        raise ApiError(400, "invalid_input", f"A {kind} job is about one {expected}.")
    if expected == "imagePrompt":
        if graph.image_prompt(owner, identifier) is None:
            raise ApiError(404, "not_found", "That picture is not in your vocabulary.")
    elif expected in ("loop", "story", "bed"):
        collection = {"loop": "loops", "story": "stories", "bed": "beds"}[expected]
        held = graph.owned_records(owner, collection, [identifier]).get(identifier)
        if held is None or held.get("deleted"):
            raise ApiError(404, "not_found", f"That {expected} is not in your vocabulary.")
    elif graph.lexeme_of(owner, expected, identifier) is None:
        raise ApiError(404, "not_found", "That word is not in your vocabulary.")
    return identifier


@router.get("/jobs")
def list_jobs(request: Request) -> JSONResponse:
    """Open jobs with `?open=true` — what a client rebuilds its map from — else recent ones."""
    account = owner_id(request)
    if request.query_params.get("open") == "true":
        return data({"jobs": jobs.open_jobs(account)})
    try:
        limit = int(request.query_params.get("limit") or 50)
    except ValueError:
        limit = 50
    return data({"jobs": jobs.recent(account, limit)})


@router.get("/jobs/{job_id}")
def read_job(job_id: str, request: Request) -> JSONResponse:
    found = jobs.get(owner_id(request), job_id)
    if found is None:
        raise NOT_FOUND
    return data(found)


@router.post("/jobs")
async def enqueue(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    kind = str(body.get("kind") or "")
    if kind not in ENQUEUEABLE:
        raise ApiError(400, "invalid_input", f"A {kind or 'nameless'} job cannot be asked for.")
    trigger = str(body.get("trigger") or "manual")
    if trigger not in TRIGGERS:
        raise ApiError(400, "invalid_input", "A job is asked for manually or by an import.")
    subject = await run_in_threadpool(_subject, account, kind, body)
    given = body.get("input") if isinstance(body.get("input"), dict) else {}
    carried = {
        key: str(given[key]) for key in INPUTS.get(kind, ())
        if isinstance(given.get(key), str) and given[key].strip()
    }
    queued = await run_in_threadpool(
        lambda: jobs.enqueue(account, kind, trigger=trigger, subject_kind=ENQUEUEABLE[kind],
                             subject_id=subject, input=carried)
    )
    return data(queued, status=202)


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str, request: Request) -> JSONResponse:
    found = await run_in_threadpool(jobs.request_cancel, owner_id(request), job_id)
    if found is None:
        raise NOT_FOUND
    return data(found)


@router.post("/jobs/{job_id}/dismiss")
async def dismiss(job_id: str, request: Request) -> JSONResponse:
    found = await run_in_threadpool(jobs.dismiss, owner_id(request), job_id)
    if found is None:
        raise NOT_FOUND
    return data(found)
