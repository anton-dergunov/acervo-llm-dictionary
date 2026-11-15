"""What scholars say a character first depicted: the "Glyph origin" of its English Wiktionary entry.

Make Me a Hanzi's hint is sometimes a traditional folk explanation (王 as "a man joining heaven and
earth", where scholars read an axe head). Wiktionary's Chinese "Glyph origin" sections summarise
current scholarship and cite it, so Argon checks every script against them (`argon.py`).

    .venv/bin/python experiments/character-pictures/run.py origins --set common

The wikitext of each page is fetched once, fifty titles a request, and cached in
`out/cache/wiktionary/` (ignored: Wiktionary's text is CC BY-SA, so it is read here and never
committed). A Simplified form whose own section only says where it comes from ("cursive script of
車") also gets the section of the form it points to, so the writer and the checker see the origin of
the drawing itself.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

import run

CACHE = run.HERE / "out" / "cache" / "wiktionary"
API = "https://en.wiktionary.org/w/api.php"
# A generic client name: Wikimedia asks for a descriptive one, and an address is never sent.
AGENT = "acervo-character-pictures/1.0 (a research experiment; reads Glyph origin sections)"
LANGUAGES = ("Chinese", "Translingual")
# Below this many characters of prose (templates and markup stripped), a section says nothing in
# words; it may still say what the character is by a template (`{{liushu|p}}`, `{{Han compound|…}}`).
PROSE = 40


def _path(title: str):
    return CACHE / f"{'-'.join(f'{ord(c):x}' for c in title)}.json"


def cached(title: str) -> dict[str, Any] | None:
    path = _path(title)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def fetch(titles: list[str]) -> int:
    """Fetch every page not cached yet. The number fetched."""
    wanted = [t for t in dict.fromkeys(titles) if cached(t) is None]
    CACHE.mkdir(parents=True, exist_ok=True)
    done = 0
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=60.0) as client:
        for start in range(0, len(wanted), 50):
            chunk = wanted[start:start + 50]
            for attempt in range(6):
                response = client.get(API, params={
                    "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                    "format": "json", "formatversion": "2", "maxlag": "5", "titles": "|".join(chunk)})
                payload = response.json() if response.is_success else {}
                if response.is_success and "error" not in payload:
                    break
                time.sleep(5 * (attempt + 1))  # lag or a refusal: wait, as Wikimedia asks
            else:
                raise ConnectionError(f"Wiktionary would not answer: {response.status_code} {response.text[:200]}")
            pages = {page["title"]: page for page in payload["query"]["pages"]}
            for title in chunk:
                page = pages.get(title) or {}
                text = (((page.get("revisions") or [{}])[0].get("slots") or {}).get("main") or {}).get("content")
                _path(title).write_text(json.dumps({"title": title, "wikitext": text, "missing": text is None},
                                                   ensure_ascii=False), encoding="utf-8")
                done += 1
            time.sleep(1.0)
    return done


def _language(wikitext: str, language: str) -> str:
    match = re.search(rf"^==\s*{language}\s*==\s*$", wikitext, re.M)
    if not match:
        return ""
    rest = wikitext[match.end():]
    end = re.search(r"^==[^=].*==\s*$", rest, re.M)
    return rest[: end.start()] if end else rest


def sections(wikitext: str | None) -> list[tuple[str, str]]:
    """(language, text) of every Glyph origin section, Chinese first."""
    found = []
    for language in LANGUAGES:
        block = _language(wikitext or "", language)
        for match in re.finditer(r"^(=+)\s*Glyph origin[^=]*\1\s*$", block, re.M):
            rest = block[match.end():]
            end = re.search(r"^=+[^=].*=+\s*$", rest, re.M)
            text = re.sub(r"<!--.*?-->", "", rest[: end.start()] if end else rest, flags=re.S).strip()
            if text:
                found.append((language, text))
    return found


def prose(text: str) -> str:
    """The section without templates and markup: what remains is what it says in words."""
    text = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", text, flags=re.S)
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    return re.sub(r"\s+", " ", re.sub(r"'''?|<[^>]+>", "", text)).strip()


def pointed_to(wikitext: str | None) -> list[str]:
    """Characters a Chinese section sends the reader to (`{{zh-see|車}}`, "of {{zh-l|*車}}")."""
    block = _language(wikitext or "", "Chinese")
    targets = re.findall(r"\{\{zh-see\|([^|}]+)", block)
    for _language_name, text in sections(wikitext):
        targets += re.findall(r"\{\{zh-l\|\*?([^|}/]+)", text)[:2]
    return [t for t in dict.fromkeys(t.strip() for t in targets) if len(t) == 1 and run._han(t)]


def related(character: str) -> list[str]:
    """The forms whose origin also tells this character's: its Traditional or Simplified
    counterparts in the catalogue, and whatever its own page points to."""
    forms = []
    for entry in run.catalogue():
        if entry.get("simplified") == character:
            forms.append(entry["character"])
        if entry["character"] == character and entry.get("simplified"):
            forms.append(entry["simplified"])
    page = cached(character) or {}
    forms += pointed_to(page.get("wikitext"))
    return [f for f in dict.fromkeys(forms) if f != character]


def text_for(character: str) -> str:
    """Everything Argon reads about the origin: this character's sections, then its related forms'.
    Empty when Wiktionary says nothing."""
    parts = []
    for title in [character] + related(character):
        page = cached(title) or {}
        for language, text in sections(page.get("wikitext")):
            label = "" if title == character else f" (of {title}, a related form)"
            parts.append(f"### {title}, {language}{label}\n\n{text}")
    return "\n\n".join(parts)


def _informative(text: str) -> bool:
    return len(prose(text)) >= PROSE or bool(re.search(r"\{\{(liushu|Han compound)\|", text))


def informative(character: str) -> bool:
    """Whether the sections say what the character is: in words, or by a classifying template."""
    return any(_informative(text) for title in [character] + related(character)
               for _language_name, text in sections((cached(title) or {}).get("wikitext")))


def origins_command(args: Any) -> None:
    chosen = run.in_scope(set_name=args.set, group=args.group, characters=args.characters)
    characters = [entry["character"] for entry in chosen]
    fetched = fetch(characters)
    fetched += fetch([f for c in characters for f in related(c)])
    counts: dict[str, list[int]] = {}
    for entry in chosen:
        row = counts.setdefault(entry["group"], [0, 0, 0])
        page = cached(entry["character"]) or {}
        row[0] += 1
        row[1] += bool(sections(page.get("wikitext")))
        row[2] += informative(entry["character"])
    print(f"{fetched} pages fetched now, cached in {CACHE.relative_to(run.HERE)}/")
    for group, (total, any_section, worded) in counts.items():
        print(f"  {group}: {total} characters, {any_section} with a Glyph origin section, "
              f"{worded} that say what it is, in words or by its type (itself or a related form)")
