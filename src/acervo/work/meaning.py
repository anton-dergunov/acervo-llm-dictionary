"""`map.name`: a model names the regions of a map that has just been drawn.

A job because it is a model call, and a map must never wait on one: the map is already on screen with
the words nearest each region's centre, and the names replace them when this finishes. The subject is
the vocabulary, so a second drawing before the first is named queues nothing new — and a job whose map
has since been redrawn finds it stale and does nothing.
"""

from __future__ import annotations

from acervo.errors import ApiError
from acervo.services import meaning
from acervo.work import retry
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Step


def name(context: JobContext, step: Step) -> str | None:
    step.gate()
    wanted = context.input.get("fingerprint") or ""
    try:
        outcome = meaning.name_regions(context.settings, context.owner, context.subject_id, wanted)
    except ApiError as error:
        # A rest is the runner's to take; a refusal for good leaves the map with its central words,
        # and says so, so a device stops waiting for names that are not coming.
        if not retry.is_transient(error.code):
            meaning.give_up_naming(context.settings, context.owner, context.subject_id, wanted)
        raise
    step.note(outcome=outcome)
    return "skipped" if outcome != "named" else None


register(Kind("map.name", ("name",),
              lambda context: context.step("name", lambda step: name(context, step), lane="text")))
