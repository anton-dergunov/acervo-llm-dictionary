"""A provider: a document the owner added, held to its family, with the key kept beside it.

The families are code, so most of what used to be checked in a file is now a fact a test can read
off the registry. What is left is the document — what the owner may say about a provider and what
is refused — and what a provider then answers about itself: whether it can be asked, which voices it
has for an accent, which locale it is sent.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from provider_rows import (
    CLOUDFLARE, GEMINI, GEMINI_KEY, GOOGLE, GOOGLE_KEYED, SERVICE_ACCOUNT, VERTEX, google_voices, provider,
)

from acervo.models import families, listing
from acervo.models.local import LocalProvidersMissing, load_local
from acervo.models.providers import DocumentError, build, parse, suggested_id


@pytest.fixture(autouse=True)
def listed_voices(monkeypatch):
    """Google's voice list, without the network."""
    monkeypatch.setattr(listing, "_google_voices", google_voices)


# ── the families ────────────────────────────────────────────────────────────


def test_every_family_is_offered_in_one_of_the_groups_add_a_provider_shows():
    for family in families.FAMILIES:
        assert family.group in families.GROUPS
        assert set(family.routes) <= set(families.KINDS)


def test_family_ids_are_unique():
    ids = [family.id for family in families.FAMILIES]
    assert len(ids) == len(set(ids))


def test_no_template_ever_carries_a_key():
    """A base URL travels into logs and error text, and a usage link is rendered in the interface:
    neither may be built from the secret, only from the settings the owner typed."""
    for family in families.FAMILIES:
        names = {field.name for field in family.fields}
        for template in (family.base_url, family.usage_url, family.list_url, family.key_url):
            for name in __import__("re").findall(r"\{([A-Za-z_]+)\}", template or ""):
                assert name in names, f"{family.id} interpolates {name}"


def test_the_quirks_found_the_hard_way_are_in_the_family():
    google = families.find("google-cloud")
    assert google.image["responseFormat"] is None, "Vertex refuses response_format outright"
    assert google.image["references"] == 14
    assert google.audio["encoding"] == "LINEAR16"
    assert google.audio["wire"]["zh-Hans-CN"] == "cmn-CN"
    cloudflare = families.find("cloudflare")
    assert cloudflare.params["text"]["max_tokens"] == 4096, "Workers AI truncates at about 256"
    assert cloudflare.audio["inputField"] == "text", "Aura takes text where MeloTTS took prompt"
    assert families.find("anthropic").json_mode == "prompt", "Anthropic ignores response_format"


def test_vertex_is_reached_only_with_a_credentials_file():
    routes = families.find("google-cloud").routes
    assert routes["text"].file_only and routes["image"].file_only
    assert not routes["audio"].file_only and not routes["ocr"].file_only


# ── the document ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("document", "secret", "said"),
    [
        ({"id": "Gemini API", "family": "gemini-api"}, {}, "lowercase letters"),
        ({"id": "x", "family": "nonesuch"}, {}, "no provider family"),
        ({"id": "x", "family": "gemini-api", "models": {"image": ["m"]}}, {}, "does not do image"),
        ({"id": "x", "family": "gemini-api", "models": {"vibes": ["m"]}}, {}, "no kind called vibes"),
        ({"id": "x", "family": "gemini-api", "models": {"text": ["m", "m"]}}, {}, "same text model twice"),
        ({"id": "x", "family": "gemini-api", "models": {"text": [{"id": "m", "direction": True}]}},
         {}, "Only a voice takes a direction"),
        ({"id": "x", "family": "gemini-api", "models": {"text": [{"id": "m", "speed": 2}]}},
         {}, "fields a model does not take"),
        ({"id": "x", "family": "google-cloud", "models": {"text": ["gemini-3.8-flash"]}},
         {"key": "a-google-key-0123456789"}, "only with a credentials file"),
        ({"id": "x", "family": "google-cloud"}, {"credentials": {"type": "nonesuch"}},
         "not a Google credentials file"),
        ({"id": "x", "family": "gemini-api"}, {"credentials": SERVICE_ACCOUNT}, "takes a key, not"),
        ({"id": "x", "family": "ollama"}, {"key": "a-key-it-does-not-take"}, "takes no key"),
        ({"id": "x", "family": "cloudflare", "settings": {"region": "eu"}}, {}, "no setting called region"),
        ({"id": "x", "family": "google-cloud", "settings": {"location": "mars"}}, {}, "must be one of"),
        ({"id": "x", "family": "gemini-api", "models": {"text": [
            {"id": "m", "allowance": {"amount": 0, "unit": "calls", "per": "day"}}]}}, {}, "free allowance"),
        ({"id": "x", "family": "gemini-api"}, {"key": "two words"}, "one line"),
    ],
)
def test_a_document_that_cannot_be_used_is_refused_with_a_sentence_for_the_owner(document, secret, said):
    with pytest.raises(DocumentError, match=said):
        parse(document, secret)


def test_a_model_may_be_written_as_its_id_alone():
    found = parse({"id": "x", "family": "gemini-api", "models": {"text": ["a", {"id": "b"}]}}, {"key": "k" * 20})
    assert found.models_for("text") == ("a", "b")


def test_a_free_allowance_is_kept_for_the_usage_gauge():
    found = parse({"id": "x", "family": "gemini-api", "models": {"text": [
        {"id": "a", "allowance": {"amount": 500, "unit": "calls", "per": "day"}}]}}, {"key": "k" * 20})
    assert found.model("text", "a").allowance == {"amount": 500, "unit": "calls", "per": "day"}


def test_build_keeps_the_order_added_and_names_any_row_it_cannot_read():
    rows = [{**CLOUDFLARE, "position": 2}, {**GEMINI, "position": 1}, {"id": "bad", "family": "nonesuch", "position": 3}]
    found, refused = build(rows, {"gemini-api": {"key": GEMINI_KEY}})
    assert [row.id for row in found] == ["gemini-api", "cloudflare"]
    assert refused == [("bad", "There is no provider family called 'nonesuch'.")]


def test_a_suggested_id_is_the_family_numbered_when_taken():
    assert suggested_id("cloudflare", []) == "cloudflare"
    assert suggested_id("cloudflare", ["cloudflare", "cloudflare-2"]) == "cloudflare-3"


# ── whether it can be asked ─────────────────────────────────────────────────


def test_reason_says_what_is_missing_and_never_a_value():
    assert provider(GEMINI).reason() is None
    assert provider(GEMINI, {}).reason() == "Gemini API has no API key"
    assert provider(CLOUDFLARE, settings={}).reason() == "Cloudflare needs its account ID"
    assert provider(GOOGLE_KEYED, {}).reason() == "Google Cloud has no key or credentials file"
    assert provider(VERTEX, settings={}).reason() == "Google Cloud needs its project"
    assert provider({"id": "o", "family": "ollama", "models": {"text": ["llama3.3"]}}).reason() is None


def test_a_refused_key_is_a_reason_and_any_other_failed_check_is_not():
    refused = provider(GEMINI, check={"ok": False, "said": "no", "reason": "authentication"})
    assert refused.reason() == "Gemini API refused its key when it was last checked"
    asleep = provider(GEMINI, check={"ok": False, "said": "no answer", "reason": "unreachable"})
    assert asleep.reason() is None, "a provider that did not answer is tried again, and falls through"


def test_a_key_hint_is_four_characters_at_each_end_and_never_more():
    assert provider(GEMINI).key_hint() == f"{GEMINI_KEY[:4]}…{GEMINI_KEY[-4:]}"
    assert provider(GEMINI, {"key": "short-key"}).key_hint() == "…"
    assert provider(GEMINI, {}).key_hint() is None


def test_a_service_account_says_whose_it_is_and_a_key_does_not():
    assert provider(VERTEX).identity() == SERVICE_ACCOUNT["client_email"]
    assert provider(GOOGLE_KEYED).identity() is None
    assert provider(VERTEX, {"credentials": {"type": "authorized_user", "refresh_token": "r" * 30}}).identity() is None


def test_extra_parameters_are_merged_into_every_call_and_win():
    found = provider(CLOUDFLARE, extra={"max_tokens": 8192, "top_p": 0.9})
    assert found.params_for("text") == {"max_tokens": 8192, "top_p": 0.9}


def test_a_compatible_service_says_whether_it_understands_json_mode():
    document = {"id": "x", "family": "openai-compatible", "settings": {"baseUrl": "http://localhost:8080/v1"},
                "models": {"text": ["m"]}}
    assert parse(document, {}).json_mode == "prompt"
    assert parse({**document, "settings": {**document["settings"], "jsonMode": "native"}}, {}).json_mode == "native"
    # A local server takes any key, and OpenAI's client will not start without one.
    assert parse(document, {}).transport("text") == {"api_key": "none", "api_base": "http://localhost:8080/v1"}


def test_building_a_provider_teaches_the_redactor_its_secrets():
    from acervo.models.errors import ProviderRefused

    provider(VERTEX)
    error = ProviderRefused("configuration", f"echoed {SERVICE_ACCOUNT['private_key']} back")
    assert "test-private-key-material" not in error.detail


# ── voices and accents ──────────────────────────────────────────────────────


def test_a_bare_language_keeps_its_main_locale_and_the_providers_first_voice():
    google = provider(GOOGLE)
    assert google.voices_for("Wavenet", "es")[0] == "es-ES-Wavenet-F"
    assert google.locale_for("Wavenet", "es") == "es-ES"
    assert google.locale_for("gemini-2.5-flash-tts", "es") == "es-ES"
    assert google.locale_for("gemini-2.5-flash-tts", "zh-Hans") == "cmn-CN"


def test_an_accent_ranks_voices_made_for_it_and_sends_the_nearest_locale_listed():
    google = provider(GOOGLE)
    assert google.voices_for("Wavenet", "en-GB")[0] == "en-GB-Wavenet-A"
    options = dict((voice.name, match) for voice, match in google.voice_options("Wavenet", "es-AR"))
    assert options["es-US-Wavenet-A"] == "near" and options["es-ES-Wavenet-F"] == "main"
    assert google.locale_for("Wavenet", "es-AR") == "es-US"
    assert google.locale_for("Wavenet", "es-AR", "es-ES-Wavenet-F") == "es-ES"
    # A Gemini voice speaks any locale it is sent, and is sent the nearest Google lists.
    assert google.locale_for("gemini-2.5-flash-tts", "es-AR") == "es-US"
    assert {match for _, match in google.voice_options("gemini-2.5-flash-tts", "es-AR")} == {"any"}


def test_a_voice_type_speaks_only_the_languages_it_has_voices_for():
    google = provider(GOOGLE)
    assert google.speaks("Wavenet", "es-AR") and not google.speaks("Wavenet", "fr")
    assert google.speaks("gemini-2.5-flash-tts", "fr"), "a Gemini voice speaks any"


def test_voices_typed_on_a_model_are_used_where_a_provider_lists_none():
    aura = provider(CLOUDFLARE, models={"audio": [{"id": "@cf/deepgram/aura-1", "languages": ["en"],
                                                   "voices": [{"name": "luna", "gender": "female"}]}]})
    assert aura.voices_for("@cf/deepgram/aura-1", "en") == ("luna",)
    assert aura.speaks("@cf/deepgram/aura-1", "en-GB") and not aura.speaks("@cf/deepgram/aura-1", "es")


def test_only_a_model_said_to_take_a_direction_does():
    google = provider(GOOGLE)
    assert google.takes_direction("gemini-2.5-flash-tts") and not google.takes_direction("Wavenet")


VOICE_CODE = (
    "src/acervo/pronunciation/speak.py",
    "src/acervo/services/pronunciations.py",
    "src/acervo/repository/pronunciation_settings.py",
    "src/acervo/models/providers.py",
)


def test_the_code_that_chooses_a_voice_names_no_provider_model_or_voice():
    """Accents, voices and locales come from the provider, so one added later is chosen the way
    today's are. A literal naming one of today's would be a branch on it."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    google = provider(GOOGLE)
    named = {"gemini-api", "google-cloud", "cloudflare"}
    for model in google.models_for("audio"):
        named.add(model)
        named.update(voice.name for voice in google.voices(model))
    for relative in VOICE_CODE:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert not literals & named, f"{relative} names {sorted(literals & named)}"


# ── the laptop's file ───────────────────────────────────────────────────────


def test_a_laptop_reads_its_providers_in_the_servers_shape_with_the_keys_inline(tmp_path):
    credentials = tmp_path / "service-account.json"
    credentials.write_text(json.dumps(SERVICE_ACCOUNT), encoding="utf-8")
    path = tmp_path / "providers.local.json"
    path.write_text(json.dumps({"providers": [
        {**GEMINI, "key": GEMINI_KEY},
        {**VERTEX, "credentials": str(credentials)},
    ]}), encoding="utf-8")
    found = load_local(path)
    assert [row.id for row in found] == ["gemini-api", "vertex"]
    assert found.find("gemini-api").credential.key == GEMINI_KEY
    assert found.find("vertex").identity() == SERVICE_ACCOUNT["client_email"]


def test_a_missing_laptop_file_says_where_it_was_looked_for(tmp_path):
    with pytest.raises(LocalProvidersMissing, match="providers.local.json"):
        load_local(tmp_path / "providers.local.json")


def test_a_laptop_file_with_a_bad_provider_stops_the_run_naming_it(tmp_path):
    path = tmp_path / "providers.local.json"
    path.write_text(json.dumps({"providers": [{"id": "x", "family": "nonesuch"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="'x'"):
        load_local(path)


def test_reading_providers_does_not_drag_litellm_in():
    """`acervo.models.pacing` is what the file ingestion and the worker image import, and the
    worker image deliberately does not install LiteLLM. A stray module-level `import litellm` would
    break it silently — everything would still pass here, and the worker would fail on the machine."""
    probe = (
        "import sys, acervo.models.pacing\n"
        "from acervo.models.providers import parse\n"
        "parse({'id': 'x', 'family': 'gemini-api', 'models': {'text': ['m']}}, {'key': 'k' * 20})\n"
        "assert 'litellm' not in sys.modules, sorted(n for n in sys.modules if 'litellm' in n)\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, capture_output=True)


# ── languages: CLDR's facts, not a provider's ───────────────────────────────


def test_the_accents_a_language_is_offered_come_from_cldr_most_speakers_first():
    from acervo.models.locales import accents

    spanish = accents("es")
    assert spanish[:3] == ("MX", "AR", "ES") and "US" in spanish and "419" in spanish
    assert "PH" not in spanish, "widely learned is not an accent of its own"
    assert "DE" not in accents("en") and accents("en")[0] == "US"
    assert accents("zh-Hant")[:2] == ("TW", "HK") and accents("zh-Hans")[0] == "CN"
    assert accents("qaa") == ()


def test_the_language_list_is_cldr_s_most_speakers_first_with_a_script_where_two_are_official():
    from acervo.models.locales import catalogue

    languages = {language.tag: language for language in catalogue()}
    assert {"zh-Hans", "zh-Hant", "sr-Cyrl", "sr-Latn"} <= set(languages)
    assert "zh" not in languages and "sr" not in languages
    assert languages["zh-Hans"].autonym == "中文 (简体)" and languages["zh-Hant"].varieties[0] == "TW"
    assert languages["fr"].name == "French" and languages["fr"].autonym == "français"
    assert languages["en"].region == "US" and languages["pt"].region == "BR"
    assert all(language.speakers >= 1_000_000 for language in languages.values())


# ── the key check ───────────────────────────────────────────────────────────




@pytest.mark.parametrize("status", [400, 401, 403])
def test_a_check_turned_away_is_a_refused_key_however_the_provider_says_it(monkeypatch, status):
    """A check sends a fixed request, so being turned away means the key, or the settings beside it.
    Google answers a key that is not valid with a 400 `INVALID_ARGUMENT`, not a 401."""
    import httpx

    monkeypatch.setattr(listing.httpx, "get", lambda url, **kwargs: httpx.Response(
        status, json={"error": {"message": "API key not valid. Please pass a valid API key."}}))
    checked = listing.check(provider(GEMINI))
    assert not checked.ok and checked.reason == "authentication"
    assert checked.said == "Gemini API refused this key: API key not valid. Please pass a valid API key"


def test_a_provider_that_does_not_answer_is_not_a_refused_key(monkeypatch):
    import httpx

    def unreachable(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(listing.httpx, "get", unreachable)
    checked = listing.check(provider({"id": "o", "family": "ollama", "models": {"text": ["llama3.3"]}}))
    assert not checked.ok and checked.reason == "unreachable"
    assert checked.said.startswith("Ollama did not answer")


def test_a_working_key_says_what_it_reached(monkeypatch):
    import httpx

    monkeypatch.setattr(listing.httpx, "get", lambda url, **kwargs: httpx.Response(200, json={"models": [
        {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
    ]}))
    checked = listing.check(provider(GEMINI))
    assert checked.ok and checked.said == "Works · 1 model"
    assert listing.models(provider(GEMINI), "text") == ("gemini-3.5-flash-lite",)


def test_a_gemini_voice_on_google_cloud_needs_the_credentials_file():
    """Measured: a key that reaches WaveNet and Vision is refused a Gemini voice, which runs on Vertex."""
    with pytest.raises(DocumentError, match="gemini-2.5-flash-tts needs a credentials file on Google Cloud"):
        provider(GOOGLE_KEYED, models={"audio": ["Wavenet", {"id": "gemini-2.5-flash-tts", "direction": True}]})
    assert provider(GOOGLE).models_for("audio")[-1] == "gemini-2.5-flash-tts"
