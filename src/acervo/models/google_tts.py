"""The Cloud Text-to-Speech adapter: Google's own speech API, which LiteLLM does not reach.

One route, `text:synthesize`, serves two quite different families of voice:

- **Standard and WaveNet voices** exist per language, carry the language in their name
  (`es-ES-Wavenet-F`) and take no direction at all. These are the character-metered voices with the
  large free allowance, and they are what reads a headword.
- **Gemini voices** are named once (`Kore`) and speak any language. They are selected by
  `voice.modelName`, and they take a free-text delivery direction in `input.prompt` — a field of its
  own, so an example's emotion shapes the reading without ever being read out.

Signing in — a key or a credentials file — lives in `google_auth.py`, beside Cloud Vision's. The
voices are Google's own list (`listing.voices`), and what to ask for is the family's
(`families.py`): `LINEAR16`, and `cmn-` for Chinese.

Failures go through `call.classify`, the same table every other provider's do, so a Google 429 is the
same kind of thing to the chain as a Cloudflare one.
"""

from __future__ import annotations

import base64
from typing import Any

from acervo.models import google_auth
from acervo.models.providers import Provider
from acervo.models.errors import ProviderRefused

SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
# What each encoding arrives as. `call.speech` sniffs the bytes rather than trusting this, which is
# the rule for every adapter — but an adapter that *claimed* the wrong type would still be lying.
MIMES = {"LINEAR16": "audio/wav", "MP3": "audio/mpeg", "OGG_OPUS": "audio/ogg"}


def speech(
    row: Provider,
    model: str,
    words: str,
    *,
    language: str,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = 30.0,
) -> tuple[bytes, str]:
    encoding = str(row.family.audio.get("encoding") or "MP3")
    chosen = voice or next(iter(row.voices_for(model, language)), None)
    if not chosen:
        # A voice list that could not be read fails here with Google's own sentence, rather than as
        # "no voice", which would send somebody looking for a missing language.
        row.voices(model, strict=True)
        raise ProviderRefused(
            "configuration", f"{model} names no voice for {language}", provider_id=row.id, model=model
        )
    body: dict[str, Any] = {
        "input": {"text": words},
        "voice": {"languageCode": row.locale_for(model, language, chosen), "name": chosen},
        # Google's `MP3` is 32 kbps for a Gemini voice and 64 for a WaveNet one, so the family asks
        # for `LINEAR16` and `pronunciation/encode.py` does the compressing — see
        # `experiments/pronunciation-encoding/`.
        "audioConfig": {"audioEncoding": encoding},
    }
    # A Gemini voice is chosen by name *and* model; a voice type's model is in its name.
    if model.startswith("gemini-"):
        body["voice"]["modelName"] = model
    if style:
        body["input"]["prompt"] = style

    response = google_auth.post(row, model, SYNTHESIZE_URL, body, timeout)
    try:
        encoded = response.json().get("audioContent")
    except (ValueError, AttributeError):
        encoded = None
    if not isinstance(encoded, str) or not encoded:
        google_auth.fail(row, model, "empty", "the response contained no audio", response.status_code)
    return base64.b64decode(encoded), MIMES.get(encoding, "audio/mpeg")
