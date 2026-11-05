"""Which providers this server holds, and which of their models this owner wants, in what order.

Two routes and no vocabulary. The choice is owner-scoped server state, never replicated: it decides
what the owner's words are *made of* — which model wrote a definition, at what cost, to what quality
— and an entry captured from a phone should be built by the same model as one captured from a
laptop. It also has to be readable by the server at request time, because the server is what calls
the model and the key never leaves it.

Deliberately **not** `schemaVersion`-gated. That number guards the replicated graph wire, and its
client-side twin decides whether a device's whole IndexedDB replica is wiped; bumping it for a route
that adds no field to any replicated record would wipe every replica for nothing. An old client
never calls this route, so there is nothing to protect.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.services.models import apply_selection, catalogue_view

router = APIRouter()


@router.get("/models")
def listing(request: Request) -> JSONResponse:
    """The providers, the families they can be added from, and this owner's chains.

    Owner-scoped: `chains` is this account's, and another account's choice is invisible here.
    """
    owner = owner_id(request)
    return data(catalogue_view(request.app.state.settings, owner))


@router.put("/models/selection")
async def selection(request: Request) -> JSONResponse:
    """Change the chains this request names, and answer with the whole readout.

    Validation, the write and the view are one threadpool call rather than three: the providers'
    keys are read from a file and the records from SQLite, and neither belongs on the event loop.
    """
    owner = owner_id(request)
    body = await json_body(request)
    return data(
        await run_in_threadpool(apply_selection, request.app.state.settings, owner, body)
    )
