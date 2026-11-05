"""The Cloud Vision adapter: Google's OCR, which LiteLLM does not reach.

One route, `images:annotate`, asked for `DOCUMENT_TEXT_DETECTION` — the dense-text reader, which
answers a page as blocks, paragraphs, words and symbols, each word with its outline and each symbol
with the break that follows it. That structure is the whole reason to use it rather than a
multimodal model: the geometry is measured rather than described, and nothing is transcribed that
is not on the page. `experiments/photo-capture/` measured it against RapidOCR on the NAS and chose
it.

What comes back is `OcrWord`s, in Vision's reading order, with Vision's names gone: a break type is
one of four words, and the block and paragraph a word sat in survive as two numbers.

Signing in and failure are `google_auth.py`'s, shared with Cloud Text-to-Speech.
"""

from __future__ import annotations

import base64
from typing import Any, Sequence

from acervo.models import google_auth
from acervo.models.providers import Provider
from acervo.models.results import OcrWord

ANNOTATE_URL = "https://vision.googleapis.com/v1/images:annotate"

# Vision's `detectedBreak.type`, in this package's words. `UNKNOWN`, or no break at all, is `None`:
# the next word is glued on, which is how Vision reports punctuation ("Baile" ",").
_BREAKS = {
    "SPACE": "space",
    "SURE_SPACE": "space",
    "EOL_SURE_SPACE": "eol",
    "LINE_BREAK": "eol",
    "HYPHEN": "hyphen",
}


def read(
    row: Provider,
    model: str,
    data: bytes,
    *,
    language_hints: Sequence[str] = (),
    timeout: float = 15.0,
) -> tuple[list[OcrWord], int, int, str | None]:
    """The words on one image, its size as Vision measured it, and the language it detected."""
    request: dict[str, Any] = {
        "image": {"content": base64.b64encode(data).decode()},
        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
    }
    if language_hints:
        request["imageContext"] = {"languageHints": list(language_hints)}
    response = google_auth.post(row, model, ANNOTATE_URL, {"requests": [request]}, timeout)
    try:
        answer = response.json()["responses"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        google_auth.fail(row, model, "unusable", "the response carried no annotation", response.status_code)
    if isinstance(answer, dict) and answer.get("error"):
        error = answer["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        google_auth.fail(row, model, None, str(message), _status_of(error))
    return parse(answer)


def parse(answer: dict[str, Any]) -> tuple[list[OcrWord], int, int, str | None]:
    """One `images:annotate` response, as words. Pure, so a recorded response is a test fixture."""
    annotation = answer.get("fullTextAnnotation") or {}
    pages = annotation.get("pages") or []
    words: list[OcrWord] = []
    block_number = paragraph_number = -1
    for page in pages:
        for block in page.get("blocks") or []:
            block_number += 1
            for paragraph in block.get("paragraphs") or []:
                paragraph_number += 1
                for word in paragraph.get("words") or []:
                    symbols = word.get("symbols") or []
                    text = "".join(str(symbol.get("text") or "") for symbol in symbols)
                    if not text:
                        continue
                    last = (symbols[-1].get("property") or {}) if symbols else {}
                    kind = (last.get("detectedBreak") or {}).get("type")
                    words.append(OcrWord(
                        text=text,
                        # Vision omits a coordinate that is zero.
                        polygon=tuple(
                            (float(vertex.get("x", 0)), float(vertex.get("y", 0)))
                            for vertex in (word.get("boundingBox") or {}).get("vertices") or []
                        ),
                        confidence=float(word.get("confidence", 0.0)),
                        break_after=_BREAKS.get(str(kind)) if kind else None,
                        block=block_number,
                        paragraph=paragraph_number,
                    ))
    first = pages[0] if pages else {}
    languages = (first.get("property") or {}).get("detectedLanguages") or []
    language = languages[0].get("languageCode") if languages and isinstance(languages[0], dict) else None
    return words, int(first.get("width") or 0), int(first.get("height") or 0), language or None


# Vision answers 200 and puts a per-image failure in the body, with a gRPC code rather than an HTTP
# status. These are the codes worth telling apart; everything else is a refusal.
_GRPC_STATUS = {3: 400, 7: 403, 8: 429, 13: 500, 14: 503, 16: 401}


def _status_of(error: Any) -> int | None:
    code = error.get("code") if isinstance(error, dict) else None
    return _GRPC_STATUS.get(code) if isinstance(code, int) else None
