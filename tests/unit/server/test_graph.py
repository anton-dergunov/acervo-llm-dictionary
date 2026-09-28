"""The replication core.

Each rule below has real semantics and is something a reasonable re-derivation gets subtly wrong.
"""

from __future__ import annotations

import re

import pytest
from graph_records import (
    DEVICE,
    attestation,
    example,
    image_prompt,
    lexeme,
    sense,
    study_state,
    topic,
    vocabulary,
)

from acervo.domain.ids import now_instant
from acervo.domain import SCHEMA_VERSION


def stored(server, key, index=0):
    """One record as the server currently holds it, so a test never hardcodes a revision."""
    return server.pull().json()["data"]["changes"][key][index]


def article(**lexeme_overrides):
    """One word with a sense, an attestation, and the example drawn from it."""
    word = lexeme(**lexeme_overrides)
    meaning = sense(word["id"])
    source = attestation(word["id"])
    drawn = example(
        meaning["id"],
        text=source["text"],
        translation=source["translation"],
        translationLang="en",
        origin="attestation",
        sourceAttestationId=source["id"],
        modelId=None,
    )
    return {
        "lexemes": [word],
        "senses": [meaning],
        "attestations": [source],
        "examples": [drawn],
    }, word, meaning, source, drawn


# ── the batch, and the order it lands in ────────────────────────────────────


def test_a_whole_article_lands_in_one_batch_because_relations_resolve_in_order(server):
    """Topics before lexemes, lexemes before senses and attestations, those before examples."""
    subject = topic()
    changes, word, meaning, source, drawn = article(topicIds=[subject["id"]])
    changes["vocabularies"] = [vocabulary()]
    changes["topics"] = [subject]

    answer = server.push(changes)
    assert answer.status_code == 200
    records = answer.json()["data"]["records"]
    assert [record["revision"] for record in records["lexemes"]] == [3]
    assert records["examples"][0]["sourceAttestationId"] == source["id"]


def test_every_written_record_takes_the_next_revision_from_one_counter_per_owner(server):
    """Never a per-table sequence: a record left at revision zero is invisible to every pull,
    permanently and silently."""
    changes, *_ = article()
    body = server.push(changes).json()["data"]
    revisions = sorted(record["revision"] for group in body["records"].values() for record in group)
    assert revisions == [1, 2, 3, 4]
    assert body["cursor"] == 4
    assert all(revision > 0 for revision in revisions)


def test_a_pull_returns_records_in_revision_order_and_a_delta_only_carries_what_changed(server):
    changes, word, *_ = article()
    server.push(changes)
    everything = server.pull().json()["data"]
    assert [record["revision"] for record in everything["changes"]["senses"]] == [2]

    server.push({"lexemes": [{**word, "revision": stored(server, "lexemes")["revision"], "shortGloss": "to mince"}]})
    delta = server.pull(since=4).json()["data"]
    assert [record["shortGloss"] for record in delta["changes"]["lexemes"]] == ["to mince"]
    assert delta["changes"]["senses"] == []


def test_a_tombstone_is_carried_to_the_client_rather_than_hidden_from_it(server):
    changes, word, *_ = article()
    server.push(changes)
    server.push({"lexemes": [{**word, "revision": stored(server, "lexemes")["revision"], "deleted": True}]})
    pulled = server.pull().json()["data"]["changes"]["lexemes"]
    assert [record["deleted"] for record in pulled] == [True]


# ── optimistic concurrency ──────────────────────────────────────────────────


def test_an_edit_from_a_stale_revision_is_refused_rather_than_merged(server):
    changes, word, *_ = article()
    server.push(changes)
    answer = server.push({"lexemes": [{**word, "revision": 0, "shortGloss": "stale"}]})
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "stale_record"


def test_an_unknown_id_at_a_non_zero_revision_is_stale_too(server):
    """Nothing is ever hard-deleted, so this means the client's cursor belongs to another database."""
    answer = server.push({"lexemes": [lexeme(revision=7)]})
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "stale_record"


def test_one_bad_record_refuses_the_whole_batch(server):
    """A save is one article, and half an article is worse than none."""
    good = topic()
    answer = server.push({"topics": [good], "lexemes": [lexeme(pos="preposition")]})
    assert answer.status_code == 400
    assert server.pull().json()["data"]["changes"]["topics"] == []


def test_an_id_another_owner_holds_is_a_conflict_rather_than_an_overwrite(server, other):
    """It takes a second lookup, and skipping it is a silent cross-owner write."""
    theirs = topic()
    assert other.push({"topics": [theirs]}).status_code == 200
    answer = server.push({"topics": [{**theirs, "name": "Mine now"}]})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "id_conflict"


# ── ids, timestamps and the dataset ─────────────────────────────────────────


@pytest.mark.parametrize("bad", ["short", "UPPERCASE12345", "sixteencharacter", "with-a-dash-12"])
def test_a_record_id_must_be_fifteen_lowercase_letters_or_digits(server, bad):
    answer = server.push({"topics": [{**topic(), "id": bad}]})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] in {"invalid_input", "invalid_record"}


def test_wire_timestamps_are_exactly_twenty_four_characters(server):
    changes, *_ = article()
    server.push(changes)
    pulled = server.pull().json()["data"]
    shape = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    assert shape.match(pulled["serverTime"])
    for group in pulled["changes"].values():
        for record in group:
            assert shape.match(record["createdAt"]), record
            assert shape.match(record["editedAt"]), record


@pytest.mark.parametrize("field", ["createdAt", "editedAt"])
def test_a_timestamp_without_milliseconds_is_refused(server, field):
    answer = server.push({"topics": [{**topic(), field: "2026-01-01T00:00:00Z"}]})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "invalid_input"


def test_created_at_is_set_once_and_never_moved_by_a_later_edit(server):
    subject = topic()
    server.push({"topics": [subject]})
    later = now_instant()
    server.push({"topics": [{**subject, "revision": 1, "createdAt": later, "name": "Renamed"}]})
    stored = server.pull().json()["data"]["changes"]["topics"][0]
    assert stored["createdAt"] == subject["createdAt"]
    assert stored["name"] == "Renamed"


def test_the_dataset_id_is_stable_per_owner_and_different_between_owners(server, other):
    """Rebuild the database and every outstanding client cursor is invalidated, which is the only
    thing that stops a client asking for revisions the new database has not reached."""
    mine = server.pull().json()["data"]["datasetId"]
    assert server.pull().json()["data"]["datasetId"] == mine
    assert re.match(r"^[a-z0-9]{15}$", mine)
    assert other.pull().json()["data"]["datasetId"] != mine


def test_the_editing_device_is_recorded_from_the_request_not_from_the_record(server):
    answer = server.push({"topics": [{**topic(), "editedBy": "somebodyelse"}]}, device="phone000000001")
    assert answer.json()["data"]["records"]["topics"][0]["editedBy"] == "phone000000001"


@pytest.mark.parametrize("bad", ["", "NOTLOWERCASE", "a" * 33, "has a space"])
def test_a_write_needs_a_valid_device_identifier(server, bad):
    answer = server.post("/graph", {"schemaVersion": SCHEMA_VERSION, "deviceId": bad, "changes": {}})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "invalid_input"


# ── the per-collection rules ────────────────────────────────────────────────


def test_a_chinese_lexeme_needs_a_reading_on_a_prefix_test(server):
    """`zh-Hant-TW` and `zho` both match, so narrowing this to equality lets an unreadable entry in."""
    server.push({"vocabularies": [vocabulary(language="zh-Hans", definitionLang="en")]})
    for language in ("zh", "zh-Hans", "zh-Hant-TW", "zho"):
        refused = server.push({"lexemes": [lexeme(language=language, reading=None)]})
        assert refused.status_code == 400, language
        assert "reading" in refused.json()["error"]["message"]
    assert server.push({"lexemes": [lexeme(language="zh-Hant-TW", reading="chī")]}).status_code == 200


def test_a_marked_form_must_occur_verbatim_in_the_text_it_marks(server):
    """Untrimmed, uncased, un-normalised. Capture drops a form that fails this exact test, so
    loosening it breaks the drop and tightening it turns a good capture into a refusal."""
    changes, word, meaning, source, drawn = article()
    server.push(changes)
    revision = stored(server, "examples")["revision"]
    for bad in ("pica", "PICA", "cebolla?"):
        answer = server.push({"examples": [{**drawn, "revision": revision, "matchedForm": bad}]})
        assert answer.status_code == 400, bad
    assert server.push(
        {"examples": [{**drawn, "revision": revision, "matchedForm": "Pica"}]}
    ).status_code == 200


def test_a_marked_translation_form_must_occur_in_the_translation(server):
    changes, word, meaning, source, drawn = article()
    server.push(changes)
    revision = stored(server, "examples")["revision"]
    refused = server.push({"examples": [{**drawn, "revision": revision, "matchedTranslationForm": "slice"}]})
    assert refused.status_code == 400
    accepted = server.push({"examples": [{**drawn, "revision": revision, "matchedTranslationForm": "Chop"}]})
    assert accepted.status_code == 200


def test_a_translation_and_its_language_are_required_together(server):
    changes, word, meaning, *_ = article()
    server.push(changes)
    only_text = example(meaning["id"], translation="Chop the onion.", translationLang=None)
    only_language = example(meaning["id"], translation=None, translationLang="en")
    assert server.push({"examples": [only_text]}).status_code == 400
    assert server.push({"examples": [only_language]}).status_code == 400


def test_a_rendering_model_without_a_rendered_image_is_refused(server):
    """One direction, not both — and the direction matters.

    A model id with nothing rendered is a record of nothing. A picture with no model is the owner
    having attached their own file, which is how provenance is modelled everywhere else here: an
    example the learner wrote carries no `modelId` either, and nothing anywhere carries a
    "the user supplied this" flag.
    """
    changes, word, *_ = article()
    server.push(changes)
    assert server.push(
        {"imagePrompts": [image_prompt(word["id"], imageRef=None, imageModelId="imagen")]}
    ).status_code == 400
    assert server.push(
        {"imagePrompts": [image_prompt(word["id"], imageRef="images/a.webp", imageModelId="imagen")]}
    ).status_code == 200


def test_a_picture_the_owner_attached_needs_no_brief_and_no_model(server):
    changes, word, *_ = article()
    server.push(changes)
    assert server.push({"imagePrompts": [image_prompt(
        word["id"], prompt="", styleId="", modelId="", promptVersion="",
        imageRef="images/a.webp", imageModelId=None,
    )]}).status_code == 200


def test_half_a_brief_is_refused_because_it_reproduces_nothing(server):
    """`compose()` needs the style to rebuild the prompt that was sent, and `promptVersion` is what
    says which template and style table produced it."""
    changes, word, *_ = article()
    server.push(changes)
    assert server.push({"imagePrompts": [image_prompt(
        word["id"], prompt="a chopped onion", styleId="", promptVersion="demo-v1"
    )]}).status_code == 400
    assert server.push({"imagePrompts": [image_prompt(
        word["id"], prompt="a chopped onion", styleId="oil-painting", promptVersion=""
    )]}).status_code == 400


CLIP_FIELDS = ("videoTitle", "videoChannel", "videoStart", "videoEnd", "clipRef")


def test_every_clip_field_needs_a_video_reference_and_none_is_shown_without_one(server):
    """Two mechanisms for one invariant: the validator refuses it in, the projection refuses it out."""
    changes, word, meaning, *_ = article()
    server.push(changes)
    for field, value in [
        ("videoTitle", "A cooking show"),
        ("videoChannel", "Easy Spanish"),
        ("videoStart", 42),
        ("videoEnd", 48),
        ("clipRef", "seg_1f4c9a2b7e6d5c3a0b91"),
    ]:
        refused = server.push({"examples": [example(meaning["id"], videoRef=None, **{field: value})]})
        assert refused.status_code == 400, field

    with_clip = example(
        meaning["id"], videoRef="corpus/show.mp4", videoTitle="A cooking show",
        videoChannel="Easy Spanish", videoStart=42, videoEnd=48, clipRef="seg_1f4c9a2b7e6d5c3a0b91",
    )
    written = server.push({"examples": [with_clip]}).json()["data"]["records"]["examples"][0]
    assert [written[field] for field in CLIP_FIELDS] == [
        "A cooking show", "Easy Spanish", 42, 48, "seg_1f4c9a2b7e6d5c3a0b91"
    ]

    # Clearing the reference means clearing what depended on it; the validator says so.
    orphaned = server.push({"examples": [{**with_clip, "revision": written["revision"], "videoRef": None}]})
    assert orphaned.status_code == 400
    cleared = server.push(
        {"examples": [{
            **with_clip, "revision": written["revision"],
            **{field: None for field in ("videoRef", *CLIP_FIELDS)},
        }]}
    ).json()["data"]["records"]["examples"][0]
    assert all(cleared[field] is None for field in CLIP_FIELDS)


def test_a_clip_must_end_after_it_starts(server):
    """An end at or before the start describes no passage at all, and the corpus never produces one."""
    changes, word, meaning, *_ = article()
    server.push(changes)
    for start, end in [(42, 42), (48, 42)]:
        refused = server.push({"examples": [
            example(meaning["id"], videoRef="corpus/show.mp4", videoStart=start, videoEnd=end)
        ]})
        assert refused.status_code == 400, (start, end)

    # An absent end is written as zero, which is "no end" rather than an end at the beginning.
    written = server.push({"examples": [
        example(meaning["id"], videoRef="corpus/show.mp4", videoStart=42)
    ]}).json()["data"]["records"]["examples"][0]
    assert written["videoEnd"] == 0


def test_a_clip_search_is_marked_with_an_instant_and_nothing_else(server):
    """`clipsSearchedAt` answers both "never consulted" and "consulted before the corpus grew", so it
    is a date rather than a flag — and a lexeme starts without one, which is what the sweep finds."""
    changes, word, *_ = article()
    written = server.push(changes).json()["data"]["records"]["lexemes"][0]
    assert written["clipsSearchedAt"] is None

    refused = server.push({"lexemes": [
        {**word, "revision": written["revision"], "clipsSearchedAt": "yesterday"}
    ]})
    assert refused.status_code == 400

    marked = server.push({"lexemes": [
        {**word, "revision": written["revision"], "clipsSearchedAt": "2026-09-11T00:22:14.069Z"}
    ]}).json()["data"]["records"]["lexemes"][0]
    assert marked["clipsSearchedAt"] == "2026-09-11T00:22:14.069Z"


def test_a_clip_title_left_behind_by_another_writer_is_still_not_shown():
    """The second half of the same invariant, and the half a route test cannot reach: the validator
    makes this row unwritable through the graph, so only the projection can refuse it."""
    from acervo.domain.projection import COLLECTION_BY_KEY, projected

    row = {
        "id": "aaaaaaaaaaaaaaa", "owner": "bbbbbbbbbbbbbbb", "sense": "ccccccccccccccc",
        "text": "Pica la cebolla.", "text_lang": "es", "translation": "", "translation_lang": "",
        "origin": "llm", "source_attestation": None, "model_id": "", "video_ref": "",
        "video_title": "A cooking show", "video_channel": "Easy Spanish", "video_start": 42,
        "video_end": 48, "clip_ref": "seg_1f4c9a2b7e6d5c3a0b91", "image_ref": "", "emotion": "",
        "note": "", "matched_form": "", "matched_translation_form": "",
        "deleted": False, "created_at": "2026-01-01T00:00:00.000Z",
        "edited_at": "2026-01-01T00:00:00.000Z", "edited_by": "job00000000001", "revision": 1,
    }
    shown = projected(COLLECTION_BY_KEY["examples"], row)
    assert shown["videoRef"] is None
    assert all(shown[field] is None for field in CLIP_FIELDS)


def test_an_attestation_example_needs_a_source_that_shares_the_owner_and_the_lexeme(server, other):
    """A two-hop join: the right owner but the wrong word must not pass."""
    changes, word, meaning, source, drawn = article()
    server.push(changes)

    assert server.push(
        {"examples": [example(meaning["id"], origin="attestation", sourceAttestationId=None)]}
    ).status_code == 400

    second_word = lexeme(headword="cortar", lemma="cortar")
    elsewhere = attestation(second_word["id"], text="Corta el pan.")
    server.push({"lexemes": [second_word], "attestations": [elsewhere]})
    wrong_word = server.push(
        {
            "examples": [
                example(
                    meaning["id"],
                    text=elsewhere["text"],
                    origin="attestation",
                    sourceAttestationId=elsewhere["id"],
                )
            ]
        }
    )
    assert wrong_word.status_code == 400
    assert "same lexeme" in wrong_word.json()["error"]["message"]


def test_a_sense_keeps_its_label_and_its_own_emoji(server):
    changes, word, *_ = article()
    labelled = sense(word["id"], domain="theater", emoji="\U0001F3AD")
    changes["senses"] = [labelled]
    changes["examples"] = []
    assert server.push(changes).status_code == 200
    pulled = next(row for row in server.pull().json()["data"]["changes"]["senses"] if row["id"] == labelled["id"])
    assert pulled["domain"] == "theater"
    assert pulled["emoji"] == "\U0001F3AD"
    # An example no longer carries an approval nothing ever set.
    assert all("approved" not in row for row in server.pull().json()["data"]["changes"]["examples"])


def test_a_sense_belonging_to_another_owners_lexeme_is_refused(server, other):
    changes, word, *_ = article()
    server.push(changes)
    answer = other.push({"senses": [sense(word["id"])]})
    assert answer.status_code == 400
    assert "does not exist" in answer.json()["error"]["message"] or "same owner" in answer.json()[
        "error"
    ]["message"]


def test_a_lexeme_referencing_another_owners_topic_is_refused(server, other):
    theirs = topic()
    other.push({"topics": [theirs]})
    answer = server.push({"lexemes": [lexeme(topicIds=[theirs["id"]])]})
    assert answer.status_code == 400
    assert "same owner" in answer.json()["error"]["message"]


def test_a_sense_needs_at_least_one_gloss_with_at_least_one_term(server):
    changes, word, *_ = article()
    server.push(changes)
    assert server.push({"senses": [sense(word["id"], glosses=[])]}).status_code == 400
    assert server.push(
        {"senses": [sense(word["id"], glosses=[{"lang": "en", "terms": []}])]}
    ).status_code == 400
    assert server.push(
        {"senses": [sense(word["id"], glosses=[{"lang": "en", "terms": ["a"]}, {"lang": "en", "terms": ["b"]}])]}
    ).status_code == 400


def test_a_vocabulary_needs_at_least_one_gloss_language(server):
    assert server.push({"vocabularies": [vocabulary(glossLangs=[])]}).status_code == 400
    assert server.push({"vocabularies": [vocabulary(glossLangs=["en", "en"])]}).status_code == 400
    assert server.push({"vocabularies": [vocabulary(language="not a tag")]}).status_code == 400


def test_two_vocabularies_for_one_language_are_not_refused_by_the_server(server):
    """Uniqueness is forbidden on a replicated collection: it is exactly the constraint two offline
    devices can each satisfy on their own. The client refuses a duplicate at graph level instead."""
    assert server.push({"vocabularies": [vocabulary()]}).status_code == 200
    assert server.push({"vocabularies": [vocabulary()]}).status_code == 200


def test_study_state_card_ids_must_be_non_negative_integers(server):
    changes, word, *_ = article()
    server.push(changes)
    assert server.push({"studyStates": [study_state(word["id"], cardIds=[-1])]}).status_code == 400
    assert server.push({"studyStates": [study_state(word["id"], cardIds=["7"])]}).status_code == 400
    assert server.push({"studyStates": [study_state(word["id"], cardIds=[7, 9])]}).status_code == 200


def test_a_study_state_note_of_zero_reads_back_as_no_note(server):
    """Alone among the numbers: there is no Anki note 0, so a stored zero means "not pushed yet"."""
    changes, word, *_ = article()
    server.push(changes)
    written = server.push({"studyStates": [study_state(word["id"], noteId=0)]})
    assert written.json()["data"]["records"]["studyStates"][0]["noteId"] is None
    numbered = server.push({"studyStates": [study_state(word["id"], noteId=1234)]})
    assert numbered.json()["data"]["records"]["studyStates"][0]["noteId"] == 1234


def test_a_study_state_may_name_a_sense_of_its_own_word_only(server):
    changes, word, meaning, *_ = article()
    other, *_ = article()
    server.push(changes)
    server.push(other)
    foreign = other["senses"][0]["id"]
    assert server.push({"studyStates": [study_state(word["id"], senseId=foreign)]}).status_code == 400
    written = server.push({"studyStates": [study_state(word["id"], senseId=meaning["id"])]})
    assert written.status_code == 200
    assert written.json()["data"]["records"]["studyStates"][0]["senseId"] == meaning["id"]
    whole = server.push({"studyStates": [study_state(word["id"])]})
    assert whole.json()["data"]["records"]["studyStates"][0]["senseId"] is None


# ── the reset ───────────────────────────────────────────────────────────────


def test_the_reset_tombstones_words_and_descendants_and_keeps_languages_and_topics(server):
    subject = topic()
    changes, word, meaning, source, drawn = article(topicIds=[subject["id"]])
    changes["vocabularies"] = [vocabulary()]
    changes["topics"] = [subject]
    server.push(changes)
    server.push({"imagePrompts": [image_prompt(word["id"])], "studyStates": [study_state(word["id"])]})

    before = server.pull().json()["data"]["datasetId"]
    answer = server.post(
        "/graph/reset", {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "confirm": "delete-all-words"}
    )
    assert answer.status_code == 200
    assert answer.json()["data"]["deleted"] == 6
    assert answer.json()["data"]["datasetId"] == before

    remaining = server.pull().json()["data"]["changes"]
    assert [record["deleted"] for record in remaining["vocabularies"]] == [False]
    assert [record["deleted"] for record in remaining["topics"]] == [False]
    for key in ("lexemes", "senses", "attestations", "examples", "imagePrompts", "studyStates"):
        assert all(record["deleted"] for record in remaining[key]), key


def test_a_second_reset_finds_nothing_left_to_tombstone(server):
    changes, *_ = article()
    server.push(changes)
    body = {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "confirm": "delete-all-words"}
    assert server.post("/graph/reset", body).json()["data"]["deleted"] == 4
    assert server.post("/graph/reset", body).json()["data"]["deleted"] == 0


def test_the_reset_needs_its_confirmation_token(server):
    for confirm in ("", "yes", "delete all words"):
        answer = server.post(
            "/graph/reset", {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "confirm": confirm}
        )
        assert answer.status_code == 400
        assert answer.json()["error"]["code"] == "confirmation_required"


def test_an_edit_never_rewrites_a_records_key(server):
    """With foreign keys on, SQLite reads `SET id = <the same id>` as a key change and scans every
    child index for rows that pointed at the old one — seven for a lexeme, the whole of
    `image_prompts` for an example — so an edit's cost grew with the database rather than the edit."""
    from sqlalchemy import event

    from acervo.repository.session import engine

    changes, word, meaning, source, drawn = article()
    server.push(changes)
    updates: list[str] = []

    def capture(_conn, _cursor, statement, *_rest):
        if statement.lstrip().upper().startswith("UPDATE") and "sync_state" not in statement:
            updates.append(statement)

    event.listen(engine(), "before_cursor_execute", capture)
    try:
        held = server.pull().json()["data"]["changes"]
        answer = server.push({
            key: [{**held[key][0], "editedAt": now_instant()}]
            for key in ("lexemes", "senses", "attestations", "examples")
        })
    finally:
        event.remove(engine(), "before_cursor_execute", capture)
    assert answer.status_code == 200, answer.json()
    assert len(updates) == 4
    for statement in updates:
        assigned = statement.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
        assert not re.search(r"\b(id|owner)\s*=", assigned), statement
