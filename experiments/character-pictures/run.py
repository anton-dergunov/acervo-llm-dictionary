"""Draw a pictographic character's object so that its strokes are the character's strokes.

The question and the method are in the README. In short: every character gets a stroke script
(`scripts.yaml`) saying where each stroke lies and which part of the object it becomes; `prepare`
checks it against the pinned stroke data and the etymology source, renders the strokes, and writes
every prompt before anything is spent; `draw` asks each model two ways — by text alone, and by editing a picture of the
character's strokes, each in its own colour; `review.py` is where the owner judges them, blind;
`report` unblinds the labels.

    .venv/bin/python experiments/character-pictures/run.py fetch
    .venv/bin/python experiments/character-pictures/run.py prepare
    .venv/bin/python experiments/character-pictures/run.py draw [--models …] [--characters 人大山]
    .venv/bin/python experiments/character-pictures/run.py report

`draw` resumes: a picture already on disk is not drawn again, so after any stop the same command
carries on. Nothing here writes to the server.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "out"
RESULTS = HERE / "results"
PROMPTS = HERE / "prompts"
STROKES = REPO / "vendor" / "strokes"
DICTIONARY = OUT / "cache" / "dictionary.txt"

# The characters, in the order the page shows them. Each must be pictographic or a simple
# ideogram by Make Me a Hanzi's own etymology; `prepare` drops one the source disagrees with.
CHARACTERS = "人大从休山水木林森口日月明火雨田门竹井册羊凸"
KINDS = ("pictographic", "ideographic")
WAYS = ("text", "edit")


@dataclass(frozen=True)
class Model:
    id: str
    provider: str            # an id in providers.local.json
    model: str
    takes: int
    characters: str | None = None  # None: every character
    usd: float = 0.0         # per picture, for the running total


MODELS = (
    Model("nano-banana-2", "vertex", "gemini-3.1-flash-image", takes=2, usd=0.067),
    Model("nano-banana-pro", "vertex", "gemini-3-pro-image", takes=2, usd=0.134),
    # A sample only: Cloudflare's free allowance is about 95 pictures a day at 1024 px, and an
    # input picture costs more. The simplest characters, both ways, one take.
    Model("flux-2-klein", "cloudflare", "@cf/black-forest-labs/flux-2-klein-4b", takes=1,
          characters="人山木日月口田林"),
)

# Fixed and well apart, by stroke index. Named in the prompt, so each must have a plain name.
COLOURS = (
    ("red", "#e53935"), ("blue", "#1e6fd9"), ("green", "#2e9e44"), ("orange", "#f28c00"),
    ("purple", "#8e24aa"), ("cyan", "#00acc1"), ("magenta", "#e91e8c"), ("brown", "#7b4a2a"),
    ("yellow", "#f2c500"), ("lime", "#8bc34a"), ("navy", "#1a237e"), ("grey", "#8a8a8a"),
)

# The stroke data's frame: a 1024 box, y up, from −124 to 900 (`web/src/writing/strokeData.ts`).
BOX, TOP = 1024, 900
SIZE = 1024

FIRST_REST, LONGEST_REST = 30.0, 600.0
# A picture still unavailable after this many tries is left for the next run: about an hour of rests.
ATTEMPTS = 9
LOGIN_HINT = ("The Google login has expired. Run `gcp-personal` (or `gcloud auth "
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


def _etymologies() -> dict[str, dict[str, Any]]:
    if not DICTIONARY.exists():
        sys.exit("No dictionary.txt yet: run `run.py fetch` first.")
    found = {}
    with DICTIONARY.open(encoding="utf-8") as lines:
        for line in lines:
            entry = json.loads(line)
            if entry["character"] in CHARACTERS:
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
    import resvg_py  # the experiment's own requirement: requirements.txt here

    return bytes(resvg_py.svg_to_bytes(svg_string=svg(character), width=SIZE, height=SIZE))


# ── prepare ─────────────────────────────────────────────────────────────────


def _scripts() -> dict[str, dict[str, Any]]:
    return yaml.safe_load((HERE / "scripts.yaml").read_text(encoding="utf-8"))


def selected() -> list[dict[str, Any]]:
    """The characters as `prepare` left them; the one list every later step reads."""
    path = RESULTS / "characters.json"
    if not path.exists():
        sys.exit("No characters yet: run `run.py prepare` first.")
    return json.loads(path.read_text(encoding="utf-8"))["characters"]


def prepare(_: argparse.Namespace) -> None:
    etymologies = _etymologies()
    scripts = _scripts()
    kept, problems = [], []
    for character in CHARACTERS:
        entry = etymologies.get(character)
        etymology = (entry or {}).get("etymology") or {}
        if etymology.get("type") not in KINDS:
            problems.append(f"{character}: the source calls it {etymology.get('type') or 'nothing'}; dropped")
            continue
        script = scripts.get(character)
        strokes = _strokes(character)
        if not script:
            problems.append(f"{character}: no stroke script in scripts.yaml; dropped")
            continue
        if len(script["strokes"]) != len(strokes["strokes"]):
            problems.append(f"{character}: the script has {len(script['strokes'])} strokes, "
                            f"the character {len(strokes['strokes'])}; dropped")
            continue
        kept.append({
            "character": character,
            "type": etymology["type"],
            "hint": etymology.get("hint") or "",
            "definition": entry.get("definition") or "",
            "strokes": len(strokes["strokes"]),
            "object": script["object"].strip(),
            "lines": [{"colour": COLOURS[i % len(COLOURS)][0], "where": line["where"].strip(),
                       "part": line["part"].strip()}
                      for i, line in enumerate(script["strokes"])],
        })
    for problem in problems:
        print(f"  {problem}")
    pin = json.loads((HERE / "pin.json").read_text(encoding="utf-8"))
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "characters.json").write_text(json.dumps({
        "source": (f"Etymology type and hint from Make Me a Hanzi's dictionary.txt "
                   f"(commit {pin['commit']}), {pin['licence']}; https://github.com/skishore/makemeahanzi"),
        "characters": kept,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (OUT / "strokes").mkdir(parents=True, exist_ok=True)
    (OUT / "prompts").mkdir(parents=True, exist_ok=True)
    for item in kept:
        (OUT / "strokes" / f"{item['character']}.png").write_bytes(_render(item["character"]))
        for way in WAYS:
            (OUT / "prompts" / f"{item['character']}-{way}.md").write_text(
                prompt(item, scripts[item["character"]], way) + "\n", encoding="utf-8")
    print(f"{len(kept)} characters ready; strokes in out/strokes/, prompts in out/prompts/")
    total = sum(len(_wanted(model, kept)) for model in MODELS)
    usd = sum(len(_wanted(model, kept)) * model.usd for model in MODELS)
    print(f"a full draw is {total} pictures, about ${usd:.0f}")


def prompt(item: dict[str, Any], script: dict[str, Any], way: str) -> str:
    """The whole prompt for one character and one way of asking."""
    if way == "text":
        lines = "\n".join(f"- Stroke {i}, {line['where']}: {line['part']}"
                          for i, line in enumerate(item["lines"], 1))
    else:
        lines = "\n".join(f"- Stroke {i}, the {line['colour']} one, {line['where']}: {line['part']}"
                          for i, line in enumerate(item["lines"], 1))
    fields = {
        "character": item["character"],
        "count": str(item["strokes"]),
        "object": item["object"],
        "strokes": lines,
        "history": (script.get("history") or "").strip(),
        "layout": (script.get("layout") or "").strip(),
    }
    direction = Template(_template("direction")).substitute(fields)
    text = Template(_template(way)).substitute(fields, direction=direction)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _template(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


# ── draw ────────────────────────────────────────────────────────────────────


def picture_path(character: str, model: str, way: str, take: int) -> Path:
    return OUT / "pictures" / character / model / f"{way}-{take}.webp"


def _wanted(model: Model, items: list[dict[str, Any]]) -> list[tuple[str, str, int]]:
    """Every picture a model is to draw: character, way, take."""
    return [(item["character"], way, take)
            for item in items if model.characters is None or item["character"] in model.characters
            for way in WAYS for take in range(1, model.takes + 1)]


_log_lock = threading.Lock()
# Everything stops on an expired login or Ctrl-C; a model's own setup problem stops that model only.
_stop = threading.Event()
_stopped: list[str] = []


def _scrubbed(message: str) -> str:
    """A provider's error without the cloud project or links it names, so the log can be committed."""
    message = re.sub(r"projects/[^/\s`'\"]+", "projects/…", message)
    message = re.sub(r"https?://\S+", "<link>", message)
    return re.sub(r"\s+", " ", message)[:300]


def _log(entry: dict[str, Any]) -> None:
    if "message" in entry:
        entry = {**entry, "message": _scrubbed(entry["message"])}
    with _log_lock, (OUT / "draws.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _say(text: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    with _log_lock:
        print(f"{stamp} {text}", flush=True)


def _halt(reason: str, model: threading.Event | None = None) -> None:
    _stopped.append(reason)
    (model or _stop).set()


def _login_expired(error: Exception) -> bool:
    """LiteLLM reports an expired Google login as a connection error, which would otherwise rest."""
    return "Reauthentication is needed" in str(error) or "RefreshError" in str(error)


def _draw_one(row: Any, model: Model, text: str, references: list[bytes], seed: int,
              entry: dict[str, Any], halted: threading.Event) -> Any:
    """One picture, resting on a busy provider. None when the provider refused this picture."""
    from acervo.images.render import MASTER
    from acervo.models import call
    from acervo.models.errors import ProviderRefused, ProviderUnavailable

    rest = FIRST_REST
    for _attempt in range(ATTEMPTS):
        if _stop.is_set() or halted.is_set():
            return None
        try:
            return call.image(text, row=row, model=model.model, size=MASTER, seed=seed,
                              references=references)
        except ProviderUnavailable as waiting:
            if _login_expired(waiting):
                _halt(LOGIN_HINT)
                return None
            _log({**entry, "error": waiting.reason, "message": str(waiting)})
            _say(f"{model.id}: {waiting.reason}, resting {rest:.0f} s ({_scrubbed(str(waiting))[:100]})")
            _stop.wait(rest)
            rest = min(rest * 2, LONGEST_REST)
        except ProviderRefused as refused:
            _log({**entry, "error": refused.reason, "message": str(refused)})
            if refused.reason in ("authentication", "configuration", "unconfigured"):
                _halt(f"{model.id}: {_scrubbed(str(refused))} — a setup problem, not this picture. "
                      "Fix it and rerun.", halted)
                return None
            _say(f"{model.id}: refused {entry['character']} {entry['way']}-{entry['take']}: {refused}")
            return None
    _say(f"{model.id}: gave up on {entry['character']} {entry['way']}-{entry['take']} after "
         f"{ATTEMPTS} tries; a rerun tries it again")
    return None


def _run_model(model: Model, row: Any, jobs: list[tuple[str, str, int]],
               prompts: dict[tuple[str, str], str], spent: list[float]) -> None:
    from acervo.images.render import encode_master

    halted = threading.Event()
    for character, way, take in jobs:
        if _stop.is_set() or halted.is_set():
            return
        target = picture_path(character, model.id, way, take)
        if target.exists():
            continue
        references = [(OUT / "strokes" / f"{character}.png").read_bytes()] if way == "edit" else []
        entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model.id,
                 "wire": model.model, "character": character, "way": way, "take": take}
        started = time.monotonic()
        result = _draw_one(row, model, prompts[(character, way)], references, take, entry, halted)
        if result is None:
            continue
        dropped = [w for w in result.answer.warnings if "reference" in w]
        if way == "edit" and dropped:
            _log({**entry, "error": "references dropped", "message": dropped[0]})
            _halt(f"{model.id}: {dropped[0]} — the editing way would not be tested. Stopped.", halted)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encode_master(result.data))
        seconds = round(time.monotonic() - started, 1)
        spent.append(model.usd)
        _log({**entry, "seconds": seconds, "costUsd": model.usd,
              "warnings": list(result.answer.warnings)})
        _say(f"{model.id}: {character} {way}-{take} in {seconds:.0f} s")


def draw(args: argparse.Namespace) -> None:
    from acervo.models.local import load_local

    items = selected()
    if args.characters:
        items = [item for item in items if item["character"] in args.characters]
    chosen = [m for m in MODELS if not args.models or m.id in args.models.split(",")]
    scripts = _scripts()
    prompts = {(item["character"], way): prompt(item, scripts[item["character"]], way)
               for item in items for way in WAYS}
    catalogue = load_local()
    plans = []
    for model in chosen:
        row = catalogue.find(model.provider)
        problem = row.reason() if row else f"no provider {model.provider!r} in providers.local.json"
        if problem:
            sys.exit(f"{model.id} cannot be called from this machine: {problem}.")
        jobs = _wanted(model, items)
        if args.limit:
            jobs = [job for job in jobs if job[2] <= args.limit]
        left = [job for job in jobs if not picture_path(job[0], model.id, job[1], job[2]).exists()]
        _say(f"{model.id}: {len(left)} of {len(jobs)} pictures to draw ({model.model})")
        plans.append((model, row, jobs))
    OUT.mkdir(exist_ok=True)
    spent: list[float] = []
    threads = [threading.Thread(target=_run_model, args=(model, row, jobs, prompts, spent),
                                name=model.id, daemon=True) for model, row, jobs in plans]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            while thread.is_alive():
                thread.join(timeout=1.0)
    except KeyboardInterrupt:
        _halt("interrupted")
        _say("stopping after the calls in flight; rerun the same command to carry on")
        for thread in threads:
            thread.join(timeout=200)
    _say(f"done: {len(spent)} pictures drawn now, about ${sum(spent):.2f}")
    if _stopped:
        for reason in _stopped:
            print(f"STOPPED: {reason}", flush=True)
        sys.exit(1)


# ── report ──────────────────────────────────────────────────────────────────

QUESTIONS = ("strokes", "depicts", "remember")
ANSWERS = ("yes", "partly", "no")
# How much the owner likes the picture, 1 to 5, as a string; and one best picture per character.
SCORES = ("1", "2", "3", "4", "5")


def report(_: argparse.Namespace) -> None:
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    labels = json.loads((OUT / "labels.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    best_of: dict[str, str] = {}
    for character, letters in key.items():
        label = labels.get(character) or {}
        judged = label.get("pictures") or {}
        if label.get("best") in letters:
            best_of[character] = letters[label["best"]]
        for letter, name in letters.items():
            answers = judged.get(letter) or {}
            if not all(answers.get(q) in ANSWERS for q in QUESTIONS):
                continue
            model, way, take = name.split("/")
            rows.append({"character": character, "model": model, "way": way, "take": int(take),
                         "name": name, "score": int(answers["score"]) if answers.get("score") else None,
                         **{q: answers[q] for q in QUESTIONS}})
    if not rows:
        sys.exit("Nothing judged yet.")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["model"], row["way"])].append(row)
    starred = Counter("/".join(name.split("/")[:2]) for name in best_of.values())

    lines = ["# Character pictures — results", "",
             f"{len(rows)} pictures judged, of {sum(len(v) for v in key.values())} planned. "
             "Each answer is the share of that model's pictures, asked that way; the score is the "
             "owner's 1–5 liking, and ★ counts the characters where that model and way drew the "
             "picture starred best. Klein drew a sample of 8 characters, one take each, so its ★ "
             "count is out of fewer chances.", "",
             "| Model | Way | n | Strokes yes / partly | Depicts yes / partly | Remember yes / partly "
             "| All three yes | Mean score | ★ best |",
             "| --- | --- | --: | --: | --: | --: | --: | --: | --: |"]
    summary = {}
    for (model, way), group in sorted(groups.items()):
        n = len(group)
        counts = {q: Counter(row[q] for row in group) for q in QUESTIONS}
        all_yes = sum(all(row[q] == "yes" for q in QUESTIONS) for row in group)
        scores = [row["score"] for row in group if row["score"]]
        mean = sum(scores) / len(scores) if scores else None
        summary[f"{model}/{way}"] = {"n": n, "allYes": all_yes, "meanScore": mean,
                                     "scores": dict(Counter(scores)),
                                     "best": starred[f"{model}/{way}"],
                                     **{q: dict(counts[q]) for q in QUESTIONS}}
        cells = " | ".join(f"{counts[q]['yes'] / n:.0%} / {counts[q]['partly'] / n:.0%}"
                           for q in QUESTIONS)
        lines.append(f"| {model} | {way} | {n} | {cells} | {all_yes / n:.0%} | "
                     f"{f'{mean:.1f}' if mean else '—'} | {starred[f'{model}/{way}']} |")

    lines += ["", "## Per character", "",
              "The picture starred best, which model and way drew a picture judged yes on all three "
              "questions, and the highest score seen.", "",
              "| Character | ★ best | Yes on all three | Top score |", "| --- | --- | --- | --: |"]
    by_character: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_character[row["character"]].append(row)
    order = {item["character"]: i for i, item in enumerate(selected())}
    for character in sorted(by_character, key=lambda c: order.get(c, 99)):
        group = by_character[character]
        winners = sorted({f"{row['model']} {row['way']}" for row in group
                          if all(row[q] == "yes" for q in QUESTIONS)})
        best = best_of.get(character, "")
        top = max((row["score"] for row in group if row["score"]), default=None)
        lines.append(f"| {character} | {best.replace('/', ' ') or '—'} | {', '.join(winners) or '—'} "
                     f"| {top or '—'} |")
    notes = {c: (labels.get(c) or {}).get("note") for c in key if (labels.get(c) or {}).get("note")}
    if notes:
        lines += ["", "## Notes", ""] + [f"- **{c}**: {note}" for c, note in notes.items()]

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    shutil.copy(OUT / "labels.json", RESULTS / "labels.json")
    shutil.copy(OUT / "key.json", RESULTS / "key.json")
    _copy_draws()
    print((RESULTS / "report.md").read_text(encoding="utf-8"))


def _copy_draws() -> None:
    """The call log, kept: timing and cost per picture. It holds no paths, keys or hostnames."""
    source = OUT / "draws.jsonl"
    if not source.exists():
        return
    text = source.read_text(encoding="utf-8")
    if re.search(r"/Users/|/home/|[\w.+-]+@[\w-]+\.\w|https?://|projects/(?!…)", text):
        print("draws.jsonl names a path, an address or a URL; not copied — look at it first")
        return
    (RESULTS / "draws.jsonl").write_text(text, encoding="utf-8")


# ── main ────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="the pinned dictionary.txt, verified")
    commands.add_parser("prepare", help="select, render the strokes, write every prompt")
    drawing = commands.add_parser("draw", help="draw what is missing, every model at once")
    drawing.add_argument("--models", help="comma-separated model ids (default: all): "
                         + ", ".join(m.id for m in MODELS))
    drawing.add_argument("--characters", help="only these characters, e.g. 人大山")
    drawing.add_argument("--limit", type=int, help="at most this many takes per character and way")
    commands.add_parser("report", help="unblind the labels and write results/")
    args = parser.parse_args(argv)
    {"fetch": fetch, "prepare": prepare, "draw": draw, "report": report}[args.command](args)


if __name__ == "__main__":
    main()
