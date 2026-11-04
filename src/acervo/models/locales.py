"""What a locale tag means, for choosing a voice: facts about languages, never about providers.

A voice is either made for one locale — `es-ES`, `en-GB` — or speaks any locale it is told to. Which
voice suits Spanish *as spoken in Argentina* is therefore a comparison between two tags, and the
comparison needs three facts no provider supplies:

- **Which locales are close.** CLDR's parent locales: `es-AR`, `es-MX` and `es-US` all descend from
  `es-419`, Latin American Spanish, and `en-GB` and `en-AU` from `en-001`. A US Spanish voice is the
  nearer stand-in for Argentina than a Castilian one, and this is how that is known.
- **Which locale a bare language means.** CLDR's likely subtags: `es` is `es-ES`, `zh-Hans` is
  `zh-Hans-CN`. A vocabulary with no accent set keeps the voices it always had.
- **What to call them.** "Argentina", "Spanish", in English, for the interface and for a direction.

- **Where a language has an accent of its own** — the regions offered as a vocabulary's accent
  (`accents`): where CLDR says the language is official, most speakers first.

All of it is CLDR data, read through Babel — and the speaker counts through `langcodes`, which
carries CLDR's population figures where Babel does not — rather than restated by hand. Tags are
parsed here rather than by Babel, because a tag a provider declares need not be a locale CLDR has
data for.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

# How well a voice's locale serves the locale asked for, best first. `any` is a voice that speaks
# whatever locale it is told; `unstated` is a voice whose row does not say which accent it has.
MATCHES = ("exact", "any", "near", "main", "other", "unstated")


@dataclass(frozen=True)
class Tag:
    language: str
    script: str | None = None
    region: str | None = None

    def __str__(self) -> str:
        return "-".join(part for part in (self.language, self.script, self.region) if part)


def parse(tag: str) -> Tag:
    """`zh-Hans-CN` → language, script, region. Anything after the region is not ours to read."""
    parts = [part for part in str(tag).replace("_", "-").split("-") if part]
    language = parts.pop(0).lower() if parts else ""
    script = region = None
    if parts and len(parts[0]) == 4 and parts[0].isalpha():
        script = parts.pop(0).title()
    if parts and ((len(parts[0]) == 2 and parts[0].isalpha()) or (len(parts[0]) == 3 and parts[0].isdigit())):
        region = parts.pop(0).upper()
    return Tag(language, script, region)


def with_region(language: str, region: str | None) -> str:
    """A vocabulary's spoken locale: its language with its accent, or the bare language."""
    return str(Tag(parse(language).language, parse(language).script, region.upper())) if region else language


@lru_cache(maxsize=1)
def _cldr() -> tuple[dict[str, str], dict[str, str]]:
    from babel.core import get_global

    return dict(get_global("parent_exceptions")), dict(get_global("likely_subtags"))


def _script(language: str, region: str | None) -> str | None:
    """The script a language is written in by default, in a region if one is given."""
    _, subtags = _cldr()
    for key in ((f"{language}_{region}",) if region else ()) + (language,):
        if found := subtags.get(key):
            return parse(found).script
    return None


def likely(tag: str) -> Tag:
    """The locale a tag most likely means, script and region filled in: `es` → `es-Latn-ES`,
    `zh-Hant` → `zh-Hant-TW`, `es-AR` → `es-Latn-AR`. Two tags are the same locale when these agree."""
    parsed = parse(tag)
    _, subtags = _cldr()
    region = parsed.region
    if not region:
        key = "_".join(part for part in (parsed.language, parsed.script) if part)
        found = subtags.get(key) or subtags.get(parsed.language)
        region = parse(found).region if found else None
    return Tag(parsed.language, parsed.script or _script(parsed.language, region), region)


def lineage(tag: str) -> tuple[Tag, ...]:
    """The locale and every regional ancestor CLDR names, nearest first: `es-AR`, `es-419`.

    Only the regional ones: the bare language is everybody's ancestor and says nothing about accent.
    """
    exceptions, _ = _cldr()
    current = likely(tag)
    found = [current]
    while current.region:
        keys = (f"{current.language}_{current.script}_{current.region}", f"{current.language}_{current.region}")
        parent = next((exceptions[key] for key in keys if key in exceptions), None)
        if not parent or parent == "root":
            break
        named = parse(parent)
        current = Tag(current.language, named.script or current.script, named.region)
        if not current.region:
            break
        found.append(current)
    return tuple(found)


def same_language(one: str, other: str) -> bool:
    """`es-AR` and `es-ES` are one language; `zh-Hans` and `zh-Hant` are not."""
    a, b = likely(one), likely(other)
    return a.language == b.language and a.script == b.script


def match(voice_locale: str | None, wanted: str, *, instruction: bool) -> str:
    """How a voice made for `voice_locale` serves `wanted`: one of `MATCHES`.

    `voice_locale` is None for a voice that is not made for one locale. Such a voice is `any` when
    its model takes an instruction — it can be told the accent — and `unstated` otherwise. A bare
    `wanted` (`es`, no accent chosen) is served best by the language's main locale.
    """
    if voice_locale is None:
        return "any" if instruction else "unstated"
    if not parse(voice_locale).region:
        return "unstated"
    voice, asked = likely(voice_locale), likely(wanted)
    if voice == asked:
        return "exact" if parse(wanted).region else "main"
    if parse(wanted).region and set(lineage(voice_locale)) & set(lineage(wanted)[1:]):
        # A shared regional parent: `es-419` for Argentina and the US.
        return "near"
    if voice == likely(str(Tag(asked.language, parse(wanted).script))):
        return "main"
    return "other"


def rank(found: str) -> int:
    return MATCHES.index(found)


# Where a language is official, or official in part of a country (Spanish in the US), it is spoken
# there natively, with an accent of its own. Where it is only widely learned (English in Germany,
# Spanish in the Philippines) CLDR names no status, and that is no accent to learn.
SPOKEN_HERE = ("official", "de_facto_official", "official_regional")
# Fewer speakers than this is a footnote rather than an accent anybody sets out to learn.
FEWEST_SPEAKERS = 200_000


@lru_cache(maxsize=64)
def accents(language: str) -> tuple[str, ...]:
    """The regions `language` has an accent of its own in, most speakers first: `es` → `MX`, `AR`,
    `ES`, `CO`, …, then a wider region two of them share (`419`, Latin America).

    The language's script is respected: `zh-Hant` is Taiwan and Hong Kong, `zh-Hans` the mainland
    and Singapore. Empty for a language CLDR knows nothing about.
    """
    import langcodes
    from babel.core import get_global

    parsed = parse(language)
    found: list[tuple[int, str]] = []
    for territory, spoken in get_global("territory_languages").items():
        if len(territory) != 2:
            continue
        here = spoken.get(f"{parsed.language}_{parsed.script}") if parsed.script else None
        if here is None:
            here = spoken.get(parsed.language)
            # `zh` in a territory counts for the script that territory writes it in.
            if here is not None and parsed.script and _script(parsed.language, territory) != parsed.script:
                here = None
        if not here or here.get("official_status") not in SPOKEN_HERE:
            continue
        tag = "-".join(part for part in (parsed.language, parsed.script, territory) if part)
        speakers = langcodes.Language.get(tag).speaking_population()
        if speakers >= FEWEST_SPEAKERS:
            found.append((speakers, territory))
    regions = [territory for _, territory in sorted(found, key=lambda pair: (-pair[0], pair[1]))]
    # A wider region is offered when it is what two or more of these share — `es-419`.
    shared: dict[str, int] = {}
    for region in regions:
        tag = "-".join(part for part in (parsed.language, parsed.script, region) if part)
        for parent in lineage(tag)[1:]:
            if parent.region and parent.region.isdigit() and parent.region != "001":
                shared[parent.region] = shared.get(parent.region, 0) + 1
    return tuple(regions + [region for region, count in shared.items() if count >= 2])


def region_name(region: str | None) -> str | None:
    """`AR` → "Argentina", `419` → "Latin America". None for no region or one CLDR does not name."""
    if not region:
        return None
    from babel import Locale

    return Locale("en").territories.get(region.upper())


def language_name(tag: str) -> str:
    """`es-AR` → "Spanish", `zh-Hans` → "Chinese". The tag itself where CLDR has no name."""
    from babel import Locale

    parsed = parse(tag)
    names = Locale("en").languages
    return names.get(parsed.language) or tag
