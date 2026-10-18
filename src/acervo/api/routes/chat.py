"""Chat: a question about one word in, prose and maybe a proposed edit out.

Writes nothing. A proposal is a suggestion the device applies to a draft and the reader approves;
the approval is an ordinary `POST /graph` through the same route every other writer uses. There is
no second write path here, and there is nothing to make one out of.

The model call runs in the threadpool for `capture.py`'s reason: one call of up to 120 seconds on
the event loop would stall every other request for two minutes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.repository import graph
from acervo.services.chat import report_refusal, run_chat

router = APIRouter()


@router.post("/chat")
async def chat(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    graph.require_device(body.get("deviceId"))
    return data(await run_in_threadpool(run_chat, request.app.state.settings, account, body))


@router.post("/chat/outcome")
async def chat_outcome(request: Request) -> JSONResponse:
    """A proposal the device refused once its repairs ran out. Logged, and nothing else."""
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    graph.require_device(body.get("deviceId"))
    return data(report_refusal(account, body))
