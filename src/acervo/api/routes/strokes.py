"""How a character is written, for the Write sheet (`docs/features/writing.md`).

One read route, asked in batches: a device fetches the characters of the owner's Mandarin words
after a pull and keeps them, so practice works offline, and the sheet asks for its own word's
characters when it opens. Nothing here writes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from acervo import activity
from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.errors import ApiError
from acervo.services import strokes

router = APIRouter()

# A batch is what one prefetch request carries. The owner's whole vocabulary is a few hundred
# characters, so this is two or three requests, and a bound keeps one from reading thousands of files.
MOST = 200


@router.get("/strokes")
def stroke_data(request: Request) -> JSONResponse:
    owner_id(request)
    asked = request.query_params.get("characters") or ""
    characters = list(dict.fromkeys(asked))
    if not characters:
        raise ApiError(400, "characters_required", "Ask for at least one character.")
    if len(characters) > MOST:
        raise ApiError(400, "too_many_characters", f"Ask for at most {MOST} characters at a time.",
                       noted={"asked": len(characters)})
    foreign = [character for character in characters if not strokes.is_han(character)]
    if foreign:
        raise ApiError(400, "not_chinese", f"Only Chinese characters have strokes; “{foreign[0]}” is not one.")

    directory = Path(request.app.state.settings.strokes_path)
    dataset = strokes.dataset(directory)
    if dataset is None:
        raise ApiError(503, "strokes_unavailable",
                       "This server holds no stroke data. It is fetched when the server image is built, "
                       "so a deploy that rebuilds the image brings it.", noted={"directory": str(directory)})
    found, missing = strokes.read(directory, characters)
    if missing:
        # Somebody will ask why a character cannot be practised; this is the line that answers it.
        activity.note("strokes missing", failed=True, dataset=dataset, characters="".join(missing))
    return data({"dataset": dataset, "characters": found, "missing": missing})
