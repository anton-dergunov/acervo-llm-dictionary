"""The one HTTP client against the Acervo API.

Batch jobs write through this, against the service's own graph route: same route, same validation,
same revision allocation as a phone. One writer process, one pipeline — the rule capture transports
already live by, where adding a transport must not add a second pipeline.

It replaces two copies of the same thirty lines, which had drifted apart in three ways that each
mattered: one used a 600-second timeout and the other 300; one carried the error `code` and the other
threw it away; and both inferred the method from the body, so a bodyless POST — which is what
`/graph/reset` and `/session/refresh` are — could not be expressed at all.

**No retries live here.** Waiting out a busy provider is the server's job runner's decision, made in
one place; a retry layer inside the transport would be a second one that nobody else knew about.
"""

from __future__ import annotations

from typing import Any, Self

import httpx

from acervo.domain import SCHEMA_VERSION

API_PATH = "/api/acervo/v1"

# The route that spends two model calls of up to 120 seconds each, and the ordinary one. Named here
# because a caller choosing a timeout should be choosing between known values, not inventing one.
CAPTURE_TIMEOUT = 600.0
DEFAULT_TIMEOUT = 300.0


class AcervoError(Exception):
    """A refusal from the service, or a failure to reach it.

    `code` is the server's own error code and is what callers dispatch on — an empty one means the
    request never got an answer, which is deliberately not retryable.
    """

    def __init__(self, message: str, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class AcervoClient:
    """One connection to one Acervo service, reused across calls."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""
        # A reused connection is the point: a publish writes thousands of records and a file walk
        # makes hundreds of sequential captures, and a fresh TCP and TLS handshake for each is pure
        # latency.
        #
        # `http` is how a test points this at an application in the same process rather than at a
        # socket — Starlette's `TestClient` is an `httpx.Client`, so a write path can be exercised
        # over the real routes with no server to start. A borrowed client is not ours to close.
        self._http = http or httpx.Client(timeout=timeout, follow_redirects=False)
        self._owns_http = http is None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    # ── the three layers ────────────────────────────────────────────────
    # Each is the one below it plus exactly one decision: `fetch` decides nothing, `raw` decides how
    # to read a body, `call` decides what counts as a failure.

    def fetch(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        anonymous: bool = False,
    ) -> httpx.Response:
        """The response, whatever it is. For a byte range, or a body that is not JSON."""
        sent = {"Accept": "application/json", **(headers or {})}
        if self.token and not anonymous:
            sent["Authorization"] = f"Bearer {self.token}"
        # Only when overridden: the client already carries a default, and a borrowed one refuses a
        # per-request timeout it has no socket to apply it to.
        overrides = {"timeout": timeout} if timeout is not None and self._owns_http else {}
        try:
            return self._http.request(
                method.upper(),
                f"{self.base_url}{path}",
                json=body,
                params=params,
                headers=sent,
                **overrides,
            )
        except httpx.HTTPError as unreachable:
            raise AcervoError(
                f"The Acervo server could not be reached: {unreachable}"
            ) from unreachable

    def raw(self, method: str, path: str, **options: Any) -> tuple[int, dict[str, Any]]:
        """The status and the whole envelope, without deciding that a 4xx is an exception."""
        response = self.fetch(method, path, **options)
        try:
            envelope = response.json()
        except ValueError:
            envelope = {}
        return response.status_code, envelope if isinstance(envelope, dict) else {}

    def call(self, method: str, path: str, **options: Any) -> Any:
        """The `data` the service returned, or `AcervoError`.

        `data` is returned as it arrives, including a bare `None` — `/mac-release` answers
        `{"data": null}` to mean "no release published", and collapsing that into `{}` would make an
        answer indistinguishable from an empty one.
        """
        status, envelope = self.raw(method, path, **options)
        if not 200 <= status < 300 or "data" not in envelope:
            problem = envelope.get("error") or {}
            raise AcervoError(
                problem.get("message") or f"The server refused the request ({status}).",
                problem.get("code", ""),
                status,
            )
        return envelope["data"]

    # ── the routes a job or a script actually uses ──────────────────────

    def sign_in(self, email: str, password: str) -> str:
        result = self.call("POST", f"{API_PATH}/session", body={"email": email, "password": password})
        self.token = result["token"]
        return self.token

    def health(self) -> dict[str, Any]:
        return self.call("GET", f"{API_PATH}/health", anonymous=True, timeout=15.0)

    def models(self) -> dict[str, Any]:
        """The catalogue as this owner sees it, and their chains, one kind at a time.

        A batch job on a laptop reads this to find out which providers the owner chose, then
        resolves that order against its *own* catalogue and its own credentials — the order is a
        preference and the credentials are a fact about the machine.
        """
        return self.call("GET", f"{API_PATH}/models")

    def pull_graph(self, since: int = 0) -> dict[str, Any]:
        return self.call(
            "GET", f"{API_PATH}/graph", params={"since": since, "schemaVersion": SCHEMA_VERSION}
        )

    def push_graph(self, changes: dict[str, list[dict]], *, device_id: str) -> dict[str, Any]:
        """One batch, all of it or none of it. A stale revision anywhere refuses the whole thing."""
        return self.call(
            "POST",
            f"{API_PATH}/graph",
            body={"schemaVersion": SCHEMA_VERSION, "deviceId": device_id, "changes": changes},
        )

    def latest_review(self, system: str) -> int | None:
        """Where the review history the server holds for this system ends: the newest review id."""
        return self.call("GET", f"{API_PATH}/reviews/latest", params={"system": system})["reviewId"]

    def push_reviews(self, system: str, reviews: list[dict[str, Any]], *, batch: int = 2000) -> dict[str, int]:
        """Add reviews to the history, a batch at a time. One already held adds nothing, so sending
        a window that overlaps the last one is safe."""
        totals = {"received": 0, "added": 0, "known": 0, "skipped": 0}
        for start in range(0, len(reviews), batch):
            answer = self.call("POST", f"{API_PATH}/reviews",
                               body={"system": system, "reviews": reviews[start:start + batch]})
            for key in totals:
                totals[key] += int(answer.get(key, 0))
        return totals

    def submit_capture(self, *, device_id: str, **request: Any) -> dict[str, Any]:
        """Queue a headless capture. Answers at once with the job; the words are its output."""
        return self.call(
            "POST",
            f"{API_PATH}/captures",
            body={"schemaVersion": SCHEMA_VERSION, "deviceId": device_id, **request},
        )

    def job(self, job_id: str) -> dict[str, Any]:
        """One job the server is doing, with its steps and the jobs it created."""
        return self.call("GET", f"{API_PATH}/jobs/{job_id}")

    def capture(self, *, device_id: str, timeout: float = CAPTURE_TIMEOUT, **request: Any) -> dict[str, Any]:
        """Propose one entry for review. Writes nothing."""
        return self.call(
            "POST",
            f"{API_PATH}/capture",
            body={"schemaVersion": SCHEMA_VERSION, "deviceId": device_id, **request},
            timeout=timeout,
        )
