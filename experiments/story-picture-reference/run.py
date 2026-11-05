"""Redraw a story's pictures with the earlier pictures of the same people and places as references.

The question is in the README. Since run 2 this is **the application's own code**, not a copy: the
labels come from `acervo.stories.continuity` and `prompts/acervo_story_continuity.md`, the references
are chosen and worded by the same functions, the picture prompt is `prompts/acervo_story_reference.md`,
and the call is `call.image(references=…)`. So a run here measures what ships.

- `fetch` copies the owner's stories and their stored pictures down;
- `prepare` labels who and where each brief shows, prints which earlier pictures every part would be
  given, and writes every prompt it would send to `<out>/prompts/` — before anything is spent;
- `draw` makes the `continuity` set;
- `report` unblinds the labels `review.py` collected.

    .venv/bin/python experiments/story-picture-reference/run.py --out …/out-2 fetch --newest 12 …
    .venv/bin/python experiments/story-picture-reference/run.py --out …/out-2 prepare
    .venv/bin/python experiments/story-picture-reference/run.py --out …/out-2 draw
    .venv/bin/python experiments/story-picture-reference/run.py --out …/out-2 report

Every style is drawn with references here, photographic ones included, whatever the owner's setting
says: the point of the run is to measure the setting's default, not to obey it. Nothing here writes
to the server.
"""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from PIL import Image

from acervo.client import AcervoClient, AcervoError
from acervo.images.render import MASTER, encode_master
from acervo.images.styles import load_styles
from acervo.models.local import load_local
from acervo.models import call, chain
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable
from acervo.stories import continuity, illustrate
from acervo.stories.write import Part

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROMPTS = REPO / "prompts"
OUT = Path(os.environ.get("STORY_PICTURES_OUT") or HERE / "out")

IMAGE_PROVIDER = "vertex"
IMAGE_MODEL = "gemini-3.1-flash-lite-image"
PICTURE_USD = 0.0342  # $0.0336 a picture and about two references at $0.00028
TEXT_CHAIN = ["gemini-api"]  # the labels; GEMINI_API_KEY from `providers.local.json`
RECENT = 5
# The sets a run draws, and which picture a returning character is drawn from in each. Run 2 drew
# `continuity` with the latest; run 3 compares that with the first, which the application now uses.
# Order matters: a part the two would draw from the same plan and the same pictures is drawn once,
# for the first set, and copied to the second, so they differ only where the anchor does.
SETS = {"continuity": "last", "continuity-first": "first"}
# The rests `src/acervo/work/` uses for the same three conditions: 30 s, doubling, ten minutes.
FIRST_REST, LONGEST_REST = 30.0, 600.0

load_dotenv(REPO / ".env", override=False)


def _template(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def _login_expired(error: Exception) -> bool:
    """LiteLLM reports an expired Google login as a connection error, which would otherwise rest."""
    return "Reauthentication is needed" in str(error) or "RefreshError" in str(error)


LOGIN_HINT = ("The Google login has expired. Run `gcloud auth application-default login` with the "
              "account that should pay, then rerun.")


# ── fetch ───────────────────────────────────────────────────────────────────


def fetch(args: argparse.Namespace) -> None:
    password = getpass.getpass(f"Password for {args.email}: ")
    with AcervoClient(args.server_url) as client:
        try:
            client.sign_in(args.email, password)
            changes = client.pull_graph(0)["changes"]
        except AcervoError as error:
            sys.exit(str(error))

        parts_of: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for part in changes.get("storyParts", []):
            if not part.get("deleted"):
                parts_of[part["storyId"]].append(part)

        live = sorted((story for story in changes.get("stories", []) if not story.get("deleted")),
                      key=lambda story: story.get("createdAt") or "")
        if args.newest:
            live = live[-args.newest:]
        kept, skipped = [], []
        for story in live:
            parts = sorted(parts_of.get(story["id"], []), key=lambda part: part.get("position", 0))
            label = f"{story.get('createdAt', '')[:10]} {story.get('title') or story['id']}"
            undrawn = [index + 1 for index, part in enumerate(parts) if not part.get("imageRef")]
            unbriefed = [index + 1 for index, part in enumerate(parts)
                         if not (part.get("imagePrompt") or "").strip()]
            if len(parts) < 2 or undrawn or unbriefed:
                why = (f"{len(parts)} part(s)" if len(parts) < 2 else
                       f"part(s) {undrawn} have no picture yet" if undrawn else
                       f"part(s) {unbriefed} have no brief")
                skipped.append((label, why))
                continue
            folder = OUT / story["id"] / "original"
            folder.mkdir(parents=True, exist_ok=True)
            for index, part in enumerate(parts):
                target = folder / f"part-{index + 1}.webp"
                if target.exists():
                    continue
                response = client.fetch("GET", f"/api/acervo/media/{part['imageRef']}")
                if response.status_code != 200:
                    sys.exit(f"{label}: picture {index + 1} answered {response.status_code}")
                target.write_bytes(response.content)
            kept.append({
                "id": story["id"], "title": story.get("title") or "",
                "titleTranslation": story.get("titleTranslation") or "",
                "emoji": story.get("emoji") or "", "language": story.get("language") or "",
                "createdAt": story.get("createdAt") or "", "styleId": story.get("styleId") or "",
                "parts": [{
                    "heading": part.get("heading") or "", "text": part.get("text") or "",
                    "translation": part.get("translation") or "",
                    "imagePrompt": part.get("imagePrompt") or "",
                    "imageModelId": part.get("imageModelId") or "",
                } for part in parts],
            })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stories.json").write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    for story in kept:
        print(f"  {story['id']}  {story['createdAt'][:16]}  {_look(story):<12} "
              f"{story['styleId']:<22} {story['title']}")
    for label, why in skipped:
        print(f"  skipped: {label} — {why}")
    print(f"{len(kept)} stories kept in {OUT}. Next: `prepare`, which spends nothing on pictures.")


# ── prepare ─────────────────────────────────────────────────────────────────


def _stories() -> list[dict[str, Any]]:
    path = OUT / "stories.json"
    if not path.exists():
        sys.exit(f"No stories in {OUT}: run `fetch` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _look(story: dict[str, Any]) -> str:
    styles = load_styles()
    photographic = story["styleId"] in styles and styles[story["styleId"]].photographic
    return "photographic" if photographic else "artwork"


def _labels_path(story_id: str) -> Path:
    return OUT / "labels" / f"{story_id}.json"


def _load_labels(story: dict[str, Any]) -> continuity.Continuity | None:
    path = _labels_path(story["id"])
    if not path.exists():
        return None
    return continuity.parse_reply(json.loads(path.read_text(encoding="utf-8")), len(story["parts"]))


def _picture(story_id: str, set_name: str, index: int) -> Path:
    return OUT / story_id / set_name / f"part-{index + 1}.webp"


def _prompt_for(story: dict[str, Any], labels: continuity.Continuity, index: int, style: Any,
                drawn: Callable[[int], bool], anchor: str = "first",
                ) -> tuple[str, tuple[continuity.Reference, ...]] | None:
    """What part `index` would be drawn from, or None when nothing recurs and it keeps its picture."""
    chosen = continuity.references(labels, index, drawn, characters=anchor)
    if not chosen:
        return None
    picture = illustrate.compose(story["parts"][index]["imagePrompt"], style)
    return continuity.compose(_template("acervo_story_reference"), labels, index, chosen,
                              picture), chosen


def prepare(args: argparse.Namespace) -> None:
    stories = _stories()
    styles = load_styles()
    catalogue = load_local()
    candidates = chain.resolve("text", TEXT_CHAIN, catalogue)
    if not candidates:
        sys.exit("No text model: GEMINI_API_KEY is not set (it is read from .env).")
    labeller = continuity.Labeller(catalogue, candidates, _template("acervo_story_continuity"))
    to_draw = 0
    for story in stories:
        count = len(story["parts"])
        folder = OUT / "prompts" / story["id"]
        folder.mkdir(parents=True, exist_ok=True)
        print(f"\n{story['createdAt'][:10]}  {story['title']}  ({story['id']}, {_look(story)})")
        parts = [Part(part["heading"], part["text"]) for part in story["parts"]]
        request = continuity.build_request(
            title=story["title"], parts=parts, briefs=[part["imagePrompt"] for part in story["parts"]])
        (folder / "labels-request.md").write_text(
            f"{labeller.template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8")
        path = _labels_path(story["id"])
        if args.force or not path.exists():
            labels = None
            # The free tier answers 503 "high demand" in bursts; a short wait usually clears it,
            # and a story whose labels still fail is simply retried by the next `prepare`.
            for attempt in range(3):
                try:
                    labels, usage = labeller.label(request, count)
                    break
                except ChainExhausted as exhausted:
                    print(f"  labels failed ({exhausted.last.reason}); "
                          f"{'waiting 30 s' if attempt < 2 else 'giving up — rerun prepare later'}")
                    if attempt < 2:
                        time.sleep(30)
            if labels is None:
                continue
            # Stored in the reply's own shape, so `parse_reply` reads it back the way it read it.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "characters": [{"id": key, "description": value}
                               for key, value in labels.characters.items()],
                "scenes": [{"id": key, "description": value} for key, value in labels.scenes.items()],
                "parts": [{"characters": list(shown.characters), "scene": shown.scene,
                           "change": shown.change} for shown in labels.parts],
                "model": usage["model"],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        labels = _load_labels(story)
        if story["styleId"] not in styles:
            print(f"  style {story['styleId']!r} is not in this checkout, so `draw` will skip it")
            continue
        for set_name, anchor in SETS.items():
            print(f"  [{set_name}: characters from their {anchor} picture]")
            for index in range(count):
                shown = labels.parts[index]
                head = f"part {index + 1} [{', '.join(shown.characters) or 'nobody'} @ {shown.scene}]"
                drawn = _prompt_for(story, labels, index, styles[story["styleId"]],
                                    lambda _part: True, anchor)
                if drawn is None:
                    print(f"    {head}: no references → keeps the original picture")
                    continue
                prompt, chosen = drawn
                (folder / f"{set_name}-part-{index + 1}.md").write_text(prompt + "\n", encoding="utf-8")
                served = "; ".join(
                    f"part {one.part + 1} ({', '.join(key.removeprefix('scene:') for key in one.keeps)})"
                    for one in chosen)
                change = f"  — change: {shown.change}" if shown.change else ""
                print(f"    {head} ← {served}{change}")
                to_draw += not _picture(story["id"], set_name, index).exists()
    print(f"\nEvery prompt is in {OUT / 'prompts'}/<story id>/.")
    print(f"`draw` will make at most {to_draw} pictures, about ${to_draw * PICTURE_USD:.2f} — fewer "
          "where the two sets share a plan and it copies instead")


# ── draw ────────────────────────────────────────────────────────────────────


def _log(entry: dict[str, Any]) -> None:
    with (OUT / "draws.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _draw_one(row: Any, prompt: str, pictures: list[bytes], entry: dict[str, Any]) -> Any:
    """One picture, resting on a busy provider. None when the provider refused this picture."""
    rest = FIRST_REST
    while True:
        try:
            return call.image(prompt, row=row, model=IMAGE_MODEL, size=MASTER, references=pictures)
        except ProviderUnavailable as waiting:
            if _login_expired(waiting):
                sys.exit(LOGIN_HINT)
            _log({**entry, "error": waiting.reason, "message": str(waiting)[:300]})
            print(f"  {waiting.reason}: resting {rest:.0f} s ({str(waiting)[:100]})")
            time.sleep(rest)
            rest = min(rest * 2, LONGEST_REST)
        except ProviderRefused as refused:
            _log({**entry, "error": refused.reason, "message": str(refused)[:300]})
            if refused.reason in ("authentication", "configuration"):
                sys.exit(f"{refused} — a setup problem, not this picture. Fix it and rerun.")
            print(f"  refused: {refused}")
            return None


def _same_as_earlier_set(story: dict[str, Any], labels: continuity.Continuity, set_name: str,
                         index: int, chosen: tuple[continuity.Reference, ...],
                         style: Any) -> Path | None:
    """An earlier set's picture of this part, when it was drawn from exactly this plan.

    Same references, chosen for the same ids, and the pictures behind them byte for byte the same:
    then the two sets would only differ by the dice, and a difference the dice made is noise.
    """
    names = list(SETS)
    for earlier in names[:names.index(set_name)]:
        theirs = continuity.references(
            labels, index, lambda part: _picture(story["id"], earlier, part).exists(),
            characters=SETS[earlier])
        drawn = _picture(story["id"], earlier, index)
        if theirs != chosen or not drawn.exists():
            continue
        if all(_picture(story["id"], earlier, one.part).read_bytes()
               == _picture(story["id"], set_name, one.part).read_bytes() for one in chosen):
            return drawn
    return None


def draw(args: argparse.Namespace) -> None:
    row = load_local().find(IMAGE_PROVIDER)
    problem = row.reason()
    if problem:
        sys.exit(f"Vertex cannot be called from this machine: {problem}.")
    styles = load_styles()
    spent, drawn_now = 0.0, 0
    for story in _stories():
        labels = _load_labels(story)
        if labels is None:
            print(f"skip {story['title']}: run `prepare` first")
            continue
        if story["styleId"] not in styles:
            print(f"skip {story['title']}: style {story['styleId']!r} is not in this checkout")
            continue
        for set_name, anchor in SETS.items():
            for index in range(len(story["parts"])):
                target = _picture(story["id"], set_name, index)
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                drawn = _prompt_for(story, labels, index, styles[story["styleId"]],
                                    lambda part: _picture(story["id"], set_name, part).exists(),
                                    anchor)
                if drawn is None:
                    shutil.copyfile(_picture(story["id"], "original", index), target)
                    continue
                prompt, chosen = drawn
                twin = _same_as_earlier_set(story, labels, set_name, index, chosen,
                                            styles[story["styleId"]])
                if twin is not None:
                    shutil.copyfile(twin, target)
                    continue
                if args.limit is not None and drawn_now >= args.limit:
                    print(f"stopped at --limit {args.limit}; ${spent:.2f} spent this run")
                    return
                pictures = [_picture(story["id"], set_name, one.part).read_bytes() for one in chosen]
                entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "story": story["id"],
                         "set": set_name, "part": index + 1,
                         "references": [one.part + 1 for one in chosen]}
                result = _draw_one(row, prompt, pictures, entry)
                if result is None:
                    break  # later parts may be drawn from this one, so the set stops here
                with Image.open(io.BytesIO(result.data)) as image:
                    size = list(image.size)
                target.write_bytes(encode_master(result.data))
                cost = result.answer.cost_usd or 0.0
                _log({**entry, "seconds": round(result.answer.seconds, 2), "costUsd": cost,
                      "drawnSize": size, "warnings": list(result.answer.warnings)})
                spent += cost
                drawn_now += 1
                print(f"  {story['createdAt'][:10]} {story['title'][:34]:<34} [{set_name}] "
                      f"part {index + 1} ← {[one.part + 1 for one in chosen]}  "
                      f"{result.answer.seconds:.0f} s  ${cost:.4f}  (run ${spent:.2f})")
    print(f"done: {drawn_now} drawn this run, ${spent:.2f}")


# ── report ──────────────────────────────────────────────────────────────────


def report(_: argparse.Namespace) -> None:
    stories = {story["id"]: story for story in _stories()}
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    ratings = json.loads((OUT / "ratings.json").read_text(encoding="utf-8"))
    order = sorted(stories, key=lambda story_id: stories[story_id]["createdAt"])
    recent = set(order[-RECENT:])

    best: dict[str, Counter] = defaultdict(Counter)
    flags: dict[str, Counter] = defaultdict(Counter)
    rated = 0
    for story_id in order:
        rating = ratings.get(story_id)
        if not rating or story_id not in key:
            continue
        story = stories[story_id]
        labels = key[story_id]
        held = _load_labels(story)
        redrawn = sum(1 for index in range(len(story["parts"]))
                      if held and continuity.references(held, index))
        look = _look(story)
        choice = rating.get("best") or ""
        if choice:
            rated += 1
            winner = labels.get(choice, "no difference")
            best["recent" if story_id in recent else "older"][winner] += 1
            best[look][winner] += 1
            best[f"  {story['styleId']}"][winner] += 1
        for label, marks in (rating.get("flags") or {}).items():
            for mark, on in marks.items():
                if on:
                    flags[labels[label]][mark] += 1
        print(f"{story['createdAt'][:10]}  {look[:5]:<5} {story['title'][:40]:<40} "
              f"{redrawn} redrawn  best: {labels.get(choice, choice or '—'):<14}"
              f"{'  note: ' + rating['note'] if rating.get('note') else ''}")

    print(f"\n{rated} stories with a preference")
    for group in ("recent", "older", "artwork", "photographic",
                  *sorted(name for name in best if name.startswith("  "))):
        if best[group]:
            print(f"  {group:<22} " + ", ".join(
                f"{arm} {count}" for arm, count in best[group].most_common()))
    print("flags (sets marked):")
    for arm, marks in sorted(flags.items()):
        print(f"  {arm:<14} " + ", ".join(f"{mark} {count}" for mark, count in marks.items()))


def main(argv: list[str] | None = None) -> None:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUT,
                        help="the run directory (default: out/, which holds run 1)")
    commands = parser.add_subparsers(dest="command", required=True)
    fetching = commands.add_parser("fetch", help="copy the stories and their pictures down")
    fetching.add_argument("--server-url", required=True)
    fetching.add_argument("--email", required=True)
    fetching.add_argument("--newest", type=int, help="only the newest N stories")
    preparing = commands.add_parser(
        "prepare", help="label who and where each picture shows; print the plan; write the prompts")
    preparing.add_argument("--force", action="store_true", help="ask for the labels again")
    drawing = commands.add_parser("draw", help="draw the continuity set; safe to stop and rerun")
    drawing.add_argument("--limit", type=int, help="stop after this many pictures")
    commands.add_parser("report", help="unblind the labels")
    args = parser.parse_args(argv)
    OUT = args.out.resolve()
    {"fetch": fetch, "prepare": prepare, "draw": draw, "report": report}[args.command](args)


if __name__ == "__main__":
    main()
