"""The one place the environment is read.

Deliberately not cached. `llmSettings()` in the hook this replaces re-read the environment on every
request, and several behaviours depend on that: health reports what the server is configured with
*now*, and the tests flip a variable between two calls to the same process. A module-level cache
would turn both into stale answers.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Everything the service reads from its environment, and nothing it reads from anywhere else."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_version: str = Field(default="0.0.0", alias="ACERVO_APP_VERSION")
    app_build: str = Field(default="0", alias="ACERVO_APP_BUILD")

    database_path: Path = Field(default=Path("/var/lib/acervo/server/acervo.db"), alias="ACERVO_DB_PATH")
    # Empty means "mint one beside the database and keep it": a restart must not sign everyone out,
    # and a local run must not need configuring.
    jwt_secret: str = Field(default="", alias="ACERVO_JWT_SECRET")

    web_path: Path = Field(default=Path("/app/web"), alias="ACERVO_WEB_PATH")
    downloads_path: Path = Field(default=Path("/var/lib/acervo/downloads"), alias="ACERVO_DOWNLOADS_PATH")
    dictionaries_path: Path = Field(default=Path("/var/lib/acervo/dictionaries"), alias="ACERVO_DICTIONARIES_PATH")
    # Sense images and, later, audio. Served like a dictionary artifact rather than like the
    # interface: behind auth, Range-capable, and outside anything a service worker precaches.
    media_path: Path = Field(default=Path("/var/lib/acervo/media"), alias="ACERVO_MEDIA_PATH")
    prompts_path: Path = Field(default=Path("/app/prompts"), alias="ACERVO_PROMPTS_PATH")

    # Every model call, one line each, rotating. Beside the database rather than on a mount of its
    # own: it is small, it is bounded, and it belongs to the same deployment the database does.
    # Empty switches it off — the lines are then simply not written anywhere, which is what a
    # laptop run wants. Nothing else changes either way.
    call_log_path: Path = Field(
        default=Path("/var/lib/acervo/server/model-calls.log"), alias="ACERVO_CALL_LOG_PATH"
    )
    call_log_bytes: int = Field(default=5_000_000, alias="ACERVO_CALL_LOG_BYTES")
    call_log_keep: int = Field(default=3, alias="ACERVO_CALL_LOG_KEEP")

    # And every job the runner takes, the same way and for the same reasons. A separate file rather
    # than a level in the first: one is written on every model call and is read for timings, the
    # other is written a few times a job and is read when something failed. Mixing them would make
    # both greps worse. Smaller, because a job writes three lines where a capture writes thirty.
    job_log_path: Path = Field(
        default=Path("/var/lib/acervo/server/jobs.log"), alias="ACERVO_JOB_LOG_PATH"
    )
    job_log_bytes: int = Field(default=2_000_000, alias="ACERVO_JOB_LOG_BYTES")
    job_log_keep: int = Field(default=3, alias="ACERVO_JOB_LOG_KEEP")

    @property
    def takes_path(self) -> Path:
        """The take cache, beside the database and the call log rather than on the media volume.

        A take is a cache, not a record's media: nothing references it, nothing replicates it, and
        the media route must not serve it. Server-local state belongs beside the database, which is
        also why this needs no new mount and no new environment variable.
        """
        return self.database_path.parent / "takes"

    @property
    def maps_path(self) -> Path:
        """The meaning map's embedding cache and its drawn maps, beside the database for the take
        cache's reasons: derived, server-local, never served as a file, and needing no new mount."""
        return self.database_path.parent / "maps"

    # Where the spoken-usage corpus answers, on the internal network. Empty means this deployment
    # runs without one: reads still work and the interface says the corpus is unavailable rather
    # than failing, exactly as it does for an unreachable external dictionary.
    speech_url: str = Field(default="", alias="ACERVO_SPEECH_URL")

    # Where the loop generator answers, on the internal network. Empty means this deployment runs
    # without one: everything else works and asking for a loop says so, exactly as an absent corpus
    # behaves.
    lexibeat_url: str = Field(default="", alias="ACERVO_LEXIBEAT_URL")
    # Authorises channel management on that service. It never leaves this process — the proxy
    # attaches it, and no route returns it — for the reason a provider key never leaves it either.
    speech_operator_token: str = Field(default="", alias="ACERVO_SPEECH_OPERATOR_TOKEN")

    # Which providers answer, in order, as ids from `models/catalogue.json`. Empty means every row
    # this deployment is credentialed for, in catalogue order — so a server with one provider
    # configured needs nothing set here at all.
    #
    # The credentials themselves are deliberately absent from this class. A provider's key variable
    # is named by its catalogue row and read from the environment there, because the catalogue is
    # the only place a provider's facts are written down; listing them here too would be a second
    # source of truth that drifts the first time a row is added.
    text_chain: str = Field(default="", alias="ACERVO_TEXT_CHAIN")

    # The zone the nightly hour in Settings ▸ Schedule is read in, as an IANA name. Empty means the
    # server's own local zone — which in a container is usually UTC, so a deployment sets this.
    timezone: str = Field(default="", alias="ACERVO_TIMEZONE")

    # The Anki sync server and the robot's own collection (`docs/features/anki.md`). The robot is
    # just another sync client, so it holds a collection of its own: here, in the directory the
    # one-shot worker mounts too, so the two share one collection and one lock. Unset endpoint or
    # credentials mean this server has no Anki behind it, and nothing Anki runs.
    anki_sync_endpoint: str = Field(default="", alias="ACERVO_ANKI_SYNC_ENDPOINT")
    anki_sync_username: str = Field(default="", alias="ACERVO_ANKI_SYNC_USERNAME")
    anki_sync_password: str = Field(default="", alias="ACERVO_ANKI_SYNC_PASSWORD")
    anki_data_path: Path = Field(default=Path("/var/lib/acervo/worker"), alias="ACERVO_ANKI_DATA_PATH")
    anki_template_path: Path = Field(default=Path("/app/templates"), alias="ACERVO_ANKI_TEMPLATE_DIR")
    # Seconds media sync may go without progress before the robot gives up on it.
    anki_media_timeout: float = Field(default=120.0, alias="ACERVO_ANKI_MEDIA_TIMEOUT")

    @property
    def anki_configured(self) -> bool:
        return bool(self.anki_sync_endpoint and self.anki_sync_username and self.anki_sync_password)

    # Whether this process runs the job runner (`acervo/work/`). Always on in a deployment; off only
    # for a process that must serve without working, which is none today.
    runner_enabled: bool = Field(default=True, alias="ACERVO_RUNNER")

    # PocketBase allowed every origin by default and FastAPI sends nothing. The macOS host loads its
    # interface from `acervo://app` and calls the server cross-origin with headers that trigger a
    # preflight, so a missing header here fails every call inside the browser with no server-side log.
    cors_origins: str = Field(default="*", alias="ACERVO_CORS_ORIGINS")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
