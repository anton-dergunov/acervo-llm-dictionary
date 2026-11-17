"""Turning the model's answer into an ArticleDraft.

The exact shape `web/src/yaml.ts` reads, so the review surface renders a generated entry through the
same serialiser as a stored one. Ids are minted here rather than left absent, because an example has
to name the attestation it was drawn from and both are created by the same save.

This is the highest-risk block in the whole capture path. Every guard below is deliberate.
"""

from __future__ import annotations

from typing import Any

from acervo.domain.ids import new_record_id, now_instant
from acervo.domain.validation import (
    GENDER_VALUES,
    POS_VALUES,
    REGISTER_VALUES,
    SOURCE_KIND_VALUES,
)
from acervo.errors import ApiError
from acervo.mandarin_ipa import mandarin_ipa
from acervo.models import journal
from acervo.pinyin import is_mandarin
from acervo.services.capture.coerce import (
    language_or_none,
    pick_choice,
    pick_optional_choice,
    text_list,
    trimmed,
)


EMOTION_LIMIT = 300


def emotion_of(value: Any) -> str | None:
    """A delivery direction, one line, cut at a word boundary rather than refused.

    The prompt asks for a dozen words or so and the validator allows three hundred characters; a
    model that wrote a paragraph has still said something usable, and refusing the whole draft over
    how the sentence should *sound* would throw the article away with it.
    """
    text = " ".join(trimmed(value).split())
    if not text:
        return None
    if len(text) <= EMOTION_LIMIT:
        return text
    cut = text[:EMOTION_LIMIT].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut or text[:EMOTION_LIMIT]


def usable_senses(answer: dict[str, Any]) -> list[dict[str, Any]]:
    """The senses a draft is built from: objects with a definition. Anything else is skipped."""
    return [
        raw for raw in answer.get("senses") or []
        if isinstance(raw, dict) and trimmed(raw.get("definition"))
    ]


def refusal_of(answer: Any, resolution: dict[str, Any]) -> ApiError | None:
    """Why this answer cannot become a draft at all, or `None` when it can.

    One place for the three conditions, read twice: by `draft_from`, and by compose's check inside
    the chain (`vet.py`), which passes the model over so the next pair answers. Two copies would let
    the check accept what the draft then refuses, which is the terminal refusal this exists to avoid.
    """
    if not isinstance(answer, dict):
        return ApiError(
            502, "llm_unusable", "The language model did not return an entry, so nothing was created."
        )
    if not usable_senses(answer):
        return ApiError(
            502, "llm_unusable", "The language model returned an entry with no meanings, so nothing was created."
        )
    # Chinese records are refused without a reading. Saying which field is missing beats letting the
    # save fail later with a validation message about a field nobody was shown.
    if resolution["language"].lower().startswith("zh") and not trimmed(answer.get("reading")):
        return ApiError(
            502,
            "llm_unusable",
            "The language model returned a Chinese entry with no reading, so nothing was created.",
        )
    return None


def _from_sentence(claimed: Any, attestations: list[dict[str, Any]]) -> dict[str, Any] | None:
    # `Number(null)` is 0, so a plain numeric read here would take "I invented this" for "this is
    # sentence 0" and quietly credit the learner with every example the model wrote.
    if claimed is None or claimed == "":
        return None
    if isinstance(claimed, bool) or not isinstance(claimed, (int, float)):
        return None
    if claimed != int(claimed):
        return None
    index = int(claimed)
    if index < 0 or index >= len(attestations):
        return None
    return attestations[index]


def draft_from(
    answer: dict[str, Any],
    resolution: dict[str, Any],
    request: dict[str, Any],
    vocabulary: dict[str, Any],
    topics: list[dict[str, Any]],
    model_id: str,
) -> dict[str, Any]:
    refused = refusal_of(answer, resolution)
    if refused is not None:
        raise refused
    captured_at = now_instant()
    topic_names = {topic["name"].lower(): topic["name"] for topic in topics}

    source_url = trimmed(request.get("sourceUrl")) or None
    source = {
        "sourceUrl": source_url,
        "sourceTitle": trimmed(request.get("sourceTitle")) or None,
        "sourceKind": pick_choice(
            request.get("sourceKind"), SOURCE_KIND_VALUES, "web" if source_url else "unknown"
        ),
        "capturedAt": captured_at,
    }
    attestations = [
        {
            "id": new_record_id(),
            "text": sentence["text"],
            "translation": sentence["translation"],
            **source,
            "photoRef": None,
            "photoRegion": None,
        }
        for sentence in resolution["sentences"]
    ]
    # Examples may be drawn only from what the learner actually wrote or read, never from a photo
    # that carried no sentence.
    sentences = list(attestations)
    photo = trimmed(request.get("photoRef")) or None
    if photo:
        region = request.get("photoRegion") if isinstance(request.get("photoRegion"), dict) else None
        if attestations:
            # The photo is where the sentence was read, so it goes with the sentence.
            attestations[0].update(photoRef=photo, photoRegion=region)
        else:
            # A street sign has no sentence: the photo is kept by itself, as the place it was met.
            attestations.append({
                "id": new_record_id(), "text": "", "translation": None, **source,
                "photoRef": photo, "photoRegion": region,
            })

    gloss_langs = vocabulary["glossLangs"]
    senses: list[dict[str, Any]] = []
    for raw in usable_senses(answer):
        definition = trimmed(raw.get("definition"))

        glosses: list[dict[str, Any]] = []
        seen: set[str] = set()
        for gloss in raw.get("glosses") or []:
            if not isinstance(gloss, dict):
                continue
            lang = language_or_none(gloss.get("lang"))
            terms = text_list(gloss.get("terms"))
            if not lang or not terms or lang in seen:
                continue
            seen.add(lang)
            glosses.append({"lang": lang, "terms": terms})
        # A sense without a gloss is refused by the record validator, so rather than lose the sense,
        # fall back to the headword in the language the learner asked to be glossed into.
        if not glosses:
            glosses.append({"lang": gloss_langs[0] if gloss_langs else "en", "terms": [resolution["headword"]]})

        examples: list[dict[str, Any]] = []
        for example in raw.get("examples") or []:
            if not isinstance(example, dict):
                continue
            text = trimmed(example.get("text"))
            if not text:
                continue
            translation = trimmed(example.get("translation")) or None
            attestation = _from_sentence(example.get("fromSentence"), sentences)
            matched_form = trimmed(example.get("matchedForm")) or None
            matched_translation = trimmed(example.get("matchedTranslationForm")) or None
            examples.append(
                {
                    "id": new_record_id(),
                    "text": text,
                    "textLang": resolution["language"],
                    "translation": translation,
                    "translationLang": (gloss_langs[0] if gloss_langs else "en") if translation else None,
                    # What makes an example the learner's own rather than the model's, and what the
                    # Obsidian export reads to mark it as such. A generated one carries the model
                    # that wrote it instead.
                    "origin": "attestation" if attestation else "llm",
                    "sourceAttestationId": attestation["id"] if attestation else None,
                    "modelId": None if attestation else model_id,
                    # Capture never consults the spoken-usage corpus (spoken-clips §2.5): the
                    # article is written first and real speech is looked for afterwards.
                    "videoRef": None,
                    "videoTitle": None,
                    "videoChannel": None,
                    "videoStart": None,
                    "videoEnd": None,
                    "clipRef": None,
                    "imageRef": None,
                    "emotion": emotion_of(example.get("emotion")),
                    "note": trimmed(example.get("note")) or None,
                    # The validator requires these to occur verbatim in the text they mark. A model
                    # that retypes an inflected form instead of copying it would otherwise refuse the
                    # whole batch.
                    "matchedForm": matched_form if matched_form and matched_form in text else None,
                    "matchedTranslationForm": matched_translation
                    if matched_translation and translation and matched_translation in translation
                    else None,
                }
            )

        senses.append(
            {
                "id": new_record_id(),
                "order": len(senses),
                "definition": definition,
                "definitionLang": language_or_none(raw.get("definitionLang")) or vocabulary["definitionLang"],
                "glosses": glosses,
                "domain": trimmed(raw.get("domain")) or None,
                "emoji": trimmed(raw.get("emoji"))[:32] or None,
                "examples": examples,
                "images": [],
            }
        )

    reading = trimmed(answer.get("reading")) or None
    ipa = trimmed(answer.get("ipa")) or None
    if is_mandarin(resolution["language"]):
        # Derived from the reading, never the model's: Pinyin is phonemic, so a table is as right as
        # the reading and always in one notation (articles.md, "Readings"). A reading that does not
        # cut into syllables leaves the field empty rather than guessed.
        ipa = mandarin_ipa(reading or "")
        if ipa is None:
            journal.outcome("compose", failed=True, ipa="unparsed", model=model_id, reading=reading,
                            reason="the reading is not Pinyin syllables, so the word has no IPA")

    return {
        "id": None,
        "language": resolution["language"],
        "headword": trimmed(answer.get("headword")) or resolution["headword"],
        "lemma": trimmed(answer.get("lemma")) or resolution["lemma"],
        "reading": reading,
        "ipa": ipa,
        "pos": pick_choice(answer.get("pos"), POS_VALUES, resolution["pos"]),
        "gender": pick_optional_choice(answer.get("gender"), GENDER_VALUES),
        "register": pick_optional_choice(answer.get("register"), REGISTER_VALUES),
        "dialect": language_or_none(answer.get("dialect")),
        "emoji": trimmed(answer.get("emoji"))[:32] or None,
        # Only topics this owner actually holds. `saveArticle` refuses an unknown name, and inventing
        # one here would turn a good entry into an error the learner has to decode.
        "topics": [
            topic_names[name.lower()] for name in text_list(answer.get("topics")) if name.lower() in topic_names
        ],
        # A draft is a proposal a person reads before saving, so saving it files an ordinary word. The
        # Inbox is for what arrived without anyone reading it, which the headless save decides.
        "status": "active",
        "shortGloss": trimmed(answer.get("shortGloss")) or None,
        # The one term a loop speaks, and how the word itself sounds. Both are optional by design:
        # a word the writer left without a `primaryGloss` is simply not eligible for a loop, and
        # nothing backfills it (plan §2.17).
        "primaryGloss": trimmed(answer.get("primaryGloss")) or None,
        "emotion": trimmed(answer.get("emotion")) or None,
        "notes": text_list(answer.get("notes")),
        "senses": senses,
        "attestations": attestations,
        "images": [],
    }
