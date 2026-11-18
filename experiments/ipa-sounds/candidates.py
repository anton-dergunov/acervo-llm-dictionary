"""Gather the Wikimedia Commons recordings of each sound in symbols.yaml, with licence and author.

    uv run --no-project --with beautifulsoup4,pyyaml python experiments/ipa-sounds/wikipedia.py   # first
    .venv/bin/python experiments/ipa-sounds/candidates.py [--search]

Standard library and PyYAML only. A row's candidates come, in this order, from:

1. the recordings its Wikipedia article's infobox embeds (results/wikipedia.json, from wikipedia.py);
2. the files symbols.yaml names outright (`files`), and `Zh-<syllable>` for a Pinyin example;
3. the members of the Commons categories that hold IPA recordings (CATEGORIES), kept when the title
   is the sound's name and nothing more ("Voiceless retroflex sibilant (2).ogg" yes, "Labialized
   voiceless retroflex sibilant.ogg" no); titles that hold the name plus other words go to
   `nearMisses` to look at by eye;
4. with --search, a full-text search of Commons for the rows still without one.

Commons rate-limits searches hard, which is why a search is the last resort: listing a category is
one request for hundreds of files. Then it asks Commons for each file's licence, author and the MP3
copy Commons makes of it (an iPad will not play Ogg), 40 files a request. Requests are paced, honour
Retry-After and carry a descriptive User-Agent, as Wikimedia's API etiquette asks. Nothing is
downloaded. Writes results/candidates.json.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "AcervoIPASurvey/0.1 (one-off survey of IPA recordings for a language-learning app)"
PAUSE = 1.5
# Where Commons files the chart recordings (found from the categories of the infobox files).
CATEGORIES = [
    "Category:Audio files of phonetic samples",
    "Category:Pronunciation of vowels",
    "Category:Pulmonic consonants",
]
AUDIO = re.compile(r"\.(ogg|oga|opus|wav|mp3|flac|webm)$", re.IGNORECASE)
# Free licences the app can ship. GFDL alone is not one: it wants the licence text shipped with the file.
FREE = re.compile(r"^(public domain|pd|cc0|cc by(-sa)? \d)", re.IGNORECASE)
# Words a title may add to the sound's name and still be a recording of just that sound.
EXTRA_OK = {"ipa", "sound", "sample", "new", "version", "female", "male", "audio", "recording", "v", "alt",
            "alternative", "sibilant", "fricative", "consonant", "vowel", "stop", "plosive", "unrounded"}


def api(params: dict) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                answer = json.loads(response.read())
            time.sleep(PAUSE)
            return answer
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 5:
                raise
            wait = int(error.headers.get("Retry-After") or 30) + 5
            print(f"  429, waiting {wait} s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def words(text: str) -> list[str]:
    text = AUDIO.sub("", text.removeprefix("File:")).lower()
    text = text.replace("labio-velar", "labial-velar").replace("labiovelar", "labial-velar")
    text = text.replace("plosive", "stop").replace("colour", "color")
    return [w for w in re.split(r"[\s_\-–(),.]+", text) if w]


def is_only(title: str, phrase: str, symbol: str) -> bool:
    title_words, phrase_words = words(title), words(phrase)
    if not all(w in title_words for w in phrase_words):
        return False
    extra = [w for w in title_words if w not in phrase_words]
    return all(w in EXTRA_OK or w.isdigit() or w == symbol.lower() or len(w) <= 2 for w in extra)


def holds(title: str, phrase: str) -> bool:
    return all(w in words(title) for w in words(phrase))


def search(phrase: str) -> list[str]:
    found = api({"action": "query", "list": "search", "srsearch": f'"{phrase}" filetype:audio',
                 "srnamespace": 6, "srlimit": 50})
    return [hit["title"] for hit in found["query"]["search"]]


def category_files(category: str) -> list[str]:
    titles: list[str] = []
    params = {"action": "query", "list": "categorymembers", "cmtitle": category, "cmtype": "file", "cmlimit": 500}
    while True:
        answer = api(params)
        titles += [m["title"] for m in answer.get("query", {}).get("categorymembers", []) if AUDIO.search(m["title"])]
        if "continue" not in answer:
            return titles
        params = {**params, **answer["continue"]}


def entries(table: dict, wikipedia: dict) -> list[dict]:
    """Every row that can have a recording, with an id the labels are keyed by."""
    rows = []
    for section in ("consonants", "affricates", "vowels"):
        for entry in table[section]:
            infobox = [f"File:{name}" for name in (wikipedia.get(entry["symbol"]) or {}).get("audio", [])]
            rows.append({"id": entry["symbol"], "symbol": entry["symbol"],
                         "phrases": list(dict.fromkeys([entry["name"], *(entry.get("audio") or [])])),
                         "files": [*infobox, *(f"File:{f}" for f in entry.get("files", []))]})
    for entry in table["combinations"]:
        rows.append({"id": entry["symbol"], "symbol": entry["symbol"], "phrases": [],
                     "files": [f"File:{f}" for f in entry["files"]]})
    for entry in table["diacritics"]:
        if entry.get("audio"):
            rows.append({"id": entry["example"], "symbol": entry["example"], "phrases": entry["audio"],
                         "files": [f"File:{f}" for f in entry.get("files", [])]})
    for contour in table["tones"]["contours"]:
        rows.append({"id": f"tone {contour['letters']}", "symbol": contour["letters"], "phrases": [],
                     "files": [f"File:{f}" for f in contour.get("files", [])]})
    for part in ("initials", "finals"):
        for row in table["pinyin"][part]:
            rows.append({"id": f"pinyin {row['letters']}", "symbol": row["letters"], "phrases": [],
                         "files": [f"File:Zh-{row['example']}.ogg", f"File:Zh-{row['example']}.oga"]})
    contour_files = {c["letters"]: c.get("files", []) for c in table["tones"]["contours"]}
    for tone in table["pinyin"]["tones"]:
        rows.append({"id": f"pinyin tone {tone['number']}", "symbol": tone["mark"], "phrases": [],
                     "files": [f"File:{f}" for f in [*contour_files.get(tone["ipa"], []), *tone.get("files", [])]]})
    return rows


def describe(titles: list[str]) -> dict[str, dict]:
    """Licence, author and playable copies for each title Commons has."""
    found: dict[str, dict] = {}
    for start in range(0, len(titles), 40):
        batch = titles[start:start + 40]
        answer = api({"action": "query", "titles": "|".join(batch), "prop": "videoinfo",
                      "viprop": "url|mime|size|extmetadata|derivatives",
                      "viextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|AttributionRequired|Credit"})
        aliases = {n["to"]: n["from"] for key in ("normalized", "redirects") for n in answer["query"].get(key, [])}
        for page in answer["query"]["pages"]:
            if page.get("missing") or not page.get("videoinfo"):
                continue
            info = page["videoinfo"][0]
            meta = info.get("extmetadata", {})
            text = lambda key: html.unescape(re.sub(r"<[^>]+>", "", meta.get(key, {}).get("value", ""))).strip()
            mp3 = next((d["src"] for d in info.get("derivatives", []) if d.get("type", "").startswith("audio/mpeg")), None)
            licence = text("LicenseShortName")
            described = {
                "file": page["title"].removeprefix("File:"),
                "page": info.get("descriptionurl"),
                "original": info.get("url", "").split("?")[0],
                "mp3": mp3.split("?")[0] if mp3 else None,
                "mime": info.get("mime"),
                "license": licence,
                "licenseUrl": text("LicenseUrl") or None,
                "free": bool(FREE.match(licence)),
                "author": text("Artist"),
                "attribution": meta.get("AttributionRequired", {}).get("value") == "true",
            }
            found[page["title"]] = described
            if page["title"] in aliases:
                found[aliases[page["title"]]] = described
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--search", action="store_true", help="search Commons for rows still without a recording")
    args = parser.parse_args()
    table = yaml.safe_load((HERE / "symbols.yaml").read_text(encoding="utf-8"))
    wikipedia_path = HERE / "results" / "wikipedia.json"
    if not wikipedia_path.exists():
        raise SystemExit("no results/wikipedia.json: run wikipedia.py first")
    rows = entries(table, json.loads(wikipedia_path.read_text(encoding="utf-8")))

    pool: list[str] = []
    for category in CATEGORIES:
        files = category_files(category)
        print(f"{category}: {len(files)} audio files", file=sys.stderr)
        pool += files
    pool = list(dict.fromkeys(pool))

    titles_for: dict[str, list[str]] = {}
    near_misses: dict[str, list[str]] = {}
    for row in rows:
        titles = list(row["files"])
        for phrase in row["phrases"]:
            for title in pool:
                if is_only(title, phrase, row["symbol"]):
                    titles.append(title)
                elif holds(title, phrase):
                    near_misses.setdefault(row["id"], []).append(title)
        titles_for[row["id"]] = list(dict.fromkeys(titles))

    every = sorted({title for titles in titles_for.values() for title in titles})
    described = describe(every)
    if args.search:
        for row in rows:
            if any(t in described for t in titles_for[row["id"]]) or not row["phrases"]:
                continue
            found = []
            for phrase in row["phrases"]:
                for title in search(phrase):
                    (found if is_only(title, phrase, row["symbol"]) else
                     near_misses.setdefault(row["id"], []) if holds(title, phrase) else []).append(title)
            titles_for[row["id"]] += found
            print(f"searched {row['id']}: {len(found)}", file=sys.stderr)
        described |= describe(sorted({t for titles in titles_for.values() for t in titles} - set(described)))

    result = {
        "about": "Commons recordings per symbols.yaml row, from candidates.py: Wikipedia's infobox files first, "
                 "then named files, then category members named for exactly the sound. nearMisses hold the "
                 "name plus other words, kept for a look by eye. `free` is false for a licence the app "
                 "cannot ship (GFDL alone, or anything not public domain, CC0, CC BY or CC BY-SA).",
        "rows": {row_id: list({described[t]["file"]: described[t] for t in titles if t in described}.values())
                 for row_id, titles in titles_for.items()},
        "nearMisses": {row_id: sorted(set(t.removeprefix("File:") for t in titles) -
                                      {d["file"] for d in (described.get(x) for x in titles_for.get(row_id, [])) if d})
                       for row_id, titles in near_misses.items()},
    }
    result["nearMisses"] = {k: v for k, v in result["nearMisses"].items() if v}
    out = HERE / "results" / "candidates.json"
    # Written whole and swapped in, so a review page reading it meanwhile never sees half a file.
    temporary = out.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(out)
    covered = sum(1 for files in result["rows"].values() if any(f["free"] for f in files))
    several = sum(1 for files in result["rows"].values() if sum(f["free"] for f in files) > 1)
    empty = [row_id for row_id, files in result["rows"].items() if not any(f["free"] for f in files)]
    print(f"{covered}/{len(rows)} rows have a freely licensed recording, {several} more than one; wrote {out}")
    print(f"without one: {' '.join(empty)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
