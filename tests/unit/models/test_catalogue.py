"""The catalogue is data, so what can go wrong with it is a schema question.

`models/catalogue.json` is tracked and public. Two of these tests are about that rather than about
correctness: no row may carry a credential, and no `baseUrl` may interpolate one.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from acervo.models.catalogue import (
    CATALOGUE_PATH,
    _PLACEHOLDER,
    CatalogueError,
    Row,
    available,
    base_url,
    load_catalogue,
    identity,
    key_hint,
    reason,
    row_settings,
    usage_url,
)

SHIPPED = load_catalogue()


def written(tmp_path, *providers):
    path = tmp_path / "catalogue.json"
    path.write_text(
        json.dumps({"version": 1, "note": "test", "providers": list(providers)}), encoding="utf-8"
    )
    return path


def a_row(**overrides):
    return {
        "id": "row",
        "label": "Row",
        "kinds": ["text"],
        "litellm": {"text": ["gemini/x"]},
        "keyEnv": "A_KEY",
        **overrides,
    }


def test_every_shipped_row_names_a_model_or_an_adapter_for_every_kind_it_declares():
    """Every row has one, in the form a row with three kinds actually needs.

    A scalar `litellm` field could not have said this: a row serving text, image and audio names
    different models for each, Cloudflare reaches two of those three through the adapter, and a kind
    may name several models because a free tier is metered per model.
    """
    for row in SHIPPED:
        for kind in row.kinds:
            assert (kind in row.litellm) != (kind in row.adapter), (row.id, kind)
            assert row.models_for(kind)


def test_a_kind_named_as_a_bare_string_rather_than_a_list_is_refused(tmp_path):
    """Always a list, even of one: a scalar would make the single-model case a different shape from
    the two-model case, and every reader would have to handle both."""
    path = written(tmp_path, a_row(litellm={"text": "gemini/x"}))
    with pytest.raises(CatalogueError, match="non-empty list"):
        load_catalogue(path)


def test_an_empty_model_list_is_refused(tmp_path):
    path = written(tmp_path, a_row(litellm={"text": []}))
    with pytest.raises(CatalogueError, match="non-empty list"):
        load_catalogue(path)


def test_the_same_model_named_twice_in_one_row_is_refused(tmp_path):
    """It would be asked twice in a row for the same bucket, which is a typo, not a fallback."""
    path = written(tmp_path, a_row(litellm={"text": ["gemini/x", "gemini/x"]}))
    with pytest.raises(CatalogueError, match="same text model twice"):
        load_catalogue(path)


def test_the_free_tier_row_offers_two_text_models_because_each_has_its_own_daily_quota():
    """Two buckets of 500 a day are a thousand a day. The second is reached by the first's 429."""
    assert SHIPPED.find("gemini-free").models_for("text") == (
        "gemini/gemini-3.5-flash-lite",
        "gemini/gemini-3.1-flash-lite",
    )


def test_the_free_tier_row_does_not_claim_it_can_make_an_image():
    """Every image model on that tier is allowed zero requests, so a row listing one would put a
    pair in the chain that can only ever 429 — slower and more confusing than not being there."""
    assert "image" not in SHIPPED.find("gemini-free").kinds
    assert [row.id for row in SHIPPED.serving("image")] == ["vertex", "cloudflare", "openai"]


def test_every_row_that_costs_money_says_where_to_read_the_bill():
    """No provider serves a usage figure over its API, so a link is the honest answer. The one row
    without a link is the one with no bill."""
    for row in SHIPPED:
        if row.id == "ollama-local":
            assert row.usageUrl is None
            continue
        assert row.usageUrl, f"{row.id} names nowhere to read its usage"
        assert row.usageUrl.startswith("https://")


@pytest.mark.parametrize("row", SHIPPED.rows, ids=lambda row: row.id)
def test_a_usage_link_carries_no_account_project_or_billing_id(row):
    """The links the owner actually uses carry a project and a billing account. This file is
    public, so the row carries the shape and the environment carries the identity."""
    for placeholder in _PLACEHOLDER.findall(row.usageUrl or ""):
        assert placeholder in row.requires
    assert "gen-lang-client-" not in (row.usageUrl or "")


def test_a_usage_link_is_filled_in_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef")
    assert usage_url(SHIPPED.find("cloudflare")) == (
        "https://dash.cloudflare.com/0123456789abcdef0123456789abcdef/ai/workers-ai"
    )


def test_a_usage_link_may_not_embed_the_key(tmp_path):
    path = written(tmp_path, a_row(usageUrl="https://x/{A_KEY}/usage"))
    with pytest.raises(CatalogueError, match="interpolates its key into usageUrl"):
        load_catalogue(path)


def test_the_shipped_catalogue_carries_no_credential():
    """It ships the list, never a secret. Variable names only, and nothing key-shaped."""
    text = CATALOGUE_PATH.read_text(encoding="utf-8")
    for row in SHIPPED:
        for name in row.secret_names:
            assert name == name.upper(), f"{row.id}: {name} does not look like a variable name"
    assert "sk-" not in text
    assert "AIza" not in text  # a Google API key's prefix


@pytest.mark.parametrize("row", SHIPPED.rows, ids=lambda row: row.id)
def test_a_shipped_base_url_never_interpolates_a_key(row):
    assert row.keyEnv is None or f"{{{row.keyEnv}}}" not in (row.baseUrl or "")


def test_ids_are_unique(tmp_path):
    with pytest.raises(CatalogueError, match="share the id"):
        load_catalogue(written(tmp_path, a_row(), a_row()))


def test_a_kind_routed_through_both_litellm_and_an_adapter_is_refused(tmp_path):
    path = written(tmp_path, a_row(adapter={"text": "cloudflare"}, models={"text": ["@cf/x"]}))
    with pytest.raises(CatalogueError, match="both LiteLLM and an adapter"):
        load_catalogue(path)


def test_a_kind_with_no_route_at_all_is_refused(tmp_path):
    path = written(tmp_path, a_row(kinds=["text", "image"]))  # image is declared, never named
    with pytest.raises(CatalogueError, match="neither a model nor an adapter"):
        load_catalogue(path)


def test_a_base_url_that_embeds_the_key_is_refused(tmp_path):
    """The locked contract as an assertion: a key does not belong in a URL."""
    path = written(tmp_path, a_row(baseUrl="https://x/{A_KEY}/v1"))
    with pytest.raises(CatalogueError, match="interpolates its key"):
        load_catalogue(path)


def test_a_base_url_may_only_interpolate_what_the_row_requires(tmp_path):
    path = written(tmp_path, a_row(baseUrl="https://x/{ACCOUNT}/v1"))
    with pytest.raises(CatalogueError, match="which it does not require"):
        load_catalogue(path)


def test_a_base_url_is_filled_in_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ACCOUNT", "abc123")
    catalogue = load_catalogue(
        written(tmp_path, a_row(requires=["ACCOUNT"], baseUrl="https://x/{ACCOUNT}/v1"))
    )
    assert base_url(catalogue.find("row")) == "https://x/abc123/v1"


def test_reason_names_the_first_unmet_requirement_and_never_a_value(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "a-token-value")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    row = SHIPPED.find("cloudflare")
    assert reason(row) == "CLOUDFLARE_ACCOUNT_ID is not set"
    assert "a-token-value" not in reason(row)

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef")
    assert available(row)


def test_a_blank_variable_counts_as_unset(monkeypatch):
    """`compose.yaml` passes `GEMINI_API_KEY: "${GEMINI_API_KEY:-}"`, so empty is the common case."""
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert reason(SHIPPED.find("gemini-free")) == "GEMINI_API_KEY is not set"


def test_vertex_asks_for_application_default_credentials_rather_than_a_key(monkeypatch, tmp_path):
    """LiteLLM has no Vertex express-key path, so `VERTEX_API_KEY` is not what makes it available."""
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("VERTEX_API_KEY", "a-key-that-means-nothing-now")
    monkeypatch.setattr("acervo.models.catalogue._ADC_FILE", tmp_path / "absent.json")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    row = SHIPPED.find("vertex")
    assert reason(row) == "Google application default credentials are not configured"

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "service-account.json"))
    assert available(row)


def test_serving_keeps_catalogue_order():
    """Row order is the default preference order, so it is load-bearing rather than cosmetic."""
    assert [row.id for row in SHIPPED.serving("text")][:3] == ["gemini-free", "vertex", "cloudflare"]
    assert [row.id for row in SHIPPED.serving("audio")] == ["google-tts", "cloudflare", "openai"]


def test_speech_capabilities_are_declared_per_model_and_widen_from_the_most_specific_tag():
    google = SHIPPED.find("google-tts")
    assert google.style_for("wavenet") == "none"
    assert google.style_for("gemini-3.1-flash-tts-preview") == "instruction"
    assert google.speaks("wavenet", "zh-Hant") and not google.speaks("wavenet", "fr")
    assert google.speaks("gemini-2.5-flash-tts", "fr")
    assert google.locale_for("wavenet", "zh-Hant") == "cmn-TW"
    assert google.locale_for("wavenet", "es-MX") == "es-ES"
    assert google.voices_for("standard", "ru")[0] == "ru-RU-Standard-A"
    assert SHIPPED.find("cloudflare").speaks("@cf/deepgram/aura-1", "en")
    assert not SHIPPED.find("cloudflare").speaks("@cf/deepgram/aura-1", "es")


def test_the_speech_chains_have_recommended_orders_that_name_real_pairs():
    assert SHIPPED.default_chains["audioPlain"][0] == ("google-tts", "wavenet")
    assert SHIPPED.default_chains["audioExpressive"][0] == ("google-tts", "gemini-3.1-flash-tts-preview")


def test_gemini_speech_is_reached_only_where_it_can_take_a_direction():
    """Through LiteLLM the Gemini API and Vertex drop a direction before the request is built, so
    neither row speaks; the same models take one through `google-tts`."""
    assert not SHIPPED.find("gemini-free").serves("audio")
    assert not SHIPPED.find("vertex").serves("audio")
    for provider, model in SHIPPED.default_chains["audioExpressive"]:
        assert SHIPPED.find(provider).style_for(model) == "instruction"


def test_an_expressive_default_that_cannot_take_a_direction_is_refused(tmp_path):
    document = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    document["defaultChains"]["audioExpressive"].append({"provider": "google-tts", "model": "wavenet"})
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CatalogueError, match="cannot take a direction"):
        load_catalogue(path)


def test_an_audio_declaration_for_a_model_the_row_does_not_offer_is_refused(tmp_path):
    document = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    google = next(row for row in document["providers"] if row["id"] == "google-tts")
    google["capabilities"]["audio"]["models"]["chirp"] = {"style": "none"}
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CatalogueError, match="does not offer"):
        load_catalogue(path)


def test_params_are_data_rather_than_code():
    """Vertex's location used to be a settings field and its thinking level an
    `if provider == "vertex"` in the call path. Both are now the row's business, which is what let
    `reasoning_effort` be dropped — LiteLLM refuses it for these models — without touching code."""
    assert SHIPPED.find("vertex").params_for("text") == {"vertex_location": "global"}
    assert SHIPPED.find("gemini-free").params_for("text") == {}


def test_a_row_lists_every_variable_it_reads_so_redaction_can_be_built_from_it():
    assert SHIPPED.find("cloudflare").secret_names == (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    )
    # Including the ones it passes as call arguments and the one naming its credentials file:
    # Vertex's project id came back inside a 404 from Google, and it is a deployment detail this
    # repository does not publish.
    assert "ACERVO_VERTEX_PROJECT" in SHIPPED.find("vertex").secret_names
    assert "GOOGLE_APPLICATION_CREDENTIALS" in SHIPPED.find("vertex").secret_names
    assert Row(id="x", label="X", kinds=("text",)).secret_names == ()


def test_a_row_may_not_pass_its_key_as_an_ordinary_call_argument(tmp_path):
    """The same rule as `baseUrl`: a credential travels as a credential, not as a parameter."""
    path = written(tmp_path, a_row(passes={"api_key": "A_KEY"}))
    with pytest.raises(CatalogueError, match="passes its key"):
        load_catalogue(path)


def test_reading_the_catalogue_does_not_drag_litellm_in():
    """`acervo.models.pacing` is what the file ingestion and the worker image import, and the
    worker image deliberately does not install LiteLLM. The lazy import in `call.py` is what makes
    that work, and a stray module-level `import litellm` would break it silently — everything would
    still pass here, and the worker would fail on the machine."""
    probe = (
        "import sys, acervo.models.pacing\n"
        "from acervo.models import load_catalogue, available\n"
        "load_catalogue()\n"
        "assert 'litellm' not in sys.modules, sorted(n for n in sys.modules if 'litellm' in n)\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, capture_output=True)


# ── whose account is being spent ────────────────────────────────────────────
# Application default credentials are whichever Google login was last signed in, so on a machine
# that holds a work account as well as a personal one, "which account is this spending?" can change
# under a project without anything in Acervo changing.


def google(tmp_path, **fields):
    path = tmp_path / "creds.json"
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def test_a_service_account_key_says_whose_it_is(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(google(
        tmp_path, type="service_account", client_email="acervo-vertex@personal.example.com"
    )))
    assert identity(SHIPPED.find("vertex")) == "acervo-vertex@personal.example.com"


def test_a_plain_user_login_does_not_say_whose_it_is(monkeypatch, tmp_path):
    """Measured, not assumed: the file `gcloud auth application-default login` writes carries an
    `account` field and leaves it empty. That is the argument for a key on a shared machine."""
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(google(
        tmp_path, type="authorized_user", account="", quota_project_id="a-project"
    )))
    assert identity(SHIPPED.find("vertex")) is None


def test_a_row_reading_a_key_is_never_asked_for_the_private_half(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(google(
        tmp_path, type="service_account", client_email="acervo-vertex@personal.example.com",
        private_key="-----BEGIN PRIVATE KEY-----secret-----END PRIVATE KEY-----",
    )))
    assert "PRIVATE KEY" not in (identity(SHIPPED.find("vertex")) or "")


def test_credentials_belonging_to_another_account_are_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(google(
        tmp_path, type="service_account", client_email="acervo@employer.example.com"
    )))
    monkeypatch.setenv("ACERVO_VERTEX_ACCOUNT", "acervo@personal.example.com")
    row = SHIPPED.find("vertex")
    assert not available(row)
    assert "acervo@employer.example.com" in reason(row)


def test_the_expected_account_lets_the_right_credentials_through(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(google(
        tmp_path, type="service_account", client_email="acervo@personal.example.com"
    )))
    monkeypatch.setenv("ACERVO_VERTEX_ACCOUNT", "acervo@personal.example.com")
    assert available(SHIPPED.find("vertex"))


def test_an_account_that_cannot_be_proved_is_refused_rather_than_assumed(monkeypatch, tmp_path):
    """Half a guard that passes when it cannot check is not a guard. Naming the expected account is
    therefore also a decision to use a key, which is the only credential that says whose it is."""
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(google(
        tmp_path, type="authorized_user", account=""
    )))
    monkeypatch.setenv("ACERVO_VERTEX_ACCOUNT", "acervo@personal.example.com")
    row = SHIPPED.find("vertex")
    assert not available(row)
    assert "do not say which account" in reason(row)


def test_no_guard_means_no_check(monkeypatch, tmp_path):
    """Opt-in. A deployment that holds one Google login has nothing to protect against."""
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(google(
        tmp_path, type="service_account", client_email="acervo@anywhere.example.com"
    )))
    monkeypatch.delenv("ACERVO_VERTEX_ACCOUNT", raising=False)
    assert available(SHIPPED.find("vertex"))


# ── what may be shown to the owner ──────────────────────────────────────────


def test_a_key_hint_is_four_characters_at_each_end(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyC1234567890abcdefghijklmnop")
    assert key_hint(SHIPPED.find("gemini-free")) == "AIza…mnop"


def test_an_unset_key_has_no_hint(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert key_hint(SHIPPED.find("gemini-free")) is None


def test_a_key_too_short_to_abbreviate_is_not_abbreviated(monkeypatch):
    """Below the minimum, four at each end would be most of the value. Say only that it is set."""
    monkeypatch.setenv("GEMINI_API_KEY", "sk-tiny")
    assert key_hint(SHIPPED.find("gemini-free")) == "…"


def test_a_row_with_no_key_variable_has_no_hint():
    assert key_hint(SHIPPED.find("vertex")) is None


def test_settings_are_the_requires_variables_and_their_values(monkeypatch):
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    assert row_settings(SHIPPED.find("vertex")) == (("ACERVO_VERTEX_PROJECT", "a-project"),)


def test_a_row_may_not_list_its_key_among_the_settings_it_shows(tmp_path):
    """`row_settings` is rendered in full in Settings ▸ Providers, so this is what keeps that safe:
    a structural refusal rather than a convention somebody has to remember."""
    document = {"providers": [{
        "id": "leaky", "label": "Leaky", "kinds": ["text"],
        "litellm": {"text": ["leaky/one"]},
        "keyEnv": "LEAKY_API_KEY", "requires": ["LEAKY_API_KEY"],
    }]}
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CatalogueError, match="lists its key among the settings"):
        load_catalogue(path)


def test_only_the_vertex_image_row_declares_that_it_takes_reference_pictures():
    """A story's later picture is drawn from its earlier ones only where a row says it can read
    them; everywhere else the picture is drawn from the brief alone, as before."""
    declared = {row.id: row.image_references() for row in SHIPPED.rows if row.serves("image")}
    assert declared.pop("vertex") > 0
    assert set(declared.values()) == {0}


@pytest.mark.parametrize("count", [-1, "2", True])
def test_image_references_that_are_not_a_count_are_refused(tmp_path, count):
    path = written(tmp_path, a_row(capabilities={"image": {"references": count}}))
    with pytest.raises(CatalogueError, match="not a count"):
        load_catalogue(path)
