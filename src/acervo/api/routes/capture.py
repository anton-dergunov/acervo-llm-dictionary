"""Capture: text in, an entry to review out — or, headless, a job that files entries in the Inbox.

`POST /capture` is synchronous because a person is waiting to review the result. `POST
/capture/resolve` is its first half alone, for a tapped word, and `/capture` accepts what it returned. `POST /captures`
is the headless transports' door: it queues a `capture` job and answers at once. Both run
`services/capture/pipeline.propose`, so there is one pipeline.

The interactive pipeline runs in the threadpool. Two model calls of up to 120 seconds each on the event
loop would stall every other request for four minutes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.errors import ApiError
from acervo.repository import graph, jobs
from acervo.services import photo
from acervo.services.capture.pipeline import TEXT_LIMIT, look_up, propose

router = APIRouter()


@router.post("/capture")
async def capture(request: Request) -> JSONResponse:
    """Propose one entry for review. Writes nothing; the interface saves what the owner approves."""
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    graph.require_device(body.get("deviceId"))
    _require_text(body)
    if body.get("photoRef"):
        # Refused before two model calls rather than at the save after them.
        photo.require(request.app.state.settings, account, str(body["photoRef"]))
    return data(await run_in_threadpool(propose, request.app.state.settings, account, body))


@router.post("/capture/resolve")
async def quick(request: Request) -> JSONResponse:
    """The quick look-up a tap makes — on a photo, or on a word being read: which word was meant,
    what it means here, and whether it is already held. One model call on the `quick` chain; writes nothing."""
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    graph.require_device(body.get("deviceId"))
    _require_text(body)
    return data(await run_in_threadpool(look_up, request.app.state.settings, account, body))


def _require_text(body: dict[str, Any]) -> str:
    text = str(body.get("text") or "")
    if not text.strip():
        raise ApiError(400, "invalid_input", "There is nothing to capture.")
    if len(text) > TEXT_LIMIT:
        raise ApiError(400, "invalid_input", "That capture is too long to process in one request.")
    return text


# What a headless capture may carry into its job. Everything else in a request is ignored. A
# `resolution` is a quick look-up's answer, carried by Add on a word tapped while reading, and checked
# again by the job exactly as `/capture` checks it (`pipeline.given_resolution`).
CAPTURE_FIELDS = (
    "text", "mode", "headword", "language", "topics", "sourceKind", "sourceUrl", "sourceTitle",
    "note", "reference", "referenceMode", "window", "complete", "limit", "resolution",
)


@router.post("/captures")
async def submit(request: Request) -> JSONResponse:
    """Capture without anyone reviewing it: one submission, one job (`docs/architecture/jobs.md`).

    The caller cannot know how many words a text holds — stream-mode resolve discovers that while it
    runs — so the submission is the unit and the words are its output. Each saved word lands in the
    Inbox and is enriched by a child job.
    """
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    graph.require_device(body.get("deviceId"))
    _require_text(body)
    job = await run_in_threadpool(
        jobs.enqueue, account, "capture", trigger="ingest",
        input={field: body[field] for field in CAPTURE_FIELDS if field in body},
    )
    return data(job, status=202)
