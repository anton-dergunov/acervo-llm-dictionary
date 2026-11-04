"""Turning a saved word into clip examples, against a fake corpus and a stubbed provider.

The corpus is faked at the HTTP boundary and fed the same recorded response
`tests/unit/clips/fixtures/search-es-picar.json` holds, so the real client runs for real — what is
stubbed is the network and the provider, and only those.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from acervo.clips.ids import clip_example_id
from acervo.errors import ApiError
from acervo.services.clips import find_clips

from graph_records import attestation, example, lexeme, sense, vocabulary

DEVICE = "device000000001"
FIXTURE = Path(__file__).resolve().parents[1] / "clips" / "fixtures" / "search-es-picar.json"
SPEECH_URL = "http://speech-retrieval:8000/api/v1"

STATUS = {
    "ready": True, "built_at": "2026-09-11T16:32:14.295846+00:00",
    "indexed_languages": ["es"], "videos": 251, "segments": 60704,
}


def recorded() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class CorpusStub:
    """The retrieval service, answering over a real `httpx` call path.

    `search` and `status` are set per test; either may be an exception to raise or a
    `(status_code, payload)` pair, which is how a 400, a 503 and a dropped connection are told apart
    without any of them being special-cased in the code under test.
    """

    def __init__(self) -> None:
        self.status: object = STATUS
        self.search: object = recorded()
        self.calls: list[httpx.URL] = []

    def __call__(self, url, *, params=None, timeout=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        self.calls.append(request.url)
        answer = self.status if request.url.path.endswith("/status") else self.search
        if isinstance(answer, BaseException):
            raise answer
        status, payload = answer if isinstance(answer, tuple) else (200, answer)
        return httpx.Response(status, json=payload, request=request)


@pytest.fixture
def corpus(server, monkeypatch) -> CorpusStub:
    from acervo.clips import corpus as corpus_module

    stub = CorpusStub()
    monkeypatch.setattr(corpus_module.httpx, "get", stub)
    monkeypatch.setattr(server.settings, "speech_url", SPEECH_URL)
    return stub


def word(server, **overrides):
    """One word with two senses and the owner's own sentence, saved and ready to be searched."""
    entry = lexeme(headword="picar", lemma="picar", **overrides)
    itch = sense(entry["id"], definition="Causar picor o comezón.", order=0)
    chop = sense(entry["id"], definition="Cortar en trozos muy pequeños.", order=1)
    source = attestation(entry["id"])
    sentence = example(
        itch["id"], text=source["text"], translation=source["translation"], translationLang="en",
        origin="attestation", sourceAttestationId=source["id"], modelId=None,
    )
    answer = server.push({
        "vocabularies": [vocabulary()],
        "lexemes": [entry], "senses": [itch, chop],
        "attestations": [source], "examples": [sentence],
    })
    assert answer.status_code == 200, answer.json()
    return entry, itch, chop


def chooses(server, *pairs):
    server.model.selection = {"senses": [
        {"senseId": one["id"], "segmentId": segment,
         "translation": "It is going to start itching.", "matchedTranslationForm": "itching"}
        if segment else {"senseId": one["id"], "segmentId": None}
        for one, segment in pairs
    ]}


class Answered:
    """A service call, read the way these tests were written to read a route's answer.

    Searching for clips is a step of the `enrich` job now, not a route — but what it *does* is this
    service function, and what a refusal carries is an `ApiError`'s status and code.
    """

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> dict:
        return self.body


def find(server, entry):
    """One corpus search and one model call for one word, as the `clips` step makes them."""
    try:
        return Answered(200, {"data": find_clips(server.settings, server.owner, DEVICE, entry["id"])})
    except ApiError as refusal:
        return Answered(
            refusal.status, {"error": {"code": refusal.code, "message": refusal.message}}
        )


def segments():
    return [row["segment_id"] for row in recorded()["results"]]


def stored_lexeme(server, entry):
    held = server.pull().json()["data"]["changes"]["lexemes"]
    return next(row for row in held if row["id"] == entry["id"])


def stored_clips(server):
    held = server.pull().json()["data"]["changes"]["examples"]
    return [row for row in held if row["origin"] == "subtitle" and not row["deleted"]]


# ── the happy path ──────────────────────────────────────────────────────────


def test_one_search_and_one_model_call_cover_every_sense(server, corpus):
    entry, itch, chop = word(server)
    chooses(server, (itch, segments()[0]), (chop, None))
    answer = find(server, entry)

    assert answer.status_code == 200, answer.json()
    assert len(server.model.calls) == 1, "batching per lexeme is why the model can tell senses apart"
    assert [url.path for url in corpus.calls] == ["/api/v1/status", "/api/v1/search"]
    # The lemma, in the lexeme's language, unioned over surface and lemma matches.
    query = dict(corpus.calls[1].params)
    assert query["q"] == "picar" and query["language"] == "es" and query["match_mode"] == "auto"


def test_a_chosen_clip_becomes_an_example_carrying_the_segment_it_quotes(server, corpus):
    entry, itch, chop = word(server)
    chooses(server, (itch, segments()[0]), (chop, None))
    find(server, entry)

    clips = stored_clips(server)
    assert len(clips) == 1
    clip = clips[0]
    first = recorded()["results"][0]
    # Verbatim: the corpus segments, the model only selects.
    assert clip["text"] == first["sentence"]
    assert clip["clipRef"] == first["segment_id"]
    assert clip["videoRef"] == first["video"]["url"]
    assert clip["videoChannel"] == first["video"]["channel"]
    assert clip["videoTitle"] == first["video"]["title"]
    assert clip["videoStart"] <= first["clip_start"] and clip["videoEnd"] >= first["clip_end"]
    assert clip["matchedForm"] == "picar" and clip["matchedForm"] in clip["text"]
    assert clip["translation"] == "It is going to start itching."
    assert clip["translationLang"] == "en"
    assert clip["matchedTranslationForm"] == "itching"
    # Like every other example a model produced.
    assert clip["modelId"]


def test_the_id_is_derived_from_the_sense_and_the_segment(server, corpus):
    """The whole reason the interface's engine and the sweep need no coordination."""
    entry, itch, chop = word(server)
    chooses(server, (itch, segments()[0]), (chop, None))
    find(server, entry)
    assert stored_clips(server)[0]["id"] == clip_example_id(itch["id"], segments()[0])


def test_searching_twice_finds_the_row_rather_than_adding_one(server, corpus):
    entry, itch, chop = word(server)
    chooses(server, (itch, segments()[0]), (chop, None))
    find(server, entry)
    assert find(server, entry).status_code == 200
    assert len(stored_clips(server)) == 1


def test_two_senses_may_each_get_their_own_clip(server, corpus):
    entry, itch, chop = word(server)
    chooses(server, (itch, segments()[0]), (chop, segments()[1]))
    find(server, entry)
    assert {row["senseId"] for row in stored_clips(server)} == {itch["id"], chop["id"]}


# ── refusing, which is the common case ──────────────────────────────────────


def test_choosing_nothing_still_marks_the_word_searched(server, corpus):
    """A thin corpus produces articles with no clips. The sweep must not re-learn that nightly."""
    entry, itch, chop = word(server)
    chooses(server, (itch, None), (chop, None))
    answer = find(server, entry)

    assert answer.json()["data"]["examples"] == []
    assert stored_clips(server) == []
    assert stored_lexeme(server, entry)["clipsSearchedAt"]


def test_a_corpus_with_nothing_to_offer_costs_no_model_call(server, corpus):
    entry, _itch, _chop = word(server)
    corpus.search = {**recorded(), "results": [], "returned": 0}
    answer = find(server, entry)

    assert answer.status_code == 200
    assert server.model.calls == [], "no candidates is not a question worth asking a model"
    assert stored_lexeme(server, entry)["clipsSearchedAt"]


def test_an_id_the_request_never_offered_is_dropped_and_counted(server, corpus):
    """Dropping rather than refusing keeps the good selections; the count is what finds the bug."""
    entry, itch, chop = word(server)
    chooses(server, (itch, "seg_invented000000000"), (chop, segments()[1]))
    answer = find(server, entry)

    assert answer.json()["data"]["dropped"] == 1
    assert [row["senseId"] for row in stored_clips(server)] == [chop["id"]]


# ── when it is not marked ───────────────────────────────────────────────────


def test_an_unreachable_corpus_leaves_the_word_looking_untouched(server, corpus):
    """§2.8: the mark is written only on a successful consultation, so the sweep finds it later."""
    entry, _itch, _chop = word(server)
    corpus.status = httpx.ConnectError("no route to host")
    answer = find(server, entry)

    assert answer.status_code == 502
    assert answer.json()["error"]["code"] == "corpus_unreachable"
    assert stored_lexeme(server, entry)["clipsSearchedAt"] is None


def test_a_language_the_corpus_does_not_index_is_skipped_rather_than_marked(server, corpus):
    """It may be indexed later, and no rescan ships — so marking it would bury the word forever."""
    entry, _itch, _chop = word(server)
    corpus.status = {**STATUS, "indexed_languages": ["fr"]}
    answer = find(server, entry)

    assert answer.status_code == 200
    assert answer.json()["data"] == {
        "lexemeId": entry["id"], "searched": False, "skipped": "language_not_indexed",
        "examples": [], "dropped": 0, "usage": None,
    }
    assert stored_lexeme(server, entry)["clipsSearchedAt"] is None


def test_a_query_the_corpus_will_never_accept_is_marked_and_left_alone(server, corpus):
    """A 400 is the corpus answering. That word's query will not get shorter, so coming back to it
    would spend a search on the same refusal forever."""
    entry, _itch, _chop = word(server)
    corpus.search = (400, {"error": {"code": "invalid_request", "message": "up to five words"}})
    answer = find(server, entry)

    assert answer.status_code == 200
    assert answer.json()["data"]["skipped"] == "query_rejected"
    assert stored_lexeme(server, entry)["clipsSearchedAt"]


def test_a_provider_failure_writes_nothing_at_all(server, corpus):
    """A clip that could not be chosen fails in the same `llm_*` vocabulary as an entry that could
    not be written."""
    import litellm

    entry, _itch, _chop = word(server)
    server.model.error = litellm.RateLimitError(
        message="provider details", llm_provider="stub", model="gemini-2.5-flash"
    )
    answer = find(server, entry)

    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "llm_rate_limited"
    assert stored_clips(server) == []
    assert stored_lexeme(server, entry)["clipsSearchedAt"] is None


def test_an_unusable_reply_is_refused_without_marking(server, corpus):
    entry, _itch, _chop = word(server)
    server.model.selection = {"nonsense": True}
    answer = find(server, entry)

    assert answer.status_code == 502
    assert answer.json()["error"]["code"] == "llm_unusable"
    assert stored_lexeme(server, entry)["clipsSearchedAt"] is None


def test_a_deployment_with_no_corpus_says_so(server):
    entry, _itch, _chop = word(server)
    answer = find(server, entry)
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "corpus_unconfigured"


# ── scoping ─────────────────────────────────────────────────────────────────


def test_another_accounts_word_is_not_found(server, other, corpus):
    """One message for "no such word" and "somebody else's": telling them apart would answer
    whether an id exists in another account."""
    entry, _itch, _chop = word(server)
    answer = find(other, entry)
    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "not_found"


# ── settings ────────────────────────────────────────────────────────────────


def test_no_row_means_following_the_deployment_default(server, corpus):
    """The three-state doctrine `image_settings` and `model_selection` already live by."""
    answer = server.get("/clips/settings").json()["data"]
    assert answer["searchEnabled"] is True
    assert answer["chosen"] is False


def test_the_settings_never_ask_the_corpus(server, corpus):
    """The switches are Acervo's own and come back at once; the corpus is another service, asked
    only by the route that reports on it — so a slow corpus cannot hold the page up."""
    assert "corpus" not in server.get("/clips/settings").json()["data"]
    assert server.put("/clips/settings", {"searchEnabled": False}).status_code == 200
    assert not [url for url in corpus.calls if url.path.endswith("/status")]


def test_the_corpus_reading_says_what_it_holds(server, corpus):
    answer = server.get("/clips/corpus").json()["data"]
    assert answer["configured"] is True and answer["reachable"] is True
    assert answer["indexedLanguages"] == ["es"]


def test_the_passage_rule_is_off_by_default_and_reaches_the_prompt_when_on(server, corpus):
    """Off is the deliberate half: real speech is messy, and preserving that is what a clip is for.

    Asserted against the prompt the model was actually sent, because the two halves of this are a
    marked section in a tracked file and a keyword at a call site — far enough apart to drift.
    """
    entry, itch, chop = word(server)
    chooses(server, (itch, segments()[0]), (chop, None))

    assert server.get("/clips/settings").json()["data"]["selfContainedOnly"] is False
    find(server, entry)
    sent = server.model.calls[-1]["messages"][-1]["content"]
    assert "followed on its own" not in sent
    assert "<!--" not in sent, "the markers are not sent to the model either"

    server.put("/clips/settings", {"selfContainedOnly": True})
    find(server, entry)
    assert "followed on its own" in server.model.calls[-1]["messages"][-1]["content"]


def test_switching_save_time_searching_off_is_recorded(server, corpus):
    stored = server.put("/clips/settings", {"searchEnabled": False}).json()["data"]
    assert stored["searchEnabled"] is False and stored["chosen"] is True
    assert server.get("/clips/settings").json()["data"]["searchEnabled"] is False


def test_the_route_searches_even_with_save_time_searching_off(server, corpus):
    """The switch gates the sweep and the enrichment engine, not the button: you pressed it, so you
    meant it — which is how you get a word with no clips and then add the one you want by hand."""
    entry, itch, chop = word(server)
    server.put("/clips/settings", {"searchEnabled": False})
    chooses(server, (itch, segments()[0]), (chop, None))
    assert find(server, entry).status_code == 200
    assert len(stored_clips(server)) == 1


def test_settings_open_with_the_corpus_down(server, corpus, caplog):
    """A corpus that is down is a fact to show, not an error to raise — and the owner was shown it,
    so it is written down where `admin log --failed` will find it."""
    corpus.status = httpx.ConnectError("no route to host")
    with caplog.at_level("WARNING", logger="acervo.activity"):
        answer = server.get("/clips/corpus")
    assert answer.status_code == 200
    assert answer.json()["data"] == {"configured": True, "reachable": False, "error": "unreachable"}
    line = next(record.getMessage() for record in caplog.records if record.name == "acervo.activity")
    assert line.startswith("corpus unanswered") and "reason=unreachable" in line
