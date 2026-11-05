"""A companion service calling home for a text call, so the keys live in one container.

The clip service translates and aligns a clip's words with a language model. It used to call the
providers itself, with keys compose handed its container; now it sends Acervo the instructions and
the text, and Acervo walks its own chain and answers. The keys never leave Acervo's server, which is
the rule for every other caller (`docs/features/spoken-clips.md`).

**It is authenticated by the operator token**, the one secret Acervo and the clip service already
share: Acervo sends it to change the corpus's channels, and the clip service sends it back here. It
is not a session — the translation runs as one of that service's own jobs, long after the reader's
request that asked for it — and so there is no owner either: the call walks the providers in the
order they were added, which is what the clip service's text order always was.

The caller's `X-Request-ID` is adopted on the way in (`trace.py`), so its model calls are filed under
the clip service's id in the call log.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import bearer_token
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.errors import ApiError
from acervo.services.models import companion_text

router = APIRouter()


@router.post("/companion/text")
async def text(request: Request) -> JSONResponse:
    expected = request.app.state.settings.speech_operator_token.strip()
    offered = bearer_token(request)
    if not expected or not offered or not hmac.compare_digest(offered, expected):
        raise ApiError(401, "unauthenticated", "This route is for Acervo's companion services.",
                       noted={"why": "no operator token is configured" if not expected
                              else "the operator token did not match"})
    body = await json_body(request)
    return data(await run_in_threadpool(companion_text, request.app.state.settings, body))
