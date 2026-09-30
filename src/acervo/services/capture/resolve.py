"""Model call one: what is this text about?

Asked two ways. Capture asks it on the owner's `text` chain as the first of its two calls. A photo tap
asks it alone, as the **quick look-up** (`POST /capture/resolve`), on the `quick` chain and with a
tight budget, because a finger is still on the glass: the same question, plus what the word means in
this sentence, answered by a model ordered for speed. `/capture` can then take that resolution
rather than pay for resolve a second time (`pipeline.given_resolution`).

A word tapped while reading in Acervo — a story, a loop's line, an example — is the same quick
look-up with `source: "reading"`: the sentence is somebody's finished text, not the learner's notes to
be corrected, and it has to come back verbatim for the capture that follows to accept it.
"""

from __future__ import annotations

from typing import Any

from acervo.domain.validation import POS_VALUES
from acervo.errors import ApiError
from acervo.models import Answer
from acervo.models.call import SHORT_HEDGE_SECONDS
from acervo.services.capture.coerce import (
    language_or_none,
    pick_choice,
    reference_of,
    trimmed,
)
from acervo.services.models import llm_json
from acervo.services.prompts import prompt_text
from acervo.settings import Settings

# The quick look-up's budget. Measured in `experiments/photo-capture/`: the flash-lite model the
# `quick` chain leads with answered in 1.02 s at the median and 1.64 s at p90, so a pair silent for
# 2.5 s is raced by the next rather than waited out, and one silent for 10 s is given up on.
QUICK_HEDGE_SECONDS = 2.5
QUICK_TIMEOUT_SECONDS = 10

UNREADABLE = ApiError(
    422, "unreadable_input", "That text could not be read as a word to learn, so nothing was created."
)


def marked(text: str, selection: Any) -> str:
    """The text with the selected span in asterisks — the prompt's "the learner pointed here".

    A selection that does not fit the text is ignored rather than refused: the headword hint still
    says which word was meant, and a pointer is a hint in any case.
    """
    if not isinstance(selection, dict):
        return text
    start, end = selection.get("start"), selection.get("end")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (start, end)):
        return text
    if not 0 <= start < end <= len(text) or not text[start:end].strip():
        return text
    return f"{text[:start]}*{text[start:end]}*{text[end:]}"


def resolve(
    settings: Settings,
    owner: str,
    request: dict[str, Any],
    vocabularies: list[dict],
    *,
    quick: bool = False,
) -> tuple[dict[str, Any], Answer]:
    stream = trimmed(request.get("mode")) == "stream" and not quick
    source = trimmed(request.get("source")) if quick else ""
    photo = source == "photo"
    reading = source == "reading"
    reference = reference_of(request)
    known = [
        entry["language"]
        + (f" ({entry['displayName']})" if entry.get("displayName") else "")
        # The gloss is written in the language this vocabulary is glossed into, and a field whose
        # language is unstated drifts from request to request.
        + (f" — gloss in {entry['glossLangs'][0]}" if quick and entry.get("glossLangs") else "")
        for entry in vocabularies
    ]
    text = str(request.get("text") or "")
    lines = text.split("\n")
    shown = marked(text, request.get("selection")) if quick else text
    user = "\n".join(
        line
        for line in [
            "Mode: " + ("stream" if stream else "single"),
            "Languages this learner studies: " + (", ".join(known) if known else "none configured yet"),
            f"The caller believes this is {trimmed(request.get('language'))}; verify it."
            if trimmed(request.get("language"))
            else "",
            f"The learner says the word is: {trimmed(request.get('headword'))}"
            if trimmed(request.get("headword"))
            else "",
            "\nReference (an external dictionary's entry for this word — CONTEXT ONLY. Do not\n"
            "take any sentence from it as one the learner supplied):\n```\n" + reference["text"] + "\n```"
            if reference
            else "",
            "",
            "The input is text read from a photograph by OCR, one sentence of it." if photo else "",
            "The input is one sentence of something the learner was reading." if reading else "",
            f"Input ({len(lines)} lines):",
            "```",
            shown,
            "```",
        ]
        if line != ""
    )

    system = prompt_text(
        settings.prompts_path, "acervo_resolve", {"quick": quick, "photo": photo, "reading": reading}
    )
    if quick:
        answer, call = llm_json(
            settings, owner, system, user, caller="resolve-quick", kind="quick",
            hedge_after=QUICK_HEDGE_SECONDS, timeout=QUICK_TIMEOUT_SECONDS,
        )
    else:
        answer, call = llm_json(
            settings, owner, system, user, caller="resolve", hedge_after=SHORT_HEDGE_SECONDS,
        )
    if isinstance(answer, dict) and trimmed(answer.get("error")):
        raise UNREADABLE
    if not isinstance(answer, dict):
        raise UNREADABLE
    language = language_or_none(answer.get("language"))
    headword = trimmed(answer.get("headword"))
    if not language or not headword:
        raise UNREADABLE

    try:
        consumed = round(float(answer.get("consumedLines") or 0))
    except (TypeError, ValueError):
        consumed = 0
    sentences = []
    for item in answer.get("sentences") or []:
        if not isinstance(item, dict):
            continue
        sentence = trimmed(item.get("text"))
        if not sentence:
            continue
        sentences.append({"text": sentence, "translation": trimmed(item.get("translation")) or None})

    # At least one line, always: a walk that consumes nothing loops on the same block forever.
    consumed_lines = max(1, min(consumed or 1, len(lines))) if stream else len(lines)
    consumed_text = trimmed(answer.get("consumedText"))
    if stream and consumed_text != "\n".join(lines[:consumed_lines]).strip():
        raise ApiError(
            502,
            "stream_boundary_mismatch",
            "The language model returned an unsafe stream boundary, so nothing was created.",
        )
    resolution = {
        "language": language,
        "headword": headword,
        "lemma": trimmed(answer.get("lemma")) or headword,
        "pos": pick_choice(answer.get("pos"), POS_VALUES, "noun"),
        "sentences": sentences,
        "note": trimmed(answer.get("note")) or None,
        "consumedLines": consumed_lines,
        "consumedText": consumed_text or None,
    }
    if quick:
        resolution["gloss"] = " ".join(trimmed(answer.get("gloss")).split())[:GLOSS_LIMIT] or None
    return resolution, call


GLOSS_LIMIT = 120
