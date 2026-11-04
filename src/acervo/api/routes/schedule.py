"""Settings ▸ Activity: the nightly hour, its step switches, and how the last run went."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.repository import jobs
from acervo.services.schedule import apply_settings, settings_view

router = APIRouter()


def _view(settings, owner: str, view: dict) -> dict:
    return {**view, "lastRun": jobs.latest_of_kind(owner, "nightly")}


@router.get("/schedule/settings")
def read(request: Request) -> JSONResponse:
    owner = owner_id(request)
    settings = request.app.state.settings
    return data(_view(settings, owner, settings_view(settings, owner)))


@router.put("/schedule/settings")
async def write(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    settings = request.app.state.settings
    view = await run_in_threadpool(apply_settings, settings, owner, body)
    return data(_view(settings, owner, view))
