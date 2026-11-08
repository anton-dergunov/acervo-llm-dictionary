"""Whether a take spoke its direction: the rule `experiments/take-verification/` settled.

A loop's voice is told how to sound, and now and then it says part of that instead of, or after, its
text: «to provide **more**» for a host "offering more food", «Seek relief from irritation in the
throat» for «cough». So the text is aligned to the closest run of the transcript's words, and the take
counts as wrong when a word *outside* that run is a word of the direction it was sent. Nothing else
counts: an exclamation around the word, a laugh or a drawn-out word is the emotion the direction asked
for, and an exclamation is never in the direction, so the rule needs no list of them in any language.
It fired on the three takes the owner judged wrong out of 2,032, and on nothing else.

The sets and functions below are the experiment's own (`check.py`, `sweep.leak`), so what ships is
what was measured. Changing them is a new measurement, not an edit.
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


def chars(words: list[str], language: str) -> str:
    """What is compared: words joined, or for Chinese characters in simplified form — Whisper writes
    圖書館 for a text that says 图书馆."""
    return _simplified("".join(words)) if language == "zh" else " ".join(words)


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
    pieces = list(heard.strip()) if language == "zh" else heard.split()
    folded = [chars(plain(piece), language) for piece in pieces]
    wanted = chars(plain(text), language)
    joiner = "" if language == "zh" else " "
    best = (distance(wanted, ""), 0, 0)
    size = len(wanted) if language == "zh" else max(1, len(wanted.split()))
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
    by character.
    """
    asked = {word for word in plain(direction) if len(word) >= 3 and word not in STOP} | GIVEAWAYS
    said = set(plain(text))
    return sorted({word for word in around(heard, text, language) if word in asked and word not in said})
