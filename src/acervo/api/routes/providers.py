"""Adding, changing, checking and removing the providers this server may call.

Providers belong to the server, not to an account: every account on a server spends the same keys,
so any signed-in account may change them. Each route answers with the provider as Settings shows it
— never its key — and `GET /models` lists them all beside the orders.

Adding a provider and replacing its key both check the key first, with a call that spends nothing,
and store nothing when the provider refuses it (`services/providers.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.services import providers

router = APIRouter()


@router.post("/providers")
async def add(request: Request) -> JSONResponse:
    owner_id(request)
    body = await json_body(request)
    return data(await run_in_threadpool(providers.add, request.app.state.settings, body), status=201)


@router.put("/providers/{identifier}")
async def change(identifier: str, request: Request) -> JSONResponse:
    owner_id(request)
    body = await json_body(request)
    return data(await run_in_threadpool(providers.change, request.app.state.settings, identifier, body))


@router.post("/providers/{identifier}/check")
async def check(identifier: str, request: Request) -> JSONResponse:
    owner_id(request)
    return data(await run_in_threadpool(providers.check, request.app.state.settings, identifier))


@router.delete("/providers/{identifier}")
async def remove(identifier: str, request: Request) -> JSONResponse:
    owner_id(request)
    await run_in_threadpool(providers.remove, request.app.state.settings, identifier)
    return data({"removed": identifier})
