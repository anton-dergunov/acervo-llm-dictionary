"""The converters, on hand-written samples of each source format.

Each sample is a few real lines from the format rather than a synthetic one, because the things that
break a converter — a headword with several parts of speech, a reading that only some entries carry,
a part of speech Acervo's enum has no room for — are exactly what a synthetic fixture leaves out.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from acervo.dictionaries.catalogue import CatalogueEntry, load_catalogue
from acervo.dictionaries.container import BuildReport
from acervo.dictionaries.converters import CONVERTERS, restyle, source_entries
from acervo.dictionaries.model import resolve_pos


def row(**overrides) -> CatalogueEntry:
    base = dict(id="test", name="Test", kind="offline", sourceLang="es", targetLang="en",
                licence="CC BY-SA 4.0", attribution="Test", url="https://example.invalid/x")
    base.update(overrides)
    return CatalogueEntry(**base)


def convert(path: Path, entry: CatalogueEntry):
    report = BuildReport()
    return list(CONVERTERS[entry.format](path, entry, report)), report


# ------------------------------------------------------------------------------------ wiktextract

KAIKKI = [
    {"word": "gratis", "pos": "adj", "lang_code": "es",
     "sounds": [{"ipa": "/ˈɡɾatis/"}],
     "senses": [{"glosses": ["free of charge"], "tags": ["colloquial"]}],
     "etymology_text": "from Latin", "categories": ["Spanish adjectives"]},
    # The same headword again as a different part of speech. wiktextract writes one line per
    # (word, pos) pair and the two lines are adjacent, which is what the grouping relies on.
    {"word": "gratis", "pos": "adv", "lang_code": "es",
     "senses": [{"glosses": ["for free"],
                 "examples": [{"text": "Lo hizo gratis.", "english": "He did it for free."}]}]},
    {"word": "sobre", "pos": "prep", "lang_code": "es",
     "senses": [{"glosses": ["on, upon"]}]},
    {"word": "vacío", "pos": "noun", "lang_code": "es", "senses": [{"glosses": []}]},
]


@pytest.fixture
def kaikki_file(tmp_path):
    path = tmp_path / "kaikki.jsonl"
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in KAIKKI),
                    encoding="utf-8")
    return path


def test_wiktextract_groups_every_part_of_speech_under_one_headword(kaikki_file):
    entries, _ = convert(kaikki_file, row(format="wiktextract", targetLang="en"))
    gratis = next(entry for entry in entries if entry.headword == "gratis")
    assert [sense.definition for sense in gratis.senses] == ["free of charge", "for free"]
    assert gratis.ipa == "/ˈɡɾatis/" and gratis.register == "colloquial"


def test_wiktextract_keeps_the_sources_own_part_of_speech_and_invents_none(kaikki_file):
    """Acervo's enum has seven values and real dictionaries have far more. A preposition says
    `preposition`; bucketing it into `expression` would be a lie and dropping it a worse one."""
    entries, report = convert(kaikki_file, row(format="wiktextract"))
    sobre = next(entry for entry in entries if entry.headword == "sobre")
    assert sobre.posLabel == "prep" and sobre.pos is None
    assert "prep" in report.unmapped_pos


def test_wiktextract_drops_an_entry_with_no_gloss_rather_than_inventing_one(kaikki_file):
    entries, report = convert(kaikki_file, row(format="wiktextract"))
    assert "vacío" not in {entry.headword for entry in entries}
    assert report.skipped == 1


def test_wiktextract_records_the_fields_it_had_nowhere_to_put(kaikki_file):
    _, report = convert(kaikki_file, row(format="wiktextract"))
    assert {"etymology_text", "categories"} <= report.dropped_fields


def test_wiktextract_writes_the_definition_language_the_edition_actually_uses(kaikki_file):
    """The English edition's glosses are English even when the headwords are Spanish, so they are
    written as English definitions rather than pretending to be Spanish ones."""
    entries, _ = convert(kaikki_file, row(format="wiktextract", targetLang="en"))
    assert all(entry.definitionLang == "en" for entry in entries)
    entries, _ = convert(kaikki_file, row(format="wiktextract", targetLang="es"))
    assert all(entry.definitionLang == "es" for entry in entries)


def test_wiktextract_ignores_other_languages_in_a_whole_edition_dump(tmp_path):
    path = tmp_path / "edition.jsonl.gz"
    records = KAIKKI + [{"word": "hound", "pos": "noun", "lang_code": "en",
                         "senses": [{"glosses": ["a dog"]}]}]
    path.write_bytes(gzip.compress(
        "\n".join(json.dumps(record) for record in records).encode("utf-8")))
    entries, _ = convert(path, row(format="wiktextract", options={"langCode": "es"}))
    assert "hound" not in {entry.headword for entry in entries}


# --------------------------------------------------------------------------------------- CC-CEDICT

def test_cc_cedict_reads_the_line_grammar_and_says_nothing_about_part_of_speech(tmp_path):
    path = tmp_path / "cedict.txt"
    path.write_text("# comment\n"
                    "漢字 汉字 [han4 zi4] /Chinese character/CL:個|个[ge4]/\n"
                    "not a cedict line\n", encoding="utf-8")
    entries, _ = convert(path, row(format="cc-cedict", sourceLang="zh-Hans", targetLang="en"))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.headword == "汉字" and entry.reading == "han4 zi4"
    assert entry.aliases == ["漢字"], "the traditional form must reach the same entry"
    assert entry.pos is None and entry.posLabel is None
    assert [sense.definition for sense in entry.senses] == ["Chinese character", "CL:個|个[ge4]"]


def test_cc_canto_prefers_the_jyutping_reading(tmp_path):
    """CC-Canto is the CC-CEDICT grammar plus `{jyutping}`. For Cantonese that is the reading that
    matters, so it is one optional group rather than a second converter."""
    path = tmp_path / "canto.txt"
    path.write_text("一世人 一世人 [yi1 shi4 ren2] {jat1 sai3 jan4} /the whole life/\n",
                    encoding="utf-8")
    entries, _ = convert(path, row(format="cc-cedict", sourceLang="yue"))
    assert entries[0].reading == "jat1 sai3 jan4"


# --------------------------------------------------------------------------------------- TEI / P5

def test_freedict_tei_reads_headwords_and_translations(tmp_path):
    path = tmp_path / "d.tei"
    path.write_text(
        '<?xml version="1.0"?><TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
        '<entry><form><orth>hound</orth></form><gramGrp><pos>n</pos></gramGrp>'
        '<sense><cit><quote>собака</quote></cit><cit><quote>гончая</quote></cit></sense></entry>'
        '<entry><form><orth>hush</orth></form><gramGrp><pos>int</pos></gramGrp>'
        '<sense><cit><quote>тише</quote></cit></sense></entry>'
        "</body></text></TEI>", encoding="utf-8")
    entries, _ = convert(path, row(format="freedict-tei", sourceLang="en", targetLang="ru"))
    assert [entry.headword for entry in entries] == ["hound", "hush"]
    assert entries[0].pos == "noun"
    assert [sense.definition for sense in entries[0].senses] == ["собака", "гончая"]


# ------------------------------------------------------------------------------------------ jmdict

def test_jmdict_uses_kana_as_a_reading_only_when_the_headword_is_kanji(tmp_path):
    path = tmp_path / "jmdict.json"
    path.write_text(json.dumps({"words": [
        {"kanji": [{"text": "犬"}], "kana": [{"text": "いぬ"}],
         "sense": [{"partOfSpeech": ["n"], "gloss": [{"text": "dog"}, {"text": "canine"}]}],
         "common": True},
        {"kanji": [], "kana": [{"text": "そして"}],
         "sense": [{"partOfSpeech": ["conj"], "gloss": [{"text": "and then"}]}]},
    ]}), encoding="utf-8")
    entries, report = convert(path, row(format="jmdict", sourceLang="ja", targetLang="en"))
    assert entries[0].headword == "犬" and entries[0].reading == "いぬ"
    assert entries[0].senses[0].definition == "dog; canine"
    assert entries[1].headword == "そして" and entries[1].reading is None
    assert entries[1].pos is None and entries[1].posLabel == "conj"
    assert "common" in report.dropped_fields


# ----------------------------------------------------------------------------------------- moedict

def test_moedict_reads_the_heteronym_shape(tmp_path):
    path = tmp_path / "moedict.json"
    path.write_text(json.dumps([{"title": "漢字", "heteronyms": [
        {"bopomofo2": "hàn zì", "definitions": [{"def": "中國文字。", "example": ["例句"]}]}]}]),
        encoding="utf-8")
    entries, _ = convert(path, row(format="moedict", sourceLang="zh-Hant", targetLang="zh-Hant"))
    assert entries[0].headword == "漢字" and entries[0].reading == "hàn zì"
    assert entries[0].senses[0].examples[0].text == "例句"


# ------------------------------------------------------------------------------------- packing up

def test_the_fields_tier_payload_is_an_array_and_omits_empty_fields(kaikki_file):
    packed = list(source_entries(kaikki_file, row(format="wiktextract", tier="fields"),
                                 BuildReport()))
    articles = json.loads(packed[0].payload)
    assert isinstance(articles, list) and len(articles) == 1
    assert "register" in articles[0] and "reading" not in articles[0]


def test_the_html_tier_produces_a_display_fragment(kaikki_file):
    packed = list(source_entries(kaikki_file, row(format="wiktextract", tier="html"), BuildReport()))
    markup = packed[0].payload.decode()
    assert markup.startswith("<h1>gratis</h1>") and "<ol>" in markup


def test_an_unknown_format_is_refused_by_name(kaikki_file):
    with pytest.raises(KeyError, match="nonesuch"):
        list(source_entries(kaikki_file, row(format="nonesuch"), BuildReport()))


# ------------------------------------------------------------------------------- shared behaviour

def test_restyle_strips_presentation_and_keeps_structure():
    """FreeDict payloads carry inline colours that fight Acervo's theme in both light and dark."""
    markup = '<div class="pos"><font color="green">verb</font></div><i style="color:red">x</i>'
    assert restyle(markup) == '<div class="pos">verb</div><i>x</i>'


@pytest.mark.parametrize("label,expected", [
    ("noun", "noun"), ("Verb", "verb"), ("interjection", "expression"),
    ("preposition", None), ("conj", None), ("", None), (None, None),
])
def test_part_of_speech_maps_only_when_it_genuinely_matches(label, expected):
    mapped, kept = resolve_pos(label)
    assert mapped == expected
    assert kept == (label.strip() if label else None)


# ----------------------------------------------------------------------------------- the catalogue

def test_every_catalogue_row_is_coherent():
    rows = load_catalogue()
    assert len(rows) > 40, "the catalogue should carry real breadth, not a token few rows"
    seen = set()
    for entry in rows:
        assert entry.id not in seen, f"duplicate catalogue id {entry.id}"
        seen.add(entry.id)
        assert entry.kind in {"offline", "online", "link"}
        assert entry.tier in {"fields", "html"}
        assert entry.url.startswith("https://"), f"{entry.id} must be fetched over https"
        assert entry.licence and entry.attribution, f"{entry.id} must say who wrote it"
        if entry.kind == "offline":
            assert entry.format in CONVERTERS, f"{entry.id} names an unknown format {entry.format!r}"
        else:
            assert entry.format is None, f"{entry.id} is {entry.kind} and needs no converter"


def test_the_catalogue_keeps_unclear_provenance_out():
    """§9: BKRS is the best zh→ru content available and the murkiest licensing here. Someone can
    add it themselves; Acervo should not suggest it."""
    identifiers = {entry.id for entry in load_catalogue()}
    assert not {identifier for identifier in identifiers if "bkrs" in identifier.lower()}


# ------------------------------------------------------------------- wiktextract: gender and variants

def _kaikki(tmp_path, records) -> Path:
    path = tmp_path / "gendered.jsonl"
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8")
    return path


def test_wiktextract_reads_gender_from_the_tags_it_normalised(tmp_path):
    path = _kaikki(tmp_path, [{
        "word": "asco", "pos": "noun", "lang_code": "es",
        "head_templates": [{"name": "es-noun", "args": {"1": "m"}, "expansion": "asco m (plural ascos)"}],
        "sounds": [{"ipa": "/ˈasko/"}, {"ipa": "[ˈas.ko]"}],
        "senses": [{"glosses": ["disgust"], "tags": ["masculine"]}],
    }])
    [entry], _ = convert(path, row(format="wiktextract"))
    assert entry.genders == ["masculine"]
    assert entry.ipa == "/ˈasko/" and entry.ipas == ["/ˈasko/", "[ˈas.ko]"]


def test_wiktextract_keeps_both_genders_of_a_homograph(tmp_path):
    path = _kaikki(tmp_path, [
        {"word": "livre", "pos": "noun", "lang_code": "fr", "tags": ["masculine"],
         "senses": [{"glosses": ["book"]}]},
        {"word": "livre", "pos": "noun", "lang_code": "fr", "tags": ["feminine"],
         "senses": [{"glosses": ["pound"]}]},
    ])
    [entry], _ = convert(path, row(format="wiktextract", sourceLang="fr"))
    assert entry.genders == ["masculine", "feminine"]


def test_wiktextract_reads_gender_off_the_headword_line_when_nothing_is_tagged(tmp_path):
    # Russian in the English edition: the gender is only in the line `соба́ка • (sobáka) f anim (…)`.
    path = _kaikki(tmp_path, [{
        "word": "собака", "pos": "noun", "lang_code": "ru",
        "head_templates": [{"name": "ru-noun+", "expansion":
                            "соба́ка • (sobáka) f anim (genitive соба́ки, male equivalent соба́кен (sobáken))"}],
        "senses": [{"glosses": ["dog"]}],
    }])
    [entry], _ = convert(path, row(format="wiktextract", sourceLang="ru"))
    assert entry.genders == ["feminine"]


def test_wiktextract_gives_no_gender_outside_nouns(tmp_path):
    path = _kaikki(tmp_path, [{
        "word": "asqueroso", "pos": "adj", "lang_code": "es",
        "head_templates": [{"expansion": "asqueroso (feminine asquerosa, masculine plural asquerosos)"}],
        "senses": [{"glosses": ["disgusting"], "tags": ["masculine"]}],
    }])
    [entry], _ = convert(path, row(format="wiktextract"))
    assert entry.genders == []


def test_wiktextract_keeps_every_variant_transcription_with_the_displayed_one_first(tmp_path):
    path = _kaikki(tmp_path, [{
        "word": "calle", "pos": "noun", "lang_code": "es", "tags": ["feminine"],
        "sounds": [{"ipa": "/ˈkaʝe/"}, {"ipa": "[ˈka.ʝe]"}, {"ipa": "/ˈkaʎe/"}, {"ipa": "/ˈkaʃe/"},
                   {"ipa": "/ˈkaʝe/"}],
        "senses": [{"glosses": ["street"]}],
    }])
    [entry], _ = convert(path, row(format="wiktextract"))
    assert entry.ipa == "/ˈkaʝe/"
    assert entry.ipas == ["/ˈkaʝe/", "/ˈkaʎe/", "/ˈkaʃe/", "[ˈka.ʝe]"]
    payload = json.loads(entry.payload())[0]
    assert payload["genders"] == ["feminine"] and payload["ipas"][2] == "/ˈkaʃe/"


def test_a_single_transcription_is_not_repeated_as_a_list(tmp_path):
    path = _kaikki(tmp_path, [{"word": "sol", "pos": "noun", "lang_code": "es", "sounds": [{"ipa": "/ˈsol/"}],
                               "senses": [{"glosses": ["sun"]}]}])
    [entry], _ = convert(path, row(format="wiktextract"))
    assert "ipas" not in json.loads(entry.payload())[0]
