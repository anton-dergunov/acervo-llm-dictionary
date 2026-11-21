"""The Argon judge: list what is wrong in composed articles, for every article in the starter corpus.

    cd experiments/compose-judge
    ../../.venv/bin/python judge.py check                          # the pinned account, and nothing else
    ../../.venv/bin/python judge.py sample --name pilot --only es-ES,en-US,ru --per-vocabulary 20 --known
    ../../.venv/bin/python judge.py online --run pilot-low  --sample pilot --thinking low
    ../../.venv/bin/python judge.py online --run pilot-med  --sample pilot --thinking medium
    ../../.venv/bin/python judge.py online --run pilot-one  --sample pilot --thinking low --per-request 1
    ../../.venv/bin/python judge.py sample --name all                # every composed article
    ../../.venv/bin/python judge.py batch --run full --sample all --thinking low   # submit, wait, collect, retry
    ../../.venv/bin/python judge.py status --run full
    ../../.venv/bin/python judge.py export --run full               # → runs/full/faults.jsonl
    ../../.venv/bin/python judge.py spent

The rubric is `rubric.md` (the system instruction); a run records its digest and refuses to continue
under another. Each request carries one vocabulary's header and `--per-request` articles, rendered
compactly (`render`), each with the senses an installed dictionary gives it (`reference`). The judge
answers in JSON mode with no schema (AGENTS.md: no constrained decoding without a measurement); an
answer that does not parse, or leaves an article out, is asked again in the next round.

Every call adds its cost to `spend.jsonl`. `--max-usd` (default 100) is the cap over all runs together:
a call or a batch whose estimate would cross it is refused before anything is sent.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import yaml  # noqa: E402

from acervo.services.capture.dictionary_check import keys_for  # noqa: E402
from acervo.services.dictionaries.lookup import articles_for  # noqa: E402

CORPUS = ROOT / "data" / "starter"
VOCABULARIES = ROOT / "scripts" / "starter" / "vocabularies.yaml"
# The served dictionaries, and the ones compiled for the judge only (kaikki for the languages the
# served set lacks), kept apart so compose's own dictionary checks do not start reading them.
DICTIONARIES = (ROOT / "data" / "dictionaries" / "out", ROOT / "data" / "dictionaries" / "judge")
RUBRIC = HERE / "rubric.md"
RUNS = HERE / "runs"
SPEND = HERE / "spend.jsonl"

MODEL = "gemini-4-argon"
# USD per 1M tokens: (online in, online out, batch in, batch out); thinking is billed as output.
# Read from task-concept-retrieval/tcr/judge.py PRICES (2026-11-05): Argon's promotion ends
# 2026-11-30, after which the prices double.
PRICES = {"gemini-4-argon": (2.00, 10.00, 1.00, 5.00)}
MAX_USD = 100.0
PILOT_PREFIX = "v2-"  # the online runs under the current rubric, whose usage the batch estimate scales
REFERENCE_SENSES = 12
# Which dictionaries make a reference, best first: Wiktionary's extracts are the cleanest sense lists;
# FreeDict's are phrase lists ("zur Verfügung stellend") and come last.
ARABIC_MARKS = __import__("regex").compile(r"[\u064B-\u065F\u0670\u0640]")
FAMILIES = ("kaikki-", "jmdict-", "cc-cedict", "ecdict-", "moedict-", "wty-", "wikdict-", "freedict-")
REFERENCE_CHARS = 110

CATEGORIES = {
    "sense.missing", "sense.oversplit", "sense.marginal", "sense.wrong", "definition.unclear",
    "definition.form", "gloss.wrong", "shortgloss.mismatch", "example.unnatural", "example.wrong-sense",
    "example.missing-word", "example.translation", "note.false", "note.filler", "note.missing",
    "field.ipa", "field.gender", "field.register", "field.pos", "field.reading", "text.corrupt",
    "language.wrong",
}  # and `new:<name>`, the judge's own name for a kind of fault none of these fits

# Defects read by hand in the session that wrote this (experiments/compose-audit/README.md), which a
# judge must find: (vocabulary, headword, the category it must name).
KNOWN = [
    ("es-MX", "caro", "shortgloss.mismatch"),
    ("es-MX", "la mañana", "sense.oversplit"),
    ("es-ES", "dar", "sense.missing"),
    ("es-ES", "el museo", "note.filler"),
    ("en-US", "museum", "note.false"),
    ("de-DE", "das Dach", "sense.wrong"),
    ("de-DE", "stellen", "sense.missing"),
    ("pl-PL", "kupować", "example.unnatural"),
    ("tr-TR", "bakmak", "field.ipa"),
    ("tr-TR", "uyumak", "sense.marginal"),
    ("zh-CN", "吃", "shortgloss.mismatch"),
    ("ru", "брать", "sense.missing"),
]

WRITING = threading.Lock()


# ── the corpus ──────────────────────────────────────────────────────────────


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def vocabularies() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(VOCABULARIES.read_text(encoding="utf-8"))
    return {v["id"]: {**data["defaults"], **v} for v in data["vocabularies"]}


def composed(vocabulary: str, key: str) -> dict[str, Any]:
    return json.loads((CORPUS / vocabulary / "compose" / f"{key}.json").read_text(encoding="utf-8"))


def ident(vocabulary: str, key: str) -> str:
    """An article's id across the corpus: a word key repeats between vocabularies (`dar-verb-…` is
    Spanish and Portuguese), so a result is always filed under its vocabulary too."""
    return f"{vocabulary}/{key}"


def every_article(only: set[str] | None = None) -> list[tuple[str, str]]:
    items = []
    for path in sorted(CORPUS.glob("*/compose/*.json")):
        if path.name.endswith(".failed.json"):
            continue
        vocabulary = path.parent.parent.name
        if only and vocabulary not in only:
            continue
        items.append((vocabulary, path.stem))
    return items


# ── what the judge reads ────────────────────────────────────────────────────


def reference(draft: dict[str, Any]) -> tuple[str, list[str], int] | None:
    """The best installed dictionary's senses for the word (`FAMILIES`), in English where one exists:
    (dictionary id, the first `REFERENCE_SENSES` distinct definitions, how many it has)."""
    keys = keys_for(draft["headword"], draft.get("lemma") or "")
    # Wiktionary files Arabic under the unvowelled spelling; compose writes it fully vowelled.
    keys += [bare for key in keys if (bare := ARABIC_MARKS.sub("", key)) != key]
    found = [item for directory in DICTIONARIES if directory.is_dir()
             for item in articles_for(directory, draft["language"], keys)]
    best = None
    for item in found:
        articles = [a for a in item.articles if a.get("pos") == draft["pos"]] or item.articles
        senses = list(dict.fromkeys(
            " ".join(str(s.get("definition") or "").split())
            for a in articles for s in a.get("senses") or [] if s.get("definition")))
        if not senses:
            continue
        english = all(a.get("definitionLang") == "en" for a in articles)
        family = next((n for n, prefix in enumerate(FAMILIES) if item.dictionary_id.startswith(prefix)), len(FAMILIES))
        rank = (english, -family, len(senses))
        if best is None or rank > best[0]:
            best = (rank, item.dictionary_id, senses)
    if best is None:
        return None
    _, dictionary_id, senses = best
    clipped = [s if len(s) <= REFERENCE_CHARS else s[: REFERENCE_CHARS - 1] + "…" for s in senses[:REFERENCE_SENSES]]
    return dictionary_id, clipped, len(senses)


def _or_dash(value: Any) -> str:
    return str(value) if value not in (None, "") else "–"


def render(item: dict[str, Any]) -> str:
    """One article as the judge reads it: every field it judges, and nothing it does not."""
    draft = item["draft"]
    lines = [f"### key: {ident(item['vocabulary'], item['word']['key'])}",
             f"headword: {draft['headword']} | lemma: {_or_dash(draft.get('lemma'))} | pos: {draft['pos']} | "
             f"gender: {_or_dash(draft.get('gender'))} | register: {_or_dash(draft.get('register'))} | "
             f"ipa: {_or_dash(draft.get('ipa'))} | reading: {_or_dash(draft.get('reading'))}",
             f"shortGloss: {_or_dash(draft.get('shortGloss'))} | primaryGloss: {_or_dash(draft.get('primaryGloss'))}"]
    notes = draft.get("notes") or []
    lines.append("notes:" + ("" if notes else " –"))
    lines += [f"  [{i}] {note}" for i, note in enumerate(notes)]
    lines.append("senses:")
    for i, sense in enumerate(draft["senses"]):
        glosses = "; ".join(f"{g['lang']}: {', '.join(g['terms'])}" for g in sense.get("glosses") or [])
        lines.append(f"  [{i}] ({_or_dash(sense.get('domain'))}) {sense['definition']} | glosses {glosses}")
        for j, example in enumerate(sense.get("examples") or []):
            lines.append(f"      example[{j}]: {example['text']} — {_or_dash(example.get('translation'))}")
            if example.get("note"):
                lines.append(f"      example[{j}] note: {example['note']}")
    ref = reference(draft)
    if ref:
        dictionary_id, senses, total = ref
        shown = f", first {len(senses)}" if total > len(senses) else ""
        lines.append(f"dictionary hint — NOT part of the entry, never shown to the learner, noisy "
                     f"({dictionary_id}, {total} senses{shown}): " + " / ".join(senses))
    return "\n".join(lines)


def header(vocabulary: dict[str, Any]) -> str:
    from acervo.models.locales import language_name
    glosses = ", ".join(language_name(g) for g in vocabulary["glossLangs"])
    return (f"Words in {language_name(vocabulary['language'])} ({vocabulary['language']}), "
            f"{vocabulary.get('variety') or 'the standard language'}; learner level {vocabulary.get('level', 'A2')}. "
            f"Definitions are written in {language_name(vocabulary['definitionLang'])}, glosses in {glosses}, "
            f"notes in {language_name(vocabulary['notesLang'])}; example translations in "
            f"{language_name(vocabulary['glossLangs'][0])}.")


def requests_for(sample: list[tuple[str, str]], per_request: int) -> list[dict[str, Any]]:
    """The sample in requests of up to `per_request` articles, one vocabulary each."""
    known = vocabularies()
    by_vocabulary: dict[str, list[str]] = {}
    for vocabulary, key in sample:
        by_vocabulary.setdefault(vocabulary, []).append(key)
    requests = []
    for vocabulary, keys in by_vocabulary.items():
        for start in range(0, len(keys), per_request):
            chunk = keys[start: start + per_request]
            request_id = f"{vocabulary}:{chunk[0]}:{len(chunk)}"
            body = "\n\n".join(render(composed(vocabulary, key)) for key in chunk)
            user = f"Request: {request_id}\n{header(known[vocabulary])}\n\n{body}"
            requests.append({"id": request_id, "vocabulary": vocabulary, "keys": [ident(vocabulary, k) for k in chunk],
                             "user": user})
    return requests


# ── what the judge answers ──────────────────────────────────────────────────


def read_answer(text: str, keys: list[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Per key, its faults and corrected entry (or `None`); and the keys the answer left out or got
    wrong, which are asked again."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}, list(keys)
    entries = parsed.get("entries") if isinstance(parsed, dict) else None
    if not isinstance(entries, list):
        return {}, list(keys)
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("key") not in keys or not isinstance(entry.get("faults"), list):
            continue
        corrected = entry.get("corrected")
        if corrected is not None and not (isinstance(corrected, dict) and isinstance(corrected.get("senses"), list)):
            continue  # a correction in no usable shape: asked again
        faults = []
        for fault in entry["faults"]:
            if not isinstance(fault, dict):
                continue
            category = str(fault.get("category") or "")
            if category not in CATEGORIES and not category.startswith("new:"):
                fault = {**fault, "category": f"new:{category or 'unnamed'}"}
            faults.append(fault)
        out[entry["key"]] = {"faults": faults, "corrected": corrected}
    return out, [key for key in keys if key not in out]


# ── spend ───────────────────────────────────────────────────────────────────


def usd(usage: dict[str, int], batch: bool) -> float:
    price = PRICES[MODEL]
    inp, out = (price[2], price[3]) if batch else (price[0], price[1])
    return (usage.get("prompt", 0) * inp + (usage.get("output", 0) + usage.get("thoughts", 0)) * out) / 1e6


def spent() -> float:
    if not SPEND.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in SPEND.read_text().splitlines() if line.strip())


def record_spend(run: str, what: str, usage: dict[str, int], batch: bool) -> float:
    cost = usd(usage, batch)
    with WRITING, SPEND.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now(), "run": run, "what": what, "model": MODEL, "batch": batch,
                                 "usd": round(cost, 6), **usage}) + "\n")
    return cost


def refuse_over(cap: float, estimate: float, what: str) -> None:
    so_far = spent()
    if so_far + estimate > cap:
        raise SystemExit(f"refused: {what} is estimated at ${estimate:.2f}; with ${so_far:.2f} spent that "
                         f"crosses the ${cap:.2f} cap (--max-usd). Nothing was sent.")


# ── runs ────────────────────────────────────────────────────────────────────


def run_dir(name: str) -> Path:
    return RUNS / name


def manifest(name: str, **fields: Any) -> dict[str, Any]:
    """The run's settings, written once; a later call under another rubric or setting is refused."""
    path = run_dir(name) / "manifest.json"
    wanted = {"model": MODEL, "rubric": digest(RUBRIC.read_text(encoding="utf-8")), **fields}
    if path.exists():
        held = json.loads(path.read_text())
        differs = {k: (held.get(k), v) for k, v in wanted.items() if held.get(k) != v}
        if differs:
            raise SystemExit(f"run {name} was started with other settings: {differs}. Start another run.")
        return held
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**wanted, "started": now()}, indent=1))
    return wanted


def done_keys(name: str) -> dict[str, dict[str, Any]]:
    """Per judged key: `{"faults": [...], "corrected": {...} or None}`."""
    path = run_dir(name) / "results.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_faults(name: str, results: dict[str, dict[str, Any]]) -> None:
    path = run_dir(name) / "results.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1))


def load_sample(name: str) -> list[tuple[str, str]]:
    return [tuple(item) for item in json.loads((RUNS / "samples" / f"{name}.json").read_text())]


def cmd_sample(args: argparse.Namespace) -> int:
    only = set(args.only.split(",")) if args.only else None
    items = every_article(only)
    if args.per_vocabulary:
        rng = random.Random(args.seed)
        chosen = []
        for vocabulary in sorted({v for v, _ in items}):
            keys = [k for v, k in items if v == vocabulary]
            chosen += [(vocabulary, k) for k in rng.sample(keys, min(args.per_vocabulary, len(keys)))]
        items = chosen
    if args.known:
        by_headword = {}
        for path in sorted(CORPUS.glob("*/compose/*.json")):
            if not path.name.endswith(".failed.json"):
                item = json.loads(path.read_text(encoding="utf-8"))
                by_headword[(item["vocabulary"], item["draft"]["headword"])] = item["word"]["key"]
        for vocabulary, headword, _ in KNOWN:
            key = by_headword.get((vocabulary, headword))
            if key is None:
                print(f"known defect {vocabulary} {headword}: not in the corpus (recomposed?)")
            elif (vocabulary, key) not in items:
                items.append((vocabulary, key))
    path = RUNS / "samples" / f"{args.name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(items), ensure_ascii=False, indent=0))
    print(f"sample {args.name}: {len(items)} articles in {len({v for v, _ in items})} vocabularies → {path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    import gcp
    pin = gcp.verify()
    print(f"account   : the pinned one (tokeninfo agrees)\nproject   : {pin.project} (number {pin.number})\n"
          f"gcloud    : {pin.gcloud_config}\nbucket    : gs://{pin.bucket}\nspent     : ${spent():.2f} of ${MAX_USD:.0f}")
    return 0


def _online_call(system: str, user: str, thinking: str | None) -> tuple[str, dict[str, int]]:
    from google.genai import types
    import vertex_batch
    config = types.GenerateContentConfig(
        system_instruction=system, temperature=1.0, response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_level=thinking.upper()) if thinking else None)
    response = vertex_batch.client().models.generate_content(model=MODEL, contents=user, config=config)
    meta = response.usage_metadata
    usage = {"prompt": meta.prompt_token_count or 0, "output": meta.candidates_token_count or 0,
             "thoughts": meta.thoughts_token_count or 0, "cached": meta.cached_content_token_count or 0}
    return response.text or "", usage


def cmd_online(args: argparse.Namespace) -> int:
    """Single calls, for the pilot: each request's reply is kept, so a rerun asks only what is missing."""
    import gcp
    gcp.verify()
    manifest(args.run, sample=args.sample, thinking=args.thinking, perRequest=args.per_request, mode="online")
    system = RUBRIC.read_text(encoding="utf-8")
    faults = done_keys(args.run)
    todo = [(v, k) for v, k in load_sample(args.sample) if ident(v, k) not in faults]
    requests = requests_for(todo, args.per_request)
    # A rough ceiling before anything is sent: 2,500 output tokens an article is above a full rewrite.
    ceiling = sum(usd({"prompt": len(r["user"]) // 2 + 2500, "output": 2500 * len(r["keys"])}, False) for r in requests)
    refuse_over(args.max_usd, ceiling, f"{len(requests)} online calls")
    replies = run_dir(args.run) / "replies.jsonl"
    print(f"{args.run}: {len(requests)} requests, {len(todo)} articles; ceiling ${ceiling:.2f}")

    def one(request: dict[str, Any]) -> None:
        for attempt in range(3):
            try:
                started = time.monotonic()
                text, usage = _online_call(system, request["user"], args.thinking)
                break
            except Exception as error:  # noqa: BLE001 — 429/503 and the like; try again, then give up
                print(f"  {request['id']}: {type(error).__name__}: {str(error)[:160]}", flush=True)
                time.sleep(10 * (attempt + 1))
        else:
            return
        cost = record_spend(args.run, request["id"], usage, batch=False)
        got, missing = read_answer(text, request["keys"])
        with WRITING:
            with replies.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"id": request["id"], "keys": request["keys"], "text": text, "usage": usage,
                                         "seconds": round(time.monotonic() - started, 1), "usd": round(cost, 6)},
                                        ensure_ascii=False) + "\n")
            faults.update(got)
            save_faults(args.run, faults)
        print(f"  {request['id']}: {sum(len(f['faults']) for f in got.values())} faults, "
              f"{sum(1 for f in got.values() if f['corrected'])} corrected, in {len(got)} articles"
              f"{f', {len(missing)} left out' if missing else ''}; {usage['thoughts']} thinking; ${cost:.4f}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, requests))
    print(f"{args.run}: {len(faults)} articles judged; spent so far ${spent():.2f}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Rounds of batch jobs until every article is judged or `--rounds` is reached; resumable."""
    import gcp
    import vertex_batch
    gcp.verify()
    manifest(args.run, sample=args.sample, thinking=args.thinking, perRequest=args.per_request, mode="batch")
    system = RUBRIC.read_text(encoding="utf-8")
    sample = load_sample(args.sample)
    for number in range(1, args.rounds + 1):
        round_ = vertex_batch.Run(run_dir(args.run) / f"r{number}", MODEL)
        state = round_.state()
        faults = done_keys(args.run)
        if state.get("collected"):
            continue
        if not state.get("job"):
            todo = [(v, k) for v, k in sample if ident(v, k) not in faults]
            if not todo:
                break
            requests = requests_for(todo, args.per_request)
            with round_.input.open("w", encoding="utf-8") as handle:
                for request in requests:
                    handle.write(json.dumps({"request": vertex_batch.request_json(system, request["user"], args.thinking)},
                                            ensure_ascii=False) + "\n")
            (round_.dir / "requests.json").write_text(json.dumps(
                {r["id"]: r["keys"] for r in requests}, ensure_ascii=False))
            estimate = estimate_batch(args.run, requests)
            refuse_over(args.max_usd, estimate, f"round {number} of {args.run} ({len(requests)} requests)")
            print(f"round {number}: {len(requests)} requests, {len(todo)} articles, estimated ${estimate:.2f}")
            round_.submit(f"compose-judge {args.run} r{number}")
        if args.submit_only:
            print(f"round {number} submitted; run the same command without --submit-only to wait and collect")
            return 0
        job = round_.wait(args.poll)
        if not str(job.state).endswith("SUCCEEDED") and not str(job.state).endswith("PARTIALLY_SUCCEEDED"):
            raise SystemExit(f"round {number} ended {job.state}; see `status`")
        keys_of = json.loads((round_.dir / "requests.json").read_text())
        got_total, missing_total, cost_total = 0, 0, 0.0
        with (round_.dir / "replies.jsonl").open("w", encoding="utf-8") as replies:
            for record in round_.download():
                user = record["request"]["contents"][0]["parts"][0]["text"]
                request_id = user.split("\n", 1)[0].removeprefix("Request: ").strip()
                keys = keys_of.get(request_id, [])
                response = record.get("response")
                if not response or not response.get("candidates"):
                    missing_total += len(keys)
                    continue
                usage = vertex_batch.usage_of(response)
                cost_total += record_spend(args.run, request_id, usage, batch=True)
                text = vertex_batch.response_text(response)
                got, missing = read_answer(text, keys)
                faults.update(got)
                got_total += len(got)
                missing_total += len(missing)
                replies.write(json.dumps({"id": request_id, "keys": keys, "text": text, "usage": usage},
                                         ensure_ascii=False) + "\n")
        save_faults(args.run, faults)
        round_.save_state({**round_.state(), "collected": now(), "usd": round(cost_total, 4)})
        print(f"round {number}: {got_total} articles judged, {missing_total} to ask again; ${cost_total:.2f}")
    print(f"{args.run}: {len(done_keys(args.run))} of {len(sample)} articles judged; spent so far ${spent():.2f}")
    return 0


def estimate_batch(run: str, requests: list[dict[str, Any]]) -> float:
    """Input tokens by Google's free count over a few requests, scaled; output tokens per article from
    the pilot's measured usage when one is recorded, else a generous 1,200."""
    import vertex_batch
    probe = requests[:: max(1, len(requests) // 8)][:8]
    system = RUBRIC.read_text(encoding="utf-8")
    counted = [vertex_batch.client().models.count_tokens(model=MODEL, contents=system + "\n\n" + r["user"]).total_tokens
               for r in probe]
    per_char = sum(counted) / sum(len(system) + len(r["user"]) for r in probe)
    prompt = sum((len(system) + len(r["user"])) * per_char for r in requests)
    articles = sum(len(r["keys"]) for r in requests)
    out_per_article = 2000.0
    if SPEND.exists():
        lines = [json.loads(l) for l in SPEND.read_text().splitlines() if l.strip()]
        pilot = [l for l in lines if not l["batch"] and l["run"].startswith(PILOT_PREFIX)]
        if pilot:
            judged = sum(int(l["what"].rsplit(":", 1)[-1]) for l in pilot)
            out_per_article = sum(l["output"] + l["thoughts"] for l in pilot) / max(1, judged) * 1.3
    return usd({"prompt": int(prompt), "output": int(out_per_article * articles)}, batch=True)


def cmd_status(args: argparse.Namespace) -> int:
    import vertex_batch
    folder = run_dir(args.run)
    for path in sorted(folder.glob("r*/state.json")):
        state = json.loads(path.read_text())
        line = f"{path.parent.name}: {state.get('job', 'not submitted')}"
        if state.get("collected"):
            line += f", collected {state['collected']} (${state.get('usd', 0):.2f})"
        elif state.get("job"):
            line += f", {vertex_batch.describe_job(vertex_batch.Run(path.parent, MODEL).job())}"
        print(line)
    print(f"judged: {len(done_keys(args.run))} articles; spent in all: ${spent():.2f}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """One line per article judged, its faults inline: the input to report.py."""
    results = done_keys(args.run)
    out = run_dir(args.run) / "faults.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for path in sorted(CORPUS.glob("*/compose/*.json")):
            article = ident(path.parent.parent.name, path.stem)
            if article not in results:
                continue
            item = json.loads(path.read_text(encoding="utf-8"))
            result = results[article]
            handle.write(json.dumps({
                "vocabulary": item["vocabulary"], "key": path.stem, "id": article, "headword": item["draft"]["headword"],
                "pos": item["draft"]["pos"], "composer": item["model"].split(":")[-1],
                "senses": len(item["draft"]["senses"]), "corrected": result["corrected"] is not None,
                "faults": result["faults"]}, ensure_ascii=False) + "\n")
    print(f"{out}: {sum(len(r['faults']) for r in results.values())} faults over {len(results)} articles")
    return 0


def cmd_spent(args: argparse.Namespace) -> int:
    print(f"${spent():.2f} of the ${MAX_USD:.0f} cap")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Print one request exactly as the judge would read it."""
    sample = load_sample(args.sample)
    print(RUBRIC.read_text(encoding="utf-8") if args.rubric else "")
    print(requests_for(sample[: args.per_request], args.per_request)[0]["user"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    commands.add_parser("spent")
    sampling = commands.add_parser("sample")
    sampling.add_argument("--name", required=True)
    sampling.add_argument("--only")
    sampling.add_argument("--per-vocabulary", type=int)
    sampling.add_argument("--seed", type=int, default=1)
    sampling.add_argument("--known", action="store_true", help="add the hand-read defects (KNOWN)")
    for name in ("online", "batch"):
        running = commands.add_parser(name)
        running.add_argument("--run", required=True)
        running.add_argument("--sample", required=True)
        # Argon does not think at low or medium (no thinking tokens; experiments/compose-judge/README.md).
        running.add_argument("--thinking", choices=["low", "medium", "high"], default="medium")
        running.add_argument("--per-request", type=int, default=5)
        running.add_argument("--max-usd", type=float, default=MAX_USD)
        if name == "online":
            running.add_argument("--workers", type=int, default=4)
        else:
            running.add_argument("--rounds", type=int, default=3)
            running.add_argument("--poll", type=int, default=120)
            running.add_argument("--submit-only", action="store_true", help="submit the next round and return")
    for name in ("status", "export"):
        commands.add_parser(name).add_argument("--run", required=True)
    showing = commands.add_parser("show")
    showing.add_argument("--sample", required=True)
    showing.add_argument("--per-request", type=int, default=2)
    showing.add_argument("--rubric", action="store_true")
    args = parser.parse_args(argv)
    return {"check": cmd_check, "sample": cmd_sample, "online": cmd_online, "batch": cmd_batch,
            "status": cmd_status, "export": cmd_export, "spent": cmd_spent, "show": cmd_show}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
