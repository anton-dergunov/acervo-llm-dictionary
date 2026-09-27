"""Storage <-> client mapping, in graph order.

Maps the snake_case storage boundary onto the camelCase client model in `web/src/domain.ts`.
Tombstones are included; the client owns filtering.

The order of `COLLECTIONS` is load-bearing three times over. It is the order a pull is assembled in;
it is the merge order the write route applies a batch in, so a relation always resolves before the
record that names it; and reversed, with the first two entries dropped, it is the tombstone order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Table

from acervo.db import tables

# ── coercion ────────────────────────────────────────────────────────────────
# The client is not the only writer and a model's answer reaches `assign` too, so every one of these
# is deliberately total: it produces a storable value for anything, and validation — not coercion —
# is what refuses a record.


def trimmed(value: Any) -> str:
    return "" if value is None else str(value).strip()


def text_or_none(value: Any) -> str | None:
    """What the wire calls an absent string. Storage keeps `""`; the projection says `null`."""
    return trimmed(value) or None


def to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def to_bool(value: Any) -> bool:
    return value is True


@dataclass(frozen=True)
class Collection:
    """One row of the projection table: a wire key, a storage table, and the two directions."""

    key: str
    table: Table
    project: Callable[[Mapping[str, Any]], dict[str, Any]]
    assign: Callable[[Mapping[str, Any]], dict[str, Any]]

    @property
    def name(self) -> str:
        return self.table.name


def _project_vocabulary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": row["language"],
        "definitionLang": row["definition_lang"],
        "glossLangs": to_list(row["gloss_langs"]),
        "notesLang": row["notes_lang"],
        "displayName": text_or_none(row["display_name"]),
        "flag": text_or_none(row["flag"]),
        "order": to_int(row["vocab_order"]),
    }


def _assign_vocabulary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": trimmed(value.get("language")),
        "definition_lang": trimmed(value.get("definitionLang")),
        "gloss_langs": to_list(value.get("glossLangs")),
        "notes_lang": trimmed(value.get("notesLang")),
        "display_name": trimmed(value.get("displayName")),
        "flag": trimmed(value.get("flag")),
        "vocab_order": to_int(value.get("order")),
    }


def _project_topic(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "icon": text_or_none(row["icon"]),
        "order": to_int(row["topic_order"]),
    }


def _assign_topic(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": trimmed(value.get("name")),
        "icon": trimmed(value.get("icon")),
        "topic_order": to_int(value.get("order")),
    }


def _project_lexeme(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": row["language"],
        "headword": row["headword"],
        "lemma": row["lemma"],
        "reading": text_or_none(row["reading"]),
        "ipa": text_or_none(row["ipa"]),
        "pos": row["pos"],
        "gender": text_or_none(row["gender"]),
        "register": text_or_none(row["register"]),
        "dialect": text_or_none(row["dialect"]),
        "emoji": text_or_none(row["emoji"]),
        "topicIds": to_list(row["topics"]),
        "status": row["status"],
        "shortGloss": text_or_none(row["short_gloss"]),
        "primaryGloss": text_or_none(row["primary_gloss"]),
        "emotion": text_or_none(row["emotion"]),
        "notes": to_list(row["notes"]),
        "clipsSearchedAt": text_or_none(row["clips_searched_at"]),
    }


def _assign_lexeme(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": trimmed(value.get("language")),
        "headword": trimmed(value.get("headword")),
        "lemma": trimmed(value.get("lemma")),
        "reading": trimmed(value.get("reading")),
        "ipa": trimmed(value.get("ipa")),
        "pos": trimmed(value.get("pos")),
        "gender": trimmed(value.get("gender")),
        "register": trimmed(value.get("register")),
        "dialect": trimmed(value.get("dialect")),
        "emoji": trimmed(value.get("emoji")),
        "topics": to_list(value.get("topicIds")),
        "status": trimmed(value.get("status")),
        "short_gloss": trimmed(value.get("shortGloss")),
        "primary_gloss": trimmed(value.get("primaryGloss")),
        "emotion": trimmed(value.get("emotion")),
        "notes": to_list(value.get("notes")),
        "clips_searched_at": trimmed(value.get("clipsSearchedAt")),
    }


def _project_sense(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "definition": row["definition"],
        "definitionLang": row["definition_lang"],
        "glosses": to_list(row["glosses"]),
        "domain": text_or_none(row["domain"]),
        "emoji": text_or_none(row["emoji"]),
        "order": to_int(row["sense_order"]),
    }


def _assign_sense(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "definition": trimmed(value.get("definition")),
        "definition_lang": trimmed(value.get("definitionLang")),
        "glosses": to_list(value.get("glosses")),
        "domain": trimmed(value.get("domain")),
        "emoji": trimmed(value.get("emoji")),
        "sense_order": to_int(value.get("order")),
    }


def _project_attestation(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "text": row["text"],
        "translation": text_or_none(row["translation"]),
        "sourceUrl": text_or_none(row["source_url"]),
        "sourceTitle": text_or_none(row["source_title"]),
        "sourceKind": row["source_kind"],
        "capturedAt": text_or_none(row["captured_at"]),
        "photoRef": text_or_none(row["photo_ref"]),
        "photoRegion": row["photo_region"],
    }


def _assign_attestation(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "text": trimmed(value.get("text")),
        "translation": trimmed(value.get("translation")),
        "source_url": trimmed(value.get("sourceUrl")),
        "source_title": trimmed(value.get("sourceTitle")),
        "source_kind": trimmed(value.get("sourceKind")),
        "captured_at": trimmed(value.get("capturedAt")),
        "photo_ref": trimmed(value.get("photoRef")),
        "photo_region": value.get("photoRegion") or None,
    }


def _project_example(row: Mapping[str, Any]) -> dict[str, Any]:
    # Every clip field is hidden when there is no reference. That invariant is asserted twice on
    # purpose — the validator refuses the combination on the way in, and this refuses to show it on
    # the way out.
    video_ref = text_or_none(row["video_ref"])
    return {
        "senseId": row["sense"],
        "text": row["text"],
        "textLang": row["text_lang"],
        "translation": text_or_none(row["translation"]),
        "translationLang": text_or_none(row["translation_lang"]),
        "origin": row["origin"],
        "sourceAttestationId": text_or_none(row["source_attestation"]),
        "modelId": text_or_none(row["model_id"]),
        "videoRef": video_ref,
        "videoTitle": text_or_none(row["video_title"]) if video_ref else None,
        "videoChannel": text_or_none(row["video_channel"]) if video_ref else None,
        "videoStart": to_int(row["video_start"]) if video_ref else None,
        "videoEnd": to_int(row["video_end"]) if video_ref else None,
        "clipRef": text_or_none(row["clip_ref"]) if video_ref else None,
        "imageRef": text_or_none(row["image_ref"]),
        "emotion": text_or_none(row["emotion"]),
        "note": text_or_none(row["note"]),
        "matchedForm": text_or_none(row["matched_form"]),
        "matchedTranslationForm": text_or_none(row["matched_translation_form"]),
    }


def _assign_example(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sense": trimmed(value.get("senseId")),
        "text": trimmed(value.get("text")),
        "text_lang": trimmed(value.get("textLang")),
        "translation": trimmed(value.get("translation")),
        "translation_lang": trimmed(value.get("translationLang")),
        "origin": trimmed(value.get("origin")),
        # A relation, so an absent one is NULL rather than "": a foreign key of "" resolves to
        # nothing and would trip the constraint.
        "source_attestation": trimmed(value.get("sourceAttestationId")) or None,
        "model_id": trimmed(value.get("modelId")),
        "video_ref": trimmed(value.get("videoRef")),
        "video_title": trimmed(value.get("videoTitle")),
        "video_channel": trimmed(value.get("videoChannel")),
        "video_start": to_int(value.get("videoStart")),
        "video_end": to_int(value.get("videoEnd")),
        "clip_ref": trimmed(value.get("clipRef")),
        "image_ref": trimmed(value.get("imageRef")),
        "emotion": trimmed(value.get("emotion")),
        "note": trimmed(value.get("note")),
        "matched_form": trimmed(value.get("matchedForm")),
        "matched_translation_form": trimmed(value.get("matchedTranslationForm")),
    }


def _project_image_prompt(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "senseId": text_or_none(row["sense"]),
        "prompt": row["prompt"],
        "styleId": row["style_id"],
        "seed": to_int(row["seed"]),
        "modelId": row["model_id"],
        "promptVersion": row["prompt_version"],
        "imageRef": text_or_none(row["image_ref"]),
        "imageModelId": text_or_none(row["image_model_id"]),
        "exampleId": text_or_none(row["example"]),
        "attempts": to_int(row["attempts"]),
        "failureReason": text_or_none(row["failure_reason"]),
        "suppressed": to_bool(row["suppressed"]),
    }


def _assign_image_prompt(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "sense": trimmed(value.get("senseId")) or None,
        "prompt": trimmed(value.get("prompt")),
        "style_id": trimmed(value.get("styleId")),
        "seed": to_int(value.get("seed")),
        "model_id": trimmed(value.get("modelId")),
        "prompt_version": trimmed(value.get("promptVersion")),
        "image_ref": trimmed(value.get("imageRef")),
        "image_model_id": trimmed(value.get("imageModelId")),
        # An empty string here would be a foreign key of "", which trips the constraint.
        "example": trimmed(value.get("exampleId")) or None,
        "attempts": to_int(value.get("attempts")),
        "failure_reason": trimmed(value.get("failureReason")),
        "suppressed": to_bool(value.get("suppressed")),
    }


def _project_pronunciation(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "targetKind": row["target_kind"],
        "targetId": row["target_id"],
        "text": row["text"],
        "lang": row["lang"],
        "emotion": text_or_none(row["emotion"]),
        "audioRef": row["audio_ref"],
        "audioMime": row["audio_mime"],
        "providerId": row["provider_id"],
        "modelId": row["model_id"],
        "voice": text_or_none(row["voice"]),
    }


def _assign_pronunciation(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "target_kind": trimmed(value.get("targetKind")),
        "target_id": trimmed(value.get("targetId")),
        # Verbatim, not trimmed: staleness is decided by comparing this to the record's text.
        "text": "" if value.get("text") is None else str(value.get("text")),
        "lang": trimmed(value.get("lang")),
        "emotion": trimmed(value.get("emotion")),
        "audio_ref": trimmed(value.get("audioRef")),
        "audio_mime": trimmed(value.get("audioMime")),
        "provider_id": trimmed(value.get("providerId")),
        "model_id": trimmed(value.get("modelId")),
        "voice": trimmed(value.get("voice")),
    }


def _project_study_state(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "system": row["system"],
        # Alone among the numbers, zero projects as null: there is no Anki note 0, so a stored zero
        # means "not pushed yet" rather than "note zero".
        "noteId": to_int(row["note_id"]) or None,
        "cardIds": to_list(row["card_ids"]),
        "reps": to_int(row["reps"]),
        "lapses": to_int(row["lapses"]),
        "stability": to_float(row["stability"]),
        "difficulty": to_float(row["difficulty"]),
        "retrievability": to_float(row["retrievability"]),
        "lastReview": text_or_none(row["last_review"]),
        "syncedAt": text_or_none(row["synced_at"]),
    }


def _assign_study_state(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "system": trimmed(value.get("system")),
        "note_id": to_int(value.get("noteId")),
        "card_ids": to_list(value.get("cardIds")),
        "reps": to_int(value.get("reps")),
        "lapses": to_int(value.get("lapses")),
        "stability": to_float(value.get("stability")),
        "difficulty": to_float(value.get("difficulty")),
        "retrievability": to_float(value.get("retrievability")),
        "last_review": trimmed(value.get("lastReview")),
        "synced_at": trimmed(value.get("syncedAt")),
    }


def _project_loop(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": row["language"],
        "styleId": text_or_none(row["style_id"]),
        "seed": to_int(row["seed"]),
        "engineVersion": text_or_none(row["engine_version"]),
        "bedFingerprint": text_or_none(row["bed_fingerprint"]),
        "format": row["format"],
        "switches": _project_switches(row["switches"]),
        "fallbackFrom": text_or_none(row["fallback_from"]),
        # An absent reference is what "not rendered yet" looks like, so the mime and the duration are
        # hidden with it rather than projected as an empty string and a zero that read like facts.
        "audioRef": text_or_none(row["audio_ref"]),
        "audioMime": text_or_none(row["audio_mime"]) if trimmed(row["audio_ref"]) else None,
        "durationSeconds": to_float(row["duration_seconds"]) if trimmed(row["audio_ref"]) else None,
        "position": to_int(row["loop_order"]),
    }


def _assign_loop(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": trimmed(value.get("language")),
        "style_id": trimmed(value.get("styleId")),
        "seed": to_int(value.get("seed")),
        "engine_version": trimmed(value.get("engineVersion")),
        "bed_fingerprint": trimmed(value.get("bedFingerprint")),
        "format": trimmed(value.get("format")),
        "switches": _assign_switches(value.get("switches")),
        "fallback_from": trimmed(value.get("fallbackFrom")),
        "audio_ref": trimmed(value.get("audioRef")),
        "audio_mime": trimmed(value.get("audioMime")),
        "duration_seconds": to_float(value.get("durationSeconds")),
        "loop_order": to_int(value.get("position")),
    }


def _project_switches(value: Any) -> dict[str, bool | str]:
    return {str(name): choice for name, choice in (value or {}).items()
            if isinstance(choice, (bool, str))} if isinstance(value, Mapping) else {}


def _assign_switches(value: Any) -> dict[str, bool | str]:
    # Not filtered for meaning beyond its shape: which switches a format offers is the generator's,
    # checked against its schema when the loop is asked for.
    if not isinstance(value, Mapping):
        return {}
    return {trimmed(name): choice if isinstance(choice, bool) else trimmed(choice)
            for name, choice in value.items()}


def to_optional_float(value: Any) -> float | None:
    return None if value is None else to_float(value)


def _project_bed(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "styleId": row["style_id"],
        "seed": to_int(row["seed"]),
        "engineVersion": text_or_none(row["engine_version"]),
        "bedFingerprint": text_or_none(row["bed_fingerprint"]),
        "sourceLoopId": row["source_loop"],
    }


def _assign_bed(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "style_id": trimmed(value.get("styleId")),
        "seed": to_int(value.get("seed")),
        "engine_version": trimmed(value.get("engineVersion")),
        "bed_fingerprint": trimmed(value.get("bedFingerprint")),
        "source_loop": trimmed(value.get("sourceLoopId")),
    }


def _project_loop_item(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "loopId": row["loop"],
        "lexemeId": row["lexeme"],
        "position": to_int(row["item_order"]),
        "sourceText": row["source_text"],
        "targetText": row["target_text"],
        "emotion": text_or_none(row["emotion"]),
        "startSeconds": to_float(row["start_seconds"]),
        "sourceRevealSeconds": to_optional_float(row["source_reveal_seconds"]),
        "targetRevealSeconds": to_optional_float(row["target_reveal_seconds"]),
        "endSeconds": to_float(row["end_seconds"]),
    }


def _assign_loop_item(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "loop": trimmed(value.get("loopId")),
        "lexeme": trimmed(value.get("lexemeId")),
        "item_order": to_int(value.get("position")),
        # Verbatim, not trimmed, for `pronunciations.text`'s reason: this is what was said, and a
        # caption that has been tidied no longer matches the recording it describes.
        "source_text": "" if value.get("sourceText") is None else str(value.get("sourceText")),
        "target_text": "" if value.get("targetText") is None else str(value.get("targetText")),
        "emotion": trimmed(value.get("emotion")),
        "start_seconds": to_float(value.get("startSeconds")),
        "source_reveal_seconds": to_optional_float(value.get("sourceRevealSeconds")),
        "target_reveal_seconds": to_optional_float(value.get("targetRevealSeconds")),
        "end_seconds": to_float(value.get("endSeconds")),
    }


def _project_loop_cue(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "loopId": row["loop"],
        "position": to_int(row["cue_order"]),
        "group": to_int(row["cue_group"]),
        "kind": row["kind"],
        "section": row["section"],
        "loopItemId": text_or_none(row["loop_item"]),
        "side": text_or_none(row["side"]),
        "role": row["role"],
        "language": row["language"],
        "text": row["text"],
        "take": to_int(row["take"]),
        "startSeconds": to_float(row["start_seconds"]),
        "endSeconds": to_float(row["end_seconds"]),
    }


def _assign_loop_cue(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "loop": trimmed(value.get("loopId")),
        "cue_order": to_int(value.get("position")),
        "cue_group": to_int(value.get("group")),
        "kind": trimmed(value.get("kind")),
        "section": trimmed(value.get("section")),
        "loop_item": trimmed(value.get("loopItemId")) or None,
        "side": trimmed(value.get("side")),
        "role": trimmed(value.get("role")),
        "language": trimmed(value.get("language")),
        # Verbatim, for `loop_items.source_text`'s reason: what was said.
        "text": "" if value.get("text") is None else str(value.get("text")),
        "take": to_int(value.get("take")),
        "start_seconds": to_float(value.get("startSeconds")),
        "end_seconds": to_float(value.get("endSeconds")),
    }


def _project_story(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": row["language"],
        "typeId": text_or_none(row["type_id"]),
        "styleId": text_or_none(row["style_id"]),
        "title": text_or_none(row["title"]),
        "titleTranslation": text_or_none(row["title_translation"]),
        "emoji": text_or_none(row["emoji"]),
        "modelId": text_or_none(row["model_id"]),
        "position": to_int(row["story_order"]),
        "guidance": text_or_none(row["guidance"]),
    }


def _assign_story(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": trimmed(value.get("language")),
        "type_id": trimmed(value.get("typeId")),
        "style_id": trimmed(value.get("styleId")),
        "title": trimmed(value.get("title")),
        "title_translation": trimmed(value.get("titleTranslation")),
        "emoji": trimmed(value.get("emoji")),
        "model_id": trimmed(value.get("modelId")),
        "story_order": to_int(value.get("position")),
        "guidance": trimmed(value.get("guidance")),
    }


def _project_story_part(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "storyId": row["story"],
        "position": to_int(row["part_order"]),
        "heading": text_or_none(row["heading"]),
        "headingTranslation": text_or_none(row["heading_translation"]),
        "text": row["text"],
        "translation": row["translation"],
        "imagePrompt": text_or_none(row["image_prompt"]),
        # An absent reference is what "not drawn yet" looks like, so the model that would have drawn
        # it is hidden with it rather than projected as an empty string that reads like a fact. The
        # same treatment `_project_loop` gives a track that does not exist.
        "imageRef": text_or_none(row["image_ref"]),
        "imageModelId": text_or_none(row["image_model_id"]) if trimmed(row["image_ref"]) else None,
        "attempts": to_int(row["attempts"]),
        "failureReason": text_or_none(row["failure_reason"]),
        # Hidden together with the passages they describe, as `imageModelId` is with its picture.
        "audioProviderId": text_or_none(row["audio_provider_id"]) if row["audio_segments"] else None,
        "audioModelId": text_or_none(row["audio_model_id"]) if row["audio_segments"] else None,
        "audioVoice": text_or_none(row["audio_voice"]) if row["audio_segments"] else None,
        "audioSegments": _project_segments(row["audio_segments"]),
    }


def _project_segments(value: Any) -> list[dict[str, Any]]:
    return [
        {"text": str(one.get("text") or ""), "direction": str(one.get("direction") or ""),
         "audioRef": str(one.get("audioRef") or ""), "audioMime": str(one.get("audioMime") or ""),
         "durationSeconds": float(one.get("durationSeconds") or 0)}
        for one in (value or []) if isinstance(one, Mapping)
    ]


def _assign_segments(value: Any) -> list[dict[str, Any]]:
    # Not filtered for meaning: `validation.py` refuses a list that does not hold together, and a
    # value that is not a list at all is refused there too rather than quietly emptied here.
    if not isinstance(value, list):
        return []
    return [
        {"text": "" if one.get("text") is None else str(one.get("text")),
         "direction": trimmed(one.get("direction")),
         "audioRef": trimmed(one.get("audioRef")), "audioMime": trimmed(one.get("audioMime")),
         "durationSeconds": to_float(one.get("durationSeconds"))}
        for one in value if isinstance(one, Mapping)
    ]


def _assign_story_part(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "story": trimmed(value.get("storyId")),
        "part_order": to_int(value.get("position")),
        "heading": trimmed(value.get("heading")),
        "heading_translation": trimmed(value.get("headingTranslation")),
        # Verbatim, not trimmed: this is the story, and paragraph shape is part of it.
        "text": "" if value.get("text") is None else str(value.get("text")),
        "translation": "" if value.get("translation") is None else str(value.get("translation")),
        "image_prompt": trimmed(value.get("imagePrompt")),
        "image_ref": trimmed(value.get("imageRef")),
        "image_model_id": trimmed(value.get("imageModelId")),
        "attempts": to_int(value.get("attempts")),
        "failure_reason": trimmed(value.get("failureReason")),
        "audio_provider_id": trimmed(value.get("audioProviderId")),
        "audio_model_id": trimmed(value.get("audioModelId")),
        "audio_voice": trimmed(value.get("audioVoice")),
        "audio_segments": _assign_segments(value.get("audioSegments")),
    }


def _project_story_word(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "storyId": row["story"],
        "lexemeId": row["lexeme"],
        "position": to_int(row["word_order"]),
        "sourceText": row["source_text"],
        # An empty list is a real answer — the story did not manage to use this word — so it is
        # projected as `[]` and never as `None`.
        "forms": [str(one) for one in (row["forms"] or []) if str(one).strip()],
        "translationForms": [str(one) for one in (row["translation_forms"] or []) if str(one).strip()],
    }


def _assign_story_word(value: Mapping[str, Any]) -> dict[str, Any]:
    forms = value.get("forms")
    translation_forms = value.get("translationForms")
    return {
        "story": trimmed(value.get("storyId")),
        "lexeme": trimmed(value.get("lexemeId")),
        "word_order": to_int(value.get("position")),
        # Verbatim, for `loop_items.source_text`'s reason: this is the word the story was asked to
        # teach, and editing the lexeme afterwards must not rewrite what was asked.
        "source_text": "" if value.get("sourceText") is None else str(value.get("sourceText")),
        "forms": [str(one) for one in forms if str(one).strip()] if isinstance(forms, list) else [],
        "translation_forms": [str(one) for one in translation_forms if str(one).strip()]
        if isinstance(translation_forms, list) else [],
    }


COLLECTIONS: tuple[Collection, ...] = (
    Collection("vocabularies", tables.vocabularies, _project_vocabulary, _assign_vocabulary),
    Collection("topics", tables.topics, _project_topic, _assign_topic),
    Collection("lexemes", tables.lexemes, _project_lexeme, _assign_lexeme),
    Collection("senses", tables.senses, _project_sense, _assign_sense),
    Collection("attestations", tables.attestations, _project_attestation, _assign_attestation),
    Collection("examples", tables.examples, _project_example, _assign_example),
    Collection("imagePrompts", tables.image_prompts, _project_image_prompt, _assign_image_prompt),
    Collection("pronunciations", tables.pronunciations, _project_pronunciation, _assign_pronunciation),
    Collection("studyStates", tables.study_states, _project_study_state, _assign_study_state),
    Collection("loops", tables.loops, _project_loop, _assign_loop),
    Collection("loopItems", tables.loop_items, _project_loop_item, _assign_loop_item),
    Collection("loopCues", tables.loop_cues, _project_loop_cue, _assign_loop_cue),
    Collection("stories", tables.stories, _project_story, _assign_story),
    Collection("storyParts", tables.story_parts, _project_story_part, _assign_story_part),
    Collection("storyWords", tables.story_words, _project_story_word, _assign_story_word),
    Collection("beds", tables.beds, _project_bed, _assign_bed),
)

COLLECTION_BY_KEY = {collection.key: collection for collection in COLLECTIONS}
COLLECTION_BY_NAME = {collection.name: collection for collection in COLLECTIONS}

# Every word and its descendants, newest relation first. Vocabularies and topics are excluded: a
# reset discards the words, not the languages the owner studies or the topics they file them under.
# Loops and stories are included, despite hanging off no word: a loop whose every caption names a
# deleted word is a track nothing describes, and a story is one nothing asked for. That is what
# putting both last in `COLLECTIONS` buys.
WORD_COLLECTIONS: tuple[Collection, ...] = tuple(reversed(COLLECTIONS[2:]))


def sync_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ownerId": row["owner"],
        "deleted": bool(row["deleted"]),
        "createdAt": row["created_at"],
        "editedAt": row["edited_at"],
        "editedBy": row["edited_by"],
        "revision": to_int(row["revision"]),
    }


def projected(collection: Collection, row: Mapping[str, Any]) -> dict[str, Any]:
    value = collection.project(row)
    value["id"] = row["id"]
    value.update(sync_fields(row))
    return value
