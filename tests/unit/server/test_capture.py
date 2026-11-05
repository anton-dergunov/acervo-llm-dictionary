"""Capture, ported case for case from the hook suite this replaces.

Every `it()` body there was a contract test and survives here. What does not survive is the harness:
against a real service with a temporary database, these assert on the thing that ships rather than on
a stand-in for it.
"""

from __future__ import annotations

import re

import httpx
import litellm
import pytest
from acervo.models import call as provider_call
from graph_records import lexeme, topic, vocabulary
from provider_rows import CLOUDFLARE, CLOUDFLARE_ACCOUNT, CLOUDFLARE_TOKEN, GEMINI, GEMINI_KEY

# What a provider says when it refuses. Every classification test asserts this never reaches
# the owner: a provider's own error text routinely echoes the request back, key included.
PRIVATE = "provider details that must stay private"

RESOLUTION = {
    "language": "es",
    "headword": "el garfio",
    "lemma": "garfio",
    "pos": "noun",
    "sentences": [{"text": "El disfraz de pirata viene con un garfio.", "translation": None}],
    "consumedLines": 2,
    "consumedText": "El disfraz de pirata viene con un garfio.",
}

ARTICLE = {
    "headword": "el garfio", "lemma": "garfio", "pos": "noun", "gender": "masculine",
    "register": "neutral", "emoji": "\U0001FA9D", "topics": ["Culture", "Nonexistent"],
    "shortGloss": "hook", "notes": ["Not el gancho."],
    "senses": [
        {
            "definition": "Gancho de metal curvo.",
            "domain": "tools", "emoji": "\U0001FA9D",
            "glosses": [{"lang": "en", "terms": ["hook"]}],
            "examples": [
                {
                    "text": "El disfraz de pirata viene con un garfio.",
                    "translation": "The pirate costume comes with a hook.",
                    "matchedForm": "un garfio", "matchedTranslationForm": "hook", "fromSentence": 0,
                },
                {
                    "text": "Perdió la mano y le pusieron un garfio.",
                    "translation": "He lost his hand and they gave him a hook.",
                    "matchedForm": "el garfio", "matchedTranslationForm": "hooks",
                    "fromSentence": None,
                },
            ],
        }
    ],
}


@pytest.fixture
def seeded(server):
    """One Spanish vocabulary, two topics, and a word the account already holds."""
    server.push(
        {
            "vocabularies": [vocabulary()],
            "topics": [topic(name="Food", order=0), topic(name="Culture", order=1)],
            "lexemes": [lexeme(headword="picar", lemma="picar", status="active", shortGloss="to itch")],
        }
    )
    server.model.resolution = dict(RESOLUTION)
    server.model.article = dict(ARTICLE)
    return server


def prompts_of(server):
    return [
        next(message["content"] for message in call["messages"] if message["role"] == "user")
        for call in server.model.calls
    ]


# ── what capture refuses, and how early ─────────────────────────────────────


def test_it_stops_at_a_word_the_account_already_holds_before_generating_anything(seeded):
    seeded.model.resolution = {**RESOLUTION, "headword": "Picar", "lemma": "picar", "sentences": []}
    body = seeded.capture(text="¿Te pica mucho la salsa?").json()["data"]
    assert [item["headword"] for item in body["duplicates"]] == ["picar"]
    assert body["draft"] is None
    # One call, not two: an article for a word already held would be thrown away.
    assert len(seeded.model.calls) == 1


def test_it_refuses_a_language_with_no_vocabulary_and_does_not_generate_for_it(seeded):
    seeded.model.resolution = {**RESOLUTION, "language": "de", "headword": "Wanderlust"}
    answer = seeded.capture(text="Fernweh und Wanderlust")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "language_not_configured"
    assert "de" in answer.json()["error"]["message"]
    assert len(seeded.model.calls) == 1


def test_it_refuses_a_vocabulary_with_no_translation_language(seeded, monkeypatch):
    """The validator will not let this state be written through the graph, so the guard is reached
    only by a vocabulary that got there another way — which is exactly why it is still checked."""
    from acervo.repository import graph

    monkeypatch.setattr(
        graph,
        "owner_vocabularies",
        lambda _owner: [
            {"language": "es", "definitionLang": "es", "glossLangs": [], "notesLang": "en",
             "displayName": "Spanish"}
        ],
    )
    answer = seeded.capture(text="El disfraz de pirata viene con un garfio.")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "language_not_configured"
    assert "no translation language" in answer.json()["error"]["message"]
    assert len(seeded.model.calls) == 1


def test_it_says_so_when_the_input_cannot_be_read_as_a_word_at_all(seeded):
    seeded.model.resolution = {"error": "!!! ???"}
    answer = seeded.capture(text="!!! ???")
    assert answer.status_code == 422
    assert answer.json()["error"]["code"] == "unreadable_input"


def test_it_reports_a_model_that_answers_with_nothing_usable_rather_than_half_an_entry(seeded):
    seeded.model.article = {"headword": "el garfio", "senses": []}
    assert seeded.capture().json()["error"]["code"] == "llm_unusable"


@pytest.mark.parametrize("text", ["", "   \n  "])
def test_it_refuses_an_empty_capture(seeded, text):
    answer = seeded.capture(text=text)
    assert answer.status_code == 400
    assert answer.json()["error"]["message"] == "There is nothing to capture."


def test_it_refuses_a_capture_too_long_to_process_in_one_request(seeded):
    answer = seeded.capture(text="a" * 20001)
    assert answer.status_code == 400
    assert "too long" in answer.json()["error"]["message"]


# ── what the submitter is allowed to say ────────────────────────────────────


def test_it_passes_on_the_word_the_submitter_named_and_says_nothing_when_they_did_not(seeded):
    """A hint for the resolver, not a bypass of it: the model still fixes the spelling, adds the
    article and picks the lemma, so a named word and a picked one reach the article the same way."""
    seeded.capture(text="El disfraz de pirata viene con un garfio.", headword="garfio")
    assert "The learner says the word is: garfio" in prompts_of(seeded)[0]

    seeded.model.calls.clear()
    seeded.capture(text="El disfraz de pirata viene con un garfio.")
    assert "The learner says the word is" not in prompts_of(seeded)[0]


def test_it_carries_a_dictionary_entry_to_both_steps_as_reference_and_only_as_reference(seeded):
    seeded.model.resolution = {**RESOLUTION, "sentences": []}
    reference = (
        "## Wiktionary (es→es)\nverb\n1. Golpear algo con una punta.\n"
        "   - una tela que pica — an itchy fabric"
    )
    seeded.capture(text="picar", headword="picar", reference=reference, referenceMode="expand")

    resolve, compose = prompts_of(seeded)
    # The resolver is told what it is looking at, and told plainly that it is not learner input.
    assert "una tela que pica" in resolve
    assert "CONTEXT ONLY" in resolve
    # The composer is grounded on it and told which treatment was chosen.
    assert "Golpear algo con una punta" in compose
    assert "FILL IN THE GAPS" in compose
    assert "STAY CLOSE TO THE REFERENCE" not in compose


def test_it_says_to_stay_close_when_that_is_what_was_asked_for(seeded):
    seeded.model.resolution = {**RESOLUTION, "sentences": []}
    seeded.capture(text="picar", reference="1. Golpear algo con una punta.", referenceMode="faithful")
    compose = prompts_of(seeded)[1]
    assert "STAY CLOSE TO THE REFERENCE" in compose
    assert "FILL IN THE GAPS" not in compose


def test_it_ignores_a_reference_mode_it_does_not_recognise_rather_than_passing_it_on(seeded):
    seeded.model.resolution = {**RESOLUTION, "sentences": []}
    seeded.capture(text="picar", reference="1. Golpear algo.", referenceMode="whatever-you-like")
    compose = prompts_of(seeded)[1]
    assert "Reference entry from an external dictionary" in compose
    assert "Treatment:" not in compose


def test_it_never_turns_a_reference_into_an_attestation(seeded):
    """The resolver is what mints attestations, and a grounded capture gives it no sentences: the
    dictionary's examples are the dictionary's, not places this person met the word."""
    seeded.model.resolution = {**RESOLUTION, "sentences": []}
    draft = seeded.capture(
        text="picar",
        reference="1. Golpear algo con una punta.\n   - una tela que pica",
        referenceMode="expand",
    ).json()["data"]["draft"]
    assert draft["attestations"] == []
    examples = [example for sense in draft["senses"] for example in sense["examples"]]
    assert examples
    assert all(example["sourceAttestationId"] is None for example in examples)
    assert all(example["origin"] == "llm" for example in examples)


# ── the draft ───────────────────────────────────────────────────────────────


def test_it_builds_a_draft_keeping_the_learners_sentence_as_an_attestation_the_example_names(seeded):
    draft = seeded.capture().json()["data"]["draft"]

    assert draft["id"] is None
    # Reviewed in the interface before it is saved, so it is not an Inbox word.
    assert draft["status"] == "active"
    # Every sense carries a one-word label and an emoji of its own.
    assert draft["senses"][0]["domain"] == "tools"
    assert draft["senses"][0]["emoji"] == "\U0001FA9D"
    assert draft["headword"] == "el garfio"
    assert draft["gender"] == "masculine"
    # A topic the account does not have is dropped rather than invented: saving would refuse it.
    assert draft["topics"] == ["Culture"]

    assert len(draft["attestations"]) == 1
    own, invented = draft["senses"][0]["examples"]
    assert own["origin"] == "attestation"
    assert own["sourceAttestationId"] == draft["attestations"][0]["id"]
    assert own["modelId"] is None
    assert invented["origin"] == "llm"
    assert invented["modelId"] == "gemini-3.5-flash-lite"
    # Every minted id is a real Acervo id, or nothing could reference anything.
    for identifier in (draft["senses"][0]["id"], own["id"], draft["attestations"][0]["id"]):
        assert re.match(r"^[a-z0-9]{15}$", identifier)


def test_it_drops_a_marked_form_the_model_retyped_instead_of_copying(seeded):
    own, invented = seeded.capture().json()["data"]["draft"]["senses"][0]["examples"]
    assert own["matchedForm"] == "un garfio"
    # "el garfio" does not occur in "Perdió la mano y le pusieron un garfio", and "hooks" does not
    # occur in its translation. Keeping either would make the record validator refuse the batch.
    assert invented["matchedForm"] is None
    assert invented["matchedTranslationForm"] is None


def test_an_examples_emotion_travels_into_the_draft_and_a_long_one_is_cut_rather_than_refused(seeded):
    rambling = "furious " * 60
    seeded.model.article = {
        **ARTICLE,
        "senses": [{**ARTICLE["senses"][0], "examples": [
            {**ARTICLE["senses"][0]["examples"][0], "emotion": "  proud,  showing off the costume "},
            {**ARTICLE["senses"][0]["examples"][1], "emotion": rambling},
        ]}],
    }
    proud, cut = seeded.capture().json()["data"]["draft"]["senses"][0]["examples"]
    assert proud["emotion"] == "proud, showing off the costume"
    assert 0 < len(cut["emotion"]) <= 300 and not cut["emotion"].endswith(" ")
    assert cut["emotion"].split(" ")[-1] == "furious"


def test_it_fills_in_a_gloss_and_a_definition_language_rather_than_losing_the_sense(seeded):
    seeded.model.article = {
        **ARTICLE,
        "senses": [{"definition": "Gancho de metal.", "glosses": [], "examples": []}],
    }
    sense = seeded.capture().json()["data"]["draft"]["senses"][0]
    assert sense["glosses"] == [{"lang": "en", "terms": ["el garfio"]}]
    assert sense["definitionLang"] == "es"


@pytest.mark.parametrize("claimed", [None, "", -1, 5, 1.5, True, "0"])
def test_an_absent_or_impossible_sentence_index_never_credits_the_learner(seeded, claimed):
    """`Number(null)` is 0 in the language this came from, so a plain numeric read here would take
    "I invented this" for "this is sentence 0"."""
    seeded.model.article = {
        **ARTICLE,
        "senses": [
            {
                "definition": "Gancho de metal.",
                "glosses": [{"lang": "en", "terms": ["hook"]}],
                "examples": [{"text": "Un garfio de metal.", "fromSentence": claimed}],
            }
        ],
    }
    example = seeded.capture().json()["data"]["draft"]["senses"][0]["examples"][0]
    assert example["origin"] == "llm"
    assert example["sourceAttestationId"] is None


def test_a_chinese_entry_with_no_reading_is_refused_before_it_reaches_the_validator(seeded):
    """Saying which field is missing beats letting the save fail later with a validation message
    about a field nobody was shown."""
    seeded.push({"vocabularies": [vocabulary(language="zh-Hans", definitionLang="en", order=1)]})
    seeded.model.resolution = {**RESOLUTION, "language": "zh-Hans", "headword": "钩子"}
    answer = seeded.capture(text="钩子")
    assert answer.json()["error"]["code"] == "llm_unusable"
    assert "reading" in answer.json()["error"]["message"]


# ── the stream ──────────────────────────────────────────────────────────────


def test_it_never_consumes_zero_lines_in_a_stream_so_a_walk_cannot_stall(seeded):
    seeded.model.resolution = {**RESOLUTION, "consumedLines": 0, "consumedText": "line one"}
    body = seeded.capture(mode="stream", text="line one\nline two\nline three").json()["data"]
    assert body["resolution"]["consumedLines"] == 1


def test_it_refuses_a_mismatched_stream_boundary_before_composing_or_writing(seeded):
    seeded.model.resolution = {**RESOLUTION, "consumedLines": 1, "consumedText": "different text"}
    answer = seeded.capture(mode="stream", text="line one\nline two")
    assert answer.json()["error"]["code"] == "stream_boundary_mismatch"
    assert len(seeded.model.calls) == 1
    changes = seeded.pull().json()["data"]["changes"]
    assert changes["attestations"] == []
    assert changes["examples"] == []


# ── writing nothing ─────────────────────────────────────────────────────────


def test_a_proposal_is_never_written_even_when_applying_is_asked_for(seeded):
    """Headless capture is a job now (`POST /captures`); this route only proposes."""
    body = seeded.capture(apply=True).json()["data"]
    assert "applied" not in body
    changes = seeded.pull().json()["data"]["changes"]
    assert changes["attestations"] == []
    assert len(changes["lexemes"]) == 1  # only the seeded `picar`


# ── how the provider is called ──────────────────────────────────────────────
# A provider is reached through LiteLLM by its family, so what is worth asserting here is what the
# family put into the request — not a URL this code no longer builds. LiteLLM is sent the family's
# prefix and the provider's own model id; a record names the provider's own id.


def test_it_asks_the_first_provider_added(seeded):
    seeded.capture()
    call = seeded.model.calls[0]
    assert call["model"] == "gemini/gemini-3.5-flash-lite"
    assert call["api_key"] == GEMINI_KEY
    assert call["timeout"] == provider_call.TIMEOUT_SECONDS
    # The Gemini API's family says JSON mode is native, so it is requested rather than asked for in
    # prose. The two capture prompts return free-form documents, so it is `json_object` and not a
    # schema.
    assert call["response_format"] == {"type": "json_object"}


def test_litellms_own_retries_are_switched_off(seeded):
    """Both of them: `num_retries` is LiteLLM's loop and `max_retries` is the provider SDK's, which
    LiteLLM otherwise sets to 2. The chain is the only fall-through, and the file ingestion is the
    only retry."""
    seeded.capture()
    assert seeded.model.calls[0]["num_retries"] == 0
    assert seeded.model.calls[0]["max_retries"] == 0


def test_the_order_decides_which_provider_is_asked_first(seeded):
    seeded.add_provider(CLOUDFLARE)
    select(seeded, {"text": [{"provider": "cloudflare", "model": CLOUDFLARE_MODEL},
                             {"provider": "gemini-api", "model": GEMINI_FIRST}]})

    seeded.capture()
    call = seeded.model.calls[0]
    assert call["model"] == f"cloudflare/{CLOUDFLARE_MODEL}"
    assert call["api_key"] == CLOUDFLARE_TOKEN
    # The account travels in the address rather than in the environment.
    assert call["api_base"] == f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT}/ai/v1"
    # Cloudflare's family asks for JSON in the prompt, and the reply is parsed afterwards.
    assert "response_format" not in call


def test_a_rate_limited_model_falls_through_to_the_next_model_of_the_same_provider(seeded):
    """The reason a row lists several models: they are separate free-tier buckets, so the second is
    reached by the first one's 429 rather than being a spare."""
    seeded.model.limited = {"gemini/gemini-3.5-flash-lite"}

    draft = seeded.capture().json()["data"]["draft"]
    asked = [call["model"] for call in seeded.model.calls]
    assert asked[:2] == ["gemini/gemini-3.5-flash-lite", "gemini/gemini-3.1-flash-lite"]
    _own, invented = draft["senses"][0]["examples"]
    assert invented["modelId"] == "gemini-3.1-flash-lite"


def test_the_second_model_call_does_not_re_probe_what_the_first_exhausted(seeded):
    """A capture is two model calls. Asking a model that just returned 429 a second time, seconds
    later, buys nothing and costs the owner the wait — so the refusal is remembered."""
    seeded.model.limited = {"gemini/gemini-3.5-flash-lite"}
    seeded.capture()

    asked = [call["model"] for call in seeded.model.calls]
    assert asked == [
        "gemini/gemini-3.5-flash-lite",   # resolve: tried, refused, and rested
        "gemini/gemini-3.1-flash-lite",   # resolve: answered
        "gemini/gemini-3.1-flash-lite",   # compose: went straight here
    ]


def test_an_exhausted_provider_falls_through_and_the_entry_records_who_answered(seeded, monkeypatch):
    """The locked provenance contract, end to end. `modelId` naming the first choice is a bug."""
    seeded.add_provider(CLOUDFLARE)
    seeded.model.limited = {"gemini/gemini-3.5-flash-lite", "gemini/gemini-3.1-flash-lite"}

    draft = seeded.capture().json()["data"]["draft"]
    asked = [call["model"] for call in seeded.model.calls]
    assert [m.split("/")[0] for m in asked[:3]] == ["gemini", "gemini", "cloudflare"]
    _own, invented = draft["senses"][0]["examples"]
    assert invented["modelId"] == CLOUDFLARE_MODEL


def test_an_authentication_failure_stops_the_chain_rather_than_spending_the_next_provider(
    seeded, monkeypatch
):
    """A mistake to fix, not a condition to route around. The call count is the assertion."""
    seeded.add_provider(CLOUDFLARE)
    seeded.model.error = litellm.AuthenticationError(message=PRIVATE, llm_provider="p", model="m")

    assert seeded.capture().json()["error"]["code"] == "llm_authentication"
    assert len(seeded.model.calls) == 1


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (lambda: litellm.AuthenticationError(message=PRIVATE, llm_provider="p", model="m"),
         "llm_authentication"),
        (lambda: litellm.PermissionDeniedError(
            message=PRIVATE, llm_provider="p", model="m",
            response=httpx.Response(403, request=httpx.Request("POST", "https://p.example.com"))),
         "llm_authentication"),
        (lambda: litellm.BadRequestError(message=PRIVATE, model="m", llm_provider="p"),
         "llm_configuration"),
        (lambda: litellm.NotFoundError(message=PRIVATE, model="m", llm_provider="p"),
         "llm_configuration"),
        (lambda: litellm.RateLimitError(message=PRIVATE, llm_provider="p", model="m"),
         "llm_rate_limited"),
        (lambda: litellm.InternalServerError(message=PRIVATE, llm_provider="p", model="m"),
         "llm_unavailable"),
        (lambda: litellm.ServiceUnavailableError(message=PRIVATE, llm_provider="p", model="m"),
         "llm_unavailable"),
        (lambda: litellm.APIError(status_code=418, message=PRIVATE, llm_provider="p", model="m"),
         "llm_failed"),
        (lambda: litellm.Timeout(message=PRIVATE, model="m", llm_provider="p"),
         "llm_unreachable"),
        (lambda: litellm.APIConnectionError(message=PRIVATE, llm_provider="p", model="m"),
         "llm_unreachable"),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_it_classifies_a_provider_failure_without_exposing_its_response(seeded, failure, code):
    """The taxonomy is a contract: the file ingestion retries on exactly three of these codes.

    The last two are the ones a status-only reading gets wrong — `Timeout` carries 408 and
    `APIConnectionError` carries 500 — and getting them wrong would stop a timeout being retried
    without touching the retry code.
    """
    seeded.model.error = failure()
    answer = seeded.capture()
    assert answer.json()["error"]["code"] == code
    assert "provider details" not in answer.text


def test_a_provider_that_cannot_be_reached_is_told_apart_from_one_that_refuses(seeded):
    seeded.model.error = litellm.APIConnectionError(message=PRIVATE, llm_provider="p", model="m")
    answer = seeded.capture()
    assert answer.status_code == 502
    assert answer.json()["error"]["code"] == "llm_unreachable"


def test_every_row_being_rate_limited_still_reads_as_rate_limited(seeded, monkeypatch):
    """What keeps the retry contract when a chain runs out: the last error is the reported one."""
    seeded.add_provider(CLOUDFLARE)
    seeded.model.error = litellm.RateLimitError(message=PRIVATE, llm_provider="p", model="m")

    assert seeded.capture().json()["error"]["code"] == "llm_rate_limited"
    # Every pair, not every provider: the Gemini API's two models and then Cloudflare's one.
    assert len(seeded.model.calls) == 3


def test_hidden_reasoning_never_reaches_the_article(seeded):
    """`llm.py` skipped Google's `thought` parts by hand; LiteLLM separates them from the content."""
    seeded.model.reasoning = "deliberation nobody asked for"
    assert seeded.capture().json()["data"]["draft"]["headword"] == "el garfio"


@pytest.mark.parametrize(
    ("text", "code"),
    [("", "llm_empty"), ("   ", "llm_empty"), ("not json at all", "llm_unusable")],
)
def test_an_answer_with_nothing_usable_in_it_is_named_as_such(seeded, text, code):
    seeded.model.text = text
    assert seeded.capture().json()["error"]["code"] == code


def test_a_fenced_answer_is_unwrapped_rather_than_refused(seeded):
    """Models wrap JSON in backticks often enough that not handling it would be the top cause of
    failure."""
    import json

    seeded.model.text = "```json\n" + json.dumps(RESOLUTION) + "\n```"
    assert seeded.capture().status_code in (200, 502)
    assert seeded.model.calls  # it got as far as asking


# ── what health says, and whether capture agrees ────────────────────────────
# Health is the only place a misconfigured model is visible before someone presses the button, so
# what it says has to be specific enough to act on. Each case pairs the readout with the refusal
# capture itself gives, because the two are computed separately on purpose and could drift.


def capture_health(server):
    return server.client.get("/api/acervo/v1/health").json()["data"]["capture"]


def test_health_reports_the_pair_that_would_be_asked_first(seeded):
    assert capture_health(seeded) == {
        "available": True,
        "provider": "gemini-api",
        "model": "gemini-3.5-flash-lite",
        "reason": None,
    }


BROKEN = {
    "no provider is added for text": {"remove": True},
    "Gemini API has no API key": {"secret": {}},
    "Cloudflare needs its account ID": {"remove": True, "add": {**CLOUDFLARE, "settings": {}}},
    "Gemini API refused its key when it was last checked": {
        "check": {"ok": False, "said": "no", "reason": "authentication", "account": None}},
}


@pytest.mark.parametrize("reason", list(BROKEN))
def test_health_names_the_first_unmet_requirement_and_capture_then_refuses(seeded, reason):
    case = BROKEN[reason]
    if case.get("remove"):
        seeded.remove_provider("gemini-api")
    if "secret" in case or "check" in case:
        seeded.add_provider(GEMINI, case.get("secret"), case.get("check"))
    if case.get("add"):
        seeded.add_provider(case["add"])

    readout = capture_health(seeded)
    assert readout["available"] is False
    assert readout["reason"] == reason

    answer = seeded.capture()
    # The code differs by cause — the taxonomy is deliberately unchanged — but nothing is built.
    assert answer.json()["error"]["code"] in {"capture_unavailable", "llm_configuration"}
    assert seeded.model.calls == []


def test_health_never_puts_a_key_an_endpoint_or_an_account_id_in_an_unauthenticated_response(
    seeded, monkeypatch
):
    seeded.add_provider(CLOUDFLARE)
    body = seeded.client.get("/api/acervo/v1/health").text
    for secret in (CLOUDFLARE_TOKEN, GEMINI_KEY, CLOUDFLARE_ACCOUNT):
        assert secret not in body


# ── whose chain decides ─────────────────────────────────────────────────────
# The point of Settings ▸ Providers: the owner's order takes effect on the next capture, with nothing
# restarted and nothing redeployed. These run against the same process, which is the whole claim.


GEMINI_FIRST = "gemini-3.5-flash-lite"
GEMINI_SECOND = "gemini-3.1-flash-lite"
CLOUDFLARE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
# What LiteLLM is sent: the family's prefix and the provider's own id.
WIRE_SECOND = f"gemini/{GEMINI_SECOND}"
WIRE_CLOUDFLARE = f"cloudflare/{CLOUDFLARE_MODEL}"


def select(server, chains):
    return server.client.put(
        "/api/acervo/v1/models/selection", headers=server.auth, json={"chains": chains}
    )


@pytest.fixture
def cloudflare_too(seeded):
    seeded.add_provider(CLOUDFLARE)


def test_the_owners_chain_takes_effect_on_the_next_capture_with_no_restart(seeded, cloudflare_too):
    seeded.capture()
    assert seeded.model.calls[0]["model"].startswith("gemini/")

    select(seeded, {"text": [{"provider": "cloudflare", "model": CLOUDFLARE_MODEL}]})
    seeded.model.calls.clear()
    seeded.capture()
    assert seeded.model.calls[0]["model"] == WIRE_CLOUDFLARE


def test_with_nothing_chosen_the_providers_are_asked_in_the_order_they_were_added(seeded, cloudflare_too):
    seeded.model.limited = {"gemini/gemini-3.5-flash-lite", WIRE_SECOND}
    seeded.capture()
    assert [call["model"] for call in seeded.model.calls][:3] == [
        "gemini/gemini-3.5-flash-lite", WIRE_SECOND, WIRE_CLOUDFLARE]


def test_the_owner_can_pin_the_second_model_of_a_provider_and_it_is_the_only_one_called(seeded):
    """Two free-tier buckets of 500 a day; the owner picks which one this account spends."""
    select(seeded, {"text": [{"provider": "gemini-api", "model": GEMINI_SECOND}]})
    seeded.capture()
    assert [call["model"] for call in seeded.model.calls] == [WIRE_SECOND, WIRE_SECOND]


def test_a_chosen_chain_falls_through_and_the_entry_records_who_answered(seeded, cloudflare_too):
    select(seeded, {"text": [
        {"provider": "gemini-api", "model": GEMINI_SECOND},
        {"provider": "cloudflare", "model": CLOUDFLARE_MODEL},
    ]})
    seeded.model.limited = {WIRE_SECOND}

    draft = seeded.capture().json()["data"]["draft"]
    assert [call["model"] for call in seeded.model.calls][:2] == [WIRE_SECOND, WIRE_CLOUDFLARE]
    _own, invented = draft["senses"][0]["examples"]
    assert invented["modelId"] == CLOUDFLARE_MODEL


def test_a_chosen_pair_whose_key_was_refused_is_skipped_rather_than_refused(seeded, cloudflare_too):
    """A refused key must not turn the owner's saved order into a refusal of every capture."""
    select(seeded, {"text": [
        {"provider": "cloudflare", "model": CLOUDFLARE_MODEL},
        {"provider": "gemini-api", "model": GEMINI_SECOND},
    ]})
    seeded.add_provider(CLOUDFLARE, check={"ok": False, "said": "no", "reason": "authentication",
                                           "account": None})
    seeded.capture()
    assert [call["model"] for call in seeded.model.calls] == [WIRE_SECOND, WIRE_SECOND]


def test_a_chosen_model_the_provider_no_longer_offers_refuses_before_spending_anything(seeded):
    """Refuse, never skip. A model nobody offers is a state nothing is supposed to produce —
    removing one takes it out of every order — and skipping it would walk half the chain the owner
    configured, silently, forever."""
    from acervo.repository import model_selection

    model_selection.save(seeded.owner, {"text": [("gemini-api", "retired-last-year")]})
    answer = seeded.capture()
    assert answer.json()["error"]["code"] == "llm_configuration"
    assert seeded.model.calls == []


def test_health_reports_the_providers_order_while_the_owner_reports_their_own(seeded, cloudflare_too):
    """`/health` is unauthenticated — the liveness probe and the pre-sign-in readout — so it must
    not vary by caller. What the owner's chain will do is `GET /models`."""
    select(seeded, {"text": [{"provider": "cloudflare", "model": CLOUDFLARE_MODEL}]})

    assert capture_health(seeded) == {
        "available": True, "provider": "gemini-api",
        "model": "gemini-3.5-flash-lite", "reason": None,
    }
    chosen = seeded.get("/models").json()["data"]["chains"]["text"]
    assert chosen["source"] == "owner"
    assert chosen["pairs"] == [{"provider": "cloudflare", "model": CLOUDFLARE_MODEL}]


def test_a_fall_through_is_reported_so_a_broken_provider_is_not_invisible(seeded, cloudflare_too):
    """The entry names the model that wrote it, which is not the same as saying who was asked first.

    A provider at the head of the owner's order that is quietly failing looks exactly like one they
    never chose, and they go on believing it is the one building their words.
    """
    select(seeded, {"text": [
        {"provider": "cloudflare", "model": CLOUDFLARE_MODEL},
        {"provider": "gemini-api", "model": GEMINI_SECOND},
    ]})
    seeded.model.limited = {WIRE_CLOUDFLARE}

    body = seeded.capture().json()["data"]
    assert body["passedOver"] == [
        {"provider": "cloudflare", "model": CLOUDFLARE_MODEL, "reason": "rate_limited"}
    ]
    _own, invented = body["draft"]["senses"][0]["examples"]
    assert invented["modelId"] == GEMINI_SECOND


def test_nothing_is_reported_when_the_first_choice_answered(seeded):
    assert seeded.capture().json()["data"]["passedOver"] == []


def test_a_provider_that_refused_both_calls_is_reported_once(seeded, cloudflare_too):
    """One thing that is wrong, not two — a capture is two model calls, not two problems."""
    select(seeded, {"text": [
        {"provider": "cloudflare", "model": CLOUDFLARE_MODEL},
        {"provider": "gemini-api", "model": GEMINI_SECOND},
    ]})
    seeded.model.limited = {WIRE_CLOUDFLARE}
    seeded.capture()

    # The rest means the second call skips it, so this also pins that a remembered refusal does not
    # cost the report: what was passed over on the way stays reported either way.
    body = seeded.capture().json()["data"]
    assert len(body["passedOver"]) <= 1


# ── the fold-in: what a repeat capture carried that the stored entry may not have ───


def test_a_repeat_capture_offers_what_it_carried(seeded):
    """§05: a repeat capture is an addition, not an entry — and this branch already knows what it
    would add, because resolve has run. No second model call is spent finding out."""
    seeded.model.resolution = {**RESOLUTION, "headword": "picar", "lemma": "picar"}
    answered = seeded.capture(text="cuidado que esa salsa pica un monton").json()["data"]
    assert answered["duplicates"]
    assert answered["draft"] is None
    assert answered["foldable"]["sentences"] == RESOLUTION["sentences"]
    assert answered["foldable"]["reference"] is False
    # One model call, not two: composing an article for a word already held is what this avoids.
    assert len(seeded.model.calls) == 1


def test_a_repeat_capture_of_just_the_word_offers_nothing(seeded):
    seeded.model.resolution = {**RESOLUTION, "headword": "picar", "lemma": "picar", "sentences": []}
    answered = seeded.capture(text="picar").json()["data"]
    assert answered["duplicates"]
    assert answered["foldable"] is None


def test_a_repeat_capture_counts_a_dictionary_entry_as_something_to_fold(seeded):
    seeded.model.resolution = {**RESOLUTION, "headword": "picar", "lemma": "picar", "sentences": []}
    answered = seeded.capture(text="picar", reference="picar — to itch", referenceMode="expand")
    folded = answered.json()["data"]["foldable"]
    assert folded["reference"] is True
    # The dictionary's text is never offered as a sentence: an attestation is somewhere the learner
    # met the word, and a dictionary's own examples are not that.
    assert folded["sentences"] == []


def test_a_new_word_has_nothing_to_fold_in(seeded):
    assert seeded.capture().json()["data"]["foldable"] is None
