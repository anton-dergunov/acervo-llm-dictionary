"""One structured model call, answered by Acervo, for the retrieval service to use.

The retrieval service's two stages — translate, then align — are each "send these instructions and
this text, get this JSON schema back". This container holds no provider key: it sends both to
Acervo's `POST /companion/text`, authenticated by the operator token the two already share, and
Acervo walks its own providers and answers (`api/routes/companion.py`). The keys live in one
container, and a provider added in Settings is the one the next clip is translated by.

**It reports the order, never the provider that answered.** The service caches a translation under
the `provider` and `model` its provider declares, so a fall-through that changed those would miss the
cache on every retry and re-translate work already paid for. Naming the order means a clip
translated by the second provider is found again when the first recovers, which is the behaviour the
cache exists for. That is the opposite of the rule for a *stored* record — an `Example.modelId` names
the model that did the work — and the difference is that one is provenance and the other is a cache
key.

**The shape is said, not sent.** The retrieval service's two prompts name no field at all — they
end with "Return only the requested structured result" and leave the shape entirely to a schema,
which is how its own native adapter works. So the schema is rendered into the instructions here,
in JSON Schema's spelling rather than Google's, and that text is the whole contract.

It is not *also* sent as a constrained schema, and that is a measured decision rather than a
stylistic one — see `docs/architecture/models.md`, "Constrained decoding is not used, anywhere". The
alignment stage was the strongest case for sending one, because its schema restricts every id to an
enum of this request's own tokens. Measured against constructed ground truth it bought no accuracy
at any size it worked at, and above roughly a hundred tokens the provider rejected the schema
outright with a 400. Saying the shape costs a few hundred tokens and works at every size.

This module imports nothing of Acervo's but the request id, and nothing at all of the retrieval
service's — the dialect rename is a pure dict walk that names no package.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from acervo import trace


class GenerationFailed(Exception):
    """A stage that did not produce a usable answer.

    `retryable` carries the one distinction the retrieval service acts on, and it is the same one
    Acervo's refusal codes already draw: a provider that is busy says nothing about the request,
    while a rejected credential is a mistake to fix rather than a condition to wait out.
    `raw` is the model's own output where there was one, for the service's invalid-output path.
    """

    def __init__(self, code: str, message: str, *, retryable: bool, raw: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.raw = raw


@dataclass(frozen=True)
class Generated:
    """What one stage produced, in the shape the service's own provider responses have."""

    payload: dict[str, Any]
    latency_ms: float
    usage: dict[str, int] | None
    raw_output: str
    provider_metadata: dict[str, str] | None = None


# Google's GenAI dialect spells the type keywords in capitals; JSON Schema, which Acervo's prompts
# speak, spells them in lower case. Nothing else about the two differs for the shapes that arrive
# here, so this is a rename rather than a translation — and it is a no-op on a schema that was
# already JSON Schema, which is why it is applied unconditionally rather than sniffed for.
_TYPES = frozenset({"OBJECT", "ARRAY", "STRING", "NUMBER", "INTEGER", "BOOLEAN", "NULL"})


def _keyword(value: Any) -> Any:
    """One type keyword, lower-cased if it is one. An `enum`'s values are data and never reach here."""
    return value.lower() if isinstance(value, str) and value.upper() in _TYPES else value


def json_schema(value: Any) -> Any:
    """The same schema, with its type keywords in JSON Schema's spelling."""
    if isinstance(value, dict):
        renamed = {}
        for name, member in value.items():
            if name != "type":
                renamed[name] = json_schema(member)
            elif isinstance(member, list):
                renamed[name] = [_keyword(entry) for entry in member]
            else:
                renamed[name] = _keyword(member)
        return renamed
    if isinstance(value, list):
        return [json_schema(entry) for entry in value]
    return value


# Acervo's refusal codes, in the service's smaller set, and whether waiting could help.
_CODES: dict[str, tuple[str, bool]] = {
    "llm_rate_limited": ("rate_limited", True),
    "llm_unavailable": ("temporarily_unavailable", True),
    "llm_unreachable": ("temporarily_unavailable", True),
    "llm_unusable": ("invalid_output", True),
    "llm_empty": ("invalid_output", True),
}


class AcervoGenerator:
    """Acervo's providers, presented as one `generate` call.

    `stage` names the call in Acervo's call log — `clip-translate` or `clip-align` — so a slow clip
    can be told from a slow capture.
    """

    provider = "acervo-chain"
    model = "deployment-default"

    def __init__(self, url: str, token: str, stage: str, *, timeout: float = 180.0) -> None:
        self._url = url.rstrip("/") + "/companion/text"
        self._token = token
        self._stage = stage
        # Long enough for Acervo to walk several providers at sixty seconds each.
        self._timeout = timeout

    def generate(self, *, instructions: str, user_text: str, schema: Any,
                 temperature: float | None = None) -> Generated:
        started = time.perf_counter()
        shape = json_schema(schema)
        # The only statement of the shape there is. The retrieval service's own prompts name no
        # field and no schema is sent, so without this line no model could answer either stage.
        instructions = (
            f"{instructions}\n\nReturn a single JSON object, and nothing else, matching this JSON "
            f"Schema:\n{json.dumps(shape, ensure_ascii=False)}"
        )
        body: dict[str, Any] = {"instructions": instructions, "text": user_text, "caller": self._stage}
        if temperature is not None:
            body["temperature"] = temperature
        try:
            response = httpx.post(self._url, json=body, timeout=self._timeout, headers={
                "Authorization": f"Bearer {self._token}",
                trace.HEADER: trace.current() or trace.mint(),
            })
        except httpx.HTTPError as error:
            raise GenerationFailed("temporarily_unavailable",
                                   f"Acervo could not be reached: {error}", retryable=True) from None
        try:
            answer = response.json()
        except ValueError:
            answer = {}
        if not response.is_success or not isinstance(answer.get("data"), dict):
            refused = answer.get("error") if isinstance(answer.get("error"), dict) else {}
            code, retryable = _CODES.get(str(refused.get("code")), ("provider_unavailable", False))
            raise GenerationFailed(code, str(refused.get("message") or f"Acervo answered {response.status_code}"),
                                   retryable=retryable)
        data = answer["data"]
        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise GenerationFailed(
                "invalid_output", "The language model did not return a JSON object.",
                retryable=True, raw=json.dumps(payload, ensure_ascii=False),
            )
        return Generated(
            payload=payload,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            usage=None,
            raw_output=json.dumps(payload, ensure_ascii=False),
            # What actually answered, for the service's own provenance record. Deliberately here
            # and not in `provider`/`model`, which are the cache key and must not move.
            provider_metadata={"answered_by": f"{data.get('provider')}:{data.get('model')}"},
        )

    async def aclose(self) -> None:
        """Nothing to close: each call is its own connection."""
        return None
