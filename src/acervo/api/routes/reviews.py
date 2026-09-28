"""The review history: the worker adds to it, and anything may ask what it says.

`POST /reviews` keeps a batch of a learning system's reviews and `GET /reviews/latest` says where
the history it holds ends, so the next pull knows where to start. `GET /stats` is the history read
as figures, in the owner's own days.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.repository import reviews
from acervo.services import reviews as history
from acervo.services.schedule import zone, zone_name

router = APIRouter()


def _bounded(value: str | None, default: int, low: int, high: int) -> int:
    try:
        return min(high, max(low, int(value))) if value else default
    except ValueError:
        return default


@router.post("/reviews")
async def keep(request: Request) -> JSONResponse:
    owner = owner_id(request)
    system, rows = history.parse(await json_body(request))
    return data(await run_in_threadpool(reviews.record, owner, system, rows))


@router.get("/reviews/latest")
def latest(request: Request) -> JSONResponse:
    owner = owner_id(request)
    system = (request.query_params.get("system") or "anki").strip()
    return data({"system": system, "reviewId": reviews.latest(owner, system)})


@router.get("/stats")
async def stats(request: Request) -> JSONResponse:
    owner = owner_id(request)
    settings = request.app.state.settings
    language = (request.query_params.get("language") or "").strip() or None
    days = _bounded(request.query_params.get("days"), 365, 7, 3660)
    weeks = _bounded(request.query_params.get("weeks"), 12, 1, 520)
    local = zone(settings)

    def read() -> dict:
        figures = history.statistics(
            reviews.history(owner, language=language), reviews.topic_names(owner),
            zone=local, today=datetime.now(local).date(), days=days, weeks=weeks,
        )
        return {"language": language, "zone": zone_name(settings), **figures}

    return data(await run_in_threadpool(read))
