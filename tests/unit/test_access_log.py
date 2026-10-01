from __future__ import annotations

import logging

import pytest
import uvicorn

from acervo.access_log import quiet_health_probes

HEALTH = "/api/acervo/v1/health"


def access(path: str, status: int) -> logging.LogRecord:
    """A record shaped the way uvicorn's access logger makes one."""
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:45592", "GET", path, "1.1", status), None,
    )


@pytest.fixture
def access_logger():
    logger = logging.getLogger("uvicorn.access")
    before = list(logger.filters)
    yield logger
    logger.filters[:] = before


def test_a_successful_probe_is_dropped_and_everything_else_is_kept(access_logger):
    quiet_health_probes(HEALTH)

    assert not access_logger.filter(access(HEALTH, 200))
    assert access_logger.filter(access("/api/acervo/v1/words", 200))
    # A failing probe is the one worth reading.
    assert access_logger.filter(access(HEALTH, 503))
    # Not the probe: Docker never sends one with a query string.
    assert access_logger.filter(access(f"{HEALTH}?verbose=1", 200))


def test_a_record_that_is_not_an_access_line_is_kept(access_logger):
    quiet_health_probes(HEALTH)

    plain = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 0, "started", None, None)
    assert access_logger.filter(plain)


def test_the_filter_survives_uvicorns_own_logging_setup(access_logger):
    """Building the config applies uvicorn's logging setup, so the filter is added afterwards — and
    must then still be there for the server that config runs."""
    uvicorn.Config(lambda scope, receive, send: None, log_level="info")
    quiet_health_probes(HEALTH)

    assert not access_logger.filter(access(HEALTH, 200))
