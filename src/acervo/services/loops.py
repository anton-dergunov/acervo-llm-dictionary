"""Acervo's binding to the loop generator: words and a scope in, a track on disk and two rows out.

The other half of the split `acervo.loops` makes, and the same split `services/clips.py` makes
against `acervo.clips`. That module knows the generator's wire shape; this one knows whose words
they are, which order speaks them, where the track goes and what Acervo's API calls a failure.

**A loop is written by the server, file and rows together**, for the reason a picture and a clip are:
nobody else holds both. The file lands first, under a name carrying a digest of its bytes, and the
rows second through `graph.merge_graph` — the same write every phone makes.

**Its state is derived, and this is where that pays.** `create` writes the `loops` row with no
`audioRef` and its `loopItems` with the words but no times; the render fills both in. So a loop whose
job failed to queue, or failed outright, simply shows as never rendered and Try again queues another
— there is no status column to get out of step with what actually happened.

Every operation is read (transaction) → render (**no** transaction, minutes of it) → write
(transaction). A repository function is a transaction and owns its own session; a four-minute render
inside one would block every other request for as long as it ran.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from typing import Any

from acervo.domain.ids import is_record_id, new_record_id, now_instant
from acervo.errors import ApiError
from acervo.loops.client import Item, Loop, LoopError, LoopService, Operation
from acervo.repository import accounts, graph, loop_scripts, pronunciation_settings
from acervo.settings import Settings
from acervo.tokens import mint_render, resolve_secret

# A loop is a handful of words, not a playlist. The generator has its own bound; this is Acervo's,
# and it is about what makes a track worth putting on rather than what the engine can survive.
MIN_WORDS = 1
MAX_WORDS = 40

# **Acervo mints the seed, rather than letting the generator mint its own.** Left to itself it uses
# `secrets.randbits(64)`, and a 64-bit integer does not survive the journey: JSON numbers are
# doubles in most readers, so anything above 2^53 loses precision on the way into the browser, and
# SQLite's INTEGER is signed. The first real render came back with one and the whole track was
# thrown away by the graph's range check — after four minutes of work, over a number.
#
# Minting it here fixes more than the range. The seed becomes a fact about the loop from the moment
# it is asked for, so Try again reproduces the same bed rather than a different one, and the value
# stored is provably the value that produced the track: the generator echoes back what it is given.
SEED_LIMIT = 2 ** 31
# What a seed may be when it is given rather than minted — a favourite's, which came from a loop and
# may have been minted by the generator itself before Acervo sent one. The graph's bound.
SEED_MAX = 2 ** 53 - 1

TRACK_LIMIT = 64 * 1024 * 1024

# Without the sample pack, fifteen of the generator's sixteen bed families name instruments that are
# loaded from its catalogue, so a render dies on `No samples cached for …` — how far it gets depends
# on which voices the seed happens to draw. §2.2 once said a pack-less server warns rather than
# refuses; that was written believing the render falls back to the synthesised palette, and it does
# not. Refusing in one second beats failing in four minutes, and this sentence says what to do.
NO_SAMPLES = (
    "This server has no sample pack, so a loop cannot be made. "
    "Install it once with ./deploy.sh --install-samples."
)

LOOP_REFUSALS: dict[str, tuple[int, str, str]] = {
    "unreachable": (502, "loops_unreachable", "The loop generator could not be reached, so nothing was made."),
    "busy": (503, "loops_busy", "The loop generator is busy; try again in a moment."),
    "refused": (502, "loops_failed", "The loop generator refused the request, so nothing was made."),
    "no_track": (502, "loops_failed", "The loop generator finished but produced no track."),
}


def configured(settings: Settings) -> bool:
    return bool(settings.lexibeat_url.strip())


def service(settings: Settings) -> LoopService:
    if not configured(settings):
        raise ApiError(
            503, "loops_unconfigured",
            "This Acervo server has no loop generator configured, so it cannot make loops.",
        )
    return LoopService(settings.lexibeat_url)


def refusal(error: LoopError) -> ApiError:
    """Acervo's wire vocabulary, **and** whatever the generator said.

    The code is ours because the interface branches on it; the sentence is largely theirs because
    only they know what went wrong. Keeping just the constant is how "No samples cached for
    'salamander'" became "The loop generator refused the request, so nothing was made." — a message
    that named nothing and left the owner with a four-minute failure and no next step.
    """
    status, code, message = LOOP_REFUSALS.get(error.code, LOOP_REFUSALS["refused"])
    said = (error.message or "").strip()
    return ApiError(status, code, f"{message} {said}"[:500].strip() if said else message)


def schema(settings: Settings, owner: str | None = None) -> dict[str, Any]:
    """What the generator can be asked for, for the dialog. Its catalogues, never copied here —
    plus the two things only Acervo knows: whether a writing model is set up, and whether the voice
    the owner chose for loops can mix languages in one line. A format that needs either says so in
    the dialog before it is asked for, instead of falling back without a word."""
    try:
        found = service(settings).schema()
    except LoopError as error:
        raise refusal(error) from None
    return {
        "apiVersion": found.api_version,
        "engineVersion": found.engine_version,
        # False means the pinned sample bundle is not installed, or not all of it: `create` refuses
        # with `loops_no_samples` rather than render beds from whatever part of it is there.
        "productionBundle": found.production_bundle,
        # Each kind of loop, with the generator's own label and sentence, the switches it offers,
        # what it requires and what it falls back to. Classic first when it is there: it needs
        # nothing and is the default.
        "formats": [
            {"id": one.id, "label": one.label, "description": one.description,
             "switches": {name: {"label": switch.label, "default": switch.default,
                                 **({"choices": list(switch.choices)} if switch.choices else {})}
                          for name, switch in one.switches.items()},
             "requires": list(one.requires), "fallback": one.fallback}
            for one in sorted(found.formats, key=lambda one: one.id != "classic")
        ],
        "writerAvailable": _writer_available(settings, owner),
        "mixesLanguages": owner is not None and delivery(owner) != "plain",
        # Each with the generator's own label and sentence, so the dialog can say what a kind of
        # music *is*. "Surprise me" is the dialog's, and not one of these.
        "families": [{"id": one.id, "label": one.label, "description": one.description}
                     for one in found.families],
        "maxItems": min(found.max_items or MAX_WORDS, MAX_WORDS),
    }


def _writer_available(settings: Settings, owner: str | None) -> bool:
    from acervo.services.models import chain_readout

    return bool(chain_readout(settings, owner, "text").get("available"))


def _offered(settings: Settings, family: str, format_id: str | None = None,
             switches: dict[str, Any] | None = None) -> None:
    """Refuse before anything is written: no samples, a family or format the generator does not
    have, or a switch its format does not offer."""
    try:
        found = service(settings).schema()
    except LoopError as error:
        raise refusal(error) from None
    if not found.production_bundle:
        raise ApiError(409, "loops_no_samples", NO_SAMPLES)
    if family and family not in {one.id for one in found.families}:
        raise ApiError(400, "invalid_input", f"The generator has no “{family}” music.")
    if format_id is None:
        return
    chosen = next((one for one in found.formats if one.id == format_id), None)
    if chosen is None:
        raise ApiError(400, "invalid_input", f"The generator makes no “{format_id}” loop.")
    for name, value in (switches or {}).items():
        switch = chosen.switches.get(name)
        if switch is None:
            raise ApiError(400, "invalid_input", f"A “{chosen.label}” loop has no “{name}” choice.")
        if not switch.accepts(value):
            offered = ", ".join(switch.choices) if switch.choices else "on or off"
            raise ApiError(400, "invalid_input", f"“{switch.label}” is {offered}.")


def _seed(value: Any) -> int:
    """A seed a caller supplied — a favourite's — held to the bound the graph stores."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= SEED_MAX:
        raise ApiError(400, "invalid_input", "A loop's seed is a whole number the browser can hold.")
    return value


# ── making one ──────────────────────────────────────────────────────────────


def create(settings: Settings, owner: str, device: str, body: dict[str, Any]) -> dict[str, Any]:
    """Write the loop and its words. Rendering is the job's, and it has not happened yet.

    The route takes **ids**, never a query: the interface sampled them from the scope on screen and
    the server does not re-derive that scope. Which also makes choosing words by hand the same route
    with a different list, and therefore no server change at all.
    """
    language = str(body.get("language") or "").strip()
    ids = body.get("lexemeIds")
    if not isinstance(ids, list) or not all(isinstance(one, str) for one in ids):
        raise ApiError(400, "invalid_input", "A loop is made from a list of word ids.")
    wanted = [one for one in ids if is_record_id(one)]
    if len(wanted) != len(ids) or not MIN_WORDS <= len(wanted) <= MAX_WORDS:
        raise ApiError(400, "invalid_input", f"A loop takes between {MIN_WORDS} and {MAX_WORDS} words.")
    if len(set(wanted)) != len(wanted):
        raise ApiError(400, "invalid_input", "A loop cannot teach the same word twice.")

    # Asked before anything is written, so a server without its samples refuses in a second rather
    # than writing rows, queueing a job and failing minutes later with the generator's own wording
    # about a missing `salamander`. One extra call on an operation that already takes minutes.
    family = str(body.get("family") or "").strip()
    format_id = str(body.get("format") or "classic").strip()
    switches = body.get("switches") or {}
    if not isinstance(switches, dict):
        raise ApiError(400, "invalid_input", "A loop's choices are a set of named values.")
    _offered(settings, family, format_id, switches)
    # A favourite is a family *and* a seed, and only the pair replays it: a seed alone would be
    # read with `auto`, which may pick a different family for it.
    if body.get("seed") is not None and not family:
        raise ApiError(400, "invalid_input", "A loop's seed is given only with its family.")
    seed = _seed(body["seed"]) if body.get("seed") is not None else secrets.randbelow(SEED_LIMIT)

    held = graph.owned_records(owner, "lexemes", wanted)
    items: list[dict[str, Any]] = []
    for identifier in wanted:
        lexeme = held.get(identifier)
        if lexeme is None or lexeme.get("deleted"):
            raise ApiError(404, "not_found", "One of those words is not in your vocabulary.")
        if language and lexeme.get("language") != language:
            raise ApiError(400, "invalid_input", "Every word in a loop is in one language.")
        language = language or str(lexeme.get("language") or "")
        gloss = (lexeme.get("primaryGloss") or "").strip()
        if not gloss:
            # Refused **by name** rather than silently dropped from the track: a loop of eleven words
            # where twelve were asked for, with nothing saying which went missing, is worse than a
            # refusal. Nothing backfills `primaryGloss`; the word is simply not eligible.
            raise ApiError(
                422, "no_primary_gloss",
                f"“{lexeme.get('headword')}” has no single term to speak, so it cannot be in a loop.",
            )
        items.append({"lexeme": lexeme, "gloss": gloss})

    loop_id = new_record_id()
    at = now_instant()
    stamp = {"ownerId": owner, "deleted": False, "createdAt": at, "editedAt": at,
             "editedBy": device, "revision": 0}
    changes = {
        "loops": [{
            "id": loop_id, "language": language,
            # Everything the render decides is empty until it has. An absent `audioRef` is the whole
            # of what "not made yet" means.
            "styleId": None, "seed": seed, "engineVersion": None,
            "bedFingerprint": None,
            "format": format_id, "switches": switches, "fallbackFrom": None,
            "audioRef": None, "audioMime": None, "durationSeconds": None,
            "position": graph.next_loop_position(owner, language),
            **stamp,
        }],
        "loopItems": [{
            "id": new_record_id(), "loopId": loop_id, "lexemeId": entry["lexeme"]["id"],
            "position": index,
            # What will be said, and what the render is told to say — the same strings, so the
            # caption is truthful from the moment the loop exists rather than only afterwards.
            "sourceText": str(entry["lexeme"].get("headword") or ""),
            "targetText": entry["gloss"],
            "emotion": (entry["lexeme"].get("emotion") or "").strip() or None,
            # Filled in by the render. Zero is not "the start of the track": it is "not timed yet",
            # and the loop's own empty `audioRef` is what says so.
            "startSeconds": 0.0, "sourceRevealSeconds": None,
            "targetRevealSeconds": None, "endSeconds": 0.0,
            **stamp,
        } for index, entry in enumerate(items)],
    }
    graph.merge_graph(owner, device, changes, enqueue=None)
    return graph.owned_records(owner, "loops", [loop_id])[loop_id]


# ── rendering it ────────────────────────────────────────────────────────────


def music(settings: Settings, owner: str, loop_id: str, body: dict[str, Any]) -> dict[str, str]:
    """What a change of music asks the render for: a family and a seed, as the job's input.

    **The row is not touched.** Its `styleId` and `seed` go on describing the track it holds until a
    new track lands, when `store` writes both together; writing the seed now would leave a loop
    whose numbers name music it does not have for as long as the render took — or for good, if it
    failed. The request therefore travels on the job, exactly as the family already did.

    An omitted family is the loop's own, so "new music in this style" is this call with nothing
    in it; an omitted seed is a new one. A favourite supplies both.
    """
    loop = graph.owned_records(owner, "loops", [loop_id]).get(loop_id)
    if loop is None or loop.get("deleted"):
        raise ApiError(404, "not_found", "That loop is not in your vocabulary.")
    family = str(body.get("family") or loop.get("styleId") or "").strip()
    _offered(settings, family)
    seed = _seed(body["seed"]) if body.get("seed") is not None else secrets.randbelow(SEED_LIMIT)
    return {**({"family": family} if family else {}), "seed": str(seed)}


def render_request(settings: Settings, owner: str, loop_id: str,
                   seed: int | None = None) -> dict[str, Any]:
    """Everything one render needs, read in one go before any of it is sent.

    `seed` is a change of music's, carried on the job; otherwise the loop's own.
    """
    loop = graph.owned_records(owner, "loops", [loop_id]).get(loop_id)
    if loop is None or loop.get("deleted"):
        raise ApiError(404, "not_found", "That loop is not in your vocabulary.")
    rows = sorted(
        (row for row in graph.loop_items(owner, loop_id) if not row.get("deleted")),
        key=lambda row: (row.get("position", 0), row.get("id", "")),
    )
    if not rows:
        raise ApiError(422, "empty_loop", "That loop has no words left in it.")

    vocabulary = next(
        (one for one in graph.owner_vocabularies(owner) if one["language"] == loop["language"]), None
    )
    gloss_language = (vocabulary or {}).get("glossLangs") or ["en"]
    account = accounts.by_id(owner)
    if account is None:
        raise ApiError(404, "not_found", "That account no longer exists.")
    return {
        "loop": loop,
        "items": [Item(row["sourceText"], row["targetText"], row.get("emotion") or "") for row in rows],
        "rows": rows,
        "source_language": {"code": loop["language"], "name": _language_name(loop["language"])},
        "target_language": {"code": gloss_language[0], "name": _language_name(gloss_language[0])},
        # One render, one token, audienced to the take route and good for an hour. It is the whole of
        # what the generator is given to speak with: no provider credential reaches that container.
        "token": mint_render(resolve_secret(settings), account, loop_id),
        # Which order the owner chose for loops. The generator builds its backend around this and
        # declares what that backend can do, so it has to travel with the request rather than be
        # asked for later — see `delivery`.
        "delivery": delivery(owner),
        # The loop's own seed, so the bed is reproducible and the number that comes back is one this
        # side can store — or the one a change of music asked for. See `SEED_LIMIT` and `music`.
        "seed": int(seed if seed is not None else loop.get("seed") or 0),
        # What the loop is and the listener's choices for it, asked for again on every render.
        "format": loop.get("format") or "classic",
        "switches": dict(loop.get("switches") or {}),
        # The lines its last render said, for a format with a writer: sent back so new music keeps
        # them, with no writing call and every take in the cache. None the first time.
        "script": loop_scripts.script(owner, loop_id),
    }


def start(settings: Settings, request: dict[str, Any], **overrides: Any) -> Operation:
    loop = request["loop"]
    try:
        return service(settings).start(
            items=request["items"],
            source_language=request["source_language"],
            target_language=request["target_language"],
            token=request["token"],
            delivery=request["delivery"],
            format=request["format"],
            switches=request["switches"],
            script=request["script"],
            seed=request.get("seed"),
            **overrides,
        )
    except LoopError as error:
        raise refusal(error) from None


def follow(settings: Settings, operation_id: str) -> Operation:
    try:
        return service(settings).operation(operation_id)
    except LoopError as error:
        raise refusal(error) from None


def store(settings: Settings, owner: str, device: str, loop_id: str, rendered: Loop) -> dict[str, Any]:
    """Fetch the finished track, write the file, then the rows. Nothing is re-encoded.

    The generator wrote MP3 at 128 kbps and these are those bytes exactly: re-encoding a lossy stream
    into another lossy codec adds a second generation of artifacts to save nothing, which is the rule
    `pronunciation/encode.py` already states for a clip that arrived compressed.
    """
    request = render_request(settings, owner, loop_id)
    loop, rows = request["loop"], request["rows"]
    try:
        audio, mime = service(settings).track(rendered.audio_url)
    except LoopError as error:
        raise refusal(error) from None
    if not audio or len(audio) > TRACK_LIMIT:
        raise ApiError(502, "loops_failed", "The loop generator's track could not be stored.")

    # A digest of the bytes, so a re-render is a *new* reference and a device that cached the old one
    # simply misses. That is what lets `mediaStore.ts` be a cache with no invalidation in it.
    digest = hashlib.sha256(audio).hexdigest()[:8]
    reference = f"loops/{loop['language']}/{loop_id}-{digest}.mp3"
    destination = Path(settings.media_path) / reference
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(audio)
    os.replace(partial, destination)

    at = now_instant()
    timed = {int(row.get("index", index)): row for index, row in enumerate(rendered.items)}
    item_ids = [row["id"] for row in rows]
    if any(cue["item"] is not None and not 0 <= cue["item"] < len(item_ids)
           for cue in rendered.cues):
        raise ApiError(502, "loops_failed",
                       "The render spoke a word this loop does not have, so it was not stored.")
    stamp = {"ownerId": owner, "deleted": False, "createdAt": at, "editedAt": at,
             "editedBy": device, "revision": 0}
    stale = [row for row in graph.loop_cues(owner, loop_id) if not row.get("deleted")]
    changes = {
        "loops": [{
            **loop, "audioRef": reference, "audioMime": mime or "audio/mpeg",
            "durationSeconds": rendered.duration_seconds, "styleId": rendered.style_id or None,
            "seed": rendered.seed, "engineVersion": rendered.engine_version or None,
            "bedFingerprint": rendered.bed_fingerprint or None,
            "format": rendered.format or loop.get("format"),
            "fallbackFrom": rendered.fallback_from,
            "editedAt": at, "editedBy": device,
        }],
        "loopItems": [
            {
                **row,
                "startSeconds": float(timed.get(index, {}).get("start") or 0.0),
                "sourceRevealSeconds": timed.get(index, {}).get("source_reveal"),
                "targetRevealSeconds": timed.get(index, {}).get("target_reveal"),
                "endSeconds": float(timed.get(index, {}).get("end") or 0.0),
                "editedAt": at, "editedBy": device,
            }
            for index, row in enumerate(rows)
        ],
        # A render's lines replace the last render's whole: the old ones become tombstones in the
        # same write, so a device never holds two recordings' worth of lines for one loop.
        "loopCues": [{**row, "deleted": True, "editedAt": at, "editedBy": device}
                     for row in stale] + [
            {
                "id": new_record_id(), "loopId": loop_id, "position": position,
                "group": cue["group"], "kind": cue["kind"], "section": cue["section"],
                "loopItemId": item_ids[cue["item"]] if cue["item"] is not None else None,
                "side": cue["side"], "role": cue["role"], "language": cue["language"],
                "text": cue["text"], "take": cue["take"],
                "startSeconds": cue["start"], "endSeconds": cue["end"],
                **stamp,
            }
            for position, cue in enumerate(rendered.cues)
        ],
    }
    try:
        graph.merge_graph(owner, device, changes, enqueue=None)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    # Kept for the next render of this loop, after the rows it belongs to have landed.
    loop_scripts.keep(owner, loop_id, rendered.format or loop.get("format") or "", rendered.script)
    previous = loop.get("audioRef")
    if previous and previous != reference:
        Path(settings.media_path).joinpath(previous).unlink(missing_ok=True)
    return graph.owned_records(owner, "loops", [loop_id])[loop_id]


def remove(settings: Settings, owner: str, device: str, loop_id: str) -> dict[str, Any]:
    """Delete a loop: its row, its words, and the track itself.

    The rows are tombstones like every other deletion, written through `merge_graph` so they are
    numbered and replicated the way a client's own write would be. The **file** is why this is a
    route rather than a client-side `repository.delete`: a track is megabytes, nothing else would
    ever remove it, and the same party has to write the row and unlink the file or one of them is a
    lie. That is the shape `DELETE /images/prompts/{id}` already has, for the same reason.

    The file goes **after** the rows land, and never before: a merge that raises must not take the
    track of a loop that still exists with it. A loop that was never rendered has no track and
    simply loses its rows.
    """
    loop = graph.owned_records(owner, "loops", [loop_id]).get(loop_id)
    if loop is None or loop.get("deleted"):
        raise ApiError(404, "not_found", "That loop is not in your vocabulary.")

    at = now_instant()
    stamp = {"deleted": True, "editedAt": at, "editedBy": device}
    rows = [row for row in graph.loop_items(owner, loop_id) if not row.get("deleted")]
    lines = [row for row in graph.loop_cues(owner, loop_id) if not row.get("deleted")]
    graph.merge_graph(owner, device, {
        "loops": [{**loop, **stamp}],
        "loopItems": [{**row, **stamp} for row in rows],
        "loopCues": [{**row, **stamp} for row in lines],
    }, enqueue=None)
    loop_scripts.forget(owner, loop_id)

    reference = loop.get("audioRef")
    if reference:
        # `missing_ok`: a track already gone is not a reason to refuse a deletion that has happened.
        Path(settings.media_path).joinpath(reference).unlink(missing_ok=True)
    return graph.owned_records(owner, "loops", [loop_id])[loop_id]


# A writer's prompt is the generator's, assembled from what a format needs; a real one is a few
# thousand characters. This bounds a malformed request, not a prompt.
PROMPT_LIMIT = 60_000


def write(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, str]:
    """The lines of one render, from the owner's text chain: the generator's writer, calling home.

    The generator holds no credential, so a format that takes its lines from a writer — a radio
    lesson, a story — asks here, with its render's token, exactly as every take does. It sends a
    prompt it assembled and gets the model's text back; it reads that text itself, which is why this
    asks for text and not for JSON (`services/models.llm_text`). A chain that cannot answer is
    refused with its own sentence, which the render keeps and the job's progress shows.
    """
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ApiError(400, "invalid_input", "A writer is asked with a prompt.")
    if len(prompt) > PROMPT_LIMIT:
        raise ApiError(400, "invalid_input", "That prompt is longer than any loop needs.")
    purpose = str(body.get("purpose") or "programme").strip()[:40] or "programme"
    from acervo.services.models import llm_text

    text, answer = llm_text(settings, owner, prompt, caller=f"loop-{purpose}")
    return {"text": text, "provider": answer.provider_id, "model": answer.model}


def delivery(owner: str) -> str:
    """Which order speaks a loop, as the owner chose it, and which travels with the render.

    The generator needs it to know whether to vary the repetitions itself or leave that to the
    director notes (§2.6), and it has no way to find out on its own: it holds no settings, no
    catalogue and no credential. Choosing the clear voice is therefore worth what it says it is —
    one recording a line rather than three — rather than three identical calls.
    """
    return pronunciation_settings.settings(owner).order_for("loops")


def _language_name(code: str) -> str:
    from acervo.pronunciation.speak import language_name

    return language_name(code)
