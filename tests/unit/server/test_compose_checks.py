"""Compose's check, rule by rule: what passes, what is corrected, and what passes the model over.

The chain behaviour — the next pair answering — is in `test_capture.py`; these hold the rules.
"""

from __future__ import annotations

import pytest

from acervo.services.capture.vet import vet
from acervo.services.dictionaries.lookup import Found
from acervo.services.models import Demoted, Unusable

SPANISH = {"language": "es", "headword": "el garfio", "lemma": "garfio"}
CHINESE = {"language": "zh-Hans", "headword": "钩子", "lemma": "钩子"}
TO_ENGLISH = {"language": "es", "definitionLang": "es", "glossLangs": ["en"], "notesLang": "en"}
TO_RUSSIAN = {"language": "es", "definitionLang": "es", "glossLangs": ["ru", "en"], "notesLang": "ru"}


def article(**overrides):
    sense = {
        "definition": "Gancho de metal curvo.", "domain": "tools", "emoji": "\U0001FA9D",
        "glosses": [{"lang": "en", "terms": ["hook"]}],
        "examples": [{"text": "Un garfio.", "emotion": "curious and a little wary"}],
    }
    sense.update(overrides.pop("sense", {}))
    return {"headword": "el garfio", "primaryGloss": "hook", "shortGloss": "hook",
            "notes": ["Not el gancho."], "emotion": "menacing, a pirate's threat", "emoji": "\U0001FA9D",
            "senses": [sense], **overrides}


def russian(**overrides):
    sense = {"domain": "инструменты",
             "glosses": [{"lang": "ru", "terms": ["крюк"]}, {"lang": "en", "terms": ["hook"]}]}
    sense.update(overrides.pop("sense", {}))
    return article(**{"primaryGloss": "крюк", "shortGloss": "крюк",
                      "notes": ["Не путать с el gancho."], "sense": sense, **overrides})


def checked(answer, vocabulary=TO_ENGLISH, resolution=SPANISH):
    return vet(vocabulary, resolution)(answer)


def test_a_good_answer_passes_untouched():
    answer = article()
    vetted = checked(answer)
    assert vetted.answer == answer
    assert vetted.fixed == [] and vetted.dropped == []


# ── refusals, shared with the draft ─────────────────────────────────────────


@pytest.mark.parametrize("answer, resolution, sentence", [
    (["not", "an", "object"], SPANISH, "did not return an entry"),
    ({"headword": "el garfio", "senses": []}, SPANISH, "no meanings"),
    ({"senses": [{"definition": " "}]}, SPANISH, "no meanings"),
    (article(), CHINESE, "Chinese entry with no reading"),
])
def test_an_answer_no_draft_could_be_built_from_passes_the_model_over(answer, resolution, sentence):
    with pytest.raises(Unusable) as refused:
        checked(answer, resolution=resolution)
    assert sentence in str(refused.value)
    assert refused.value.refusal is not None and refused.value.refusal.code == "llm_unusable"


def test_a_chinese_entry_with_a_reading_passes():
    checked({**article(), "reading": "gōu zi"}, resolution=CHINESE)


# ── demotions, by script ────────────────────────────────────────────────────


def test_glosses_in_the_first_gloss_language_pass():
    checked(russian(), TO_RUSSIAN)


def test_glosses_in_another_script_than_the_first_gloss_language_pass_the_model_over():
    with pytest.raises(Unusable) as refused:
        checked(article(notes=["Не путать с el gancho."]), TO_RUSSIAN)
    assert str(refused.value) == ("the glosses are in Latin script, and the vocabulary glosses into "
                                  "Russian first")
    assert refused.value.refusal is None


def test_a_vocabulary_glossing_into_a_language_of_the_same_script_is_never_demoted_for_it():
    """Spanish into English: both Latin, so the check cannot tell them apart and does not try."""
    checked(article(primaryGloss="gancho", shortGloss="gancho"), TO_ENGLISH)


def test_a_second_gloss_language_is_not_held_to_the_first_ones_script():
    checked(russian(), TO_RUSSIAN)  # its English group is Latin, and is not read


def test_notes_in_the_notes_language_pass_even_when_they_quote_the_word():
    checked({**article(), "reading": "gōu zi", "notes": ["Not 钩子 but 钩, in writing: 钩子 is spoken."]},
            resolution=CHINESE)


def test_notes_in_another_script_pass_the_model_over():
    with pytest.raises(Unusable) as refused:
        checked(russian(notes=["Not el gancho, which is any hook."]), TO_RUSSIAN)
    assert str(refused.value) == ("the notes are in Latin script, and the vocabulary writes its notes "
                                  "in Russian")


def test_no_notes_at_all_pass():
    checked(russian(notes=[]), TO_RUSSIAN)


# ── coercions ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("given, kept", [("hook; gaff", "hook"), ("hook, gaff", "hook"),
                                         ("hook/gaff", "hook"), ("take a walk", "take a walk")])
def test_primary_gloss_is_cut_to_its_first_term(given, kept):
    vetted = checked(article(primaryGloss=given))
    assert vetted.answer["primaryGloss"] == kept
    assert vetted.fixed == ([] if given == kept else ["primaryGloss"])


@pytest.mark.parametrize("given, kept", [
    ("\U0001FA9D\U0001F3A3", "\U0001FA9D"),
    # One grapheme cluster, however many code points: a flag, a skin tone, a keycap sequence.
    ("\U0001F3F3️‍\U0001F308", "\U0001F3F3️‍\U0001F308"),
    ("\U0001F44D\U0001F3FD\U0001F44D", "\U0001F44D\U0001F3FD"),
])
def test_an_emoji_is_cut_to_its_first_grapheme_cluster(given, kept):
    vetted = checked(article(emoji=given, sense={"emoji": given}))
    assert vetted.answer["emoji"] == kept
    assert vetted.answer["senses"][0]["emoji"] == kept
    assert vetted.fixed == ([] if given == kept else ["emoji", "sense.emoji"])


def test_the_reply_itself_is_not_changed():
    answer = article(primaryGloss="hook; gaff")
    checked(answer)
    assert answer["primaryGloss"] == "hook; gaff"


# ── drops ───────────────────────────────────────────────────────────────────


def two_senses(first, second):
    one = article()["senses"][0]
    return article(senses=[{**one, "domain": first}, {**one, "domain": second}])


def test_a_domain_is_lower_cased():
    vetted = checked(article(sense={"domain": "Tools"}))
    assert vetted.answer["senses"][0]["domain"] == "tools"
    assert vetted.fixed == ["domain"] and vetted.dropped == []


def test_a_two_word_domain_is_kept_and_a_three_word_one_dropped():
    assert checked(article(sense={"domain": "pirate gear"})).answer["senses"][0]["domain"] == "pirate gear"
    vetted = checked(article(sense={"domain": "things pirates carry"}))
    assert vetted.answer["senses"][0]["domain"] is None
    assert vetted.dropped == ["domain"]


def test_a_domain_repeated_between_senses_is_dropped_from_the_later_sense():
    vetted = checked(two_senses("tools", "Tools"))
    assert [sense["domain"] for sense in vetted.answer["senses"]] == ["tools", None]
    assert vetted.dropped == ["domain"]


def test_distinct_domains_are_kept():
    vetted = checked(two_senses("tools", "fishing"))
    assert [sense["domain"] for sense in vetted.answer["senses"]] == ["tools", "fishing"]


@pytest.mark.parametrize("emotion", [
    "menacing",                                         # too short
    "a long and winding direction that goes on far past the twelve words it is allowed",
    "menacing and gleeful \U0001F3F4‍☠️",  # an emoji
    "Curious and a little  wary",                       # one of its own examples' emotions
])
def test_a_word_emotion_out_of_shape_is_dropped(emotion):
    vetted = checked(article(emotion=emotion))
    assert vetted.answer["emotion"] is None
    assert vetted.dropped == ["emotion"]


def test_a_word_with_no_emotion_is_left_alone():
    vetted = checked(article(emotion=None))
    assert vetted.answer["emotion"] is None and vetted.dropped == []


# ── demote softly: an installed dictionary disagrees ────────────────────────

MANDARIN = {"language": "zh-Hans", "headword": "麻烦", "lemma": "麻烦"}
ASCO = {"language": "es", "headword": "el asco", "lemma": "asco"}
TO_ENGLISH_ZH = {**TO_ENGLISH, "language": "zh-Hans"}


def found(dictionary_id="kaikki-es-en", key="asco", **article):
    return [Found(dictionary_id, key, [article])]


def judged(answer, entries, resolution=ASCO, vocabulary=TO_ENGLISH, checking=True):
    return vet(vocabulary, resolution, entries, checking)(answer)


def chinese_article(reading, **overrides):
    return article(**{"headword": "麻烦", "reading": reading, "ipa": "/ma˧˥ fan/", **overrides})


def test_a_mandarin_reading_off_by_a_tone_is_demoted_naming_the_dictionary():
    with pytest.raises(Demoted) as doubted:
        judged(chinese_article("máfán"), found("cc-cedict", "麻烦", reading="ma2 fan5"),
               MANDARIN, TO_ENGLISH_ZH)
    assert str(doubted.value) == "cc-cedict reads 麻烦 as ma2 fan5; the model wrote máfán"
    # What the check would have returned is carried, so it can be kept if no model does better.
    assert doubted.value.checked.answer["reading"] == "máfán"


def test_a_mandarin_reading_differing_only_by_sandhi_passes():
    vetted = judged(chinese_article("yíyàng"), found("cc-cedict", "一样", reading="yi1 yang4"),
                    {**MANDARIN, "headword": "一样", "lemma": "一样"}, TO_ENGLISH_ZH)
    assert vetted.answer["reading"] == "yíyàng"


def test_a_mandarin_ipa_is_never_compared_because_it_is_derived():
    vetted = judged(chinese_article("máfan", ipa="/xxxxx/"),
                    found("cc-cedict", "麻烦", reading="ma2 fan5", ipas=["/ma˧˥ fan/"]),
                    MANDARIN, TO_ENGLISH_ZH)
    assert vetted.answer["ipa"] == "/xxxxx/"


def test_a_transcription_far_from_every_variant_is_demoted():
    with pytest.raises(Demoted) as doubted:
        judged(article(headword="el asco", ipa="/ˈaska/"), found(ipas=["/ˈasko/"]))
    assert str(doubted.value) == "kaikki-es-en reads el asco as /ˈasko/; the model wrote /ˈaska/"


def test_a_transcription_matching_any_variant_passes():
    vetted = judged(article(headword="el asco", ipa="/ˈasko/"), found(ipas=["/ˈas.ko/", "[ˈah.ko]"]))
    assert vetted.answer["ipa"] == "/ˈasko/"


def test_a_transcription_of_another_form_is_not_compared():
    """Found under the lemma only (`asustar` for `asustado`): another word's sound."""
    vetted = judged(article(headword="asustado", ipa="/asusˈtado/"), found(key="asustar", ipas=["/asusˈtaɾ/"]),
                    {"language": "es", "headword": "asustado", "lemma": "asustar"})
    assert vetted.answer["ipa"] == "/asusˈtado/"


def test_a_gender_the_dictionary_does_not_give_is_demoted():
    with pytest.raises(Demoted) as doubted:
        judged(article(gender="feminine"), found(genders=["masculine"]))
    assert str(doubted.value) == "kaikki-es-en has el asco as masculine; the model wrote feminine"


@pytest.mark.parametrize("gender", ["masculine", None])
def test_a_matching_or_absent_gender_passes(gender):
    assert judged(article(gender=gender), found(genders=["masculine"])).answer["gender"] == gender


def test_with_no_dictionary_installed_nothing_is_compared():
    vetted = judged(article(gender="feminine", ipa="/ˈaska/"), [])
    assert vetted.answer["gender"] == "feminine"


def test_a_demoted_answer_carries_what_the_check_corrected():
    with pytest.raises(Demoted) as doubted:
        judged(article(gender="feminine", primaryGloss="hook; gaff"), found(genders=["masculine"]))
    assert doubted.value.checked.answer["primaryGloss"] == "hook"
    assert doubted.value.checked.fixed == ["primaryGloss"]


# ── checks off ──────────────────────────────────────────────────────────────


def test_with_checks_off_a_wrong_script_answer_passes_uncorrected():
    answer = russian(primaryGloss="hook; gaff", shortGloss="hook",
                     sense={"glosses": [{"lang": "ru", "terms": ["hook"]}]})
    vetted = judged(answer, found(genders=["feminine"]), SPANISH, TO_RUSSIAN, checking=False)
    assert vetted.answer == answer
    assert vetted.fixed == [] and vetted.dropped == []


def test_with_checks_off_an_answer_no_draft_could_be_built_from_is_still_refused():
    with pytest.raises(Unusable) as refused:
        judged({"headword": "el garfio", "senses": []}, [], SPANISH, checking=False)
    assert "no meanings" in refused.value.refusal.message
