"""What this server has asked of each model, against the free allowances the owner set.

One route, read by every Usage page in Settings ▸ Providers: the counters behind it are the server's
rather than an account's, like the providers they count, so any signed-in account sees the same
answer. It spends nothing and calls no provider.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.services.usage import view

router = APIRouter()


@router.get("/usage")
def listing(request: Request) -> JSONResponse:
    """Today, this month and all time per provider and model, each model's last thirty days, and
    every gauge measured against its allowance's own period. A plain `def`: FastAPI runs it in its
    threadpool, which the SQLite reads and the secrets file want."""
    owner_id(request)
    return data(view(request.app.state.settings))
