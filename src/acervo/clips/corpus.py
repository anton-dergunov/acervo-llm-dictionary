"""The narrow client against the spoken-usage corpus, and the only place its wire shape is read.

The corpus is a **separate repository and a separate service** (`docs/features/spoken-clips.md`
§2.2): Acervo does not hold it, does not import `speech_retrieval` and never opens its database. It
talks to one pinned `/api/v1` contract over HTTP, and the version it talks to is
`deploy/acervo/speech/pin.json`.

Written by hand rather than taken from the wheel, deliberately. Installing that package to reach it
would drag FastAPI, uvicorn, yt-dlp and simplemma into Acervo's image to make four GET requests, and
it would put the service *inside* the process the whole design keeps it outside of.

This module stands alone the way `models/cloudflare.py` does: no `acervo.settings`, no
`acervo.errors`, no graph. It speaks its own refusals and `services/clips.py` translates them, for
the same reason `acervo.models` decides *what kind of thing* went wrong while `services/models.py`
decides what Acervo's wire calls it.

**Everything the corpus says is turned into a `Candidate` here and nowhere else.** A raw response
dict must not escape this module — that is the rule `dictionary.ts` lives by for the artifact format,
and it is what makes a pinned-version bump one file to read rather than a search.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

TIMEOUT_SECONDS = 20.0

REQUEST_ID_HEADER = "X-Request-ID"

# The API caps at 50 and defaults to 20. Twenty is what `spoken-clips.md` §2.7 fixes as the bounded
# candidate set, and `docs/plans/quality/clip-selection.md` names the count as the first knob to
# vary — so it is a default here rather than a constant buried in a call.
CANDIDATE_LIMIT = 20


class CorpusError(Exception):
    """Something the corpus did that was not an answer.

    `reason` is this package's own vocabulary, not Acervo's wire codes:

    - `unreachable` — a timeout or a dropped connection.
    - `unavailable` — a 5xx, or a service that is not ready.
    - `rejected` — a **400**: a query this corpus will never accept, whatever happens next. Over
      five tokens, or a language it does not know. Not a failure, and the caller marks the word
      searched rather than leaving it for a sweep that would ask the same question forever.
    - `refused` — anything else terminal.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Candidate:
    """One segment the corpus offers, in the only shape the rest of Acervo sees.

    `matched_surface` is the corpus's `match.text`, which it guarantees occurs verbatim in
    `sentence` at `[char_start:char_end]`. That guarantee is what lets `Example.matchedForm` hold
    it — the invariant is verbatim, untrimmed and un-normalised — and the selector re-checks it
    anyway rather than trusting a promise across a service boundary.
    """

    segment_id: str
    sentence: str
    matched_surface: str
    char_start: int
    char_end: int
    clip_start: float
    clip_end: float
    video_url: str
    video_title: str
    channel: str
    caption_kind: str
    speech_style: tuple[str, ...]
    varieties: tuple[str, ...]
    boundary_reason: str
    rank: int

    @property
    def start_second(self) -> int:
        """The stored start. Floored, because a clip must begin at or before the speech does."""
        return max(0, math.floor(self.clip_start))

    @property
    def end_second(self) -> int:
        """The stored end. Ceiled, for the same reason, and always after the start."""
        return max(self.start_second + 1, math.ceil(self.clip_end))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(_text(one) for one in value if _text(one)) if isinstance(value, list) else ()


def _candidate(row: Any) -> Candidate | None:
    """One result row, or nothing if it is missing what a clip cannot do without."""
    if not isinstance(row, dict):
        return None
    match = row.get("match") if isinstance(row.get("match"), dict) else {}
    video = row.get("video") if isinstance(row.get("video"), dict) else {}
    boundary = row.get("boundary") if isinstance(row.get("boundary"), dict) else {}
    segment_id, sentence, url = _text(row.get("segment_id")), _text(row.get("sentence")), _text(video.get("url"))
    # `videoRef` is what every clip field hangs on, so a row without one is not a candidate at all.
    if not (segment_id and sentence and url):
        return None
    return Candidate(
        segment_id=segment_id,
        sentence=sentence,
        matched_surface=_text(match.get("text")),
        char_start=int(match.get("char_start") or 0),
        char_end=int(match.get("char_end") or 0),
        clip_start=float(row.get("clip_start") or 0.0),
        clip_end=float(row.get("clip_end") or 0.0),
        video_url=url,
        video_title=_text(video.get("title")),
        channel=_text(video.get("channel")),
        caption_kind=_text(video.get("caption_kind")),
        speech_style=_strings(video.get("speech_style")),
        varieties=_strings(video.get("varieties")),
        boundary_reason=_text(boundary.get("reason")),
        rank=int(row.get("rank") or 0),
    )


def _unique(rows: Iterable[Candidate]) -> tuple[Candidate, ...]:
    """One entry per segment, keeping the best rank.

    The corpus answers per *occurrence*, so a sentence saying the word twice arrives twice. Offering
    the same sentence to the model twice spends candidate budget on nothing and invites it to pick
    the one the request did not index.
    """
    best: dict[str, Candidate] = {}
    for row in rows:
        held = best.get(row.segment_id)
        if held is None or row.rank < held.rank:
            best[row.segment_id] = row
    return tuple(sorted(best.values(), key=lambda row: (row.rank, row.segment_id)))


@dataclass(frozen=True)
class Operation:
    """An update or rebuild the corpus is running, as far as Acervo needs to know it."""

    id: str
    status: str
    successful: bool | None
    error: str | None

    @property
    def finished(self) -> bool:
        return self.status not in ("queued", "running")


class Corpus:
    """Read routes, the operator's update route, and no retries.

    No retries for `client.py`'s reason: a caller that wants them owns them, and a retry layer here
    would change how a job behaves without changing a line of the job.
    """

    def __init__(self, base_url: str, *, timeout: float = TIMEOUT_SECONDS,
                 http: httpx.Client | None = None, operator_token: str = "",
                 request_id: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # The seam `AcervoClient` uses, and how the fake corpus is injected in tests.
        self._http = http
        # Sent only on the operator routes. It never leaves this process.
        self._operator_token = operator_token
        # Whose work this is, as the caller's own logs name it. The corpus logs under it and says
        # it back in an error, so a refusal there can be matched to the search that caused it.
        self._request_id = request_id

    def _get(self, path: str, params: dict[str, Any] | None = None, *,
             operator: bool = False) -> Any:
        return self._send("GET", path, params=params, operator=operator)

    def _send(self, method: str, path: str, *, params: dict[str, Any] | None = None,
              body: Any = None, operator: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        headers = {
            **({"Authorization": f"Bearer {self._operator_token}"} if operator else {}),
            **({REQUEST_ID_HEADER: self._request_id} if self._request_id else {}),
        }
        try:
            if method == "GET":
                sender = self._http.get if self._http is not None else httpx.get
                response = sender(url, params=params, timeout=self.timeout,
                                  **({"headers": headers} if headers else {}))
            else:
                sender = self._http.post if self._http is not None else httpx.post
                response = sender(url, json=body, timeout=self.timeout,
                                  **({"headers": headers} if headers else {}))
        except httpx.HTTPError as error:
            raise CorpusError("unreachable", str(error)) from None

        if response.status_code == 400:
            raise CorpusError("rejected", _message(response))
        if response.status_code == 503:
            raise CorpusError("unavailable", _message(response))
        if response.status_code >= 500:
            raise CorpusError("unavailable", f"The corpus answered with status {response.status_code}.")
        if response.status_code >= 400:
            raise CorpusError("refused", _message(response))
        try:
            return response.json()
        except ValueError:
            raise CorpusError("refused", "The corpus did not answer with JSON.") from None

    def status(self) -> dict[str, Any]:
        """What the corpus holds. `ready` is false until an index exists, and that is a 200.

        `indexed_languages` is the one field a caller must read before searching: a language the
        corpus does not index yet may be indexed later, so a word in one has not been *consulted*
        and must not be marked as though it had.

        `translation` is about the *player's* target text, not the article's — a different surface
        with a different owner (`docs/features/spoken-clips.md` §2.13). It is carried because it is
        the one thing about this service that can be switched off without anything saying so: the
        player renders one grey sentence whether no provider is configured, the chain has no
        credential here, or a model answered badly, and there was nowhere to read which.
        """
        payload = self._get("/status")
        if not isinstance(payload, dict):
            raise CorpusError("refused", "The corpus did not describe itself.")
        translation = payload.get("translation")
        translation = translation if isinstance(translation, dict) else {}
        return {
            "ready": bool(payload.get("ready")),
            "builtAt": _text(payload.get("built_at")) or None,
            "indexedLanguages": _strings(payload.get("indexed_languages")),
            "videos": int(payload.get("videos") or 0),
            "segments": int(payload.get("segments") or 0),
            "translation": {
                "available": bool(translation.get("provider_available")),
                "provider": _text(translation.get("provider")) or None,
                "model": _text(translation.get("model")) or None,
            },
        }

    def search(self, language: str, query: str, *, limit: int = CANDIDATE_LIMIT) -> tuple[Candidate, ...]:
        """The bounded candidate set for one word.

        `match_mode=auto` unions surface and contiguous lemma matches, which is why the lemma is
        the right query: `estar podrido de` retrieves `estoy podrido de`. `order=ranked` is the
        corpus's own quality order — the model is the last gate, not the retrieval mechanism.
        """
        payload = self._get(
            "/search",
            {"language": language, "q": query, "match_mode": "auto", "order": "ranked",
             "limit": max(1, min(int(limit), 50))},
        )
        if not isinstance(payload, dict):
            raise CorpusError("refused", "The corpus did not answer with a search result.")
        rows = payload.get("results")
        if not isinstance(rows, list):
            return ()
        found = (_candidate(row) for row in rows)
        return _unique(row for row in found if row is not None)


    # ── the operator's routes ─────────────────────────────────────────────────

    def start_update(self, operation: str = "update") -> Operation:
        """Ask the corpus to fetch what its enabled channels have new, and rebuild its index.

        One runs at a time on that side: asking while one is active answers with the active one, so
        a nightly run and an Update now follow the same operation rather than starting two.
        """
        payload = self._send(
            "POST", "/corpus/operations", body={"operation": operation}, operator=True
        )
        return _operation(payload)

    def operation(self, operation_id: str) -> Operation:
        return _operation(self._get(f"/corpus/operations/{operation_id}", operator=True))


def _operation(payload: Any) -> Operation:
    if not isinstance(payload, dict) or not _text(payload.get("operation_id")):
        raise CorpusError("refused", "The corpus did not describe the operation.")
    successful = payload.get("successful")
    return Operation(
        id=_text(payload.get("operation_id")),
        status=_text(payload.get("status")) or "failed",
        successful=successful if isinstance(successful, bool) else None,
        error=_text(payload.get("error")) or None,
    )


def _message(response: httpx.Response) -> str:
    """The corpus's own error message, which is `{"error": {"code", "message"}}`."""
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return _text(error.get("message")) if isinstance(error, dict) else ""
