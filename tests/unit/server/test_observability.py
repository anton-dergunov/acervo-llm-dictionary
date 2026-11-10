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
from provider_rows import GOOGLE

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
    server.add_provider(GOOGLE)
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


@pytest.mark.parametrize(("hearing", "result"), [
    (["Asco. Repulsed.", "Asco, recoiling."], "result=leaked-twice"),
    (RuntimeError("Invalid data found when processing input"), 'check="RuntimeError: Invalid data'),
], ids=["a take that spoke its direction twice", "a check that could not run"])
def test_a_take_kept_with_a_fault_is_what_admin_log_failed_shows(logs, server, monkeypatch, ear, hearing, result):
    """Both are kept — the check never fails a loop — so the line is the only place they surface."""
    server.add_provider(GOOGLE)
    from test_takes import wav

    monkeypatch.setattr("acervo.models.google_tts.speech",
                        lambda row, model, words, **_: (wav(words), "audio/wav"))
    server.push({"vocabularies": [vocabulary()]})
    if isinstance(hearing, Exception):
        ear.failure = hearing
    else:
        ear.saying = list(hearing)
    answer = server.post("/pronunciations/take",
                         {"text": "asco", "language": "es", "direction": "repulsed, recoiling slightly", "take": 0})
    assert answer.status_code == 200, answer.text

    lines(logs["call"])
    failed = activity.select(activity.entries(logs), failed=True)
    assert any("pronounce-take outcome" in text and result in text for _, _, _, text in failed), failed


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


# ── chat: an edit that could not be made is on the record, whole ─────────────


def _chat(server, turn_id: str, **overrides):
    from conftest import DEVICE

    from acervo.domain import SCHEMA_VERSION
    body = {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE,
            "subject": {"kind": "article", "lexemeId": "", "document": "headword: picar\nlanguage: es\n",
                        "focus": None},
            "turns": [{"role": "you", "text": "use mince instead of dice"}], **overrides}
    return server.client.post(f"{API}{overrides.pop('path', '/chat')}",
                              headers={**server.auth, "X-Request-ID": turn_id}, json=body)


def test_a_chat_proposal_the_server_could_not_read_is_logged_whole_under_its_turn(logs, server):
    server.push({"vocabularies": [vocabulary()]})
    server.model.chat = {"intent": "edit", "reply": "Here is a change.", "proposal": {
        "summary": "Swaps a gloss.", "ops": [{"op": "set", "target": "sense:sensepicarchop0",
                                              "value": [{"lang": "en", "terms": ["to mince"]}]}]}}
    assert _chat(server, "turnabcdefgh123").json()["data"]["proposalProblem"]
    filed = [line for line in lines(logs["call"]) if "rid=turnabcdefgh123" in line]
    outcome = next(line for line in filed if " chat outcome " in line)
    assert "result=dropped" in outcome and "intent=edit" in outcome
    assert 'problem="Operation 1 is a `set` with no `field`' in outcome
    # The answer itself, past the point a 400-character excerpt would have cut it.
    assert any(" chat answer " in line and "to mince" in line for line in filed)


def test_a_proposal_the_device_refused_is_logged_under_the_same_turn(logs, server):
    from conftest import DEVICE

    from acervo.domain import SCHEMA_VERSION
    server.push({"vocabularies": [vocabulary()]})
    server.model.chat = {"intent": "edit", "reply": "Here is a change.", "proposal": {
        "summary": "Removes it.", "ops": [{"op": "remove", "target": "example:nosuchexample01"}]}}
    sentence = "The model referred to a part of the entry that is not there, so nothing was changed."
    _chat(server, "turnzyxwvuts987", repair={"problem": sentence, "attempt": 1,
                                             "previous": {"summary": "Removes it.", "ops": []}})
    reported = server.client.post(f"{API}/chat/outcome",
                                  headers={**server.auth, "X-Request-ID": "turnzyxwvuts987"},
                                  json={"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE,
                                        "problem": sentence, "proposal": {"summary": "Removes it.",
                                                                          "ops": [{"op": "remove"}]}})
    assert reported.status_code == 200
    sent_back = [line for line in lines(logs["call"])
                 if "rid=turnzyxwvuts987" in line and " chat outcome " in line]
    assert len(sent_back) == 1 and "repair=1" in sent_back[0] and "that is not there" in sent_back[0]
    assert any(" chat sent back " in line and "Removes it." in line and "rid=turnzyxwvuts987" in line
               for line in lines(logs["call"]))
    refused = [line for line in lines(logs["act"]) if " chat proposal refused " in line]
    assert len(refused) == 1
    assert "rid=turnzyxwvuts987" in refused[0] and "that is not there" in refused[0] and "ops=1" in refused[0]


def test_a_language_list_that_cannot_be_read_is_logged_in_its_own_words(logs, server, monkeypatch):
    """`GET /languages` reads CLDR on its first call; a broken install says so in the log."""
    def broken():
        raise LookupError("no CLDR data for territory_languages")

    monkeypatch.setattr("acervo.models.locales.catalogue", broken)
    assert server.get("/languages").status_code == 500
    (line,) = refusals(logs)
    assert "path=/api/acervo/v1/languages" in line
    assert 'message="LookupError: no CLDR data for territory_languages"' in line


def test_a_story_passage_that_said_more_than_itself_is_what_admin_log_failed_shows(logs, server, monkeypatch, ear):
    """Recorded again and put right, so the story shows nothing: the line is where it surfaces."""
    from test_story_audio import narrate_reply, wav
    from test_story_jobs import Models, a_story, brief_reply, story_reply, translation_reply

    from acervo.repository import graph, image_settings, pronunciation_settings
    from acervo.work.runner import Runner
    from provider_rows import VERTEX_IMAGE

    server.add_provider(GOOGLE)
    server.add_provider(VERTEX_IMAGE)
    models = Models()
    monkeypatch.setattr("acervo.models.call.completion", lambda **kw: models.completion(**kw))
    monkeypatch.setattr("acervo.models.call.image_generation", lambda **kw: models.image_generation(**kw))
    monkeypatch.setattr("acervo.models.google_tts.speech", lambda row, model, words, **_: (wav(words), "audio/wav"))
    image_settings.save(server.owner, story_continuity="off")
    pronunciation_settings.save(server.owner, pregenerate={"stories": False})
    story = a_story(server, 2)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    Runner(server.settings).run_until_idle()
    part = graph.story_parts(server.owner, story["id"])[0]
    models.texts = [narrate_reply(part["text"])]
    ear.saying = ["Marcos vio algo asombroso, y luego se fue a su casa sin decir nada.", "Marcos vio algo asombroso."]

    answer = server.post(f"/stories/{story['id']}/parts/{part['id']}/audio", {"deviceId": "device000000001"})
    assert answer.status_code == 200, answer.text

    lines(logs["call"])
    failed = activity.select(activity.entries(logs), failed=True)
    assert any("story-audio outcome result=said-more remedy=retook" in text
               and "said more than its passage; recorded once more" in text for _, _, _, text in failed), failed


def test_a_refused_play_is_what_admin_log_shows_with_its_sentence(logs, server):
    """A play sent from a device's queue fails where nobody is watching: the line is the only witness."""
    from graph_records import play

    answer = server.push({"plays": [play()]})
    assert answer.status_code == 400
    (line,) = refusals(logs)
    assert "code=invalid_record" in line and "A play is of one loop or one story." in line
