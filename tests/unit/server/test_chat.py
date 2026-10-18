"""The chat route: one turn in, prose and maybe a proposed edit out. It writes nothing.

What is asserted here is the wire contract — the limits the route enforces, which prompt answers
which subject, and which of `proposal` / `capture` each kind may return. Whether an operation *means*
anything is `web/src/articleEdit.ts`'s question: the document is a YAML string this layer
deliberately does not parse, because `yaml.ts` is the only place that projection is understood.
"""

from __future__ import annotations

import litellm
import pytest
from conftest import DEVICE
from graph_records import vocabulary

from acervo.domain import SCHEMA_VERSION

PRIVATE = "provider details that must stay private"

REPLY = {
    "reply": "«el traje» is any outfit; «el disfraz» is worn to be taken for someone else.",
    "followUps": ["Add that to the notes", "One more example"],
}

PROPOSAL = {
    "summary": "Adds the contrast to the notes.",
    "ops": [{"op": "set", "target": "lexeme", "field": "notes", "value": ["Not el traje."]}],
}

CAPTURE = {"headword": "el disfraz", "referenceMode": "expand", "note": "they asked about theatre"}

REFERENCE_SUBJECT = {"kind": "reference", "headword": "el disfraz", "language": "es"}


@pytest.fixture
def talking(server):
    server.push({"vocabularies": [vocabulary()]})
    server.model.chat = {**REPLY, "proposal": dict(PROPOSAL)}
    server.model.chat_reference = {**REPLY, "capture": dict(CAPTURE)}
    return server


def prompts_of(server):
    return [
        next(message["content"] for message in call["messages"] if message["role"] == "user")
        for call in server.model.calls
    ]


def systems_of(server):
    return [
        next(message["content"] for message in call["messages"] if message["role"] == "system")
        for call in server.model.calls
    ]


# ── what it refuses, and how early ──────────────────────────────────────────


def test_it_needs_a_token(server):
    answered = server.client.post("/api/acervo/v1/chat", json={})
    assert answered.status_code == 401
    assert server.model.calls == []


def test_it_refuses_a_request_that_says_nothing_about_what_it_is_about(talking):
    answered = talking.chat(subject={"kind": "article", "document": ""})
    assert answered.status_code == 400
    assert answered.json()["error"]["code"] == "invalid_input"
    assert talking.model.calls == []


def test_it_refuses_a_subject_kind_it_does_not_know(talking):
    answered = talking.chat(subject={"kind": "corpus", "document": "x"})
    assert answered.status_code == 400
    assert talking.model.calls == []


def test_it_says_so_when_no_model_is_configured(server, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    answered = server.chat()
    assert answered.status_code == 503
    assert answered.json()["error"]["code"] == "capture_unavailable"
    # Nothing was attempted: an unconfigured server must not spend a round trip finding that out.
    assert server.model.calls == []


def test_it_refuses_a_wrong_schema_version(talking):
    answered = talking.chat(schemaVersion=2)
    assert answered.status_code == 409
    assert talking.model.calls == []


# ── the limits, enforced here rather than asked for in the prompt ───────────


def test_it_sends_only_the_last_eight_turns(talking):
    turns = [{"role": "you" if index % 2 == 0 else "acervo", "text": f"turn {index}"} for index in range(12)]
    talking.chat(turns=turns)
    asked = prompts_of(talking)[0]
    assert "turn 11" in asked
    assert "turn 4" in asked
    assert "turn 3" not in asked


def test_it_caps_the_document(talking):
    talking.chat(subject={"kind": "article", "lexemeId": "lexemepicar0001",
                          "document": "x" * 40000, "focus": None})
    assert "x" * 32000 in prompts_of(talking)[0]
    assert "x" * 32001 not in prompts_of(talking)[0]


def test_it_caps_the_reference(talking):
    talking.chat(reference="y" * 20000)
    asked = prompts_of(talking)[0]
    assert "y" * 8000 in asked
    assert "y" * 8001 not in asked


def test_it_caps_the_neighbours(talking):
    talking.chat(neighbours=[{"headword": f"word{index}", "shortGloss": None} for index in range(40)])
    asked = prompts_of(talking)[0]
    assert "word19" in asked
    assert "word20" not in asked


def test_it_clamps_the_reply_and_the_follow_ups(talking):
    talking.model.chat = {
        "reply": "z" * 4000,
        "followUps": ["a" * 80, "b", "c", "d"],
        "proposal": None,
    }
    answered = talking.chat().json()["data"]
    assert len(answered["reply"]) == 1200
    assert len(answered["followUps"]) == 3
    assert len(answered["followUps"][0]) == 40


def test_it_drops_a_proposal_with_too_many_operations_and_keeps_the_reply(talking):
    talking.model.chat = {
        **REPLY,
        "proposal": {
            "summary": "a rewrite",
            "ops": [{"op": "set", "target": "lexeme", "field": "emoji", "value": "x"}] * 25,
        },
    }
    answered = talking.chat().json()["data"]
    assert answered["proposal"] is None
    assert answered["reply"].startswith("«el traje»")


def test_one_malformed_operation_drops_the_whole_proposal_and_says_which(talking):
    malformed = {"summary": "…", "ops": [
        {"op": "set", "target": "lexeme", "field": "notes", "value": ["fine"]},
        {"op": "set", "target": "lexeme"},
    ]}
    talking.model.chat = {**REPLY, "proposal": malformed}
    answered = talking.chat().json()["data"]
    assert answered["proposal"] is None
    # Never silent: the sentence names the operation, so a repair can fix exactly that one.
    assert answered["proposalProblem"].startswith("Operation 2 is a `set` with no `field`")
    assert answered["rejected"] == malformed


def test_a_set_never_reads_a_missing_value_as_null(talking):
    # A shape a real model writes: the value under the field's name. Read as null it would erase the
    # translation; read from where it was put, it is the edit that was asked for.
    talking.model.chat = {**REPLY, "proposal": {"summary": "…", "ops": [
        {"op": "set", "target": "example:b8n4k2j7w1q5z0c", "field": "translation",
         "translation": "The pirate outfit comes with a hook."}]}}
    assert talking.chat().json()["data"]["proposal"]["ops"][0]["value"] == "The pirate outfit comes with a hook."
    talking.model.chat = {**REPLY, "proposal": {"summary": "…", "ops": [
        {"op": "set", "target": "example:b8n4k2j7w1q5z0c", "field": "translation"}]}}
    answered = talking.chat().json()["data"]
    assert answered["proposal"] is None
    assert "with no `value`" in answered["proposalProblem"]


def test_an_answer_that_says_it_edits_and_carries_nothing_is_a_problem(talking):
    talking.model.chat = {**REPLY, "intent": "edit", "proposal": None}
    answered = talking.chat().json()["data"]
    assert answered["proposal"] is None
    assert "carried no `proposal`" in answered["proposalProblem"]


def test_a_plain_answer_is_no_problem(talking):
    talking.model.chat = {**REPLY, "intent": "answer", "proposal": None}
    answered = talking.chat().json()["data"]
    assert answered["proposal"] is None and answered["proposalProblem"] is None


def test_a_turn_says_what_became_of_the_change_it_offered(talking):
    talking.chat(turns=[
        {"role": "you", "text": "use jacket instead of coat"},
        {"role": "acervo", "text": "Here is a change.",
         "offered": {"summary": "Replaces coat.", "outcome": "refused",
                     "reason": "That was a rewrite rather than an edit, so nothing was changed."}},
        {"role": "you", "text": "try again"},
    ])
    sent = prompts_of(talking)[-1]
    assert ("acervo: Here is a change.\n  [offered a change: Replaces coat. — NOT applied, nothing "
            "changed: That was a rewrite rather than an edit, so nothing was changed.]") in sent


def test_a_discarded_change_does_not_read_as_a_request_still_standing(talking):
    talking.chat(turns=[
        {"role": "you", "text": "drop the example"},
        {"role": "acervo", "text": "Here is a change.",
         "offered": {"summary": "Removes it.", "outcome": "discarded"}},
        {"role": "you", "text": "why is it there?"},
    ])
    sent = prompts_of(talking)[-1]
    assert "[offered a change: Removes it. — discarded by the learner, nothing changed]" in sent
    assert "NOT applied" not in sent


def test_a_turn_sent_back_carries_the_sentence_and_what_was_sent(talking):
    talking.chat(repair={"problem": "The model referred to a part of the entry that is not there.",
                         "attempt": 1, "previous": {"summary": "x", "ops": [{"op": "remove",
                                                                             "target": "example:nope"}]}})
    sent = prompts_of(talking)[-1]
    assert "COULD NOT BE USED" in sent
    assert "a part of the entry that is not there" in sent
    assert '"target": "example:nope"' in sent


def test_a_turn_is_sent_back_at_most_twice(talking):
    answered = talking.chat(repair={"problem": "still wrong", "attempt": 3, "previous": None})
    assert answered.status_code == 400
    assert talking.model.calls == []


def test_the_device_reports_what_it_would_not_apply_and_nothing_is_written(talking):
    before = talking.pull().json()["data"]["cursor"]
    answered = talking.post("/chat/outcome", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE,
        "problem": "That was a rewrite rather than an edit, so nothing was changed.",
        "proposal": {"summary": "x", "ops": []},
    })
    assert answered.status_code == 200
    assert talking.pull().json()["data"]["cursor"] == before
    assert talking.model.calls == []


def test_a_report_must_say_what_was_refused(talking):
    answered = talking.post("/chat/outcome", {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE})
    assert answered.status_code == 400


def test_it_drops_an_operation_name_it_does_not_know(talking):
    talking.model.chat = {**REPLY, "proposal": {"summary": "…", "ops": [{"op": "rewrite"}]}}
    assert talking.chat().json()["data"]["proposal"] is None


def test_it_carries_a_well_formed_proposal_through(talking):
    answered = talking.chat().json()["data"]
    assert answered["proposal"]["ops"] == PROPOSAL["ops"]
    assert answered["proposal"]["summary"] == PROPOSAL["summary"]
    assert answered["modelId"]


# ── the two subjects, and what each may return ──────────────────────────────


def test_an_article_subject_reads_the_article_prompt(talking):
    talking.chat()
    assert "You answer a learner's message" in systems_of(talking)[0]


def test_a_reference_subject_reads_the_reference_prompt(talking):
    talking.chat(subject=dict(REFERENCE_SUBJECT))
    assert "You help a learner read" in systems_of(talking)[0]


def test_a_reference_subject_never_returns_a_proposal(talking):
    # The stub is told to propose one anyway: there is nothing editable on screen, so the field is
    # dropped rather than passed on. A dictionary entry is not the learner's to change.
    talking.model.chat_reference = {**REPLY, "proposal": dict(PROPOSAL), "capture": dict(CAPTURE)}
    answered = talking.chat(subject=dict(REFERENCE_SUBJECT)).json()["data"]
    assert answered["proposal"] is None
    assert answered["capture"]["headword"] == "el disfraz"


def test_an_article_subject_never_returns_a_capture(talking):
    talking.model.chat = {**REPLY, "proposal": None, "capture": dict(CAPTURE)}
    assert talking.chat().json()["data"]["capture"] is None


def test_it_drops_a_reference_mode_it_does_not_know(talking):
    talking.model.chat_reference = {**REPLY, "capture": {**CAPTURE, "referenceMode": "invent"}}
    answered = talking.chat(subject=dict(REFERENCE_SUBJECT)).json()["data"]
    assert answered["capture"]["referenceMode"] is None


def test_it_passes_the_focus_on_when_a_block_was_tapped(talking):
    talking.chat(subject={"kind": "article", "lexemeId": "lexemepicar0001",
                          "document": "headword: picar\n", "focus": "sense:sensepicaritch0"})
    assert "sense:sensepicaritch0" in prompts_of(talking)[0]


# ── what a bad answer is called ─────────────────────────────────────────────


def test_an_unparseable_answer_says_nothing_was_changed(talking):
    talking.model.text = "not json at all"
    answered = talking.chat()
    assert answered.status_code == 502
    assert answered.json()["error"]["code"] == "llm_unusable"
    assert answered.json()["error"]["message"].endswith("so nothing was changed.")


def test_an_answer_with_no_reply_is_unusable(talking):
    talking.model.chat = {"reply": "", "followUps": [], "proposal": dict(PROPOSAL)}
    answered = talking.chat()
    assert answered.status_code == 502
    assert answered.json()["error"]["code"] == "llm_unusable"


def test_a_rate_limited_chain_reports_itself_as_rate_limited(talking):
    talking.model.error = litellm.RateLimitError(
        message=PRIVATE, llm_provider="stub", model="gemini/gemini-3.1-flash-lite"
    )
    answered = talking.chat()
    assert answered.json()["error"]["code"] == "llm_rate_limited"
    # A provider's own error text routinely echoes the request back, key included.
    assert PRIVATE not in answered.text


def test_it_writes_nothing(talking):
    before = talking.pull().json()["data"]["cursor"]
    talking.chat()
    assert talking.pull().json()["data"]["cursor"] == before


def test_it_reads_a_nested_attestation_reference(talking):
    """A real model puts `fromAttestation` inside `example` about half the time.

    Missing it is silent: the applier would derive `origin: "llm"` for a sentence the learner
    actually met, and nothing downstream would ever notice the entry had lied about provenance.
    """
    talking.model.chat = {
        **REPLY,
        "proposal": {"summary": "…", "ops": [
            {"op": "add", "target": "attestation", "ref": "a1", "value": {"text": "Se disfrazó."}},
            {"op": "add", "target": "example", "in": "sense:kq2m7x1p4vd9r0s",
             "value": {"text": "Se disfrazó.", "fromAttestation": "a1"}},
        ]},
    }
    ops = talking.chat().json()["data"]["proposal"]["ops"]
    assert ops[1]["fromAttestation"] == "a1"
    # Lifted, not duplicated: the applier reads one place.
    assert "fromAttestation" not in ops[1]["value"]


def test_it_drops_an_add_target_it_does_not_know(talking):
    talking.model.chat = {
        **REPLY,
        "proposal": {"summary": "…", "ops": [{"op": "add", "target": "picture", "value": {}}]},
    }
    assert talking.chat().json()["data"]["proposal"] is None


def test_it_drops_a_reorder_of_something_other_than_senses(talking):
    talking.model.chat = {
        **REPLY,
        "proposal": {"summary": "…", "ops": [
            {"op": "reorder", "target": "examples", "ids": ["kq2m7x1p4vd9r0s"]}
        ]},
    }
    assert talking.chat().json()["data"]["proposal"] is None


def test_it_requires_the_parent_an_added_example_goes_into(talking):
    talking.model.chat = {
        **REPLY,
        "proposal": {"summary": "…", "ops": [
            {"op": "add", "target": "example", "value": {"text": "Se disfrazó."}}
        ]},
    }
    assert talking.chat().json()["data"]["proposal"] is None


# ── follow-ups that say nothing ─────────────────────────────────────────────


def test_it_drops_a_follow_up_that_only_agrees_with_itself(talking):
    """The prompt forbids these; this is the cap it cannot argue with.

    A follow-up is the only one-tap action there is on a phone, and "Looks good" spends it on
    nothing — there is no change to make and no question to answer.
    """
    talking.model.chat = {
        "reply": "«el traje» is any outfit.",
        "followUps": ["Looks good", "Thanks!", "Perfect.", "One more example"],
        "proposal": None,
    }
    assert talking.chat().json()["data"]["followUps"] == ["One more example"]


def test_it_keeps_a_follow_up_that_merely_starts_with_thanks(talking):
    # Whole-string only, never substring. This is the case the ban must not break.
    talking.model.chat = {
        "reply": "…",
        "followUps": ["Thanks, now add an example", "How do I remember it?"],
        "proposal": None,
    }
    assert talking.chat().json()["data"]["followUps"] == [
        "Thanks, now add an example", "How do I remember it?"
    ]
