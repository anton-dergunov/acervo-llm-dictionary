"""`enrich`: what a saved word gets, whoever saved it (`docs/architecture/jobs.md`).

Three steps, in this order: clips, then pictures (a brief, then one draw per sense), then
pronunciations. Clips first because one call covers every sense and it is the step that changes the
example set; pictures second because they are what the owner is waiting to see; pronunciations last
because they are invisible, and by then the examples are final.

A job says *which word*. Each step reads what that word still lacks from the graph when it starts,
and reads its own switch then too, so a job run twice writes nothing the second time and a setting
changed mid-job affects the next step to run. "None" is a finished outcome: a word with no clip or no
picture is complete.

Every step calls the service function a route calls. Nothing here is a second pipeline.
"""

from __future__ import annotations

from typing import Any

from acervo.article import GENERATED_STATUSES, live
from acervo.errors import ApiError
from acervo.images.ids import image_prompt_id
from acervo.pronunciation.ids import pronunciation_id
from acervo.pronunciation.targets import COLLECTION, current, wanted
from acervo.repository import clip_settings, graph, image_settings, pronunciation_settings
from acervo.settings import Settings
from acervo.services import clips, images, pronunciations
from acervo.work import retry
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Step

# What the graph records as having written an enrichment. A device id like any other writer's.
DEVICE = "acervorunner"

STEPS = ("clips", "pictures", "pronunciations")


def _enriched(records: dict[str, list[dict]], lexeme_id: str) -> dict[str, Any] | None:
    """The word, if it is one worth enriching: live, and not set aside. A word set aside is treated as
    absent, so every step skips it and a backfill never queues it."""
    return next(
        (row for row in live(records.get("lexemes", []))
         if row["id"] == lexeme_id and row.get("status") in GENERATED_STATUSES),
        None,
    )


def _word(context: JobContext) -> tuple[dict[str, Any] | None, dict[str, list[dict]]]:
    records = graph.article_records(context.owner, context.subject_id)
    return _enriched(records, context.subject_id), records


def _senses(records: dict[str, list[dict]], lexeme_id: str) -> list[dict]:
    return [row for row in live(records.get("senses", [])) if row.get("lexemeId") == lexeme_id]


# ── clips ───────────────────────────────────────────────────────────────────


def find_clips(context: JobContext, step: Step) -> str | None:
    if not clip_settings.settings(context.owner).search_enabled:
        return "skipped"
    if not context.settings.speech_url:
        # A deployment without a corpus. Not a failure of this word.
        return "skipped"
    lexeme, records = _word(context)
    if lexeme is None or lexeme.get("clipsSearchedAt") or not _senses(records, lexeme["id"]):
        return "skipped"
    step.gate()
    answer = clips.find_clips(context.settings, context.owner, DEVICE, lexeme["id"])
    if not answer["searched"]:
        step.note(skipped=answer["skipped"])
        return "skipped"
    step.note(found=len(answer["examples"]))
    return None


# ── pictures ────────────────────────────────────────────────────────────────


def _prompts(records: dict[str, list[dict]]) -> dict[str, dict]:
    return {row["id"]: row for row in live(records.get("imagePrompts", []))}


def _unbriefed(records: dict[str, list[dict]], lexeme_id: str) -> list[dict]:
    held = _prompts(records)
    return [sense for sense in _senses(records, lexeme_id)
            if image_prompt_id(sense["id"]) not in held]


def _drawable(records: dict[str, list[dict]], lexeme_id: str) -> list[dict]:
    """Rows with a brief and no picture that nothing has ruled out.

    A row the provider declined carries a `failureReason`, and is left for the owner's Try again
    rather than drawn again on its own — which is what keeps a second run of this job silent.
    """
    live_senses = {sense["id"] for sense in _senses(records, lexeme_id)}
    return [
        row for row in _prompts(records).values()
        if row.get("senseId") in live_senses
        and not row.get("imageRef")
        and not row.get("suppressed")
        and not row.get("failureReason")
        and (row.get("prompt") or "").strip()
        and int(row.get("attempts") or 0) < images.MAX_ATTEMPTS
    ]


def draw_pictures(context: JobContext, step: Step) -> str | None:
    if not image_settings.settings(context.owner).draw_enabled:
        return "skipped"
    lexeme, records = _word(context)
    if lexeme is None:
        return "skipped"
    briefed = False
    if _unbriefed(records, lexeme["id"]):
        step.gate()
        images.brief_lexeme(context.settings, context.owner, DEVICE, lexeme["id"])
        briefed = True
        lexeme, records = _word(context)
        if lexeme is None:
            return "skipped"

    drawable = sorted(_drawable(records, lexeme["id"]), key=lambda row: row["id"])
    if not drawable:
        return None if briefed else "skipped"
    # A step put back to wait keeps what it had already drawn, so "2 of 3" stays true across a rest.
    done = int(step.record.get("done") or 0)
    total = done + len(drawable)
    refused = int((step.record.get("detail") or {}).get("refused") or 0)
    step.progress(done, total)
    for row in drawable:
        step.gate()
        drawn = images.render_prompt(context.settings, context.owner, DEVICE, row["id"])
        if not drawn.get("imageRef"):
            refused += 1
            step.note(refused=refused)
        done += 1
        step.progress(done, total)
    if refused:
        raise ApiError(
            502, "image_refused",
            f"{total - refused} of {total} pictures drawn; the provider declined the rest.",
        )
    return None


# ── pronunciations ──────────────────────────────────────────────────────────


def record_pronunciations(context: JobContext, step: Step) -> str | None:
    chosen = pronunciation_settings.settings(context.owner)
    choice = chosen.pregenerate
    if not chosen.words_in_advance:
        return "skipped"
    lexeme, records = _word(context)
    if lexeme is None:
        return "skipped"
    clips_held = {row["id"]: row for row in records.get("pronunciations", [])}
    targets = [
        target for target in wanted(records, lexeme["id"], choice)
        if not current(clips_held.get(pronunciation_id(target.kind, target.id)), target)
    ]
    if not targets:
        return "skipped"
    done = int(step.record.get("done") or 0)
    total = done + len(targets)
    step.progress(done, total)
    failure: ApiError | None = None
    for target in targets:
        step.gate()
        try:
            pronunciations.pronounce(
                context.settings, context.owner, DEVICE, COLLECTION[target.kind], target.id
            )
        except ApiError as refusal:
            # A busy provider is the runner's to wait out, for every field at once. Anything else is
            # this field's own problem, and the next field may well be fine.
            if retry.is_transient(refusal.code):
                raise
            failure = failure or refusal
        done += 1
        step.progress(done, total)
    if failure is not None:
        raise failure
    return None


# ── what is missing ─────────────────────────────────────────────────────────


def lacking(settings: Settings, owner: str, lexeme_id: str) -> list[str]:
    """Which steps would do something for this word, in step order. Empty means it is complete.

    The same questions each step asks when it starts, asked without running anything — which is what
    a backfill needs, and the reason it is one function rather than two sets of rules.
    """
    records = graph.article_records(owner, lexeme_id)
    lexeme = _enriched(records, lexeme_id)
    if lexeme is None:
        return []
    found = []
    if settings.speech_url and clip_settings.settings(owner).search_enabled \
            and not lexeme.get("clipsSearchedAt") and _senses(records, lexeme_id):
        found.append("clips")
    if image_settings.settings(owner).draw_enabled \
            and (_unbriefed(records, lexeme_id) or _drawable(records, lexeme_id)):
        found.append("pictures")
    chosen = pronunciation_settings.settings(owner)
    choice = chosen.pregenerate
    if chosen.words_in_advance:
        clips_held = {row["id"]: row for row in records.get("pronunciations", [])}
        if any(not current(clips_held.get(pronunciation_id(target.kind, target.id)), target)
               for target in wanted(records, lexeme_id, choice)):
            found.append("pronunciations")
    return found


def incomplete(settings: Settings, owner: str, *, language: str = "",
               limit: int = 0) -> list[dict[str, Any]]:
    """The owner's words that are missing something, newest first.

    A query against the graph rather than a list anybody keeps: running a backfill late, twice or
    never costs latency and nothing else.
    """
    words = sorted(
        (row for row in live(graph.pull(owner, 0)["changes"]["lexemes"])
         if not language or row["language"] == language),
        key=lambda row: (row["createdAt"], row["id"]),
        reverse=True,
    )
    found = []
    for word in words:
        steps = lacking(settings, owner, word["id"])
        if steps:
            found.append({"id": word["id"], "headword": word["headword"], "lacking": steps})
        if limit and len(found) >= limit:
            break
    return found


def enrich(context: JobContext) -> None:
    context.step("clips", lambda step: find_clips(context, step), lane="clip")
    context.step("pictures", lambda step: draw_pictures(context, step), lane="image")
    context.step("pronunciations", lambda step: record_pronunciations(context, step), lane="audio")


register(Kind("enrich", STEPS, enrich))
