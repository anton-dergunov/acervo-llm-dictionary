"""The lexibeat container's command: LexiBeat's loop service, with Acervo's voice behind it.

`lexibeat.service.create_service` takes a `backend_factory` — a public entry point of that package —
so the speech a loop is made of runs on the **owner's** chain without this container holding a
provider credential, a model catalogue, a rate limiter or a cooldown store. It calls home instead,
to `POST /pronunciations/take` for every line and to `POST /loops/write` for a format whose lines a
writer model writes, with a render-scoped token that arrives in the request and lives in the process
and nowhere else (docs/features/loops.md §2.3).

This file is the only place the two projects' vocabularies meet, and it is deliberately thin.
LexiBeat sees a `Backend` and a `Writer`; Acervo sees an authenticated HTTP client. If the balance ever changes —
if it became worth running LiteLLM in here — it is this file that changes and nothing else.

There is no startup dependency in either direction. Render requests arrive *from* the server, so the
server is up whenever a call comes home.
"""

from __future__ import annotations

import io
import os
import sys
import time

import httpx
import numpy as np
import soundfile
import uvicorn

from lexibeat.service import RenderContext, ServiceConfig, create_service
from lexibeat.voice import (
    BackendCapabilities,
    SpeechRequest,
    SynthesisResult,
    delivery_instruction,
    register_secret,
)
from lexibeat.writer import WriteRequest

# How Acervo describes a take on the wire, and what the two answers mean here.
DIRECTED, PLAIN = "directed", "plain"

# One line of a loop, over a chain that may be resting. Generous, because nobody is watching it
# arrive — the job polls an operation — and a take that times out costs the whole render.
TAKE_TIMEOUT = 180.0
# A whole programme's lines in one model call, over a chain that may walk several pairs.
WRITE_TIMEOUT = 300.0


def _capabilities(delivery: str) -> BackendCapabilities:
    """What this backend can do, which depends on which order the owner chose for loops.

    This is the whole of what §2.7's setting buys, and it cannot be guessed from in here — so Acervo
    states it in the request.

    **Directed**: the voice takes a director note, so each repetition is its own note and its own
    model call — three a line, ~72 for a twelve-word loop. LexiBeat must not *also* vary them
    locally, or every take is varied twice.

    **Plain**: the voice takes nothing, so one call a line is enough and LexiBeat varies the
    repetitions itself by pitch and speed — ~24 calls. This is also the state a deployment with no
    instruction-following voice lands in, and it is why a dropped direction is a useful answer rather
    than a failure: three distinguishable takes, no emotion, and nothing on either side branching.

    `languages=()` means "any": which languages can be spoken is the owner's chain's answer, and a
    table in here would be a second, wrong copy of it.

    **Mixing languages** in one line — a remark in English that quotes the Spanish word — is what an
    instruction-following voice does and a plain one does not, so it follows the same answer. A
    format that needs it renders its plainer fallback on a plain voice, and says so.
    """
    if delivery == PLAIN:
        return BackendCapabilities("post-process", "post-process", "preset", languages=())
    return BackendCapabilities("instruction", "instruction", "preset", languages=(),
                               mixes_languages=True)


class AcervoVoice:
    """LexiBeat's `Backend`, satisfied structurally, over one authenticated route."""

    name = "acervo"
    model_id = "acervo:pronunciations/take"
    load_seconds = 0.0

    def __init__(self, base_url: str, token: str, delivery: str) -> None:
        self.capabilities = _capabilities(delivery)
        self.sample_rate = 24_000  # replaced by whatever the answer actually carries
        self._delivery = delivery
        self._url = base_url.rstrip("/") + "/pronunciations/take"
        self._token = token
        self._http = httpx.Client(timeout=TAKE_TIMEOUT)

    def synth(self, request: SpeechRequest) -> SynthesisResult:
        started = time.perf_counter()
        # Directed: the *whole* director note, prosody words included, because the model is the only
        # thing varying the repetitions. Plain: nothing, and the same take index every time, so
        # Acervo answers all three repetitions from one cached recording rather than paying for
        # three identical ones. `take` is in Acervo's cache key, which is what makes that work.
        directed = self._delivery != PLAIN
        body = {
            "text": request.text,
            "language": request.language.code,
            "direction": delivery_instruction(request.delivery) if directed else None,
            "take": request.delivery.take if directed else 0,
            # Who says it. Acervo answers a guide line in the owner's guide voice, where one is set.
            "role": request.role,
        }
        answer = self._http.post(
            self._url, json=body, headers={"Authorization": f"Bearer {self._token}"}
        )
        if answer.status_code != 200:
            # Acervo's own message, which already names what the owner can do about it — a chain with
            # no voice for this language, an exhausted allowance, a rotated key. Re-wording it here
            # would only lose that.
            raise RuntimeError(
                f"Acervo refused a take ({answer.status_code}): {_message(answer)}"
            )

        audio, rate = soundfile.read(io.BytesIO(answer.content), dtype="float32", always_2d=True)
        return SynthesisResult(
            np.asarray(audio, dtype=np.float32).mean(axis=1),
            int(rate),
            time.perf_counter() - started,
            {
                "provider": answer.headers.get("x-acervo-provider", ""),
                "model": answer.headers.get("x-acervo-model", ""),
                "voice": answer.headers.get("x-acervo-voice", ""),
                # `sent`, `dropped` or `none`. Recorded rather than acted on: what to do about a
                # dropped direction was decided when the capabilities were declared.
                "direction": answer.headers.get("x-acervo-direction", ""),
                "delivery": self._delivery,
            },
            "instruction-rate" if directed else "local-post-process",
        )

    def close(self) -> None:
        self._http.close()


class AcervoWriter:
    """LexiBeat's `Writer`, satisfied structurally, over `POST /loops/write`.

    One call per render, for a format whose lines a model writes. The owner's text chain answers —
    its rate limits, its cooldowns, its call log — and the generator reads the text itself.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self._url = base_url.rstrip("/") + "/loops/write"
        self._token = token

    def write(self, request: WriteRequest) -> str:
        with httpx.Client(timeout=WRITE_TIMEOUT) as http:
            answer = http.post(self._url, json={"prompt": request.prompt, "purpose": request.purpose},
                               headers={"Authorization": f"Bearer {self._token}"})
        if answer.status_code != 200:
            # Acervo's own sentence — which provider refused, and why — kept whole for the job.
            raise RuntimeError(f"Acervo could not write the lines ({answer.status_code}): "
                               f"{_message(answer)}")
        body = answer.json()
        data = body.get("data") if isinstance(body, dict) else None
        return str((data or {}).get("text") or "")


def _message(answer: httpx.Response) -> str:
    """Acervo's error shape is `{"error": {"code", "message"}}`; anything else is said as it came."""
    try:
        body = answer.json()
    except ValueError:
        return answer.text[:300]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return answer.text[:300]


def backend_for(context: RenderContext) -> AcervoVoice:
    """One voice per render, built around the credential that came with it."""
    base_url = os.environ.get("ACERVO_API_URL", "").strip()
    if not base_url:
        raise RuntimeError(
            "ACERVO_API_URL is not set, so there is nowhere to ask for a voice. "
            "It should point at the server's own API on the compose network."
        )
    if not context.credentials:
        raise RuntimeError(
            "This render carried no speech token. Acervo mints one per render and sends it as "
            "`speech.token`; without it there is no way to ask for a voice."
        )
    # So a token can never reach a provider error message, a log line or a traceback.
    register_secret(context.credentials)
    return AcervoVoice(base_url, context.credentials, _delivery_of(context))


def writer_for(context: RenderContext) -> AcervoWriter:
    """One writer per render, around the same credential as its voice."""
    base_url = os.environ.get("ACERVO_API_URL", "").strip()
    if not base_url or not context.credentials:
        raise RuntimeError("A render that needs its lines written came with nowhere to ask.")
    register_secret(context.credentials)
    return AcervoWriter(base_url, context.credentials)


def _delivery_of(context: RenderContext) -> str:
    """Which order the owner chose for loops, as Acervo resolved it and sent it.

    It rides on the request because it cannot be found out from in here: this container holds no
    settings, no catalogue and no credential, and the answer is the owner's rather than the
    deployment's. It arrives as `speech.delivery` and reaches the factory untouched.

    Anything other than `plain` is `directed`, which is the better-sounding answer and therefore the
    right one for a hand-run `curl` that says nothing.
    """
    wanted = context.delivery or DIRECTED
    return PLAIN if str(wanted).lower() == PLAIN else DIRECTED


def main() -> None:
    config = ServiceConfig.from_environment()
    host = os.environ.get("LEXIBEAT_SERVICE_HOST", "0.0.0.0")  # noqa: S104 — the container's own port
    port = int(os.environ.get("LEXIBEAT_SERVICE_PORT", "8000"))
    print(f"lexibeat: takes come from {os.environ.get('ACERVO_API_URL', '<ACERVO_API_URL unset>')}",
          file=sys.stderr, flush=True)
    app = create_service(config=config, backend_factory=backend_for, writer_factory=writer_for)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
