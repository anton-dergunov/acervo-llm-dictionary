"""`POST /articles`: a parsed document in, one atomic write out.

Ported from the device's `saveArticle` suite when the diff moved to the server
(`docs/architecture/jobs.md`). A document is the `ArticleDraft` `web/src/yaml.ts` parses into; the
tests build one from the stored records the way that parser would, then edit it the way a person
editing YAML would.
"""

from __future__ import annotations

import copy

import pytest

from acervo.clips.ids import clip_example_id
from acervo.domain import SCHEMA_VERSION
from acervo.images.ids import image_prompt_id
from acervo.pronunciation.ids import pronunciation_id
from acervo.repository import jobs

from graph_records import (
    DEVICE, example, image_prompt, lexeme, sense, stamp, study_state, topic, vocabulary,
)

LEXEME = "lexeme000000001"
SENSE = "sense0000000001"
EXAMPLE = "example00000001"
TOPIC = "topic0000000001"


def save(server, draft, minted=(), **extra):
    return server.post("/articles", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "draft": draft,
        "minted": list(minted), **extra,
    })


def saved(server, draft, minted=(), **extra):
    answer = save(server, draft, minted, **extra)
    assert answer.status_code == 200, answer.json()
    return answer.json()["data"]


def held(server, key, *, deleted=False):
    rows = server.pull().json()["data"]["changes"][key]
    return rows if deleted else [row for row in rows if not row["deleted"]]


def one(server, key, identifier):
    return next(row for row in held(server, key, deleted=True) if row["id"] == identifier)


@pytest.fixture
def seeded(server):
    """One stored entry, ready to be edited through its document."""
    answer = server.push({
        "vocabularies": [vocabulary()],
        "topics": [topic(id=TOPIC, name="Health")],
        "lexemes": [lexeme(id=LEXEME, headword="desmayarse", lemma="desmayarse", emoji="😵",
                           topicIds=[TOPIC], status="active", shortGloss=None)],
        "senses": [sense(LEXEME, id=SENSE, definition="Perder el conocimiento.",
                         glosses=[{"lang": "en", "terms": ["to faint"]}])],
        "examples": [example(SENSE, id=EXAMPLE, text="Me desmayé.", translation="I fainted.",
                             translationLang="en", origin="manual", modelId=None)],
    })
    assert answer.status_code == 200, answer.json()
    # The seed is not what these tests are about.
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])
    return server


def draft_of(server, lexeme_id=LEXEME):
    """What `parseArticle(yamlFor(article))` yields for a stored entry."""
    word = one(server, "lexemes", lexeme_id)
    topics = {row["id"]: row["name"] for row in held(server, "topics")}
    senses = sorted(
        (row for row in held(server, "senses") if row["lexemeId"] == lexeme_id),
        key=lambda row: (row["order"], row["id"]),
    )
    examples = held(server, "examples")
    prompts = held(server, "imagePrompts")
    image = lambda row: {key: row[key] for key in (  # noqa: E731
        "id", "exampleId", "prompt", "styleId", "seed", "modelId", "promptVersion", "imageRef",
        "imageModelId")}
    return {
        "id": word["id"],
        **{key: word[key] for key in (
            "language", "headword", "lemma", "reading", "ipa", "pos", "gender", "register",
            "dialect", "emoji", "status", "shortGloss", "notes")},
        "topics": [topics[identifier] for identifier in word["topicIds"]],
        "senses": [{
            **{key: row[key] for key in (
                "id", "order", "definition", "definitionLang", "glosses", "domain", "emoji")},
            "examples": [
                {key: value for key, value in item.items()
                 if key not in ("senseId", "ownerId", "deleted", "createdAt", "editedAt",
                                "editedBy", "revision")}
                for item in examples if item["senseId"] == row["id"]
            ],
            "images": [image(item) for item in prompts if item["senseId"] == row["id"]],
        } for row in senses],
        "attestations": [
            {key: item[key] for key in (
                "id", "text", "translation", "sourceUrl", "sourceTitle", "sourceKind", "capturedAt")}
            for item in held(server, "attestations") if item["lexemeId"] == lexeme_id
        ],
        "images": [image(item) for item in prompts
                   if item["lexemeId"] == lexeme_id and not item["senseId"]],
    }


def new_sense(**overrides):
    return {
        "id": None, "order": 1, "definition": "Sentir una emoción intensa.", "definitionLang": "es",
        "glosses": [{"lang": "en", "terms": ["to swoon"]}], "domain": None, "emoji": None,
        "examples": [], "images": [], **overrides,
    }


def new_example(**overrides):
    record = example(SENSE, **overrides)
    for key in ("senseId", "deleted", "createdAt", "editedAt", "editedBy", "revision"):
        record.pop(key)
    return {**record, "id": overrides.get("id")}


# ── the diff ────────────────────────────────────────────────────────────────


def test_an_update_a_creation_and_a_removal_are_one_write(seeded):
    article = draft_of(seeded)
    article["emoji"] = "🫠"
    article["senses"][0]["examples"][0]["id"] = None  # replaced rather than edited
    article["senses"].append(new_sense())
    cursor = seeded.pull().json()["data"]["cursor"]

    data = saved(seeded, article)

    assert data["lexemeId"] == LEXEME
    assert one(seeded, "lexemes", LEXEME)["emoji"] == "🫠"
    assert len([row for row in held(seeded, "senses") if row["lexemeId"] == LEXEME]) == 2
    # The example whose id was dropped is replaced: a new row, and the old one tombstoned.
    assert one(seeded, "examples", EXAMPLE)["deleted"] is True
    assert len(held(seeded, "examples")) == 1
    # One write: every record it touched was numbered in the same batch, past the old cursor.
    assert data["records"]["lexemes"][0]["revision"] > cursor
    assert data["cursor"] >= max(
        row["revision"] for rows in data["records"].values() for row in rows
    )


def test_every_id_it_was_given_is_kept_so_nothing_is_recreated(seeded):
    created = one(seeded, "lexemes", LEXEME)["createdAt"]
    article = draft_of(seeded)
    article["headword"] = "desvanecerse"
    saved(seeded, article)

    assert [row["id"] for row in held(seeded, "lexemes", deleted=True)] == [LEXEME]
    assert [row["id"] for row in held(seeded, "senses", deleted=True)] == [SENSE]
    assert [row["id"] for row in held(seeded, "examples", deleted=True)] == [EXAMPLE]
    # The Anki join and the image seed hang off these, and provenance off createdAt.
    assert one(seeded, "lexemes", LEXEME)["createdAt"] == created
    assert one(seeded, "lexemes", LEXEME)["headword"] == "desvanecerse"


def test_a_clip_examples_id_is_derived_from_its_sense_and_segment(seeded):
    article = draft_of(seeded)
    article["senses"][0]["examples"].append(new_example(
        text="Se desmayó en pleno directo.", translation="She passed out live on air.",
        translationLang="en", origin="subtitle", modelId=None,
        videoRef="https://youtu.be/od_YtGbRC48", videoTitle="Informe semanal",
        videoChannel="DW Español", videoStart=252, videoEnd=258,
        clipRef="seg_4b1c7d2e9a350f68cd41",
    ))
    saved(seeded, article)
    clips = [row for row in held(seeded, "examples") if row["origin"] == "subtitle"]
    assert [row["id"] for row in clips] == [clip_example_id(SENSE, "seg_4b1c7d2e9a350f68cd41")]

    # Saving the same document again is the second writer: it finds the row, it does not add one.
    again = draft_of(seeded)
    for item in again["senses"][0]["examples"]:
        if item["origin"] == "subtitle":
            item["id"] = None
    saved(seeded, again)
    assert len([row for row in held(seeded, "examples") if row["origin"] == "subtitle"]) == 1


def test_a_removed_sense_carries_its_examples_away(seeded):
    article = draft_of(seeded)
    article["senses"].append(new_sense(examples=[new_example(text="Casi me desmayo.", origin="manual",
                                                              modelId=None)]))
    saved(seeded, article)

    trimmed = draft_of(seeded)
    trimmed["senses"] = [item for item in trimmed["senses"] if item["id"] != SENSE]
    saved(seeded, trimmed)

    assert one(seeded, "senses", SENSE)["deleted"] is True
    assert one(seeded, "examples", EXAMPLE)["deleted"] is True
    assert len(held(seeded, "examples")) == 1


def test_a_removed_sense_takes_its_study_state_and_leaves_the_words(seeded):
    article = draft_of(seeded)
    article["senses"].append(new_sense())
    saved(seeded, article)
    meaning = study_state(LEXEME, senseId=SENSE)
    word = study_state(LEXEME)
    assert seeded.push({"studyStates": [meaning, word]}).status_code == 200

    trimmed = draft_of(seeded)
    trimmed["senses"] = [item for item in trimmed["senses"] if item["id"] != SENSE]
    saved(seeded, trimmed)

    assert one(seeded, "studyStates", meaning["id"])["deleted"] is True
    assert one(seeded, "studyStates", word["id"])["deleted"] is False


def test_an_example_moved_to_another_sense_keeps_its_id(seeded):
    article = draft_of(seeded)
    article["senses"].append(new_sense())
    saved(seeded, article)

    moved = draft_of(seeded)
    first, second = moved["senses"]
    second["examples"], first["examples"] = first["examples"], []
    saved(seeded, moved)

    stored = one(seeded, "examples", EXAMPLE)
    assert stored["deleted"] is False
    assert stored["senseId"] == second["id"]


def test_a_document_with_no_ids_creates_a_whole_entry(seeded):
    data = saved(seeded, {
        "id": None, "language": "es", "headword": "sobremesa", "lemma": "sobremesa",
        "reading": None, "ipa": None, "pos": "noun", "gender": "feminine", "register": None,
        "dialect": None, "emoji": None, "topics": ["health"], "status": "active",
        "shortGloss": None, "notes": [], "images": [], "attestations": [],
        "senses": [new_sense(order=0, definition="Charla tras la comida.",
                             examples=[new_example(text="La sobremesa duró dos horas.",
                                                   origin="manual", modelId=None)])],
    })
    created = one(seeded, "lexemes", data["lexemeId"])
    assert created["headword"] == "sobremesa"
    # Topics are named case-insensitively, as a rail label is read.
    assert created["topicIds"] == [TOPIC]
    assert created["clipsSearchedAt"] is None


def test_a_generated_document_creates_the_ids_it_minted(seeded):
    """What capture proposes: an example naming an attestation that this same save creates."""
    data = saved(seeded, {
        "id": None, "language": "es", "headword": "el garfio", "lemma": "garfio", "reading": None,
        "ipa": None, "pos": "noun", "gender": "masculine", "register": "neutral", "dialect": None,
        "emoji": "🪝", "topics": ["Health"], "status": "inbox", "shortGloss": "hook", "notes": [],
        "images": [],
        "senses": [new_sense(id="sense0000000091", order=0, definition="Gancho de metal curvo.",
                             examples=[new_example(
                                 id="example00000091", text="Viene con un garfio.",
                                 translation="It comes with a hook.", translationLang="en",
                                 origin="attestation", sourceAttestationId="attest000000091",
                                 modelId=None)])],
        "attestations": [{
            "id": "attest000000091", "text": "Viene con un garfio.", "translation": None,
            "sourceUrl": None, "sourceTitle": None, "sourceKind": "unknown",
            "capturedAt": "2026-08-29T12:00:00.000Z",
        }],
    })
    assert one(seeded, "senses", "sense0000000091")["lexemeId"] == data["lexemeId"]
    assert one(seeded, "attestations", "attest000000091")["lexemeId"] == data["lexemeId"]
    assert one(seeded, "examples", "example00000091")["sourceAttestationId"] == "attest000000091"


def test_an_unknown_id_is_refused_when_the_document_edits_a_stored_entry(seeded):
    article = draft_of(seeded)
    article["senses"][0]["id"] = "sense0000000099"
    answer = save(seeded, article)
    assert answer.status_code == 400
    assert "not in your vocabulary" in answer.json()["error"]["message"]


def test_an_id_the_caller_says_it_minted_is_created(seeded):
    """The one exception, and it is an argument rather than anything in the document."""
    article = draft_of(seeded)
    article["attestations"].append({
        "id": "attest000000077", "text": "Se desmayó en el metro.",
        "translation": "He fainted on the metro.", "sourceUrl": None, "sourceTitle": "Radio",
        "sourceKind": "video", "capturedAt": "2026-08-28T12:00:00.000Z",
    })
    article["senses"][0]["examples"].append(new_example(
        text="Se desmayó en el metro.", translation="He fainted on the metro.",
        translationLang="en", origin="attestation", sourceAttestationId="attest000000077",
        modelId=None,
    ))
    saved(seeded, article, minted=["attest000000077"])
    assert one(seeded, "attestations", "attest000000077")["lexemeId"] == LEXEME
    assert any(row["sourceAttestationId"] == "attest000000077" for row in held(seeded, "examples"))


def test_the_same_document_is_refused_when_nothing_says_the_id_was_minted(seeded):
    article = draft_of(seeded)
    article["attestations"].append({
        "id": "attest000000078", "text": "Se desmayó en el metro.", "translation": None,
        "sourceUrl": None, "sourceTitle": None, "sourceKind": "unknown",
        "capturedAt": "2026-08-28T12:00:00.000Z",
    })
    answer = save(seeded, article)
    assert answer.status_code == 400
    assert "not in your vocabulary" in answer.json()["error"]["message"]


def test_an_unknown_topic_is_refused_and_the_known_ones_named(seeded):
    article = draft_of(seeded)
    article["topics"] = ["Cooking"]
    answer = save(seeded, article)
    assert answer.status_code == 400
    error = answer.json()["error"]
    assert error["code"] == "unknown_topic"
    assert 'There is no topic called "Cooking"' in error["message"]
    assert "Health" in error["message"]


def test_an_id_belonging_to_another_entry_is_refused_rather_than_stolen(seeded):
    assert seeded.push({"lexemes": [lexeme(id="lexeme000000002", headword="mareo")]}).status_code == 200
    article = draft_of(seeded)
    article["id"] = "lexeme000000002"
    answer = save(seeded, article)
    assert answer.status_code == 400
    assert "belongs to a different entry" in answer.json()["error"]["message"]


def test_a_document_naming_a_missing_or_deleted_entry_is_refused(seeded):
    article = draft_of(seeded)
    article["id"] = "lexeme000000099"
    assert save(seeded, article).status_code == 400

    stored = one(seeded, "lexemes", LEXEME)
    assert seeded.push({"lexemes": [{**stored, "deleted": True}]}).status_code == 200
    answer = save(seeded, draft_of(seeded))
    assert answer.status_code == 400
    assert "not in your vocabulary" in answer.json()["error"]["message"]


def test_somebody_elses_record_is_never_reached(seeded, other):
    article = draft_of(seeded)
    article["id"] = None
    # A new entry may carry ids it minted — but not one another account holds.
    answer = save(other, {**article, "topics": []})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "id_conflict"


def base_of(server, lexeme_id=LEXEME):
    """What a device's replica holds of one entry: every record, at the revision it holds it."""
    senses = {row["id"] for row in held(server, "senses", deleted=True) if row["lexemeId"] == lexeme_id}
    records = [
        *[row for row in held(server, "lexemes", deleted=True) if row["id"] == lexeme_id],
        *[row for row in held(server, "senses", deleted=True) if row["lexemeId"] == lexeme_id],
        *[row for row in held(server, "examples", deleted=True) if row["senseId"] in senses],
        *[row for key in ("attestations", "imagePrompts", "pronunciations")
          for row in held(server, key, deleted=True) if row["lexemeId"] == lexeme_id],
    ]
    return {row["id"]: row["revision"] for row in records}


def test_a_document_edited_from_a_stale_replica_is_refused_and_nothing_changes(seeded):
    article, base = draft_of(seeded), base_of(seeded)
    elsewhere = draft_of(seeded)
    elsewhere["headword"] = "desvanecerse"
    saved(seeded, elsewhere, base=base_of(seeded))

    article["headword"] = "marearse"
    cursor = seeded.pull().json()["data"]["cursor"]
    answer = save(seeded, article, base=base)
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "stale_record"
    assert seeded.pull().json()["data"]["cursor"] == cursor
    assert one(seeded, "lexemes", LEXEME)["headword"] == "desvanecerse"


def test_a_sense_the_author_had_not_seen_is_left_alone(seeded):
    """Added on another device and not yet pulled here: the document could not have mentioned it,
    so leaving it out is not asking for it to go."""
    article, base = draft_of(seeded), base_of(seeded)
    assert seeded.push({"senses": [sense(LEXEME, id="sense0000000002", order=1)]}).status_code == 200
    # The other device's write moved nothing this document names, so its save still lands.
    article["emoji"] = "🫠"
    saved(seeded, article, base=base)
    assert one(seeded, "senses", "sense0000000002")["deleted"] is False
    assert one(seeded, "lexemes", LEXEME)["emoji"] == "🫠"


# ── what a document cannot assert ───────────────────────────────────────────


def test_a_pictures_server_state_is_carried_through_an_edit(seeded):
    prompt_id = image_prompt_id(SENSE)
    assert seeded.push({"imagePrompts": [image_prompt(
        LEXEME, id=prompt_id, senseId=SENSE, attempts=3, failureReason="declined",
        suppressed=True, styleId="oil-painting",
    )]}).status_code == 200

    article = draft_of(seeded)
    article["senses"][0]["images"][0]["prompt"] = "a different scene"
    saved(seeded, article)

    stored = one(seeded, "imagePrompts", prompt_id)
    assert stored["prompt"] == "a different scene"
    assert (stored["attempts"], stored["failureReason"], stored["suppressed"]) == (3, "declined", True)


def test_a_new_picture_row_takes_the_id_derived_from_its_sense(seeded):
    article = draft_of(seeded)
    article["senses"][0]["images"].append({
        "id": None, "exampleId": None, "prompt": "a scene", "styleId": "oil-painting", "seed": 1,
        "modelId": "stub-model", "promptVersion": "v1", "imageRef": None, "imageModelId": None,
    })
    saved(seeded, article)
    assert [row["id"] for row in held(seeded, "imagePrompts")] == [image_prompt_id(SENSE)]


def test_the_clip_search_mark_survives_an_edit(seeded):
    stored = one(seeded, "lexemes", LEXEME)
    marked = "2026-09-01T10:00:00.000Z"
    assert seeded.push({"lexemes": [{**stored, "clipsSearchedAt": marked}]}).status_code == 200
    article = draft_of(seeded)
    article["headword"] = "desvanecerse"
    saved(seeded, article)
    assert one(seeded, "lexemes", LEXEME)["clipsSearchedAt"] == marked


def test_a_recording_of_a_removed_example_goes_with_it_and_the_headwords_stays(seeded):
    rows = [
        {"id": pronunciation_id(kind, identifier), "lexemeId": LEXEME, "targetKind": kind,
         "targetId": identifier, "text": text, "lang": "es", "audioRef": f"audio/{identifier}.ogg",
         "audioMime": "audio/ogg", "providerId": "google-tts", "modelId": "wavenet",
         "voice": None, "emotion": None, **stamp()}
        for kind, identifier, text in (
            ("lexeme", LEXEME, "desmayarse"), ("example", EXAMPLE, "Me desmayé."))
    ]
    answer = seeded.push({"pronunciations": rows})
    assert answer.status_code == 200, answer.json()

    article = draft_of(seeded)
    article["senses"][0]["examples"] = []
    article["headword"] = "desvanecerse"
    saved(seeded, article)

    assert one(seeded, "pronunciations", pronunciation_id("example", EXAMPLE))["deleted"] is True
    assert one(seeded, "pronunciations", pronunciation_id("lexeme", LEXEME))["deleted"] is False


# ── enrichment ──────────────────────────────────────────────────────────────


def test_a_new_entry_answers_with_the_job_that_enriches_it(seeded):
    article = draft_of(seeded)
    article = {**article, "id": None, "senses": [new_sense(order=0)], "attestations": []}
    data = saved(seeded, article)
    job = jobs.get(seeded.owner, data["jobId"])
    assert (job["kind"], job["subject"]["id"], job["trigger"]) == ("enrich", data["lexemeId"], "save")


def test_an_added_sense_asks_again_and_an_edit_does_not(seeded):
    edited = draft_of(seeded)
    edited["headword"] = "desvanecerse"
    assert saved(seeded, edited)["jobId"] is None

    grown = draft_of(seeded)
    grown["senses"].append(new_sense())
    assert saved(seeded, grown)["jobId"] is not None


def test_a_writer_that_will_ask_later_queues_nothing(seeded):
    article = {**draft_of(seeded), "id": None, "senses": [new_sense(order=0)], "attestations": []}
    data = saved(seeded, article, enrich=False)
    assert data["jobId"] is None
    assert jobs.open_jobs(seeded.owner) == []


# ── the request ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("draft", [None, [], "headword: picar", {"senses": "none"}])
def test_a_body_that_is_not_a_document_is_refused(seeded, draft):
    answer = save(seeded, draft)
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "invalid_input"


def test_the_route_needs_an_account_and_a_current_schema(seeded):
    assert seeded.client.post("/api/acervo/v1/articles", json={}).status_code == 401
    answer = seeded.post("/articles", {"schemaVersion": 1, "deviceId": DEVICE, "draft": {}})
    assert answer.json()["error"]["code"] == "schema_version_mismatch"


def test_a_refused_document_writes_nothing_at_all(seeded):
    cursor = seeded.pull().json()["data"]["cursor"]
    article = draft_of(seeded)
    article["headword"] = "desvanecerse"
    article["senses"][0]["glosses"] = []  # refused by the record validator
    answer = save(seeded, copy.deepcopy(article))
    assert answer.status_code == 400
    assert seeded.pull().json()["data"]["cursor"] == cursor
    assert one(seeded, "lexemes", LEXEME)["headword"] == "desmayarse"
