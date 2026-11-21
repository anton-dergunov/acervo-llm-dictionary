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


def chinese(**overrides):
    return article(**{"headword": "钩子", "reading": "gōu zi",
                      "sense": {"examples": [{"text": "墙上有一个钩子。"}]}, **overrides})


def test_a_chinese_entry_with_a_reading_passes():
    checked(chinese(), resolution=CHINESE)


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
    checked(chinese(notes=["Not 钩子 but 钩, in writing: 钩子 is spoken."]), resolution=CHINESE)


def test_notes_in_another_script_pass_the_model_over():
    with pytest.raises(Unusable) as refused:
        checked(russian(notes=["Not el gancho, which is any hook."]), TO_RUSSIAN)
    assert str(refused.value) == ("the notes are in Latin script, and the vocabulary writes its notes "
                                  "in Russian")


def test_no_notes_at_all_pass():
    checked(russian(notes=[]), TO_RUSSIAN)


# ── definitions in `definitionLang` ─────────────────────────────────────────

KOREAN = {"language": "ko", "headword": "옷", "lemma": "옷"}
ITALIAN = {"language": "it", "headword": "la sedia", "lemma": "sedia"}
FOR_ENGLISH = {"language": "it", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}


def defined(definition, *more):
    senses = [{"definition": text, "glosses": [{"lang": "en", "terms": ["chair"]}]} for text in (definition, *more)]
    return {"headword": "la sedia", "primaryGloss": "chair", "shortGloss": "chair", "notes": [],
            "senses": senses}


def test_a_definition_in_another_script_passes_the_model_over():
    with pytest.raises(Unusable) as refused:
        checked({**defined("사람이 몸에 걸쳐 입는 물건의 총칭."), "headword": "옷"},
                {**FOR_ENGLISH, "language": "ko"}, KOREAN)
    assert str(refused.value) == "the definitions are in Hangul script, and the vocabulary defines its senses in English"


def test_an_english_definition_quoting_the_word_in_its_own_script_passes():
    checked({**defined("Clothing; what 옷 means in general."), "headword": "옷"}, {**FOR_ENGLISH, "language": "ko"},
            KOREAN)


def test_a_definition_in_the_words_language_is_doubted_and_kept_when_no_model_does_better():
    answer = defined("A seat for one person, with a back.", "Mobile su cui ci si siede, con uno schienale.")
    with pytest.raises(Demoted) as doubted:
        checked(answer, FOR_ENGLISH, ITALIAN)
    assert str(doubted.value) == ("a definition of la sedia reads as Italian, and the vocabulary defines "
                                  "its senses in English")
    assert doubted.value.by == "language"
    assert doubted.value.checked.answer == answer


def test_an_english_definition_in_a_vocabulary_defined_in_the_words_language_is_doubted():
    with pytest.raises(Demoted) as doubted:
        checked(article(sense={"definition": "A curved metal hook used to catch or hold things."}))
    assert "reads as English, and the vocabulary defines its senses in Spanish" in str(doubted.value)


@pytest.mark.parametrize("definition", ["A seat for one person, with a back.", "Fast.", "An adult male person."])
def test_english_definitions_for_an_italian_word_pass_however_short(definition):
    checked(defined(definition), FOR_ENGLISH, ITALIAN)


def test_with_checks_off_a_definition_in_the_wrong_language_passes():
    vet(FOR_ENGLISH, ITALIAN, checking=False)(defined("Mobile su cui ci si siede, con uno schienale."))


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
    return article(**{"headword": "麻烦", "reading": reading, "ipa": "/ma˧˥ fan/",
                      "sense": {"examples": [{"text": "真麻烦。"}]}, **overrides})


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
        judged(article(headword="el asco", gender="feminine", primaryGloss="hook; gaff"),
               found(genders=["masculine"]))
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


# ── a word in two scripts, an example in another script ─────────────────────

GREEK = {"language": "el", "headword": "το σπίτι", "lemma": "σπίτι", "pos": "noun"}
GREEK_TO_ENGLISH = {"language": "el", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}


def greek(text="Είναι ώρα να πάμε σπίτι.", **overrides):
    return article(**{"headword": "το σπίτι", "notes": [],
                      "sense": {"definition": "A building where people live.",
                                "glosses": [{"lang": "en", "terms": ["house", "home"]}],
                                "examples": [{"text": text, "translation": "It is time to go home."}]},
                      **overrides})


def test_greek_written_in_greek_passes():
    checked(greek(), GREEK_TO_ENGLISH, GREEK)


@pytest.mark.parametrize("text, word", [
    ("Είναι ώρα να πάμε σπίti.", "σπίti"),        # measured: 3.5 Flash-Lite, a fifth of its Greek
    ("Λαtrεύω την ελληνική κουζίνα.", "Λαtrεύω"),
])
def test_a_word_written_in_two_scripts_passes_the_model_over(text, word):
    with pytest.raises(Unusable) as refused:
        checked(greek(text), GREEK_TO_ENGLISH, GREEK)
    assert str(refused.value) == f"an example has {word!r}, a word written in two scripts"


@pytest.mark.parametrize("text", ["Tシャツを着る。", "時々図書館へ行く。", "スーパーで買い物をした。"])
def test_japanese_mixes_its_own_scripts_in_one_word(text):
    resolution = {"language": "ja", "headword": "時々", "lemma": "時々"}
    vocabulary = {"language": "ja", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}
    checked(article(headword="時々", notes=[], sense={"examples": [{"text": text}]}), vocabulary, resolution)


def test_an_example_in_another_script_than_the_words_passes_the_model_over():
    with pytest.raises(Unusable) as refused:
        checked(greek("The learner did not provide a sentence for this."), GREEK_TO_ENGLISH, GREEK)
    assert str(refused.value) == "an example is in Latin script, and το σπίτι is Greek"


def test_a_russian_stress_mark_typed_as_a_latin_vowel_is_made_cyrillic():
    resolution = {"language": "ru", "headword": "писать", "lemma": "писать", "pos": "verb"}
    vocabulary = {"language": "ru", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}
    answer = article(headword="писать", notes=["The stress falls on the second syllable: писáть."],
                     sense={"definition": "To write.", "examples": [{"text": "Я люблю писать."}]})
    vetted = checked(answer, vocabulary, resolution)
    assert vetted.answer["notes"] == ["The stress falls on the second syllable: писа\u0301ть."]
    assert vetted.fixed == ["stress"]


def test_a_headword_compose_rewrote_is_put_back_as_resolve_settled_it():
    """Measured: Hindi जानना came back as جاننا, in Urdu's script, and देना as denā."""
    resolution = {"language": "hi", "headword": "देना", "lemma": "देना", "pos": "verb"}
    vocabulary = {"language": "hi", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}
    answer = article(headword="denā", notes=[],
                     sense={"definition": "To give.", "examples": [{"text": "मुझे पानी दो।"}]})
    vetted = checked(answer, vocabulary, resolution)
    assert vetted.answer["headword"] == "देना" and vetted.fixed == ["headword"]


# ── reading, transcription and gender as the language has them ──────────────

JAPANESE = {"language": "ja", "headword": "同僚", "lemma": "同僚", "pos": "noun"}
FOR_JAPANESE = {"language": "ja", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}


def japanese(reading, headword="同僚"):
    return article(headword=headword, reading=reading, notes=[],
                   sense={"definition": "A person you work with.", "examples": [{"text": "同僚と話す。"}]})


@pytest.mark.parametrize("reading, kept, field", [
    ("どうりょう", "どうりょう", None),
    ("どう りょう", "どうりょう", "fixed"),        # spaced
    ("ドウリョウ", "どうりょう", "fixed"),         # katakana
    ("dō ryō", None, "dropped"),                  # measured: 58% of starter readings were romaji
])
def test_a_japanese_reading_is_the_word_in_hiragana(reading, kept, field):
    vetted = checked(japanese(reading), FOR_JAPANESE, JAPANESE)
    assert vetted.answer["reading"] == kept
    assert (vetted.fixed, vetted.dropped) == {None: ([], []), "fixed": (["reading"], []),
                                              "dropped": ([], ["reading"])}[field]


def test_a_japanese_word_with_no_kanji_has_no_reading():
    vetted = checked(japanese("すーぱー", headword="スーパー"), FOR_JAPANESE,
                     {**JAPANESE, "headword": "スーパー", "lemma": "スーパー"})
    assert vetted.answer["reading"] is None


def test_a_reading_in_a_language_that_has_none_yet_is_dropped():
    """Measured: Korean romanised with tone marks it does not have (`mā si da`)."""
    resolution = {"language": "ko", "headword": "마시다", "lemma": "마시다", "pos": "verb"}
    vocabulary = {"language": "ko", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}
    answer = article(headword="마시다", reading="mā si da", notes=[],
                     sense={"definition": "To drink.", "examples": [{"text": "물을 마셔요."}]})
    vetted = checked(answer, vocabulary, resolution)
    assert vetted.answer["reading"] is None and vetted.dropped == ["reading"]


def test_a_chinese_reading_is_left_to_the_dictionary():
    assert checked(chinese(), resolution=CHINESE).answer["reading"] == "gōu zi"


@pytest.mark.parametrize("ipa, kept", [
    ("/deːɐ̯ ʃtɛʁn/", "/ʃtɛʁn/"),
    ("/ʃtɛʁn/", "/ʃtɛʁn/"),
    ("[deːɐ̯ ʃtɛʁn]", "[ʃtɛʁn]"),
])
def test_the_transcription_is_of_the_lemma_not_the_article(ipa, kept):
    resolution = {"language": "de", "headword": "der Stern", "lemma": "Stern", "pos": "noun"}
    vocabulary = {"language": "de", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"}
    answer = article(headword="der Stern", lemma="Stern", ipa=ipa, gender="masculine", notes=[],
                     sense={"definition": "A point of light in the night sky.",
                            "examples": [{"text": "Der Stern leuchtet."}]})
    vetted = checked(answer, vocabulary, resolution)
    assert vetted.answer["ipa"] == kept
    assert vetted.fixed == ([] if ipa == kept else ["ipa"])


@pytest.mark.parametrize("language, pos, gender, kept", [
    ("en", "noun", "neuter", None),          # measured: 58 English nouns had a gender
    ("es", "adj", "masculine", None),        # an adjective agrees, it has no gender of its own
    ("es", "noun", "common", "common"),      # el / la estudiante
    ("nl", "noun", "masculine", "common"),   # a de-word
    ("nl", "noun", "neuter", "neuter"),
    ("it", "noun", "neuter", None),
    ("xx", "noun", "neuter", "neuter"),      # a language CLDR does not list keeps what it was given
])
def test_a_gender_is_kept_only_as_the_language_has_it(language, pos, gender, kept):
    resolution = {"language": language, "headword": "el garfio", "lemma": "garfio", "pos": pos}
    vocabulary = {"language": language, "definitionLang": "es", "glossLangs": ["en"], "notesLang": "en"}
    vetted = checked(article(gender=gender, pos=pos), vocabulary, resolution)
    assert vetted.answer["gender"] == kept
