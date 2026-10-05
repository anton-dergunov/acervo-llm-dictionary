"""When something the owner asked for does not happen, the server says why — in a file, by id.

Against the real application with its three logs pointed at a temporary directory, because the id
is stamped where a file is opened and a test that read the emitted records would never see it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from graph_records import lexeme, sense, vocabulary

from acervo import activity
from acervo.models import journal as call_journal
from acervo.repository import accounts
from acervo.tokens import ALGORITHM, mint_render, signing_key
from acervo.work import journal as job_journal

API = "/api/acervo/v1"


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """Named before `server` by every test here, so the application opens these files."""
    paths = {"call": tmp_path / "logs" / "model-calls.log", "job": tmp_path / "logs" / "jobs.log",
             "act": tmp_path / "logs" / "activity.log"}
    monkeypatch.setenv("ACERVO_CALL_LOG_PATH", str(paths["call"]))
    monkeypatch.setenv("ACERVO_JOB_LOG_PATH", str(paths["job"]))
    monkeypatch.setenv("ACERVO_ACTIVITY_LOG_PATH", str(paths["act"]))
    yield paths
    for name in (call_journal.LOGGER, job_journal.LOGGER, activity.LOGGER):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if getattr(handler, "acervo_log_file", False):
                handler.close()
                logger.removeHandler(handler)
        logger.propagate = True


def lines(path) -> list[str]:
    for name in (call_journal.LOGGER, job_journal.LOGGER, activity.LOGGER):
        for handler in logging.getLogger(name).handlers:
            handler.flush()
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def refusals(logs) -> list[str]:
    return [line for line in lines(logs["act"]) if " refused " in line]


# ── every request has an id, and says which ─────────────────────────────────


def test_a_response_says_which_request_it_was(logs, server):
    answer = server.get("/health")
    assert len(answer.headers["X-Request-ID"]) == 15
    assert answer.headers["X-Request-ID"] != server.get("/health").headers["X-Request-ID"]


def test_a_callers_own_id_is_kept_and_a_strangers_is_replaced(logs, server):
    kept = server.client.get(f"{API}/health", headers={"X-Request-ID": "abcdefghij12345"})
    assert kept.headers["X-Request-ID"] == "abcdefghij12345"
    replaced = server.client.get(f"{API}/health", headers={"X-Request-ID": "x y\tINFO forged"})
    assert replaced.headers["X-Request-ID"] != "x y\tINFO forged"
    assert len(replaced.headers["X-Request-ID"]) == 15


def test_a_browser_may_read_the_id(logs, server):
    answer = server.client.get(f"{API}/health", headers={"Origin": "acervo://app"})
    assert "x-request-id" in answer.headers["access-control-expose-headers"].lower()


# ── a refusal is written down with its sentence ─────────────────────────────


def test_a_stale_write_says_which_record_and_which_revisions_disagreed(logs, server):
    word = lexeme()
    server.push({"vocabularies": [vocabulary()]})
    server.push({"lexemes": [word], "senses": [sense(word["id"])]})
    held = server.pull().json()["data"]["changes"]["lexemes"][0]["revision"]
    answer = server.push({"lexemes": [{**word, "revision": 0, "shortGloss": "stale"}]})
    assert answer.status_code == 409

    (line,) = refusals(logs)
    assert " WARNING refused status=409 code=stale_record method=POST " in line
    assert f"path={API}/graph" in line
    assert f"collection=lexemes id={word['id']} claimed=0 stored={held} device=device000000001" in line
    assert 'message="This entry was changed somewhere else.' in line
    # The same id the response carried, so the owner's failure and this line are one thing.
    assert line.endswith(f"rid={answer.headers['X-Request-ID']}")
    # And nothing the log was told reaches the wire.
    assert answer.json() == {"error": {"code": "stale_record", "message": answer.json()["error"]["message"]}}


def test_a_request_that_succeeds_leaves_no_line(logs, server):
    server.push({"vocabularies": [vocabulary()]})
    assert refusals(logs) == []


def test_a_malformed_body_and_a_missing_route_are_refusals_too(logs, server):
    server.client.post(f"{API}/session", content=b"not json", headers={"Content-Type": "application/json"})
    server.get("/no-such-route")
    codes = [line.split("code=")[1].split()[0] for line in refusals(logs)]
    assert "not_found" in codes and len(codes) == 2


def test_a_crash_is_logged_in_its_own_words_and_answered_in_none_of_them(logs, server, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("the disk said no")

    monkeypatch.setattr("acervo.repository.graph.pull", broken)
    answer = server.pull()
    assert answer.status_code == 500
    assert "disk" not in answer.text
    (line,) = refusals(logs)
    assert " ERROR refused status=500 code=server_error " in line
    assert 'message="RuntimeError: the disk said no"' in line
    assert "rid=" in line


# ── a 401 says which 401 ────────────────────────────────────────────────────


def forged(server, **claims) -> str:
    user = accounts.by_id(server.owner)
    now = datetime.now(timezone.utc)
    body = {"sub": user["id"], "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()), **claims}
    key = claims.pop("_key", None) or signing_key(server.client.app.state.jwt_secret, user["token_key"])
    body.pop("_key", None)
    return jwt.encode(body, key, algorithm=ALGORITHM)


def reasons(logs) -> list[str]:
    return [line.split("reason=")[1].split()[0] for line in refusals(logs)]


def test_each_way_a_token_fails_is_named_and_the_caller_is_told_nothing(logs, server):
    past = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    tokens = [
        "",
        "nonsense",
        forged(server, exp=past),
        forged(server, _key=b"another key entirely, long enough to sign with"),
        forged(server, sub="nobodynobody001"),
        forged(server, aud=["acervo:pronunciations/take"]),
    ]
    bodies = []
    for token in tokens:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        answer = server.client.get(f"{API}/pronunciations/settings", headers=headers)
        assert answer.status_code == 401
        bodies.append(answer.json())

    assert reasons(logs) == ["missing", "malformed", "expired", "bad_signature", "no_account",
                             "wrong_audience"]
    assert all(body == {"error": {"code": "unauthenticated", "message": "Sign in to continue."}}
               for body in bodies)
    # A token is never in a line, whatever was wrong with it.
    assert not any(token in line for token in tokens if token for line in refusals(logs))


# ── a call home is filed under the work that asked ──────────────────────────


def test_a_take_asked_for_with_a_renders_token_is_filed_under_that_render(logs, server, monkeypatch, tmp_path):
    credentials = tmp_path / "service-account.json"
    credentials.write_text("{}")
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project-name")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(credentials))
    monkeypatch.delenv("ACERVO_VERTEX_ACCOUNT", raising=False)
    from test_takes import wav

    monkeypatch.setattr("acervo.models.google_tts.speech",
                        lambda row, model, words, **_: (wav(words), "audio/wav"))
    server.push({"vocabularies": [vocabulary()]})

    token = mint_render(server.client.app.state.jwt_secret, accounts.by_id(server.owner),
                        render="loopmorning0001", rid="jobjobjobjob001")
    answer = server.client.post(
        f"{API}/pronunciations/take", headers={"Authorization": f"Bearer {token}"},
        json={"text": "asco", "language": "es", "direction": None, "take": 0})
    assert answer.status_code == 200, answer.text

    written = lines(logs["call"])
    assert written, "the take made no model call line at all"
    assert all(line.endswith("rid=jobjobjobjob001") for line in written), written


def test_an_id_in_a_token_that_does_not_verify_is_not_taken_up(logs, server):
    token = forged(server, aud=["acervo:pronunciations/take"], rid="jobjobjobjob001",
                   _key=b"another key entirely, long enough to sign with")
    answer = server.client.post(f"{API}/pronunciations/take",
                                headers={"Authorization": f"Bearer {token}"}, json={})
    assert answer.status_code == 401
    (line,) = refusals(logs)
    assert "rid=jobjobjobjob001" not in line


# ── what the server did to the owner's files, and when it came up ───────────


def test_removing_a_media_file_leaves_a_line_and_a_file_already_gone_leaves_none(logs, server):
    from acervo.services import media

    (server.media / "images").mkdir()
    (server.media / "images" / "one.webp").write_bytes(b"picture")
    assert media.remove(server.media, "images/one.webp", "replaced") is True
    assert media.remove(server.media, "images/one.webp", "replaced") is False
    assert media.remove(server.media, None, "deleted") is False
    assert not (server.media / "images" / "one.webp").exists()
    removed = [line for line in lines(logs["act"]) if " media removed " in line]
    assert len(removed) == 1 and removed[0].endswith("media removed ref=images/one.webp reason=replaced")


def test_the_server_says_which_version_came_up(logs, server):
    with server.client:
        pass
    started, stopped = [line for line in lines(logs["act"]) if " server " in line]
    assert "server start version=1.4.2 build=218" in started
    assert "server stop version=1.4.2 build=218" in stopped
