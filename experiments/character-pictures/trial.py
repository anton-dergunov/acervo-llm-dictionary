"""A trial beside the full run: Flex PayGo for Nano Banana 2, and Nano Banana 2.1 in a batch job.

The full run's batch jobs on Nano Banana 2 slowed to a few pictures an hour in November 2026 (README,
"The full run"). This draws 25 new characters two more ways, at most $3 in all, so that the owner can
pick between them for the rest of the run:

- **Flex PayGo, Nano Banana 2**: single calls at the batch price, served from spare capacity. Takes
  7 and 8, since the full run's jobs in flight already own takes 1–6 of these characters. The
  measure is how fast it draws.
- **Nano Banana 2.1, one batch job**: an update to Nano Banana 2 at half its batch price, never
  judged on this task. Takes 1 and 2 in its own folder. The measures are the owner's scores against
  Nano Banana 2's, and how fast its batch queue moves.

The characters are the most popular g2 characters with a checked script and no picture yet. Every
picture lands in the full run's `out/full/pictures/`, so a good one is used there. The batch job's
state is kept apart from the full run's (`out/full/trial/batches.json`): the full run reloads its own
state every round and would collect a job it did not submit. The call log, `out/full/draws.jsonl`, is
shared, so the full run's cap counts the trial's spending.

    .venv/bin/python experiments/character-pictures/trial.py pick          # the 25 characters, once
    .venv/bin/python experiments/character-pictures/trial.py run --dry-run # what it would draw, and cost
    caffeinate -i .venv/bin/python experiments/character-pictures/trial.py run   # until both are done
    .venv/bin/python experiments/character-pictures/trial.py status
    .venv/bin/python experiments/character-pictures/review.py --round trial --host "$(tailscale ip -4)"
    .venv/bin/python experiments/character-pictures/trial.py report        # unblinded, into results/

`run` carries on after any stop: a picture on disk is never drawn again and the job is never
submitted twice.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import batch
import run

TRIAL = run.OUT / "trial"
CHARACTERS = TRIAL / "characters.json"
STATE = TRIAL / "batches.json"
RESULTS = run.RESULTS / "trial"
COUNT = 25
FLEX = run.model_by_id("nano-banana-2")   # Nano Banana 2, through Flex
FLEX_TAKES = (7, 8)
NEW = run.model_by_id("nano-banana-2.1")  # in one batch job
NEW_TAKES = (1, 2)


def characters() -> list[str]:
    if not CHARACTERS.exists():
        sys.exit("No trial characters yet: run `trial.py pick` first.")
    return json.loads(CHARACTERS.read_text(encoding="utf-8"))["characters"]


def items() -> list[dict[str, Any]]:
    """The trial's characters as the review page shows them, in the order picked."""
    chosen = characters()
    found = {item["character"]: item for item in run.items(characters=chosen)}
    return [found[c] for c in chosen if c in found]


def planned() -> list[str]:
    """Every picture of a trial character, as the scoring page's key names them."""
    return ([f"{FLEX.id}/edit/{take}" for take in FLEX_TAKES]
            + [f"{NEW.id}/edit/{take}" for take in NEW_TAKES])


def pick(_: argparse.Namespace) -> None:
    if CHARACTERS.exists():
        sys.exit(f"The trial's characters are already fixed in {CHARACTERS.relative_to(run.REPO)}.")
    chosen = [item for item in run.items(group="g2")
              if item["checked"] and not run.drawn_pictures(item["character"])][:COUNT]
    if len(chosen) < COUNT:
        sys.exit(f"Only {len(chosen)} g2 characters are checked and undrawn; {COUNT} were wanted.")
    TRIAL.mkdir(parents=True, exist_ok=True)
    CHARACTERS.write_text(json.dumps({"characters": [item["character"] for item in chosen],
                                      "picked": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                     ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{COUNT} characters: {''.join(item['character'] for item in chosen)}")


def _missing(model: run.Model, takes: tuple[int, ...]) -> list[tuple[str, int]]:
    return [(c, take) for c in characters() for take in takes
            if not run.picture_path(c, model.id, "edit", take).exists()]


def _submit_new(row: Any, remembered: dict[str, str] | None, state: dict[str, Any],
                prompts: dict[str, str]) -> list[dict[str, Any]]:
    """Submit the Nano Banana 2.1 job for every take not on disk and not in flight."""
    flying = {key for job in state["jobs"] if not job.get("harvested") for key in job["requests"]}
    keys = [f"{c}/{take}" for c, take in _missing(NEW, NEW_TAKES) if f"{c}/{take}" not in flying]
    if not keys:
        return []
    bucket = batch.bucket_for(row)
    known = set(batch._list(row, bucket, "refs/"))
    made = []
    for job in batch._new_jobs(row, bucket, [("trial", key) for key in keys], 500, state, remembered):
        job["model"] = NEW.id
        state["jobs"].append(job)
        batch.save(state, STATE)  # before creating it: a stop in between is found again by its name
        batch.submit(row, job, prompts, known)
        batch.save(state, STATE)
        made.append(job)
        run.say(f"submitted {job['display']}: {len(job['requests'])} pictures with {NEW.model}")
    return made


def run_trial(args: argparse.Namespace) -> None:
    chosen = items()
    prompts = run.prompts_for(chosen)
    rows = batch._rows()
    row, remembered = batch.resolve(argparse.Namespace(provider="current", project=None, credentials=None), rows)
    batch.guard(row)
    state = batch.load(STATE)
    running = batch._collect(state, rows, STATE)
    flex_left = _missing(FLEX, FLEX_TAKES)
    flying = {key for job in running for key in job["requests"]}
    new_left = [pair for pair in _missing(NEW, NEW_TAKES) if f"{pair[0]}/{pair[1]}" not in flying]
    held = sum(len(job["requests"]) for job in running) * batch.PICTURE_RESERVE
    cost = len(flex_left) * batch.PICTURE_RESERVE + len(new_left) * batch.PICTURE_RESERVE
    left = batch.allowance(row) - held
    run.say(f"trial: {len(chosen)} characters; {len(flex_left)} Flex pictures ({FLEX.model}) and "
            f"{len(new_left)} batch pictures ({NEW.model}) to draw, {len(flying)} in flight; "
            f"holding ${cost:.2f} of the ${left:.2f} the cap leaves")
    if cost > left:
        sys.exit("STOPPED: the cap in billing.local.json does not leave enough for the trial")
    if args.dry_run:
        return
    running += _submit_new(row, remembered, state, prompts)

    outcome: dict[str, Any] = {}

    def flex() -> None:
        try:
            outcome["counts"] = batch.flex(row, FLEX, flex_left, prompts, workers=args.workers,
                                           hours=args.flex_hours)
        except batch.Stop as stop:
            outcome["stop"] = stop

    worker = threading.Thread(target=flex, daemon=True)
    worker.start()
    try:
        while worker.is_alive() or running:
            if worker.is_alive():
                worker.join(timeout=args.poll)
            else:
                time.sleep(args.poll)
            if "stop" in outcome:
                break
            if running:
                running = batch._collect(state, rows, STATE)
                for job in running:
                    run.say(f"{job['display']}: {job.get('state', '?').removeprefix('JOB_STATE_').lower()} "
                            f"{job.get('done', 0)}/{len(job['requests'])}")
            if "stop" in outcome:
                break
    except KeyboardInterrupt:
        print("\nStopped here. The batch job keeps running at Google; `trial.py run` again collects it.")
        sys.exit(1)
    if "stop" in outcome:
        print(f"STOPPED: {outcome['stop']}", flush=True)
        sys.exit(1)
    counts = outcome.get("counts") or Counter()
    run.say("trial done: Flex " + (", ".join(f"{n} {k}" for k, n in counts.items()) or "nothing to draw")
            + f"; Nano Banana 2.1 {len(characters()) * len(NEW_TAKES) - len(_missing(NEW, NEW_TAKES))} "
            f"of {len(characters()) * len(NEW_TAKES)} drawn. Score them: review.py --round trial")


# ── measuring ───────────────────────────────────────────────────────────────


def _calls() -> list[dict[str, Any]]:
    """The call log's lines for the trial's pictures."""
    chosen = set(characters())
    path = run.OUT / "draws.jsonl"
    if not path.exists():
        return []
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [entry for entry in lines if entry.get("character") in chosen
            and ((entry.get("route") == "flex" and entry.get("take") in FLEX_TAKES)
                 or (entry.get("model") == NEW.id))]


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text)


def measured() -> list[str]:
    """How each way drew: pictures, time, cost."""
    calls = _calls()
    lines = []
    flex = [e for e in calls if e.get("route") == "flex"]
    drawn = [e for e in flex if e.get("costUsd") and not e.get("error")]
    total = len(characters()) * len(FLEX_TAKES)
    on_disk = total - len(_missing(FLEX, FLEX_TAKES))
    if flex:
        first = min(_when(e["at"]) - _seconds(e) for e in flex)
        last = max(_when(e["at"]) for e in flex)
        hours = max((last - first).total_seconds() / 3600, 1e-9)
        seconds = [e["seconds"] for e in drawn]
        busy = sum(1 for e in flex if e.get("error") == "busy")
        lines.append(f"- Flex PayGo, {FLEX.model}: {on_disk} of {total} pictures; {len(drawn)} drawn in "
                     f"{hours:.2f} h ({len(drawn) / hours:.0f} an hour with up to 4 calls at once); "
                     + (f"a call took {statistics.median(seconds):.0f} s at the median, "
                        f"{max(seconds):.0f} s at most; " if seconds else "")
                     + f"{busy} busy answers rested on; {sum(1 for e in flex if e.get('error') == 'refused')} "
                     f"refused; ${sum(e.get('costUsd') or 0 for e in flex):.2f}")
    else:
        lines.append(f"- Flex PayGo, {FLEX.model}: {on_disk} of {total} pictures; no call logged yet")
    new = [e for e in calls if e.get("model") == NEW.id]
    total = len(characters()) * len(NEW_TAKES)
    on_disk = total - len(_missing(NEW, NEW_TAKES))
    jobs = batch.load(STATE)["jobs"]
    timing = ""
    if jobs:
        submitted = min(_when(job["submitted"]) for job in jobs)
        done = [_when(e["at"]) for e in new if e.get("costUsd")]
        end = max(done) if done and all(job.get("harvested") for job in jobs) else datetime.now(timezone.utc)
        timing = (f"; job {'collected' if all(job.get('harvested') for job in jobs) else 'in flight'} "
                  f"{(end - submitted).total_seconds() / 3600:.1f} h after it was submitted")
    thoughts = [int((e.get("tokens") or {}).get("thoughtsTokenCount") or 0) for e in new if e.get("costUsd")]
    lines.append(f"- Batch, {NEW.model}: {on_disk} of {total} pictures{timing}; "
                 f"{sum(1 for e in new if e.get('error') == 'refused')} refused, "
                 f"{sum(1 for e in new if e.get('error') == 'unfinished')} unfinished; "
                 + (f"{statistics.median(thoughts):.0f} thinking tokens at the median; " if thoughts else "")
                 + f"${sum(e.get('costUsd') or 0 for e in new):.2f}")
    return lines


def _seconds(entry: dict[str, Any]) -> timedelta:
    return timedelta(seconds=float(entry.get("seconds") or 0))


def status(_: argparse.Namespace) -> None:
    print(f"{len(characters())} characters: {''.join(characters())}")
    print("\n".join(measured()))
    labels = _labels()
    print(f"scored: {sum(1 for c in characters() if (labels.get(c) or {}).get('pictures'))} of "
          f"{len(characters())} characters")


# ── the report ──────────────────────────────────────────────────────────────


def _labels() -> dict[str, Any]:
    path = TRIAL / "labels.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def report(_: argparse.Namespace) -> None:
    """Unblind the owner's scores, compare the two models, and make each star a full-run choice."""
    labels = _labels()
    key = json.loads((TRIAL / "key.json").read_text(encoding="utf-8")) if (TRIAL / "key.json").exists() else {}
    scores: dict[str, list[int]] = defaultdict(list)
    answers: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    stars: Counter = Counter()
    starred: dict[str, str] = {}
    for character in characters():
        label = labels.get(character) or {}
        names = key.get(character) or {}
        for letter, given in (label.get("pictures") or {}).items():
            model = names[letter].split("/")[0]
            if given.get("score"):
                scores[model].append(int(given["score"]))
            for question in run.QUESTIONS:
                if given.get(question):
                    answers[model][question][given[question]] += 1
        if label.get("best"):
            model, _way, take = names[label["best"]].split("/")
            stars[model] += 1
            starred[character] = f"{model}/{take}"
    lines = ["# Character pictures: the Flex and Nano Banana 2.1 trial", "",
             f"{len(characters())} g2 characters, two pictures each from Nano Banana 2 (through Flex "
             "PayGo) and Nano Banana 2.1 (in a batch job), scored blind by the owner.", "",
             "## How each way drew", ""] + measured() + ["", "## The owner's scores", "",
             "| Model | Pictures scored | Mean score | 1 | 2 | 3 | 4 | 5 | Strokes kept (yes) | Depicts (yes) | ★ best |",
             "| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |"]
    for model in (FLEX, NEW):
        given = scores.get(model.id) or []
        histogram = Counter(given)
        mean = f"{statistics.mean(given):.2f}" if given else "—"
        yes = [f"{answers[model.id][q]['yes']} of {sum(answers[model.id][q].values())}" for q in run.QUESTIONS]
        lines.append(f"| {model.id} | {len(given)} | {mean} | "
                     + " | ".join(str(histogram[s]) for s in range(1, 6))
                     + f" | {yes[0]} | {yes[1]} | {stars[model.id]} |")
    notes = {c: (labels.get(c) or {}).get("note") for c in characters() if (labels.get(c) or {}).get("note")}
    if notes:
        lines += ["", "## Notes", ""] + [f"- **{c}**: {note}" for c, note in notes.items()]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name in ("labels.json", "key.json", "characters.json"):
        if (TRIAL / name).exists():
            (RESULTS / name).write_text((TRIAL / name).read_text(encoding="utf-8"), encoding="utf-8")
    choices = run.choices()
    added = 0
    for character, picture in starred.items():
        label = choices.setdefault(character, {"best": "", "redraw": False, "note": ""})
        if not label.get("best"):
            label["best"], label["at"] = picture, datetime.now(timezone.utc).isoformat(timespec="seconds")
            added += 1
    if added:
        temporary = run.OUT / "choices.tmp"
        temporary.write_text(json.dumps(choices, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(run.OUT / "choices.json")
    print((RESULTS / "report.md").read_text(encoding="utf-8"))
    print(f"{added} starred pictures made the full run's choice for their character "
          f"({len(starred) - added} already had one)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pick", help=f"fix the trial's {COUNT} characters")
    running = commands.add_parser("run", help="draw both ways until done; safe to rerun")
    running.add_argument("--dry-run", action="store_true")
    running.add_argument("--workers", type=int, default=4, help="Flex calls at once")
    running.add_argument("--flex-hours", type=float, default=24.0,
                         help="how long Flex keeps asking again while it answers busy")
    running.add_argument("--poll", type=float, default=300.0, help="seconds between asking for the job")
    commands.add_parser("status", help="pictures, speed and cost so far")
    commands.add_parser("report", help="the unblinded scores into results/full/trial/")
    args = parser.parse_args(argv)
    try:
        {"pick": pick, "run": run_trial, "status": status, "report": report}[args.command](args)
    except batch.Stop as stop:
        print(f"STOPPED: {stop}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
