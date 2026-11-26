"""The replication routes: the cursor pull, the write, and the reset."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.errors import ApiError
from acervo.repository import graph
from acervo.services import photo

router = APIRouter()

CONFIRMATION = "delete-all-words"


@router.get("/graph")
def read(request: Request) -> JSONResponse:
    account = owner_id(request)
    graph.require_schema_version(request.query_params.get("schemaVersion"))
    try:
        since = max(0, round(float(request.query_params.get("since") or 0)))
    except ValueError:
        since = 0
    return data(graph.pull(account, since))


@router.post("/graph")
async def write(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    device = graph.require_device(body.get("deviceId"))
    changes = body.get("changes")
    # A save enriches the words it creates. An import writes its words through `POST /articles`.
    return data(
        await run_in_threadpool(
            lambda: graph.merge_graph(
                account, device, changes if isinstance(changes, dict) else {}, enqueue=graph.SAVE,
                place_photo=photo.placer(request.app.state.settings),
            )
        )
    )


@router.post("/graph/reset")
async def reset(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    device = graph.require_device(body.get("deviceId"))
    # Deleting every word is the one genuinely dangerous call in this API. The interface asks for the
    # word to be typed; the token is what stops a stray request.
    if str(body.get("confirm") or "").strip() != CONFIRMATION:
        raise ApiError(
            400,
            "confirmation_required",
            "This request must confirm that all words are to be deleted.",
        )
    return data(await run_in_threadpool(graph.tombstone_all_words, account, device))
