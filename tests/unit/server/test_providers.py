"""Adding, changing, checking and removing a provider — and where its key goes.

The key check is a call to the provider, so it is stood in for here: `listing.check` answers as the
test says. What is under test is what the server does with the answer — a refused key stores
nothing and says the provider's own sentence, a working one stores the row and the secret apart —
and that the key never comes back out.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import stat

import pytest
from provider_rows import CLOUDFLARE_ACCOUNT, CLOUDFLARE_TOKEN, GEMINI_KEY, GOOGLE, SERVICE_ACCOUNT

from acervo import activity
from acervo.models import listing
from acervo.models.providers import Checked
from acervo.services import provider_secrets

NEW_KEY = "test-replacement-key-zyxwvutsrqponm"


@pytest.fixture
def checks(monkeypatch):
    """What each check says, in order; a working key by default."""
    said: list[Checked] = []
    asked: list[str] = []

    def check(provider):
        asked.append(provider.id)
        return said.pop(0) if said else Checked(True, "Works · 3 models")

    monkeypatch.setattr(listing, "check", check)
    return said, asked


def cloudflare(**changes):
    return {"family": "cloudflare", "settings": {"accountId": CLOUDFLARE_ACCOUNT},
            "models": {"text": ["@cf/meta/llama-3.3-70b-instruct-fp8-fast"],
                       "image": ["@cf/black-forest-labs/flux-2-klein-4b"]},
            "key": CLOUDFLARE_TOKEN, **changes}


def providers(server):
    return {row["id"]: row for row in server.get("/models").json()["data"]["providers"]}


# ── adding ──────────────────────────────────────────────────────────────────


def test_a_provider_whose_key_works_is_added_after_the_others(server, checks):
    answer = server.post("/providers", cloudflare())
    assert answer.status_code == 201
    added = answer.json()["data"]
    assert added["id"] == "cloudflare" and added["label"] == "Cloudflare"
    assert added["check"]["ok"] is True and added["check"]["said"] == "Works · 3 models"
    assert added["available"] is True
    assert list(providers(server)) == ["gemini-api", "cloudflare"]
    pairs = server.get("/models").json()["data"]["chains"]["text"]["pairs"]
    assert pairs[-1] == {"provider": "cloudflare", "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"}


def test_a_refused_key_stores_nothing_and_says_what_the_provider_said(server, checks, caplog):
    said, _ = checks
    said.append(Checked(False, "Cloudflare refused this key: Authentication error", "authentication"))
    caplog.set_level(logging.INFO, logger=activity.LOGGER)

    answer = server.post("/providers", cloudflare())
    assert answer.status_code == 400
    assert answer.json()["error"] == {
        "code": "key_refused",
        "message": "Cloudflare refused this key: Authentication error. Nothing was saved.",
    }
    assert "cloudflare" not in providers(server)
    assert "cloudflare" not in provider_secrets.read(server.settings)
    # What `admin log --failed` shows: the provider's own sentence, and never the key.
    line = next(record.getMessage() for record in caplog.records if "provider check" in record.getMessage())
    assert "Authentication error" in line and "reason=authentication" in line
    assert CLOUDFLARE_TOKEN not in caplog.text


def test_a_provider_that_did_not_answer_is_not_added_either(server, checks):
    said, _ = checks
    said.append(Checked(False, "Ollama did not answer: connection refused", "unreachable"))
    answer = server.post("/providers", {"family": "ollama", "models": {"text": ["llama3.3"]}})
    assert answer.status_code == 502
    assert answer.json()["error"]["code"] == "provider_check_failed"
    assert "ollama" not in providers(server)


def test_what_is_missing_is_refused_before_anything_is_asked(server, checks):
    _, asked = checks
    answer = server.post("/providers", cloudflare(settings={}))
    assert answer.status_code == 400
    assert answer.json()["error"]["message"] == "Cloudflare needs its account ID."
    answer = server.post("/providers", cloudflare(key=""))
    assert answer.json()["error"]["message"] == "Cloudflare has no API token."
    assert asked == []


@pytest.mark.parametrize(("body", "code"), [
    ({"family": "nonesuch"}, "unknown_family"),
    ({"family": "gemini-api", "id": "gemini-api", "key": GEMINI_KEY}, "provider_exists"),
    ({"family": "gemini-api", "models": {"image": ["x"]}, "key": GEMINI_KEY}, "invalid_input"),
])
def test_a_bad_provider_is_refused_with_a_code_that_says_which_mistake(server, checks, body, code):
    assert server.post("/providers", body).json()["error"]["code"] == code


def test_a_second_provider_of_one_family_is_numbered(server, checks):
    added = server.post("/providers", {"family": "gemini-api", "key": NEW_KEY,
                                       "models": {"text": ["gemini-3.5-flash-lite"]}}).json()["data"]
    assert added["id"] == "gemini-api-2"


def test_google_cloud_takes_an_uploaded_credentials_file_as_its_text(server, checks):
    added = server.post("/providers", {
        "family": "google-cloud", "id": "vertex", "settings": {"project": "example-project"},
        "credentials": json.dumps(SERVICE_ACCOUNT), "models": {"text": ["gemini-3.8-flash"]},
    }).json()["data"]
    assert added["credential"] == {"kind": "file", "hint": None, "account": SERVICE_ACCOUNT["client_email"]}


# ── where the key is ────────────────────────────────────────────────────────


def test_the_key_is_in_a_file_beside_the_database_and_never_in_it(server, checks):
    server.post("/providers", cloudflare())
    path = provider_secrets.path(server.settings)
    assert path.parent == server.settings.database_path.parent
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["cloudflare"] == {"key": CLOUDFLARE_TOKEN}
    # The database itself — and so every backup and every deploy's copy of it — holds no key.
    with sqlite3.connect(server.settings.database_path) as connection:
        dumped = "\n".join(connection.iterdump())
    assert CLOUDFLARE_TOKEN not in dumped and GEMINI_KEY not in dumped
    assert '"accountId"' in dumped


def test_no_route_ever_answers_with_a_key(server, checks):
    bodies = [server.post("/providers", cloudflare()).text,
              server.post("/providers/cloudflare/check", {}).text,
              server.put("/providers/cloudflare", {"label": "Workers AI"}).text,
              server.get("/models").text]
    for body in bodies:
        assert CLOUDFLARE_TOKEN not in body and GEMINI_KEY not in body


# ── changing and checking ───────────────────────────────────────────────────


def test_a_new_key_is_checked_before_it_replaces_the_old_one(server, checks):
    said, asked = checks
    said.append(Checked(False, "Gemini API refused this key", "authentication"))
    answer = server.put("/providers/gemini-api", {"key": NEW_KEY})
    assert answer.json()["error"]["code"] == "key_refused"
    assert provider_secrets.read(server.settings)["gemini-api"] == {"key": GEMINI_KEY}

    changed = server.put("/providers/gemini-api", {"key": NEW_KEY}).json()["data"]
    assert changed["credential"]["hint"] == f"{NEW_KEY[:4]}…{NEW_KEY[-4:]}"
    assert provider_secrets.read(server.settings)["gemini-api"] == {"key": NEW_KEY}
    assert asked == ["gemini-api", "gemini-api"]


def test_a_change_that_keeps_the_key_and_the_settings_asks_nothing(server, checks):
    _, asked = checks
    changed = server.put("/providers/gemini-api", {"label": "My Gemini"}).json()["data"]
    assert changed["label"] == "My Gemini" and asked == []


def test_a_providers_family_and_id_do_not_change(server, checks):
    assert server.put("/providers/gemini-api", {"family": "openai"}).json()["error"]["code"] == "invalid_input"
    assert server.put("/providers/gemini-api", {"id": "other"}).json()["error"]["code"] == "invalid_input"
    assert server.put("/providers/nonesuch", {"label": "x"}).json()["error"]["code"] == "unknown_provider"


def test_a_model_taken_away_leaves_every_order_and_voice_choice(server, checks):
    server.add_provider(GOOGLE)
    server.put("/models/selection", {"chains": {
        "text": [{"provider": "gemini-api", "model": "gemini-3.1-flash-lite"},
                 {"provider": "gemini-api", "model": "gemini-3.5-flash-lite"}],
        "audioPlain": [{"provider": "google-cloud", "model": "Standard"},
                       {"provider": "google-cloud", "model": "Wavenet"}],
    }})
    server.put("/pronunciations/settings", {
        "voices": {"google-cloud": {"Standard": {"es": "es-ES-Standard-F"}, "Wavenet": {"es": "es-ES-Wavenet-E"}}},
        "first": {"plain": {"es": ["google-cloud", "Standard"]}},
    })

    server.put("/providers/gemini-api", {"models": {"text": ["gemini-3.5-flash-lite"]}})
    server.put("/providers/google-cloud", {"models": {
        "audio": [m for m in GOOGLE["models"]["audio"] if m != "Standard"], "ocr": ["document-text-detection"]}})

    chains = server.get("/models").json()["data"]["chains"]
    assert chains["text"]["pairs"] == [{"provider": "gemini-api", "model": "gemini-3.5-flash-lite"}]
    assert chains["audioPlain"]["pairs"] == [{"provider": "google-cloud", "model": "Wavenet"}]
    voices = server.get("/pronunciations/settings").json()["data"]
    assert voices["voices"] == {"google-cloud": {"Wavenet": {"es": "es-ES-Wavenet-E"}}}
    assert not voices["first"].get("plain")


def test_a_check_is_kept_whatever_it_said_and_a_refused_key_is_then_skipped(server, checks):
    said, _ = checks
    said.append(Checked(False, "Gemini API refused this key", "authentication"))
    checked = server.post("/providers/gemini-api/check", {}).json()["data"]
    assert checked["check"]["ok"] is False and checked["check"]["said"] == "Gemini API refused this key"
    assert checked["available"] is False
    assert server.capture().json()["error"]["code"] == "capture_unavailable"
    assert server.model.calls == []

    server.post("/providers/gemini-api/check", {})
    assert providers(server)["gemini-api"]["available"] is True


# ── removing ────────────────────────────────────────────────────────────────


def test_removing_a_provider_takes_its_key_and_every_order_naming_it(server, checks, other):
    server.post("/providers", cloudflare())
    for account in (server, other):
        account.put("/models/selection", {"chains": {
            "text": [{"provider": "cloudflare", "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
                     {"provider": "gemini-api", "model": "gemini-3.5-flash-lite"}],
            "image": [{"provider": "cloudflare", "model": "@cf/black-forest-labs/flux-2-klein-4b"}],
        }})

    assert server.delete("/providers/cloudflare").json()["data"] == {"removed": "cloudflare"}

    assert "cloudflare" not in providers(server)
    assert "cloudflare" not in provider_secrets.read(server.settings)
    for account in (server, other):
        chains = account.get("/models").json()["data"]["chains"]
        assert chains["text"]["pairs"] == [{"provider": "gemini-api", "model": "gemini-3.5-flash-lite"}]
        # An order that named nothing else is forgotten, not switched off: removing a provider is
        # not choosing to make no pictures.
        assert chains["image"]["source"] == "default"
    assert server.delete("/providers/cloudflare").json()["error"]["code"] == "unknown_provider"


def test_every_route_needs_a_signed_in_account(server):
    for method, path in (("post", "/providers"), ("put", "/providers/x"),
                         ("post", "/providers/x/check"), ("delete", "/providers/x")):
        answer = getattr(server.client, method)(f"/api/acervo/v1{path}", **({"json": {}} if method != "delete" else {}))
        assert answer.status_code == 401
