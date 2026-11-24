"""Draw the starter vocabularies' shared concept pictures: briefs, then Vertex batch jobs.

    .venv/bin/python experiments/starter-pictures/run.py briefs            # Flash-Lite, the free key
    .venv/bin/python experiments/starter-pictures/run.py check             # who would be billed
    caffeinate -i .venv/bin/python experiments/starter-pictures/run.py draw 2>&1 | tee -a experiments/starter-pictures/out/draw.log
    .venv/bin/python experiments/starter-pictures/run.py status
    .venv/bin/python experiments/starter-pictures/review.py --host "$(tailscale ip -4)"

`briefs` writes one brief per pictured concept with the app's own brief writer, template and style
table (`cards.py` builds the card it reads), through Flash-Lite on the root `.env`'s
`GEMINI_API_KEY`. `draw` draws each brief's composed prompt with Nano Banana 2.1 in Vertex batch
jobs (`vertex.py`), only on the account `.env` beside this file pins (`gcp.py`). Both skip what is
done, so either may be stopped and rerun at any time. The README says why each choice was made.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

RESULTS = HERE / "results"
BRIEFS = RESULTS / "briefs"
DRAWS = RESULTS / "draws.jsonl"
SMOKE = RESULTS / "smoke.jsonl"   # the smoke test's three pictures, drawn from briefs since replaced
LABELS = RESULTS / "labels.json"
OUT = HERE / "out"
PICTURES = OUT / "pictures"
STATE = OUT / "batches.json"
TEMPLATE = ROOT / "prompts" / "acervo_image_brief.md"
STYLES = ROOT / "config" / "image-styles.yaml"

TEXT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
PER_MINUTE = 8          # the free tier meters the key, not the model (scripts/starter/build.py)
REST_SECONDS = 60.0
RESTS = 10              # rests on one concept before it is left for the next run
REFUSALS_TO_SKIP = 2

_log_lock = threading.Lock()


def say(text: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {text}", flush=True)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(path: Path, entry: dict[str, Any]) -> None:
    with _log_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def brief_path(concept: str) -> Path:
    return BRIEFS / f"{concept}.json"


def read_brief(concept: str) -> dict[str, Any] | None:
    path = brief_path(concept)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def picture_path(concept: str, take: int) -> Path:
    return PICTURES / concept / f"{take}.webp"


def takes(concept: str) -> list[int]:
    folder = PICTURES / concept
    return sorted(int(p.stem) for p in folder.glob("*.webp")) if folder.is_dir() else []


def labels() -> dict[str, Any]:
    return json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}


def version() -> str:
    from acervo.images.compose import prompt_version
    from acervo.images.styles import load_styles

    return prompt_version(TEMPLATE, load_styles(STYLES).digest)


def chosen(args: argparse.Namespace, items: list[Any]) -> list[Any]:
    names = {name.strip() for name in (getattr(args, "concepts", "") or "").split(",") if name.strip()}
    if names:
        unknown = names - {item.id for item in items}
        if unknown:
            sys.exit(f"no pictured concept named {', '.join(sorted(unknown))}")
        items = [item for item in items if item.id in names]
    return items


# ── briefs ──────────────────────────────────────────────────────────────────


def text_candidates():
    """Flash-Lite on the root `.env`'s GEMINI_API_KEY, as a one-provider chain."""
    from dotenv import dotenv_values

    from acervo.models import chain
    from acervo.models.providers import build

    key = dotenv_values(ROOT / ".env").get("GEMINI_API_KEY")
    if not key:
        sys.exit(f"{ROOT / '.env'} has no GEMINI_API_KEY")
    document = {"id": "gemini-env", "family": "gemini-api", "models": {"text": list(TEXT_MODELS)}, "position": 0}
    catalogue, refused = build([document], {"gemini-env": {"key": key}})
    if refused:
        sys.exit(f"the GEMINI_API_KEY in .env was refused: {refused[0][1]}")
    return catalogue, chain.resolve("text", ["gemini-env"], catalogue), f"{key[:4]}…{key[-4:]}"


class Pacer:
    """Starts at most PER_MINUTE calls a minute across every worker."""

    def __init__(self, per_minute: int) -> None:
        self.gap = 60.0 / per_minute
        self.next = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            moment = time.monotonic()
            start = max(moment, self.next)
            self.next = start + self.gap
        time.sleep(max(0.0, start - moment))


class DayOver(Exception):
    pass


def briefs(args: argparse.Namespace) -> None:
    import cards
    from acervo.images.brief import BriefWriter, build_request
    from acervo.images.compose import compose
    from acervo.images.styles import load_styles
    from acervo.models.errors import ChainExhausted

    styles = load_styles(STYLES)
    current = version()
    catalogue, candidates, shown = text_candidates()
    writer = BriefWriter(catalogue, candidates, TEMPLATE.read_text(encoding="utf-8"), styles)
    every = chosen(args, cards.cards())
    todo = [card for card in every
            if args.redo or (read_brief(card.id) or {}).get("promptVersion") != current]
    if args.limit:
        todo = todo[: args.limit]
    say(f"briefs: {len(every)} pictured concepts, {len(todo)} to write, prompt version {current}, "
        f"key {shown}, models {', '.join(TEXT_MODELS)}")
    pacer = Pacer(PER_MINUTE)
    stop = threading.Event()
    counts: Counter[str] = Counter()

    def one(card) -> None:
        if stop.is_set():
            return
        article = cards.article(card)
        for rest in range(RESTS + 1):
            pacer.wait()
            if stop.is_set():
                return
            try:
                written, usage = writer.write(article)
                break
            except ChainExhausted as exhausted:
                detail = str(exhausted.last)
                if "perday" in detail.replace("_", "").replace("-", "").lower():
                    stop.set()
                    raise DayOver(detail) from None
                if exhausted.waited_on_nothing or rest == RESTS:
                    counts["failed"] += 1
                    say(f"{card.id}: no usable brief ({detail[:300]}); a rerun asks again")
                    return
                time.sleep(REST_SECONDS)
        sense = written[0]
        style = styles[sense.style_id] if not sense.refused else None
        record = {
            "concept": card.id, **card.summary(),
            "refused": sense.refused, "refusalReason": sense.refusal_reason,
            "styleId": sense.style_id or None, "styleLabel": style.label if style else None,
            "situation": sense.situation, "subject": sense.subject, "brief": sense.brief,
            "anchorExampleId": sense.anchor_example_id,
            "prompt": compose(sense.brief, style) if style else None,
            "promptVersion": current, "writtenAt": stamp(), "usage": usage,
            "request": {key: value for key, value in build_request(article, styles).items() if key != "styles"},
        }
        write_json(brief_path(card.id), record)
        counts["refused" if sense.refused else "written"] += 1
        done = sum(counts.values())
        if done % 25 == 0 or done == len(todo):
            say(f"{done}/{len(todo)}: {dict(counts)}")

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in [pool.submit(one, card) for card in todo]:
                future.result()
    except DayOver as over:
        say(f"STOPPED: the free key's daily allowance is spent ({str(over)[:200]}). Rerun after "
            "midnight in California; written briefs are kept.")
        sys.exit(1)
    say(f"done: {dict(counts)}")


# ── drawing ─────────────────────────────────────────────────────────────────


def refusals() -> Counter[str]:
    return Counter(entry["concept"] for entry in read_jsonl(DRAWS) if entry.get("error") == "refused")


def spent() -> float:
    """Everything this experiment has spent, the smoke test's three pictures included."""
    return sum(float(entry.get("costUsd") or 0) for path in (DRAWS, SMOKE) for entry in read_jsonl(path))


def request_key(concept: str, take: int, variant: bool) -> str:
    """A job's name for one picture. Several ideas for one concept share a concept, so each takes its own
    key (`week~5/1`), which `store` turns back into concept and take."""
    return f"{concept}~{take}/1" if variant else f"{concept}/{take}"


def prompt_for(brief: dict[str, Any], concept_take: int, have_last: int) -> dict[str, Any]:
    """The brief fields a picture is drawn from: the concept's own, or the variant for this take."""
    variants = brief.get("variants") or []
    if variants and concept_take > have_last:
        return variants[(concept_take - have_last - 1) % len(variants)]
    return brief


def wanted(args: argparse.Namespace, state: dict[str, Any]) -> list[tuple[str, int]]:
    """(concept, take) for every picture to submit now, in the concept list's order."""
    import cards

    in_flight = {key for job in state["jobs"] if not job.get("harvested") for key in job["requests"]}
    refused = refusals()
    labelled = labels()
    named = bool(getattr(args, "concepts", ""))
    plan = []
    for card in chosen(args, cards.cards()):
        brief = read_brief(card.id)
        if not brief or brief.get("refused") or not brief.get("prompt"):
            continue
        have = takes(card.id)
        alternatives = brief.get("variants") or []
        if args.redraw:
            label = labelled.get(card.id) or {}
            if not have or label.get("label") != "redraw" or label.get("through", label.get("take")) != have[-1]:
                continue
            # A concept the owner keeps rejecting carries several ideas in `variants`: one take for each.
            new = range(have[-1] + 1, have[-1] + 1 + max(1, len(alternatives)))
        elif have:
            continue
        else:
            new = range(1, 2)
        if refused[card.id] >= REFUSALS_TO_SKIP and not named:
            continue
        for take in new:
            if request_key(card.id, take, bool(args.redraw and alternatives)) not in in_flight:
                plan.append((card.id, take))
    return plan


def store(job: dict[str, Any]):
    """The writer `vertex.harvest` calls: the master, and its line in draws.jsonl."""
    from acervo.images.render import encode_master
    import vertex

    def write(key: str, take: int, data: bytes, usage: dict[str, Any]) -> bool:
        concept = key
        if "~" in key:   # one of several ideas for a concept: the take is in the key
            concept, number = key.split("~")
            take = int(number)
        target = picture_path(concept, take)
        if target.exists():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encode_master(data))
        meta = job["meta"][key]
        append(DRAWS, {"at": stamp(), "concept": concept, "take": take, "job": job["display"],
                       "model": vertex.MODEL, "route": "vertex-batch", "styleId": meta["styleId"],
                       "promptVersion": meta["promptVersion"], "brief": meta["brief"], "seed": None,
                       "costUsd": vertex.cost(usage), "tokens": usage})
        return True

    return write


def collect(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Ask every job in flight for its state; collect the finished ones. The ones still running."""
    import vertex

    running = []
    for job in state["jobs"]:
        if job.get("harvested"):
            continue
        if not job.get("name"):
            found = vertex.find_job(job["display"])
            if not found:
                job["harvested"], job["state"] = True, "NEVER_CREATED"
                vertex.save(state, STATE)
                continue
            job["name"] = found["name"]
        try:
            vertex.refresh(job)
        except ConnectionError as error:
            say(f"{job['display']}: could not ask for its state ({error}); trying again later")
            running.append(job)
            continue
        if job["state"] in vertex.RUNNING:
            vertex.save(state, STATE)
            running.append(job)
            continue
        prompts = {concept: meta["prompt"] for concept, meta in job["meta"].items()}
        drawn, refused, unfinished = vertex.harvest(job, prompts, store(job), lambda entry: append(DRAWS, entry))
        vertex.save(state, STATE)
        note = f"; {job['error']}" if job.get("error") else ""
        say(f"{job['display']}: {job['state'].removeprefix('JOB_STATE_').lower()}, {drawn} pictures written, "
            f"{refused} refused, {unfinished} unfinished (asked for again){note}")
        if job.get("error") and any(word in job["error"].lower() for word in ("billing", "credit", "payment")):
            raise vertex.Stop(f"job {job['display']} stopped because the account cannot pay: {job['error']}")
    return running


def submit(plan: list[tuple[str, int]], state: dict[str, Any]) -> dict[str, Any]:
    import vertex

    vertex.bucket()
    display = f"starter-pictures-{len(state['jobs']) + 1:03d}-{datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%S')}"
    meta, requests = {}, []
    for concept, take in plan:
        brief = read_brief(concept)
        have = takes(concept)
        source = prompt_for(brief, take, have[-1] if have else 0) if brief.get("variants") and have else brief
        request = request_key(concept, take, source is not brief)
        key = request.rsplit("/", 1)[0]   # what `vertex.harvest` calls the concept
        meta[key] = {"prompt": source["prompt"], "styleId": source.get("styleId") or brief["styleId"],
                     "promptVersion": brief["promptVersion"], "brief": source["brief"]}
        requests.append(request)
    job = {"display": display, "prefix": f"jobs/{display}", "requests": requests,
           "meta": meta, "model": vertex.MODEL, "name": None, "state": "SUBMITTING", "harvested": False,
           "submitted": stamp()}
    body = "".join(json.dumps(vertex.request_line(meta[request.rsplit("/", 1)[0]]["prompt"]), ensure_ascii=False) + "\n"
                   for request in requests)
    state["jobs"].append(job)
    vertex.save(state, STATE)  # before creating it: a stop in between is found again by its name
    try:
        vertex.create_job(job, body)
    except ConnectionError:
        state["jobs"].remove(job)
        vertex.save(state, STATE)
        raise
    vertex.save(state, STATE)
    say(f"submitted {display}: {len(plan)} pictures")
    return job


def draw(args: argparse.Namespace) -> None:
    import gcp
    import vertex

    pin = gcp.verify()
    say(f"account checked: gcloud configuration {pin.gcloud_config}, credentials {Path(pin.adc).name}, "
        f"bucket gs://<project>{gcp.BUCKET_SUFFIX}; model {vertex.MODEL}")
    state = vertex.load(STATE)
    submitted = 0
    while True:
        running = collect(state)
        if not running:
            plan = wanted(args, state)
            if args.limit:
                plan = plan[: max(0, args.limit - submitted)]
            left = args.cap - spent()
            plan = plan[: max(0, int(left // vertex.PICTURE_RESERVE))]
            plan = plan[: args.job_size]
            say(f"to submit now: {len(plan)} pictures (${spent():.2f} of the ${args.cap:.2f} cap spent)")
            if args.dry_run or not plan:
                break
            try:
                running = [submit(plan, state)]
            except ConnectionError as error:
                say(f"could not submit now ({error}); trying again after the wait")
            submitted += len(plan) if running else 0
        if args.no_wait:
            say("not waiting; rerun the same command to collect")
            return
        for job in running:
            say(vertex.job_progress(job))
        drawn = sum(1 for p in PICTURES.glob("*/*.webp")) if PICTURES.exists() else 0
        say(f"pictures on disk: {drawn}; waiting {args.poll:.0f} s")
        time.sleep(args.poll)
    missing = len(wanted(args, state))
    say(f"done; {missing} pictures still wanted" + (" — run the same command again" if missing else ""))


def check(_: argparse.Namespace) -> None:
    import cards
    import gcp
    import vertex

    pin = gcp.verify()
    print(f"account        {pin.account}\nproject        {pin.project} (number {pin.number})\n"
          f"gcloud config  {pin.gcloud_config}\nADC file       {pin.adc}\nbucket         gs://{pin.bucket}\n"
          f"model          {vertex.MODEL} ({vertex.LOCATION})")
    every = cards.cards()
    ready = [c for c in every if (read_brief(c.id) or {}).get("prompt")]
    state = vertex.load(STATE)
    args = argparse.Namespace(concepts="", redraw=False)
    plan = wanted(args, state)
    print(f"briefs         {len(ready)} of {len(every)} pictured concepts\n"
          f"to draw        {len(plan)} pictures, about ${len(plan) * 0.0244:.2f} "
          f"(at most ${len(plan) * vertex.PICTURE_RESERVE:.2f}), about {len(plan) / 55:.1f} h at one job's pace\n"
          f"spent so far   ${spent():.2f}")


def status(_: argparse.Namespace) -> None:
    import cards
    import vertex

    every = cards.cards()
    briefed = [read_brief(c.id) for c in every]
    drawn = [c for c in every if takes(c.id)]
    refused = refusals()
    labelled = labels()
    marks = Counter(label.get("label") for concept, label in labelled.items()
                    if takes(concept) and label.get("through", label.get("take")) == takes(concept)[-1])
    print(f"concepts   {len(every)} pictured")
    print(f"briefs     {sum(1 for b in briefed if b and b.get('prompt'))} written, "
          f"{sum(1 for b in briefed if b and b.get('refused'))} refused by the writer, "
          f"{sum(1 for b in briefed if not b)} missing")
    print(f"pictures   {len(drawn)} concepts drawn, {sum(len(takes(c.id)) for c in drawn)} takes; "
          f"{len(refused)} concepts refused by the model at least once")
    print(f"labels     {marks.get('good', 0)} good, {marks.get('redraw', 0)} redraw, "
          f"{len(drawn) - sum(marks.values())} to label")
    print(f"spent      ${spent():.2f}")
    for job in vertex.load(STATE)["jobs"]:
        if not job.get("harvested"):
            print(vertex.job_progress(job))
    if any(b and b.get("refused") for b in briefed):
        print("writer refused:", ", ".join(b["concept"] for b in briefed if b and b.get("refused")))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    writing = sub.add_parser("briefs", help="Write a brief per pictured concept (Flash-Lite, free key)")
    writing.add_argument("--concepts", default="", help="Only these concept ids, comma-separated")
    writing.add_argument("--limit", type=int, default=0)
    writing.add_argument("--redo", action="store_true", help="Write again even where a current brief exists")
    writing.add_argument("--workers", type=int, default=3)
    drawing = sub.add_parser("draw", help="Draw the pictures in Vertex batch jobs, one job at a time")
    drawing.add_argument("--concepts", default="", help="Only these concept ids (also redraws refused ones)")
    drawing.add_argument("--limit", type=int, default=0, help="At most this many pictures in this run")
    drawing.add_argument("--redraw", action="store_true", help="The next take of each concept labelled redraw")
    drawing.add_argument("--job-size", type=int, default=250)
    drawing.add_argument("--poll", type=float, default=300.0)
    drawing.add_argument("--cap", type=float, default=25.0, help="Dollars this experiment may spend in all")
    drawing.add_argument("--dry-run", action="store_true")
    drawing.add_argument("--no-wait", action="store_true")
    sub.add_parser("check", help="Check the pinned account and say what a draw would cost")
    sub.add_parser("status", help="Briefs, pictures, labels and jobs in flight")
    args = parser.parse_args(argv)
    command = {"briefs": briefs, "draw": draw, "check": check, "status": status}[args.command]
    import vertex

    try:
        command(args)
    except vertex.Stop as stop:
        print(f"STOPPED: {stop}", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped here. A job already submitted keeps running at Google; run the same command "
              "again to collect it.", flush=True)
        sys.exit(130)


if __name__ == "__main__":
    main()
