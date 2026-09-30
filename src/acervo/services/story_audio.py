"""Acervo's binding to story narration: a part in, one recording and its row out.

The other half of the split `acervo.stories.narrate` makes, and the sibling of `services/stories.py`
(the pictures) and `services/pronunciations.py` (a word). This is where it is decided *whose* voice
reads it, and it reuses what those two already answer: the chain a pair is chosen from, the way a
model's refusal is spoken, and the file-then-row write.

**A story is read in one voice, but the pin is a preference and not a cage.** The first part to be
recorded walks the owner's order, and whichever (provider, model, voice) answers is asked for every
later passage and part. If that pair then refuses — a daily quota is the case this exists for — the
next pair in the order records the rest instead. A story that changes voice between parts is worse
than one read throughout in a single voice and far better than one that stops after part one, which
is what insisting cost: the pinned pair was the free row whose allowance had run out, the chain of one
had nothing to fall through to, and three parts stayed silent for a day. **Within a part the pin never
moves**, so a paragraph is never read by two voices. The pin is read back off the graph — the first
part already recorded — and never remembered, which is what lets a retry, a route and a job agree
without coordinating.

**A directed story is read by whoever reads the expressive order**, which is only voices that take a
direction (`pronunciations.readers`) — the rule every spoken thing follows, not one of the story's
own. The passages exist to carry a direction, so **when no directed voice can be reached the part is
read whole, in one call, with no passages**: a plain reading of the whole paragraph rather than an
expensive one that is plain anyway. If the directed voices run out partway through a part, the
passages still to record are read by the plain order one at a time; they keep their breaks, and carry
no direction.

**A part is one file per passage, and never one joined file.** A directed voice is asked for one
passage at a time, each with its own direction (`stories/narrate.py` decides where they break), and
each recording is stored as it came. The alternative was tried: join them, remember where each one
starts, and seek. It does not work, because **a browser seeks a compressed stream to a page boundary**
— one second, in the Ogg libsndfile writes — so a passage started after its first words or after the
end of the one before it, unpredictably, and the element reports the time that was *asked for* rather
than the time it gave, so there is nothing to correct against. A file that begins where the passage
begins needs no seek and cannot be wrong. A clear voice records one passage covering the whole part,
so the shape is the same either way and the reader simply has nothing to tap.

Every operation is read (transaction) → calls (**no** transaction, tens of seconds of them) → write
(transaction), for `services/stories.py`'s reason.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Callable

from acervo.domain.ids import now_instant
from acervo.errors import ApiError
from acervo.models import journal, load_catalogue
from acervo.models.call import audio_mime
from acervo.models.errors import ChainExhausted, ProviderError
from acervo.pronunciation import encode, speak as speaking, takes as take_store
from acervo.repository import graph, pronunciation_settings
from acervo.services import pronunciations, stories
from acervo.services.models import refusal
from acervo.settings import Settings
from acervo.stories import narrate

NARRATE_TEMPLATE = "acervo_story_narrate"
# What tells the voice how to read a passage. Not the sentence template a word's example uses
# ("in the moment", "keep a natural pace"): this is a narrator, and the direction is a whole sentence.
SPEAK_TEMPLATE = "acervo_pronounce_story"

# The two reasons a *model's answer* is refused for being what it is rather than for the weather. A
# segmentation that fails only this way is not worth waiting for — the part is read whole instead.
UNUSABLE = frozenset({"unusable", "empty"})

# What is worth stepping over a pinned voice for: a condition that passes on its own. Written out
# here rather than imported from `work/retry.py`, because `services/` may not know jobs exist
# (`test_layering.py`) — the same three codes, decided for the same reason, in the layer that may
# say them.
PASSING = frozenset({"llm_rate_limited", "llm_unavailable", "llm_unreachable"})

Pin = tuple[str, str, "str | None"]


def narrate_story(
    settings: Settings, owner: str, device: str, story_id: str,
    gate: Callable[[], None] | None = None, progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Record the parts that have no recording yet.

    **What is missing is re-derived here rather than passed in**, for `stories.draw_pictures`'s
    reason: a run that lost its last part to a rate limit records one part and not four. `progress`
    counts over every part, so a retry carries on from what is there and the figure never runs
    backwards.
    """
    stories._story(owner, story_id)
    parts = stories._parts(owner, story_id)
    pending = [row for row in parts if not row.get("audioSegments")]
    done = len(parts) - len(pending)
    if progress is not None:
        progress(done, len(parts))
    for row in pending:
        if gate is not None:
            gate()
        narrate_part(settings, owner, device, story_id, row["id"], gate=gate)
        done += 1
        if progress is not None:
            progress(done, len(parts))
    return {"recorded": len(pending), "parts": len(parts)}


def narrate_part(
    settings: Settings, owner: str, device: str, story_id: str, part_id: str,
    gate: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Record one part and answer with its row. The one pipeline for the job and for the route."""
    started = time.monotonic()
    story = stories._story(owner, story_id)
    parts = stories._parts(owner, story_id)
    part = next((row for row in parts if row["id"] == part_id), None)
    if part is None:
        raise ApiError(404, "not_found", "That part is not in this story.")
    language = story["language"]

    preferences = pronunciation_settings.settings(owner)
    order = preferences.order_for("stories")
    reading, voices = _readers(settings, owner, language, order)

    segments = _segments(settings, owner, part["text"], language, reading)
    pin = _pin(parts, language)
    recordings, pin = _record(settings, owner, segments, language, order, reading, preferences, pin,
                              voices, gate)

    row = _place_and_store(settings, owner, device, story_id, part_id, segments, recordings, pin)
    journal.outcome(
        "story-audio", False, story=story_id, part=part_id, order=order, passages=len(segments),
        directed=sum(1 for _data, said in recordings if said),
        pair=f"{pin[0]}:{pin[1]}" if pin else None, voice=pin[2] if pin else None,
        bytes=sum(len(one.get("audioRef") or "") for one in (row.get("audioSegments") or [])) and
        sum(len(data) for data, _said in recordings),
        seconds=time.monotonic() - started,
    )
    return row


def _record(settings: Settings, owner: str, segments, language: str, order: str, reading: str,
            preferences, pin: Pin | None, voices, gate) -> tuple[list[tuple[bytes, str]], Pin | None]:
    """Say every passage, in one voice. The pair that answers the first is asked for the rest.

    **A passage already recorded is not recorded again.** A part is written only once every one of
    its passages exists, so a part that ran out of allowance halfway used to throw away the passages
    it had already paid for and buy them again on the next try — on a tier of ten calls a day, that
    is the difference between finishing a story and never finishing one. The masters go in the same
    content-addressed store a loop take uses, under the same key, so a retry costs only what is
    genuinely missing.
    """
    cache = Path(settings.takes_path)
    recordings: list[tuple[bytes, str]] = []
    for segment in segments:
        if gate is not None:
            gate()
        text = segment.text.strip()
        style = None
        if reading == "expressive" and segment.direction:
            style = speaking.direction(
                stories._template(settings, SPEAK_TEMPLATE), segment.direction, language)
        # A direction is recorded on the row only where one was really sent. A passage found in the
        # cache was keyed on what was sent; a fresh one says so on its answer.
        kept = _remembered(cache, text, language, style, pin, voices)
        if kept is not None:
            data, pin = kept
            recordings.append((data, segment.direction if style else ""))
            continue
        spoken = _say(settings, owner, text, language, order, style, preferences, pin, voices)
        answered = spoken.result.answer
        pin = (answered.provider_id, answered.model, spoken.result.voice)
        master, mime = encode.master(spoken.result.data, spoken.result.mime)
        take_store.store(cache, _take_key(text, language, spoken.direction, pin), master, mime)
        recordings.append((spoken.result.data, segment.direction if spoken.direction else ""))
    return recordings, pin


def _take_key(text: str, language: str, direction: str | None, pin: Pin) -> str:
    return take_store.key(
        text=text, language=language, direction=direction, take=0,
        provider=pin[0], model=pin[1], voice=pin[2],
    )


def _remembered(cache: Path, text: str, language: str, style: str | None, pin: Pin | None,
                candidates) -> tuple[bytes, Pin] | None:
    """This passage, if it has already been paid for, and the voice it was paid for in.

    The story's own pair is asked for first. Failing that, every pair the order offers is tried, the
    way `pronunciations.take` probes its cache: a passage recorded yesterday by a pair that has since
    fallen out of favour is the same words in the same voice, and paying for it again on a tier of
    ten calls a day is the thing this exists to avoid. A hit becomes the pin, so the rest of the part
    is read by whoever read this.
    """
    wanted: list[Pin] = [pin] if pin else []
    for candidate in candidates:
        voice = next(iter(candidate.row.voices_for(candidate.model, language)), None)
        wanted.append((candidate.row.id, candidate.model, voice))
    for pair in wanted:
        found = take_store.find(cache, _take_key(text, language, style, pair))
        if found:
            return found[0], pair
    return None


def _say(settings: Settings, owner: str, text: str, language: str, order: str, style: str | None,
         preferences, pin: Pin | None, voices) -> speaking.Spoken:
    """One passage, in the story's own voice where that voice will still answer.

    A pinned pair that refuses for a reason that passes — a quota, a busy provider, a dropped
    connection — is stepped over rather than waited out, and the rest of the order answers instead.
    Anything else is the deployment's own mistake and is raised, because falling through a rejected
    credential would only spend somebody else's allowance on it.
    """
    if pin is not None and any(pin[:2] == one.named for one in voices):
        try:
            return pronunciations._speak(
                settings, owner, text, language, order, style, speaking.CALLERS["stories"],
                lambda reason: None, preferences=preferences, pinned=pin,
            )
        except ApiError as refused:
            if refused.code not in PASSING:
                raise
            journal.outcome("story-audio", True, result="voice_changed", reason=refused.code,
                            pair=f"{pin[0]}:{pin[1]}")
    return pronunciations._speak(
        settings, owner, text, language, order, style, speaking.CALLERS["stories"],
        lambda reason: None, preferences=preferences,
    )


def _readers(settings: Settings, owner: str, language: str, order: str):
    """The order that reads this story and its voices, in the owner's order, by the rule
    `pronunciations.readers` states. A stored order the catalogue no longer honours reads as no
    voices here, and `_speak` then says why in the refusal it raises."""
    try:
        reading, chosen = pronunciations.readers(settings, owner, order, language)
        return reading, speaking.speakers(chosen, load_catalogue(), language)
    except ProviderError:
        return order, ()


def _pin(parts: list[dict[str, Any]], language: str) -> Pin | None:
    """The voice this story is already being read in: the first recorded part's, if it can still be
    asked for. A pair that has since left the catalogue, lost its credential or stopped speaking the
    language is not one to insist on — a story then starts again with whatever answers first."""
    for part in sorted(parts, key=lambda row: row.get("position", 0)):
        if part.get("audioSegments") and part.get("audioProviderId") and part.get("audioModelId"):
            pair = (part["audioProviderId"], part["audioModelId"])
            try:
                usable = speaking.speakers([pair], load_catalogue(), language)
            except ProviderError:
                usable = ()
            return (*pair, part.get("audioVoice") or None) if usable else None
    return None


def _segments(settings: Settings, owner: str, text: str, language: str,
              reading: str) -> tuple[narrate.Segment, ...]:
    """What is said, in order, and how each is directed. Joined, always exactly `text`.

    One passage and no text call at all unless a direction can actually be sent: the clear voice reads
    a part in one go by design, and a directed order with no direction-capable voice within reach is
    the same thing in practice. Asking a model where to cut a part nobody can read expressively is a
    call spent on nothing.
    """
    if reading != "expressive":
        return narrate.chunks(text)
    candidates = stories._candidates(settings, owner, "text")
    stories._require(candidates, settings, owner, "text")
    narrator = narrate.Narrator(
        load_catalogue(), candidates, stories._template(settings, NARRATE_TEMPLATE))
    try:
        tiled, usage = narrator.segment(
            narrate.build_request(language_name=speaking.language_name(language), text=text))
    except ChainExhausted as exhausted:
        if set(exhausted.reasons) <= UNUSABLE:
            # Nothing was wrong with the weather: every model was asked and none could do it. The
            # part is still worth hearing, so it is read whole, in the voice's own manner.
            journal.outcome("story-narrate", True, result="unusable", reasons=",".join(exhausted.reasons))
            return narrate.chunks(text)
        raise refusal(exhausted, "text") from None
    except ProviderError as error:
        raise refusal(error, "text") from None
    journal.outcome(
        "story-narrate", False, passages=len(tiled.segments), dropped=tiled.dropped, filled=tiled.filled,
        model=usage["model"], seconds=usage["seconds"],
    )
    return tiled.segments


def _place_and_store(
    settings: Settings, owner: str, device: str, story_id: str, part_id: str,
    segments: tuple[narrate.Segment, ...], recordings: list[tuple[bytes, str]], pin: Pin | None,
) -> dict[str, Any]:
    """Write every passage's file, then the row, then remove the files the row used to name.

    The same order `services/pronunciations._store` writes a clip in and for the same reason: a
    device that cached a passage by its reference simply misses the new one, and nothing is unlinked
    until the row naming its successor has landed.
    """
    media = Path(settings.media_path)
    written: list[dict[str, Any]] = []
    for index, (segment, (data, said)) in enumerate(zip(segments, recordings)):
        try:
            compact, mime = encode.compact(data, audio_mime(data))
        except encode.CannotEncode as unwritable:
            _discard_all(media, written, keep=())
            raise ApiError(500, "audio_unencodable",
                           f"That recording could not be stored: {unwritable}") from None
        if len(compact) > pronunciations.CLIP_LIMIT:
            _discard_all(media, written, keep=())
            raise ApiError(400, "invalid_input", "That recording is too large to keep.")
        reference = (f"stories/{story_id}/{part_id}-{index:02d}"
                     f"-{hashlib.sha256(compact).hexdigest()[:8]}.{speaking.extension_for(mime)}")
        stories._place(media, reference, compact)
        written.append({
            "text": segment.text, "direction": said, "audioRef": reference, "audioMime": mime,
            "durationSeconds": _seconds(compact),
        })

    # Read again *after* the calls, which took a while: the row this replaces may have moved — a
    # picture landed, or the other of the job and the route finished first — and a write states the
    # revision it was made from.
    fresh = graph.owned_records(owner, "storyParts", [part_id]).get(part_id)
    if fresh is None or fresh.get("deleted"):
        # The story was deleted while this was being recorded; its files go with it.
        _discard_all(media, written, keep=())
        raise ApiError(404, "not_found", "That part is not in this story any more.")
    previous = fresh.get("audioSegments") or []
    at = now_instant()
    try:
        graph.merge_graph(owner, device, {"storyParts": [{
            **fresh, "audioProviderId": pin[0] if pin else "", "audioModelId": pin[1] if pin else "",
            "audioVoice": (pin[2] or "") if pin else "", "audioSegments": written,
            "editedAt": at, "editedBy": device,
        }]}, enqueue=None)
    except Exception:
        _discard_all(media, written, keep=[one["audioRef"] for one in previous])
        raise
    _discard_all(media, previous, keep=[one["audioRef"] for one in written])
    return graph.owned_records(owner, "storyParts", [part_id])[part_id]


def _discard_all(media: Path, passages, keep) -> None:
    kept = set(keep)
    for one in passages:
        reference = one.get("audioRef") if isinstance(one, dict) else None
        if reference and reference not in kept:
            media.joinpath(reference).unlink(missing_ok=True)


def _seconds(data: bytes) -> float:
    """How long a passage lasts, so the reader can draw where it is without decoding it first."""
    import io

    try:
        import soundfile

        with soundfile.SoundFile(io.BytesIO(data)) as reading:
            return round(len(reading) / reading.samplerate, 3)
    except Exception:  # noqa: BLE001 — a length nobody could read is a length nobody needs
        return 0.0
