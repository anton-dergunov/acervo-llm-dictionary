"""Settings ▸ Providers, on the server: the orders the owner may choose, and what they may never see.

Three things here are load-bearing beyond the obvious. The orders are owner-scoped, so one account's
choice must be invisible to another. They are *not* replicated, and the failure mode of getting that
wrong is silent — the record would simply start appearing in every device's replica. And the route
serves providers whose keys the server holds, so what it leaves out matters as much as what it
returns. Adding, checking and removing a provider is `test_providers.py`.
"""

from __future__ import annotations

import json

import pytest
from graph_records import vocabulary
from provider_rows import CLOUDFLARE, CLOUDFLARE_ACCOUNT, CLOUDFLARE_TOKEN, GEMINI_KEY, GOOGLE, VERTEX

from acervo.domain.projection import COLLECTIONS

GEMINI = "gemini-3.5-flash-lite"
GEMINI_SECOND = "gemini-3.1-flash-lite"
LLAMA = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def models(server):
    return server.get("/models").json()["data"]


def choose(server, chains):
    return server.client.put(
        "/api/acervo/v1/models/selection", headers=server.auth, json={"chains": chains}
    )


def pair(provider, model):
    return {"provider": provider, "model": model}


@pytest.fixture
def cloudflare(server):
    """A second provider, so a chain has somewhere to go."""
    server.add_provider(CLOUDFLARE)


# ── what the owner is shown ─────────────────────────────────────────────────


def test_both_routes_need_a_signed_in_owner(server):
    assert server.client.get("/api/acervo/v1/models").status_code == 401
    assert server.client.put("/api/acervo/v1/models/selection", json={"chains": {}}).status_code == 401


def test_with_no_record_every_kind_follows_the_providers_own_order(server):
    readout = models(server)
    assert {kind: chain["source"] for kind, chain in readout["chains"].items()} == {
        "text": "default", "quick": "default", "image": "default",
        "audioPlain": "default", "audioExpressive": "default", "ocr": "default",
    }
    assert readout["chains"]["text"]["pairs"] == [
        pair("gemini-api", GEMINI), pair("gemini-api", GEMINI_SECOND)
    ]


def test_the_default_order_is_the_order_providers_and_their_models_were_added(server, cloudflare):
    assert models(server)["chains"]["text"]["pairs"] == [
        pair("gemini-api", GEMINI), pair("gemini-api", GEMINI_SECOND), pair("cloudflare", LLAMA),
    ]


def test_the_expressive_default_holds_only_voices_that_take_a_direction(server):
    server.add_provider(GOOGLE)
    readout = models(server)["chains"]
    assert readout["audioPlain"]["pairs"][:2] == [pair("google-cloud", "Wavenet"), pair("google-cloud", "Standard")]
    assert readout["audioExpressive"]["pairs"] == [
        pair("google-cloud", "gemini-3.1-flash-tts-preview"), pair("google-cloud", "gemini-2.5-flash-tts"),
    ]


def test_a_server_with_no_provider_says_so_for_every_kind(server):
    server.remove_provider("gemini-api")
    readout = models(server)
    assert readout["providers"] == []
    assert readout["chains"]["text"]["reason"] == "no provider is added for text"
    assert readout["chains"]["ocr"]["reason"] == "no provider is added for reading photos"


def test_it_lists_the_families_a_provider_can_be_added_from(server):
    families = {family["id"]: family for family in models(server)["families"]}
    assert {"gemini-api", "google-cloud", "cloudflare", "openai-compatible"} <= set(families)
    assert families["cloudflare"]["fields"][0]["name"] == "accountId"
    assert families["google-cloud"]["credential"] == "key-or-file"
    assert families["google-cloud"]["fileOnly"] == ["text", "image"]


def test_a_provider_offers_its_models_per_kind_because_the_choice_is_a_pair(server):
    server.add_provider(GOOGLE)
    rows = {row["id"]: row for row in models(server)["providers"]}
    assert rows["gemini-api"]["models"]["text"] == [{"id": GEMINI}, {"id": GEMINI_SECOND}]
    assert {"id": "gemini-2.5-flash-tts", "direction": True} in rows["google-cloud"]["models"]["audio"]
    assert {"id": "Wavenet"} in rows["google-cloud"]["models"]["audio"]


def test_it_says_where_to_read_the_usage(server, cloudflare):
    rows = {row["id"]: row for row in models(server)["providers"]}
    assert rows["gemini-api"]["usageUrl"].startswith("https://aistudio.google.com/")
    assert rows["cloudflare"]["usageUrl"] == f"https://dash.cloudflare.com/{CLOUDFLARE_ACCOUNT}/ai/workers-ai"


def test_it_never_returns_a_key_or_a_credentials_file(server, cloudflare):
    """Asserted on the whole body, not on named fields: the failure guarded against is a field
    somebody adds later. The Cloudflare account id is a setting the owner typed and is shown."""
    server.add_provider(VERTEX)
    body = server.get("/models").text
    for secret in (GEMINI_KEY, CLOUDFLARE_TOKEN, "test-private-key-material", "pkid-9f8e7d6c5b4a3210"):
        assert secret not in body
    for field in ("\"private_key\"", "\"api_key\"", "vertex_credentials", "refresh_token"):
        assert field not in body
    assert CLOUDFLARE_ACCOUNT in body


def test_a_key_is_shown_as_four_characters_at_each_end_and_never_more(server):
    """"A key is set" and "*that* key is set" are different answers, and only the second one closes a
    half-finished rotation or tells two accounts apart. The test above is what stops this widening."""
    row = next(row for row in models(server)["providers"] if row["id"] == "gemini-api")
    assert row["credential"] == {"kind": "key", "hint": "test…mnop", "account": None}


def test_a_key_too_short_to_abbreviate_is_reported_as_present_and_not_shown(server):
    from provider_rows import GEMINI as DOCUMENT

    server.add_provider(DOCUMENT, {"key": "short-key"})
    row = next(row for row in models(server)["providers"] if row["id"] == "gemini-api")
    assert row["credential"]["kind"] == "key" and row["credential"]["hint"] == "…"


def test_a_credentials_file_is_shown_as_the_account_it_names(server):
    server.add_provider(VERTEX)
    row = next(row for row in models(server)["providers"] if row["id"] == "vertex")
    assert row["credential"] == {
        "kind": "file", "hint": None, "account": "acervo@project.example.com",
    }
    assert row["settings"] == {"project": "example-project"}


def test_a_provider_whose_key_was_refused_is_shown_and_skipped(server, cloudflare):
    server.add_provider(CLOUDFLARE, check={"ok": False, "said": "Cloudflare refused this key",
                                           "reason": "authentication", "account": None})
    readout = models(server)
    row = next(row for row in readout["providers"] if row["id"] == "cloudflare")
    assert row["available"] is False
    assert row["reason"] == "Cloudflare refused its key when it was last checked"
    assert row["check"]["ok"] is False and row["check"]["said"] == "Cloudflare refused this key"
    # The order with nothing chosen is what will be walked, and that skips it.
    assert pair("cloudflare", LLAMA) not in readout["chains"]["text"]["pairs"]


# ── choosing ────────────────────────────────────────────────────────────────


def test_a_saved_chain_becomes_the_owners_and_survives_a_reread(server, cloudflare):
    answer = choose(server, {"text": [pair("cloudflare", LLAMA), pair("gemini-api", GEMINI)]})
    assert answer.status_code == 200
    text = answer.json()["data"]["chains"]["text"]
    assert text["source"] == "owner"
    assert text["pairs"] == [pair("cloudflare", LLAMA), pair("gemini-api", GEMINI)]
    assert models(server)["chains"]["text"] == text


def test_only_the_kinds_named_change(server, cloudflare):
    choose(server, {"text": [pair("cloudflare", LLAMA)]})
    readout = models(server)
    assert readout["chains"]["text"]["source"] == "owner"
    assert readout["chains"]["audioPlain"]["source"] == "default"


def test_the_owner_may_pin_one_model_of_a_provider(server):
    """A provider offers two free-tier buckets and the owner picks one."""
    choose(server, {"text": [pair("gemini-api", GEMINI_SECOND)]})
    assert models(server)["chains"]["text"]["pairs"] == [pair("gemini-api", GEMINI_SECOND)]


def test_switching_every_model_off_is_a_choice_and_not_an_absence(server):
    """Three states, not two. Refusing this left no way to say "do not build entries at all"."""
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


def test_forgetting_a_kind_returns_it_to_the_providers_own_order(server):
    choose(server, {"text": [pair("gemini-api", GEMINI_SECOND)]})
    assert models(server)["chains"]["text"]["source"] == "owner"
    choose(server, {"text": None})
    readout = models(server)["chains"]["text"]
    assert readout["source"] == "default"
    assert readout["pairs"] == [pair("gemini-api", GEMINI), pair("gemini-api", GEMINI_SECOND)]


def test_a_pair_whose_key_was_refused_is_kept_and_skipped_when_the_chain_is_walked(server, cloudflare):
    """A chain is an owner preference; a working key is a fact about the provider, and one must not
    destroy the other. Refusing this would mean a refused key locked the owner out of reordering."""
    choose(server, {"text": [pair("cloudflare", LLAMA), pair("gemini-api", GEMINI)]})
    server.add_provider(CLOUDFLARE, check={"ok": False, "said": "no", "reason": "authentication",
                                           "account": None})
    readout = models(server)
    assert readout["chains"]["text"]["pairs"][0] == pair("cloudflare", LLAMA)
    assert choose(server, {"text": [pair("gemini-api", GEMINI), pair("cloudflare", LLAMA)]}).status_code == 200
    server.capture()
    assert [call["model"] for call in server.model.calls][:1] == [f"gemini/{GEMINI}"]


# ── refusals ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("chains", "code"),
    [
        ({}, "invalid_input"),
        ({"text": "gemini-api"}, "invalid_input"),
        ({"text": [{"provider": "gemini-api"}]}, "invalid_input"),
        ({"vibes": [pair("gemini-api", GEMINI)]}, "unsupported_kind"),
        ({"image": [pair("gemini-api", GEMINI)]}, "unsupported_kind"),
        ({"text": [pair("nonesuch", GEMINI)]}, "unknown_provider"),
        ({"text": [pair("gemini-api", "retired-last-year")]}, "unknown_model"),
        ({"text": [pair("gemini-api", GEMINI), pair("gemini-api", GEMINI)]}, "duplicate_pair"),
    ],
)
def test_a_bad_selection_is_refused_with_a_code_that_says_which_mistake(server, chains, code):
    answer = choose(server, chains)
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == code


def test_a_refusal_leaves_the_stored_chain_untouched(server, cloudflare):
    """Every kind is validated before anything is written."""
    choose(server, {"text": [pair("cloudflare", LLAMA)]})
    answer = choose(server, {
        "text": [pair("gemini-api", GEMINI)],
        "audioPlain": [pair("cloudflare", "retired-last-year")],
    })
    assert answer.json()["error"]["code"] == "unknown_model"
    assert models(server)["chains"]["text"]["pairs"] == [pair("cloudflare", LLAMA)]


def test_an_expressive_order_naming_a_voice_that_takes_no_direction_is_kept_as_saved(server):
    """A preference the walk skips, not a mistake to refuse: the order is kept exactly as saved."""
    server.add_provider(GOOGLE)
    choose(server, {"audioExpressive": [pair("google-cloud", "Wavenet"), pair("google-cloud", "gemini-2.5-flash-tts")]})
    stored = models(server)["chains"]["audioExpressive"]
    assert stored["source"] == "owner"
    assert stored["pairs"] == [pair("google-cloud", "Wavenet"), pair("google-cloud", "gemini-2.5-flash-tts")]


def test_a_speech_chain_takes_only_speech_models(server, cloudflare):
    answer = choose(server, {"audioPlain": [pair("cloudflare", LLAMA)]})
    assert answer.json()["error"]["code"] == "unknown_model"
    answer = choose(server, {"audioPlain": [pair("gemini-api", GEMINI)]})
    assert answer.json()["error"]["code"] == "unsupported_kind"


def test_one_owners_chain_is_invisible_to_another(server, other):
    choose(server, {"text": [pair("gemini-api", GEMINI_SECOND)]})
    assert models(server)["chains"]["text"]["source"] == "owner"
    assert models(other)["chains"]["text"]["source"] == "default"


# ── it is not vocabulary ────────────────────────────────────────────────────


@pytest.mark.parametrize("table", ["model_selection", "providers"])
def test_neither_table_is_a_replicated_collection(table):
    """The failure mode is silent: it would simply start appearing in every device's replica.
    Asserted against `COLLECTIONS`, which is what `graph.pull` iterates."""
    from acervo.db import tables

    assert table not in {collection.name for collection in COLLECTIONS}
    assert not set(getattr(tables, table).c.keys()) & {"revision", "deleted", "edited_by"}
    assert table not in tables.REPLICATED


def test_a_saved_chain_never_reaches_the_graph(server, cloudflare):
    """End to end, which is the assertion that would actually catch a regression."""
    server.push({"vocabularies": [vocabulary(language="es")]})
    choose(server, {"text": [pair("cloudflare", LLAMA)]})
    body = json.dumps(server.pull().json())
    assert "cloudflare" not in body
    assert LLAMA not in body
