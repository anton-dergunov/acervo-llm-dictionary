"""A Mandarin reading's IPA, derived by table (`docs/features/articles.md`, "Readings")."""

from __future__ import annotations

import pytest

from acervo.mandarin_ipa import mandarin_ipa, syllable_ipa
from acervo.pinyin import INVENTORY, Syllable


@pytest.mark.parametrize(
    ("reading", "ipa"),
    [
        # The owner's hand correction, which settled the notation, and two words beside it.
        ("dòu fu", "/tou̯˥˩ fu/"),
        ("shū", "/ʂu˥/"),
        ("dōng xi", "/tʊŋ˥ ɕi/"),
        # Citation tones: a third tone stays ˨˩˦ even before another one.
        ("hǎo", "/xau̯˨˩˦/"),
        ("nǐ hǎo", "/ni˨˩˦ xau̯˨˩˦/"),
        ("yī", "/i˥/"),
        ("bù", "/pu˥˩/"),
        # ü, written u after j q x and y.
        ("nǚ", "/ny˨˩˦/"),
        ("lǜ", "/ly˥˩/"),
        ("qù", "/tɕʰy˥˩/"),
        ("yuè", "/y̯e˥˩/"),
        # The apical vowels.
        ("zhī chī shì rì", "/ʈʂɻ̩˥ ʈʂʰɻ̩˥ ʂɻ̩˥˩ ʐɻ̩˥˩/"),
        ("zì cí sī", "/tsɹ̩˥˩ tsʰɹ̩˧˥ sɹ̩˥/"),
        ("ér zi", "/ɚ˧˥ tsɹ̩/"),
        # No initial.
        ("ān", "/an˥/"),
        ("wǒ", "/u̯o˨˩˦/"),
        ("yǒu", "/i̯ou̯˨˩˦/"),
        ("wèi", "/u̯ei̯˥˩/"),
        # Spellings Pinyin shortens.
        ("liù", "/li̯ou̯˥˩/"),
        ("guì", "/ku̯ei̯˥˩/"),
        ("dùn", "/tu̯ən˥˩/"),
        ("bō", "/pu̯o˥/"),
        # Erhua.
        ("yìdiǎnr", "/i˥˩ ti̯ɐ˞˨˩˦/"),
        ("huār", "/xu̯a˞˥/"),
        ("shìr", "/ʂɚ˥˩/"),
        ("kòngr", "/kʰʊ̃˞˥˩/"),
        ("píngr", "/pʰi̯ɤ̃˞˧˥/"),
        # Numbered, run together, or split by an apostrophe: the same syllables, spaced.
        ("tu2 shu1 guan3", "/tʰu˧˥ ʂu˥ ku̯an˨˩˦/"),
        ("túshūguǎn", "/tʰu˧˥ ʂu˥ ku̯an˨˩˦/"),
        ("Xī'ān", "/ɕi˥ an˥/"),
    ],
)
def test_derives_the_broad_transcription(reading, ipa):
    assert mandarin_ipa(reading) == ipa


@pytest.mark.parametrize("reading", ["tu shu guan", "/maloˈɡɾaɾ/", "hàn·zì", "case study", ""])
def test_leaves_a_reading_that_does_not_parse_without_one(reading):
    assert mandarin_ipa(reading) is None


@pytest.mark.parametrize("syllable", sorted(INVENTORY))
def test_every_syllable_has_a_transcription(syllable):
    for tone in (1, 5):
        assert syllable_ipa(Syllable(syllable, tone, False, ""))
    if syllable != "er":
        assert syllable_ipa(Syllable(f"{syllable}r", 1, True, "")).endswith(("˞˥", "ɚ˥"))
