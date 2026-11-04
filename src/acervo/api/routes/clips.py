"""Finding real speech for a word that is already saved: Settings ▸ Clips's routes.

The owner's two switches, and what the corpus holds — apart, because the second is a call to
another service and the first must not wait for it. Finding itself is work (`find_clips`), whose
unit is one corpus search plus one text call for a whole lexeme, which
is the granularity §2.7 fixes: the batching is load-bearing rather than an optimisation, because a
model that sees every sense of one word at once can tell which of them a fragment is an instance of,
and that judgement is the entire reason to spend a frontier call here at all.

Deliberately **not** `schemaVersion`-gated, for `routes/images.py`'s reason: that number guards the
replicated graph wire and its client twin wipes replicas, and these routes add no field to any
record beyond what `POST /graph` already carries. The rows they write go through `merge_graph` and
are gated there like every other write.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.repository import graph
from acervo.services.clips import apply_settings, corpus_view, settings_view

router = APIRouter()


@router.get("/clips/settings")
def read_settings(request: Request) -> JSONResponse:
    return data(settings_view(owner_id(request)))


@router.put("/clips/settings")
async def write_settings(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    return data(await run_in_threadpool(apply_settings, owner, body))


@router.get("/clips/corpus")
async def read_corpus(request: Request) -> JSONResponse:
    """What the corpus holds. Its own route because it is a call to another service, made in a
    thread so a slow corpus holds up nothing else."""
    owner_id(request)
    return data(await run_in_threadpool(corpus_view, request.app.state.settings))
