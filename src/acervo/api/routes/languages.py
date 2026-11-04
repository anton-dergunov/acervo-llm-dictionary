"""Settings ▸ Vocabularies: the languages a vocabulary may be kept in, and their varieties."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.services.languages import catalogue_view

router = APIRouter()


@router.get("/languages")
async def read(request: Request) -> JSONResponse:
    owner_id(request)
    return data(await run_in_threadpool(catalogue_view))
