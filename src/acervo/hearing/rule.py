"""Whether a take spoke its direction: the rule `experiments/take-verification/` settled.

A loop's voice is told how to sound, and now and then it says part of that instead of, or after, its
text: «to provide **more**» for a host "offering more food", «Seek relief from irritation in the
throat» for «cough». So the text is aligned to the closest run of the transcript's words, and the take
counts as wrong when a word *outside* that run is a word of the direction it was sent. Nothing else
counts: an exclamation around the word, a laugh or a drawn-out word is the emotion the direction asked
for, and an exclamation is never in the direction, so the rule needs no list of them in any language.
It fired on the three takes the owner judged wrong out of 2,032, and on nothing else.

A story passage is held to more than that (`added`): any run of words outside its stretch is wrong,
whatever they are. A passage is narration, not a word said with feeling, so it has no exclamation of
its own to allow for, and the faults it has are words of no list — a voice that finished an unfinished
sentence with words of its own, and a voice that read its direction aloud in the story's language,
which Whisper writes in that language («con un hint de defianza»), so `leaked` matches none of it
(`experiments/story-fragments/`).

The sets and functions below are the experiments' own (`take-verification/check.py`, `sweep.leak`;
`story-fragments/`), so what ships is what was measured. Changing them is a new measurement, not an
edit.
"""

from __future__ import annotations

import re
import unicodedata

from opencc import OpenCC

# Words that say an instruction was read out, in English or the line's own language: the accent
# vocabulary the expressive-voice experiment collected, and the director note LexiBeat sends with
# every take ("Speak warmly, as if teaching someone, but clearly, at a natural pace, with a natural
# pitch range.").
GIVEAWAYS = frozenset({
    "acento", "accent", "argentina", "argentino", "argentine", "españa", "spain", "castilian",
    "castellano", "british", "american", "native", "speaker", "sounding", "direction", "акцент",
    "tone", "calm", "speak", "clearly", "pace", "pitch", "warmly", "teaching", "slowly", "naturally",
})
# Words of a direction that a line may well say on its own account.
STOP = frozenset({
    "this", "that", "with", "from", "aloud", "read", "would", "words", "sentence", "text", "keep",
    "explain", "drop", "translate", "story", "passage", "short", "like", "the", "and", "but", "someone",
    "range", "natural", "slightly", "lower", "higher", "faster",
})

_simplified = OpenCC("t2s").convert


def plain(text: str) -> list[str]:
    """Words, lowercased, accents and punctuation gone, ё read as е."""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c)).replace("ё", "е")
    return re.findall(r"[\w']+", folded)


# Scripts that put no space between words, by the first word of a letter's Unicode name. A text in
# one is compared by character, as Chinese is: split at spaces it would be one word.
_UNSPACED = frozenset({"CJK", "HIRAGANA", "KATAKANA", "THAI", "LAO", "KHMER", "MYANMAR", "TIBETAN"})


def by_character(text: str, language: str) -> bool:
    """Whether `text` is compared character by character: Chinese, and any text written mostly in a
    script with no spaces between its words. Decided by the script rather than by a list of
    languages, so a language nobody has listed is still compared the way it is written."""
    if language == "zh":
        return True
    letters = [c for c in text if c.isalpha()]
    unspaced = sum(1 for c in letters if unicodedata.name(c, "").split(" ")[0] in _UNSPACED)
    return bool(letters) and 2 * unspaced > len(letters)


def chars(words: list[str], language: str, by_char: bool = False) -> str:
    """What is compared: words joined, or characters — for Chinese in simplified form, since Whisper
    writes 圖書館 for a text that says 图书馆."""
    if language == "zh":
        return _simplified("".join(words))
    return "".join(words) if by_char else " ".join(words)


def distance(a: str, b: str) -> int:
    """Levenshtein, characters."""
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def around(heard: str, text: str, language: str) -> list[str]:
    """The words of the transcript outside the closest run of it to the text, folded.

    Only runs of about the text's own length can be the text: a run twice as long costs at least the
    text's length in insertions, which the empty run already beats. Without the bound twenty «ha»s
    would be hundreds of alignments.
    """
    by_char = by_character(text, language)
    pieces = list(heard.strip()) if by_char else heard.split()
    folded = [chars(plain(piece), language, by_char) for piece in pieces]
    wanted = chars(plain(text), language, by_char)
    joiner = "" if by_char else " "
    best = (distance(wanted, ""), 0, 0)
    size = len(wanted) if by_char else max(1, len(wanted.split()))
    longest = 2 * size + 2
    for start in range(len(pieces)):
        for end in range(start + 1, min(len(pieces), start + longest) + 1):
            span = joiner.join(piece for piece in folded[start:end] if piece)
            best = min(best, (distance(wanted, span), start, end), key=lambda b: (b[0], -(b[2] - b[1])))
    _, start, end = best
    return [piece for piece in folded[:start] + folded[end:] if piece]


def leaked(heard: str, text: str, direction: str, language: str) -> list[str]:
    """The words of `direction` heard around `text`, sorted; empty when the take is right.

    `language` is a primary subtag (`es`, not `es-AR`): it decides only whether Chinese is compared
    in simplified characters.
    """
    asked = {word for word in plain(direction) if len(word) >= 3 and word not in STOP} | GIVEAWAYS
    said = set(plain(text))
    return sorted({word for word in around(heard, text, language) if word in asked and word not in said})


# How much a story passage may be heard to say outside its own stretch. Of the 388 stored passages
# one is heard with a word outside it and the rest with none; of 519 new takes, three wrong ones added
# exactly three words («…, seguirán con todo.») and one right one was heard so badly — a shouted line in
# an Argentine accent — that it reached three too, which costs one more take. The voice that finished
# a sentence on its own added fifteen. By character, six — about three words of Chinese — which no
# measurement has set yet: no story has been recorded in a language written without spaces.
MORE_WORDS = 3
MORE_CHARACTERS = 6


def added(heard: str, text: str, language: str) -> list[str]:
    """What a story passage said beyond its own words, folded; empty when the take is right."""
    outside = around(heard, text, language)
    limit = MORE_CHARACTERS if by_character(text, language) else MORE_WORDS
    return outside if len(outside) >= limit else []
