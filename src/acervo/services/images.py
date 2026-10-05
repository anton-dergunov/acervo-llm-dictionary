"""Acervo's binding to the image pipeline: settings and the graph in, a picture on disk out.

The other half of the split `acervo.images` makes, and the same split `services/models.py` makes
against `acervo.models`. `acervo.images` knows what a picture is; this module knows whose it is,
where it goes, which chain draws it and what Acervo's API calls a failure to draw one — and it
speaks the same `llm_*` codes, through the same `services.models.refusal`, because a picture that
could not be drawn and an entry that could not be written should fail alike.

**The unit of work is one model call**, and each one is an ordinary synchronous route in the
threadpool — the shape capture already has, for a sharper reason than symmetry. A whole-lexeme route
would outlive the client's own timeout while the server kept drawing; the client would retry and the
picture would be drawn, and billed, twice.

Every operation is read (transaction) → model call (**no** transaction) → write (transaction). A
repository function is a transaction and owns its own session; an image call of up to two minutes
inside one would block every other request for as long as it ran.

Nothing here is a second write path. Rows go through `repository.graph.merge_graph`, the same route
a phone's writes take, with the same validation and the same revision allocation. The server writes
the row as well as the file because it is the only party holding both — a picture is not a capture
draft, which is a proposal for a person to review; there is nothing here to review and nothing the
client could have produced.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from acervo.article import ArticleView, article_for
from acervo.domain.ids import now_instant
from acervo.errors import ApiError
from acervo.images.brief import BriefWriter, SenseBrief
from acervo.images.compose import compose, prompt_version
from acervo.images.ids import image_prompt_id, image_reference, seed_for
from acervo.images.render import Renderer, as_master
from acervo.images.styles import StyleTable, load_styles
from acervo.models import ChainExhausted, ProviderError, ProviderRefused, chain, load_catalogue
from acervo.repository import graph, image_settings
from acervo.services import media as media_files
from acervo.services.models import chain_for, refusal
from acervo.services.rules import with_rules
from acervo.settings import Settings

# How many times a sense is drawn before the sweep leaves it alone. In code rather than in the
# record, which is what keeps `attempts` a count and stops it becoming a status enum: the record
# says what happened, the threshold says what to do about it, and only one of those is data.
MAX_ATTEMPTS = 4

# Every call here makes one attempt. Whether to ask again after a quota or an outage is the job
# runner's decision (`acervo/work/retry.py`), made in one place.

# `drawEnabled` is checked by the thing that draws *on its own* — the `enrich` job — and
# deliberately not by the routes below. A route draws what
# it is asked, because every caller of it other than those two is a person pressing a button, and
# switching automatic drawing off is precisely how you get a word with no pictures and then add the
# one you want by hand. Gating the routes would take that away.

BRIEF_TEMPLATE = "acervo_image_brief.md"


def _template(settings: Settings) -> Path:
    return Path(settings.prompts_path) / BRIEF_TEMPLATE


def _styles() -> StyleTable:
    return load_styles()


def _candidates(settings: Settings, owner: str, kind: str) -> tuple[chain.Candidate, ...]:
    """The owner's chain for one kind, resolved against this server's credentials.

    Resolved per call rather than cached, for `chain_for`'s reason: it is one indexed read against a
    local SQLite file set against a model call of up to two minutes, and caching it would mean a
    change in Settings ▸ Pictures took effect at some unpredictable later time.
    """
    try:
        return chain.resolve(kind, chain_for(settings, owner, kind), load_catalogue())
    except ProviderError as error:
        raise refusal(error, kind) from None


def _require(candidates: tuple[chain.Candidate, ...], settings: Settings, owner: str, kind: str) -> None:
    if not candidates:
        raise refusal(chain.unconfigured(kind, chain_for(settings, owner, kind), load_catalogue()), kind)


# ── settings ────────────────────────────────────────────────────────────────


def settings_view(settings: Settings, owner: str) -> dict[str, Any]:
    """What the owner chose, what they could choose, and whether a picture can be drawn at all.

    The style table travels with the settings rather than through a route of its own: the switches
    are meaningless without the labels, and one round trip cannot show a half-loaded screen.
    """
    table = _styles()
    chosen = image_settings.settings(owner)
    candidates = _candidates(settings, owner, "image")
    return {
        **chosen,
        "maxAttempts": MAX_ATTEMPTS,
        "styles": [
            {"id": style.id, "label": style.label, "mono": style.mono,
             "photographic": style.photographic}
            for style in table.styles
        ],
        # Whether this server could draw one right now, so the screen can say "no provider is
        # configured" instead of offering a button that will refuse.
        "available": bool(candidates),
    }


def apply_settings(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validate a submitted document, store it, and answer with the whole readout.

    The only validator, exactly as `services/models.apply_selection` is for chains: the repository
    stores what it is given and deliberately does not know which styles exist. Two validators would
    be one drift.
    """
    table = _styles()
    changes: dict[str, Any] = {}

    if "drawEnabled" in body:
        changes["draw_enabled"] = _flag(body["drawEnabled"], "drawEnabled")
    if "boostVariety" in body:
        changes["boost_variety"] = _flag(body["boostVariety"], "boostVariety")
    if "storyContinuity" in body:
        if body["storyContinuity"] not in image_settings.CONTINUITY:
            raise ApiError(400, "invalid_input",
                           f"storyContinuity takes {', '.join(image_settings.CONTINUITY)}.")
        changes["story_continuity"] = body["storyContinuity"]
    if "stylesOff" in body:
        submitted = body["stylesOff"]
        if not isinstance(submitted, list):
            raise ApiError(400, "invalid_input", "The switched-off styles must be a list of ids.")
        unknown = [str(one) for one in submitted if str(one) not in table]
        if unknown:
            raise ApiError(
                400, "unknown_style",
                f"This server has no style called {unknown[0]!r}.",
            )
        if len(set(map(str, submitted))) >= len(table.styles):
            # `StyleTable.offer` raises on an empty menu, which would refuse every brief from here
            # on with an error about the style table rather than about the choice that caused it.
            raise ApiError(
                400, "no_styles_left",
                "At least one style must stay switched on, or no picture can be drawn.",
            )
        changes["styles_off"] = [str(one) for one in submitted]

    image_settings.save(owner, **changes)
    return settings_view(settings, owner)


def _flag(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ApiError(400, "invalid_input", f"{field} must be true or false.")
    return value


# ── the two calls ───────────────────────────────────────────────────────────


def brief_lexeme(settings: Settings, owner: str, device: str, lexeme_id: str,
                 revive: str | None = None) -> dict[str, Any]:
    """One text call for every sense of one word, and the rows it produces.

    Batched per lexeme because §03's batching is load-bearing: a writer that sees both senses of
    *venom* can deliberately make them look nothing alike, which is the whole reason per-sense
    pictures beat one per word. It is also why this is per lexeme and rendering is per sense.

    A sense the writer **refuses** gets a row too, with no brief, the reason it gave, and
    `suppressed`. That refusal is a finished outcome, and a row is the only place it can be recorded
    where the sweep will see it; leaving the sense bare would have it re-briefed every night forever.

    `revive` names the one sense whose picture dialog asked, and that sense is briefed even though
    the owner ruled it out — asking for a new brief from its own dialog is taking the ruling back,
    exactly as drawing there is. Every other ruled-out sense stays ruled out.
    """
    chosen = image_settings.settings(owner)
    candidates = _candidates(settings, owner, "text")
    _require(candidates, settings, owner, "text")

    view, stored = _article(owner, lexeme_id)
    table = _styles()
    writer = BriefWriter(
        load_catalogue(), candidates,
        with_rules(_template(settings).read_text(encoding="utf-8"), owner), table,
        weights=chosen.weights(style.id for style in table.styles),
        boost_variety=chosen.boost_variety,
    )

    try:
        briefs, usage = writer.write(view)
    except ChainExhausted as exhausted:
        # Every pair was asked and none could hold the shape. Said as a picture problem rather than
        # in the generic words, because that is what the reader was trying to do.
        if exhausted.last.reason == "unusable":
            raise ApiError(
                502, "llm_unusable", "The language model did not describe a usable picture."
            ) from None
        raise refusal(exhausted) from None
    except ProviderError as error:
        raise refusal(error) from None
    except ValueError as unusable:
        # `parse_reply` refusing the answer: an unknown sense id, an off-menu style, an empty brief.
        raise ApiError(
            502, "llm_unusable", "The language model did not describe a usable picture."
        ) from unusable

    version = prompt_version(_template(settings), table.digest)
    # From the raw records rather than from `view.image_prompts`, and the difference is a real bug
    # rather than a nicety: `build_articles` filters tombstones, which is right for the pipeline and
    # wrong here. A tombstoned row still holds its id and its revision, and this id is *derived*
    # from the sense — so writing revision zero over it is refused as stale, and the sense could
    # never be briefed again. Editing a word's YAML and dropping its imagePrompts block is enough to
    # produce one.
    held = {row["id"]: row for row in stored.get("imagePrompts", [])}
    at = now_instant()
    written = [
        _brief_row(brief, view, held, version, usage["model"], at, device)
        for brief in briefs
        # A sense the owner has ruled on is not re-briefed, and this is the check that makes
        # `suppressed` mean something rather than being a field nothing reads.
        if brief.sense_id == revive
        or not (held.get(image_prompt_id(brief.sense_id)) or {}).get("suppressed")
    ]
    if written:
        graph.merge_graph(owner, device, {"imagePrompts": written}, enqueue=None)
    return {"lexemeId": lexeme_id, "imagePrompts": [_readable(row, table) for row in written]}


def _brief_row(brief: SenseBrief, view: ArticleView, held: dict[str, dict],
               version: str, model: str, at: str, device: str) -> dict[str, Any]:
    prompt_id = image_prompt_id(brief.sense_id)
    existing = held.get(prompt_id)
    # A new row states revision zero; an existing one states the revision it was edited from, and a
    # stale one is refused rather than merged. Rewriting a brief deliberately keeps `attempts`: the
    # count is of how often this sense has been *drawn*, which a new brief does not undo.
    base = {
        "id": prompt_id,
        "lexemeId": view.id,
        "senseId": brief.sense_id,
        "exampleId": brief.anchor_example_id,
        "promptVersion": version,
        "modelId": model,
        "attempts": (existing or {}).get("attempts", 0),
        # A tombstoned row is revived rather than left dead: the id is derived from the sense, so
        # there is no other row this brief could ever occupy.
        "deleted": False,
        "createdAt": (existing or {}).get("createdAt", at),
        "editedAt": at,
        "editedBy": device,
        "revision": (existing or {}).get("revision", 0),
    }
    if brief.refused:
        return {
            **base,
            "prompt": "",
            "styleId": "",
            "seed": 0,
            "imageRef": None,
            "imageModelId": None,
            "failureReason": brief.refusal_reason or "the writer declined to describe this sense",
            "suppressed": True,
        }
    return {
        **base,
        "prompt": brief.brief,
        "styleId": brief.style_id,
        "seed": seed_for(brief.sense_id, base["attempts"]),
        # A rewritten brief keeps the picture it already has until a new one is drawn, so the
        # article never goes blank while you are looking at it.
        "imageRef": (existing or {}).get("imageRef"),
        "imageModelId": (existing or {}).get("imageModelId"),
        "failureReason": None,
        "suppressed": False,
    }


def _place(media: Path, reference: str, data: bytes) -> None:
    """Put the bytes where the reference says, whole or not at all.

    Written beside the target and moved into place, so a reader never sees a half-written file. Two
    writers can only collide here by having drawn byte-identical pictures, the name carrying a digest
    of what it holds — and then they are writing the same thing.
    """
    destination = media / reference
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, destination)


def _discard(media: Path, reference: str | None, *, keep: str | None, reason: str) -> None:
    """Remove a file no row names any more.

    `keep` is not defensive: a redraw that comes out byte-for-byte identical lands on the same
    reference, and that file is the current one. Without the guard it would be deleted immediately
    after being written and the article would break.
    """
    if reference and reference != keep:
        media_files.remove(media, reference, reason)


def render_prompt(settings: Settings, owner: str, device: str, prompt_id: str,
                  body: dict[str, Any] | None = None) -> dict[str, Any]:
    """One image call for one sense. The picture lands on disk, then the row lands in the graph.

    Files first, then rows, for `publish.py`'s reason: a row whose file is missing is a broken
    picture the owner sees, and a file whose row is missing is an orphan nobody looks at. Then the
    file the row *used* to name is removed, which is the order `pronunciations._store` writes in and
    for the same reason: the name carries a digest of the bytes, so the picture being replaced is a
    different file and stays readable until the row naming its successor has landed.

    `body` may carry a `prompt` and a `styleId` — edit-and-draw, which costs no text call. Without
    them the stored brief is drawn again with a fresh seed, so a picture you disliked is genuinely
    different rather than the same one back.
    """
    body = body or {}
    record = _held(owner, prompt_id)
    table = _styles()

    brief = str(body.get("prompt") or record["prompt"] or "").strip()
    if not brief:
        raise ApiError(
            400, "no_brief",
            "This picture has no description to draw from. Write a new brief for the word first.",
        )
    style_id = str(body.get("styleId") or record["styleId"] or "")
    if style_id not in table:
        raise ApiError(400, "unknown_style", f"This server has no style called {style_id!r}.")

    candidates = _candidates(settings, owner, "image")
    _require(candidates, settings, owner, "image")

    attempts = int(record["attempts"] or 0) + 1
    seed = seed_for(record["senseId"] or record["id"], attempts)

    # What was tried, written whether or not it worked. An edited brief has to be stored with the
    # version it was composed under: the style table and the template are what turn a brief into
    # the prompt that was sent, so a brief without them reproduces nothing — and the validator says
    # so, which is how a picture attached earlier (no version at all) would otherwise refuse an
    # edit-and-draw with a message about the wrong thing.
    tried = {
        **_state(record),
        "prompt": brief,
        "styleId": style_id,
        "promptVersion": prompt_version(_template(settings), table.digest),
        "seed": seed,
        "attempts": attempts,
    }

    try:
        drawn = _draw(candidates, compose(brief, table[style_id]), seed)
    except ProviderRefused as declined:
        if declined.reason == "refused":
            # The provider looked at the prompt and said no. Terminal for this wording, so it is
            # recorded rather than retried — but not suppressed: a different brief may well pass,
            # and that is exactly what the edit-and-draw flow is for. The brief it declined is kept,
            # because "what was tried" is the only useful thing to show next to the reason.
            return _write(owner, device, {
                **tried,
                "failureReason": declined.detail or "the provider declined to draw this",
            }, table)
        raise refusal(declined, "image") from None
    except ChainExhausted as exhausted:
        # Nothing was drawn and nothing is wrong with the request, so the attempt is not counted
        # against the sense: an allowance that ran out must not use up a sense's retries, and the
        # row is left exactly as it was. The interface re-reads what is still drawable after it
        # rests, which is what turns that into a retry rather than a word left one picture short.
        raise refusal(exhausted, "image") from None
    except ProviderError as error:
        raise refusal(error, "image") from None

    media = Path(settings.media_path)
    previous = record["imageRef"]
    # From the *stored* lexeme id, after the row was confirmed to be this owner's — never from
    # anything the request said, which is what keeps a path traversal from being expressible.
    reference = image_reference(record["lexemeId"], prompt_id, drawn.data)
    _place(media, reference, drawn.data)
    try:
        written = _write(owner, device, {
            **tried,
            "imageRef": reference,
            "imageModelId": drawn.answer.model,
            "failureReason": None,
            "suppressed": False,
        }, table)
    except Exception:
        # The row never landed, so the picture the owner is looking at is still the old one and this
        # file is the orphan. `keep` covers the redraw that changed nothing: then they are one file.
        _discard(media, reference, keep=previous, reason="rollback")
        raise
    _discard(media, previous, keep=reference, reason="replaced")
    return written


def _draw(candidates: tuple[chain.Candidate, ...], prompt: str, seed: int):
    """Walk the pairs until one draws, resting the ones that could not.

    Through `chain.walk` even when there is only one pair, and that is not for tidiness: `walk` is
    what remembers a refusal, so a chain that skipped it on the single-provider case would re-probe
    an exhausted allowance on every word. `chain.stamped` works on a `Rendered` unchanged, because
    it is a frozen dataclass with an `answer` field like every other result in the package.
    """
    renderer = Renderer()
    return chain.walk(
        "image",
        [candidate.named for candidate in candidates],
        load_catalogue(),
        lambda candidate: renderer.draw(prompt, seed, candidate),
        chain.stamped,
        caller="picture",
    )


# ── the picture the owner supplies, and the one they rule out ───────────────


def attach_picture(settings: Settings, owner: str, device: str, sense_id: str,
                   data: bytes, drawn_by: str = "") -> dict[str, Any]:
    """Put a file where a drawn picture would have gone.

    Two callers, told apart by `drawn_by`, and the difference is provenance rather than mechanism:

    - **The owner choosing a picture.** No model drew it, so `imageModelId` stays empty — the same
      way an example the learner wrote carries no `modelId` — and the row is `suppressed`, because
      choosing a picture is choosing it and nothing should draw over it.
    - **An import putting one back**, naming the model that drew it originally. That is a fact about
      the past, carried in the bundle exactly as an example's `origin` is, so the row keeps it and
      is *not* suppressed: a restored picture is an ordinary drawn one and can be redrawn.

    Nothing anywhere in Acervo has a "the user supplied this" boolean and this must not be the
    first; the absence of a rendering model is what says it.

    Keyed by the **sense**, not by an image prompt, and that is the point rather than a detail: a
    sense that has never been briefed has no prompt to name, and both callers hit exactly that case
    — the owner would not want to spend a text call before choosing a file, and an import restores
    a picture into a word it has only just written. The prompt id is *derived* from the sense, so
    the row is either found or minted at the id it was always going to have.

    Re-encoded to the same 1024² WebP master rather than stored as handed over, so every picture in
    the article is one kind of thing and a 12 MB phone photograph does not become a 12 MB download —
    unless it already is one, which is what every picture an import puts back is (`as_master`).
    """
    prompt_id = image_prompt_id(sense_id)
    lexeme_id, existing = _sense_row(owner, sense_id, prompt_id)
    try:
        master = as_master(data)
    except Exception as unreadable:  # noqa: BLE001 — every decoder failure means the same thing here
        raise ApiError(400, "unreadable_image", "That file could not be read as an image.") from unreadable

    media = Path(settings.media_path)
    previous = (existing or {}).get("imageRef")
    reference = image_reference(lexeme_id, prompt_id, master)
    _place(media, reference, master)

    at = now_instant()
    base = existing or {
        "id": prompt_id, "lexemeId": lexeme_id, "senseId": sense_id, "exampleId": None,
        "prompt": "", "styleId": "", "seed": 0, "modelId": "", "promptVersion": "",
        "attempts": 0, "createdAt": at, "revision": 0,
    }
    restoring = bool(drawn_by.strip())
    try:
        written = _write(owner, device, {
            **base,
            "editedAt": at,
            # A tombstoned row is revived: the id is derived, so this is the only row it could be.
            "deleted": False,
            "imageRef": reference,
            "imageModelId": drawn_by.strip() or None,
            "failureReason": None,
            # Choosing a picture is choosing it, so nothing draws over it. A restored one is an
            # ordinary drawn picture and stays replaceable.
            "suppressed": not restoring,
        }, _styles())
    except Exception:
        _discard(media, reference, keep=previous, reason="rollback")
        raise
    _discard(media, previous, keep=reference, reason="replaced")
    return written


def _sense_row(owner: str, sense_id: str, prompt_id: str) -> tuple[str, dict[str, Any] | None]:
    """The sense's word, and its image prompt if it has one — tombstone included.

    Tombstones included for the reason `brief_lexeme` documents: the id is derived, so a dead row
    still owns it, and writing revision zero over one is refused as stale.
    """
    sense = graph.sense_record(owner, sense_id)
    if sense is None:
        raise ApiError(404, "not_found", "That sense is not in your vocabulary.")
    records = graph.article_records(owner, sense["lexemeId"])
    existing = next(
        (row for row in records.get("imagePrompts", []) if row["id"] == prompt_id), None
    )
    return sense["lexemeId"], existing


def suppress_prompt(settings: Settings, owner: str, device: str, prompt_id: str) -> dict[str, Any]:
    """Remove the picture and rule the sense out, permanently and on purpose.

    Deliberately not a tombstone. `image_prompt_id` is derived from `senseId`, so a tombstoned row
    is invisible to the sweep, which re-briefs the sense and mints **the same id** — tombstoning
    does not prevent regeneration, it guarantees a collision at a higher revision. The row stays,
    visible, saying the owner has ruled on this sense.
    """
    record = _held(owner, prompt_id)
    if record["imageRef"]:
        # `missing_ok`: the file may already be gone, and refusing to record the owner's decision
        # because of that would leave the sweep drawing it again.
        media_files.remove(settings.media_path, record["imageRef"], "deleted")

    return _write(owner, device, {
        **_state(record),
        "imageRef": None,
        "imageModelId": None,
        "suppressed": True,
    }, _styles())


# ── shared ──────────────────────────────────────────────────────────────────


def _article(owner: str, lexeme_id: str) -> tuple[ArticleView, dict[str, list[dict]]]:
    """The article the writer is given, and the records it was built from.

    Both, because they answer different questions. The view drops tombstones, which is what the
    brief writer wants; the records keep them, which is what a writer of *rows* needs — see the
    comment at the `held` map above.
    """
    records = graph.article_records(owner, lexeme_id)
    found = article_for(records, lexeme_id)
    if found is None:
        # One message for "no such word", "somebody else's word" and "a word you deleted": telling
        # them apart would answer whether an id exists in another account.
        raise ApiError(404, "not_found", "That word is not in your vocabulary.")
    if not found.senses:
        raise ApiError(400, "no_senses", "A word with no senses has nothing to draw.")
    return found, records


def prompt_view(owner: str, prompt_id: str) -> dict[str, Any]:
    """One picture's row and the whole prompt it composes to, for the picture dialog to show."""
    return _readable(_held(owner, prompt_id), _styles())


def _held(owner: str, prompt_id: str) -> dict[str, Any]:
    record = graph.image_prompt(owner, prompt_id)
    if record is None:
        raise ApiError(404, "not_found", "That picture is not in your vocabulary.")
    return record


def _state(record: dict[str, Any]) -> dict[str, Any]:
    """The stored row as the basis of the next write.

    Every field is carried across and the caller overrides what it changed, because
    `_assign_image_prompt` builds a whole row from the wire value — an omitted field is a reset, not
    a no-op. `revision` is the one it was read at, so a concurrent write is refused rather than
    silently overwritten.
    """
    return {**record, "editedAt": now_instant()}


def _write(owner: str, device: str, record: dict[str, Any], table: StyleTable) -> dict[str, Any]:
    graph.merge_graph(owner, device, {"imagePrompts": [{**record, "editedBy": device}]},
                      enqueue=None)
    stored = graph.image_prompt(owner, record["id"])
    return _readable(stored or record, table)


def _readable(record: dict[str, Any], table: StyleTable) -> dict[str, Any]:
    """The row, plus the prompt that was actually sent — which is composed and never stored.

    §04 stores the brief, the style id and the version because those three plus the tracked files
    reproduce the full prompt exactly. The regenerate screen wants to *show* it, so it is rebuilt
    here rather than becoming an eleventh column holding the same text twice.
    """
    style_id = record.get("styleId") or ""
    brief = record.get("prompt") or ""
    composed = compose(brief, table[style_id]) if brief and style_id in table else None
    return {**record, "composedPrompt": composed}
