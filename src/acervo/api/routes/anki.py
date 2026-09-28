"""Settings ▸ Anki: the two switches, how the last push and read went, and Push now / Read now."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.errors import ApiError
from acervo.repository import anki_settings, jobs
from acervo.services import anki

router = APIRouter()

SUBJECTS = {"push": anki_settings.PUSH, "pull": anki_settings.PULL}


def _view(settings, owner: str) -> dict:
    chosen = anki_settings.settings(owner)
    return {
        "configured": settings.anki_configured,
        "push": chosen.push,
        "pull": chosen.pull,
        "lastPush": jobs.latest_of_kind(owner, anki_settings.PUSH),
        "lastPull": jobs.latest_of_kind(owner, anki_settings.PULL),
    }


@router.get("/anki")
def read(request: Request) -> JSONResponse:
    return data(_view(request.app.state.settings, owner_id(request)))


@router.put("/anki/settings")
async def write(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    settings = request.app.state.settings
    await run_in_threadpool(anki.apply_settings, settings, owner, body)
    return data(_view(settings, owner))


@router.post("/anki/{what}")
async def now(request: Request, what: str) -> JSONResponse:
    """Push now, or Read now: due at once, even if a push was waiting for the writes to stop."""
    owner = owner_id(request)
    kind = SUBJECTS.get(what)
    if kind is None:
        raise ApiError(404, "not_found", "Anki can be pushed to or read from.")
    anki.robot(request.app.state.settings)  # refuses on a server with no Anki behind it

    def queue() -> dict:
        queued = jobs.enqueue(owner, kind, trigger="manual", subject_kind=anki_settings.SUBJECT,
                              subject_id=what)
        return jobs.hasten(queued["id"]) or queued

    return data(await run_in_threadpool(queue), status=202)
