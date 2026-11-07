"""Figures about the owner's words that are derived rather than stored.

- `GET /words/rarity?language=xx` answers how common each live word is (`services/rarity.py`), for the
  make dialogs' "Rare" order. Read-only and cheap; a language with no frequency list is refused by
  name.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.services.rarity import rarity

router = APIRouter()


@router.get("/words/rarity")
async def read_rarity(request: Request, language: str = "") -> JSONResponse:
    owner = owner_id(request)
    return data(await run_in_threadpool(rarity, owner, language))
