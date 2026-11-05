"""Adding, changing, checking and removing the providers this server may call, and asking one what
it has.

Providers belong to the server, not to an account: every account on a server spends the same keys,
so any signed-in account may change them. A change answers with everything `GET /models` answers —
the providers, never a key, and this owner's orders — plus the id of the provider it changed,
because removing a model or a provider also takes it out of the orders, and the page should render
what the server holds rather than guess it.

Adding a provider and replacing its key both check the key first, with a call that spends nothing,
and store nothing when the provider refuses it (`services/providers.py`). Asking a provider for its
models or a model's voices is the same kind of call, made when "Add a model" or a voice model's page
opens.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.services import providers
from acervo.services.models import catalogue_view

router = APIRouter()


async def _readout(request: Request, change: Callable[[], str]) -> dict[str, Any]:
    """Make one change, then answer with the whole readout: one threadpool call, since the keys are
    read from a file and the rows from SQLite."""
    owner = owner_id(request)
    settings = request.app.state.settings

    def run() -> dict[str, Any]:
        identifier = change()
        return {**catalogue_view(settings, owner), "provider": identifier}

    return await run_in_threadpool(run)


@router.post("/providers")
async def add(request: Request) -> JSONResponse:
    owner_id(request)
    body = await json_body(request)
    settings = request.app.state.settings
    return data(await _readout(request, lambda: providers.add(settings, body)["id"]), status=201)


@router.put("/providers/{identifier}")
async def change(identifier: str, request: Request) -> JSONResponse:
    owner_id(request)
    body = await json_body(request)
    settings = request.app.state.settings
    return data(await _readout(request, lambda: providers.change(settings, identifier, body)["id"]))


@router.post("/providers/{identifier}/check")
async def check(identifier: str, request: Request) -> JSONResponse:
    settings = request.app.state.settings
    return data(await _readout(request, lambda: providers.check(settings, identifier)["id"]))


@router.delete("/providers/{identifier}")
async def remove(identifier: str, request: Request) -> JSONResponse:
    settings = request.app.state.settings

    def removed() -> str:
        providers.remove(settings, identifier)
        return identifier

    return data(await _readout(request, removed))


@router.get("/providers/{identifier}/models")
async def models(identifier: str, request: Request, kind: str = "text") -> JSONResponse:
    owner_id(request)
    return data(await run_in_threadpool(providers.offered_models, request.app.state.settings, identifier, kind))


@router.get("/providers/{identifier}/voices")
async def voices(identifier: str, request: Request, model: str = "") -> JSONResponse:
    owner_id(request)
    return data(await run_in_threadpool(providers.offered_voices, request.app.state.settings, identifier, model))
