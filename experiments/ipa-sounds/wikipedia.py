"""Read each sound's English Wikipedia article: its infobox recording and its Occurrence table.

    uv run --no-project --with beautifulsoup4 python experiments/ipa-sounds/wikipedia.py

For every consonant, affricate and vowel in the table (web/src/ipa/symbols.json) it fetches the
article named by the row's `name` (or, failing that, its `audio` phrases), through the REST endpoint, paced and honouring
Retry-After, and caches the page under out/wikipedia/ so a rerun asks for nothing. From each page it
keeps:

- the Commons audio files the infobox embeds: the recording Wikipedia itself uses for the sound,
  the first candidate the review page offers;
- the rows of the Occurrence table that name a language the row's `like` or `heard` cites (English
  always), so each analogy can be checked against what the article says.

Writes results/wikipedia.json. The analogies are judged by reading it, not by this script.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
TABLE = HERE.parents[1] / "web" / "src" / "ipa" / "symbols.json"
CACHE = HERE / "out" / "wikipedia"
REST = "https://en.wikipedia.org/api/rest_v1/page/html/"
USER_AGENT = "AcervoIPASurvey/0.1 (one-off survey of IPA analogies for a language-learning app)"
PAUSE = 2.0
LANGUAGE = re.compile(r"\b([A-Z][a-z]+)\b")


def fetch(title: str) -> str | None:
    """The article's HTML, from the cache or the REST endpoint; None when there is no such article."""
    path = CACHE / f"{title}.html"
    if path.exists():
        return path.read_text(encoding="utf-8") or None
    url = REST + urllib.parse.quote(title.replace(" ", "_"), safe="")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as error:
            if error.code == 404:
                text = ""
                break
            if error.code != 429 or attempt == 5:
                raise
            wait = int(error.headers.get("Retry-After") or 30) + 5
            print(f"  429, waiting {wait} s", file=sys.stderr)
            time.sleep(wait)
    time.sleep(PAUSE)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text or None


def infobox_audio(soup: BeautifulSoup) -> list[str]:
    box = soup.find("table", class_=re.compile("infobox"))
    if box is None:
        return []
    files = []
    for element in box.find_all(["audio", "video"]):
        resource = element.get("resource", "")
        if "File:" in resource:
            files.append(urllib.parse.unquote(resource.split("File:", 1)[1]).replace("_", " "))
    return list(dict.fromkeys(files))


def occurrence_rows(soup: BeautifulSoup) -> list[str]:
    """Every row of the article's occurrence tables as 'Language | word | IPA | meaning | notes'."""
    rows: list[str] = []
    for heading in soup.find_all(["h2", "h3"]):
        if not heading.get_text(strip=True).lower().startswith("occurrence"):
            continue
        section = heading.find_parent("section") or heading.parent
        for table in section.find_all("table", class_=re.compile("wikitable")):
            width, language = 0, ""
            for tr in table.find_all("tr"):
                cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
                if not cells or tr.find("th") and not tr.find("td"):
                    continue
                if len(cells) >= width:
                    width, language = len(cells), cells[0]
                else:
                    cells = [language, *cells]
                rows.append(" | ".join(cells))
    return rows


def cited_languages(entry: dict) -> set[str]:
    text = " ".join(str(entry.get(key) or "") for key in ("heard",))
    names = {m for m in LANGUAGE.findall(text)}
    return {"English", *names}


def main() -> int:
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    entries = [e for section in ("consonants", "affricates", "vowels") for e in table[section]]
    result: dict[str, dict] = {}
    for number, entry in enumerate(entries, 1):
        titles = [entry["name"], *(entry.get("audio") or [])]
        for title in dict.fromkeys(t[0].upper() + t[1:] for t in titles):
            page = fetch(title)
            if page:
                break
        else:
            result[entry["symbol"]] = {"article": None}
            print(f"{number}/{len(entries)} {entry['symbol']}: no article", file=sys.stderr)
            continue
        soup = BeautifulSoup(page, "html.parser")
        languages = cited_languages(entry)
        rows = occurrence_rows(soup)
        result[entry["symbol"]] = {
            "article": title,
            "audio": infobox_audio(soup),
            "like": entry.get("like"),
            "heard": entry.get("heard"),
            "rows": [r for r in rows if any(r.startswith(lang) or f"{lang} " in r.split(" | ")[0] for lang in languages)],
            "rowCount": len(rows),
        }
        print(f"{number}/{len(entries)} {entry['symbol']}: {title}, {len(result[entry['symbol']]['audio'])} audio, "
              f"{len(rows)} rows", file=sys.stderr)
    out = HERE / "results" / "wikipedia.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
