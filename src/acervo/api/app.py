"""The application: routers, CORS, the error envelope, and the static surfaces."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from acervo import activity, logfiles, trace

from acervo.api import auth, errors, static
from acervo.api.routes import (
    anki,
    articles,
    capture,
    chat,
    clips,
    dictionaries,
    events,
    graph,
    health,
    schedule,
    images,
    loops,
    jobs,
    mac_release,
    meaning,
    models,
    photo,
    pronunciations,
    reviews,
    rules,
    session,
    speech,
    stories,
)
from acervo.repository.session import open_database
from acervo.services.models import open_call_log
from acervo.settings import Settings
from acervo.settings import settings as read_settings
from acervo.work import anki as anki_jobs
from acervo.work import nightly, photos
from acervo.work.runner import Runner

API_ROOT = "/api/acervo/v1"

log = logging.getLogger("acervo.api")


class RequestId:
    """Give every request the id its log lines are filed under, and say which in the response.

    A well-formed `X-Request-ID` is kept, so a caller that already has one — batch work, a companion
    service — goes on being the same piece of work on this side; anything else gets a new one.

    Pure ASGI rather than `@app.middleware`, and it never puts the old value back: each request runs
    in a task of its own, and the handler for an unhandled exception runs *outside* this middleware,
    where a restored value would leave the one line most worth joining without its id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = trace.begin(Headers(scope=scope).get(trace.HEADER, ""))

        async def stamped(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[trace.HEADER] = rid
            await send(message)

        await self.app(scope, receive, stamped)


def open_activity_log(settings: Settings) -> None:
    """Point the activity log at a file, if this deployment wants one. `open_call_log`'s twin, and
    not fatal for the same reason: a server that cannot write its log should still serve words."""
    if not settings.activity_log_path:
        return
    try:
        logfiles.open_rotating(activity.LOGGER, settings.activity_log_path,
                               settings.activity_log_bytes, settings.activity_log_keep)
    except OSError as unwritable:   # noqa: BLE001
        log.warning("Acervo: the activity log could not be opened (%s); refusals will not be "
                    "recorded", unwritable)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or read_settings()
    runner = Runner(settings)
    # The one timed thing the server does for the owner. Only the served application ticks it: a runner built by a
    # test or a script runs jobs without queuing nights.
    runner.ticks.append(nightly.timer(settings, runner.clock))
    # And the hourly read of Anki's review state, for an owner who has it on.
    runner.ticks.append(anki_jobs.timer(settings, runner.clock))
    # Not timed work in that sense: file housekeeping for the photos nobody added.
    runner.ticks.append(photos.timer(settings, runner.clock))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # The runner lives exactly as long as the served application. A test client that is not
        # entered as a context manager never starts it, and drives `runner.run_until_idle()` itself.
        if settings.runner_enabled:
            runner.start()
        # Which version came up, and when: the answer to "what changed before this broke". A deploy
        # is recorded here, by the server it started, rather than by the installer writing into a
        # file this process owns and rotates.
        activity.note("server start", version=settings.app_version, build=settings.app_build,
                      runner=settings.runner_enabled)
        try:
            yield
        finally:
            runner.stop()
            activity.note("server stop", version=settings.app_version, build=settings.app_build)

    app = FastAPI(title="Acervo", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = open_database(settings.database_path)
    app.state.runner = runner
    app.state.jwt_secret = auth.resolve_secret(settings)
    # Before the first request, because the first request is the one worth having a record of.
    open_call_log(settings)
    open_activity_log(settings)

    # PocketBase allowed every origin by default; FastAPI sends nothing. The macOS host loads its
    # interface from `acervo://app` and calls the server cross-origin with headers that trigger a
    # preflight, so without this every call fails inside the browser with no server-side log and the
    # client reports "The Acervo server could not be reached" — the wrong diagnosis, with no evidence
    # pointing anywhere near the truth. Credentials stay off: auth is a header, never a cookie.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Length", "Content-Range", trace.HEADER],
    )
    # Added after CORS, so it is the outer of the two and a preflight is a request like any other.
    app.add_middleware(RequestId)

    errors.install(app)

    api = APIRouter(prefix=API_ROOT)
    for module in (health, session, graph, anki, articles, capture, chat, clips, dictionaries, events, images,
                   jobs, loops, mac_release, meaning, models, photo, pronunciations, reviews, rules,
                   schedule, speech, stories):
        api.include_router(module.router)
    app.include_router(api)

    # Registered last, so the two catch-alls it adds never shadow a real route.
    static.install(app)
    return app
