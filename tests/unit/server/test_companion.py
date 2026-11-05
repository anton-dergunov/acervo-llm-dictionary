"""`POST /companion/text`: the clip service calling home, so its container holds no key.

It is authenticated by the operator token the two already share, walks the providers in the order
they were added — the clip service's job has no owner — and answers in Acervo's envelope, with the
same refusal codes every other model call has. The client half is `tests/unit/speech/`.
"""

from __future__ import annotations

import json

import pytest

TOKEN = "an-operator-token-0123456789abcdef"
ROUTE = "/api/acervo/v1/companion/text"
REQUEST_ID = "clipclipclip001"


@pytest.fixture
def home(server, monkeypatch):
    monkeypatch.setattr(server.settings, "speech_operator_token", TOKEN)
    return server


def ask(server, body=None, token=TOKEN, **headers):
    return server.client.post(ROUTE, json=body if body is not None else {
        "instructions": "Translate it. Return a single JSON object.", "text": "me pica",
        "caller": "clip-translate", "temperature": 0.2,
    }, headers={"Authorization": f"Bearer {token}", **headers})


def test_it_answers_with_the_parsed_object_and_who_wrote_it(home):
    home.model.resolution = {"target_text": "it itches"}
    answer = ask(home)
    assert answer.status_code == 200, answer.text
    data = answer.json()["data"]
    assert isinstance(data["payload"], dict)
    assert (data["provider"], data["model"]) == ("gemini-api", "gemini-3.5-flash-lite")
    call = home.model.calls[-1]
    assert call["response_format"] == {"type": "json_object"}
    assert call["temperature"] == 0.2
    assert call["messages"][0]["content"].startswith("Translate it.")
    assert call["messages"][-1]["content"] == "me pica"


def test_it_walks_the_providers_own_order_whatever_an_owner_chose(home):
    """No owner: the call comes from the clip service's own job, long after any reader's request."""
    home.put("/models/selection", {"chains": {"text": [{"provider": "gemini-api", "model": "gemini-3.1-flash-lite"}]}})
    ask(home)
    assert home.model.calls[-1]["model"] == "gemini/gemini-3.5-flash-lite"


@pytest.mark.parametrize("token", ["", "a-wrong-token"])
def test_it_needs_the_operator_token(home, token):
    answer = ask(home, token=token)
    assert answer.status_code == 401
    assert home.model.calls == []


def test_a_session_is_not_enough(home):
    """It is a route for a service, not for a reader: an owner's session does not open it."""
    answer = home.client.post(ROUTE, json={"instructions": "x", "text": "y"}, headers=home.auth)
    assert answer.status_code == 401


def test_a_server_with_no_operator_token_refuses_everyone(server):
    assert ask(server, token="").status_code == 401
    assert ask(server, token="anything").status_code == 401


def test_the_callers_request_id_files_the_model_call(home, caplog):
    import logging

    from acervo.models import journal

    caplog.set_level(logging.INFO, logger=journal.LOGGER)
    answer = ask(home, **{"X-Request-ID": REQUEST_ID})
    assert answer.headers["X-Request-ID"] == REQUEST_ID
    assert any("clip-translate" in record.getMessage() for record in caplog.records)


def test_a_refusal_carries_the_same_codes_as_every_other_model_call(home):
    home.remove_provider("gemini-api")
    answer = ask(home)
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "capture_unavailable"


@pytest.mark.parametrize("body", [{}, {"instructions": "", "text": "x"}, {"instructions": "x"}])
def test_a_call_without_instructions_and_text_is_refused(home, body):
    answer = ask(home, body)
    assert answer.status_code == 400
    assert json.loads(answer.text)["error"]["code"] == "invalid_input"
