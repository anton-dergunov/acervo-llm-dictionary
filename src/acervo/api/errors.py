"""The one envelope.

Every response is `{"data": …}` or `{"error": {"code", "message"}}`. The client treats *any* body
without `data` as a generic failure, so FastAPI's `{"detail": …}` must never reach it — which is what
these three handlers are for.

It is also the one place every refusal passes through, so it is where a refusal is written down
(`acervo/activity.py`): the status, the code and the sentence the owner was shown, with whatever the
error itself noted for the log. A route gets that by raising — which is the reason a route never
builds an error response of its own.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from acervo import activity, trace
from acervo.errors import ApiError

logger = logging.getLogger("acervo.api")

GENERIC_FAILURE = "The Acervo server could not complete the request."

# Codes that are refused too often, and too uninterestingly, to be worth a line each. Empty until
# one earns its place here: silencing a code is a decision made from a real log, not ahead of one.
QUIET: frozenset[str] = frozenset()


def _note(request: Request, status: int, code: str, message: str, **noted: Any) -> None:
    if code in QUIET:
        return
    activity.refused(status, code, message, method=request.method, path=request.url.path, **noted)


def _crashed(raised: BaseException) -> None:
    """The traceback, to stderr, naming the request so it can be matched to its activity line."""
    logger.error("Acervo API request failed rid=%s", trace.current() or "-", exc_info=raised)


def data(payload: Any, status: int = 200) -> JSONResponse:
    return JSONResponse({"data": payload}, status_code=status)


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, raised: ApiError) -> JSONResponse:
        if raised.status >= 500:
            _crashed(raised)
        _note(request, raised.status, raised.code, raised.message, **raised.noted)
        return error(raised.status, raised.code, raised.message)

    @app.exception_handler(RequestValidationError)
    async def _invalid_input(request: Request, raised: RequestValidationError) -> JSONResponse:
        # A malformed body is the caller's mistake and gets the code the client already handles;
        # FastAPI's own 422 with a `detail` list would read as an unexplained failure.
        _note(request, 400, "invalid_input", "The request could not be read.")
        return error(400, "invalid_input", "The request could not be read.")

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, raised: HTTPException) -> JSONResponse:
        if raised.status_code >= 500:
            _crashed(raised)
            _note(request, raised.status_code, "server_error", str(raised.detail))
            return error(raised.status_code, "server_error", GENERIC_FAILURE)
        code = "not_found" if raised.status_code == 404 else "request_failed"
        _note(request, raised.status_code, code, str(raised.detail))
        return error(raised.status_code, code, str(raised.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, raised: Exception) -> JSONResponse:
        # An unhandled exception must not leak its internals. An error raised deliberately carries a
        # message written for the owner and is handled above. The log is not the wire: there the
        # exception's own words are the only thing that says what happened.
        _crashed(raised)
        _note(request, 500, "server_error", f"{type(raised).__name__}: {raised}")
        return error(500, "server_error", GENERIC_FAILURE)
