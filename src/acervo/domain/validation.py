"""The rules every write is held to, whichever writer it came from.

Ported from the PocketBase record-validation hook plus the field constraints its migration declared,
which SQLite does not enforce for us: a `select` was a real storage constraint and a `max` was a real
length bound, so both are checks here.

Each rule below has a test today and each is something a reasonable re-derivation gets subtly wrong.
The comments mark the ones where that is most true.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from acervo.domain.ids import is_instant, is_language, is_record_id
from acervo.errors import RecordRefused

POS_VALUES = ("noun", "verb", "adj", "adv", "phrase", "idiom", "expression")
GENDER_VALUES = ("masculine", "feminine", "common", "neuter")
REGISTER_VALUES = ("neutral", "formal", "colloquial", "slang", "vulgar")
STATUS_VALUES = ("inbox", "active", "learned", "retired", "suppressed")
# `sign` is text met out in the world rather than read — a street sign, a menu, a label — which a
# photo is the usual way to keep.
SOURCE_KIND_VALUES = ("web", "book", "conversation", "video", "lesson", "sign", "unknown")
# Where a kept photo lives under the media root: the owner's own directory, named by a digest of the
# bytes, so the reference alone says whose it is and a second word saved from the same photo names
# the same file. `photos/{owner}/pending/` is where it waits until a save names it.
PHOTO_REF = re.compile(r"^photos/(?P<owner>[a-z0-9]{15})/(?P<digest>[0-9a-f]{16})\.jpg$")
# The most polygons a photo region may carry: a sentence of a hundred words, and then some.
PHOTO_REGION_LIMIT = 400
# A story's guidance is a note in the owner's words, not a second prompt: a few sentences at most.
GUIDANCE_LIMIT = 1000
ORIGIN_VALUES = ("attestation", "llm", "tatoeba", "subtitle", "wiktionary", "manual")
# What a pronunciation reads, and the table and field each one names.
PRONUNCIATION_TARGETS = {
    "lexeme": ("lexemes", "headword"),
    "sense": ("senses", "definition"),
    "example": ("examples", "text"),
    "attestation": ("attestations", "text"),
}

# field -> (required, maximum length). Straight from the bootstrap migration.
TEXT_RULES: dict[str, dict[str, tuple[bool, int]]] = {
    "vocabularies": {
        "language": (True, 35), "definition_lang": (True, 35), "notes_lang": (True, 35),
        "display_name": (False, 120), "flag": (False, 32),
    },
    "topics": {"name": (True, 120), "icon": (False, 120)},
    "lexemes": {
        "language": (True, 35), "headword": (True, 240), "lemma": (True, 240),
        "reading": (False, 240), "ipa": (False, 240), "dialect": (False, 35),
        "emoji": (False, 32), "short_gloss": (False, 500), "primary_gloss": (False, 240),
        "emotion": (False, 300), "clips_searched_at": (False, 24),
    },
    "senses": {
        "definition": (True, 2000), "definition_lang": (True, 35), "domain": (False, 120),
        "emoji": (False, 32),
    },
    "attestations": {
        # Not required here: an attestation may be a photo alone (below).
        "text": (False, 5000), "translation": (False, 5000), "source_title": (False, 500),
        "photo_ref": (False, 500),
    },
    "examples": {
        "text": (True, 5000), "text_lang": (True, 35), "translation": (False, 5000),
        "translation_lang": (False, 35), "model_id": (False, 240), "video_ref": (False, 500),
        "video_title": (False, 500), "video_channel": (False, 500), "clip_ref": (False, 120),
        "image_ref": (False, 500), "emotion": (False, 300),
        "note": (False, 2000), "matched_form": (False, 240),
        "matched_translation_form": (False, 240),
    },
    "image_prompts": {
        # `prompt` is optional because two legitimate rows have none: one the writer refused, which
        # is a finished outcome recorded so nothing asks again, and one holding a picture the owner
        # supplied themselves, which no brief produced.
        "prompt": (False, 10000), "style_id": (False, 120), "model_id": (False, 240),
        "prompt_version": (False, 128), "image_ref": (False, 500), "image_model_id": (False, 240),
        "failure_reason": (False, 500),
    },
    "pronunciations": {
        "target_id": (True, 15), "text": (True, 5000), "lang": (True, 35), "emotion": (False, 300),
        "audio_ref": (True, 500), "audio_mime": (True, 80), "provider_id": (True, 80),
        "model_id": (True, 240), "voice": (False, 120),
    },
    "study_states": {"system": (True, 80)},
    "loops": {
        "language": (True, 35), "style_id": (False, 120), "engine_version": (False, 64),
        "bed_fingerprint": (False, 64), "format": (True, 64), "fallback_from": (False, 64),
        "audio_ref": (False, 500), "audio_mime": (False, 80),
    },
    "loop_items": {
        "source_text": (True, 240), "target_text": (True, 240), "emotion": (False, 300),
    },
    "loop_cues": {
        "kind": (True, 32), "section": (True, 16), "side": (False, 16), "role": (True, 16),
        "language": (True, 35), "text": (True, 600),
    },
    "stories": {
        "language": (True, 35), "type_id": (False, 64), "style_id": (False, 120),
        "title": (False, 240), "title_translation": (False, 240), "emoji": (False, 16),
        "model_id": (False, 120), "guidance": (False, GUIDANCE_LIMIT),
    },
    "story_parts": {
        "heading": (False, 240), "heading_translation": (False, 240),
        # A part is prose, and these are the bounds a *story* is written to rather than arbitrary
        # ones: `prompts/acervo_story_write.md` asks for two to four sentences a part, so a value
        # near this ceiling is already a prompt that has gone wrong.
        "text": (False, 4000), "translation": (False, 4000), "image_prompt": (False, 4000),
        "image_ref": (False, 500), "image_model_id": (False, 120), "failure_reason": (False, 500),
        "audio_provider_id": (False, 120), "audio_model_id": (False, 120), "audio_voice": (False, 120),
    },
    "story_words": {"source_text": (True, 240)},
    "beds": {"style_id": (True, 120), "engine_version": (False, 64), "bed_fingerprint": (False, 64)},
}

SELECT_RULES: dict[str, dict[str, tuple[tuple[str, ...], bool]]] = {
    "lexemes": {
        "pos": (POS_VALUES, True),
        "gender": (GENDER_VALUES, False),
        "register": (REGISTER_VALUES, False),
        "status": (STATUS_VALUES, True),
    },
    "attestations": {"source_kind": (SOURCE_KIND_VALUES, True)},
    "examples": {"origin": (ORIGIN_VALUES, True)},
    "pronunciations": {"target_kind": (tuple(PRONUNCIATION_TARGETS), True)},
    # Who says a line and which half of a word's pair it is are what a player colours and holds
    # back, so they are closed; a line's `kind` and `section` are the generator's vocabulary and grow
    # with its formats, so they are only bounded.
    "loop_cues": {"role": (("native", "guide"), True), "side": (("source", "target"), False)},
}

# field -> (minimum, maximum or None)
NUMBER_RULES: dict[str, dict[str, tuple[float, float | None]]] = {
    "vocabularies": {"vocab_order": (0, None)},
    "topics": {"topic_order": (0, None)},
    "senses": {"sense_order": (0, None)},
    "examples": {"video_start": (0, None), "video_end": (0, None)},
    "image_prompts": {"seed": (0, 2147483647), "attempts": (0, None)},
    "study_states": {
        "note_id": (0, None), "reps": (0, None), "lapses": (0, None),
        "stability": (0, None), "difficulty": (0, None), "retrievability": (0, 1),
    },
    "loops": {
        # The JavaScript safe-integer bound, not 2^31: the replica is a browser and a JSON number
        # is a double there, so this is the largest value that can round-trip at all. A generator
        # that mints its own seed rather than taking the one Acervo sends still fits, as long as it
        # fits in a double — which `secrets.randbits(64)` does not, and that is what refused the
        # first real render. `image_prompts` keeps 2^31 because Acervo mints those itself.
        "seed": (0, 9007199254740991), "duration_seconds": (0, None), "loop_order": (0, None),
    },
    "loop_items": {
        "item_order": (0, None), "start_seconds": (0, None), "source_reveal_seconds": (0, None),
        "target_reveal_seconds": (0, None), "end_seconds": (0, None),
    },
    "loop_cues": {
        "cue_order": (0, None), "cue_group": (0, None), "take": (0, None),
        "start_seconds": (0, None), "end_seconds": (0, None),
    },
    "stories": {"story_order": (0, None)},
    "story_parts": {"part_order": (0, None), "attempts": (0, None)},
    "story_words": {"word_order": (0, None)},
    # The loop's own bound, since a favourite's seed is a loop's seed.
    "beds": {"seed": (0, 9007199254740991)},
}

# The row a related id resolves to, or None. Supplied by the repository, so this module never learns
# what a database is.
Lookup = Callable[[str, str], Mapping[str, Any] | None]


def refuse(message: str) -> None:
    raise RecordRefused(message)


def _text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    return "" if value is None else str(value).strip()


def valid_language(value: Any, label: str) -> str:
    language = "" if value is None else str(value).strip()
    if not is_language(language):
        refuse(f"{label} must be a BCP-47 language tag.")
    return language


def string_array(value: Any, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        refuse(f"{label} must be an array of non-empty strings.")
    if len(set(value)) != len(value):
        refuse(f"{label} must not contain duplicates.")


def gloss_array(value: Any) -> None:
    if not isinstance(value, list) or not value:
        refuse("Glosses must contain at least one language group.")
    seen: set[str] = set()
    for gloss in value:
        if not isinstance(gloss, dict):
            refuse("Each gloss must be an object.")
        language = valid_language(gloss.get("lang"), "Gloss language")
        if language in seen:
            refuse("Gloss languages must be unique within a sense.")
        seen.add(language)
        string_array(gloss.get("terms"), "Gloss terms")
        if not gloss.get("terms"):
            refuse("Each gloss must contain at least one term.")


def _related(lookup: Lookup, table: str, identifier: str, label: str) -> Mapping[str, Any]:
    row = lookup(table, identifier) if identifier else None
    if row is None:
        refuse(f"{label} does not exist.")
    return row  # type: ignore[return-value]


def _audio_segments(value: Any) -> None:
    """A part's passages: each one has words, its own recording, and a direction that fits where a
    direction is recorded. Whether they join back to the part's text is not checked here — the text
    is the story's and a recording made from an earlier text is simply not shown on the device
    (`segmentSpans` refuses passages that do not tile it)."""
    if value is None or value == []:
        return
    if not isinstance(value, list):
        refuse("A story part's passages must be a list.")
    if len(value) > 32:
        refuse("A story part has too many passages.")
    for one in value:
        if not isinstance(one, Mapping) or not isinstance(one.get("text"), str) or not one["text"]:
            refuse("A passage of a story part must have text.")
        if len(str(one.get("direction") or "")) > 300:
            refuse("A passage's direction is too long.")
        # Its own file, which is the whole of what "recorded" means here: a passage without one is a
        # passage nothing can play, and a part is written only once every one of them exists.
        if not str(one.get("audioRef") or "").strip():
            refuse("A passage of a story part must name its own recording.")
        if len(str(one.get("audioRef"))) > 500 or len(str(one.get("audioMime") or "")) > 120:
            refuse("A passage's recording is named too long.")


def _photo_region(value: Any, has_photo: bool) -> None:
    """Where on the photo the word and its sentence are: `{words: [...], sentence: [...]}`, each a list
    of polygons, each polygon a list of `[x, y]` points normalised to the image."""
    if value is None:
        return
    if not has_photo:
        refuse("A photo region needs a photo.")
    if not isinstance(value, Mapping) or set(value) - {"words", "sentence"}:
        refuse("A photo region has words and a sentence, and nothing else.")
    count = 0
    for key in ("words", "sentence"):
        polygons = value.get(key, [])
        if not isinstance(polygons, list):
            refuse("A photo region's polygons must be a list.")
        for polygon in polygons:
            if not isinstance(polygon, list) or not 3 <= len(polygon) <= 16:
                refuse("A photo region's polygon must have between three and sixteen points.")
            for point in polygon:
                if (
                    not isinstance(point, list) or len(point) != 2
                    or not all(isinstance(axis, (int, float)) and 0 <= axis <= 1 for axis in point)
                ):
                    refuse("A photo region's points must be [x, y] between 0 and 1.")
            count += 1
    if count > PHOTO_REGION_LIMIT:
        refuse("A photo region has too many polygons.")


def _same_owner(row: Mapping[str, Any], parent: Mapping[str, Any], label: str) -> None:
    if row.get("owner") != parent.get("owner"):
        refuse(f"{label} must belong to the same owner.")


def _check_declared_bounds(name: str, row: Mapping[str, Any]) -> None:
    for field, (required, maximum) in TEXT_RULES.get(name, {}).items():
        value = _text(row, field)
        if required and not value:
            refuse(f"{field} is required.")
        if len(value) > maximum:
            refuse(f"{field} must be at most {maximum} characters.")
    for field, (allowed, required) in SELECT_RULES.get(name, {}).items():
        value = _text(row, field)
        if not value:
            if required:
                refuse(f"{field} is required.")
            continue
        if value not in allowed:
            refuse(f"{field} must be one of {', '.join(allowed)}.")
    for field, (minimum, maximum) in NUMBER_RULES.get(name, {}).items():
        value = row.get(field) or 0
        if value < minimum or (maximum is not None and value > maximum):
            refuse(f"{field} is out of range.")


def _sync_record(row: Mapping[str, Any]) -> None:
    if not is_record_id(str(row.get("id") or "")):
        refuse("Record ids must be 15 lowercase letters or digits.")
    if not is_instant(_text(row, "created_at")) or not is_instant(_text(row, "edited_at")):
        refuse("Record timestamps must be ISO-8601 UTC instants with milliseconds.")


def validate(name: str, row: Mapping[str, Any], lookup: Lookup) -> None:
    """Hold one record to every rule its collection carries. Raises `RecordRefused`."""
    _sync_record(row)
    _check_declared_bounds(name, row)

    if name == "vocabularies":
        valid_language(row.get("language"), "Vocabulary language")
        valid_language(row.get("definition_lang"), "Vocabulary definition language")
        gloss_langs = row.get("gloss_langs")
        string_array(gloss_langs, "Vocabulary gloss languages")
        if not gloss_langs:
            refuse("A vocabulary needs at least one gloss language.")
        for code in gloss_langs:  # type: ignore[union-attr]
            valid_language(code, "Vocabulary gloss language")
        valid_language(row.get("notes_lang"), "Vocabulary notes language")
        return

    if name == "topics":
        if not _text(row, "name"):
            refuse("Topic name is required.")
        return

    if name == "lexemes":
        language = valid_language(row.get("language"), "Lexeme language")
        # A prefix test, so `zh-Hant-TW` and `zho` both match. Narrowing this to equality would let a
        # Chinese entry through with no way to read it.
        if language.lower().startswith("zh") and not _text(row, "reading"):
            refuse("Chinese lexemes require a reading.")
        dialect = _text(row, "dialect")
        if dialect:
            valid_language(dialect, "Lexeme dialect")
        for topic_id in row.get("topics") or []:
            _same_owner(row, _related(lookup, "topics", topic_id, "Topic"), "Lexeme topic")
        string_array(row.get("notes"), "Notes")
        searched = _text(row, "clips_searched_at")
        if searched and not is_instant(searched):
            refuse("Clip search timestamp must be an ISO-8601 UTC instant with milliseconds.")
        return

    if name == "senses":
        _same_owner(row, _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme"), "Sense")
        valid_language(row.get("definition_lang"), "Definition language")
        gloss_array(row.get("glosses"))
        return

    if name == "attestations":
        _same_owner(row, _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme"), "Attestation")
        if not is_instant(_text(row, "captured_at")):
            refuse("Capture timestamp must be an ISO-8601 UTC instant with milliseconds.")
        photo = _text(row, "photo_ref")
        # A photo with no sentence is a place the word was met — a street sign has no sentence — so
        # the text may be empty then, and only then.
        if not _text(row, "text") and not photo:
            refuse("text is required.")
        if photo:
            match = PHOTO_REF.match(photo)
            if match is None:
                refuse("An attestation's photo must be a photo this server stored.")
            if match["owner"] != row.get("owner"):  # type: ignore[index]
                refuse("An attestation's photo must belong to the same owner.")
        _photo_region(row.get("photo_region"), bool(photo))
        return

    if name == "examples":
        sense = _related(lookup, "senses", _text(row, "sense"), "Sense")
        _same_owner(row, sense, "Example")
        valid_language(row.get("text_lang"), "Example language")
        translation = _text(row, "translation")
        translation_language = _text(row, "translation_lang")
        if bool(translation) != bool(translation_language):
            refuse("Example translation and language must be provided together.")
        if translation_language:
            valid_language(translation_language, "Translation language")
        # `video_ref` is what every clip field hangs on: a title, a channel, a timing or the
        # corpus's own segment id without one describes a clip that names no video, and the
        # projection hides them all when there is none.
        video_ref = _text(row, "video_ref")
        start = row.get("video_start") or 0
        end = row.get("video_end") or 0
        if not video_ref and (
            _text(row, "video_title")
            or _text(row, "video_channel")
            or _text(row, "clip_ref")
            or start > 0
            or end > 0
        ):
            refuse("An example clip title, channel, segment or timing requires a video reference.")
        if end and end <= start:
            refuse("An example clip must end after it starts.")
        # Verbatim: untrimmed, uncased, un-normalised. Capture silently drops a form that fails this
        # exact test, so loosening it breaks the drop and tightening it turns a good capture into a
        # refusal.
        matched = _text(row, "matched_form")
        if matched and matched not in str(row.get("text") or ""):
            refuse("The matched form must occur in the example text.")
        matched_translation = _text(row, "matched_translation_form")
        if matched_translation and matched_translation not in translation:
            refuse("The matched translation form must occur in the example translation.")
        source_id = _text(row, "source_attestation")
        if _text(row, "origin") == "attestation" and not source_id:
            refuse("Attestation examples require a source attestation.")
        if source_id:
            attestation = _related(lookup, "attestations", source_id, "Source attestation")
            _same_owner(row, attestation, "Example source attestation")
            # The second hop. An attestation belonging to the right owner but the wrong word would
            # otherwise pass.
            if attestation.get("lexeme") != sense.get("lexeme"):
                refuse("Example source attestation and sense must belong to the same lexeme.")
        return

    if name == "image_prompts":
        lexeme = _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme")
        _same_owner(row, lexeme, "Image prompt")
        sense_id = _text(row, "sense")
        if sense_id:
            sense = _related(lookup, "senses", sense_id, "Sense")
            _same_owner(row, sense, "Image prompt sense")
            if sense.get("lexeme") != lexeme.get("id"):
                refuse("Image prompt sense must belong to its lexeme.")
        example_id = _text(row, "example")
        if example_id:
            example = _related(lookup, "examples", example_id, "Image prompt example")
            _same_owner(row, example, "Image prompt example")
            # The second hop, exactly as for an example's source attestation: an example belonging
            # to the right owner but the wrong sense would otherwise pass.
            if sense_id and example.get("sense") != sense_id:
                refuse("Image prompt example must belong to its sense.")
        # A brief the writer wrote is three fields or none of them: `compose()` needs the style to
        # build the prompt that was actually sent, and `prompt_version` is what says which template
        # and style table produced it. Half a brief reproduces nothing.
        if _text(row, "prompt") and not (_text(row, "style_id") and _text(row, "prompt_version")):
            refuse("An image brief must name the style and the prompt version it was written for.")
        # One direction, not both. A rendering model with nothing rendered is nonsense; a rendered
        # image with no model is a picture the owner attached themselves, which is how provenance is
        # modelled everywhere else here — an example the learner wrote carries no `model_id` either.
        if _text(row, "image_model_id") and not _text(row, "image_ref"):
            refuse("A rendering model without a rendered image is not a record of anything.")
        return

    if name == "pronunciations":
        lexeme = _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme")
        _same_owner(row, lexeme, "Pronunciation")
        valid_language(row.get("lang"), "Pronunciation language")
        table, _field = PRONUNCIATION_TARGETS[_text(row, "target_kind")]
        target = _related(lookup, table, _text(row, "target_id"), "Pronounced record")
        _same_owner(row, target, "Pronounced record")
        # Every target must belong to this pronunciation's word; an example reaches it through its
        # sense, which is the second hop that a record of the right owner but another word would pass.
        if table == "lexemes":
            word = target.get("id")
        elif table == "examples":
            word = (_related(lookup, "senses", str(target.get("sense") or ""), "Example sense") or {}).get("lexeme")
        else:
            word = target.get("lexeme")
        if word != lexeme.get("id"):
            refuse("A pronounced record must belong to the pronunciation's lexeme.")
        return

    if name == "loops":
        valid_language(row.get("language"), "Loop language")
        # A rendered track is bytes plus the type of those bytes. A mime with no reference describes
        # nothing, and a reference with no mime is a file nothing can decide how to play — and the
        # projection hides both when there is no reference, so this is the same invariant asserted
        # on the way in that `_project_loop` asserts on the way out.
        audio_ref = _text(row, "audio_ref")
        if bool(audio_ref) != bool(_text(row, "audio_mime")):
            refuse("A loop's audio reference and type must be provided together.")
        if not audio_ref and (row.get("duration_seconds") or 0) > 0:
            refuse("A loop that has not been rendered has no duration.")
        return

    if name == "beds":
        # The loop it was kept from is required and same-owner, and deliberately *not* required to
        # be alive: a favourite outlives the loop, and its reference then names a tombstone.
        _same_owner(row, _related(lookup, "loops", _text(row, "source_loop"), "Loop"),
                    "Favourite bed")
        return

    if name == "loop_items":
        loop = _related(lookup, "loops", _text(row, "loop"), "Loop")
        _same_owner(row, loop, "Loop item")
        # The word is required and same-owner, but it is deliberately *not* required to be alive:
        # deleting a word leaves the loops it appears in playing, captioned with what was actually
        # said. The reference then points at a tombstone, which is the honest state.
        _same_owner(row, _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme"), "Loop item")
        start, end = row.get("start_seconds") or 0.0, row.get("end_seconds") or 0.0
        if end < start:
            refuse("A loop item's times must not run backwards.")
        for field in ("source_reveal_seconds", "target_reveal_seconds"):
            # Either side may come first — a review format asks the meaning before the word — but
            # each is heard within the word's own block, or not at all.
            reveal = row.get(field)
            if reveal is not None and not start <= reveal <= end:
                refuse("A loop item's sides are heard within its own block.")
        return

    if name == "loop_cues":
        loop = _related(lookup, "loops", _text(row, "loop"), "Loop")
        _same_owner(row, loop, "Loop line")
        item = _text(row, "loop_item")
        if item:
            _same_owner(row, _related(lookup, "loop_items", item, "Loop item"), "Loop line")
        if (row.get("end_seconds") or 0.0) < (row.get("start_seconds") or 0.0):
            refuse("A loop line's times must not run backwards.")
        if bool(_text(row, "side")) and not item:
            refuse("Only a word's own line says one side of it.")
        return

    if name == "stories":
        valid_language(row.get("language"), "Story language")
        return

    if name == "story_parts":
        _same_owner(row, _related(lookup, "stories", _text(row, "story"), "Story"), "Story part")
        # A drawn picture is bytes plus the model that made them, and the projection hides the model
        # when there is no reference — so this is the same invariant on the way in that
        # `_project_story_part` asserts on the way out. `loops` states it for a track.
        if _text(row, "image_model_id") and not _text(row, "image_ref"):
            refuse("A story part that has no picture cannot name the model that drew one.")
        if not row.get("audio_segments") and (
            _text(row, "audio_provider_id") or _text(row, "audio_model_id") or _text(row, "audio_voice")
        ):
            refuse("A story part that has not been read aloud cannot say who spoke it.")
        _audio_segments(row.get("audio_segments"))
        return

    if name == "story_words":
        _same_owner(row, _related(lookup, "stories", _text(row, "story"), "Story"), "Story word")
        # Same-owner and required, but deliberately *not* required to be alive, for the reason a
        # loop item's word is not: deleting a word leaves the stories it appears in readable, and
        # the text still truthfully says which word it was written around.
        _same_owner(row, _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme"), "Story word")
        forms = row.get("forms")
        if not isinstance(forms, list) or any(not isinstance(one, str) for one in forms):
            refuse("A story word's forms must be a list of strings.")
        elif any(len(one) > 240 for one in forms):
            refuse("A story word's form is too long.")
        translation_forms = row.get("translation_forms")
        if not isinstance(translation_forms, list) or any(not isinstance(one, str) for one in translation_forms):
            refuse("A story word's translated forms must be a list of strings.")
        elif any(len(one) > 240 for one in translation_forms):
            refuse("A story word's translated form is too long.")
        return

    if name == "study_states":
        lexeme = _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme")
        _same_owner(row, lexeme, "Study state")
        sense_id = _text(row, "sense")
        if sense_id:
            sense = _related(lookup, "senses", sense_id, "Sense")
            _same_owner(row, sense, "Study state sense")
            if sense.get("lexeme") != lexeme.get("id"):
                refuse("Study state sense must belong to its lexeme.")
        card_ids = row.get("card_ids")
        if not isinstance(card_ids, list) or any(
            not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 0
            for identifier in card_ids
        ):
            refuse("Study-state card ids must be non-negative safe integers.")
        for field in ("last_review", "synced_at"):
            value = _text(row, field)
            if value and not is_instant(value):
                refuse(f"{field} must be an ISO-8601 UTC instant with milliseconds.")
