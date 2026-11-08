"""Which settings should Acervo use for ElevenLabs: which model, and what to send for a feeling and
an accent?

ElevenLabs was added an hour before this was written and had only round 0 behind it (`README.md`).
This records one fixed set through Eleven v4 and v3 the way Acervo sends it, plus four ways of
sending v4 an accent alone, and leaves the takes for a blind listening on the tablet (`review.py`).
Gemini on Vertex, the default with a month of real use, reads the same set as a reference for what
a text should sound like; it is not being compared. Round 2, pairs, is `pairs.py`.

    .venv/bin/python experiments/expressive-voice/run.py set        # read-only pull, draw set.json
    .venv/bin/python experiments/expressive-voice/run.py probe      # which routes answer; the free cap
    .venv/bin/python experiments/expressive-voice/run.py bill       # ElevenLabs characters, spends nothing
    .venv/bin/python experiments/expressive-voice/run.py record     # resumable
    experiments/expressive-voice/.venv/bin/python experiments/expressive-voice/transcribe.py
    .venv/bin/python experiments/expressive-voice/run.py blind      # loudness-matched letters + key
    .venv/bin/python experiments/expressive-voice/review.py --host "$(tailscale ip -4)"
    .venv/bin/python experiments/expressive-voice/run.py report     # after listening

Every take goes through `pronunciation.speak.speak`, the function the server calls, pinned to one
pair and one voice, so a direction reaches each voice in the form Acervo would send it — the whole
sentence to Gemini, the short tag to ElevenLabs. The accent group's ElevenLabs variants are the one
place the experiment sends something Acervo does not: that is the question being asked.

`out/` (audio, the pull, the key and labels until the report) is ignored; `set.json` and
`results/` are committed.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from acervo.models import locales
from acervo.models.errors import ProviderError
from acervo.models.local import LOCAL_PATH, SECRET_FIELDS
from acervo.models.providers import Providers, build
from acervo.pronunciation import speak
from acervo.services.prompts import prompt_text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = Path(os.environ.get("EXPRESSIVE_VOICE_OUT") or HERE / "out")
RESULTS = HERE / "results"
SET = HERE / "set.json"
TAKES = RESULTS / "takes.jsonl"
PROMPTS = ROOT / "prompts"
SEED = 20261107

STYLE, ACCENT, STORY = "acervo_pronounce_style", "acervo_pronounce_accent", "acervo_pronounce_story"

# One voice per system. Gemini's is the one the server's expressive order uses for every language
# (read from Settings ▸ Pronunciation on 7 Nov 2026); ElevenLabs' is Sarah, as in round 0, so the two
# rounds compare. (Acervo's own chooser would pick Bella, the first in the account's list.)
SARAH = "EXAVITQu4vr4xnSDxMaL"


@dataclass(frozen=True)
class System:
    id: str
    provider: str
    model: str
    voice: str
    takes: int = 1          # Gemini is asked three times: cheap, and its slips are about 1 in 30


SYSTEMS = (
    System("gemini", "vertex", "gemini-3.1-flash-tts-preview", "Achernar", takes=3),
    System("v4", "elevenlabs", "eleven_v4", SARAH),
    System("v3", "elevenlabs", "eleven_v3", SARAH),
)
BY_ID = {system.id: system for system in SYSTEMS}

# The accent alone, sent to Eleven v4 four ways. `current` is Acervo's tag form when there is a
# feeling, sent here without one, which round 0 heard doubling short texts; `calm` always gives a
# feeling, a candidate fix; `named` names the variety the way people say it; `none` is the control
# and what Acervo sends today.
ACCENT_VARIANTS = ("current", "calm", "named", "none")
VARIETY = {"AR": "Argentine Spanish accent", "ES": "Castilian Spanish accent"}

# Graded word counts for the accent group: round 0 doubled one word and three; where does it stop?
# Twenty-two words was planned too and left out: it did not fit the month's ElevenLabs credits.
ACCENT_LENGTHS = (1, 2, 3, 5, 8, 12, 16)

# Which takes the page shows for each group, as (system, variant). Eleven v3 reads words and
# feelings only: the whole set came to 11,700 characters against 8,968 left in the month, and v4 is
# the model Acervo puts first.
SOURCES = {
    "words": [("gemini", ""), ("v4", ""), ("v3", "")],
    "feeling": [("gemini", ""), ("v4", ""), ("v3", "")],
    "accent": [("gemini", ""), *[("v4", variant) for variant in ACCENT_VARIANTS]],
    "story": [("gemini", ""), ("v4", "")],
}


def sources(item: dict[str, Any]) -> list[tuple[str, str]]:
    """The takes for one item. ElevenLabs takes no region, so the untagged control is the same
    request in both varieties and is recorded once, under Argentina."""
    found = SOURCES[item["group"]]
    if item["group"] == "accent" and not item["language"].endswith("-AR"):
        found = [pair for pair in found if pair != ("v4", "none")]
    return found


# What is trimmed first when ElevenLabs' credits do not cover the set: the end of this list.
PRIORITY = [("v4", "feeling"), ("v4", "accent"), ("v4", "story"), ("v3", "feeling"),
            ("v4", "words"), ("v3", "words")]
MARGIN = 0.05


# ── providers ───────────────────────────────────────────────────────────────


def catalogue(extra: list[dict[str, Any]] | None = None, audio: dict[str, list[Any]] | None = None) -> Providers:
    """`providers.local.json`, read the way `local.load_local` reads it, with experiment-only
    additions held in memory: `audio` adds models to an existing provider, `extra` adds providers
    (a key borrowed from another entry is named `{"keyFrom": id}`). The file is not edited."""
    document = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
    entries = [dict(entry) for entry in document["providers"]]
    by_id = {entry["id"]: entry for entry in entries}
    for provider, models in (audio or {}).items():
        own = dict(by_id[provider].get("models") or {})
        own["audio"] = [*own.get("audio", []), *models]
        by_id[provider]["models"] = own
    for entry in extra or []:
        entry = dict(entry)
        source = entry.pop("keyFrom", None)
        if source:
            entry["key"] = by_id[source]["key"]
        entries.append(entry)
    rows, secrets = [], {}
    for position, entry in enumerate(entries):
        secret = {name: entry[name] for name in SECRET_FIELDS if entry.get(name)}
        if isinstance(secret.get("credentials"), str):
            secret["credentials"] = json.loads(Path(secret["credentials"]).expanduser().read_text(encoding="utf-8"))
        rows.append({**{k: v for k, v in entry.items() if k not in SECRET_FIELDS}, "position": position})
        secrets[str(entry["id"])] = secret
    providers, refused = build(rows, secrets)
    if refused:
        sys.exit(f"provider {refused[0][0]!r}: {refused[0][1]}")
    return providers


def say(providers: Providers, provider: str, model: str, voice: str | None, text: str, language: str,
        style: str | None) -> speak.Spoken:
    return speak.speak(text, language, chosen=[(provider, model)], catalogue=providers, style=style,
                       voice=lambda *_: voice, caller="pronounce-preview")


def failure(error: BaseException) -> str:
    """The provider's own sentence: a chain keeps the last one it heard on `last`."""
    last = getattr(error, "last", None)
    return f"{type(last or error).__name__}: {last or error}"


def credits(providers: Providers) -> dict[str, Any]:
    key = providers.find("elevenlabs").credential.key
    answer = httpx.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=20)
    answer.raise_for_status()
    found = answer.json()
    return {"used": found["character_count"], "limit": found["character_limit"],
            "left": found["character_limit"] - found["character_count"], "tier": found.get("tier")}


# ── the set ─────────────────────────────────────────────────────────────────


def _words(text: str) -> int:
    return len(re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ']+", text))


def _audible(text: str) -> int:
    """How much of an Argentine or Castilian accent a Spanish text gives a listener to hear: «ll» and
    «y» (sheísmo), «z», «ce», «ci» (distinción), and a final «s»."""
    lowered = text.lower()
    return (len(re.findall(r"ll|y[aeiouáéíóú]", lowered)) * 2 + len(re.findall(r"z|c[eiéí]", lowered)) * 2
            + len(re.findall(r"s\b", lowered)))


def _repeats(text: str) -> bool:
    """Whether the text says a pair of words twice itself ("el cuello, el cuello"), which would
    read as a doubling. Pairs of short words ("de la") do not count."""
    words = [w.lower() for w in re.findall(r"[\wáéíóúüñ']+", text)]
    runs = [pair for pair in zip(words, words[1:]) if max(len(w) for w in pair) >= 4]
    return len(runs) != len(set(runs))


def _sentence(text: str) -> bool:
    first = text.lstrip("¿¡«\"")[:1]
    return bool(first) and first.isupper() and text.rstrip()[-1:] in ".!?»\""


def draw(args: argparse.Namespace) -> None:
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    live = lambda kind: [record for record in graph[kind] if not record.get("deleted")]
    vocabularies = {v["language"]: v for v in live("vocabularies")}
    region = {language: (v.get("region") or "") for language, v in vocabularies.items()}
    locale = lambda language: f"{language}-{region[language]}" if region.get(language) else language
    pick = random.Random(SEED)
    items: list[dict[str, Any]] = []

    def add(group: str, text: str, language: str, note: str = "", **more: Any) -> None:
        items.append({"id": f"{group[0]}{sum(1 for item in items if item['group'] == group) + 1:02d}",
                      "group": group, "language": language, "text": " ".join(text.split()),
                      "note": note, "words": _words(text), **more})

    lexemes = live("lexemes")
    examples = [e for e in live("examples") if e.get("emotion") and e.get("origin") in ("llm", "attestation")]

    # Accent alone: one Spanish text per length, heard in both varieties.
    accent: list[tuple[str, str]] = []
    texts = [(l["headword"], l["id"]) for l in lexemes if l["language"] == "es"]
    texts += [(e["text"], e["id"]) for e in live("examples") if e["textLang"] == "es" and _sentence(e["text"])]
    for length in ACCENT_LENGTHS:
        pool = [(text, source) for text, source in texts if _words(text) == length
                and (text, source) not in accent and not _repeats(text)]
        pool.sort(key=lambda pair: (-min(_audible(pair[0]), 2 + length), pick.random()))
        accent.append(pool[0])
    # Words: headwords as Acervo reads them, Spanish ones with something of the accent in them.
    spanish = [l for l in lexemes if l["language"] == "es" and 1 <= _words(l["headword"]) <= 3
               and l["headword"] not in {text for text, _ in accent}]
    spanish.sort(key=lambda l: (-min(_audible(l["headword"]), 4), pick.random()))
    for lexeme in spanish[:6]:
        add("words", lexeme["headword"], locale("es"), source=lexeme["id"])
    english = [l for l in lexemes if l["language"] == "en" and _words(l["headword"]) <= 2]
    for lexeme in pick.sample(english, 2):
        add("words", lexeme["headword"], locale("en"), source=lexeme["id"])
    russian = [l for l in lexemes if l["language"] == "en" and l.get("primaryGloss")
               and _words(l["primaryGloss"]) == 1 and re.search("[а-яё]", l["primaryGloss"])]
    for lexeme in pick.sample(russian, 2):
        add("words", lexeme["primaryGloss"], "ru", source=lexeme["id"], origin="Russian gloss of an English word")

    # Feeling: real examples with the emotion stored on them; Russian from the Russian translations
    # of English examples, which carry that example's emotion.
    fits = lambda text: 30 <= len(text) <= 85 and _sentence(text)
    used: set[str] = set()
    for language, count in (("es", 9), ("en", 3)):
        pool = [e for e in examples if e["textLang"] == language and fits(e["text"])]
        for example in pick.sample(pool, count):
            used.add(example["id"])
            add("feeling", example["text"], locale(language), example["emotion"], source=example["id"])
    pool = [e for e in examples if e["textLang"] == "en" and e.get("translationLang") == "ru"
            and e["id"] not in used and fits(e.get("translation") or "")]
    for example in pick.sample(pool, 3):
        add("feeling", example["translation"], "ru", example["emotion"], source=example["id"],
            origin="Russian translation of an English example, with its emotion")

    for variety in ("AR", "ES"):
        for text, source in accent:
            add("accent", text, f"es-{variety}", source=source)

    # Story: passages as the server cut them, each with the direction it was recorded under.
    stories = {s["id"]: s for s in live("stories")}
    passages = [(part, segment) for part in live("storyParts") for segment in part.get("audioSegments") or []
                if (segment.get("direction") or "").strip() and 70 <= len(segment["text"].strip()) <= 170]
    seen: set[str] = set()
    english = [pair for pair in passages if stories.get(pair[0]["storyId"], {}).get("language") == "en"]
    # One English passage when an English story was ever read with directions; Spanish otherwise.
    for language, count in (("es", 3 if english else 4), ("en", 1 if english else 0)):
        pool = [pair for pair in passages if stories.get(pair[0]["storyId"], {}).get("language") == language]
        chosen = []
        for part, segment in pick.sample(pool, len(pool)):
            if count == 0:
                break
            # A passage per story while there are stories enough; a part apart from that otherwise.
            if part["storyId"] in seen and len({p["storyId"] for p, _ in pool}) >= count:
                continue
            if part["id"] in seen:
                continue
            seen.add(part["id"])
            seen.add(part["storyId"])
            chosen.append((part, segment))
            if len(chosen) == count:
                break
        for part, segment in chosen:
            add("story", segment["text"], locale(language), segment["direction"].strip(), source=part["id"],
                title=stories[part["storyId"]].get("title") or "")

    SET.write_text(json.dumps({"seed": SEED, "regions": region, "items": items}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    for group, found in Counter(item["group"] for item in items).items():
        print(f"{group:8} {found}")
    for item in items:
        print(f"  {item['id']} {item['language']:6} {item['text'][:70]!r}  {item['note'][:50]}")


def items() -> list[dict[str, Any]]:
    return json.loads(SET.read_text(encoding="utf-8"))["items"]


# ── what each take is sent ──────────────────────────────────────────────────


def template(name: str) -> str:
    return prompt_text(PROMPTS, name)


def style_for(item: dict[str, Any], system: System, variant: str) -> speak.Direction | None:
    """The direction Acervo would hand `speak` for this item — `speak.asked_of` then sends Gemini
    the sentence and ElevenLabs the tag — or, for the accent variants, the tag under test."""
    language, note = item["language"], item["note"]
    if item["group"] == "feeling":
        return speak.direction(template(STYLE), note, language)
    if item["group"] == "story":
        return speak.direction(template(STORY), note, language)
    # Words and the accent alone: what `services.pronunciations.directed` sends with no feeling.
    alone = speak.direction(template(ACCENT), "", language) if speak.accented(language) else None
    if item["group"] == "words" or system.provider != "elevenlabs":
        return alone
    region = locales.parse(language).region or ""
    where = locales.region_name(region)
    tags = {"current": f"accent from {where}", "calm": f"calm and natural; accent from {where}",
            "named": VARIETY.get(region, f"accent from {where}"), "none": None}
    tag = tags[variant]
    return speak.Direction(str(alone), tag) if tag else None


def planned() -> list[dict[str, Any]]:
    """Every take to record: item, system, variant, take number."""
    found = []
    for item in items():
        for system_id, variant in sources(item):
            system = BY_ID[system_id]
            for take in range(1, system.takes + 1):
                found.append({"item": item["id"], "system": system_id, "variant": variant, "take": take})
    return found


def key_of(row: dict[str, Any]) -> str:
    return f"{row['item']}/{row['system']}{'-' + row['variant'] if row['variant'] else ''}/{row['take']}"


def billed(item: dict[str, Any], system: System, variant: str) -> int:
    """The characters ElevenLabs bills for this take: the words and the tag as `elevenlabs.worded`
    sends them."""
    from acervo.models.elevenlabs import worded

    style = style_for(item, system, variant)
    tag = getattr(style, "tag", None) if style is not None and item["group"] != "words" else None
    return len(worded(item["text"], tag))


def budget(providers: Providers) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    """Which (system, group) pairs of ElevenLabs fit in the credits left, by `PRIORITY`."""
    left = credits(providers)
    allowed = int(left["left"] * (1 - MARGIN))
    by_item = {item["id"]: item for item in items()}
    cost: dict[tuple[str, str], int] = defaultdict(int)
    for row in planned():
        system = BY_ID[row["system"]]
        if system.provider == "elevenlabs":
            item = by_item[row["item"]]
            cost[(row["system"], item["group"])] += billed(item, system, row["variant"])
    kept, spent = set(), 0
    for pair in PRIORITY:
        if spent + cost[pair] <= allowed:
            kept.add(pair)
            spent += cost[pair]
    return kept, {"credits": left, "allowed": allowed, "cost": {f"{s}/{g}": c for (s, g), c in cost.items()},
                  "kept": sorted(f"{s}/{g}" for s, g in kept), "spend": spent}


def bill(args: argparse.Namespace) -> None:
    _, plan = budget(catalogue())
    print(json.dumps(plan, indent=1))


# ── probe ───────────────────────────────────────────────────────────────────


PROBE_TEXT = "Ayer llovió tanto que la calle quedó llena de charcos."
PROBE_STYLE = "Say it surprised and a little amused."


def probe(args: argparse.Namespace) -> None:
    """Which Gemini routes answer, and the free key's cap, written to `results/probe.json`.

    Each route is asked one sentence. The free key is then asked until it refuses (at most
    `--cap-calls`), three a minute, so its own 429 says what the limit is."""
    providers = catalogue(
        audio={"vertex": [{"id": "gemini-3.8-flash-tts", "direction": True},
                          {"id": "gemini-3.8-flash-lite-tts", "direction": True},
                          {"id": "gemini-2.5-pro-tts", "direction": True}],
               "gemini-api": [{"id": "gemini-3.8-flash-tts", "direction": True}]},
        extra=[{"id": "google-key-as-gemini-api", "family": "gemini-api", "keyFrom": "google-key",
                "models": {"audio": [{"id": "gemini-3.8-flash-tts", "direction": True},
                                     {"id": "gemini-3.8-flash-lite-tts", "direction": True}]}}],
    )
    found: dict[str, Any] = _read(RESULTS / "probe.json", {})
    routes = [("vertex", "gemini-3.1-flash-tts-preview"), ("vertex", "gemini-2.5-flash-tts"),
              ("vertex", "gemini-3.8-flash-tts"), ("vertex", "gemini-3.8-flash-lite-tts"),
              ("vertex", "gemini-2.5-pro-tts"),
              ("google-key-as-gemini-api", "gemini-3.8-flash-tts"),
              ("google-key-as-gemini-api", "gemini-3.8-flash-lite-tts")]
    (OUT / "probe").mkdir(parents=True, exist_ok=True)
    answers = found.setdefault("routes", {})
    for provider, model in routes:
        name = f"{provider}/{model}"
        if name in answers and not args.again:
            continue
        answers[name] = _try(providers, provider, model, PROBE_TEXT, "es-AR", PROBE_STYLE, OUT / "probe" / f"{provider}-{model}")
        print(f"{name}: {answers[name]}")
        _write(RESULTS / "probe.json", found)

    if args.cap_calls:
        free = found.setdefault("free", {"calls": []})
        model = "gemini-3.8-flash-lite-tts"
        texts = [item for item in items() if item["group"] in ("feeling", "words")]
        for item in texts[len(free["calls"]):args.cap_calls]:
            started = time.monotonic()
            answer = _try(providers, "gemini-api", model, item["text"], item["language"], None,
                          OUT / "free" / item["id"])
            free["calls"].append({"item": item["id"], "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **answer})
            _write(RESULTS / "probe.json", found)
            print(f"free {len(free['calls'])}: {answer}")
            if not answer.get("ok"):
                break
            time.sleep(max(0.0, 21.0 - (time.monotonic() - started)))


def _try(providers: Providers, provider: str, model: str, text: str, language: str, style: str | None,
         stem: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        spoken = say(providers, provider, model, None, text, language, style)
    except (ProviderError, speak.NoVoice, Exception) as error:  # the sentence is the finding
        return {"ok": False, "error": failure(error)[:600], "seconds": round(time.monotonic() - started, 2)}
    stem.parent.mkdir(parents=True, exist_ok=True)
    path = stem.with_suffix("." + speak.extension_for(spoken.result.mime))
    path.write_bytes(spoken.result.data)
    return {"ok": True, "voice": spoken.result.voice, "bytes": len(spoken.result.data),
            "seconds": round(time.monotonic() - started, 2), "sent": spoken.direction}


# ── record ──────────────────────────────────────────────────────────────────


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)


def done() -> dict[str, dict[str, Any]]:
    if not TAKES.exists():
        return {}
    rows = [json.loads(line) for line in TAKES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {key_of(row): row for row in rows}


def master_path(row: dict[str, Any]) -> Path:
    return OUT / "masters" / f"{key_of(row).replace('/', '_')}.wav"


def seconds_of(path: Path) -> float:
    found = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, check=True).stdout.strip()
    return round(float(found), 2)


def record(args: argparse.Namespace) -> None:
    providers = catalogue()
    kept, plan = budget(providers)
    print(f"ElevenLabs: {plan['credits']['left']} credits left, spending at most {plan['spend']}; "
          f"left out: {sorted(set(plan['cost']) - set(plan['kept'])) or 'nothing'}")
    by_item = {item["id"]: item for item in items()}
    have = done()
    todo = [row for row in planned() if key_of(row) not in have and
            (BY_ID[row["system"]].provider != "elevenlabs" or (row["system"], by_item[row["item"]]["group"]) in kept)]
    if args.only:
        todo = [row for row in todo if row["system"] in args.only.split(",")]
    print(f"{len(have)} recorded, {len(todo)} to go")
    deadline = time.monotonic() + args.minutes * 60
    failures = 0
    TAKES.parent.mkdir(parents=True, exist_ok=True)
    for row in todo:
        if time.monotonic() > deadline:
            print("time is up for this pass; run `record` again to continue")
            return
        item, system = by_item[row["item"]], BY_ID[row["system"]]
        style = style_for(item, system, row["variant"])
        started = time.monotonic()
        try:
            spoken = say(providers, system.provider, system.model, system.voice, item["text"], item["language"], style)
        except Exception as error:  # noqa: BLE001 — the provider's sentence is written down, not raised
            failures += 1
            print(f"  {key_of(row)}: {failure(error)[:200]}")
            if failures >= 5:
                sys.exit("five failures in a row; stopping. Fix the cause and run `record` again.")
            time.sleep(5)
            continue
        failures = 0
        path = master_path(row)
        path.parent.mkdir(parents=True, exist_ok=True)
        if spoken.result.mime not in ("audio/wav", "audio/x-wav"):
            raw = path.with_suffix("." + speak.extension_for(spoken.result.mime))
            raw.write_bytes(spoken.result.data)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), str(path)], check=True)
            raw.unlink()
        else:
            path.write_bytes(spoken.result.data)
        sent = spoken.direction
        entry = {**row, "group": item["group"], "language": item["language"], "provider": system.provider,
                 "model": spoken.result.answer.model, "voice": spoken.result.voice,
                 "sent": str(sent) if sent else None,
                 "characters": billed(item, system, row["variant"]) if system.provider == "elevenlabs" else len(item["text"]),
                 "bytes": len(spoken.result.data), "seconds": seconds_of(path),
                 "wait": round(time.monotonic() - started, 2)}
        with TAKES.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  {key_of(row)}  {entry['seconds']}s  sent={(entry['sent'] or '')[:60]!r}")
    print("all planned takes recorded" if not todo or len(done()) >= len(planned()) else "pass finished")


# ── blind ───────────────────────────────────────────────────────────────────


LETTERS = "ABCDEF"


def blind(args: argparse.Namespace) -> None:
    """Take 1 of every rated source, loudness-matched, under a letter shuffled per item."""
    have = done()
    key: dict[str, dict[str, str]] = _read(OUT / "key.json", {})
    labels = _read(OUT / "labels.json", {})
    for item in items():
        found = [f"{system}{'-' + variant if variant else ''}" for system, variant in sources(item)
                   if f"{item['id']}/{system}{'-' + variant if variant else ''}/1" in have]
        if item["id"] in key and set(key[item["id"]].values()) == set(found):
            continue
        if item["id"] in labels and item["id"] in key:
            continue                                  # a label never comes to mean another take
        shuffled = found[:]
        random.Random(f"{SEED}:{item['id']}").shuffle(shuffled)
        key[item["id"]] = {LETTERS[n]: source for n, source in enumerate(shuffled)}
    folder = OUT / "blind"
    for item_id, letters in key.items():
        for letter, source in letters.items():
            target = folder / item_id / f"{letter}.wav"
            master = OUT / "masters" / f"{item_id}_{source}_1.wav"
            if target.exists() and target.stat().st_mtime >= master.stat().st_mtime:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Loudness-matched so no system is given away by being louder (round 0's take 5 was).
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-af",
                            "loudnorm=I=-20:TP=-1.5:LRA=11", "-ar", "24000", "-ac", "1", str(target)], check=True)
    _write(OUT / "key.json", key)
    print(f"{sum(len(v) for v in key.values())} takes under letters for {len(key)} items in {folder}")


# ── report ──────────────────────────────────────────────────────────────────


# The Argentine sound a listener hears: «ll» and «y» before a vowel (sheísmo). A text without one
# ("decepcionar") sounds the same in every variety, so its accent rating carries nothing.
SHEISMO = re.compile(r"ll|y[aeiouáéíóú]")

# The owner speaks Argentine Spanish and cannot rate Castilian on its own, so Spain's items are listed
# and left out of every summary; round 2 hears Spain only as the other half of a pair (`pairs.py`).
UNJUDGED = ("es-ES",)

SCALE_WORDS = {"right": ("wrong", "a slip", "right"), "feeling": ("flat", "some", "carries it"),
               "accent": ("not it", "partly", "clearly")}


def _mean(values: list[int]) -> str:
    return f"{sum(values) / len(values):.2f} ({len(values)})" if values else "–"


def _count(values: list[int], score: int) -> str:
    return f"{sum(1 for v in values if v == score)}/{len(values)}" if values else "–"


def _top(row: dict[str, Any]) -> bool:
    """Every scale the take was asked about at its best: what "good" means when Best picks only one."""
    return all(row.get(scale) == 3 for scale in row["scales"])


def report(args: argparse.Namespace) -> None:
    """Unblind the labels into `results/report.md`, written around ElevenLabs' settings.

    The question is which settings Acervo should use for ElevenLabs. Gemini's takes are the
    reference for what a text should sound like, not a contestant, so they appear as a last row.
    A Best pick is the better of several good takes, and no pick means none was good: Best is
    therefore reported but decides nothing, and "top marks" counts every good take."""
    key = _read(OUT / "key.json", {})
    labels = _read(OUT / "labels.json", {})
    transcripts = {}
    path = RESULTS / "transcripts.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            transcripts[row["key"]] = row
    sent = {key_of(row): row.get("sent") for row in done().values()}
    by_item = {item["id"]: item for item in items()}
    rows = []
    for item_id, letters in key.items():
        item = by_item[item_id]
        accented = "-" in item["language"]
        scales = ["right", *(["feeling"] if item["note"] else []), *(["accent"] if accented else [])]
        for letter, source in letters.items():
            label = (labels.get(item_id) or {}).get(letter) or {}
            heard = transcripts.get(f"{item_id}/{source}/1", {})
            rows.append({"item": item_id, "group": item["group"], "language": item["language"],
                         "words": item["words"], "text": item["text"], "source": source, "letter": letter,
                         "sent": sent.get(f"{item_id}/{source}/1"), "scales": scales,
                         "audible": bool(SHEISMO.search(item["text"].lower())), **label,
                         "best": (labels.get(item_id) or {}).get("_best") == letter,
                         "whisper": {k: heard.get(k) for k in ("wer", "twice", "instruction", "different", "text")}})
    judged = [row for row in rows if row["language"] not in UNJUDGED]
    flagged = lambda mine, name: f"{sum(1 for r in mine if name in (r.get('flags') or []))}/{len(mine)}"
    heard = lambda mine, name: f"{sum(1 for r in mine if r['whisper'].get(name))}/{len(mine)}"
    order = lambda sources: sorted(sources, key=lambda s: (s == "gemini", s))

    lines = ["# Expressive voice, round 1: which settings for ElevenLabs", "",
             "Unblinded from the owner's labels by `run.py report`. Gemini is the reference for what a text "
             "should sound like and is the last row of each table; it is not being compared. "
             f"{len([r for r in rows if r.get('right')])} of {len(rows)} takes rated, over {len(key)} items. "
             "Scores are 1–3 (wrong / a slip / right; flat / some / carries it; not it / partly / clearly), "
             "as mean (takes). Spain's items (`es-ES`) are listed at the end and left out of every summary: "
             "the owner cannot rate Castilian on its own.", ""]

    # 1. The model: everything that was sent the way Acervo sends it.
    shipped = [r for r in judged if r["group"] in ("feeling", "story", "words")]
    lines += ["## Which model: feeling, story and word takes", "",
              "| Take | Right | Wrong | Feeling | Flat | Accent | Top marks | Read aloud (ear) | Said twice (ear) "
              "| Whisper: tag read aloud | Whisper: other words |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for source in order({r["source"] for r in shipped}):
        mine = [r for r in shipped if r["source"] == source]
        right = [r["right"] for r in mine if r.get("right")]
        feeling = [r["feeling"] for r in mine if r.get("feeling")]
        lines.append(f"| {source} | {_mean(right)} | {_count(right, 1)} | {_mean(feeling)} | {_count(feeling, 1)} "
                     f"| {_mean([r['accent'] for r in mine if r.get('accent')])} "
                     f"| {sum(_top(r) for r in mine)}/{len(mine)} | {flagged(mine, 'read aloud')} "
                     f"| {flagged(mine, 'said twice')} | {heard(mine, 'instruction')} | {heard(mine, 'different')} |")
    lines.append("")

    # 2. By group and language: where a feeling or an accent holds and where it does not.
    lines += ["## By group and language", "", "| Group | Language | Take | Right | Feeling | Accent |", "|---|---|---|---|---|---|"]
    for group in ("feeling", "story", "words"):
        for language in sorted({r["language"] for r in shipped if r["group"] == group}):
            here = [r for r in shipped if r["group"] == group and r["language"] == language]
            for source in order({r["source"] for r in here}):
                mine = [r for r in here if r["source"] == source]
                lines.append(f"| {group} | {language} | {source} | {_mean([r['right'] for r in mine if r.get('right')])} "
                             f"| {_mean([r['feeling'] for r in mine if r.get('feeling')])} "
                             f"| {_mean([r['accent'] for r in mine if r.get('accent')])} |")
    lines.append("")

    # 3. The accent where it can be heard at all.
    argentine = [r for r in judged if r["language"] == "es-AR" and r.get("accent")]
    lines += ["## The Argentine accent, where it can be heard", "",
              "A text with «ll» or «y» before a vowel carries the sound that differs; one without "
              "(\"decepcionar\") sounds the same in every variety.", "",
              "| Take | Group | Sent | With ll/y: accent | Not it | Without: accent | Not it |", "|---|---|---|---|---|---|---|"]
    for group in ("feeling", "story", "words", "accent"):
        here = [r for r in argentine if r["group"] == group]
        for source in order({r["source"] for r in here}):
            mine = [r for r in here if r["source"] == source]
            tags = sorted({(r["sent"] if source.startswith("v") else "the sentence") or "nothing" for r in mine})
            what = tags[0] if len(tags) == 1 else ("a feeling; accent from Argentina" if group in ("feeling", "story")
                                                    else ", ".join(tags))
            yes = [r["accent"] for r in mine if r["audible"]]
            no = [r["accent"] for r in mine if not r["audible"]]
            lines.append(f"| {source} | {group} | {what} | {_mean(yes)} | {_count(yes, 1)} | {_mean(no)} | {_count(no, 1)} |")
    lines.append("")

    # 4. The accent alone on Eleven v4: four ways, by length.
    alone = [r for r in judged if r["group"] == "accent"]
    if alone:
        lines += ["## Accent alone (es-AR), by what Eleven v4 was sent", "",
                  "| Take | Sent | Right | Said twice (ear) | Whisper: twice | Accent, ll/y texts | Accent, others |",
                  "|---|---|---|---|---|---|---|"]
        for source in order({r["source"] for r in alone}):
            mine = [r for r in alone if r["source"] == source]
            tag = (mine[0]["sent"] or "nothing") if source.startswith("v") else "the sentence"
            lines.append(f"| {source} | {tag} | {_mean([r['right'] for r in mine if r.get('right')])} "
                         f"| {flagged(mine, 'said twice')} | {heard(mine, 'twice')} "
                         f"| {_mean([r['accent'] for r in mine if r['audible'] and r.get('accent')])} "
                         f"| {_mean([r['accent'] for r in mine if not r['audible'] and r.get('accent')])} |")
        lines += ["", "Said twice by the ear, by length in words:", "",
                  "| Take | " + " | ".join(str(n) for n in ACCENT_LENGTHS) + " |", "|---|" + "---|" * len(ACCENT_LENGTHS)]
        for source in order({r["source"] for r in alone}):
            cells = []
            for length in ACCENT_LENGTHS:
                mine = [r for r in alone if r["source"] == source and r["words"] == length]
                cells.append(f"{sum(1 for r in mine if 'said twice' in (r.get('flags') or []))}/{len(mine)}" if mine else "–")
            lines.append(f"| {source} | " + " | ".join(cells) + " |")
        lines.append("")

    # 5. Best picks: the better of several good takes, or none when nothing was good.
    lines += ["## Best picks", "",
              "The owner picked the better take where several were good and none where none was. It is "
              "reported for completeness and decides nothing here.", "",
              "| Group | Items | No take good enough | " + " | ".join(order({r["source"] for r in rows if r["source"] != "gemini"} | {"gemini"})) + " |",
              "|---|---|---|" + "---|" * len({r["source"] for r in rows})]
    every_source = order({r["source"] for r in rows})
    for group in ("feeling", "story", "words", "accent"):
        here = [r for r in judged if r["group"] == group]
        ids = {r["item"] for r in here}
        none = sum(1 for i in ids if not (labels.get(i) or {}).get("_best"))
        counts = [str(sum(1 for r in here if r["source"] == s and r["best"])) if any(r["source"] == s for r in here) else "–"
                  for s in every_source]
        lines.append(f"| {group} | {len(ids)} | {none} | " + " | ".join(counts) + " |")
    spain_ids = {r["item"] for r in rows if r["language"] in UNJUDGED}
    if spain_ids:
        lines += ["", f"Spain's {len(spain_ids)} accent items are left out: "
                  f"{sum(1 for i in spain_ids if not (labels.get(i) or {}).get('_best'))} have no pick."]
    lines.append("")

    # 6. Every note and flag, unblinded.
    noted = [r for r in rows if r.get("note") or r.get("flags")]
    lines += ["## Notes and flags", ""]
    for r in sorted(noted, key=lambda r: (r["item"], r["source"])):
        bits = [*(r.get("flags") or []), *([f"“{r['note'].strip()}”"] if r.get("note") else [])]
        lines.append(f"- `{r['item']}` {r['source']} ({r['language']}, “{r['text'][:60]}”): {'; '.join(bits)}")
    lines.append("")

    # 7. Spain's items, not judged by ear.
    spain = [r for r in rows if r["language"] in UNJUDGED]
    if spain:
        lines += ["## Spain (`es-ES`): rated, not judged", "",
                  "Listed for the record. The owner cannot rate Castilian on its own, so nothing above uses "
                  "these; round 2 plays Spain only against Argentina, as a pair.", "",
                  "| Take | Right | Accent | Said twice (ear) | Whisper: twice |", "|---|---|---|---|---|"]
        for source in order({r["source"] for r in spain}):
            mine = [r for r in spain if r["source"] == source]
            lines.append(f"| {source} | {_mean([r['right'] for r in mine if r.get('right')])} "
                         f"| {_mean([r['accent'] for r in mine if r.get('accent')])} "
                         f"| {flagged(mine, 'said twice')} | {heard(mine, 'twice')} |")
        lines.append("")

    # 8. Whisper over every take, Gemini's three included: what was said against what was given.
    every = list(transcripts.values())
    if every:
        lines += ["## Whisper, every take", "",
                  "| Take | Takes | Said twice | Tag read aloud | Other words (WER > 0.25) |", "|---|---|---|---|---|"]
        for source in order({row["key"].split("/")[1] for row in every}):
            mine = [row for row in every if row["key"].split("/")[1] == source]
            lines.append(f"| {source} | {len(mine)} | {sum(r['twice'] for r in mine)}/{len(mine)} "
                         f"| {sum(bool(r['instruction']) for r in mine)}/{len(mine)} "
                         f"| {sum(r['different'] for r in mine)}/{len(mine)} |")
        caught = [row for row in every if row["twice"] or row["instruction"] or row["different"]]
        lines += ["", *[f"- `{row['key']}`: “{row['text']}”" for row in caught], ""]

    if not labels:
        print("\n".join(lines))
        print("\nNo labels yet: nothing written. Listen on the page first.")
        return
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write(RESULTS / "summary.json", rows)
    shutil.copy(OUT / "labels.json", RESULTS / "labels.json")
    shutil.copy(OUT / "key.json", RESULTS / "key.json")
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("set").set_defaults(run=draw)
    found = commands.add_parser("probe")
    found.add_argument("--again", action="store_true", help="ask every route again")
    found.add_argument("--cap-calls", type=int, default=0, help="spend up to this many free calls to find the cap")
    found.set_defaults(run=probe)
    commands.add_parser("bill").set_defaults(run=bill)
    found = commands.add_parser("record")
    found.add_argument("--minutes", type=float, default=9.0, help="stop after this long; rerun to continue")
    found.add_argument("--only", help="comma-separated system ids")
    found.set_defaults(run=record)
    commands.add_parser("blind").set_defaults(run=blind)
    commands.add_parser("report").set_defaults(run=report)
    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
