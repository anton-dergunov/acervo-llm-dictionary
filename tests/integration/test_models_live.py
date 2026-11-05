"""Real calls to real providers. Gated off, because this one costs money.

Everything about how a provider *failure* is handled is in `tests/unit/models/`, which runs offline
in two seconds against real LiteLLM exception objects. What only a live call can tell you is the
half a stub cannot fake: that a provider's model id still exists, that its key is accepted, that a
family whose JSON mode is native really does honour `response_format`, that every key check is
right about a working key, and that the bytes coming back are an image rather than a URL or an
envelope nobody parsed.

The providers are this machine's `providers.local.json` (`acervo/models/local.py`):

    RUN_LIVE_MODEL_TESTS=true .venv/bin/python -m pytest tests/integration/test_models_live.py -v

A provider with no key skips individually rather than failing the run, so the same command is
useful with three providers and with one.
"""

from __future__ import annotations

import json
import os

import pytest

from acervo.models import call, listing
from acervo.models.errors import ProviderUnavailable
from acervo.models.local import LocalProvidersMissing, load_local
from acervo.models.providers import parse

pytestmark = pytest.mark.integration

try:
    CATALOGUE = load_local()
except LocalProvidersMissing:
    from acervo.models.providers import Providers

    CATALOGUE = Providers()

# Short, cheap and unambiguous. The text prompt asks for a shape rather than for knowledge, so a
# failure is about the transport rather than about the model being clever enough.
WORD = "hola"
TEXT_PROMPT = 'Reply with only this JSON object and nothing else: {"ok": true, "word": "hola"}'
IMAGE_PROMPT = "a plain red circle centred on a white background"


@pytest.fixture(scope="module", autouse=True)
def gated():
    if os.environ.get("RUN_LIVE_MODEL_TESTS") != "true":
        pytest.skip("set RUN_LIVE_MODEL_TESTS=true to spend real money on real providers")


def pairs(kind: str) -> list[tuple[str, str]]:
    """Every (provider, model) this machine has for a kind — each one gets its own case.

    Per pair rather than per provider, because a provider's second model is exactly the thing a stub
    cannot check: it is listed so that the first one's 429 has somewhere to go, and a model id that has
    been retired sits there silently until the day the first bucket runs out.
    """
    return [(row.id, model) for row in CATALOGUE.serving(kind) for model in row.models_for(kind)]


def row_for(kind: str, identifier: str):
    row = CATALOGUE.find(identifier)
    if not row.serves(kind):
        pytest.skip(f"{identifier} does not serve {kind}")
    if not row.available:
        pytest.skip(f"{identifier}: {row.reason()}")
    return row


def check(answer, row) -> None:
    """Every live call proves the same three things about what came back."""
    assert answer.provider_id == row.id
    assert answer.model
    assert answer.seconds > 0, "a real call cannot take no time"


def reachable(row, kind):
    """Rate limiting is the provider answering correctly and having nothing left.

    A 429 proves both of the things this file exists to check — that the model id still resolves and
    that the credential was accepted — because the request got past authentication and routing to
    reach a quota. Gemini's free tier has separate, much smaller allowances for images and speech
    than for text, so on most days that is what the image and speech rows have to say. Anything else
    still fails: this widens what counts as a pass by exactly one typed error, not by a category.
    """

    def run(make):
        try:
            return make()
        except ProviderUnavailable as error:
            if error.reason != "rate_limited":
                raise
            pytest.skip(f"{row.id} {kind}: reached, and out of quota — {error.status}")

    return run


@pytest.mark.parametrize(("identifier", "model"), pairs("text"), ids=lambda v: v.split("/")[-1])
def test_text_comes_back_as_json_from_a_real_provider(identifier, model):
    row = row_for("text", identifier)
    result = reachable(row, "text")(
        lambda: call.text(
            TEXT_PROMPT, row=row, model=model, system="You answer with JSON only.", as_json=True
        )
    )
    check(result.answer, row)
    assert isinstance(result.parsed, dict), f"unparseable reply: {result.text[:200]!r}"
    assert result.parsed.get("word") == WORD
    assert result.answer.model == model
    # `native` rows are sent `response_format`; `prompt` rows are asked in prose and parsed after.
    # Either way the caller gets a dict, which is the whole point of the capability declaration.
    print(f"\n{identifier}: {model} in {result.answer.seconds:.1f}s cost={result.answer.cost_usd}")


@pytest.mark.parametrize(("identifier", "model"), pairs("image"), ids=lambda v: v.split("/")[-1])
def test_an_image_comes_back_as_bytes_from_a_real_provider(identifier, model):
    row = row_for("image", identifier)
    result = reachable(row, "image")(
        lambda: call.image(IMAGE_PROMPT, row=row, model=model, size=(512, 512))
    )
    check(result.answer, row)
    assert len(result.data) > 1000, "that is too small to be an image"
    # PNG, JPEG or WebP — enough to prove these are pixels and not a URL or a base64 string nobody
    # decoded, without pinning a provider to one encoder.
    assert result.data[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"RIFF"), (
        f"unexpected leading bytes {result.data[:8]!r}"
    )
    print(f"\n{identifier}: {model} → {len(result.data)} bytes in {result.answer.seconds:.1f}s")


@pytest.mark.parametrize(("identifier", "model"), pairs("audio"), ids=lambda v: v.split("/")[-1])
def test_speech_comes_back_as_audio_from_a_real_provider(identifier, model):
    row = row_for("audio", identifier)
    # The word in a language the model says it speaks: Aura is English-only, the rest take Spanish.
    language = "es" if row.speaks(model, "es") else "en"
    words = WORD if language == "es" else "hello"
    # A style goes only where the model declares it takes one, which is exactly what is being
    # checked for the Gemini voices: that `prompt` is accepted and the answer is still audio.
    style = "Say it warmly, like greeting an old friend." if row.takes_direction(model) else None
    result = reachable(row, "audio")(
        lambda: call.speech(words, row=row, model=model, language=language, style=style)
    )
    check(result.answer, row)
    assert len(result.data) > 500, "that is too small to be a spoken word"
    # Sniffed from the bytes, not asserted by the family: Gemini answers WAV and Aura answers MP3.
    assert result.mime != "application/octet-stream", f"unrecognised audio {result.data[:8]!r}"
    assert result.answer.warnings == ()
    print(f"\n{identifier}: {model} voice={result.voice} style={bool(style)} → {len(result.data)} "
          f"bytes {result.mime} in {result.answer.seconds:.1f}s")


@pytest.mark.parametrize(("identifier", "model"), pairs("ocr"), ids=lambda v: v.split("/")[-1])
def test_a_photographed_page_comes_back_as_words_with_outlines(identifier, model):
    """One fixture photo, at the size the interface sends. One image of the free thousand a month."""
    from io import BytesIO
    from pathlib import Path

    from PIL import Image

    row = row_for("ocr", identifier)
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "photo-capture" / "camera-01.jpg"
    image = Image.open(fixture).convert("RGB")
    image.thumbnail((2048, 2048))
    sent = BytesIO()
    image.save(sent, "JPEG", quality=85)
    result = reachable(row, "ocr")(
        lambda: call.ocr(sent.getvalue(), row=row, model=model, language_hints=["es"])
    )
    check(result.answer, row)
    assert len(result.words) > 50, "a page of a book has more words than that"
    assert result.language and result.language.startswith("es")
    assert all(len(word.polygon) == 4 for word in result.words)
    assert len({word.paragraph for word in result.words}) > 1, "the paragraph structure survived"
    print(f"\n{identifier}: {len(result.words)} words, {result.language}, in {result.answer.seconds:.1f}s")


def _first_with_a_key(kind: str):
    row = next((row for row in CATALOGUE.serving(kind) if row.credential.key and row.available), None)
    if row is None:
        pytest.skip(f"no provider here has a key for {kind}")
    return row


def test_a_wrong_credential_is_refused_rather_than_routed_around():
    """The locked rule, against the real service: a rejected key must not spend the next provider.

    This is the one live case worth having beyond "it works", because it is the one where being
    wrong costs money quietly rather than failing loudly.
    """
    from acervo.models.errors import ProviderRefused

    good = _first_with_a_key("text")
    wrong = parse({"id": good.id, "family": good.family.id, "settings": dict(good.settings),
                   "models": {"text": list(good.models_for("text"))}}, {"key": "not-a-real-key-0000000000"})
    with pytest.raises(ProviderRefused) as caught:
        call.text(TEXT_PROMPT, row=wrong, as_json=True)
    assert caught.value.reason in ("authentication", "configuration")
    assert "not-a-real-key-0000000000" not in caught.value.detail


@pytest.mark.parametrize("identifier", [row.id for row in CATALOGUE], ids=str)
def test_the_key_check_says_a_working_key_works(identifier):
    """The call that decides whether a provider may be added. It spends nothing."""
    row = CATALOGUE.find(identifier)
    if not row.available:
        pytest.skip(f"{identifier}: {row.reason()}")
    checked = listing.check(row)
    assert checked.ok, checked.said
    print(f"\n{identifier}: {checked.said}")


def test_the_key_check_says_a_wrong_key_is_refused():
    good = _first_with_a_key("text")
    wrong = parse({"id": good.id, "family": good.family.id, "settings": dict(good.settings),
                   "models": {"text": list(good.models_for("text"))}}, {"key": "not-a-real-key-0000000000"})
    checked = listing.check(wrong)
    assert not checked.ok and checked.reason in ("authentication", "configuration"), checked.said
    assert "not-a-real-key-0000000000" not in checked.said


def test_this_machine_has_providers_to_check():
    checked = [row.id for row in CATALOGUE if row.available]
    assert checked, "no provider in providers.local.json can be asked; nothing was verified"
    print("\ncan be asked here: " + json.dumps(checked))
