"""Settings ▸ Models, on the server: what the owner may choose, and what they may never see.

Three things here are load-bearing beyond the obvious. The route is owner-scoped, so one account's
choice must be invisible to another. It is *not* replicated, and the failure mode of getting that
wrong is silent — the record would simply start appearing in every device's replica. And it serves a
catalogue that knows every credential this server holds, so what it leaves out matters as much as
what it returns.
"""

from __future__ import annotations

import json

import pytest
from graph_records import vocabulary

from acervo.domain.projection import COLLECTIONS

GEMINI = "gemini/gemini-3.5-flash-lite"
GEMINI_SECOND = "gemini/gemini-3.1-flash-lite"
CLOUDFLARE = "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast"
ACCOUNT_ID = "0123456789abcdef0123456789abcdef"


def models(server):
    return server.get("/models").json()["data"]


def choose(server, chains):
    return server.client.put(
        "/api/acervo/v1/models/selection", headers=server.auth, json={"chains": chains}
    )


def pair(provider, model):
    return {"provider": provider, "model": model}


@pytest.fixture
def cloudflare(monkeypatch):
    """A second credentialed row, so a chain has somewhere to go."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cloudflare-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_ID)


# ── what the owner is shown ─────────────────────────────────────────────────


def test_both_routes_need_a_signed_in_owner(server):
    assert server.client.get("/api/acervo/v1/models").status_code == 401
    assert server.client.put("/api/acervo/v1/models/selection", json={"chains": {}}).status_code == 401


def test_with_no_record_every_kind_follows_the_deployment(server):
    readout = models(server)
    assert {kind: chain["source"] for kind, chain in readout["chains"].items()} == {
        "text": "deployment", "quick": "deployment", "image": "deployment",
        "audioPlain": "deployment", "audioExpressive": "deployment", "ocr": "deployment",
    }
    assert readout["chains"]["text"]["pairs"] == [
        pair("gemini-free", GEMINI), pair("gemini-free", GEMINI_SECOND)
    ]


def test_it_lists_every_row_including_the_ones_this_server_cannot_use(server):
    """"Why can I not pick Cloudflare" is a question the interface should answer without a shell."""
    rows = {row["id"]: row for row in models(server)["providers"]}
    assert set(rows) == {
        "gemini-free", "vertex", "google-tts", "google-vision", "cloudflare", "openai", "openrouter",
        "ollama-local",
    }
    assert rows["gemini-free"]["available"] is True and rows["gemini-free"]["reason"] is None
    assert rows["cloudflare"]["available"] is False
    assert rows["cloudflare"]["reason"] == "CLOUDFLARE_API_TOKEN is not set"


def test_a_row_offers_its_models_per_kind_because_the_choice_is_a_pair(server):
    rows = {row["id"]: row for row in models(server)["providers"]}
    assert rows["gemini-free"]["models"]["text"] == [GEMINI, GEMINI_SECOND]
    assert "image" not in rows["gemini-free"]["models"]  # that tier is allowed no image requests


def test_it_says_where_to_read_the_usage(server, cloudflare):
    rows = {row["id"]: row for row in models(server)["providers"]}
    assert rows["gemini-free"]["usageUrl"].startswith("https://aistudio.google.com/")
    assert rows["cloudflare"]["usageUrl"] == f"https://dash.cloudflare.com/{ACCOUNT_ID}/ai/workers-ai"
    assert rows["ollama-local"]["usageUrl"] is None  # no bill, nowhere to read one


def test_it_never_returns_a_key_or_how_a_provider_is_reached(server, cloudflare, monkeypatch):
    """Asserted on the whole body, not on named fields: the failure guarded against is a field
    somebody adds later.

    `usageUrl` deliberately carries the Cloudflare account id — that is what makes the link point at
    the right dashboard, this route is authenticated, and the account is the owner's own. A *key*
    may never appear anywhere, and `catalogue._validate` already refuses a row that puts one in
    either URL.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "a-very-secret-gemini-key")
    body = server.get("/models").text
    for secret in ("a-very-secret-gemini-key", "cloudflare-token", "stub-key"):
        assert secret not in body
    for field in ("keyEnv", "baseUrl", "requires", "passes", "params", "litellm", "adapter"):
        assert f'"{field}"' not in body
    # The one interpolated value, and only inside the link it belongs to.
    assert ACCOUNT_ID in body
    assert all(ACCOUNT_ID in row["usageUrl"] for row in models(server)["providers"]
               if row["id"] == "cloudflare")


def test_a_key_is_shown_as_four_characters_at_each_end_and_never_more(server, monkeypatch):
    """The one deliberate relaxation of the rule above, and its bound.

    "A key is set" and "*that* key is set" are different answers, and only the second one closes a
    half-finished rotation or tells two accounts apart. Four characters at each end of a long token
    is enough to match against the provider's own dashboard by eye and is not a credential. The
    test above is what stops this widening: it asserts the *whole* value is absent, on the whole
    body, so any future field that carries more fails there.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyC1234567890abcdefghijklmnop")
    row = next(row for row in models(server)["providers"] if row["id"] == "gemini-free")
    assert row["credential"] == {
        "kind": "key", "variable": "GEMINI_API_KEY", "present": True, "hint": "AIza…mnop"
    }


def test_a_key_too_short_to_abbreviate_is_reported_as_present_and_not_shown(server, monkeypatch):
    """Nothing Acervo talks to issues a key this short; the guard is against a row added later."""
    monkeypatch.setenv("GEMINI_API_KEY", "short-key")
    row = next(row for row in models(server)["providers"] if row["id"] == "gemini-free")
    assert row["credential"]["present"] is True
    assert row["credential"]["hint"] == "…"


def test_a_provider_with_no_credential_names_the_variable_it_wants(server, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    row = next(row for row in models(server)["providers"] if row["id"] == "gemini-free")
    assert row["credential"] == {
        "kind": "key", "variable": "GEMINI_API_KEY", "present": False, "hint": None
    }


def test_the_settings_shown_are_the_row_s_own_deployment_facts(server, cloudflare):
    """The project, the account id, the local URL — what tells one deployment from another. They
    are shown in full, which `catalogue._validate` makes safe by refusing a row that lists its key
    among them."""
    row = next(row for row in models(server)["providers"] if row["id"] == "cloudflare")
    assert row["settings"] == [{"name": "CLOUDFLARE_ACCOUNT_ID", "value": ACCOUNT_ID}]


def test_a_mistyped_deployment_chain_renders_a_reason_rather_than_failing_the_pane(server, monkeypatch):
    monkeypatch.setattr(server.settings, "text_chain", "nonesuch")
    readout = models(server)
    assert readout["chains"]["text"]["pairs"] == []
    assert "nonesuch" in readout["chains"]["text"]["reason"]


# ── choosing ────────────────────────────────────────────────────────────────


def test_a_saved_chain_becomes_the_owners_and_survives_a_reread(server, cloudflare):
    answer = choose(server, {"text": [pair("cloudflare", CLOUDFLARE), pair("gemini-free", GEMINI)]})
    assert answer.status_code == 200
    text = answer.json()["data"]["chains"]["text"]
    assert text["source"] == "owner"
    assert text["pairs"] == [pair("cloudflare", CLOUDFLARE), pair("gemini-free", GEMINI)]
    assert models(server)["chains"]["text"] == text


def test_only_the_kinds_named_change(server, cloudflare):
    choose(server, {"text": [pair("cloudflare", CLOUDFLARE)]})
    readout = models(server)
    assert readout["chains"]["text"]["source"] == "owner"
    assert readout["chains"]["audioPlain"]["source"] == "deployment"


def test_the_owner_may_pin_one_model_of_a_row(server):
    """A row offers two free-tier buckets and the owner picks one."""
    choose(server, {"text": [pair("gemini-free", GEMINI_SECOND)]})
    assert models(server)["chains"]["text"]["pairs"] == [pair("gemini-free", GEMINI_SECOND)]


def test_switching_every_model_off_is_a_choice_and_not_an_absence(server):
    """Three states, not two. Refusing this left no way to say "do not build entries at all", and
    made unticking the last model bounce back to the server's order while entries kept being made."""
    answer = choose(server, {"text": []})
    assert answer.status_code == 200

    readout = models(server)["chains"]["text"]
    assert readout["source"] == "owner"
    assert readout["pairs"] == []
    assert readout["reason"] == "no model is switched on for text"


def test_capture_refuses_while_every_model_is_switched_off(server):
    choose(server, {"text": []})
    answer = server.capture()
    assert answer.status_code >= 400
    assert answer.json()["error"]["message"] == "no model is switched on for text"
    assert server.model.calls == []


def test_forgetting_a_kind_returns_it_to_the_deployment(server):
    """Without this there is no way back: unchecking everything is refused as an empty chain, so a
    single choice would be a one-way door out of following the server's own order."""
    choose(server, {"text": [pair("gemini-free", GEMINI_SECOND)]})
    assert models(server)["chains"]["text"]["source"] == "owner"

    choose(server, {"text": None})
    readout = models(server)["chains"]["text"]
    assert readout["source"] == "deployment"
    assert readout["pairs"] == [pair("gemini-free", GEMINI), pair("gemini-free", GEMINI_SECOND)]


def test_an_unavailable_pair_may_be_kept_and_is_simply_skipped_when_the_chain_is_walked(server, cloudflare, monkeypatch):
    """A chain is an owner preference; a credential is deployment state, and one must not destroy
    the other. Refusing this would mean a rotated key locked the owner out of reordering at all."""
    choose(server, {"text": [pair("cloudflare", CLOUDFLARE), pair("gemini-free", GEMINI)]})
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")

    readout = models(server)
    # Still stored, still first, and marked so the interface can say why it will be passed over.
    assert readout["chains"]["text"]["pairs"][0] == pair("cloudflare", CLOUDFLARE)
    rows = {row["id"]: row for row in readout["providers"]}
    assert rows["cloudflare"]["available"] is False
    # And the owner can still reorder that kind, which is the trap this avoids.
    assert choose(server, {"text": [pair("gemini-free", GEMINI), pair("cloudflare", CLOUDFLARE)]}).status_code == 200


# ── refusals ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("chains", "code"),
    [
        ({}, "invalid_input"),
        ({"text": "gemini-free"}, "invalid_input"),
        ({"text": [{"provider": "gemini-free"}]}, "invalid_input"),
        ({"vibes": [pair("gemini-free", GEMINI)]}, "unsupported_kind"),
        ({"image": [pair("openrouter", "openrouter/meta-llama/llama-3.3-70b-instruct")]}, "unsupported_kind"),
        ({"text": [pair("nonesuch", GEMINI)]}, "unknown_provider"),
        ({"text": [pair("gemini-free", "gemini/retired-last-year")]}, "unknown_model"),
        ({"text": [pair("gemini-free", GEMINI), pair("gemini-free", GEMINI)]}, "duplicate_pair"),
    ],
)
def test_a_bad_selection_is_refused_with_a_code_that_says_which_mistake(server, chains, code):
    answer = choose(server, chains)
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == code


def test_a_refusal_leaves_the_stored_chain_untouched(server, cloudflare):
    """Every kind is validated before anything is written, so a bad second kind cannot leave the
    first one stored."""
    choose(server, {"text": [pair("cloudflare", CLOUDFLARE)]})
    answer = choose(server, {
        "text": [pair("gemini-free", GEMINI)],
        "audioPlain": [pair("google-tts", "retired-last-year")],
    })
    assert answer.json()["error"]["code"] == "unknown_model"
    assert models(server)["chains"]["text"]["pairs"] == [pair("cloudflare", CLOUDFLARE)]


def test_the_two_speech_chains_start_from_the_catalogues_recommended_orders(server):
    """A headword wants a clear free voice and an example a voice that can take its emotion, so
    neither follows plain catalogue order — which would read a headword with a paid Gemini voice."""
    from acervo.services.models import deployment_chain

    assert deployment_chain(server.settings, "audioPlain")[0] == ("google-tts", "wavenet")
    assert deployment_chain(server.settings, "audioExpressive")[0] == ("google-tts", "gemini-3.1-flash-tts-preview")
    # A voice that cannot take a direction is a preference the walk skips, not a mistake to refuse:
    # the order is kept exactly as saved.
    choose(server, {"audioExpressive": [pair("google-tts", "wavenet"), pair("google-tts", "gemini-2.5-flash-tts")]})
    stored = models(server)["chains"]["audioExpressive"]
    assert stored["source"] == "owner"
    assert stored["pairs"] == [pair("google-tts", "wavenet"), pair("google-tts", "gemini-2.5-flash-tts")]


def test_each_speech_model_says_whether_it_takes_a_direction(server):
    """What Settings ▸ Providers offers for the expressive order is read from this."""
    providers = {provider["id"]: provider for provider in models(server)["providers"]}
    assert providers["google-tts"]["styles"]["wavenet"] == "none"
    assert providers["google-tts"]["styles"]["gemini-3.1-flash-tts-preview"] == "instruction"
    assert providers["gemini-free"]["styles"] == {}


def test_a_speech_chain_takes_only_speech_models(server):
    answer = choose(server, {"audioPlain": [pair("openai", "openai/gpt-5.1")]})
    assert answer.json()["error"]["code"] == "unknown_model"
    # And a row that no longer speaks at all is refused for the kind.
    answer = choose(server, {"audioPlain": [pair("gemini-free", GEMINI)]})
    assert answer.json()["error"]["code"] == "unsupported_kind"


def test_one_owners_chain_is_invisible_to_another(server, other):
    choose(server, {"text": [pair("gemini-free", GEMINI_SECOND)]})
    assert models(server)["chains"]["text"]["source"] == "owner"
    assert models(other)["chains"]["text"]["source"] == "deployment"


# ── it is not vocabulary ────────────────────────────────────────────────────


def test_the_selection_is_not_a_replicated_collection():
    """The failure mode is silent: it would simply start appearing in every device's replica.

    Asserted against `COLLECTIONS`, which is what `graph.pull` iterates. `tables.REPLICATED` is
    declared and never read, so a test against it would prove nothing.
    """
    assert "model_selection" not in {collection.name for collection in COLLECTIONS}


def test_the_table_cannot_be_replicated_even_if_someone_listed_it():
    """No `revision` to order by and no `deleted` to tombstone with — structural, not a convention."""
    from acervo.db import tables

    columns = set(tables.model_selection.c.keys())
    assert not columns & {"revision", "deleted", "edited_by"}
    assert "model_selection" not in tables.REPLICATED


def test_a_saved_chain_never_reaches_the_graph(server, cloudflare):
    """End to end, which is the assertion that would actually catch a regression."""
    server.push({"vocabularies": [vocabulary(language="es")]})
    choose(server, {"text": [pair("cloudflare", CLOUDFLARE)]})
    body = json.dumps(server.pull().json())
    assert "cloudflare" not in body
    assert CLOUDFLARE not in body
