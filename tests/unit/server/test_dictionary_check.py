"""Comparing a model's reading, transcription and gender with what an installed dictionary attests.

The classes are what the measurement in `experiments/dictionary-checks/` counts, so each is pinned on
the word that motivated it.
"""

from __future__ import annotations

import json

import pytest

from acervo.dictionaries.container import SourceEntry, build_artifact
from acervo.services.capture.dictionary_check import (
    attested,
    gender_verdict,
    ipa_verdict,
    keys_for,
    per,
    reading_verdict,
    transcription_to_judge,
    variants,
)
from acervo.services.dictionaries import lookup
from acervo.services.dictionaries.lookup import Found


# ── readings ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("model, entries, kind", [
    ("máfan", ["ma2 fan5"], "match"),
    ("ma2 fan5", ["ma2 fan5"], "match"),
    ("máfán", ["ma2 fan5"], "neutral-only"),            # the register's defect 2
    ("dōngxi", ["dong1 xi1", "dong1 xi5"], "match"),     # either entry of a 多音字 passes
    ("dōngxī", ["dong1 xi1", "dong1 xi5"], "match"),
    ("yí gè", ["yi1 ge4"], "sandhi-only"),
    ("bú shì", ["bu4 shi4"], "sandhi-only"),
    ("ní hǎo", ["ni3 hao3"], "sandhi-only"),
    ("Běijīng", ["Bei3 jing1"], "match"),
    ("yìdiǎnr", ["yi1 dian3 r5"], "sandhi-only"),
    ("mā fan", ["ma2 fan5"], "tone-mismatch"),
    ("má fang", ["ma2 fan5"], "mismatch"),
])
def test_a_reading_is_sorted_by_how_it_differs(model, entries, kind):
    assert reading_verdict(model, entries).kind == kind


def test_a_reading_with_no_pinyin_entry_is_not_judged():
    assert reading_verdict("máfan", ["ㄇㄚˊ ㄈㄢˊ"]).kind == "no-entry"
    assert reading_verdict("máfan", []).kind == "no-entry"
    assert reading_verdict("mafan", ["ma2 fan5"]).kind == "unparsed"


# ── transcriptions ────────────────────────────────────────────────────────────────────────────

CALLE = ["/ˈkaʝe/", "/ˈkaʎe/", "/ˈkaʃe/", "/ˈkaʒe/", "[ˈka.ʝe]"]


@pytest.mark.parametrize("model, entries, kind", [
    ("/ˈaska/", ["/ˈasko/", "[ˈas.ko]"], "mismatch"),     # the register's defect 1
    ("/ˈas.ko/", ["/ˈasko/"], "match"),
    ("[ˈas.ko]", ["/ˈasko/"], "match"),
    ("/asko/", ["/ˈasko/"], "stress-only"),
    ("/ˈkaʃe/", CALLE, "match"),                         # any variety's transcription is attested
    ("/ˈθjelo/", ["/ˈsjelo/"], "vowels-agree"),
    ("/ˈɡato/", ["/ˈgato/"], "match"),                   # ASCII g and IPA ɡ are one letter
])
def test_a_transcription_is_sorted_by_how_it_differs(model, entries, kind):
    assert ipa_verdict(model, entries).kind == kind


def test_the_first_variant_alone_can_be_asked_for():
    assert ipa_verdict("/ˈkaʃe/", CALLE, first_only=True).kind == "vowels-agree"


def test_phone_error_rate_counts_phones_not_characters():
    assert per("/tou̯/", "/tou̯/") == 0
    assert per("/ˈaska/", "/ˈasko/") == pytest.approx(0.25)


def test_a_transcription_with_nothing_to_compare_is_not_judged():
    assert ipa_verdict("/ˈasko/", []).kind == "no-entry"
    assert ipa_verdict(None, ["/ˈasko/"]).kind == "model-none"


# ── gender ────────────────────────────────────────────────────────────────────────────────────

def test_a_gender_passes_when_the_dictionary_gives_it_among_others():
    assert gender_verdict("feminine", ["masculine", "feminine"]).kind == "match"
    assert gender_verdict("feminine", ["masculine"]).kind == "mismatch"
    assert gender_verdict(None, ["masculine"]).kind == "model-none"
    assert gender_verdict("masculine", []).kind == "no-entry"


def test_attested_values_come_from_every_article_without_repeats():
    readings, ipas, genders = attested([
        {"reading": "hang2", "ipa": "/x/", "genders": ["masculine"]},
        {"reading": "xing2", "ipa": "/x/", "ipas": ["/x/", "/y/"], "genders": ["masculine", "feminine"]},
    ])
    assert readings == ["hang2", "xing2"] and ipas == ["/x/", "/y/"]
    assert genders == ["masculine", "feminine"]


# ── the installed dictionaries ────────────────────────────────────────────────────────────────

def _install(directory, identifier, source_lang, words, tier="fields"):
    entries = [SourceEntry(key=word, payload=json.dumps([article], ensure_ascii=False).encode())
               for word, article in sorted(words.items())]
    build_artifact(entries, destination=directory, dictionary_id=identifier, tier=tier,
                   metadata={"id": identifier, "name": identifier, "sourceLang": source_lang})


def test_a_word_is_looked_up_in_every_dictionary_of_its_language(tmp_path):
    _install(tmp_path, "kaikki-es-en", "es", {"asco": {"headword": "asco", "ipa": "/ˈasko/"}})
    _install(tmp_path, "kaikki-es-es", "es", {"asco": {"headword": "asco", "genders": ["masculine"]}})
    _install(tmp_path, "kaikki-it-en", "it", {"asco": {"headword": "asco", "ipa": "/ˈasko/"}})
    found = lookup.articles_for(tmp_path, "es-AR", ["asco", "el asco"])
    assert [(item.dictionary_id, item.key) for item in found] == [("kaikki-es-en", "asco"), ("kaikki-es-es", "asco")]
    assert attested(article for item in found for article in item.articles)[2] == ["masculine"]


def test_the_headword_is_tried_when_the_lemma_is_not_held(tmp_path):
    _install(tmp_path, "cc-cedict", "zh-Hans", {"麻烦": {"headword": "麻烦", "reading": "ma2 fan5"}})
    found = lookup.articles_for(tmp_path, "zh", ["", "麻烦"])
    assert found[0].articles[0]["reading"] == "ma2 fan5"


def test_no_dictionary_means_no_articles(tmp_path):
    assert lookup.articles_for(tmp_path, "ko", ["사과"]) == []
    assert lookup.articles_for(tmp_path / "missing", "es", ["asco"]) == []


def test_an_html_dictionary_is_not_read(tmp_path):
    build_artifact([SourceEntry(key="asco", payload=b"<h1>asco</h1>")], destination=tmp_path,
                   dictionary_id="wikdict-es-en", tier="html",
                   metadata={"id": "wikdict-es-en", "name": "w", "sourceLang": "es"})
    assert lookup.articles_for(tmp_path, "es", ["asco"]) == []


def test_an_unreadable_dictionary_is_skipped_and_said(tmp_path, caplog):
    _install(tmp_path, "kaikki-es-en", "es", {"asco": {"headword": "asco", "ipa": "/ˈasko/"}})
    (tmp_path / "kaikki-es-en.idx").write_bytes(b"not an index")
    import os
    os.utime(tmp_path / "kaikki-es-en.json", (1, 1))  # a changed artifact is opened again
    caplog.set_level("INFO")
    assert lookup.articles_for(tmp_path, "es", ["asco"]) == []
    assert any("dictionary_unreadable" in record.getMessage() for record in caplog.records)


# ── which form is compared ────────────────────────────────────────────────────────────────────

def test_a_word_is_looked_up_under_its_own_form_before_its_lemma():
    assert keys_for("el asco", "asco") == ["el asco", "asco"]
    assert keys_for("la bandera roja", "bandera roja") == ["la bandera roja", "bandera roja"]
    assert keys_for("asustado", "asustar") == ["asustado", "asustar"]


def test_a_transcription_is_compared_only_with_an_entry_of_the_same_form():
    lemma_only = [Found("kaikki-es-en", "asustar", [{"ipa": "/asusˈtaɾ/"}])]
    assert transcription_to_judge("asustado", "/asusˈtaðo/", lemma_only) is None


def test_an_article_left_out_of_the_transcription_is_no_difference():
    found = [Found("kaikki-es-en", "asco", [{"ipa": "/ˈasko/"}])]
    assert transcription_to_judge("el asco", "/ˈaska/", found) == ("/ˈaska/", ["/ˈasko/"])
    assert transcription_to_judge("la verdad", "/la βeɾˈðað/", [Found("d", "verdad", [{"ipa": "/beɾˈðað/"}])]) \
        == ("βeɾˈðað", ["/beɾˈðað/"])


def test_one_string_may_stand_for_several_transcriptions():
    assert variants("['blɪsf(ə)l, 'blɪsful]") == ["['blɪsfəl", "['blɪsfl", "'blɪsful]"]
    assert ipa_verdict("/ˈblɪsfəl/", ["['blɪsf(ə)l, 'blɪsful]"]).kind == "match"


def test_notation_that_does_not_change_the_sound_is_evened_out():
    assert ipa_verdict("/ˈbrɛdˌwɪn.ər/", ["/ˈbɹɛdˌwɪnɚ/"]).kind == "match"
    assert ipa_verdict("/ˈfeɪθ.fəl/", ["/ˈfeɪ̯θ.fəl/"]).kind == "match"


def test_a_common_noun_agrees_with_a_dictionary_listing_both_genders():
    assert gender_verdict("common", ["feminine", "masculine"]).kind == "match"
    assert gender_verdict("common", ["masculine"]).kind == "mismatch"
