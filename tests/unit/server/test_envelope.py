"""Every response is `{data}` or `{error}`, and a 500 says nothing about itself.

The client treats *any* body without `data` as a generic failure, so FastAPI's own `{"detail": …}`
reaching it would turn a stateable refusal into "something went wrong".
"""

from __future__ import annotations

import pytest

from graph_records import DEVICE, lexeme, vocabulary
from acervo.domain import SCHEMA_VERSION


def test_a_refusal_carries_a_code_and_a_message_the_owner_can_act_on(server):
    answer = server.post("/graph/reset", {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "confirm": "yes"})
    assert answer.status_code == 400
    assert answer.json() == {
        "error": {
            "code": "confirmation_required",
            "message": "This request must confirm that all words are to be deleted.",
        }
    }


def test_an_unsigned_request_is_401_and_an_unknown_route_is_404(server):
    anonymous = server.client.get(f"/api/acervo/v1/graph?schemaVersion={SCHEMA_VERSION}&since=0")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "unauthenticated"

    missing = server.get("/nowhere")
    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": "not_found",
        "message": "The requested Acervo API route does not exist.",
    }


def test_an_out_of_date_client_is_409_rather_than_a_confusing_failure(server):
    answer = server.get("/graph?schemaVersion=999&since=0")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "schema_version_mismatch"


def test_an_unreadable_body_fails_on_the_field_it_lacks_not_on_the_parser(server):
    answer = server.client.post(
        "/api/acervo/v1/graph",
        headers={**server.auth, "content-type": "application/json"},
        content=b"{not json",
    )
    assert answer.status_code == 409  # schemaVersion is missing, which is the first thing checked
    assert "data" not in answer.json()


def test_an_unhandled_failure_keeps_its_internals_off_the_wire(server, monkeypatch):
    from acervo.repository import graph

    def explode(*_args, **_kwargs):
        raise RuntimeError("the connection string is postgres://someone:hunter2@internal")

    monkeypatch.setattr(graph, "pull", explode)
    answer = server.pull()
    assert answer.status_code == 500
    assert answer.json() == {
        "error": {"code": "server_error", "message": "The Acervo server could not complete the request."}
    }
    assert "hunter2" not in answer.text


@pytest.mark.parametrize("origin", ["acervo://app", "https://acervo.example.com"])
def test_the_macos_host_gets_the_cors_headers_its_preflight_needs(server, origin):
    """Without these every call fails inside the browser with no server-side log, and the client
    reports it as "the server could not be reached" — the wrong diagnosis entirely."""
    preflight = server.client.options(
        "/api/acervo/v1/graph",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "*"

    answered = server.client.get("/api/acervo/v1/health", headers={"Origin": origin})
    assert answered.headers["access-control-allow-origin"] == "*"


def test_a_malformed_record_names_the_collection_and_the_id(server):
    word = lexeme(language="zh-Hans", reading=None)
    answer = server.push({"vocabularies": [vocabulary(language="zh-Hans", definitionLang="en")], "lexemes": [word]})
    assert answer.status_code == 400
    error = answer.json()["error"]
    assert error["code"] == "invalid_record"
    assert error["message"] == f"lexemes {word['id']}: Chinese lexemes require a reading."
