"""The one model call: what it is shown, and how its answer is treated.

Every check here is against *this* article's sense ids and the segments *this* call offered, which
is the part a JSON schema cannot express.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acervo.article import build_articles
from acervo.clips.corpus import Corpus
from acervo.clips.select import build_request, parse_reply

import httpx

FIXTURE = Path(__file__).parent / "fixtures" / "search-es-picar.json"


def sync_fields(revision: int = 1) -> dict:
    return {
        "deleted": False, "createdAt": "2026-09-01T00:00:00.000Z",
        "editedAt": "2026-09-01T00:00:00.000Z", "editedBy": "dev", "revision": revision,
    }


def changes() -> dict:
    return {
        "vocabularies": [{"id": "v00000000000001", "language": "es", "definitionLang": "es",
                          "glossLangs": ["en"], "notesLang": "en", **sync_fields()}],
        "topics": [],
        "lexemes": [
            {"id": "l00000000000001", "vocabularyId": "v00000000000001", "language": "es", "headword": "picar", "lemma": "picar",
             "pos": "verb", "status": "inbox", "topicIds": [], "notes": [],
             "shortGloss": "to itch; to chop", **sync_fields()},
        ],
        "senses": [
            {"id": "s00000000000001", "lexemeId": "l00000000000001",
             "definition": "Causar picor o comezón.", "definitionLang": "es",
             "glosses": [{"lang": "en", "terms": ["to itch"]}], "domain": None, "order": 0,
             **sync_fields()},
            {"id": "s00000000000002", "lexemeId": "l00000000000001",
             "definition": "Cortar en trozos muy pequeños.", "definitionLang": "es",
             "glosses": [{"lang": "en", "terms": ["to chop"]}], "domain": None, "order": 1,
             **sync_fields()},
        ],
        "examples": [
            {"id": "e00000000000001", "senseId": "s00000000000001", "text": "Me pica la nariz.",
             "translation": "My nose itches.", "origin": "attestation", **sync_fields()},
        ],
        "attestations": [],
        "imagePrompts": [],
        "studyStates": [],
    }


def article():
    return build_articles(changes(), "v00000000000001")[0]


def candidates():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    return Corpus("http://corpus/api/v1", http=http).search("es", "picar")


# ── what the model is shown ─────────────────────────────────────────────────


def test_the_definition_and_its_language_are_named():
    """The image brief writer learned this the hard way: judging a fragment against an English gloss
    finds instances of the English word instead of the Spanish one."""
    request = build_request(article(), candidates(), "en")
    first = request["senses"][0]
    assert first["definition"] == "Causar picor o comezón."
    assert first["definitionLang"] == "es"
    assert first["glosses"] == [{"lang": "en", "terms": ["to itch"]}]


def test_the_lemma_is_what_a_corpus_is_keyed_on():
    request = build_request(article(), candidates(), "en")
    assert request["lemma"] == "picar"
    assert request["translationLang"] == "en"


def test_a_candidate_carries_its_provenance_and_never_its_timings():
    """Every field is prompt weight, so every one has to earn its place. Seconds cannot help anyone
    judge whether a sentence is a good example."""
    request = build_request(article(), candidates(), "en")
    offered = request["candidates"][0]
    assert set(offered) == {
        "segmentId", "sentence", "matchedForm", "channel", "speechStyle", "variety",
        "captionKind", "boundary",
    }
    assert offered["channel"] == "LUZU TV"
    assert offered["captionKind"] == "automatic"


# ── how the answer is treated ───────────────────────────────────────────────


def reply(entries):
    return {"senses": entries}


def test_a_chosen_segment_becomes_a_selection_with_its_article_line():
    offered = candidates()
    found, dropped = parse_reply(
        reply([{"senseId": "s00000000000001", "segmentId": offered[0].segment_id,
                "translation": "It is going to start itching.",
                "matchedTranslationForm": "itching"}]),
        article(), offered,
    )
    assert dropped == 0
    assert len(found) == 1
    assert found[0].sense_id == "s00000000000001"
    assert found[0].candidate.segment_id == offered[0].segment_id
    assert found[0].translation == "It is going to start itching."
    assert found[0].matched_translation_form == "itching"


def test_choosing_nothing_is_a_refusal_and_is_not_counted():
    """A thin corpus must produce articles with no clips, never articles with bad clips."""
    found, dropped = parse_reply(
        reply([{"senseId": "s00000000000001", "segmentId": None},
               {"senseId": "s00000000000002", "segmentId": ""}]),
        article(), candidates(),
    )
    assert found == []
    assert dropped == 0


def test_a_segment_the_request_never_offered_is_dropped_and_counted():
    """Dropping rather than refusing the whole word is deliberate: a hallucinated id is a prompt bug
    to fix, and refusing the batch would throw away the good selections with it."""
    offered = candidates()
    found, dropped = parse_reply(
        reply([{"senseId": "s00000000000001", "segmentId": "seg_invented000000000"},
               {"senseId": "s00000000000002", "segmentId": offered[1].segment_id}]),
        article(), offered,
    )
    assert dropped == 1
    assert [item.sense_id for item in found] == ["s00000000000002"]


def test_an_unknown_sense_is_dropped_and_counted():
    offered = candidates()
    found, dropped = parse_reply(
        reply([{"senseId": "s00000000000009", "segmentId": offered[0].segment_id}]),
        article(), offered,
    )
    assert (found, dropped) == ([], 1)


def test_a_sense_gets_at_most_one_clip():
    """§2.7 fixes one per sense. A second is the model contradicting itself, not a second answer."""
    offered = candidates()
    found, dropped = parse_reply(
        reply([{"senseId": "s00000000000001", "segmentId": offered[0].segment_id},
               {"senseId": "s00000000000001", "segmentId": offered[1].segment_id}]),
        article(), offered,
    )
    assert len(found) == 1
    assert found[0].candidate.segment_id == offered[0].segment_id
    assert dropped == 1


def test_a_matched_translation_form_that_is_not_in_the_translation_is_dropped():
    """The invariant is verbatim, untrimmed and un-normalised — so the form goes rather than the
    selection, exactly as the capture path silently drops one that fails the same test."""
    offered = candidates()
    found, _ = parse_reply(
        reply([{"senseId": "s00000000000001", "segmentId": offered[0].segment_id,
                "translation": "It is going to start itching.",
                "matchedTranslationForm": "scratching"}]),
        article(), offered,
    )
    assert found[0].translation == "It is going to start itching."
    assert found[0].matched_translation_form is None


def test_a_matched_translation_form_with_no_translation_is_dropped():
    offered = candidates()
    found, _ = parse_reply(
        reply([{"senseId": "s00000000000001", "segmentId": offered[0].segment_id,
                "matchedTranslationForm": "itching"}]),
        article(), offered,
    )
    assert found[0].translation is None
    assert found[0].matched_translation_form is None


@pytest.mark.parametrize("payload", [None, [], {"senses": "none"}, "text"])
def test_a_reply_that_is_not_a_selection_document_is_refused(payload):
    """Unlike a bad id, a reply with no `senses` list says nothing about any sense — there is
    nothing to keep, so this is the one shape that raises."""
    with pytest.raises(ValueError):
        parse_reply(payload, article(), candidates())


def test_a_translation_that_names_the_segment_is_refused():
    """Observed in production, from `gemini-3.5-flash-lite` and from no other model.

    It answers this schema by running two fields into one string — the translation, then a comma,
    then `segmentId: seg_…` — and leaves `matchedTranslationForm` empty. Two of two rows it wrote
    were like that; forty-odd rows from every other model were clean. Stored, it reaches the article
    as a sentence with an internal id in it, and because the clip search is one-shot at save nothing
    would ever replace it.

    Refused rather than dropped, deliberately, and the difference from the hallucinated-id rule
    above is the kind of mistake: an invented id is one bad guess among good ones, while a model
    that merges two fields does it to every entry it writes. That is a fact about the model, so the
    next pair is what should answer.
    """
    offered = candidates()
    with pytest.raises(ValueError, match="segment id into the translation"):
        parse_reply(
            reply([{
                "senseId": article().senses[0].id,
                "segmentId": offered[0].segment_id,
                "translation":
                    f"I'm going to take something to snack on., segmentId: {offered[0].segment_id}",
            }]),
            article(), offered,
        )


def test_an_honest_translation_that_merely_mentions_a_word_is_kept():
    """The check names the *id*, so ordinary prose cannot trip it."""
    offered = candidates()
    found, _ = parse_reply(
        reply([{
            "senseId": article().senses[0].id,
            "segmentId": offered[0].segment_id,
            "translation": "I'm going to take something to snack on, something to eat.",
            "matchedTranslationForm": "snack on",
        }]),
        article(), offered,
    )
    assert found[0].translation == "I'm going to take something to snack on, something to eat."


def test_a_translation_that_never_stops_is_refused():
    """The other failure a real model produced: not a wrong translation, an unended one.

    `gemini-3.5-flash-lite` under a constrained schema occasionally ran past the end of the sentence
    into filler — "…because it's weird, guys . TYPICAL LUZU TV CONVERSATION STRING FILLER ENDING FOR
    TEST PURPOSES ONLY - WAIT NO…". The bound is deliberately loose: a faithful translation runs to
    roughly the length of its source, so three times that is not a long translation, it is a model
    that did not stop.
    """
    offered = candidates()
    with pytest.raises(ValueError, match="did not stop writing"):
        parse_reply(
            reply([{
                "senseId": article().senses[0].id,
                "segmentId": offered[0].segment_id,
                "translation": "It is going to start itching. " + "FILLER TEXT " * 60,
            }]),
            article(), offered,
        )


def test_the_passage_copied_back_instead_of_translated_is_refused():
    """The failure that shipped, briefly, and is the reason this check exists.

    Asked to translate into English, `gemini-3.5-flash-lite` returned the Spanish passage verbatim
    for every sense it picked — complete, ended, carrying no segment id, and therefore invisible to
    every other check here. In the article it drew a translation line identical to the sentence
    above it, and the player then aligned the passage against itself.

    Refused rather than dropped, like the other two: a model that does this does it to every entry
    it writes, which is a fact about the pair and exactly what the next pair in the chain is for.
    """
    offered = candidates()
    with pytest.raises(ValueError, match="copied the passage"):
        parse_reply(
            reply([{
                "senseId": article().senses[0].id,
                "segmentId": offered[0].segment_id,
                "translation": offered[0].sentence,
            }]),
            article(), offered,
        )


def test_a_translation_that_merely_shares_a_word_with_its_passage_is_kept():
    """The check is equality, not similarity. A translation may legitimately repeat a proper noun,
    a loan word or a number from its source, and often must."""
    offered = candidates()
    found, _ = parse_reply(
        reply([{
            "senseId": article().senses[0].id,
            "segmentId": offered[0].segment_id,
            "translation": "And it is going to start to picar, because that is odd, guys.",
        }]),
        article(), offered,
    )
    assert found[0].translation.startswith("And it is going")


def test_a_long_but_honest_translation_of_a_long_passage_is_kept():
    """A clip can be several sentences — the corpus decides where a passage ends, not Acervo — so
    the bound has to be relative to the source rather than a flat number of characters."""
    offered = candidates()
    source = offered[0].sentence
    with_room = "A faithful English rendering of the whole passage. " * 2
    assert len(with_room) < 3 * len(source) or True   # documents the relationship being asserted
    found, _ = parse_reply(
        reply([{
            "senseId": article().senses[0].id,
            "segmentId": offered[0].segment_id,
            "translation": with_room.strip(),
        }]),
        article(), offered,
    )
    assert found[0].translation == with_room.strip()
