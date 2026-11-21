#!/usr/bin/env python3
"""Spend money: does the reworded compose prompt keep definitions in `definitionLang`?

    .venv/bin/python experiments/definition-language/run.py --providers FILE --row ID [--arm …] [--model …] [--set …]
    .venv/bin/python experiments/definition-language/report.py

The starter build found `gemini-3.5-flash-lite` writing 30-50% of its definitions in the word's own
language for vocabularies that define in English (README). This re-sends **the requests the builder
sent**, rebuilt by `compose_parts` from what each stored compose file recorded, with only the system
prompt (or the language lines) changed per arm:

- `before`: the prompt as it shipped when the failure was found (`arms/before.md`);
- `after`: the reworded prompt (`arms/after.md`);
- `named`: `after`, with the user message naming its languages (`Define senses in: English (en)`).

Two sets of words, both drawn from `data/starter/` with a fixed seed:

- `sample`: 15 words from each of seven vocabularies where 3.5 Flash-Lite wrote a definition the
  check doubts or refuses;
- `control`: 30 es-MX words re-asked with `definitionLang: es`, which must stay in Spanish.

Every reply is scored by compose's own check (`vet.definition_doubt`) per sense, and stored with the
reply under `runs/<run>/`. The provider row comes from a providers file outside the repository
(`--providers`, in `providers.local.json`'s shape), so no project or account is written here.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "starter"))

import build  # noqa: E402  the starter builder: its vocabularies, topics and request
from acervo.models import call  # noqa: E402
from acervo.models.errors import ProviderError  # noqa: E402
from acervo.models.local import load_local  # noqa: E402
from acervo.models.locales import language_name  # noqa: E402
from acervo.services.capture.compose import compose_parts  # noqa: E402
from acervo.services.capture.draft import usable_senses  # noqa: E402
from acervo.services.capture.vet import definition_doubt  # noqa: E402
from acervo.services.prompts import sections  # noqa: E402
from acervo.services.reader import reader_section  # noqa: E402

ARMS = ("before", "after", "named")
MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
SAMPLED = ("es-ES", "fr-FR", "it-IT", "pt-BR", "de-DE", "ko-KR", "ru")
PER_VOCABULARY = 15
CONTROL = ("es-MX", 30)
SEED = 20261121
WORKERS = 4
TIMEOUT = 120.0
TRIES = 4
LINE_KEYS = ("Define senses in: ", "Gloss into: ", "Write notes in: ")
TOPICS = [{"name": name} for name in build.load_vocabularies()[1].values()]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stored(vocabulary: str) -> list[dict[str, Any]]:
    folder = build.OUT / vocabulary / "compose"
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.json"))
            if not path.name.endswith(".failed.json")]


def misdefined(composed: dict[str, Any], record: dict[str, Any]) -> bool:
    resolution = composed["request"]["resolution"]
    quoted = [resolution["headword"], resolution["lemma"], composed["draft"].get("reading") or ""]
    return any(definition_doubt(sense["definition"], record, resolution, quoted)
               for sense in composed["draft"]["senses"])


def words(which: str) -> list[dict[str, Any]]:
    """The jobs' words: the stored compose file, the vocabulary record compose was told about."""
    vocabularies = {v["id"]: v for v in build.load_vocabularies()[0]}
    chosen: list[dict[str, Any]] = []
    rng = random.Random(SEED)
    if which == "sample":
        for vocabulary in SAMPLED:
            record = build.record_for(vocabularies[vocabulary])
            failing = [c for c in stored(vocabulary)
                       if c["model"].endswith("gemini-3.5-flash-lite") and misdefined(c, record)]
            for composed in rng.sample(failing, min(PER_VOCABULARY, len(failing))):
                chosen.append({"set": which, "vocabulary": vocabulary, "record": record, "composed": composed})
    else:
        vocabulary, count = CONTROL
        record = {**build.record_for(vocabularies[vocabulary]), "definitionLang": "es"}
        for composed in rng.sample(stored(vocabulary), count):
            chosen.append({"set": which, "vocabulary": vocabulary, "record": record, "composed": composed})
    return chosen


def named(user: str) -> str:
    """The `named` arm: each language line says the language's name before its code."""
    lines = []
    for line in user.split("\n"):
        key = next((k for k in LINE_KEYS if line.startswith(k)), None)
        if key:
            codes = [code.strip() for code in line[len(key):].split(",")]
            line = key + ", ".join(f"{language_name(code)} ({code})" for code in codes)
        lines.append(line)
    return "\n".join(lines)


def request_for(word: dict[str, Any], arm: str) -> tuple[str, str, Any]:
    composed, record = word["composed"], word["record"]
    request = composed["request"]
    _, user, check = compose_parts(build.APP_PROMPTS, build.DICTIONARIES, request["resolution"],
                                   request["request"], record, TOPICS)
    template = (HERE / "arms" / f"{'before' if arm == 'before' else 'after'}.md").read_text(encoding="utf-8")
    section = reader_section(record)
    body = sections(template.strip(), {}, "acervo_compose")
    system = f"{body}\n\n{section}" if section else body
    return system, (named(user) if arm == "named" else user), check


def score(reply: Any, word: dict[str, Any]) -> dict[str, Any]:
    resolution = word["composed"]["request"]["resolution"]
    if not isinstance(reply, dict):
        return {"senses": 0, "wrong": 0, "certain": 0, "doubts": ["not JSON"]}
    quoted = [resolution["headword"], resolution["lemma"], str(reply.get("reading") or "")]
    senses = usable_senses(reply)
    doubts = [definition_doubt(sense.get("definition"), word["record"], resolution, quoted) for sense in senses]
    return {"senses": len(senses), "wrong": sum(1 for d in doubts if d),
            "certain": sum(1 for d in doubts if d and d[1]), "doubts": [d[0] for d in doubts if d],
            "definitions": [sense.get("definition") for sense in senses]}


def ask(row: Any, model: str, arm: str, word: dict[str, Any], out: Path) -> dict[str, Any]:
    path = out / arm / model / f"{word['vocabulary']}--{word['composed']['word']['key']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    system, user, _ = request_for(word, arm)
    record: dict[str, Any] = {"set": word["set"], "vocabulary": word["vocabulary"], "arm": arm, "model": model,
                              "headword": word["composed"]["word"]["headword"],
                              "definitionLang": word["record"]["definitionLang"], "at": now()}
    for attempt in range(TRIES):
        try:
            result = call.text(user, row=row, model=model, system=system, as_json=True, timeout=TIMEOUT)
            break
        except ProviderError as error:
            if error.reason not in ("rate_limited", "unavailable", "unreachable") or attempt == TRIES - 1:
                record |= {"ok": False, "reason": error.reason, "detail": error.detail[:400]}
                return record
            time.sleep(10 * 2 ** attempt)
    record |= {"ok": True, "seconds": round(result.answer.seconds, 2), "costUsd": result.answer.cost_usd,
               "reply": result.parsed if result.parsed is not None else result.text,
               "score": score(result.parsed, word)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--providers", required=True, help="a providers file outside the repository")
    parser.add_argument("--row", required=True, help="the provider id in it to call")
    parser.add_argument("--arm", action="append", choices=ARMS)
    parser.add_argument("--model", action="append", choices=MODELS)
    parser.add_argument("--set", action="append", dest="sets", choices=("sample", "control"))
    parser.add_argument("--run", default="runs/1")
    parser.add_argument("--dry-run", action="store_true", help="count the jobs, call nothing")
    args = parser.parse_args(argv)

    jobs = [(model, arm, word) for which in (args.sets or ["sample"]) for word in words(which)
            for model in (args.model or [MODELS[0]]) for arm in (args.arm or list(ARMS))]
    print(f"{len(jobs)} calls on {args.row}", flush=True)
    if args.dry_run:
        return 0
    row = next(r for r in load_local(args.providers).serving("text") if r.id == args.row)
    out = HERE / args.run
    done = failed = 0
    spent = 0.0
    with ThreadPoolExecutor(WORKERS) as pool:
        for record in pool.map(lambda job: ask(row, job[0], job[1], job[2], out), jobs):
            done += 1
            failed += not record.get("ok")
            spent += record.get("costUsd") or 0.0
            if done % 25 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} answered, {failed} failed, ${spent:.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
