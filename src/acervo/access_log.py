"""Keep the container's own healthcheck out of the access log.

Docker probes each service's health route every minute (`deploy/acervo/compose.yaml`), and every
probe used to be an access-log line. Synology's log driver keeps those lines in an indexed database,
so the probe was a write of its own and its lines buried the requests worth reading. A probe that
answers 200 is dropped; one that fails is still logged, because then it is news.

It imports nothing of Acervo's, so the corpus service's launcher can use it as well as the server.
"""

from __future__ import annotations

import logging


class _HealthProbeFilter(logging.Filter):
    def __init__(self, paths: frozenset[str]) -> None:
        super().__init__()
        self.paths = paths

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn's access record: (client, method, path with query string, HTTP version, status).
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        return not (args[2] in self.paths and args[4] == 200)


def quiet_health_probes(*paths: str) -> None:
    """Drop successful requests for `paths` from `uvicorn.access`.

    Call it after `uvicorn.Config(...)` and before the server runs: building the config is what
    applies uvicorn's logging setup, so the filter is added to the logger that setup leaves behind.
    """
    logging.getLogger("uvicorn.access").addFilter(_HealthProbeFilter(frozenset(paths)))
