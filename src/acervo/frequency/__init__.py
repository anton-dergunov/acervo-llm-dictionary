"""How common a word is in everyday use, as a Zipf figure: 7 for "the", 1 for a word met once in a
hundred million.

The figures are wordfreq's (code Apache-2.0, word lists CC BY-SA 4.0), which blends subtitles,
Wikipedia, books, news and the web for about forty languages. A make dialog orders words by this when
the owner asks for the rare ones, so it is one number per headword and nothing else.

**A headword is looked up as it is written.** wordfreq tokenises a phrase and combines its parts, and
an article is too common to move the figure: "el muro" and "muro" both answer 4.45. So there is no
article stripping here to keep in step with anything.

**A language it cannot read is not covered, and says so.** Chinese is read through `jieba`, which is
installed; Japanese and Korean need MeCab and its dictionaries, which are not, so they are not covered
rather than half-covered. A word wordfreq has never seen answers 0, which is what it is: rarer than
anything on its lists.

Stands alone — imports nothing of Acervo's — like the other pipeline packages; `services/rarity.py`
is what knows whose words these are.
"""

from __future__ import annotations

from functools import cache

from wordfreq import zipf_frequency

# A word every covered language has, to ask whether the language can be read at all. Any failure
# answering it — no list for the language, or no tokeniser installed for its script — means the same
# thing to the caller: this language cannot be ordered by frequency here.
_PROBE = "a"


@cache
def covers(language: str) -> bool:
    """Whether this language's words can be given a frequency."""
    try:
        zipf_frequency(_PROBE, _base(language))
    except (LookupError, ImportError, ValueError):
        return False
    return True


def zipf(text: str, language: str) -> float:
    """How common `text` is, from 0 (unseen) to about 8. Call `covers` first: an uncovered language
    raises rather than answering a figure that means nothing."""
    return float(zipf_frequency(text, _base(language)))


def _base(language: str) -> str:
    """wordfreq's lists are per language, not per region: `es-AR` reads Spanish's."""
    return language.split("-")[0].lower()
