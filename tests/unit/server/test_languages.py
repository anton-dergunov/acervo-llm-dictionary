"""Settings ▸ Vocabularies: the language list, and a vocabulary's level and note about its learner."""

from __future__ import annotations

from graph_records import vocabulary


def test_the_language_list_names_each_language_twice_and_offers_its_varieties(server):
    answer = server.get("/languages")
    assert answer.status_code == 200
    languages = {entry["tag"]: entry for entry in answer.json()["data"]["languages"]}
    spanish = languages["es"]
    assert spanish["name"] == "Spanish" and spanish["autonym"] == "español" and spanish["region"] == "ES"
    assert spanish["varieties"][:2] == ["MX", "AR"] and "419" in spanish["varieties"]
    assert languages["zh-Hant"]["region"] == "TW" and "zh" not in languages, "a script chosen, not a bare tag"
    tags = list(languages)
    assert tags.index("en") < tags.index("es") < tags.index("ru"), "most speakers first"


def test_a_level_and_a_note_are_replicated(server):
    note = "Preparing for a trip to Argentina; the subjunctive is my weak spot."
    assert server.push({"vocabularies": [vocabulary(level="b1", learnerNote=f"  {note} ")]}).status_code == 200
    pulled = server.pull().json()["data"]["changes"]["vocabularies"][0]
    assert pulled["level"] == "B1" and pulled["learnerNote"] == note
    assert server.push({"vocabularies": [vocabulary(language="ru")]}).status_code == 200
    plain = [entry for entry in server.pull().json()["data"]["changes"]["vocabularies"] if entry["language"] == "ru"]
    assert plain[0]["level"] is None and plain[0]["learnerNote"] is None


def test_a_level_is_a_cefr_level_and_a_note_is_short(server):
    refused = server.push({"vocabularies": [vocabulary(level="B3")]})
    assert refused.status_code == 400 and "A1, A2, B1, B2, C1 or C2" in refused.json()["error"]["message"]
    assert server.push({"vocabularies": [vocabulary(learnerNote="x" * 1001)]}).status_code == 400
