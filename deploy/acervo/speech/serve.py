"""The speech container's command: the retrieval service, with Acervo's chain behind its providers.

`speech_retrieval.create_app` takes a `TranslationProvider` and a `WordAlignmentProvider` as
constructor arguments — a public entry point of that package — so the player's target text runs on
the owner's own chain without that repository gaining a LiteLLM dependency, a schema-dialect port or
an error-taxonomy mapping. It changes nothing at all (`docs/features/spoken-clips.md` §2.13).

This file is the only place the two projects' vocabularies meet, and it is deliberately thin: the
call itself is `acervo.speech.provider.ChainGenerator`, which imports nothing of this service's and
is tested from a virtualenv that does not carry FastAPI, uvicorn, yt-dlp or Stanza. What is here is
the wiring that knows this version's prompts, schemas and exception types.

Without `ACERVO_TEXT_CHAIN` and a credential, no providers are injected and the service falls back
to its own behaviour — the authored caption where one exists, and no target text where none does.
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
from acervo.speech.provider import ChainGenerator, GenerationFailed


class _Stage:
    """One stage, satisfying the service's Protocol structurally.

    `provider` and `model` name the **chain**, never the row that answered: the service caches on
    them, so a fall-through that moved them would miss the cache on every retry and re-translate
    work already paid for. What actually answered travels in `provider_metadata`.
    """

    def __init__(self, generator: ChainGenerator) -> None:
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

    Separate generators so the two stages are separate cache keys — the service keys them apart and
    they need not be served by the same model. Absent when nothing is configured, which leaves the
    service's own behaviour: the authored caption where one exists, and no target text where none.

    **The question asked here is the one the chain will ask.** An earlier version asked whether
    *any* text row was credentialed, ignoring `ACERVO_TEXT_CHAIN` — so a chain naming only rows
    this container lacks passed the guard, injected a provider, and failed every single clip with a
    message about a failure. "Translation is unavailable." is the truthful answer to that state,
    and it is only reachable by injecting nothing.
    """
    named = [part.strip() for part in os.environ.get("ACERVO_TEXT_CHAIN", "").split(",") if part.strip()]
    try:
        from acervo.models import chain, load_catalogue

        candidates = chain.resolve("text", named or None, load_catalogue())
    except Exception as error:   # noqa: BLE001 — a broken catalogue must not stop the corpus serving
        # Searching and playing must keep working; only the target text is lost. Said out loud,
        # because the first version of this swallowed a misplaced catalogue and the only symptom was
        # translations quietly never appearing.
        print(f"speech: the text chain could not be resolved ({error!r}); "
              "the player will show no target text", file=sys.stderr, flush=True)
        return None, None
    if not candidates:
        print("speech: no credentialed text provider; the player will show no target text",
              file=sys.stderr, flush=True)
        return None, None
    # What would answer, and in what order. This image carries no `acervo.admin`, so this line is
    # the only reading of it available on the deployment — and the one question worth being able to
    # answer from a log when the player shows nothing.
    print("speech: target text runs on " + ", ".join(
        f"{candidate.row.id}:{candidate.model}" for candidate in candidates
    ), file=sys.stderr, flush=True)
    return (
        AcervoTranslationProvider(ChainGenerator(named or None)),
        AcervoAlignmentProvider(ChainGenerator(named or None)),
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
