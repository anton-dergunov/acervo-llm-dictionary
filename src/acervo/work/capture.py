"""`capture`: a submission of text turned into Inbox entries, with nobody reviewing.

See `docs/architecture/jobs.md`.

The submission is the unit, and the words are its output: stream-mode resolve discovers where each
entry ends while it runs. For each one the job stops at a word the owner already holds, or composes
the entry and saves it through the same save the interface makes — filed in the Inbox, and enriched
by a child `enrich` job.

Progress is recorded on the step as it goes (`consumedLines`, and one outcome per word), so a job put
back to wait out a busy provider carries on from the entry it was on, and a job that fails says
exactly how much of the text it finished. That is what a caller's checkpoint advances by.
"""

from __future__ import annotations

from typing import Any

from acervo.errors import ApiError
from acervo.repository import graph
from acervo.services.articles import save_article
from acervo.services.capture.pipeline import leading_blanks, logical_block, propose
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, JobFailed, Step

DEVICE = "acervocapture"
WINDOW = 40


def _check_configuration(owner: str, request: dict[str, Any]) -> None:
    """Before the first model call can spend money: the language hint and the topics must exist."""
    language = str(request.get("language") or "").strip().lower()
    if language and language not in {v["language"].lower() for v in graph.owner_vocabularies(owner)}:
        raise JobFailed(
            "language_not_configured",
            f"The account has no {language} vocabulary. Add it in Settings, then submit this again.",
        )
    known = {topic["name"].strip().lower() for topic in graph.owner_topics(owner)}
    missing = [str(name) for name in request.get("topics") or []
               if str(name).strip().lower() not in known]
    if missing:
        raise JobFailed(
            "topic_not_configured",
            "The account has no topic called " + ", ".join(missing)
            + ". Add or rename it, then submit this again.",
        )


def walk(context: JobContext, step: Step) -> str | None:
    request = dict(context.input)
    stream = str(request.get("mode") or "stream") == "stream"
    lines = str(request.get("text") or "").split("\n")
    window_size = max(1, int(request.get("window") or WINDOW))
    complete = request.get("complete", True) is not False
    limit = int(request.get("limit") or 0)

    detail = step.record.get("detail") or {}
    offset = int(detail.get("consumedLines") or 0)
    words: list[dict[str, Any]] = list(detail.get("words") or [])

    def record(outcome: dict[str, Any], consumed: int) -> None:
        nonlocal offset
        if outcome:
            words.append(outcome)
        offset += consumed
        step.note(words=words, consumedLines=offset, totalLines=len(lines))

    if not stream:
        # One entry from the whole text, however many lines it runs to.
        lines, window_size = ["\n".join(lines)], 1

    while offset < len(lines):
        if limit and len(words) >= limit:
            break
        blanks = leading_blanks(lines[offset:]) if stream else 0
        if blanks:
            record({}, blanks)
            continue
        if stream and not complete and offset + window_size > len(lines):
            # The rest may be the front of an entry the next submission holds the end of.
            break
        window = lines[offset:offset + window_size]
        step.gate()
        try:
            proposal = propose(context.settings, context.owner, {
                **request, "text": "\n".join(window), "mode": "stream" if stream else "single",
            })
        except ApiError as refusal:
            if refusal.code != "unreadable_input":
                raise
            skipped = logical_block(window) if stream else len(window)
            record({"outcome": "failed", "error": refusal.code, "message": refusal.message,
                    "text": window[0][:120], "lines": skipped}, skipped)
            continue

        resolution = proposal["resolution"]
        consumed = min(max(1, int(resolution.get("consumedLines") or 1)), len(window))
        outcome: dict[str, Any] = {"headword": resolution["headword"], "lines": consumed}
        if proposal["duplicates"]:
            outcome.update(outcome="duplicate",
                           existing=[item["headword"] for item in proposal["duplicates"]])
        else:
            saved = save_article(
                context.owner, DEVICE, proposal["draft"], status="inbox",
                vocabulary=proposal["vocabularyId"],
                enqueue=graph.Enqueue("ingest", parent=context.id),
            )
            outcome.update(outcome="saved", lexemeId=saved["lexemeId"],
                           headword=proposal["draft"]["headword"])
        record(outcome, consumed)
    return None


def capture(context: JobContext) -> None:
    _check_configuration(context.owner, context.input)
    context.step("capture", lambda step: walk(context, step), lane="text")


register(Kind("capture", ("capture",), capture))
