"""The narrow client against the LexiBeat loop service, and the only place its wire shape is read.

LexiBeat is a **separate repository and a separate service** (`docs/features/loops.md`
§2.1): Acervo does not hold the music engine, does not import `lexibeat`, and never opens its output
directory. It talks to one pinned `/api/v1` contract over HTTP, and the version it talks to is
`deploy/acervo/lexibeat/pin.json`.

Written by hand rather than taken from the wheel, exactly as `clips/corpus.py` is. Installing that
package to reach it would drag numpy, scipy, soundfile and pedalboard into Acervo's image to make
four HTTP requests, and it would put the renderer *inside* the process the whole design keeps it
outside of.

This module stands alone: no `acervo.settings`, no `acervo.errors`, no graph. It speaks its own
refusals and `services/loops.py` translates them, for the reason `acervo.models` decides *what kind
of thing* went wrong while `services/models.py` decides what Acervo's wire calls it.

**Nothing the service says escapes this module as a raw dict.** A pinned-version bump is one file to
read rather than a search — the rule `dictionary.ts` lives by for the artifact format.

The operation vocabulary is deliberately the corpus's: `operation_id`, `status`, `successful`,
`error`. `work/loop.py` can then be `work/corpus.py` with a different noun rather than a second way
of following a long-running thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

# A render is minutes of work, but every *request* here is small: starting one, asking after it, and
# fetching the finished track. The track is the only one that can be large.
TIMEOUT_SECONDS = 30.0
TRACK_TIMEOUT_SECONDS = 120.0

REQUEST_ID_HEADER = "X-Request-ID"


class LoopError(Exception):
    """Something the loop service did that was not an answer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Family:
    """One kind of music, with the words the generator gives a listener to choose it by."""

    id: str
    label: str
    description: str


@dataclass(frozen=True)
class Switch:
    """A choice a format offers the listener: on or off, or one of named `choices`."""

    label: str
    default: bool | str
    choices: tuple[str, ...] = ()

    def accepts(self, value: Any) -> bool:
        if self.choices:
            return isinstance(value, str) and value in self.choices
        return isinstance(value, bool)


@dataclass(frozen=True)
class Format:
    """One kind of loop the generator can make, with the words it gives a listener to choose it by.

    What a format *is made of* is the generator's (its `docs/programme-format.md`) and is never read
    here; Acervo names one, sets its switches, and says what it requires.
    """

    id: str
    label: str
    description: str
    switches: dict[str, Switch] = field(default_factory=dict)
    # What a render needs: `writer` (a model that writes the lines) and `multilingual_voice` (a voice
    # that can say words of two languages in one line). A missing one renders the fallback.
    requires: tuple[str, ...] = ()
    # What a render makes instead when a requirement is missing, or None when it is refused.
    fallback: str | None = None
    bars_per_item: int = 0


@dataclass(frozen=True)
class Schema:
    """What this deployment of the generator can be asked for.

    The catalogues are **its**, never copied here: a family or a format added in a later version
    appears in the dialog with nothing changing on this side.
    """

    api_version: str
    engine_version: str
    # Complete, not merely present: a bundle missing files renders thinner beds rather than failing.
    production_bundle: bool
    # Which bundle, from its own manifest. The generator's container looks for the one `pin.json`
    # names, so a stale volume reads as no bundle at all; this is for saying which one answered.
    bundle_version: str
    formats: tuple[Format, ...]
    # The kinds of music there are. `auto` is not one of them: it is the absence of a choice, and
    # the generator leaves it out of these for that reason.
    families: tuple[Family, ...]
    max_items: int

    @property
    def sample_free(self) -> bool:
        """No sample bundle, so only the synthesised palette is available.

        Not an error and not a refusal — the service serves perfectly well in this state, which is
        why its healthcheck asserts liveness. It is worth *saying*, because the difference is
        recorded instruments against oscillators rather than a slightly plainer bed.
        """
        return not self.production_bundle


@dataclass(frozen=True)
class Item:
    """One word of a loop, as the generator receives it."""

    source: str
    target: str
    direction: str = ""

    def to_wire(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "direction": self.direction}


@dataclass(frozen=True)
class Loop:
    """A finished render, as far as Acervo needs to know it: the loop, its words, its lines.

    `format` is the one rendered, and `fallback_from` the one asked for when a requirement was
    missing. `script` is the writer's text as the generator read it, kept to render the same lines
    again; it is the generator's shape and is stored, never read, on this side.
    """

    audio_url: str
    audio_mime: str
    duration_seconds: float
    format: str
    fallback_from: str | None
    style_id: str
    seed: int
    engine_version: str
    bed_fingerprint: str
    bpm: float
    items: tuple[dict[str, Any], ...]
    cues: tuple[dict[str, Any], ...]
    script: dict[str, Any] | None = None


@dataclass(frozen=True)
class Operation:
    """A render the service is running, as far as Acervo needs to know it."""

    id: str
    status: str
    successful: bool | None
    error: str | None
    fraction: float
    message: str
    result: Loop | None = None

    @property
    def finished(self) -> bool:
        return self.status not in ("queued", "running")


class LoopService:
    """Start a render, follow it, fetch the track. No retries, for `client.py`'s reason: a caller
    that wants them owns them, and a retry layer here would change how a job behaves without
    changing a line of the job."""

    def __init__(self, base_url: str, *, timeout: float = TIMEOUT_SECONDS,
                 http: httpx.Client | None = None, request_id: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Whose work this is, as the caller's own logs name it. Sent on every request so the
        # service can file its side under the same id; this module does not know what mints one.
        self._headers = {REQUEST_ID_HEADER: request_id} if request_id else {}
        # The seam a test injects a fake service through, as `Corpus` takes one.
        self._http = http

    # -- requests ------------------------------------------------------------

    def schema(self) -> Schema:
        payload = self._send("GET", "/schema")
        return Schema(
            api_version=_text(payload.get("api_version")),
            engine_version=_text(payload.get("engine_version")),
            production_bundle=payload.get("production_bundle") is True,
            bundle_version=_text((payload.get("bundle") or {}).get("version")),
            formats=tuple(_format(row) for row in payload.get("formats") or []
                          if isinstance(row, dict) and _text(row.get("id"))),
            families=tuple(
                Family(_text(row.get("id")), _text(row.get("label")), _text(row.get("description")))
                for row in payload.get("family_details") or [] if isinstance(row, dict)
            ),
            max_items=_int((payload.get("limits") or {}).get("max_items")),
        )

    def alive(self) -> bool:
        try:
            return _text(self._send("GET", "/health").get("status")) == "ok"
        except LoopError:
            return False

    def start(self, *, items: Iterable[Item], source_language: dict[str, str],
              target_language: dict[str, str], token: str, delivery: str,
              format: str = "classic", switches: dict[str, bool | str] | None = None,
              script: dict[str, Any] | None = None, family: str = "auto",
              seed: int | None = None, palette: str = "hybrid") -> Operation:
        """Ask for one loop. `token` is the render-scoped credential the generator calls home with.

        It is the *whole* of what the generator is given to speak with: no provider key reaches that
        container, so a token that is absent or refused is a render with no voice rather than one
        that quietly falls back to something else.

        `delivery` goes with it because the generator cannot find it out: only this side knows which
        order the owner chose, and that is what decides whether a repetition is its own recording
        with its own director note or one recording varied there by pitch and speed.

        `script` is a previous render's, sent back so the same lines are said again — new music for
        a radio lesson — with no writer call.
        """
        body: dict[str, Any] = {
            "items": [item.to_wire() for item in items],
            "source_language": source_language,
            "target_language": target_language,
            "format": format,
            "switches": dict(switches or {}),
            "family": family,
            "palette": palette,
            "speech": {"token": token, "delivery": delivery},
        }
        if seed is not None:
            body["seed"] = seed
        if script is not None:
            body["script"] = script
        return _operation(self._send("POST", "/loops", body=body))

    def operation(self, operation_id: str) -> Operation:
        return _operation(self._send("GET", f"/operations/{operation_id}"))

    def cancel(self, operation_id: str) -> Operation:
        return _operation(self._send("DELETE", f"/operations/{operation_id}"))

    def track(self, audio_url: str) -> tuple[bytes, str]:
        """The finished MP3, stored exactly as it arrives. Acervo re-encodes nothing."""
        client = self._http or httpx.Client(timeout=TRACK_TIMEOUT_SECONDS)
        try:
            answer = client.get(_join(self.base_url, audio_url), headers=self._headers)
        except httpx.HTTPError as failure:
            raise LoopError("unreachable", f"The loop generator could not be reached: {failure}") from None
        if answer.status_code != 200:
            raise LoopError("no_track", _message(answer) or "That loop has no track.")
        return answer.content, answer.headers.get("content-type", "audio/mpeg").split(";")[0]

    # -- transport -----------------------------------------------------------

    def _send(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        client = self._http or httpx.Client(timeout=self.timeout)
        try:
            answer = client.request(method, self.base_url + path, json=body,
                                    timeout=self.timeout, headers=self._headers)
        except httpx.HTTPError as failure:
            raise LoopError("unreachable", f"The loop generator could not be reached: {failure}") from None
        if answer.status_code == 429:
            raise LoopError("busy", _message(answer) or "The loop generator is busy.")
        if answer.status_code >= 400:
            raise LoopError("refused", _message(answer) or f"The loop generator answered {answer.status_code}.")
        try:
            payload = answer.json()
        except ValueError:
            raise LoopError("refused", "The loop generator did not answer with JSON.") from None
        if not isinstance(payload, dict):
            raise LoopError("refused", "The loop generator did not describe what it did.")
        return payload


def _operation(payload: Any) -> Operation:
    if not isinstance(payload, dict) or not _text(payload.get("operation_id")):
        raise LoopError("refused", "The loop generator did not describe the render.")
    successful = payload.get("successful")
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    return Operation(
        id=_text(payload.get("operation_id")),
        status=_text(payload.get("status")) or "failed",
        successful=successful if isinstance(successful, bool) else None,
        error=_text(payload.get("error")) or None,
        fraction=_float(progress.get("fraction")),
        message=_text(progress.get("message")),
        result=_loop(payload.get("result")),
    )


def _format(row: dict[str, Any]) -> Format:
    switches: dict[str, Switch] = {}
    for name, spec in (row.get("switches") or {}).items():
        if not isinstance(spec, dict):
            continue
        choices = tuple(_text(choice) for choice in spec.get("choices") or [])
        default = spec.get("default")
        switches[_text(name)] = Switch(
            label=_text(spec.get("label")),
            default=_text(default) if choices else default is True,
            choices=choices)
    return Format(
        id=_text(row.get("id")), label=_text(row.get("label")),
        description=_text(row.get("description")), switches=switches,
        requires=tuple(_text(need) for need in row.get("requires") or []),
        fallback=_text(row.get("fallback")) or None,
        bars_per_item=_int(row.get("bars_per_item")))


def _loop(payload: Any) -> Loop | None:
    if not isinstance(payload, dict) or not _text(payload.get("audio_url")):
        return None
    script = payload.get("script")
    return Loop(
        audio_url=_text(payload.get("audio_url")),
        audio_mime=_text(payload.get("audio_mime")) or "audio/mpeg",
        duration_seconds=_float(payload.get("duration_seconds")),
        format=_text(payload.get("format")),
        fallback_from=_text(payload.get("fallback_from")) or None,
        style_id=_text(payload.get("style_id")),
        seed=_int(payload.get("seed")),
        engine_version=_text(payload.get("engine_version")),
        bed_fingerprint=_text(payload.get("bed_fingerprint")),
        bpm=_float(payload.get("bpm")),
        items=_items(payload.get("items")),
        cues=_cues(payload.get("cues")),
        script=script if isinstance(script, dict) else None,
    )


def _items(payload: Any) -> tuple[dict[str, Any], ...]:
    """One row per word, built key by key rather than passed through: nothing of the service's own
    shape leaves this module. A side the format never says in its words section has no reveal."""
    built: list[dict[str, Any]] = []
    for index, row in enumerate(payload if isinstance(payload, list) else []):
        if not isinstance(row, dict):
            continue
        built.append({
            "index": _int(row.get("index")) if row.get("index") is not None else index,
            # What the render says it said, which the caller checks against what it asked for.
            "source": _text(row.get("source")),
            "target": _text(row.get("target")),
            "start": _float(row.get("start")),
            "end": _float(row.get("end")),
            "source_reveal": _optional_float(row.get("source_reveal")),
            "target_reveal": _optional_float(row.get("target_reveal")),
        })
    return tuple(built)


def _cues(payload: Any) -> tuple[dict[str, Any], ...]:
    """Every line of the loop in the order it is heard, key by key.

    `group` is what a player shows together: a word's own lines, a line and its translation.
    `item` is the word a line belongs to, as an index into the request's items, or None.
    """
    built: list[dict[str, Any]] = []
    for row in payload if isinstance(payload, list) else []:
        if not isinstance(row, dict) or not _text(row.get("text")):
            continue
        built.append({
            "kind": _text(row.get("kind")),
            "section": _text(row.get("section")),
            "group": _int(row.get("group")),
            "item": _int(row.get("item")) if row.get("item") is not None else None,
            "side": _text(row.get("side")) or None,
            "role": _text(row.get("role")) or "native",
            "language": _text(row.get("language")),
            "text": _text(row.get("text")),
            "take": _int(row.get("take")),
            "start": _float(row.get("start")),
            "end": _float(row.get("end")),
        })
    return tuple(built)


def _message(answer: httpx.Response) -> str:
    """The generator's own error shape, which is `{"error": {"code", "message"}}`."""
    try:
        body = answer.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return _text(error.get("message")) if isinstance(error, dict) else ""


def _join(base: str, path: str) -> str:
    """A path the service gave us, resolved against its own base.

    Never concatenated from anything a *client* sent: `audio_url` comes out of an answer this module
    parsed, which is the only thing that makes joining it safe.
    """
    if path.startswith(("http://", "https://")):
        return path
    root = base[: -len("/api/v1")] if base.endswith("/api/v1") else base
    return root.rstrip("/") + "/" + path.lstrip("/")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> float | None:
    return None if value is None else _float(value)
