"""`POST /articles`: save one parsed document (`docs/architecture/jobs.md`).

The device sends the `ArticleDraft` its YAML parsed into, and the server works out what that means
for the stored entry. `POST /graph` stays for raw record writes — study states, topics, vocabularies,
the Anki consumer — and an article goes through here.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.errors import ApiError
from acervo.repository import graph
from acervo.services import photo
from acervo.services.articles import save_article

router = APIRouter()


@router.post("/articles")
async def save(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    device = graph.require_device(body.get("deviceId"))
    minted = body.get("minted") or []
    if not isinstance(minted, list):
        raise ApiError(400, "invalid_input", "minted must be a list of record ids.")
    # A save enriches what it creates. An import's save asks for nothing, now or later: it queues no
    # job and marks every sense that arrives without a picture as having none (`docs/features/export.md`,
    # "Import"), so nothing an import brings in ever spends a provider by itself.
    imported = body.get("imported") is True
    return data(await run_in_threadpool(
        lambda: save_article(
            account, device, body.get("draft"), minted, enqueue=None if imported else graph.SAVE,
            imported=imported, base=body.get("base"),
            # Where a new word goes: the vocabulary in view, or the one chosen for it.
            vocabulary=body.get("vocabularyId"),
            # A photo taken for this word is kept by the save that names it (`services/photo.py`).
            place_photo=photo.placer(request.app.state.settings),
        )
    ))
