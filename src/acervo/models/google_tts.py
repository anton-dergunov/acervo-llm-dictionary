"""The Cloud Text-to-Speech adapter: Google's own speech API, which LiteLLM does not reach.

One route, `text:synthesize`, serves two quite different families of voice, and the row says which
is which rather than this module:

- **Standard and WaveNet voices** exist per language, carry the language in their name
  (`es-ES-Wavenet-F`) and take no direction at all. These are the character-metered voices with the
  large free allowance, and they are what reads a headword.
- **Gemini voices** are named once (`Kore`) and speak any language. They are selected by
  `voice.modelName`, and they take a free-text delivery direction in `input.prompt` — a field of its
  own, so an example's emotion shapes the reading without ever being read out.

Authentication is Google's application default credentials, exactly as for the `vertex` row, and
lives in `google_auth.py` beside Cloud Vision's.

Failures go through `call.classify`, the same table every other provider's do, so a Google 429 is the
same kind of thing to the chain as a Cloudflare one.
"""

from __future__ import annotations

import base64
from typing import Any

from acervo.models import google_auth
from acervo.models.catalogue import Row
from acervo.models.errors import ProviderRefused

SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
# What each encoding arrives as. `call.speech` sniffs the bytes rather than trusting this, which is
# the rule for every adapter — but an adapter that *claimed* the wrong type would still be lying.
MIMES = {"LINEAR16": "audio/wav", "MP3": "audio/mpeg", "OGG_OPUS": "audio/ogg"}


def speech(
    row: Row,
    model: str,
    words: str,
    *,
    language: str,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = 30.0,
) -> tuple[bytes, str]:
    declared = row.audio_for(model)
    chosen = voice or next(iter(row.voices_for(model, language)), None)
    if not chosen:
        raise ProviderRefused(
            "configuration", f"{model} names no voice for {language}", provider_id=row.id, model=model
        )
    body: dict[str, Any] = {
        "input": {"text": words},
        "voice": {"languageCode": row.locale_for(model, language, chosen), "name": chosen},
        # The row says what to ask for, per model. Google's `MP3` is 32 kbps for a Gemini voice and
        # 64 for a WaveNet one, so the rows ask for `LINEAR16` and `pronunciation/encode.py` does the
        # compressing — see `experiments/pronunciation-encoding/`.
        "audioConfig": {"audioEncoding": str(declared.get("encoding") or "MP3")},
    }
    if declared.get("modelName"):
        body["voice"]["modelName"] = declared["modelName"]
    if style:
        body["input"]["prompt"] = style

    response = google_auth.post(row, model, SYNTHESIZE_URL, body, timeout)
    try:
        encoded = response.json().get("audioContent")
    except (ValueError, AttributeError):
        encoded = None
    if not isinstance(encoded, str) or not encoded:
        google_auth.fail(row, model, "empty", "the response contained no audio", response.status_code)
    return base64.b64decode(encoded), MIMES.get(str(declared.get("encoding") or "MP3"), "audio/mpeg")
