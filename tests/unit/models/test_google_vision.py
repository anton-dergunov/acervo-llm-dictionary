"""The Cloud Vision adapter, against a stubbed transport and stubbed credentials.

What is worth pinning is the reading of Vision's shape — a break type onto one of four words, a
missing zero coordinate, the block and paragraph a word sat in — and that a per-image failure Vision
reports *inside* a 200 is classified like an HTTP one, so a quota answer falls through the chain.
"""

from __future__ import annotations

import httpx
import pytest

from acervo.models import google_auth, google_vision
from acervo.models.call import ocr
from provider_rows import GOOGLE_KEYED, google_voices, provider
from acervo.models.errors import ProviderRefused, ProviderUnavailable

# Vision takes a key, and this is the provider a key makes.
ROW = provider(GOOGLE_KEYED)


class _Credentials:
    valid = True
    token = "an-access-token-value"


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    from acervo.models import listing

    google_auth.forget_credentials()
    monkeypatch.setattr(listing, "_google_voices", google_voices)
    monkeypatch.setattr(google_auth, "_load", lambda info, project: _Credentials())
    yield
    google_auth.forget_credentials()


def transport(monkeypatch, response: httpx.Response, calls: list):
    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(google_auth.httpx, "post", post)


def word(text: str, box: tuple[int, int, int, int], after: str | None = "SPACE", confidence=0.98):
    x0, y0, x1, y1 = box
    symbols = [{"text": character} for character in text]
    if after:
        symbols[-1]["property"] = {"detectedBreak": {"type": after}}
    # Vision leaves out a coordinate that is zero, which is why the first vertex has no `x`.
    vertices = [{"y": y0} if x0 == 0 else {"x": x0, "y": y0}, {"x": x1, "y": y0}, {"x": x1, "y": y1},
                {"x": x0, "y": y1}]
    return {"boundingBox": {"vertices": vertices}, "confidence": confidence, "symbols": symbols}


ANSWER = {
    "fullTextAnnotation": {"pages": [{
        "width": 200, "height": 100,
        "property": {"detectedLanguages": [{"languageCode": "es", "confidence": 0.9}]},
        "blocks": [
            {"paragraphs": [{"words": [word("12:04", (0, 0, 30, 8), "EOL_SURE_SPACE")]}]},
            {"paragraphs": [
                {"words": [word("Hola", (10, 20, 40, 30)), word("mun", (45, 20, 70, 30), "HYPHEN")]},
                {"words": [word("do", (10, 35, 25, 45), None), word(".", (25, 35, 28, 45), "LINE_BREAK")]},
            ]},
        ],
    }]},
}


def test_a_response_is_read_as_words_with_their_breaks_blocks_and_paragraphs():
    words, width, height, language = google_vision.parse(ANSWER)
    assert (width, height, language) == (200, 100, "es")
    assert [(w.text, w.break_after, w.block, w.paragraph) for w in words] == [
        ("12:04", "eol", 0, 0),
        ("Hola", "space", 1, 1),
        ("mun", "hyphen", 1, 1),
        ("do", None, 1, 2),
        (".", "eol", 1, 2),
    ]
    assert words[0].polygon[0] == (0.0, 0.0), "a coordinate Vision left out is zero"
    assert words[1].polygon == ((10.0, 20.0), (40.0, 20.0), (40.0, 30.0), (10.0, 30.0))


def test_an_image_with_no_text_is_no_words_rather_than_an_error():
    assert google_vision.parse({}) == ([], 0, 0, None)


def test_the_request_asks_for_dense_text_with_the_owners_languages_as_hints(monkeypatch):
    calls = []
    transport(monkeypatch, httpx.Response(200, json={"responses": [ANSWER]}), calls)
    result = ocr(b"jpeg-bytes", row=ROW, language_hints=["es", "zh"])
    request = calls[-1]["json"]["requests"][0]
    assert request["features"] == [{"type": "DOCUMENT_TEXT_DETECTION"}]
    assert request["imageContext"] == {"languageHints": ["es", "zh"]}
    assert calls[-1]["headers"]["x-goog-api-key"] == ROW.credential.key
    assert [w.text for w in result.words][:2] == ["12:04", "Hola"]
    assert (result.answer.provider_id, result.answer.model) == ("google-keyed", "document-text-detection")


@pytest.mark.parametrize(
    ("status", "failure", "reason"),
    [
        (429, ProviderUnavailable, "rate_limited"),
        (503, ProviderUnavailable, "unavailable"),
        (403, ProviderRefused, "authentication"),
    ],
)
def test_http_failures_are_classified_like_every_other_providers(monkeypatch, status, failure, reason):
    transport(monkeypatch, httpx.Response(status, json={"error": {"message": "the API is not enabled"}}), [])
    with pytest.raises(failure) as caught:
        ocr(b"jpeg-bytes", row=ROW)
    assert caught.value.reason == reason
    assert "the API is not enabled" in str(caught.value)


def test_a_failure_inside_a_successful_response_is_classified_by_its_code(monkeypatch):
    """Vision answers 200 and puts a per-image error in the body, with a gRPC code."""
    body = {"responses": [{"error": {"code": 8, "message": "Quota exceeded for this project."}}]}
    transport(monkeypatch, httpx.Response(200, json=body), [])
    with pytest.raises(ProviderUnavailable) as caught:
        ocr(b"jpeg-bytes", row=ROW)
    assert caught.value.reason == "rate_limited"


def test_an_answer_without_responses_is_unusable(monkeypatch):
    transport(monkeypatch, httpx.Response(200, json={}), [])
    with pytest.raises(ProviderUnavailable) as caught:
        ocr(b"jpeg-bytes", row=ROW)
    assert caught.value.reason == "unusable"
