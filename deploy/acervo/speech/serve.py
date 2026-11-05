"""The speech container's command: the retrieval service, with Acervo behind its providers.

`speech_retrieval.create_app` takes a `TranslationProvider` and a `WordAlignmentProvider` as
constructor arguments — a public entry point of that package — so the player's target text is
written by Acervo's own providers without that repository gaining a LiteLLM dependency, a
schema-dialect port or an error-taxonomy mapping (`docs/features/spoken-clips.md` §2.13). This
container holds no provider key: each call goes home to Acervo's `POST /companion/text`.

This file is the only place the two projects' vocabularies meet, and it is deliberately thin: the
call itself is `acervo.speech.provider.AcervoGenerator`, which imports nothing of this service's and
is tested from a virtualenv that does not carry FastAPI, uvicorn, yt-dlp or Stanza. What is here is
the wiring that knows this version's prompts, schemas and exception types.

Without Acervo's address and the operator token, no providers are injected and the service falls
back to its own behaviour — the authored caption where one exists, and no target text where none
does. With them, a server that has no provider says so on each clip, as any refusal does.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import uvicorn

from speech_retrieval.api import create_app
from speech_retrieval.prompt_registry import (
    ALIGNMENT_PROMPT,
    TRANSLATION_PROMPT,
    TRANSLATION_SCHEMA,
    alignment_schema,
)
from speech_retrieval.settings import Settings
from speech_retrieval.translations import (
    InvalidProviderOutput,
    ProviderAlignmentRequest,
    ProviderResponse,
    ProviderTranslationRequest,
    TranslationProviderError,
)

from acervo.access_log import quiet_health_probes
from acervo.speech.provider import AcervoGenerator, GenerationFailed


class _Stage:
    """One stage, satisfying the service's Protocol structurally.

    `provider` and `model` name the **order**, never the provider that answered: the service caches on
    them, so a fall-through that moved them would miss the cache on every retry and re-translate
    work already paid for. What actually answered travels in `provider_metadata`.
    """

    def __init__(self, generator: AcervoGenerator) -> None:
        self._generator = generator
        self.provider = generator.provider
        self.model = generator.model

    async def _call(self, *, instructions: str, user_text: str, schema,
                    temperature: float) -> ProviderResponse:
        """One stage, off the event loop.

        `generate` is synchronous — LiteLLM's `completion` is — and awaiting it inline would hold
        the single uvicorn loop for the length of a model call. Nothing else in this container
        would answer meanwhile: not a search, not a clip, not its own healthcheck, which allows
        three seconds. Two stages at a sixty-second timeout is two minutes of a service that is
        running perfectly and reports itself unhealthy.
        """
        try:
            answer = await asyncio.to_thread(
                self._generator.generate,
                instructions=instructions, user_text=user_text, schema=schema,
                temperature=temperature,
            )
        except GenerationFailed as failed:
            if failed.code == "invalid_output":
                raise InvalidProviderOutput(str(failed), failed.raw) from None
            raise TranslationProviderError(
                failed.code, str(failed), retryable=failed.retryable
            ) from None
        return ProviderResponse(
            payload=answer.payload,
            latency_ms=answer.latency_ms,
            usage=answer.usage,
            raw_output=answer.raw_output,
            provider_metadata=answer.provider_metadata,
        )

    async def aclose(self) -> None:
        await self._generator.aclose()


class AcervoTranslationProvider(_Stage):
    async def translate(self, request: ProviderTranslationRequest) -> ProviderResponse:
        reference = (
            "\nAuthored target-language reference (possibly free or incomplete):\n"
            + request.authored_reference
            if request.authored_reference
            else ""
        )
        return await self._call(
            instructions=TRANSLATION_PROMPT.text,
            user_text=(
                f"Source language: {request.source_language}\n"
                f"Target language: {request.target_language}\n"
                f"Source text:\n{request.source_text}{reference}"
            ),
            schema=TRANSLATION_SCHEMA,
            temperature=TRANSLATION_PROMPT.temperature,
        )


class AcervoAlignmentProvider(_Stage):
    async def align(self, request: ProviderAlignmentRequest) -> ProviderResponse:
        def token_lines(tokens) -> str:
            return "\n".join(
                f"{token.id}: {json.dumps(token.text, ensure_ascii=False)}" for token in tokens
            )

        return await self._call(
            instructions=ALIGNMENT_PROMPT.text,
            user_text=(
                f"Source language: {request.source_language}\n"
                f"Target language: {request.target_language}\n"
                f"Source text: {request.source_text}\n"
                f"Target text: {request.target_text}\n\n"
                f"Source tokens:\n{token_lines(request.source_tokens)}\n\n"
                f"Target tokens:\n{token_lines(request.target_tokens)}"
            ),
            schema=alignment_schema(
                [token.id for token in request.source_tokens],
                [token.id for token in request.target_tokens],
            ),
            temperature=ALIGNMENT_PROMPT.temperature,
        )


def providers():
    """Both stages, or neither.

    Separate generators so the two stages are separate cache keys and separate lines in Acervo's
    call log. Absent when this container has not been told where Acervo is or what the operator
    token is, which leaves the service's own behaviour: the authored caption where one exists, and
    no target text where none. Said out loud, because the only symptom otherwise is translations
    quietly never appearing.
    """
    url = os.environ.get("ACERVO_API_URL", "").strip()
    token = os.environ.get("SPEECH_RETRIEVAL_OPERATOR_TOKEN", "").strip()
    if not url or not token:
        print("speech: no Acervo address or operator token; the player will show no target text",
              file=sys.stderr, flush=True)
        return None, None
    print(f"speech: target text is written by Acervo at {url}", file=sys.stderr, flush=True)
    return (
        AcervoTranslationProvider(AcervoGenerator(url, token, "clip-translate")),
        AcervoAlignmentProvider(AcervoGenerator(url, token, "clip-align")),
    )


def main() -> None:
    settings = Settings.from_env()
    translation, alignment = providers()
    app = create_app(settings, translation_provider=translation, alignment_provider=alignment)
    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="info")
    quiet_health_probes("/api/v1/health/live")
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
