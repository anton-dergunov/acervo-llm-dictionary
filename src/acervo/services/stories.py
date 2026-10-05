"""Acervo's binding to the story pipeline: words in, a story and its pictures out.

The other half of the split `acervo.stories` makes, and the same split `services/images.py` makes
against `acervo.images`. That package knows what a story is; this one knows whose words they are,
which chain writes it, which language it is translated into, where the pictures go and what
Acervo's API calls a failure.

Every operation is read (transaction) → call (**no** transaction, tens of seconds of it) → write
(transaction), for `services/loops.py`'s reason: a repository function is a transaction and owns
its session, and a model call inside one blocks every other request while it runs.

**A story's state is derived, and this is where that pays.** `create` writes the `stories` row and
its `storyWords` with no parts at all; the job fills them in. So a story whose job failed to queue,
or failed outright, simply reads as one that was asked for and never written — there is no status
column to get out of step with what happened, and Try again queues another.

**Each step re-derives what is missing from the graph** rather than being handed it, which is what
makes a retry cost only what it has to: `draw_pictures` draws the parts with no `imageRef`, so a
run that lost its last picture to a timeout redraws one picture and not four.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from acervo.domain.ids import is_record_id, new_record_id, now_instant
from acervo.domain.validation import GUIDANCE_LIMIT
from acervo.errors import ApiError
from acervo.images.styles import load_styles
from acervo.models import chain, load_catalogue
from acervo.models.errors import ChainExhausted, ProviderError, ProviderRefused
from acervo.pronunciation.speak import language_name
from acervo.repository import image_settings
from acervo.repository import graph
from acervo.repository.graph import article_records
from acervo.services import media as media_files
from acervo.services.models import chain_for, refusal
from acervo.services.prompts import prompt_text
from acervo.services.rules import with_rules
from acervo.settings import Settings
from acervo.stories import continuity, illustrate, translate, write
from acervo.stories.types import story_types

# A story is built around a handful of words, not a vocabulary list. The ceiling is about what the
# writer can weave into twenty sentences without the prose buckling, which the experiment found
# starts happening well before it: three is the default the dialog offers.
MIN_WORDS = 1
MAX_WORDS = 8

# What the dialog offers and the writer is asked for. The model chooses within this.
MIN_PARTS = 4
MAX_PARTS = 6
DEFAULT_PARTS = 4

# Named without `.md`: `prompt_text` appends the extension itself.
WRITE_TEMPLATE = "acervo_story_write"
TRANSLATE_TEMPLATE = "acervo_story_translate"
BRIEF_TEMPLATE = "acervo_story_brief"
CONTINUITY_TEMPLATE = "acervo_story_continuity"
REFERENCE_TEMPLATE = "acervo_story_reference"

# A picture that has failed this many times is left alone. `images/` uses the same number for the
# same reason: past this it is the brief that is wrong, not the weather.
MAX_ATTEMPTS = 4


def _template(settings: Settings, name: str) -> str:
    return prompt_text(Path(settings.prompts_path), name)


def _candidates(settings: Settings, owner: str, kind: str) -> tuple[chain.Candidate, ...]:
    """The owner's chain for one kind, resolved per call. See `services/images._candidates`."""
    try:
        return chain.resolve(kind, chain_for(settings, owner, kind), load_catalogue())
    except ProviderError as error:
        raise refusal(error, kind) from None


def _require(candidates: tuple[chain.Candidate, ...], settings: Settings, owner: str, kind: str) -> None:
    if not candidates:
        raise refusal(chain.unconfigured(kind, chain_for(settings, owner, kind), load_catalogue()), kind)


# ── what can be asked for ───────────────────────────────────────────────────


def types_view(settings: Settings, owner: str) -> dict[str, Any]:
    """The kinds of story and the styles they can be drawn in, for the dialog.

    The styles travel with the types for `services/images.settings_view`'s reason: the choice is
    meaningless without the labels, and one round trip cannot render a half-loaded screen.
    """
    table = story_types()
    styles = load_styles()
    off = set(image_settings.settings(owner).styles_off)
    return {
        "types": [
            {"id": one.id, "label": one.label, "emoji": one.emoji, "styles": list(one.styles)}
            for one in table.types
        ],
        # Every style the owner has left switched on, so a story may be drawn in one its type does
        # not suggest. "Surprise me" reaches only for the type's own; this is the whole list.
        "styles": [
            {"id": style.id, "label": style.label}
            for style in styles.styles if style.id not in off
        ],
        "minWords": MIN_WORDS, "maxWords": MAX_WORDS,
        "minParts": MIN_PARTS, "maxParts": MAX_PARTS, "defaultParts": DEFAULT_PARTS,
    }


# ── asking for one ──────────────────────────────────────────────────────────


def create(settings: Settings, owner: str, device: str, body: dict[str, Any]) -> dict[str, Any]:
    """Write the story and the words it must use. Writing the story itself is the job's.

    The route takes **ids**, never a query, for `services/loops.create`'s reason: the interface
    sampled them from the scope on screen, and choosing words by hand later is the same route with
    a different list.
    """
    language = str(body.get("language") or "").strip()
    ids = body.get("lexemeIds")
    if not isinstance(ids, list) or not all(isinstance(one, str) for one in ids):
        raise ApiError(400, "invalid_input", "A story is made from a list of word ids.")
    wanted = [one for one in ids if is_record_id(one)]
    if len(wanted) != len(ids) or not MIN_WORDS <= len(wanted) <= MAX_WORDS:
        raise ApiError(400, "invalid_input",
                       f"A story takes between {MIN_WORDS} and {MAX_WORDS} words.")
    if len(set(wanted)) != len(wanted):
        raise ApiError(400, "invalid_input", "A story cannot be asked to teach the same word twice.")

    table = story_types()
    type_id = str(body.get("typeId") or "").strip()
    if type_id and type_id not in table:
        raise ApiError(400, "invalid_input", f"There is no “{type_id}” kind of story.")

    styles = load_styles()
    style_id = str(body.get("styleId") or "").strip()
    if style_id and style_id not in styles:
        raise ApiError(400, "invalid_input", f"There is no “{style_id}” style.")

    guidance = body.get("guidance") or ""
    if not isinstance(guidance, str):
        raise ApiError(400, "invalid_input", "A story's guidance is text.")
    guidance = guidance.strip()
    if len(guidance) > GUIDANCE_LIMIT:
        raise ApiError(400, "invalid_input",
                       f"A story's guidance is at most {GUIDANCE_LIMIT} characters.")
    parts = int(body.get("parts") or DEFAULT_PARTS)
    if not MIN_PARTS <= parts <= MAX_PARTS:
        raise ApiError(400, "invalid_input",
                       f"A story has between {MIN_PARTS} and {MAX_PARTS} parts.")

    held = graph.owned_records(owner, "lexemes", wanted)
    words: list[dict[str, Any]] = []
    for identifier in wanted:
        lexeme = held.get(identifier)
        if lexeme is None or lexeme.get("deleted"):
            raise ApiError(404, "not_found", "One of those words is not in your vocabulary.")
        if language and lexeme.get("language") != language:
            raise ApiError(400, "invalid_input", "Every word in a story is in one language.")
        language = language or str(lexeme.get("language") or "")
        words.append(lexeme)

    story_id = new_record_id()
    # Chosen now rather than at render time, so Try again on a story that was never written reaches
    # for the same kind and the same look rather than quietly becoming a different story.
    chosen_type = table[type_id] if type_id else table.surprise(story_id)
    off = set(image_settings.settings(owner).styles_off)
    allowed = [style.id for style in styles.styles if style.id not in off]
    chosen_style = style_id or table.style_for(chosen_type, story_id, allowed=allowed)

    at = now_instant()
    stamp = {"ownerId": owner, "deleted": False, "createdAt": at, "editedAt": at,
             "editedBy": device, "revision": 0}
    graph.merge_graph(owner, device, {
        "stories": [{
            "id": story_id, "language": language,
            "typeId": chosen_type.id, "styleId": chosen_style,
            # Everything the writer decides is empty until it has. No parts at all is the whole of
            # what "not written yet" means.
            "title": "", "titleTranslation": "", "emoji": chosen_type.emoji, "modelId": "",
            "position": graph.next_story_position(owner, language),
            "guidance": guidance,
            **stamp,
        }],
        "storyWords": [{
            "id": new_record_id(), "storyId": story_id, "lexemeId": word["id"], "position": index,
            "sourceText": str(word.get("headword") or ""),
            # Filled in by the writer, and an empty list afterwards is a real answer: the story did
            # not manage to use this word.
            "forms": [],
            **stamp,
        } for index, word in enumerate(words)],
    }, enqueue=None)
    return graph.owned_records(owner, "stories", [story_id])[story_id]


# ── writing it ──────────────────────────────────────────────────────────────


def _story(owner: str, story_id: str) -> dict[str, Any]:
    story = graph.owned_records(owner, "stories", [story_id]).get(story_id)
    if story is None or story.get("deleted"):
        raise ApiError(404, "not_found", "That story is not in your vocabulary.")
    return story


def _gloss_language(owner: str, language: str) -> str:
    """The language a story is translated into: the first the vocabulary is glossed into.

    The same one a loop speaks (`services/loops.render_request`), and deliberately not `notesLang`.
    A note is unbounded contrastive prose about a word; a story translation is a rendering of a
    text, which is what a gloss language means. `notesLang` already defaults to this, so the two
    agree unless the owner has deliberately split them.
    """
    vocabulary = next(
        (one for one in graph.owner_vocabularies(owner) if one["language"] == language), None
    )
    return ((vocabulary or {}).get("glossLangs") or ["en"])[0]


# What each of the first three steps has already done, asked of the graph. A step that finds its
# work there is skipped rather than repeated: Try again exists to redo what failed, and the way a story
# fails most often — a recording that would not finish — must not cost a second story.


def _live_parts(owner: str, story_id: str) -> list[dict[str, Any]]:
    return [row for row in graph.story_parts(owner, story_id) if not row.get("deleted")]


def is_written(owner: str, story_id: str) -> bool:
    return bool(_live_parts(owner, story_id))


def is_translated(owner: str, story_id: str) -> bool:
    parts = _live_parts(owner, story_id)
    return bool(parts) and all((row.get("translation") or "").strip() for row in parts)


def is_briefed(owner: str, story_id: str) -> bool:
    parts = _live_parts(owner, story_id)
    return bool(parts) and all((row.get("imagePrompt") or "").strip() for row in parts)


def write_story(settings: Settings, owner: str, device: str, story_id: str) -> dict[str, Any]:
    """Ask for the story, and write its parts. The first and only creative call."""
    story = _story(owner, story_id)
    rows = [row for row in graph.story_words(owner, story_id) if not row.get("deleted")]
    if not rows:
        raise ApiError(422, "empty_story", "That story has no words in it.")

    held = graph.owned_records(owner, "lexemes", [row["lexemeId"] for row in rows])
    words = []
    for row in rows:
        lexeme = held.get(row["lexemeId"]) or {}
        # `article_records` is the reader the image pipeline already feeds from, and it keeps
        # tombstones — `live()` elsewhere is what drops them, and doing it twice is how two readers
        # come to disagree. One definition is enough here: the writer needs to know which meaning
        # is being learned, not the whole article.
        senses = [one for one in article_records(owner, row["lexemeId"]).get("senses", [])
                  if not one.get("deleted")]
        words.append({
            "id": row["lexemeId"],
            "headword": lexeme.get("headword") or row["sourceText"],
            "lemma": lexeme.get("lemma") or "",
            "pos": lexeme.get("pos") or "",
            "gloss": lexeme.get("shortGloss") or lexeme.get("primaryGloss") or "",
            "definition": (senses[0].get("definition") if senses else "") or "",
        })

    candidates = _candidates(settings, owner, "text")
    _require(candidates, settings, owner, "text")
    table = story_types()
    story_type = table.get(story["typeId"] or "") or table.surprise(story_id)

    writer = write.StoryWriter(
        load_catalogue(), candidates, with_rules(_template(settings, WRITE_TEMPLATE), owner)
    )
    request = write.build_request(
        language=story["language"], language_name=language_name(story["language"]),
        words=words, story_type_brief=story_type.brief, story_type_label=story_type.label,
        parts=DEFAULT_PARTS, guidance=story.get("guidance") or "",
    )
    try:
        written, usage = writer.write(request, words)
    except write.StoryRefused as refused:
        # The writer's judgement, not a shape failure. Terminal, and in its own words — the rule
        # `services/loops.refusal` states: the code is ours, the sentence is theirs.
        raise ApiError(422, "story_refused", refused.reason) from None
    except ChainExhausted as exhausted:
        raise refusal(exhausted, "text") from None
    except ProviderError as error:
        raise refusal(error, "text") from None

    at = now_instant()
    stamp = {"ownerId": owner, "deleted": False, "createdAt": at, "editedAt": at,
             "editedBy": device, "revision": 0}
    graph.merge_graph(owner, device, {
        "stories": [{**story, "title": written.title,
                     "emoji": written.emoji or story.get("emoji") or story_type.emoji,
                     "modelId": usage["model"], "editedAt": at, "editedBy": device}],
        "storyParts": [{
            "id": new_record_id(), "storyId": story_id, "position": index,
            "heading": part.heading, "text": part.text,
            "headingTranslation": "", "translation": "",
            "imagePrompt": "", "imageRef": "", "imageModelId": "",
            "attempts": 0, "failureReason": "",
            **stamp,
        } for index, part in enumerate(written.parts)],
        # The forms it actually used, so the reader can mark them. A word it could not use keeps
        # its empty list, which is what the interface shows as unused.
        "storyWords": [{**row, "forms": list(written.forms.get(row["lexemeId"], ())),
                        "editedAt": at, "editedBy": device} for row in rows],
    }, enqueue=None)
    return {"parts": len(written.parts), "unused": list(written.unused([w["id"] for w in words])),
            **usage}


def _parts(owner: str, story_id: str) -> list[dict[str, Any]]:
    rows = [row for row in graph.story_parts(owner, story_id) if not row.get("deleted")]
    if not rows:
        raise ApiError(422, "story_unwritten", "That story has not been written yet.")
    return rows


def translate_story(settings: Settings, owner: str, device: str, story_id: str) -> dict[str, Any]:
    """Translate the whole story at once. See `stories/translate.py` for why not part by part."""
    story = _story(owner, story_id)
    rows = _parts(owner, story_id)
    into = _gloss_language(owner, story["language"])
    # The words the story really used, with the forms it used them in: the translator is asked what
    # became of each so the reader can mark it. A word the writer could not work in has nothing to
    # find a counterpart of, so it is not asked about.
    word_rows = [row for row in graph.story_words(owner, story_id) if not row.get("deleted")]
    asked = [
        {"id": row["lexemeId"], "headword": row["sourceText"], "forms": row["forms"]}
        for row in word_rows if row.get("forms")
    ]

    candidates = _candidates(settings, owner, "text")
    _require(candidates, settings, owner, "text")
    translator = translate.Translator(
        load_catalogue(), candidates, with_rules(_template(settings, TRANSLATE_TEMPLATE), owner)
    )
    parts = [write.Part(row["heading"] or "", row["text"] or "") for row in rows]
    try:
        done, usage = translator.translate(
            translate.build_request(
                title=story.get("title") or "", parts=parts,
                source_name=language_name(story["language"]),
                target_name=language_name(into), target_code=into, words=asked,
            ),
            parts,
        )
    except ChainExhausted as exhausted:
        raise refusal(exhausted, "text") from None
    except ProviderError as error:
        raise refusal(error, "text") from None

    at = now_instant()
    graph.merge_graph(owner, device, {
        "stories": [{**story, "titleTranslation": done.title, "editedAt": at, "editedBy": device}],
        "storyParts": [
            {**row, "translation": done.parts[index].text,
             "headingTranslation": done.parts[index].heading, "editedAt": at, "editedBy": device}
            for index, row in enumerate(rows)
        ],
        # Every word, not only the ones asked about: a translation run again must not leave the marks
        # of the one before it standing against text that is no longer there.
        "storyWords": [
            {**row, "translationForms": list(done.forms.get(row["lexemeId"], ())),
             "editedAt": at, "editedBy": device}
            for row in word_rows
        ],
    }, enqueue=None)
    return {"parts": len(rows), "into": into, **usage}


def brief_story(settings: Settings, owner: str, device: str, story_id: str) -> dict[str, Any]:
    """One call covering every part, so the same character can be kept across every picture."""
    story = _story(owner, story_id)
    rows = _parts(owner, story_id)

    candidates = _candidates(settings, owner, "text")
    _require(candidates, settings, owner, "text")
    briefer = illustrate.BriefWriter(
        load_catalogue(), candidates, with_rules(_template(settings, BRIEF_TEMPLATE), owner)
    )
    parts = [write.Part(row["heading"] or "", row["text"] or "") for row in rows]
    try:
        briefed, usage = briefer.write(
            illustrate.build_request(
                title=story.get("title") or "", parts=parts,
                language_name=language_name(story["language"]),
            ),
            parts,
        )
    except ChainExhausted as exhausted:
        raise refusal(exhausted, "text") from None
    except ProviderError as error:
        raise refusal(error, "text") from None

    at = now_instant()
    graph.merge_graph(owner, device, {"storyParts": [
        {**row, "imagePrompt": briefed.briefs[index], "editedAt": at, "editedBy": device}
        for index, row in enumerate(rows)
    ]}, enqueue=None)
    return {"parts": len(rows), **usage}


def draw_pictures(settings: Settings, owner: str, device: str, story_id: str,
                  gate: Any = None, progress: Any = None) -> dict[str, Any]:
    """Draw the parts that have no picture yet, every one in the story's own style.

    **What is missing is re-derived here rather than passed in**, which is what makes a retry cost
    only what it has to: a run that lost its last picture redraws one and not four.

    **One model draws the whole story, as one voice reads it** (`services/story_audio`): the pair
    that drew its first picture is asked first for every later one, and the chain is walked past it
    only when it is busy or out of allowance, which is what `chain.walk` already does. A fall-through
    mid-story to a model that draws differently is a style change halfway through a book.

    **Later pictures are drawn from the earlier ones** where the owner's `storyContinuity` says so
    for this style: `stories/continuity.py` labels who and where each brief shows, and a part is sent
    the last earlier pictures of its returning people and place. The labels are one small text call
    per run, and opportunistic — a label call that fails, or a pair that takes no reference
    pictures, draws the part exactly as it was drawn before any of this existed.

    `progress(done, total)` is called before the first picture and after each attempt, drawn or
    refused, so a caller can say "picture 2 of 4". It is a plain callable and not a job's step: this
    layer does not know jobs exist, and `gate` is handed in the same way.
    """
    story = _story(owner, story_id)
    styles = load_styles()
    style_id = story.get("styleId") or ""
    if style_id not in styles:
        raise ApiError(422, "unknown_style", "That story names a style this server does not have.")
    style = styles[style_id]

    candidates = _candidates(settings, owner, "image")
    _require(candidates, settings, owner, "image")
    media = Path(settings.media_path)
    catalogue = load_catalogue()
    drawn = 0
    referenced = 0
    failed: list[str] = []

    # Every part, in reading order, because a reference is found by position in the story. Progress
    # is counted over every part that has a brief, not only the ones this run will draw. A run
    # resumed after a rest, or a Try again, then carries on from what is already there instead of
    # restarting from zero over a shorter list — which is how a percentage runs backwards.
    rows = _parts(owner, story_id)
    briefed = [row for row in rows if (row.get("imagePrompt") or "").strip()]
    pending = [
        index for index, row in enumerate(rows)
        if (row.get("imagePrompt") or "").strip() and not row.get("imageRef")
        and int(row.get("attempts") or 0) < MAX_ATTEMPTS
    ]
    attempted = len(briefed) - len(pending)
    if progress is not None:
        progress(attempted, len(briefed))

    labels = _labels(settings, owner, story, rows, style, pending)
    template = _template(settings, REFERENCE_TEMPLATE) if labels else ""

    for index in pending:
        row = rows[index]
        if gate is not None:
            gate()
        chosen: tuple[continuity.Reference, ...] = ()
        if labels is not None:
            chosen = continuity.references(
                labels, index, lambda earlier: _picture_exists(media, rows[earlier]))
        pictures = [media.joinpath(rows[reference.part]["imageRef"]).read_bytes()
                    for reference in chosen]
        try:
            rendered = illustrate.draw(
                row["imagePrompt"], style,
                seed=_seed_for(row["id"], int(row.get("attempts") or 0)),
                candidates=_pinned(candidates, rows), catalogue=catalogue,
                references=pictures,
                with_references=(continuity.compose(
                    template, labels, index, chosen, illustrate.compose(row["imagePrompt"], style))
                    if chosen else None),
            )
        except ChainExhausted as exhausted:
            # **Not counted against the part, and the step stops here.** `services/images.py` states
            # the first half: an allowance that ran out is not something wrong with this brief, so
            # it must not use up the part's retries. The second half is this loop's own — every
            # remaining part would walk the same exhausted chain, so drawing them is spending time
            # to collect the same refusal four times.
            raise refusal(exhausted, "image") from None
        except ProviderRefused as declined:
            # This brief, refused. Recorded on its own row and the loop carries on: one part that
            # could not be drawn must not cost the other three. Try again picks up exactly these.
            at = now_instant()
            graph.merge_graph(owner, device, {"storyParts": [{
                **row, "attempts": int(row.get("attempts") or 0) + 1,
                "failureReason": refusal(declined, "image").message[:500],
                "editedAt": at, "editedBy": device,
            }]}, enqueue=None)
            failed.append(row["id"])
            attempted += 1
            if progress is not None:
                progress(attempted, len(briefed))
            continue

        reference = _picture_reference(story_id, row["id"], rendered.data)
        _place(media, reference, rendered.data)
        previous = row.get("imageRef")
        at = now_instant()
        stored = {
            **row, "imageRef": reference, "imageModelId": rendered.answer.model,
            "attempts": int(row.get("attempts") or 0) + 1, "failureReason": "",
            "editedAt": at, "editedBy": device,
        }
        try:
            graph.merge_graph(owner, device, {"storyParts": [stored]}, enqueue=None)
        except Exception:
            _discard(media, reference, keep=previous, reason="rollback")
            raise
        _discard(media, previous, keep=reference, reason="replaced")
        # Held for the rest of this run: a later part is drawn from this picture, and the pin reads
        # which pair drew it.
        rows[index] = stored
        drawn += 1
        if chosen and catalogue.find(rendered.answer.provider_id).image_references():
            referenced += 1
        attempted += 1
        if progress is not None:
            progress(attempted, len(briefed))

    return {"drawn": drawn, "referenced": referenced, "failed": failed}


def _labels(settings: Settings, owner: str, story: dict[str, Any], rows: list[dict[str, Any]],
            style: Any, pending: list[int]) -> continuity.Continuity | None:
    """Who and where each brief shows, or None when references will not be used this run.

    None when the owner's setting leaves this style out, when nothing left to draw has an earlier
    part to draw from, or when the label call fails for any reason — the pictures are drawn either
    way, and a picture without references is what every story had before.
    """
    if not image_settings.settings(owner).continuity_for(style.photographic):
        return None
    if not any(index > 0 for index in pending):
        return None
    briefs = [(row.get("imagePrompt") or "").strip() for row in rows]
    if not all(briefs):
        return None
    candidates = _candidates(settings, owner, "text")
    if not candidates:
        return None
    labeller = continuity.Labeller(load_catalogue(), candidates,
                                   _template(settings, CONTINUITY_TEMPLATE))
    parts = [write.Part(row["heading"] or "", row["text"] or "") for row in rows]
    try:
        labels, _usage = labeller.label(
            continuity.build_request(title=story.get("title") or "", parts=parts, briefs=briefs),
            len(rows),
        )
    except (ChainExhausted, ProviderError):
        return None
    return labels


def _pinned(candidates: tuple[chain.Candidate, ...],
            rows: list[dict[str, Any]]) -> tuple[chain.Candidate, ...]:
    """The owner's chain with the pair that drew this story's first picture moved to the front.

    Read back off the graph rather than remembered, so a Try again a day later pins the same pair.
    A preference and not a cage: it is only first in the walk, so a busy or exhausted pin is
    stepped over — the lesson `services/story_audio` learned when insisting cost three silent parts.
    """
    model = next((row.get("imageModelId") for row in rows
                  if row.get("imageRef") and row.get("imageModelId")), None)
    if not model:
        return candidates
    first = [candidate for candidate in candidates if candidate.model == model][:1]
    return (*first, *(candidate for candidate in candidates if candidate not in first))


def _picture_exists(media: Path, row: dict[str, Any]) -> bool:
    reference = row.get("imageRef")
    return bool(reference) and media.joinpath(reference).is_file()


def _seed_for(part_id: str, attempt: int) -> int:
    digest = hashlib.sha256(f"acervo/storyPart/v1:{part_id}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2 ** 31)


def _picture_reference(story_id: str, part_id: str, data: bytes) -> str:
    """A digest of the bytes, so a redraw is a *new* reference and a cached picture simply misses.

    `images/ids.image_reference`'s rule, and the reason `mediaStore.ts` is a cache with no
    invalidation in it at all.
    """
    return f"stories/{story_id}/{part_id}-{hashlib.sha256(data).hexdigest()[:8]}.webp"


def _place(media: Path, reference: str, data: bytes) -> None:
    destination = media / reference
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, destination)


def _discard(media: Path, reference: str | None, *, keep: str | None, reason: str) -> None:
    if reference and reference != keep:
        media_files.remove(media, reference, reason)


# ── removing one ────────────────────────────────────────────────────────────


def remove(settings: Settings, owner: str, device: str, story_id: str) -> dict[str, Any]:
    """Delete a story: its row, its parts, its words, and the pictures and recordings themselves.

    A route rather than a client-side tombstone for `services/loops.remove`'s reason: the pictures
    are megabytes, nothing else would ever remove them, and the same party has to write the row and
    unlink the file or one of them is a lie.

    The files go **after** the rows land, never before: a merge that raises must not take the
    pictures of a story that still exists with it.
    """
    story = _story(owner, story_id)
    at = now_instant()
    stamp = {"deleted": True, "editedAt": at, "editedBy": device}
    parts = [row for row in graph.story_parts(owner, story_id) if not row.get("deleted")]
    words = [row for row in graph.story_words(owner, story_id) if not row.get("deleted")]
    graph.merge_graph(owner, device, {
        "stories": [{**story, **stamp}],
        "storyParts": [{**row, **stamp} for row in parts],
        "storyWords": [{**row, **stamp} for row in words],
    }, enqueue=None)

    media = Path(settings.media_path)
    for row in parts:
        # The picture, and one file for every passage that was read aloud.
        references = [row.get("imageRef")] + [
            one.get("audioRef") for one in (row.get("audioSegments") or []) if isinstance(one, dict)
        ]
        for reference in references:
            media_files.remove(media, reference, "deleted")
    return graph.owned_records(owner, "stories", [story_id])[story_id]
