"""Forwarding a fixed set of retrieval routes to the corpus, on the browser's behalf.

The alternative — exposing the retrieval service to the browser directly — means a second hostname,
a second CORS configuration, an unauthenticated read API on the network, and the operator token for
channel mutations somewhere near a browser. The proxy costs one router and removes all four
(`docs/features/spoken-clips.md` §2.9). The retrieval service stays bound to the internal compose
network and is never published.

**The body is passed through verbatim**, which is the one place Acervo's `{"data": …}` envelope does
not apply, and it is deliberate: `web/src/clips.ts` builds the *packaged* typed client with this
proxy as its base URL, so the client that the retrieval repository ships and tests is used unchanged
rather than reimplemented against a rewrapped shape. Rewrapping would mean maintaining a second
copy of its response types in two languages, forever, to gain nothing.

**The operator token never leaves this process.** Acervo holds it as deployment configuration and
attaches it to the mutating channel calls, exactly as a provider key is held. Because the body is
forwarded rather than built here, that is enforced rather than merely intended: a forwarded body
containing the token is refused instead of passed on, so the test can assert the whole value is
absent from the whole response — the same assertion `GET /models` makes about a provider key.
"""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from acervo import trace
from acervo.errors import ApiError
from acervo.settings import Settings

# Longer than the corpus client's, because a search the browser is waiting on may be a cold query
# against a large index, and shorter than a model call, which never comes through here.
TIMEOUT_SECONDS = 30.0


class Forwarded:
    """What the corpus answered, to be returned as it stands."""

    __slots__ = ("status", "body", "media_type")

    def __init__(self, status: int, body: bytes, media_type: str) -> None:
        self.status = status
        self.body = body
        self.media_type = media_type


def _base(settings: Settings) -> str:
    if not settings.speech_url:
        raise ApiError(
            503, "corpus_unconfigured",
            "This Acervo server has no spoken-usage corpus configured.",
        )
    return settings.speech_url.rstrip("/")


def forward(settings: Settings, method: str, path: str, *,
            params: Mapping[str, Any] | None = None,
            json_body: Any = None,
            operator: bool = False,
            http: httpx.Client | None = None) -> Forwarded:
    """One allow-listed route, forwarded.

    `path` is built by the route function from typed path parameters, never from anything the
    client sent as a string — which is what makes this an allow-list rather than a pass-through with
    a filter in front of it.
    """
    url = f"{_base(settings)}{path}"
    headers: dict[str, str] = {"Accept": "application/json"}
    # The corpus logs under the id it is sent and says it back in an error, so what it refused can
    # be matched to the request that asked.
    if trace.current():
        headers[trace.HEADER] = trace.current()
    if operator:
        if not settings.speech_operator_token:
            raise ApiError(
                503, "corpus_unmanaged",
                "This Acervo server holds no operator token for the spoken-usage corpus, "
                "so its channel list cannot be changed from here.",
            )
        headers["Authorization"] = f"Bearer {settings.speech_operator_token}"

    client = http or httpx
    try:
        response = client.request(
            method, url, params=params, json=json_body, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except httpx.HTTPError:
        raise ApiError(
            502, "corpus_unreachable", "The spoken-usage corpus could not be reached."
        ) from None

    # The corpus has no reason to say its own bearer token back, so this can only fire on a bug in
    # that service — and a credential on its way to a browser is worth refusing loudly rather than
    # forwarding. It also lets the proxy assert the strong form the models route asserts: the whole
    # value is absent from the whole body, whatever the corpus said.
    if settings.speech_operator_token and settings.speech_operator_token.encode() in response.content:
        raise ApiError(
            502, "corpus_leaked_credential",
            "The spoken-usage corpus returned something that looks like its own operator token, "
            "so the response was not passed on.",
        )

    # Status and body as they stand, including the corpus's own error envelope: the packaged client
    # reads `{"error": {"code", "message"}, "request_id"}` and raises its own typed error from it.
    return Forwarded(
        response.status_code,
        response.content,
        response.headers.get("content-type", "application/json"),
    )
