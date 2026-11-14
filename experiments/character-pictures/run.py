"""Draw a pictographic character's object so that its strokes are the character's strokes.

The question and the method are in the README. In short: every character gets a stroke script
(`scripts/*.yaml`) saying where each stroke lies and which part of the object it becomes; `prepare`
checks it against the pinned stroke data, renders the strokes, and writes every prompt before
anything is spent; `batch` (or `draw`, one call at a time) asks Nano Banana 2 to draw over a picture
of the character's strokes in black, with the script as its prompt; `review.py --choose` is where
the owner picks the best picture or asks for a redraw.

This is the full run: every character Make Me a Hanzi calls pictographic or ideographic, apart
from the 72 drawn in rounds 1–3, in four popularity groups. Rounds 1–3 were drawn and judged with
this script as it stood at the commits the README names.

    .venv/bin/python experiments/character-pictures/run.py fetch
    .venv/bin/python experiments/character-pictures/run.py select          # the characters, by group
    .venv/bin/python experiments/character-pictures/run.py facts --group g1 # sheets for script writers
    .venv/bin/python experiments/character-pictures/run.py check            # every script, validated
    .venv/bin/python experiments/character-pictures/run.py batch --set common
    .venv/bin/python experiments/character-pictures/run.py status
    .venv/bin/python experiments/character-pictures/run.py report

A picture already on disk is never drawn again, so after any stop the same command carries on.
Nothing here writes to the server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from string import Template
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STAGE = "full"
OUT = HERE / "out" / STAGE
RESULTS = HERE / "results" / STAGE
PROMPTS = HERE / "prompts"
SCRIPTS = HERE / "scripts"
STROKES = REPO / "vendor" / "strokes"
DICTIONARY = HERE / "out" / "cache" / "dictionary.txt"

KINDS = ("pictographic", "ideographic")
# The blind scoring page of rounds 1–3 (`review.py` without `--choose`): two questions, a 1–5 score.
QUESTIONS = ("strokes", "depicts")
ANSWERS = ("yes", "partly", "no")
SCORES = ("1", "2", "3", "4", "5")
# Round 2 also asked by text alone: it broke the strokes in 8 of 25 characters, editing in 2.
WAYS = ("edit",)

# Popularity groups, by a character's best rank in Simplified Chinese, Traditional Chinese or
# Japanese (character frequency summed over wordfreq's word lists). A coarse order on purpose: the
# most used are drawn and chosen first, and the rare ones are a set of their own.
GROUPS = (("g1", 1000), ("g2", 2000), ("g3", 3000), ("g4", None))
# g4, the rarer characters, is not drawn: a learner aiming at moderate Chinese meets them almost never.
SETS = {"common": ("g1", "g2", "g3")}


@dataclass(frozen=True)
class Model:
    id: str
    provider: str            # an id in providers.local.json
    model: str
    takes: int
    usd: float = 0.0         # per picture, called one at a time
    batch_usd: float = 0.0   # per picture, in a Vertex batch job (half)
    pace: float = 0.0        # seconds between the starts of two calls; 0 calls as fast as answered


MODELS = (
    # Vertex lets this model draw about one picture a minute one call at a time (1.07 a minute over
    # round 2, 1.29 in round 3), so `draw` starts one call every 50 s. A batch job has no such limit.
    # Four takes: in round 3, a character had a picture scored 5 within 4 of its 8 takes 67% of the
    # time, and one scored 4 or more 90% of the time. The ones marked to redraw get 4 more.
    Model("nano-banana-2", "vertex", "gemini-3.1-flash-image", takes=4, usd=0.067,
          batch_usd=0.0336, pace=50.0),
    # Nano Banana Pro was dropped after round 2 (3.28 against 3.71, at twice the price), FLUX.2
    # klein after round 1 (mean 2.0, 9 of 16 scored 1).
)
MODEL = MODELS[0]

# Fixed and well apart, by stroke index. Only the review page's overlay and the writers' sheets use
# them: the models get the strokes in black, because a coloured reference came back as coloured ink.
COLOURS = (
    ("red", "#e53935"), ("blue", "#1e6fd9"), ("green", "#2e9e44"), ("orange", "#f28c00"),
    ("purple", "#8e24aa"), ("cyan", "#00acc1"), ("magenta", "#e91e8c"), ("brown", "#7b4a2a"),
    ("yellow", "#f2c500"), ("lime", "#8bc34a"), ("navy", "#1a237e"), ("grey", "#8a8a8a"),
)

# The stroke data's frame: a 1024 box, y up, from −124 to 900 (`web/src/writing/strokeData.ts`).
BOX, TOP = 1024, 900
SIZE = 1024

# After a 429 the limit needs about a minute to let one more call through.
FIRST_REST, LONGEST_REST = 60.0, 600.0
ATTEMPTS = 9
LOGIN_HINT = ("The Google login has expired. Run `gcp-digest` (or `gcloud auth "
              "application-default login` with the account that should pay), then rerun.")


# ── fetch ───────────────────────────────────────────────────────────────────


def fetch(_: argparse.Namespace) -> None:
    pin = json.loads((HERE / "pin.json").read_text(encoding="utf-8"))
    if DICTIONARY.exists() and _digest(DICTIONARY.read_bytes()) == pin["sha256"]:
        print(f"dictionary.txt already here and verified ({pin['commit'][:10]})")
    else:
        print(f"fetching {pin['url']}")
        with urllib.request.urlopen(pin["url"], timeout=120) as response:
            data = response.read()
        if _digest(data) != pin["sha256"]:
            sys.exit(f"dictionary.txt does not match the pin: {_digest(data)} != {pin['sha256']}")
        DICTIONARY.parent.mkdir(parents=True, exist_ok=True)
        DICTIONARY.write_bytes(data)
        print(f"  verified, {len(data) // 1024} KB, {pin['licence']}")
    if not (STROKES / "dataset.json").exists():
        sys.exit("No stroke data in vendor/strokes: run `python3 deploy/acervo/strokes/fetch.py`.")
    print(f"stroke data: {json.loads((STROKES / 'dataset.json').read_text())['dataset']}")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── the characters and their strokes ────────────────────────────────────────


@cache
def _dictionary() -> dict[str, dict[str, Any]]:
    if not DICTIONARY.exists():
        sys.exit("No dictionary.txt yet: run `run.py fetch` first.")
    found = {}
    with DICTIONARY.open(encoding="utf-8") as lines:
        for line in lines:
            entry = json.loads(line)
            found[entry["character"]] = entry
    return found


def _strokes(character: str) -> dict[str, Any]:
    return json.loads((STROKES / f"{character}.json").read_text(encoding="utf-8"))


def svg(character: str, *, coloured: bool = True) -> str:
    """The character's strokes on white, in the square every picture is drawn in."""
    data = _strokes(character)
    paths = "".join(
        f'<path d="{outline}" fill="{COLOURS[i % len(COLOURS)][1] if coloured else "#111"}"/>'
        for i, outline in enumerate(data["strokes"]))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BOX} {BOX}" '
            f'width="{SIZE}" height="{SIZE}"><rect width="{BOX}" height="{BOX}" fill="#fff"/>'
            f'<g transform="translate(0 {TOP}) scale(1 -1)">{paths}</g></svg>')


def _render(character: str) -> bytes:
    """The reference picture the model draws over: solid black strokes on white, nothing else.

    Hard rule: no colour, no numbers, no labels, no grid. Round 1's coloured reference came back
    as coloured ink, and its numbered strokes as stroke-order numbers drawn into the picture. The
    coloured, numbered sheets a session draws to write a script are for that session's eyes only.
    """
    import resvg_py  # the experiment's own requirement: requirements.txt here

    drawing = svg(character, coloured=False)
    data = bytes(resvg_py.svg_to_bytes(svg_string=drawing, width=SIZE, height=SIZE))
    _check_reference(data, character)
    return data


def _check_reference(data: bytes, character: str) -> None:
    """Refuse a reference picture that is not pure black and white, before anything is spent."""
    import io

    from PIL import Image

    pixels = Image.open(io.BytesIO(data)).convert("RGB")
    if any(len(set(rgb)) > 1 for _count, rgb in pixels.getcolors(maxcolors=1 << 16) or [(0, (0, 1, 2))]):
        sys.exit(f"The reference for {character} has colour in it; references must be black on white.")


def reference(character: str) -> Path:
    """The character's reference picture, rendered once into the stage's `strokes/`."""
    path = OUT / "strokes" / f"{character}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_render(character))
    return path


# ── select: which characters, in which group ────────────────────────────────


def _han(char: str) -> bool:
    return "一" <= char <= "鿿" or "㐀" <= char <= "䶿" or "豈" <= char <= "﫿"


def _ranks() -> tuple[dict[str, int], dict[str, int], Any]:
    """Each character's rank by how often it is written, in Chinese and in Japanese.

    A character's frequency is the sum of the frequencies of the words it appears in, read from
    wordfreq's lists directly, so Japanese needs no tokenizer. wordfreq keeps Chinese in Simplified
    form, so a Traditional character is ranked by its Simplified form.
    """
    from wordfreq import get_frequency_dict
    from wordfreq.chinese import simplify_chinese

    def ranked(language: str) -> dict[str, int]:
        found: Counter[str] = Counter()
        for word, frequency in get_frequency_dict(language, wordlist="large").items():
            for char in set(word):
                if _han(char):
                    found[char] += frequency
        return {char: rank for rank, (char, _) in enumerate(found.most_common())}

    return ranked("zh"), ranked("ja"), simplify_chinese


def select(_: argparse.Namespace) -> None:
    from importlib.metadata import version

    dictionary = _dictionary()
    drawn = set(_scripts_from([SCRIPTS / "rounds.yaml"]))
    zh, ja, simplify = _ranks()
    chosen = []
    for character, entry in dictionary.items():
        etymology = entry.get("etymology") or {}
        if etymology.get("type") not in KINDS or character in drawn:
            continue
        if not (STROKES / f"{character}.json").exists():
            continue
        simplified = simplify(character)
        ranks = {"zh": zh.get(character), "zhHant": zh.get(simplified) if simplified != character else None,
                 "ja": ja.get(character)}
        known = [rank for rank in ranks.values() if rank is not None]
        best = min(known) if known else None
        group = next(name for name, limit in GROUPS if limit is None or (best is not None and best < limit))
        chosen.append({
            "character": character,
            "type": etymology["type"],
            "hint": (etymology.get("hint") or "").replace("\xa0", " "),
            "definition": entry.get("definition") or "",
            "decomposition": entry.get("decomposition") or "",
            "strokes": len(_strokes(character)["strokes"]),
            "simplified": simplified if simplified != character else None,
            "ranks": ranks,
            "rank": best,
            "group": group,
        })
    order = {name: i for i, (name, _) in enumerate(GROUPS)}
    chosen.sort(key=lambda item: (order[item["group"]], item["rank"] if item["rank"] is not None else 10**9))
    pin = json.loads((HERE / "pin.json").read_text(encoding="utf-8"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "characters.json").write_text(json.dumps({
        "source": (f"Etymology type and hint from Make Me a Hanzi's dictionary.txt "
                   f"(commit {pin['commit']}), {pin['licence']}; https://github.com/skishore/makemeahanzi"),
        "ranks": (f"Rank by character frequency in wordfreq {version('wordfreq')}'s large lists, "
                  "summed over the words containing it; zhHant is the rank of a Traditional "
                  "character's Simplified form; 0 is the most common"),
        "characters": chosen,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    counts = Counter(item["group"] for item in chosen)
    print(f"{len(chosen)} characters (rounds 1–3 drew {len(drawn)} more): "
          + ", ".join(f"{name} {counts[name]}" for name, _ in GROUPS))
    for name, groups in SETS.items():
        print(f"  set {name}: {sum(counts[g] for g in groups)}")


@cache
def catalogue() -> tuple[dict[str, Any], ...]:
    """Every character of the full run, most popular first, as `select` left them."""
    path = RESULTS / "characters.json"
    if not path.exists():
        sys.exit("No characters yet: run `run.py select` first.")
    return tuple(json.loads(path.read_text(encoding="utf-8"))["characters"])


def in_scope(*, set_name: str | None = None, group: str | None = None,
             characters: str | None = None) -> list[dict[str, Any]]:
    groups = SETS[set_name] if set_name else (group,) if group else tuple(name for name, _ in GROUPS)
    return [entry for entry in catalogue() if entry["group"] in groups
            and (not characters or entry["character"] in characters)]


# ── the stroke scripts ──────────────────────────────────────────────────────

REQUIRED = ("object", "strokes", "layout")


def _scripts_from(paths: list[Path]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    origin: dict[str, str] = {}
    for path in paths:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            sys.exit(f"{path.name} is not valid YAML: {error}")
        if not isinstance(document, dict):
            sys.exit(f"{path.name} must map each character to its script")
        for character, script in document.items():
            if character in merged:
                sys.exit(f"{character} has a script in both {origin[character]} and {path.name}")
            merged[str(character)] = script
            origin[str(character)] = path.name
    return merged


_loaded: dict[str, Any] = {}


def _scripts() -> dict[str, dict[str, Any]]:
    """Every script: rounds 1–3 in `scripts/rounds.yaml`, the full run one file per writing batch.

    Read again whenever a file is added or changed, so a review page left running sees new ones.
    """
    paths = sorted(SCRIPTS.glob("*.yaml"))
    signature = tuple((path.name, path.stat().st_mtime_ns) for path in paths)
    if _loaded.get("signature") != signature:
        _loaded["scripts"] = _scripts_from(paths)
        _loaded["signature"] = signature
    return _loaded["scripts"]


def problems(character: str, script: Any) -> list[str]:
    """What is wrong with one script, before anything is spent. Empty when it may be drawn."""
    found = []
    if not isinstance(script, dict):
        return [f"{character}: the script is not a mapping"]
    for field in REQUIRED:
        if not script.get(field):
            found.append(f"{character}: no `{field}`")
    lines = script.get("strokes") or []
    if not isinstance(lines, list) or not all(isinstance(line, dict) and line.get("where") and line.get("part")
                                              for line in lines):
        found.append(f"{character}: every stroke needs a `where` and a `part`")
        return found
    if not (STROKES / f"{character}.json").exists():
        return found + [f"{character}: not in the pinned stroke data"]
    count = len(_strokes(character)["strokes"])
    if len(lines) != count:
        found.append(f"{character}: the script has {len(lines)} strokes, the character {count}")
    exact = script.get("exact") or []
    if not isinstance(exact, list) or not all(isinstance(line, str) for line in exact):
        found.append(f"{character}: `exact` must be a list of sentences")
        exact = []
    texts = [str(script.get(field) or "") for field in ("object", "history", "layout")]
    texts += [str(line["where"]) + " " + str(line["part"]) for line in lines] + list(exact)
    # Numbered strokes came back as numbers drawn into the picture (round 1).
    if any(re.search(r"\d", text) for text in texts):
        found.append(f"{character}: a digit in the script; say lengths and places in words, never number a stroke")
    if any(re.search(r"\bS\d|\bstroke (one|two|three|four|five|six|seven|eight|nine|ten)\b", text, re.I)
           for text in texts):
        found.append(f"{character}: a numbered stroke; name a stroke by where it lies")
    return found


def item(character: str, script: dict[str, Any], entry: dict[str, Any] | None = None) -> dict[str, Any]:
    """One character as every later step reads it: the source's facts and its script's lines."""
    source = entry or {}
    etymology = (_dictionary().get(character) or {}).get("etymology") or {}
    return {
        "character": character,
        "type": source.get("type") or etymology.get("type") or "",
        "hint": source.get("hint") or (etymology.get("hint") or "").replace("\xa0", " "),
        "definition": source.get("definition") or (_dictionary().get(character) or {}).get("definition") or "",
        "group": source.get("group") or "",
        "strokes": len(_strokes(character)["strokes"]),
        "object": script["object"].strip(),
        "lines": [{"colour": COLOURS[i % len(COLOURS)][0], "where": line["where"].strip(),
                   "part": line["part"].strip()}
                  for i, line in enumerate(script["strokes"])],
    }


def items(*, set_name: str | None = None, group: str | None = None,
          characters: str | None = None, quiet: bool = True) -> list[dict[str, Any]]:
    """The characters in scope that have a valid script, most popular first."""
    scripts = _scripts()
    found, bad = [], []
    for entry in in_scope(set_name=set_name, group=group, characters=characters):
        script = scripts.get(entry["character"])
        if script is None:
            continue
        wrong = problems(entry["character"], script)
        if wrong:
            bad += wrong
            continue
        found.append(item(entry["character"], script, entry))
    if bad and not quiet:
        print(f"  {len(bad)} script problems; these characters are not drawn until fixed "
              "(`run.py check` lists them all):")
        for line in bad[:20]:
            print(f"    {line}")
    return found


def selected() -> list[dict[str, Any]]:
    """Every drawable character of the full run (the review page's list)."""
    return items()


def prompt(item: dict[str, Any], script: dict[str, Any], way: str) -> str:
    """The whole prompt for one character and one way of asking (`prompts/<way>.md`).

    The strokes are listed in stroke order but never numbered: in round 1, numbered strokes came
    back as stroke-order numbers drawn into the picture.
    """
    lines = "\n".join(f"- {line['where']}: {line['part']}" for line in item["lines"])
    exact = [line.strip() for line in script.get("exact") or []]
    fields = {
        "character": item["character"],
        "count": str(item["strokes"]),
        "object": item["object"],
        "strokes": lines,
        "history": (script.get("history") or "").strip(),
        "layout": (script.get("layout") or "").strip(),
        "exact": ("Keep these details of the character's shape exactly:\n"
                  + "\n".join(f"- {line}" for line in exact)) if exact else "",
    }
    direction = Template(_template("direction")).substitute(fields)
    text = Template(_template(way)).substitute(fields, direction=direction)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _template(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def prompts_for(chosen: list[dict[str, Any]]) -> dict[str, str]:
    scripts = _scripts()
    return {entry["character"]: prompt(entry, scripts[entry["character"]], "edit") for entry in chosen}


# ── facts and check: for the script writers ─────────────────────────────────


def facts_command(args: argparse.Namespace) -> None:
    import facts

    from wordfreq.chinese import simplify_chinese

    chosen = in_scope(set_name=args.set, group=args.group, characters=args.characters)
    if args.unscripted:
        chosen = [entry for entry in chosen if entry["character"] not in _scripts()]
    scripts = _scripts()
    variants: dict[str, list[str]] = defaultdict(list)
    for entry in catalogue():
        if entry.get("simplified"):
            variants[entry["simplified"]].append(entry["character"])
    sheets = Path(args.sheets) if args.sheets else None
    written = 0
    for entry in chosen:
        character = entry["character"]
        counterpart = None
        simplified = simplify_chinese(character)
        if simplified != character:
            counterpart = f"Traditional form of {simplified}"
            if simplified in scripts:
                counterpart += f" (already scripted: “{scripts[simplified]['object'].strip()}”)"
        elif variants.get(character):
            counterpart = f"Simplified form of {''.join(variants[character])}"
            done = [v for v in variants[character] if v in scripts]
            if done:
                counterpart += f" ({done[0]} already scripted: “{scripts[done[0]]['object'].strip()}”)"
        text = facts.sheet(character, _dictionary()[character], _strokes(character), entry,
                           {k: v for k, v in scripts.items() if k != character}, counterpart, _dictionary())
        target = OUT / "facts" / entry["group"] / f"{character}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if sheets:
            sheets.mkdir(parents=True, exist_ok=True)
            (sheets / f"{character}.png").write_bytes(facts.numbered_sheet(_strokes(character)))
        written += 1
    print(f"{written} fact sheets in {(OUT / 'facts').relative_to(HERE)}/"
          + (f"; numbered drawings in {sheets}" if sheets else ""))
    if args.list:
        Path(args.list).write_text("".join(entry["character"] for entry in chosen) + "\n", encoding="utf-8")


def check(args: argparse.Namespace) -> None:
    """Validate scripts: the files named, or every one. Exit 1 on any problem."""
    paths = [Path(p) for p in args.files] if args.files else sorted(SCRIPTS.glob("*.yaml"))
    scripts = _scripts_from(paths)
    _scripts_from(sorted(SCRIPTS.glob("*.yaml")))  # no duplicates across files either
    known = {entry["character"] for entry in catalogue()}
    found = []
    for character, script in scripts.items():
        found += problems(character, script)
        if character not in known and Path(SCRIPTS / "rounds.yaml") not in paths:
            found.append(f"{character}: not one of the full run's characters")
    for line in found:
        print(line)
    print(f"{len(scripts)} scripts checked, {len(found)} problems")
    if found:
        sys.exit(1)


# ── which pictures are wanted ───────────────────────────────────────────────


def picture_path(character: str, model: str, way: str, take: int) -> Path:
    return OUT / "pictures" / character / model / f"{way}-{take}.webp"


def drawn_takes(character: str) -> list[int]:
    folder = OUT / "pictures" / character / MODEL.id
    if not folder.exists():
        return []
    return sorted(int(path.stem.split("-")[1]) for path in folder.glob("edit-*.webp"))


def choices() -> dict[str, dict[str, Any]]:
    path = OUT / "choices.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def wanted_takes(character: str, *, redraw: bool, marked: dict[str, dict[str, Any]],
                 takes: int | None = None) -> list[int]:
    """The takes to draw for one character: the first four, or four more after a redraw mark.

    A redraw mark records how many takes the owner had seen (`redrawFrom`); the next four follow
    them. Marking it again after those are chosen from asks for four more after that.
    """
    count = takes or MODEL.takes
    if not redraw:
        return list(range(1, count + 1))
    label = marked.get(character) or {}
    if not label.get("redraw"):
        return []
    start = int(label.get("redrawFrom") or MODEL.takes)
    return list(range(start + 1, start + count + 1))


def _wanted(model: Model, chosen: list[dict[str, Any]], *, redraw: bool = False,
            takes: int | None = None) -> list[tuple[str, str, int]]:
    """Every picture a model is to draw: character, way, take."""
    marked = choices() if redraw else {}
    return [(entry["character"], way, take) for entry in chosen for way in WAYS
            for take in wanted_takes(entry["character"], redraw=redraw, marked=marked, takes=takes)]


# ── prepare ─────────────────────────────────────────────────────────────────


def prepare(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Render the references and write the prompts of every scripted character in scope."""
    scope = in_scope(set_name=getattr(args, "set", None), characters=getattr(args, "characters", None))
    chosen = items(set_name=getattr(args, "set", None), characters=getattr(args, "characters", None), quiet=False)
    scripts = _scripts()
    (OUT / "prompts").mkdir(parents=True, exist_ok=True)
    for entry in chosen:
        reference(entry["character"])
        target = OUT / "prompts" / f"{entry['character']}-edit.md"
        text = prompt(entry, scripts[entry["character"]], "edit") + "\n"
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
    by_group = Counter(entry["group"] for entry in chosen)
    in_group = Counter(entry["group"] for entry in scope)
    print("scripted and ready: " + ", ".join(f"{g} {by_group[g]} of {in_group[g]}"
                                             for g, _ in GROUPS if in_group[g]))
    return chosen


# ── draw: one call at a time ────────────────────────────────────────────────

_log_lock = threading.Lock()
_stop = threading.Event()
_stopped: list[str] = []


def _scrubbed(message: str) -> str:
    """A provider's error without the cloud project or links it names, so the log can be committed."""
    message = re.sub(r"projects/[^/\s`'\"]+", "projects/…", message)
    message = re.sub(r"https?://\S+", "<link>", message)
    message = re.sub(r"gs://\S+", "gs://…", message)
    return re.sub(r"\s+", " ", message)[:300]


def log(entry: dict[str, Any]) -> None:
    if "message" in entry:
        entry = {**entry, "message": _scrubbed(entry["message"])}
    OUT.mkdir(parents=True, exist_ok=True)
    with _log_lock, (OUT / "draws.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def say(text: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    with _log_lock:
        print(f"{stamp} {text}", flush=True)


def _halt(reason: str, model: threading.Event | None = None) -> None:
    _stopped.append(reason)
    (model or _stop).set()


def _login_expired(error: Exception) -> bool:
    """LiteLLM reports an expired Google login as a connection error, which would otherwise rest."""
    return "Reauthentication is needed" in str(error) or "RefreshError" in str(error)


_next_call: dict[str, float] = {}


def _wait_turn(model: Model) -> None:
    if model.pace <= 0:
        return
    delay = _next_call.get(model.id, 0.0) - time.monotonic()
    if delay > 0:
        _stop.wait(delay)
    _next_call[model.id] = time.monotonic() + model.pace


def _draw_one(row: Any, model: Model, text: str, references: list[bytes],
              entry: dict[str, Any], halted: threading.Event) -> Any:
    """One picture, resting on a busy provider. None when the provider refused this picture."""
    from acervo.images.render import MASTER
    from acervo.models import call
    from acervo.models.errors import ProviderRefused, ProviderUnavailable

    rest = FIRST_REST
    for _attempt in range(ATTEMPTS):
        _wait_turn(model)
        if _stop.is_set() or halted.is_set():
            return None
        try:
            # No seed: the route that sends a reference picture never sends one, so takes are
            # independent samples.
            return call.image(text, row=row, model=model.model, size=MASTER, references=references)
        except ProviderUnavailable as waiting:
            if _login_expired(waiting):
                _halt(LOGIN_HINT)
                return None
            log({**entry, "error": waiting.reason, "message": str(waiting)})
            say(f"{model.id}: {waiting.reason}, resting {rest:.0f} s ({_scrubbed(str(waiting))[:100]})")
            _stop.wait(rest)
            rest = min(rest * 2, LONGEST_REST)
        except ProviderRefused as refused:
            log({**entry, "error": refused.reason, "message": str(refused)})
            if refused.reason in ("authentication", "configuration", "unconfigured"):
                _halt(f"{model.id}: {_scrubbed(str(refused))} — a setup problem, not this picture. "
                      "Fix it and rerun.", halted)
                return None
            if "billing" in str(refused).lower():
                _halt(f"{model.id}: {_scrubbed(str(refused))} — this account cannot pay. Switch to "
                      "another with `--provider`.", halted)
                return None
            say(f"{model.id}: refused {entry['character']} {entry['way']}-{entry['take']}: {refused}")
            return None
    say(f"{model.id}: gave up on {entry['character']} {entry['way']}-{entry['take']} after "
        f"{ATTEMPTS} tries; a rerun tries it again")
    return None


def _run_model(model: Model, row: Any, jobs: list[tuple[str, str, int]],
               prompts: dict[str, str], spent: list[float]) -> None:
    from acervo.images.render import encode_master

    halted = threading.Event()
    for character, way, take in jobs:
        if _stop.is_set() or halted.is_set():
            return
        target = picture_path(character, model.id, way, take)
        if target.exists():
            continue
        references = [reference(character).read_bytes()]
        entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model.id,
                 "wire": model.model, "route": "online", "provider": row.id,
                 "character": character, "way": way, "take": take}
        started = time.monotonic()
        result = _draw_one(row, model, prompts[character], references, entry, halted)
        if result is None:
            continue
        dropped = [w for w in result.answer.warnings if "reference" in w]
        if dropped:
            log({**entry, "error": "references dropped", "message": dropped[0]})
            _halt(f"{model.id}: {dropped[0]} — the reference would not be sent. Stopped.", halted)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encode_master(result.data))
        seconds = round(time.monotonic() - started, 1)
        spent.append(model.usd)
        log({**entry, "seconds": seconds, "costUsd": model.usd, "warnings": list(result.answer.warnings)})
        say(f"{model.id}: {character} {way}-{take} in {seconds:.0f} s")


def provider_row(provider: str) -> Any:
    from acervo.models.local import load_local

    catalogue_ = load_local()
    try:
        row = catalogue_.find(provider)
    except KeyError:
        sys.exit(f"No provider {provider!r} in providers.local.json; its ids are: "
                 + ", ".join(r.id for r in catalogue_.rows))
    problem = row.reason()
    if problem:
        sys.exit(f"{provider} cannot be called from this machine: {problem}.")
    return row


def draw(args: argparse.Namespace) -> None:
    """Draw what is missing, one call at a time (the fallback to `batch`)."""
    chosen = prepare(args)
    model = replace(MODEL, pace=args.pace) if args.pace is not None else MODEL
    row = provider_row(args.provider or model.provider)
    import batch

    try:
        batch.guard(row)
    except batch.Stop as stop:
        sys.exit(f"STOPPED: {stop}")
    prompts = prompts_for(chosen)
    jobs = _wanted(model, chosen, redraw=args.redraw)
    if args.limit:
        jobs = [job for job in jobs if job[2] <= args.limit]
    left = [job for job in jobs if not picture_path(job[0], model.id, job[1], job[2]).exists()]
    paced = f", one call every {model.pace:.0f} s: at least {len(left) * model.pace / 3600:.1f} h" if model.pace and left else ""
    say(f"{model.id}: {len(left)} of {len(jobs)} pictures to draw ({model.model}, provider {row.id}){paced}")
    spent: list[float] = []
    thread = threading.Thread(target=_run_model, args=(model, row, jobs, prompts, spent), daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            thread.join(timeout=1.0)
    except KeyboardInterrupt:
        _halt("interrupted")
        say("stopping after the call in flight; rerun the same command to carry on")
        thread.join(timeout=200)
    say(f"done: {len(spent)} pictures drawn now, about ${sum(spent):.2f}")
    missing = sum(not picture_path(c, model.id, w, t).exists() for c, w, t in jobs)
    if missing and not _stopped:
        say(f"{missing} pictures still missing (a refusal, or a provider that stayed busy); "
            "run the same command again to try them")
    if _stopped:
        for reason in _stopped:
            print(f"STOPPED: {reason}", flush=True)
        sys.exit(1)


def batch_command(args: argparse.Namespace) -> None:
    import batch

    batch.main(args)


# ── status and report ───────────────────────────────────────────────────────


def _group_table() -> list[str]:
    scripts = _scripts()
    marked = choices()
    in_flight: set[str] = set()
    state = OUT / "batches.json"
    if state.exists():
        for job in json.loads(state.read_text(encoding="utf-8")).get("jobs", []):
            if not job.get("harvested"):
                in_flight.update(key.split("/")[0] for key in job.get("requests", []))
    lines = ["| Group | Characters | Scripted | Drawn | Pictures | In flight | Chosen | Redraw |",
             "| --- | --: | --: | --: | --: | --: | --: | --: |"]
    for name, limit in GROUPS:
        members = [entry["character"] for entry in catalogue() if entry["group"] == name]
        drawn = [c for c in members if drawn_takes(c)]
        pictures = sum(len(drawn_takes(c)) for c in members)
        chosen = sum(1 for c in members if (marked.get(c) or {}).get("best"))
        redraw = sum(1 for c in members if (marked.get(c) or {}).get("redraw"))
        label = f"{name} (top {limit:,})" if limit else f"{name} (rarer, not drawn)"
        lines.append(f"| {label} | {len(members)} | {sum(c in scripts for c in members)} | {len(drawn)} | "
                     f"{pictures} | {sum(c in in_flight for c in members)} | {chosen} | {redraw} |")
    return lines


def _spent() -> list[str]:
    path = OUT / "draws.jsonl"
    if not path.exists():
        return ["Nothing drawn yet."]
    spent: dict[str, float] = defaultdict(float)
    count: Counter[str] = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("costUsd"):
            key = f"{entry.get('provider', '?')} ({entry.get('route', 'online')})"
            spent[key] += entry["costUsd"]
            count[key] += 1
    return [f"- {key}: {count[key]} pictures, ${usd:.2f}" for key, usd in spent.items()] or ["Nothing paid yet."]


def status(_: argparse.Namespace) -> None:
    print("\n".join(_group_table()))
    print("\nSpent, by provider:")
    print("\n".join(_spent()))


def report(_: argparse.Namespace) -> None:
    """The full run's state, and the owner's choices, copied into `results/full/`."""
    marked = choices()
    lines = ["# Character pictures — the full run", "",
             "Per popularity group: characters, how many have a script, how many are drawn, how many "
             "the owner has chosen a picture for, and how many are marked to redraw.", ""]
    lines += _group_table()
    redraw = [c for c, label in marked.items() if label.get("redraw")]
    if redraw:
        lines += ["", f"Marked to redraw: {' '.join(redraw)}."]
    notes = {c: label["note"] for c, label in marked.items() if label.get("note")}
    if notes:
        lines += ["", "## Notes", ""] + [f"- **{c}**: {note}" for c, note in notes.items()]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if marked:
        shutil.copy(OUT / "choices.json", RESULTS / "choices.json")
    _copy_draws()
    print((RESULTS / "report.md").read_text(encoding="utf-8"))


def _copy_draws() -> None:
    """The call log, kept: timing and cost per picture. It holds no paths, keys or hostnames."""
    source = OUT / "draws.jsonl"
    if not source.exists():
        return
    text = source.read_text(encoding="utf-8")
    if re.search(r"/Users/|/home/|[\w.+-]+@[\w-]+\.\w|https?://|gs://(?!…)|projects/(?!…)", text):
        print("draws.jsonl names a path, an address or a URL; not copied — look at it first")
        return
    (RESULTS / "draws.jsonl").write_text(text, encoding="utf-8")


# ── main ────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="the pinned dictionary.txt, verified")
    commands.add_parser("select", help="every remaining character, by popularity group")

    sheets = commands.add_parser("facts", help="fact sheets for the script writers")
    sheets.add_argument("--set", choices=sorted(SETS))
    sheets.add_argument("--group", choices=[name for name, _ in GROUPS])
    sheets.add_argument("--characters", help="only these characters, e.g. 人大山")
    sheets.add_argument("--unscripted", action="store_true", help="only characters with no script yet")
    sheets.add_argument("--sheets", help="also write numbered drawings here (a scratch directory, never sent)")
    sheets.add_argument("--list", help="write the characters, in order, to this file")

    checking = commands.add_parser("check", help="validate scripts (default: every file in scripts/)")
    checking.add_argument("files", nargs="*")

    preparing = commands.add_parser("prepare", help="render the strokes and write every prompt")
    preparing.add_argument("--set", choices=sorted(SETS))
    preparing.add_argument("--characters")

    drawing = commands.add_parser("draw", help="draw what is missing, one call at a time")
    drawing.add_argument("--set", choices=sorted(SETS), default="common")
    drawing.add_argument("--characters", help="only these characters, e.g. 人大山")
    drawing.add_argument("--provider", help=f"a providers.local.json id (default {MODEL.provider})")
    drawing.add_argument("--redraw", action="store_true", help="four more takes for characters marked to redraw")
    drawing.add_argument("--limit", type=int, help="at most this take number")
    drawing.add_argument("--pace", type=float, help="seconds between the starts of two calls")

    batching = commands.add_parser("batch", help="draw what is missing in Vertex batch jobs, then collect them")
    batching.add_argument("--set", choices=sorted(SETS), default="common")
    batching.add_argument("--characters", help="only these characters, e.g. 人大山")
    batching.add_argument("--provider", help=f"a providers.local.json id (default {MODEL.provider}), or "
                          "`current`: the shell's current Google Cloud account (after `gcp-<profile>`)")
    batching.add_argument("--project", help="a Google Cloud project to use with your current Google sign-in")
    batching.add_argument("--credentials", help="a Google credentials file to use (with --project, or alone)")
    batching.add_argument("--cap", type=float, help="spend at most this many dollars in all on this account, "
                          "counting what it has already spent and what is in flight")
    batching.add_argument("--budget", type=float, help="submit at most this many dollars' worth in this run")
    batching.add_argument("--job-size", type=int, default=500, help="requests per batch job (default 500)")
    batching.add_argument("--redraw", action="store_true", help="four more takes for characters marked to redraw")
    batching.add_argument("--takes", type=int, help=f"takes per character (default {MODEL.takes}); "
                          "with --redraw, how many more")
    batching.add_argument("--dry-run", action="store_true", help="say what would be submitted, and stop")
    batching.add_argument("--no-wait", action="store_true", help="submit and collect what is done, then stop")
    batching.add_argument("--poll", type=float, default=300.0, help="seconds between checks (default 300)")

    commands.add_parser("status", help="per group: scripted, drawn, in flight, chosen; money spent")
    commands.add_parser("report", help="the full run's state and the owner's choices into results/full/")
    args = parser.parse_args(argv)
    {"fetch": fetch, "select": select, "facts": facts_command, "check": check, "prepare": prepare,
     "draw": draw, "batch": batch_command, "status": status, "report": report}[args.command](args)


if __name__ == "__main__":
    main()
