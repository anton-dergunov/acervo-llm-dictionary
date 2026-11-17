"""Argon fact-checks the stroke scripts against their scholarly origin, and writes the missing ones.

Both run as Vertex batch jobs (half the price), in the same account, bucket and cap as the drawing
(`batch.py`), the way the owner's task-concept-retrieval judge runs them: a JSONL of requests keyed
`<kind>|<character>|<attempt>`, the state saved before and after a job is created so nothing is ever
submitted twice, and an answer that cannot be used asked again with its problems listed, at most
three times.

- **factcheck** (`prompts/factcheck.md`): the guide, the fact sheet, the script and Wiktionary's
  "Glyph origin" (`origins.py`). Argon keeps the script, corrects its object and history (and what
  follows from them), or drops a character the origin calls sound plus meaning. Every stroke's
  `where` is the fact sheet's and may not change.
- **write** (`prompts/write.md`): the guide, the fact sheet, the origin and the numbered drawing of
  the strokes. Argon writes one script, or drops the character as above.

Answers are a YAML block, never constrained decoding. A correction is spliced into its file in
place, so untouched scripts stay byte-identical and `git diff` shows exactly what Argon changed. A
checked script carries `checked: argon`, and only checked scripts are drawn; a dropped one carries
`dropped: <reason>` and is never drawn. Every reply goes to `results/full/argon/<kind>.jsonl`.

`run.py full` runs everything left in order, under the cap: check g1, then draw it while g2 and g3
are written; check those, then draw them.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
import textwrap
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import batch
import origins
import run

MODEL = "gemini-4-argon"  # served on the global endpoint only
# Vertex batch prices per million tokens, at the promotion that lasts to 30 November 2026 (read
# 2026-11-05 for the task-concept-retrieval judge): $1 in, $5 out, thinking counted as output.
PRICE_IN, PRICE_OUT = 1.00, 5.00
MAX_OUTPUT = 20_000
# A request's upper bound: at most 30,000 tokens in (the origin is cut at ORIGIN_CHARACTERS) and
# every token it may answer with. The ledger keeps the same number (`batch.ARGON_RESERVE`).
RESERVE = batch.ARGON_RESERVE
assert RESERVE >= (30_000 * PRICE_IN + MAX_OUTPUT * PRICE_OUT) / 1e6
ORIGIN_CHARACTERS = 12_000
ATTEMPTS = 3
FILE_SIZE = 25  # scripts a file, as g1's
STATE = batch.ARGON_STATE
LOG = batch.ARGON_LOG
REPLIES = run.RESULTS / "argon"
KINDS = ("factcheck", "write")
FIELDS = ("object", "history", "layout", "exact", "strokes")


# ── the script files ────────────────────────────────────────────────────────


def locate(character: str) -> tuple[Path, int, int, int] | None:
    """Where a character's script is: its file, the start and end of its block, the end of its key line."""
    for path in sorted(run.SCRIPTS.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        match = re.search(rf"^{re.escape(character)}:[ \t]*$", text, re.M)
        if match:
            following = re.compile(r"^[^\s#-]", re.M).search(text, match.end())
            return path, match.start(), following.start() if following else len(text), match.end()
    return None


def _plain(text: str) -> bool:
    try:
        return "\n" not in text and yaml.safe_load(f"k: {text}") == {"k": text}
    except yaml.YAMLError:
        return False


def _scalar(text: str) -> str:
    return text if _plain(text) else json.dumps(text, ensure_ascii=False)


def _folded(text: str, indent: int) -> str:
    lines = textwrap.wrap(text, width=100 - indent, break_long_words=False, break_on_hyphens=False)
    return ">-\n" + "\n".join(" " * indent + line for line in lines)


def _clean(script: dict[str, Any]) -> dict[str, Any]:
    """The fields a script keeps, whitespace settled, in the guide's order."""
    found: dict[str, Any] = {}
    for key in ("checked", "dropped", "object", "history", "layout"):
        if script.get(key):
            found[key] = re.sub(r"\s+", " ", str(script[key])).strip()
    if script.get("exact"):
        found["exact"] = [re.sub(r"\s+", " ", str(line)).strip() for line in script["exact"]]
    if script.get("strokes"):
        found["strokes"] = [{"where": re.sub(r"\s+", " ", str(line["where"])).strip(),
                             "part": re.sub(r"\s+", " ", str(line["part"])).strip()} for line in script["strokes"]]
    return found


def emit(character: str, script: dict[str, Any]) -> str:
    """One script as YAML, in the files' own style; checked by reading it back."""
    script = _clean(script)
    lines = [f"{character}:"]
    for key in ("checked", "dropped", "object"):
        if key in script:
            lines.append(f"  {key}: {_scalar(script[key])}")
    for key in ("history", "layout"):
        if key in script:
            lines.append(f"  {key}: {_folded(script[key], 4)}")
    if "exact" in script:
        lines.append("  exact:")
        lines += [f"    - {_scalar(line)}" for line in script["exact"]]
    if "strokes" in script:
        lines.append("  strokes:")
        for line in script["strokes"]:
            lines += [f"    - where: {_scalar(line['where'])}", f"      part: {_scalar(line['part'])}"]
    text = "\n".join(lines) + "\n"
    if yaml.safe_load(text) != {character: script}:
        text = yaml.safe_dump({character: script}, allow_unicode=True, sort_keys=False, width=100)
    assert yaml.safe_load(text) == {character: script}
    return text


def _replace(path: Path, start: int, end: int, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    tail = "\n" if end < len(text) else ""
    path.write_text(text[:start] + block + tail + text[end:].lstrip("\n"), encoding="utf-8")


def mark(character: str, extra: dict[str, str]) -> None:
    """Add `checked`/`dropped` under a script's key, touching nothing else in the file."""
    path, _start, _end, key_end = locate(character)
    text = path.read_text(encoding="utf-8")
    added = "".join(f"\n  {key}: {_scalar(value)}" for key, value in extra.items())
    path.write_text(text[:key_end] + added + text[key_end:], encoding="utf-8")


def replace_script(character: str, script: dict[str, Any]) -> None:
    path, start, end, _key_end = locate(character)
    _replace(path, start, end, emit(character, script))


def file_for(entry: dict[str, Any]) -> Path:
    members = [e["character"] for e in run.catalogue() if e["group"] == entry["group"]]
    return run.SCRIPTS / f"{entry['group']}-{members.index(entry['character']) // FILE_SIZE + 1:02d}.yaml"


def add_script(entry: dict[str, Any], script: dict[str, Any]) -> None:
    if locate(entry["character"]):
        replace_script(entry["character"], script)
        return
    path = file_for(entry)
    number = path.stem.split("-")[1]
    text = path.read_text(encoding="utf-8") if path.exists() else (
        f"# Full run, group {entry['group']}, batch {number}. Written by Argon (argon.py) from the fact "
        "sheets, following scripts/GUIDE.md.\n")
    path.write_text(text.rstrip("\n") + "\n\n" + emit(entry["character"], script), encoding="utf-8")


def block_text(character: str) -> str:
    path, start, end, _ = locate(character)
    return path.read_text(encoding="utf-8")[start:end].strip() + "\n"


# ── the requests ────────────────────────────────────────────────────────────


def _system(kind: str) -> str:
    guide = (run.SCRIPTS / "GUIDE.md").read_text(encoding="utf-8")
    return (run.PROMPTS / f"{kind}.md").read_text(encoding="utf-8").strip() + "\n\n---\n\n" + guide


def _origin_text(character: str) -> str:
    text = origins.text_for(character)
    if len(text) > ORIGIN_CHARACTERS:
        text = text[:ORIGIN_CHARACTERS] + "\n\n(cut here)"
    return text or "Wiktionary has no Glyph origin section for this character or its related forms."


def request_line(kind: str, entry: dict[str, Any], attempt: int, task: dict[str, Any],
                 system: str) -> dict[str, Any]:
    import facts

    character = entry["character"]
    sheet = run.fact_sheet_path(entry).read_text(encoding="utf-8")
    text = [f"# {character}", "", "## The fact sheet", "", sheet.strip(), ""]
    if kind == "factcheck":
        text += ["## The script as written", "", "```yaml", block_text(character).rstrip(), "```", ""]
    text += ["## Glyph origin, from the character's English Wiktionary entry (wikitext)", "",
             _origin_text(character), ""]
    if task.get("problems"):
        text += ["## Your previous answer could not be used", "",
                 *[f"- {problem}" for problem in task["problems"]], "",
                 "Answer again, whole, fixing every problem."]
    parts: list[dict[str, Any]] = [{"text": "\n".join(text)}]
    if kind == "write":
        drawing = facts.numbered_sheet(run._strokes(character))
        parts += [{"text": "The numbered drawing of the strokes (numbers for you only; never write them):"},
                  {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(drawing).decode()}}]
    return {"key": f"{kind}|{character}|{attempt}", "request": {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 1.0, "maxOutputTokens": MAX_OUTPUT,
                             "thinkingConfig": {"thinkingLevel": "HIGH"}},
    }}


# ── the state ───────────────────────────────────────────────────────────────


def load() -> dict[str, Any]:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"jobs": [], "tasks": {}}


def save(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(STATE)


def in_flight(state: dict[str, Any]) -> set[str]:
    return {key.rsplit("|", 1)[0] for job in state["jobs"] if not job.get("harvested") for key in job["requests"]}


def targets(kind: str, state: dict[str, Any], groups: tuple[str, ...],
            characters: str | None = None) -> list[dict[str, Any]]:
    """Every character this stage still has to do, most popular first."""
    scripts = run._scripts()
    flying = in_flight(state)
    found = []
    for group in groups:
        for entry in run.in_scope(group=group, characters=characters):
            character = entry["character"]
            task = state["tasks"].get(f"{kind}|{character}") or {}
            if f"{kind}|{character}" in flying or task.get("status") in ("done", "failed"):
                continue
            script = scripts.get(character)
            if kind == "factcheck":
                if not isinstance(script, dict) or script.get("checked") or run.problems(character, script):
                    continue
            elif script is not None:
                continue
            found.append(entry)
    return found


# ── answers ─────────────────────────────────────────────────────────────────


def _answer_text(response: dict[str, Any]) -> str:
    candidate = (response.get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in (candidate.get("content") or {}).get("parts") or []
                   if not p.get("thought"))


def parse(text: str) -> Any:
    blocks = re.findall(r"```ya?ml[ \t]*\n(.*?)```", text, re.S)
    return yaml.safe_load(blocks[-1] if blocks else text)


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def judge(kind: str, character: str, answer: Any) -> tuple[str, dict[str, Any] | None, list[str]]:
    """(verdict, the script to keep, problems). A script returned is already valid."""
    if not isinstance(answer, dict):
        return "", None, ["the answer must be one YAML mapping in a ```yaml block"]
    verdict = str(answer.get("verdict") or "").strip()
    allowed = ("keep", "correct", "drop") if kind == "factcheck" else ("write", "drop")
    problems = [] if verdict in allowed else [f"`verdict` must be one of {', '.join(allowed)}"]
    for field in ("origin", "reason"):
        if not _norm(answer.get(field)):
            problems.append(f"no `{field}`")
    if problems or verdict in ("keep", "drop"):
        return verdict, None, problems
    script = answer.get("script")
    if not isinstance(script, dict):
        return verdict, None, ["no `script` mapping"]
    script = {key: script[key] for key in FIELDS if key in script}
    if kind == "factcheck":
        original = run._scripts()[character]
        lines, before = script.get("strokes") or [], original["strokes"]
        if not isinstance(lines, list) or len(lines) != len(before):
            return verdict, None, [f"the script must keep all {len(before)} strokes, in order"]
        for index, (new, old) in enumerate(zip(lines, before)):
            if not isinstance(new, dict) or _norm(new.get("where")) != _norm(old["where"]):
                problems.append(f"the stroke whose `where` was “{_norm(old['where'])}” must keep that "
                                "`where` word for word")
            elif isinstance(new, dict):
                new["where"] = old["where"]  # the original text, not a re-wrapped copy
        if len(script.get("exact") or []) != len(original.get("exact") or []):
            problems.append(f"`exact` must keep its {len(original.get('exact') or [])} items, reworded "
                            "only where a part's name changed")
    try:
        problems += run.problems(character, script)
    except (KeyError, TypeError, AttributeError) as error:
        problems.append(f"the script is malformed: {error}")
    return verdict, (None if problems else script), problems


def _cost(usage: dict[str, Any]) -> float:
    prompt = int(usage.get("promptTokenCount") or 0)
    output = int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)
    return round((prompt * PRICE_IN + output * PRICE_OUT) / 1e6, 6)


def _record(kind: str, entry: dict[str, Any]) -> None:
    REPLIES.mkdir(parents=True, exist_ok=True)
    with (REPLIES / f"{kind}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def apply(kind: str, character: str, attempt: int, text: str, usage: dict[str, Any],
          state: dict[str, Any], job: dict[str, Any]) -> str:
    """Use one answer: change the script file, record the reply. The verdict, or '' if unusable."""
    task = state["tasks"].setdefault(f"{kind}|{character}", {"attempts": attempt})
    entry = next(e for e in run.catalogue() if e["character"] == character)
    try:
        answer = parse(text)
    except yaml.YAMLError as error:
        answer, verdict, script, problems = None, "", None, [f"the YAML does not parse: {str(error)[:200]}"]
    else:
        verdict, script, problems = judge(kind, character, answer)
    record = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "character": character,
              "group": entry["group"], "attempt": attempt, "job": job["display"], "verdict": verdict or None,
              "origin": _norm((answer or {}).get("origin")) if isinstance(answer, dict) else None,
              "originFrom": "English Wiktionary, Glyph origin (CC BY-SA 4.0)" if origins.text_for(character) else None,
              "reason": _norm((answer or {}).get("reason")) if isinstance(answer, dict) else None,
              "problems": problems or None, "tokens": usage, "reply": text}
    if kind == "factcheck" and not problems:
        before = run._scripts()[character]
        record["before"] = {k: _norm(before.get(k)) for k in ("object", "history")}
    if problems:
        task.update(problems=problems, status="failed" if attempt >= ATTEMPTS else "open")
        _record(kind, record)
        return ""
    reason = _norm(answer["reason"])
    if verdict == "keep":
        mark(character, {"checked": "argon"})
    elif verdict == "drop":
        if kind == "factcheck":
            mark(character, {"checked": "argon", "dropped": reason})
        else:
            add_script(entry, {"checked": "argon", "dropped": reason})
    elif verdict == "correct":
        replace_script(character, {"checked": "argon", **script})
        record["after"] = {k: _norm(script.get(k)) for k in ("object", "history")}
    else:  # write
        add_script(entry, script)
    task.update(status="done", verdict=verdict, problems=None)
    _record(kind, record)
    return verdict


def collect(state: dict[str, Any], rows: dict[str, Any]) -> list[dict[str, Any]]:
    """Ask every Argon job in flight for its state; use the finished ones. The ones still running."""
    running = []
    for job in state["jobs"]:
        if job.get("harvested"):
            continue
        row = batch._row_for(job, rows)
        if not job.get("name"):
            found = batch._find_job(row, job["display"])
            if not found:
                job["harvested"], job["state"] = True, "NEVER_CREATED"
                save(state)
                continue
            job["name"] = found["name"]
        try:
            batch.refresh(row, job)
        except ConnectionError as error:
            run.say(f"{job['display']}: could not ask for its state ({error}); trying again later")
            running.append(job)
            continue
        if job["state"] in batch.RUNNING:
            running.append(job)
            continue
        verdicts: Counter[str] = Counter()
        seen = set()
        names = batch._list(row, job["bucket"], f"{job['prefix']}/output")
        for name in sorted(n for n in names if n.endswith(".jsonl")):
            for raw in batch._lines(row, job["bucket"], name):
                line = json.loads(raw)
                key = line.get("key") or ""
                if key not in job["requests"] or key in seen:
                    continue
                seen.add(key)
                kind, character, attempt = key.split("|")
                response = line.get("response") or {}
                usage = response.get("usageMetadata") or {}
                cost = _cost(usage)
                with LOG.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                             "model": MODEL, "kind": kind, "character": character,
                                             "attempt": int(attempt), "job": job["display"], "provider": row.id,
                                             "costUsd": cost, "tokens": usage,
                                             **({} if response else {"error": run._scrubbed(str(line.get("status")))})},
                                            ensure_ascii=False) + "\n")
                text = _answer_text(response)
                if not text:
                    finish = ((response.get("candidates") or [{}])[0]).get("finishReason")
                    reason = finish or run._scrubbed(str(line.get("status") or "no answer"))
                    task = state["tasks"].setdefault(f"{kind}|{character}", {"attempts": int(attempt)})
                    task.update(problems=[f"no answer came back ({reason})"],
                                status="failed" if int(attempt) >= ATTEMPTS else "open")
                    verdicts["unusable"] += 1
                    continue
                verdicts[apply(kind, character, int(attempt), text, usage, state, job) or "unusable"] += 1
        for key in job["requests"]:
            if key not in seen:
                kind, character, attempt = key.split("|")
                task = state["tasks"].setdefault(f"{kind}|{character}", {"attempts": int(attempt)})
                task.update(problems=["no answer came back from the batch job"],
                            status="failed" if int(attempt) >= ATTEMPTS else "open")
                verdicts["missing"] += 1
        job["harvested"], job["verdicts"] = True, dict(verdicts)
        save(state)
        batch._delete(row, job["bucket"], names + [f"{job['prefix']}/input.jsonl"])
        note = f"; {job['error']}" if job.get("error") else ""
        run.say(f"{job['display']}: {job['state'].removeprefix('JOB_STATE_').lower()}, "
                + ", ".join(f"{n} {v}" for v, n in verdicts.items()) + note)
    return running


def submit(kind: str, chosen: list[dict[str, Any]], row: Any, remembered: dict[str, str] | None,
           state: dict[str, Any], size: int, dry_run: bool = False) -> list[dict[str, Any]]:
    """Submit one stage's requests that the cap allows, in jobs of `size`. The jobs made."""
    if not chosen:
        return []
    left = batch.allowance(row)
    fits = chosen[: max(0, math.floor(left / RESERVE))]
    run.say(f"{kind}: {len(fits)} of {len(chosen)} to submit, holding ${len(fits) * RESERVE:.2f} of the "
            f"${left:.2f} the cap leaves")
    if dry_run or not fits:
        return []
    run.write_fact_sheets(fits)  # with the components' scripts as they are now
    system = _system(kind)
    bucket = batch.bucket_for(row)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")
    made = []
    for start in range(0, len(fits), size):
        members = fits[start:start + size]
        lines, keys = [], []
        for entry in members:
            task = state["tasks"].setdefault(f"{kind}|{entry['character']}", {"attempts": 0})
            attempt = int(task.get("attempts") or 0) + 1
            line = request_line(kind, entry, attempt, task, system)
            lines.append(json.dumps(line, ensure_ascii=False))
            keys.append(line["key"])
        display = f"character-pictures-{kind}-{len(state['jobs']) + 1:03d}-{stamp}"
        job = {"display": display, "kind": kind, "provider": row.id, "bucket": bucket,
               "prefix": f"jobs/{display}", "requests": keys, "name": None, "state": "SUBMITTING",
               "harvested": False, "account": remembered,
               "submitted": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        state["jobs"].append(job)
        save(state)  # before creating it: a stop in between is found again by its name
        try:
            batch.create_job(row, job, "\n".join(lines) + "\n", MODEL)
        except ConnectionError as error:
            state["jobs"].remove(job)
            save(state)
            run.say(f"could not submit {display} now ({error}); the next round submits it")
            break
        for key in keys:
            state["tasks"][key.rsplit("|", 1)[0]]["attempts"] = int(key.rsplit("|", 1)[1])
        save(state)
        made.append(job)
        run.say(f"submitted {display}: {len(keys)} requests")
    return made


# ── the commands ────────────────────────────────────────────────────────────


def _account() -> tuple[Any, dict[str, str], dict[str, Any]]:
    rows = batch._rows()
    row, remembered = batch.account(None, None)
    rows[row.id] = row
    batch.guard(row)
    run.say(f"account: Google Cloud project {remembered['project']}, checked against {batch.BILLING.name}")
    return row, remembered, rows


def _ledger(row: Any) -> str:
    spent, flying = batch.spent_through(row.id)
    cap = float(batch.billing()["cap"])
    return f"${spent:.2f} spent, ${flying:.2f} held for jobs in flight, cap ${cap:.2f}"


def stage(args: argparse.Namespace) -> None:
    """`run.py factcheck` or `run.py write`: one stage on its own, for the pilot."""
    kind = args.command
    groups = tuple(args.group or run.SETS["common"])
    row, remembered, rows = _account()
    state = load()
    running = collect(state, rows)
    chosen = targets(kind, state, groups, args.characters)
    running += submit(kind, chosen, row, remembered, state, args.job_size, args.dry_run)
    run.say(_ledger(row))
    if args.dry_run or args.no_wait:
        return
    while running:
        run.say(f"waiting {args.poll:.0f} s: " + ", ".join(
            f"{j['display'].split('-')[2]}-{j['display'].split('-')[3]} "
            f"{j.get('state', '?').removeprefix('JOB_STATE_').lower()}" for j in running))
        time.sleep(args.poll)
        running = collect(state, rows)
    run.say("done; " + _ledger(row))


def full(args: argparse.Namespace) -> None:
    """Everything left, as soon as it may start, under the cap; stops when nothing is left."""
    row, remembered, rows = _account()
    common = run.SETS["common"]
    takes = {group: args.takes for group in common}
    for setting in args.takes_for or []:
        group, _, count = setting.partition("=")
        if group not in takes or not count.isdigit():
            sys.exit(f"--takes-for wants GROUP=N with a group of {', '.join(common)}, not {setting!r}")
        takes[group] = int(count)
    run.say("takes: " + ", ".join(f"{g} {n}" for g, n in takes.items()))
    while True:
        try:
            text_state, picture_state = load(), batch.load()
            text_running = collect(text_state, rows)
            picture_running = batch._collect(picture_state, rows)
            made = submit("factcheck", targets("factcheck", text_state, common), row, remembered,
                          text_state, args.text_job_size, args.dry_run)
            g1_open = bool(targets("factcheck", text_state, ("g1",))) or any(
                key.startswith("factcheck|") and next(e for e in run.catalogue() if e["character"] == key.split("|")[1])["group"] == "g1"
                for key in in_flight(text_state))
            if not g1_open:
                made += submit("write", targets("write", text_state, ("g2", "g3")), row, remembered,
                               text_state, args.text_job_size, args.dry_run)
            chosen = run.prepare(argparse.Namespace(set="common", characters=None))
            pictures = []
            # One picture job at a time: Vertex serves about one and leaves the rest at 0 (README, "One
            # job at a time"), so a second only waits. The next goes out when this one has ended.
            for group in common if not picture_running else ():  # most popular first, each with its own takes
                members = [entry for entry in chosen if entry["group"] == group]
                picture_args = argparse.Namespace(redraw=False, takes=takes[group], characters=None,
                                                  budget=None, cap=None, job_size=args.job_size)
                pictures += batch.submit_pictures(
                    row, remembered, picture_args, members, picture_state,
                    run.prompts_for([entry for entry in members if entry["checked"]]),
                    dry_run=args.dry_run, max_jobs=1)
                if pictures:
                    break
            ready = [entry for entry in chosen if entry["checked"]]
            wanted = sum(takes[entry["group"]] for entry in ready)
            drawn = sum(min(len(run.drawn_pictures(entry["character"])), takes[entry["group"]]) for entry in ready)
        except ConnectionError as error:
            run.say(f"a call failed ({error}); trying again in {args.poll:.0f} s")
            time.sleep(args.poll)
            continue
        text_running += made
        picture_running += pictures
        run.say(f"in flight: {sum(len(j['requests']) for j in text_running)} Argon requests in "
                f"{len(text_running)} jobs, {sum(len(j['requests']) for j in picture_running)} pictures in "
                f"{len(picture_running)} jobs; {_ledger(row)}")
        for line in batch.progress_lines(picture_running, drawn, wanted):
            run.say(line)
        if args.dry_run:
            return
        if not text_running and not picture_running:
            break
        time.sleep(args.poll)
    print("\n".join(summary()))
    run.say("all done: nothing left to submit or in flight; " + _ledger(row))


def summary() -> list[str]:
    """Per group and stage: done, kept, corrected, dropped, failed."""
    state = load()
    groups = {e["character"]: e["group"] for e in run.catalogue()}
    table: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for key, task in state["tasks"].items():
        kind, character = key.split("|")
        table[(kind, groups[character])][task.get("verdict") or task.get("status") or "open"] += 1
    flying = Counter(k.split("|")[0] for k in in_flight(state))
    lines = ["Argon:"]
    for (kind, group), counts in sorted(table.items()):
        lines.append(f"- {kind} {group}: " + ", ".join(f"{n} {v}" for v, n in sorted(counts.items())))
    if flying:
        lines.append("- in flight: " + ", ".join(f"{n} {k}" for k, n in flying.items()))
    return lines if len(lines) > 1 else []


def main(args: argparse.Namespace) -> None:
    try:
        (full if args.command == "full" else stage)(args)
    except batch.Stop as stop:
        print(f"STOPPED: {stop}", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped here. Jobs already submitted keep running at Google; run the same command "
              "again to collect them.", flush=True)
