"""The application: routers, CORS, the error envelope, and the static surfaces."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acervo.api import auth, errors, static
from acervo.api.routes import (
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
from acervo.work import nightly, photos
from acervo.work.runner import Runner

API_ROOT = "/api/acervo/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or read_settings()
    runner = Runner(settings)
    # The one timed thing the server does for the owner. Only the served application ticks it: a runner built by a
    # test or a script runs jobs without queuing nights.
    runner.ticks.append(nightly.timer(settings, runner.clock))
    # Not timed work in that sense: file housekeeping for the photos nobody added.
    runner.ticks.append(photos.timer(settings, runner.clock))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # The runner lives exactly as long as the served application. A test client that is not
        # entered as a context manager never starts it, and drives `runner.run_until_idle()` itself.
        if settings.runner_enabled:
            runner.start()
        try:
            yield
        finally:
            runner.stop()

    app = FastAPI(title="Acervo", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = open_database(settings.database_path)
    app.state.runner = runner
    app.state.jwt_secret = auth.resolve_secret(settings)
    # Before the first request, because the first request is the one worth having a record of.
    open_call_log(settings)

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
        expose_headers=["Content-Length", "Content-Range"],
    )

    errors.install(app)

    api = APIRouter(prefix=API_ROOT)
    for module in (health, session, graph, articles, capture, chat, clips, dictionaries, events, images,
                   jobs, loops, mac_release, meaning, models, photo, pronunciations, reviews, rules,
                   schedule, speech, stories):
        api.include_router(module.router)
    app.include_router(api)

    # Registered last, so the two catch-alls it adds never shadow a real route.
    static.install(app)
    return app
