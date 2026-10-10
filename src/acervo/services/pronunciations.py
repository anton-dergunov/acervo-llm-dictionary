"""Acervo's binding to pronunciation: the graph and settings in, a clip on disk and a row out.

The other half of the split `acervo.pronunciation` makes, exactly as `services/images.py` is for
pictures. That package knows what to say and how to ask for it; this module knows whose word it is,
which chain reads it, where the file goes and what Acervo's API calls a failure.

**A clip is written by the server, file and row together**, for the reason a picture is: nobody else
holds both. The file lands first, under a name that changes with every recording, and the row second
through `graph.merge_graph` — the same write every phone makes. So a device that cached the previous
recording by its reference simply misses the new one and fetches it, and the previous file is removed
only once the row naming its successor has landed.

Every operation is read (transaction) → model call (**no** transaction) → write (transaction).

A selection is the one thing said and not kept: it names no record, so there is no row to put it in
and nothing to make stale. It is spoken and returned, and the call log is its only trace.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from acervo.domain.ids import is_language, now_instant
from acervo.errors import ApiError
from acervo.models import ChainExhausted, ProviderError, journal, load_catalogue
from acervo.models.call import audio_mime
from acervo.models.catalogue import available
from acervo.pronunciation import encode, speak as speaking
from acervo.pronunciation.ids import pronunciation_id
from acervo.pronunciation.targets import COLLECTION, Target, current, target_in
from acervo.pronunciation import takes as take_store
from acervo.repository import graph, pronunciation_settings
from acervo.repository.pronunciation_settings import ORDERS, SWITCHES, USES
from acervo.services import media as media_files
from acervo.services.models import chain_for, refusal, speech_chain
from acervo.services.prompts import prompt_text
from acervo.settings import Settings

STYLE_PROMPT = "acervo_pronounce_style"

# A loop take is framed differently from an example, and it has to be. What arrives in `direction`
# there is not an adjective written on a record — it is the generator's whole director note for this
# repetition, pace and pitch included ("Speak warmly, as if teaching someone, but clearly, slightly
# briskly, with a slightly brighter pitch."). Dropping that into `acervo_pronounce_style`'s
# `sounding {emotion}` slot produced a sentence that was not one, and the template's own "Keep a
# natural pace" then cancelled the one clause that made a word's three takes differ. This template
# relays the note and says nothing about pace, and nothing about how many repetitions there are —
# that is the generator's business, not ours.
TAKE_PROMPT = "acervo_pronounce_take"

# Route segment → target kind. The route is addressed by the record being read.
ROUTE_KINDS = {plural: kind for kind, plural in COLLECTION.items()}

# The two orders, named here for the chains they are. The orders themselves are named for their
# *capability* — a clear even voice, and one that takes a direction — and which of them reads each of
# the three uses is the owner's answer in `pronunciation_settings.delivery`.
CHAINS = {"plain": "audioPlain", "expressive": "audioExpressive"}

# How long a pair may stay silent before the next is asked beside it. Measured on 2026-09-15 against
# Cloud TTS: WaveNet and Standard answered a word in 0.3–1.2 s, a Gemini voice a sentence in 2–3 s.
# Somebody pressed a button and is waiting, so both are set just above the healthy tail. Keyed by
# *order* rather than by use, because it is a fact about how fast that chain answers.
HEDGE = {"plain": 3.0, "expressive": 8.0}

# A take is one line of a loop. Nobody is watching it arrive — the job polls an operation — so the
# bound is on how long one line may take, not on how long a person will wait.
TAKE_LIMIT = 500
TAKES = 8

# A selection is read aloud from the page, not stored; this bounds what one press can cost.
UTTERANCE_LIMIT = 2000
CLIP_LIMIT = 4 * 1024 * 1024


# ── settings ────────────────────────────────────────────────────────────────


def settings_view(settings: Settings, owner: str) -> dict[str, Any]:
    """What the owner chose, and the voices each model in each order offers per vocabulary language.

    The voice lists travel with the settings for `images.settings_view`'s reason: the selects are
    meaningless without them, and one round trip cannot show a half-loaded screen.
    """
    catalogue = load_catalogue()
    chosen = pronunciation_settings.settings(owner)
    vocabularies = graph.owner_vocabularies(owner)
    languages = [vocabulary["language"] for vocabulary in vocabularies]
    # What a loop's guide says its lines in: each vocabulary's first gloss language, as a render
    # asks for its translations. The guide voice is chosen per one of these.
    guide_languages = list(dict.fromkeys(
        (vocabulary.get("glossLangs") or ["en"])[0] for vocabulary in vocabularies))
    offered = list(dict.fromkeys([*languages, *guide_languages]))
    orders: dict[str, list[dict[str, Any]]] = {}
    for reading in CHAINS:
        entries = []
        for candidate in _pairs(settings, owner, reading, catalogue):
            row, model = candidate
            entries.append({
                "provider": row.id,
                "providerLabel": row.label,
                "model": model,
                "available": available(row),
                "style": row.style_for(model),
                "voices": {
                    language: list(row.voices_for(model, language))
                    for language in offered if row.speaks(model, language)
                },
            })
        orders[reading] = entries
    return {**chosen, "languages": languages, "guideLanguages": guide_languages, "orders": orders}


def _pairs(settings: Settings, owner: str, order: str, catalogue) -> list[tuple[Any, str]]:
    """Every pair that may read an order, credentialed or not, so a voice can be chosen before a key
    is set. For the expressive order that is only the pairs that take a direction (`readers`)."""
    found = []
    for choice in order_of(settings, owner, order) or [
        (row.id, model) for row in catalogue.serving("audio") for model in row.models_for("audio")
    ]:
        identifier, model = (choice, None) if isinstance(choice, str) else choice
        row = catalogue.find(identifier)
        for one in ([model] if model else row.models_for("audio")):
            if order == "expressive" and row.style_for(one) != "instruction":
                continue
            found.append((row, one))
    return found


def apply_settings(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validate a submitted document, store it, and answer with the whole readout."""
    changes: dict[str, Any] = {}
    if "pregenerate" in body:
        submitted = body["pregenerate"]
        if not isinstance(submitted, dict) or any(
            name not in SWITCHES or not isinstance(value, bool) for name, value in submitted.items()
        ):
            raise ApiError(
                400, "invalid_input",
                f"Recording in advance takes true or false for {', '.join(SWITCHES)}.",
            )
        changes["pregenerate"] = submitted
    if "delivery" in body:
        submitted = body["delivery"]
        if not isinstance(submitted, dict) or any(
            use not in USES or order not in ORDERS for use, order in submitted.items()
        ):
            raise ApiError(
                400, "invalid_input",
                f"Delivery takes {' or '.join(ORDERS)} for {', '.join(USES)}.",
            )
        changes["delivery"] = submitted
    if "voices" in body:
        changes["voices"] = _voices(body["voices"])
    if "guideVoices" in body:
        changes["guide_voices"] = _voices(body["guideVoices"])
    pronunciation_settings.save(owner, **changes)
    return settings_view(settings, owner)


def _voices(submitted: Any) -> dict[str, dict[str, dict[str, str]]]:
    """A voice document held to the catalogue: every provider, model and voice must exist."""
    if not isinstance(submitted, dict):
        raise ApiError(400, "invalid_input", "Voices must be {provider: {model: {language: voice}}}.")
    catalogue = load_catalogue()
    kept: dict[str, dict[str, dict[str, str]]] = {}
    for provider_id, models in submitted.items():
        try:
            row = catalogue.find(str(provider_id))
        except KeyError:
            raise ApiError(400, "unknown_provider", f"This server has no provider called {provider_id}.") from None
        if not row.serves("audio") or not isinstance(models, dict):
            raise ApiError(400, "unsupported_kind", f"{row.label} does not speak.")
        for model, languages in models.items():
            if model not in row.models_for("audio") or not isinstance(languages, dict):
                raise ApiError(400, "unknown_model", f"{row.label} does not offer {model} for speech.")
            for language, voice in languages.items():
                if voice in (None, ""):
                    continue
                offered = row.voices_for(model, str(language))
                if not is_language(str(language)) or (offered and voice not in offered):
                    raise ApiError(400, "unknown_voice", f"{model} has no voice {voice!r} for {language}.")
                kept.setdefault(row.id, {}).setdefault(model, {})[str(language)] = str(voice)
    return kept


# ── saying a record ─────────────────────────────────────────────────────────


def pronounce(settings: Settings, owner: str, device: str, route_kind: str, target_id: str,
              again: bool = False) -> dict[str, Any]:
    """The clip for one spoken field: the stored one while it is current, otherwise a new recording.

    `again` records it anew even when the stored clip is current — "Record again" after hearing a bad
    one. The row is rewritten at its derived id, so there is still exactly one clip per field.
    """
    started = time.monotonic()
    target, records = _target(owner, route_kind, target_id)
    clip_id = pronunciation_id(target.kind, target.id)
    existing = next((row for row in records.get("pronunciations", []) if row["id"] == clip_id), None)
    caller = speaking.CALLERS[target.use]
    log = _logger(caller, target)

    if not again and current(existing, target):
        log(started, source="reused", clip=existing, result="stored")
        return existing  # type: ignore[return-value]
    source = "again" if again else ("stale" if existing and not existing.get("deleted") else "generated")

    preferences = pronunciation_settings.settings(owner)
    # Which order reads this is the owner's answer, per use. Choosing the directed order *is* asking
    # for emotion — there is no second switch, which is why turning emotion off no longer leaves the
    # expensive voice reading every sentence.
    order = preferences.order_for(target.use)
    style = None
    if target.kind == "example" and target.emotion and order == "expressive":
        style = speaking.direction(
            prompt_text(Path(settings.prompts_path), STYLE_PROMPT), target.emotion, target.language
        )
    spoken = _speak(
        settings, owner, target.text, target.language, order, style, caller,
        lambda error, **noted: log(started, source=source, result=error, failed=True, **noted),
        preferences=preferences,
    )
    result = spoken.result
    # The provider answered with a master; what is kept is Opus. An answer that was already
    # compressed passes through untouched — see `pronunciation/encode.py`.
    kept, mime = encode.compact(result.data, result.mime)
    return _store(
        settings, owner, device, target, existing, clip_id, kept, mime,
        provider_id=result.answer.provider_id, model_id=result.answer.model, voice=result.voice,
        emotion=target.emotion if spoken.direction else None,
        on_logged=lambda clip, outcome: log(
            started, source=source, clip=clip, result=outcome, failed=outcome != "stored",
            bytes=len(kept), answered=f"{result.mime}:{len(result.data)}",
            attempts=len(result.answer.attempts), passed_over=_passed(result.answer),
            warnings="; ".join(result.answer.warnings), style="yes" if spoken.direction else ("dropped" if style else "no"),
        ),
    )


def restore(settings: Settings, owner: str, device: str, route_kind: str, target_id: str,
            data: bytes, spoken: dict[str, str]) -> dict[str, Any]:
    """Put back a clip an export carried, keeping who recorded it.

    Refused when the record no longer says what the clip says: a bundle's clip of a sentence that has
    since been edited is a recording of something else, and storing it would present it as current.
    """
    started = time.monotonic()
    target, records = _target(owner, route_kind, target_id)
    log = _logger("pronounce-restore", target)
    if spoken.get("text") != target.text:
        log(started, source="restored", result="stale", failed=True)
        raise ApiError(409, "stale_clip", "That recording is of different words than the record now holds.")
    mime = audio_mime(data)
    if mime == "application/octet-stream":
        raise ApiError(400, "unreadable_audio", "That file could not be read as audio.")
    provider_id, model_id = spoken.get("providerId", "").strip(), spoken.get("modelId", "").strip()
    if not provider_id or not model_id:
        raise ApiError(400, "invalid_input", "A restored clip must name the provider and model that recorded it.")
    clip_id = pronunciation_id(target.kind, target.id)
    existing = next((row for row in records.get("pronunciations", []) if row["id"] == clip_id), None)
    return _store(
        settings, owner, device, target, existing, clip_id, data, mime,
        provider_id=provider_id[:80], model_id=model_id[:240], voice=(spoken.get("voice") or None),
        emotion=(spoken.get("emotion") or None),
        on_logged=lambda clip, outcome: log(started, source="restored", clip=clip, result=outcome,
                                            failed=outcome != "stored"),
    )


def utterance(settings: Settings, owner: str, text: str, language: str) -> tuple[bytes, str, dict[str, str]]:
    """Say a selection. Nothing is stored; the answer is the audio and who said it."""
    started = time.monotonic()
    words = (text or "").strip()
    if not words or len(words) > UTTERANCE_LIMIT:
        raise ApiError(400, "invalid_input", f"Select between 1 and {UTTERANCE_LIMIT} characters to listen to.")
    if not is_language(language or ""):
        raise ApiError(400, "invalid_input", "language must be a BCP-47 language tag.")

    def failed(error: str, **noted: Any) -> None:
        journal.outcome("pronounce-selection", True, lang=language, chars=len(words), text=words,
                        result=error, seconds=time.monotonic() - started, **noted)

    order = pronunciation_settings.settings(owner).order_for("words")
    spoken = _speak(settings, owner, words, language, order, None, "pronounce-selection", failed)
    # Compressed like a stored clip, though nothing is stored: this one is downloaded before it can
    # be heard, and a master is four times the wait on a phone for audio that lives one playback.
    result = spoken.result
    audio, mime = encode.compact(result.data, result.mime)
    journal.outcome(
        "pronounce-selection", lang=language, chars=len(words), text=words,
        pair=f"{result.answer.provider_id}:{result.answer.model}", voice=result.voice,
        bytes=len(audio), answered=f"{result.mime}:{len(result.data)}", mime=mime, result="spoken",
        seconds=time.monotonic() - started,
    )
    return audio, mime, {
        "provider": result.answer.provider_id, "model": result.answer.model, "voice": result.voice or "",
    }


def take(settings: Settings, owner: str, body: dict[str, Any]) -> tuple[bytes, str, dict[str, str]]:
    """One line of a loop, as the **master**, cached by what it is a recording of.

    Not `utterance`, and the difference is the whole point. A selection is downloaded before it can
    be heard, so it is compressed; a take is about to be time-stretched, pitch-shifted and mixed into
    a track that is itself encoded, so it wants the master and the only lossy generation in a loop is
    the final MP3.

    Not a plain-or-directed choice made by the caller, either. This reads the owner's **loop**
    delivery setting and reports whether the direction was honoured — and **a dropped direction is a
    useful answer, not a failure**. LexiBeat falls back to its own pitch and speed variation, so a
    deployment with no instruction-following voice still gets loops, with three distinguishable takes
    and no emotion. That requirement is met by this contract rather than by a branch on either side.

    A stored pronunciation is deliberately not read through. A plain headword take has the same text,
    language, model and voice as the clip the article already holds — but that clip is Opus at about
    51 kbps, compressed for a phone, and stretching it would put a second lossy generation in front
    of the master. It would save one call per word in the plain case and none in the directed case.
    """
    started = time.monotonic()
    words = str(body.get("text") or "").strip()
    language = str(body.get("language") or "")
    direction_text = (str(body.get("direction")) if body.get("direction") is not None else "").strip()
    if not words or len(words) > TAKE_LIMIT:
        raise ApiError(400, "invalid_input", f"A take is between 1 and {TAKE_LIMIT} characters.")
    if not is_language(language):
        raise ApiError(400, "invalid_input", "language must be a BCP-47 language tag.")
    try:
        index = int(body.get("take") or 0)
    except (TypeError, ValueError):
        index = -1
    if not 0 <= index < TAKES:
        raise ApiError(400, "invalid_input", f"take must be between 0 and {TAKES - 1}.")

    preferences = pronunciation_settings.settings(owner)
    # A loop's guide lines — translations, remarks, announcements — in the owner's guide voice where
    # one is chosen. The voice is in the cache key, so the two voices never share a take.
    role = str(body.get("role") or "native")
    if role not in ("native", "guide"):
        raise ApiError(400, "invalid_input", "role is native or guide.")
    if role == "guide":
        preferences = preferences.for_guide()
    order = preferences.order_for("loops")
    style = None
    if direction_text and order == "expressive":
        style = speaking.direction(
            prompt_text(Path(settings.prompts_path), TAKE_PROMPT), direction_text, language
        )

    def log(**extra: Any) -> None:
        journal.outcome(
            speaking.CALLERS["loops"], extra.pop("failed", False), lang=language, chars=len(words),
            text=words, emotion=direction_text or None, take=index, order=order,
            seconds=time.monotonic() - started, **extra,
        )

    cache = Path(settings.takes_path)
    catalogue = load_catalogue()

    def kept(reading: str, asked_style: str | None) -> tuple[bytes, str, dict[str, str]] | None:
        """The take already recorded for this line by a pair of `reading`, if there is one.

        Which pair answers is not known until it has, so every pair of the order is tried: a
        fall-through yesterday still answers today, which is most of what makes the cache worth
        having.
        """
        for row, model in _pairs(settings, owner, reading, catalogue):
            if not row.speaks(model, language):
                continue
            # Keyed on what this pair would be *sent*, by the same function the call itself uses —
            # so a pair that cannot take a direction looks the same up as it stores down, and a take
            # recorded under the provider's own default voice is found again.
            asked_voice, would_send = speaking.asked_of(row, model, language, asked_style, preferences.voice)
            found = take_store.find(cache, take_store.key(
                text=words, language=language, direction=would_send, take=index,
                provider=row.id, model=model, voice=asked_voice,
            ))
            if found is None:
                continue
            data, mime = found
            log(result="cached", pair=f"{row.id}:{model}", bytes=len(data), mime=mime)
            return data, mime, _spoken_headers(row.id, model, asked_voice, direction_text,
                                               sent=bool(would_send))
        return None

    def failed(error: str, **noted: Any) -> None:
        log(result=error, failed=True, **noted)

    if (found := kept(order, style)) is not None:
        return found
    try:
        spoken = _speak(
            settings, owner, words, language, order, style, speaking.CALLERS["loops"], failed,
            preferences=preferences, directed_only=True,
        )
    except Undirected:
        # **A take recorded without its direction is looked for only here**, once no directed voice
        # can read the line. Looked for before the directed voices were asked, it answered for ever:
        # one day without a directed voice left every line it recorded flat in each later loop that
        # used the same words, with the directed voice back and never asked.
        if (found := kept("plain", None)) is not None:
            return found
        spoken = _speak(
            settings, owner, words, language, "plain", None, speaking.CALLERS["loops"], failed,
            preferences=preferences,
        )
    result = spoken.result
    # The master, not Opus: this is the one place in Acervo that keeps audio uncompressed on purpose.
    data, mime = encode.master(result.data, result.mime)
    digest = take_store.key(
        text=words, language=language, direction=spoken.direction, take=index,
        provider=result.answer.provider_id, model=result.answer.model, voice=spoken.asked_voice,
    )
    take_store.store(cache, digest, data, mime)
    log(result="recorded", pair=f"{result.answer.provider_id}:{result.answer.model}",
        voice=result.voice, bytes=len(data), mime=mime,
        answered=f"{result.mime}:{len(result.data)}",
        style="sent" if spoken.direction else ("dropped" if style else "none"))
    return data, mime, _spoken_headers(
        result.answer.provider_id, result.answer.model, spoken.asked_voice, direction_text,
        sent=bool(spoken.direction),
    )


def _spoken_headers(provider: str, model: str, voice: str | None, direction: str, *, sent: bool) -> dict[str, str]:
    """Who said it, and whether the direction reached them.

    `voice` is the one *asked for*, which is empty when the owner chose none and the provider used
    its own default — and it is the asked-for one on both paths deliberately. A cache hit cannot know
    what answered, so reporting that on a fresh recording and this on a hit would make one header
    mean two things. Provenance of what actually spoke belongs on a clip row, which stores it, not on
    a cache entry, which has no table to store it in.

    `dropped` covers both ways a direction can fail to land: the owner chose the clear order for
    loops, or the answering voice cannot take one. The caller does not need to tell those apart —
    either way it varies the takes itself — and `none` says there was no direction to begin with.
    """
    return {
        "provider": provider,
        "model": model,
        "voice": voice or "",
        "direction": ("sent" if sent else "dropped") if direction else "none",
    }


# ── shared ──────────────────────────────────────────────────────────────────


def _target(owner: str, route_kind: str, target_id: str) -> tuple[Target, dict[str, list[dict]]]:
    kind = ROUTE_KINDS.get(route_kind)
    lexeme_id = graph.lexeme_of(owner, kind, target_id) if kind else None
    records = graph.article_records(owner, lexeme_id) if lexeme_id else {}
    target = target_in(records, kind, target_id) if kind and lexeme_id else None
    if target is None:
        # One message for "no such record", "somebody else's" and "deleted", as everywhere else.
        raise ApiError(404, "not_found", "There is nothing there to pronounce.")
    return target, records


class Undirected(Exception):
    """No voice that takes a direction could read this: none is in the order, or none answered."""


def order_of(settings: Settings, owner: str, order: str, caller: str | None = None) -> Any:
    """The owner's order for a speech chain, as far as the catalogue still offers it — the rule is
    `services.models.speech_chain`'s. Each read that steps over a pair says so in the call log, under
    `caller`; a reader with no caller, such as the settings pane's, says nothing."""
    chain_name = CHAINS[order]
    chosen, skipped = speech_chain(settings, owner, chain_name)
    for pair in skipped if caller else ():
        journal.outcome(caller, True, result="skipped", reason="retired", order=chain_name, pair=pair)
    return chosen


def readers(settings: Settings, owner: str, order: str, language: str,
            caller: str | None = None) -> tuple[str, Any]:
    """Who reads `order` in `language`: the order that actually reads, and the choices to walk.

    **The expressive order is read only by voices that take a direction.** It exists to carry one,
    and a pair that cannot — a row declaring `style: none` — records the clip as though no direction
    had been asked for, silently: that is how a whole deployment's examples, loops and stories lost
    their emotion with nothing failing and nothing logged. So the owner's expressive order is walked
    with its `none` pairs left out. The order itself is a preference and is kept as saved; only the
    walk skips them. **When no directed voice can be reached, the plain order reads instead**, and
    the caller records without a direction — the answer is still worth hearing.

    A pair the catalogue no longer offers is left out of either order (`order_of`), with `caller`
    naming whose line says so.
    """
    chosen = order_of(settings, owner, order, caller)
    if order != "expressive":
        return order, chosen
    directed = [
        candidate.named for candidate in speaking.speakers(chosen, load_catalogue(), language)
        if candidate.row.style_for(candidate.model) == "instruction"
    ]
    if directed:
        return order, directed
    return "plain", order_of(settings, owner, "plain", caller)


def _speak(settings: Settings, owner: str, text: str, language: str, order: str,
           style: str | None, caller: str, on_failure,
           preferences=None, pinned: tuple[str, str, str | None] | None = None,
           directed_only: bool = False) -> speaking.Spoken:
    """Say `text` in `order`, by the rule `readers` states. `Spoken.direction` says what was sent.

    `pinned` is `(provider, model, voice)`: ask exactly that pair and that voice, and never another.
    For a caller that has to hear one voice throughout a passage — a story keeps the voice that read
    its first part. The chain is then a chain of one, so there is nothing to hedge onto, and a caller
    that would rather change voice than stall asks again **without** the pin when it refuses; that
    judgement belongs to the caller and not here.

    Directed voices that are all out of reach — every one refused for a quota, a busy provider or an
    unusable answer — are the same case as none being configured: the plain order is walked once
    more, without the direction. A rejected credential is not, and is raised.

    `directed_only` stops at that hand-over and raises `Undirected` in its place, for a caller with
    something of its own to try before the plain order reads — a loop's take, which looks for the
    line already recorded plainly. It changes nothing when `order` is the plain one.
    """
    preferences = preferences or pronunciation_settings.settings(owner)
    chain_name = CHAINS[order]
    try:
        if pinned is not None:
            provider_id, model, voice_name = pinned
            return speaking.speak(
                text, language,
                chosen=[(provider_id, model)], catalogue=load_catalogue(),
                style=style, voice=lambda provider, model_id, lang: voice_name,
                caller=caller, hedge_after=None,
            )
        reading, chosen = readers(settings, owner, order, language, caller)
        chain_name = CHAINS[reading]
        if reading != order:
            journal.outcome(caller, False, lang=language, result="undirected", reason="no_directed_voice")
            if directed_only:
                raise Undirected
            style = None
        try:
            return speaking.speak(
                text, language, chosen=chosen, catalogue=load_catalogue(),
                style=style, voice=preferences.voice, caller=caller, hedge_after=HEDGE[reading],
            )
        except ChainExhausted as exhausted:
            if reading == "plain":
                raise
            journal.outcome(caller, True, lang=language, result="undirected",
                            reason=",".join(exhausted.reasons))
            if directed_only:
                raise Undirected from None
            chain_name = CHAINS["plain"]
            return speaking.speak(
                text, language, chosen=order_of(settings, owner, "plain", caller),
                catalogue=load_catalogue(), style=None, voice=preferences.voice, caller=caller,
                hedge_after=HEDGE["plain"],
            )
    except speaking.NoVoice:
        on_failure("no_model_for_language")
        raise ApiError(
            422, "no_voice_for_language",
            f"Nothing in your pronunciation order speaks {speaking.language_name(language)}. "
            "Add a model that does in Settings ▸ Providers.",
        ) from None
    except ChainExhausted as exhausted:
        error = refusal(exhausted, chain_name)
        on_failure(f"refused:{error.code}", **error.noted)
        raise error from None
    except ProviderError as failure:
        error = refusal(failure, chain_name)
        on_failure(f"refused:{error.code}", **error.noted)
        raise error from None


def _store(settings: Settings, owner: str, device: str, target: Target, existing: dict | None,
           clip_id: str, data: bytes, mime: str, *, provider_id: str, model_id: str,
           voice: str | None, emotion: str | None, on_logged) -> dict[str, Any]:
    """Write the file, then the row, then remove the file the row used to name."""
    if len(data) > CLIP_LIMIT:
        raise ApiError(400, "invalid_input", "That recording is too large to keep.")
    digest = hashlib.sha256(data).hexdigest()[:8]
    # From the stored lexeme id and the derived id — never from anything the request said.
    reference = f"audio/{target.lexeme_id}/{clip_id}-{digest}.{speaking.extension_for(mime)}"
    destination = Path(settings.media_path) / reference
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, destination)

    at = now_instant()
    row = {
        "id": clip_id,
        "lexemeId": target.lexeme_id,
        "targetKind": target.kind,
        "targetId": target.id,
        "text": target.text,
        "lang": target.language,
        "emotion": emotion,
        "audioRef": reference,
        "audioMime": mime,
        "providerId": provider_id,
        "modelId": model_id,
        "voice": voice,
        # A tombstone is revived at its stored revision: the id is derived, so this is its row.
        "deleted": False,
        "createdAt": (existing or {}).get("createdAt", at),
        "editedAt": at,
        "editedBy": device,
        "revision": (existing or {}).get("revision", 0),
    }
    try:
        graph.merge_graph(owner, device, {"pronunciations": [row]}, enqueue=None)
    except Exception:
        if reference != (existing or {}).get("audioRef"):
            media_files.remove(settings.media_path, reference, "rollback")
        on_logged(row, "write_failed")
        raise
    previous = (existing or {}).get("audioRef")
    if previous and previous != reference:
        media_files.remove(settings.media_path, previous, "replaced")
    stored = graph.pronunciation(owner, clip_id) or row
    on_logged(stored, "stored")
    return stored


def _logger(caller: str, target: Target):
    def log(started: float, *, source: str, result: str, clip: dict | None = None, failed: bool = False,
            **extra: Any) -> None:
        journal.outcome(
            caller, failed,
            target=f"{target.kind}:{target.id}", lang=target.language, chars=len(target.text),
            text=target.text, emotion=target.emotion if target.kind == "example" else None,
            source=source,
            pair=f"{clip['providerId']}:{clip['modelId']}" if clip else None,
            voice=(clip or {}).get("voice"), ref=(clip or {}).get("audioRef"),
            mime=(clip or {}).get("audioMime"), result=result,
            seconds=time.monotonic() - started, **extra,
        )

    return log


def _passed(answer) -> str | None:
    return ",".join(f"{provider}:{model}:{reason}" for provider, model, reason in answer.passed_over) or None
