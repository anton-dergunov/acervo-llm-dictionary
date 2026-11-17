"""Pinyin as the server reads it: tone marks for numbered syllables, and a reading cut into syllables.

Two twins of ``web/src/pinyin.ts``, for the readers of a reading that are not the interface:

- ``accented_pinyin`` (``accentedPinyin``) turns ``tu2 shu1 guan3`` into ``tú shū guǎn`` for an Anki
  card. Anything that is not recognisably numbered Pinyin is returned untouched, so a reading already
  written with marks, or not Pinyin at all, passes through.
- ``pinyin_syllables`` (``pinyinSyllables``) reads a reading, numbered or marked, as syllables with
  tones. Compose derives a Mandarin IPA from it (``acervo.mandarin_ipa``).

Each pair is held to one case file: ``web/src/testFixtures/pinyinVectors.json`` for the marks, and
``web/src/testFixtures/pinyinSyllableVectors.json`` for the syllables and the syllable table. So the
two implementations cannot drift. Imports nothing of Acervo's.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

_MARKS = {
    "a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ",
}
_SYLLABLE = re.compile(r"^([a-zü]+)([0-5])$", re.IGNORECASE)


def is_mandarin(language: str) -> bool:
    """Every Chinese tag but Cantonese, whose Jyutping has six tones and no marks."""
    lower = language.lower()
    if lower.startswith("cmn"):
        return True
    return lower.startswith("zh") and not re.match(r"^zh-yue\b", lower)


def _mark_position(letters: str) -> int:
    lower = letters.lower()
    for vowel in ("a", "e"):
        if vowel in lower:
            return lower.index(vowel)
    if "ou" in lower:
        return lower.index("ou")
    for index in range(len(lower) - 1, -1, -1):
        if lower[index] in _MARKS:
            return index
    return -1


def _accent_syllable(token: str) -> str:
    normalised = re.sub(r"([nljqxy])v", r"\1ü", re.sub(r"u:", "ü", token, flags=re.IGNORECASE),
                        flags=re.IGNORECASE)
    parts = _SYLLABLE.match(normalised)
    if not parts:
        return token
    letters, tone = parts.group(1), parts.group(2)
    if tone in ("0", "5"):
        return letters
    at = _mark_position(letters)
    if at < 0:
        return letters
    vowel = letters[at]
    marked = _MARKS[vowel.lower()][int(tone) - 1]
    if vowel != vowel.lower():
        marked = marked.upper()
    return letters[:at] + marked + letters[at + 1:]


def is_numbered_pinyin(reading: str) -> bool:
    tokens = reading.split()
    if not tokens:
        return False
    syllables = [token for token in tokens if _SYLLABLE.match(re.sub(r"u:", "ü", token, flags=re.IGNORECASE))]
    # Most of it, not all: a reading may carry a stray `·` between syllables.
    return bool(syllables) and len(syllables) >= len(tokens) - 1


def accented_pinyin(reading: str) -> str:
    if not is_numbered_pinyin(reading):
        return reading
    return "".join(part if part.isspace() else _accent_syllable(part)
                   for part in re.split(r"(\s+)", reading.strip()))


# ── a reading as syllables with tones ─────────────────────────────────────────────────────────────


class Syllable(NamedTuple):
    """One syllable of a Mandarin reading, as the interface shows it."""

    text: str
    """Tone-marked, in the case it was written: ``Běi``, ``diǎnr``."""
    tone: int
    """1–4, or 5 for the neutral tone, which carries no mark."""
    erhua: bool
    """Ends in the ``r`` that 儿 adds to the syllable before it (``diǎnr``, 点儿)."""
    before: str
    """What separated it from the syllable before it in the source: a space, an apostrophe, nothing."""


# Every syllable Hanyu Pinyin has, without tones: what a run like `túshūguǎn` is cut against. The same
# list as `INVENTORY` in `pinyin.ts`, which the shared vector file pins. Interjections with no vowel
# (`m`, `ng`, `hm`) are left out: no vocabulary word is spelled with one, and letting them in would let
# `n` and `m` split ordinary syllables.
INVENTORY = frozenset((
    "a o e ai ei ao ou an en ang eng er yi ya yo ye yao you yan yin yang ying yong "
    "wu wa wo wai wei wan wen wang weng yu yue yuan yun "
    "ba bo bai bei bao ban ben bang beng bi bie biao bian bin bing bu "
    "pa po pai pei pao pou pan pen pang peng pi pie piao pian pin ping pu "
    "ma mo me mai mei mao mou man men mang meng mi mie miao miu mian min ming mu "
    "fa fo fei fou fan fen fang feng fu "
    "da de dai dei dao dou dan den dang deng dong di dia die diao diu dian ding du duo dui duan dun "
    "ta te tai tei tao tou tan tang teng tong ti tie tiao tian ting tu tuo tui tuan tun "
    "na ne nai nei nao nou nan nen nang neng nong ni nie niao niu nian nin niang ning nu nuo nuan nü nüe "
    "la lo le lai lei lao lou lan lang leng long li lia lie liao liu lian lin liang ling lu luo luan lun lü lüe "
    "ga ge gai gei gao gou gan gen gang geng gong gu gua guo guai gui guan gun guang "
    "ka ke kai kei kao kou kan ken kang keng kong ku kua kuo kuai kui kuan kun kuang "
    "ha he hai hei hao hou han hen hang heng hong hu hua huo huai hui huan hun huang "
    "ji jia jie jiao jiu jian jin jiang jing jiong ju jue juan jun "
    "qi qia qie qiao qiu qian qin qiang qing qiong qu que quan qun "
    "xi xia xie xiao xiu xian xin xiang xing xiong xu xue xuan xun "
    "zha zhe zhi zhai zhei zhao zhou zhan zhen zhang zheng zhong zhu zhua zhuo zhuai zhui zhuan zhun zhuang "
    "cha che chi chai chao chou chan chen chang cheng chong chu chua chuo chuai chui chuan chun chuang "
    "sha she shi shai shei shao shou shan shen shang sheng shu shua shuo shuai shui shuan shun shuang "
    "re ri rao rou ran ren rang reng rong ru rua ruo rui ruan run "
    "za ze zi zai zei zao zou zan zen zang zeng zong zu zuo zui zuan zun "
    "ca ce ci cai cao cou can cen cang ceng cong cu cuo cui cuan cun "
    "sa se si sai sao sou san sen sang seng song su suo sui suan sun"
).split(" "))

# The longest syllable (`zhuang`), plus the `r` of erhua.
_LONGEST = 7

# A marked vowel → its bare vowel and tone, in both cases.
_UNMARK: dict[str, tuple[str, int]] = {}
for _vowel, _marked in _MARKS.items():
    for _index, _character in enumerate(_marked):
        _UNMARK[_character] = (_vowel, _index + 1)
        _UNMARK[_character.upper()] = (_vowel.upper(), _index + 1)

_GAP = re.compile(r"([\s'’\-]+)")
_NUMBERED_PART = re.compile(r"[a-zü]+[0-5]|.", re.IGNORECASE)


def unmark(text: str) -> tuple[str, int | None, int]:
    """The syllable without its mark, the tone the mark said (`None` when it had none), and how many
    marks it carried."""
    tone: int | None = None
    marks = 0
    bare = []
    for character in text:
        found = _UNMARK.get(character)
        if found:
            tone = found[1]
            marks += 1
            bare.append(found[0])
        else:
            bare.append(character)
    return "".join(bare), tone, marks


def _syllable_shape(bare: str) -> bool | None:
    """Whether a bare syllable (any case) carries erhua; `None` when Pinyin has no such syllable."""
    lower = bare.lower()
    if lower in INVENTORY:
        return False
    if lower.endswith("r") and lower[:-1] in INVENTORY and lower != "err":
        return True
    return None


def _cut_run(run: str) -> list[tuple[str, int | None, bool]] | None:
    """Cuts one run of tone-marked letters into syllables: `túshūguǎn` → `tú`, `shū`, `guǎn`.

    Longest match first, backing off when the rest will not cut. One mark per syllable settles most
    ambiguity a toneless table leaves (`xīān` is `xī` + `ān`), and erhua is allowed only at the end of
    a run, where Pinyin writes it.
    """

    def cut(start: int) -> list[tuple[str, int | None, bool]] | None:
        if start == len(run):
            return []
        for length in range(min(_LONGEST, len(run) - start), 0, -1):
            text = run[start:start + length]
            bare, tone, marks = unmark(text)
            if marks > 1:
                continue
            erhua = _syllable_shape(bare)
            if erhua is None or (erhua and start + length != len(run)):
                continue
            rest = cut(start + length)
            if rest is not None:
                return [(text, tone, erhua), *rest]
        return None

    return cut(0)


def pinyin_syllables(reading: str) -> list[Syllable] | None:
    """A Mandarin reading as syllables with tones, from numbered or tone-marked Pinyin alike.

    `tu2 shu1 guan3`, `tú shū guǎn` and `túshūguǎn` give the same three syllables. CC-CEDICT's `r5`
    (the 儿 of 一点儿) joins the syllable before it. `None` when the reading does not read as Pinyin,
    or when it carries no tone at all: a reading with no marks is not one whose tones are neutral.
    """
    source = unicodedata.normalize("NFC", reading).strip()
    if not source:
        return None
    syllables: list[Syllable] = []
    toned = False
    gap = ""
    for piece in _GAP.split(source):
        if not piece:
            continue
        if _GAP.fullmatch(piece):
            gap += re.sub(r"\s+", " ", piece).replace("’", "'")
            continue
        before = gap if syllables else ""
        gap = ""
        if re.search(r"[0-9]", piece):
            # Numbered: each syllable carries its digit; a run may hold several (`tu2shu1`).
            ascii_form = re.sub(r"v", "ü", re.sub(r"u:", "ü", piece, flags=re.IGNORECASE), flags=re.IGNORECASE)
            first = True
            for part in _NUMBERED_PART.findall(ascii_form):
                numbered = _SYLLABLE.match(part)
                if not numbered:
                    return None
                # After j, q, x and y the dots are never written: `ju`, not `jü`.
                letters = re.sub(r"^([jqxy])ü", r"\1u", numbered.group(1), flags=re.IGNORECASE)
                digit = numbered.group(2)
                tone = 5 if digit == "0" else int(digit)
                if letters.lower() == "r" and syllables:
                    previous = syllables[-1]
                    syllables[-1] = previous._replace(text=previous.text + "r", erhua=True)
                    first = False
                    continue
                erhua = _syllable_shape(letters)
                if erhua is None:
                    return None
                if tone != 5:
                    toned = True
                syllables.append(Syllable(_accent_syllable(f"{letters}{tone}"), tone, erhua, before if first else ""))
                first = False
            continue
        if not piece.isalpha():
            return None
        cut = _cut_run(piece)
        if cut is None:
            return None
        for index, (text, tone, erhua) in enumerate(cut):
            if tone:
                toned = True
            syllables.append(Syllable(text, tone or 5, erhua, before if index == 0 else ""))
    return syllables if toned and syllables else None
