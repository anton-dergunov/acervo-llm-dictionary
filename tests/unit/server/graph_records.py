"""Wire-shaped records, so a test says what it is about rather than restating every field."""

from __future__ import annotations

from typing import Any

from acervo.domain.ids import new_record_id, now_instant

DEVICE = "device000000001"


def stamp(**overrides: Any) -> dict[str, Any]:
    at = now_instant()
    return {
        "deleted": False,
        "createdAt": at,
        "editedAt": at,
        "editedBy": DEVICE,
        "revision": 0,
        **overrides,
    }


def vocabulary(**overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "language": "es", "definitionLang": "es", "glossLangs": ["en"],
        "notesLang": "en", "displayName": "Spanish", "flag": "\U0001F1EA\U0001F1F8", "order": 0,
        **stamp(), **overrides,
    }


def topic(**overrides: Any) -> dict[str, Any]:
    return {"id": new_record_id(), "name": "Food", "icon": None, "order": 0, **stamp(), **overrides}


def lexeme(**overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "language": "es", "headword": "picar", "lemma": "picar",
        "reading": None, "ipa": None, "pos": "verb", "gender": None, "register": "neutral",
        "dialect": None, "emoji": None, "topicIds": [], "status": "inbox",
        "shortGloss": "to chop", "primaryGloss": None, "emotion": None, "notes": [],
        "clipsSearchedAt": None, **stamp(), **overrides,
    }


def sense(lexeme_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "lexemeId": lexeme_id, "definition": "Cortar en trozos.",
        "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["to chop"]}], "domain": None, "emoji": None,
        "order": 0, **stamp(), **overrides,
    }


def attestation(lexeme_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "lexemeId": lexeme_id, "text": "Pica la cebolla.",
        "translation": "Chop the onion.", "sourceUrl": None, "sourceTitle": None,
        "sourceKind": "conversation", "capturedAt": now_instant(), "photoRef": None,
        "photoRegion": None, **stamp(), **overrides,
    }


def example(sense_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "senseId": sense_id, "text": "Pica la cebolla.", "textLang": "es",
        "translation": None, "translationLang": None, "origin": "llm",
        "sourceAttestationId": None, "modelId": "stub-model", "videoRef": None, "videoTitle": None,
        "videoChannel": None, "videoStart": None, "videoEnd": None, "clipRef": None,
        "imageRef": None, "emotion": None, "note": None, "matchedForm": None,
        "matchedTranslationForm": None, **stamp(), **overrides,
    }


def image_prompt(lexeme_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "lexemeId": lexeme_id, "senseId": None, "prompt": "a chopped onion",
        "styleId": "flat", "seed": 7, "modelId": "stub-model", "promptVersion": "v1",
        "imageRef": None, "imageModelId": None, "exampleId": None, "attempts": 0,
        "failureReason": None, "suppressed": False, **stamp(), **overrides,
    }


def study_state(lexeme_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "lexemeId": lexeme_id, "senseId": None, "system": "anki", "noteId": None,
        "cardIds": [], "reps": 0, "lapses": 0, "stability": 0, "difficulty": 0,
        "retrievability": 0, "lastReview": None, "syncedAt": None, **stamp(), **overrides,
    }


def loop(**overrides: Any) -> dict[str, Any]:
    """A rendered loop. Pass `audioRef=None, audioMime=None` for one the job has not finished."""
    return {
        "id": new_record_id(), "language": "es", "styleId": "sunlit-acoustic", "seed": 104740,
        "engineVersion": "1.4.0", "bedFingerprint": "90c6ad267d159b0e", "pattern": "retrieval",
        "audioRef": "loops/es/90c6ad267d159b0e.mp3", "audioMime": "audio/mpeg",
        "durationSeconds": 124.5, "position": 0, **stamp(), **overrides,
    }


def loop_item(loop_id: str, lexeme_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_record_id(), "loopId": loop_id, "lexemeId": lexeme_id, "position": 0,
        "sourceText": "picar", "targetText": "to sting", "emotion": "wincing slightly",
        "startSeconds": 8.82, "sourceRevealSeconds": 8.82, "targetRevealSeconds": 17.65,
        "endSeconds": 44.12, **stamp(), **overrides,
    }
