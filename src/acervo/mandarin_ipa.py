"""A Mandarin reading's IPA, derived by table: `dòu fu` → `/tou̯˥˩ fu/`.

Pinyin is phonemic. Each of its ~410 syllables has one broad IPA form and each tone one Chao value,
so a transcription derived from a checked reading is as right as the reading and always in one
notation. Compose writes this instead of asking a model (`docs/features/articles.md`, "Readings").

The values are Wikipedia's "Standard Chinese phonology" (initials, finals, Chao tone letters) and,
for the rhotic coda, its "Erhua" article. The notation settles what those pages leave open:

- Syllables are separated by spaces. A syllable's tone letters follow it: 1 `˥`, 2 `˧˥`, 3 `˨˩˦`,
  4 `˥˩`. The neutral tone is unmarked. These are **citation tones**, the ones the reading shows, so
  third-tone, 一 and 不 sandhi are not applied.
- A non-syllabic vowel, glide or offglide, is written with `̯`: `i̯`, `u̯`, `y̯` (`ai̯`, `i̯a`, `y̯ɛn`).
- No tie bars on affricates (`tɕ`, `ʈʂ`, `ts`).
- The apical vowels are the syllabic approximants `ɻ̩` (after zh ch sh r) and `ɹ̩` (after z c s).
- Erhua drops a coda `i̯` or `n`, nasalises the vowel before a dropped `ŋ`, turns a high or apical
  nucleus into a glide before `ɚ`, and marks any other rhotic vowel with `˞`.

`None` for a reading that does not parse into syllables: the field is left empty, never guessed.
Imports only `acervo.pinyin`.
"""

from __future__ import annotations

from acervo.pinyin import Syllable, pinyin_syllables, unmark

TONE_LETTERS = {1: "˥", 2: "˧˥", 3: "˨˩˦", 4: "˥˩", 5: ""}

INITIALS = {
    "b": "p", "p": "pʰ", "m": "m", "f": "f",
    "d": "t", "t": "tʰ", "n": "n", "l": "l",
    "g": "k", "k": "kʰ", "h": "x",
    "j": "tɕ", "q": "tɕʰ", "x": "ɕ",
    "zh": "ʈʂ", "ch": "ʈʂʰ", "sh": "ʂ", "r": "ʐ",
    "z": "ts", "c": "tsʰ", "s": "s",
}

# Each final as (medial, nucleus, coda), so erhua can act on its parts. Keyed by the final's full
# spelling: the y/w spellings and the contractions (`iu`, `ui`, `un`) are undone before the lookup.
FINALS: dict[str, tuple[str, str, str]] = {
    "a": ("", "a", ""), "o": ("", "o", ""), "e": ("", "ɤ", ""), "er": ("", "ɚ", ""),
    "ai": ("", "a", "i̯"), "ei": ("", "e", "i̯"), "ao": ("", "a", "u̯"), "ou": ("", "o", "u̯"),
    "an": ("", "a", "n"), "en": ("", "ə", "n"), "ang": ("", "a", "ŋ"), "eng": ("", "ə", "ŋ"),
    "ong": ("", "ʊ", "ŋ"),
    "i": ("", "i", ""), "ia": ("i̯", "a", ""), "io": ("i̯", "o", ""), "ie": ("i̯", "e", ""),
    "iao": ("i̯", "a", "u̯"), "iou": ("i̯", "o", "u̯"), "ian": ("i̯", "ɛ", "n"), "in": ("", "i", "n"),
    "iang": ("i̯", "a", "ŋ"), "ing": ("", "i", "ŋ"), "iong": ("i̯", "ʊ", "ŋ"),
    "u": ("", "u", ""), "ua": ("u̯", "a", ""), "uo": ("u̯", "o", ""), "uai": ("u̯", "a", "i̯"),
    "uei": ("u̯", "e", "i̯"), "uan": ("u̯", "a", "n"), "uen": ("u̯", "ə", "n"),
    "uang": ("u̯", "a", "ŋ"), "ueng": ("u̯", "ə", "ŋ"),
    "ü": ("", "y", ""), "üe": ("y̯", "e", ""), "üan": ("y̯", "ɛ", "n"), "ün": ("", "y", "n"),
}

RETROFLEX_APICAL = "ɻ̩"
ALVEOLAR_APICAL = "ɹ̩"
RHOTIC = "˞"
NASAL = "\u0303"       # combining tilde: a vowel nasalised before a dropped ŋ
NON_SYLLABIC = "\u032f"  # combining inverted breve below


def _initial_and_final(bare: str) -> tuple[str, str]:
    """`zhuang` → (`zh`, `uang`), with every spelling rule undone: `you` → (``, `iou`)."""
    initial = next((candidate for candidate in ("zh", "ch", "sh") if bare.startswith(candidate)), "")
    if not initial and bare[0] in INITIALS:
        initial = bare[0]
    final = bare[len(initial):]
    if not initial and bare[0] == "y":
        rest = bare[1:]
        if rest.startswith("u"):
            final = "ü" + rest[1:]                 # yu yue yuan yun
        elif rest.startswith("i"):
            final = rest                           # yi yin ying
        else:
            final = "i" + rest                     # ya ye yao you yan yang yong
    elif not initial and bare[0] == "w":
        rest = bare[1:]
        final = rest if rest.startswith("u") else "u" + rest
    if initial in ("j", "q", "x") and final.startswith("u"):
        final = "ü" + final[1:]
    if initial in ("b", "p", "m", "f") and final == "o":
        final = "uo"
    # Written short after an initial; `you`, `wei`, `wen` already reached the full spelling above.
    final = {"iu": "iou", "ui": "uei", "un": "uen"}.get(final, final)
    return initial, final


def _rime(initial: str, final: str, erhua: bool) -> str:
    if final == "i" and initial in ("zh", "ch", "sh", "r"):
        return "ɚ" if erhua else RETROFLEX_APICAL
    if final == "i" and initial in ("z", "c", "s"):
        return "ɚ" if erhua else ALVEOLAR_APICAL
    medial, nucleus, coda = FINALS[final]
    if not erhua:
        return medial + nucleus + coda
    if nucleus in ("i", "y") and coda in ("", "n"):
        return nucleus + NON_SYLLABIC + "ɚ"           # 气儿 i̯ɚ, 裙儿 y̯ɚ
    if coda == "ŋ":
        vowel = "ɤ" if nucleus in ("i", "ə") else nucleus
        return medial + ("i̯" if nucleus == "i" else "") + vowel + NASAL + RHOTIC
    if coda in ("i̯", "n"):
        return medial + ("ɐ" + RHOTIC if nucleus in ("a", "ɛ") else "ɚ")
    if coda == "u̯":
        return medial + nucleus + coda + RHOTIC
    return medial + nucleus + RHOTIC


def syllable_ipa(syllable: Syllable) -> str:
    """One syllable's broad IPA with its tone letters: `dòu` → `tou̯˥˩`."""
    bare = unmark(syllable.text)[0].lower()
    if syllable.erhua:
        bare = bare[:-1]
    initial, final = _initial_and_final(bare)
    return INITIALS.get(initial, "") + _rime(initial, final, syllable.erhua) + TONE_LETTERS[syllable.tone]


def mandarin_ipa(reading: str) -> str | None:
    """The broad IPA of a Mandarin reading, numbered or tone-marked; `None` when it does not parse."""
    syllables = pinyin_syllables(reading)
    if syllables is None:
        return None
    return "/" + " ".join(syllable_ipa(syllable) for syllable in syllables) + "/"
