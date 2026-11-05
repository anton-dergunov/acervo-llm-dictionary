"""Ask the model one chat turn per case, and score the answer end to end.

An **arm** is a prompt and the server code that renders the request and shapes the answer, named in
`arms/<arm>.json`:

    {"prompt": "git:c46759f:prompts/acervo_chat.md", "code": "git:c46759f"}   # as shipped
    {"prompt": "arms/r1.md", "code": "worktree"}                                 # a candidate

`code` decides which `services/chat.py` builds the user turn (`_subject`, `_user_turn`) and shapes the
answer (`_shaped`). A git revision is loaded from git rather than from the working tree, so changing
the shipped code later cannot quietly change what the baseline measured. The device half is the
bundled `checker.ts` built from the same code (`build/checker-<code>.mjs`), so an answer meets the
`applyOps` that would actually have met it.

**One pair, called directly**, never through `chain.walk`: a fall-through would attribute one
model's answer to another, which is the comparison destroyed (`experiments/clip-translation/`).
The pair is the one production answered with.

Jobs run **repeat-major**, so a run that stops half way has every case equally sampled.

    .venv/bin/python experiments/chat-edits/run.py --arm before --split replay --repeats 3 --dry-run
    .venv/bin/python experiments/chat-edits/run.py --arm before --split replay --repeats 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import types
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import dataset

from acervo.models.local import load_local
from acervo.models import call
from acervo.models.errors import ProviderError, ProviderUnavailable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = HERE / "runs"
ARMS = HERE / "arms"
BUILD = HERE / "build"
WEB = ROOT / "web"

PROVIDER = "gemini-api"
MODEL = "gemini-3.5-flash-lite"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_show(revision: str, path: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{revision}:{path}"],
                          check=True, capture_output=True, text=True).stdout


# ── an arm ─────────────────────────────────────────────────────────────────────

class Arm:
    def __init__(self, name: str):
        spec = json.loads((ARMS / f"{name}.json").read_text(encoding="utf-8"))
        self.name = name
        self.spec = spec
        prompt = spec["prompt"]
        if prompt.startswith("git:"):
            _, revision, path = prompt.split(":", 2)
            self.prompt = git_show(revision, path)
        else:
            self.prompt = (HERE / prompt).read_text(encoding="utf-8")
        self.code = spec["code"]
        if self.code == "worktree":
            from acervo.services import chat as module
            self.chat = module
            self.checker = BUILD / "checker-worktree.mjs"
            bundle(self.checker)
        else:
            revision = self.code.removeprefix("git:")
            source = git_show(revision, "src/acervo/services/chat.py")
            module = types.ModuleType(f"chat_{revision}")
            module.__file__ = f"<git {revision}>/src/acervo/services/chat.py"
            # `from __future__ import annotations` + dataclass-free code: executing it in a fresh
            # module is enough, and its own imports resolve against the installed package.
            exec(compile(source, module.__file__, "exec"), module.__dict__)
            self.chat = module
            self.checker = BUILD / f"checker-{revision}.mjs"
            if not self.checker.exists():
                raise SystemExit(f"{self.checker} is missing: bundle it from a checkout of {revision}")

    def manifest(self) -> dict[str, Any]:
        return {**self.spec, "promptSha256": digest(self.prompt), "promptChars": len(self.prompt),
                "checkerSha256": digest(self.checker.read_text(encoding="utf-8"))}


def bundle(target: Path) -> None:
    """Bundle `checker.ts` against the working tree's `web/src`, with the bundler vite installs."""
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["npx", "rolldown", str(HERE / "checker.ts"), "-o", str(target), "-f", "esm",
                    "-p", "node"], cwd=WEB, check=True, capture_output=True)


class Checker:
    """`checker.ts` as a long-running process: one JSON line in, one JSON line out."""

    def __init__(self, path: Path):
        self.process = subprocess.Popen(["node", str(path)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, encoding="utf-8")

    def ask(self, request: dict[str, Any]) -> dict[str, Any]:
        assert self.process.stdin and self.process.stdout
        self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        self.process.wait(timeout=10)


# ── one turn ──────────────────────────────────────────────────────────────────

def document_for(case: dataset.Case, checker: "Checker | None" = None) -> str:
    """The document as this arm's `yaml.ts` would write it: the stored file, with today's header.

    Only the two header comment lines can differ — the body is the same record either way — so an
    arm on the shipped code sends the file exactly, and an arm on the working tree sends the header
    its own `yamlForDraft` writes for it.
    """
    text = case.text()
    if checker is None:
        return text
    header = checker.ask({"document": text, "header": True}).get("header")
    if not header:
        return text
    lines = text.split("\n")
    return "\n".join([*header.split("\n"), *lines[2:]])


def body_for(case: dataset.Case, document: str | None = None,
             repair: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The request `App.askAboutDraft` sends from the Add view: no neighbours, no reference."""
    body: dict[str, Any] = {
        "subject": {"kind": "article", "lexemeId": "", "focus": case.focus,
                    "document": document if document is not None else case.text()},
        "neighbours": [], "reference": None, "referenceSources": [],
        "turns": list(case.turns),
    }
    if repair is not None:
        body["repair"] = dict(repair)
    return body


def row_for_pair():
    catalogue = load_local()
    for row in catalogue.serving("text"):
        if row.id == PROVIDER:
            return row
    raise SystemExit(f"no text row {PROVIDER} in the catalogue")


def call_model(arm: Arm, body: dict[str, Any], row, attempts: int = 4) -> dict[str, Any]:
    subject = arm.chat._subject(body)
    user = arm.chat._user_turn(subject, body)
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result = call.text(user, row=row, model=MODEL, system=arm.prompt, as_json=True,
                               timeout=call.TIMEOUT_SECONDS)
        except ProviderUnavailable as unavailable:
            if unavailable.reason in ("rate_limited", "unavailable", "timeout") and attempt < attempts:
                time.sleep(min(15.0 * 2 ** (attempt - 1), 120.0))
                continue
            return {"status": "error", "reason": unavailable.reason, "detail": str(unavailable),
                    "user": user, "seconds": round(time.perf_counter() - started, 2)}
        except ProviderError as error:
            return {"status": "error", "reason": getattr(error, "reason", "refused"),
                    "detail": str(error), "user": user,
                    "seconds": round(time.perf_counter() - started, 2)}
        return {"status": "ok", "user": user, "raw": result.text, "parsed": result.parsed,
                "seconds": round(result.answer.seconds, 2), "model": result.answer.model}
    raise AssertionError("unreachable")


def shape(arm: Arm, parsed: Any, body: dict[str, Any]) -> dict[str, Any]:
    """The server half: `_shaped`, plus *why* a proposal was dropped, which it does not say."""
    subject = arm.chat._subject(body)
    if not isinstance(parsed, Mapping):
        return {"usable": False, "why": "not a JSON object"}
    try:
        shaped = arm.chat._shaped(parsed, subject, MODEL)
    except Exception as refused:  # noqa: BLE001 — `ApiError`, from whichever revision is loaded
        return {"usable": False, "why": str(refused)}
    raw = parsed.get("proposal")
    dropped = None
    if shaped.get("proposalProblem") and shaped.get("rejected") is not None:
        # Newer code says why itself.
        dropped = shaped["proposalProblem"]
    elif "proposalProblem" in shaped:
        pass
    elif isinstance(raw, Mapping) and shaped.get("proposal") is None:
        ops = raw.get("ops")
        if not isinstance(ops, list) or not ops:
            dropped = "proposal carries no list of ops"
        elif len(ops) > arm.chat.OP_LIMIT:
            dropped = f"{len(ops)} ops, over the limit"
        else:
            bad = [index for index, op in enumerate(ops) if arm.chat._op(op) is None]
            dropped = f"op {bad} malformed: {json.dumps([ops[i] for i in bad], ensure_ascii=False)[:600]}"
    return {"usable": True, "shaped": shaped, "dropped": dropped}


def apply(checker: Checker, case: dataset.Case, ops: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not ops:
        return {"status": "none"}
    before = checker.ask({"document": case.text()})
    glosses = [group.get("lang") for item in before["draft"]["senses"] for group in item.get("glosses") or []]
    return checker.ask({"document": case.text(), "ops": ops, "modelId": MODEL,
                        "glossLang": glosses[0] if glosses else None})


def judge(case: dataset.Case, checker: Checker, shaped: dict[str, Any],
          applied: dict[str, Any]) -> dict[str, Any]:
    """Did the turn get what it asked for? One verdict, and the reason when it did not."""
    if not shaped.get("usable"):
        return {"pass": False, "failure": "unusable", "why": shaped.get("why")}
    proposal = shaped["shaped"].get("proposal")
    if shaped.get("dropped"):
        failure = {"pass": False, "failure": "dropped", "why": shaped["dropped"]}
        return failure if case.expect != "answer" else {**failure, "failure": "dropped-on-question"}
    if proposal is None:
        if case.expect == "edit":
            return {"pass": False, "failure": "no-proposal", "why": "the turn asked for a change"}
        return {"pass": True}
    if case.expect == "answer":
        return {"pass": False, "failure": "proposed-on-question",
                "why": json.dumps(proposal["ops"], ensure_ascii=False)[:400]}
    if applied["status"] == "refused":
        if case.refusal_ok:
            return {"pass": True, "minor": [f"refused: {applied['sentence']}"]}
        return {"pass": False, "failure": "refused", "why": applied["sentence"]}
    if applied["status"] == "threw":
        return {"pass": False, "failure": "threw", "why": applied["sentence"]}
    if applied["status"] != "applied":
        return {"pass": False, "failure": applied["status"], "why": applied.get("sentence")}
    if case.check is None:
        return {"pass": True}
    before = checker.ask({"document": case.text()})["draft"]
    verdict = case.check(dataset.Outcome(before, applied["draft"], proposal["ops"]))
    if verdict.problems:
        return {"pass": False, "failure": "wrong-edit", "why": "; ".join(verdict.problems),
                "minor": verdict.minor}
    return {"pass": True, "minor": verdict.minor}


# ── the device's repair ───────────────────────────────────────────────────────

def problem_of(shaped: dict[str, Any], applied: dict[str, Any]) -> tuple[str | None, Any]:
    """What the device would send back, and the proposal it would send it with — or nothing.

    Only what the device can *see*: a proposal the server reports it could not use, or one `applyOps`
    refuses. A proposal that applies but does the wrong thing looks, to the device, like success.
    """
    answer = shaped.get("shaped") or {}
    if answer.get("proposalProblem"):
        return answer["proposalProblem"], answer.get("rejected")
    if answer.get("proposal") and applied.get("status") in ("refused", "threw"):
        return applied["sentence"], answer["proposal"]
    return None, None


def repair_loop(limit: int, arm: Arm, checker: Checker, case: dataset.Case, body: dict[str, Any],
                row, shaped: dict[str, Any], applied: dict[str, Any],
                verdict: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for attempt in range(1, limit + 1):
        problem, previous = problem_of(shaped, applied)
        if problem is None:
            break
        sent = {**body, "repair": {"problem": problem, "attempt": attempt, "previous": previous}}
        answer = call_model(arm, sent, row)
        if answer["status"] != "ok":
            steps.append({"attempt": attempt, "problem": problem, "status": answer["status"],
                          "verdict": {"pass": False, "failure": answer["status"]}})
            break
        shaped = shape(arm, answer["parsed"], sent)
        proposal = (shaped.get("shaped") or {}).get("proposal")
        applied = apply(checker, case, proposal["ops"] if proposal else None)
        verdict = judge(case, checker, shaped, applied)
        steps.append({"attempt": attempt, "problem": problem, "raw": answer["raw"],
                      "parsed": answer["parsed"], "seconds": answer["seconds"],
                      "applied": {k: v for k, v in applied.items() if k not in ("draft", "yaml")},
                      "verdict": verdict})
    return steps, verdict


def repair_stored(path: Path, arm: Arm, checker: Checker, case: dataset.Case, row, limit: int) -> int:
    """Run the device's repair on a stored first answer that the current code would send back.

    For a fix made after the run: the first answer is the same call it was, judged again by the
    code as it is now, and only an answer that code would send back costs anything.
    """
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("repairs"):
        return 0
    body = body_for(case, document_for(case, checker if arm.code == "worktree" else None))
    shaped = shape(arm, record["parsed"], body)
    proposal = (shaped.get("shaped") or {}).get("proposal")
    applied = apply(checker, case, proposal["ops"] if proposal else None)
    verdict = judge(case, checker, shaped, applied)
    if problem_of(shaped, applied)[0] is None:
        return 0
    record["repairs"], record["final"] = repair_loop(limit, arm, checker, case, body, row, shaped,
                                                     applied, verdict)
    write(path, record)
    for step in record["repairs"]:
        print(f"  {case.id} r{record['repeat']} repair {step['attempt']}: {step['problem'][:100]} → "
              f"{'PASS' if step['verdict']['pass'] else step['verdict'].get('failure')}")
    return len(record["repairs"])


# ── the run ───────────────────────────────────────────────────────────────────

def write(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", dest="arms", required=True)
    parser.add_argument("--split", action="append", dest="splits", help="replay, dev, held; repeatable")
    parser.add_argument("--case", action="append", dest="cases", help="repeatable")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--first-repeat", type=int, default=1,
                        help="number the repeats from here, to extend a run without overwriting it")
    parser.add_argument("--run", help="an existing run id, to resume or extend")
    parser.add_argument("--max-calls", type=int, default=60, help="stop after this many model calls")
    parser.add_argument("--repair-existing", action="store_true",
                        help="run the repairs on stored answers the current code would send back")
    parser.add_argument("--repairs", type=int, default=0,
                        help="send a turn back this many times when the device would (at most 2)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cases = [case for case in dataset.CASES
             if (not args.splits or case.split in args.splits)
             and (not args.cases or case.id in args.cases)]
    repeats = range(args.first_repeat, args.first_repeat + args.repeats)
    matrix = [(repeat, arm, case) for repeat in repeats for arm in args.arms for case in cases]
    print(f"{len(matrix)} calls: {len(cases)} cases × {len(args.arms)} arm(s) × {args.repeats} repeat(s)"
          f" on {PROVIDER}:{MODEL}")
    if args.dry_run:
        for repeat, arm, case in matrix:
            print(f"  r{repeat} {arm:8s} {case.id}")
        return 0
    if len(matrix) > args.max_calls:
        print(f"refusing: {len(matrix)} calls is over --max-calls {args.max_calls}", file=sys.stderr)
        return 2

    run_id = args.run or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / run_id
    arms = {name: Arm(name) for name in args.arms}
    checkers = {name: Checker(arm.checker) for name, arm in arms.items()}
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "runId": run_id, "started": datetime.now(timezone.utc).isoformat(),
        "provider": PROVIDER, "model": MODEL, "arms": {}}
    for name, arm in arms.items():
        manifest["arms"][name] = arm.manifest()
    write(manifest_path, manifest)

    row = row_for_pair()
    calls = 0
    try:
        for repeat, name, case in matrix:
            path = run_dir / name / f"{case.id}--r{repeat}.json"
            if path.exists() and json.loads(path.read_text()).get("status") == "ok":
                if args.repair_existing and args.repairs:
                    calls += repair_stored(path, arms[name], checkers[name], case, row, args.repairs)
                continue
            arm, checker = arms[name], checkers[name]
            body = body_for(case, document_for(case, checker if arm.code == "worktree" else None))
            answer = call_model(arm, body, row)
            calls += 1
            # The rendered request is the same on every repeat, so it is written once per arm and
            # case rather than into every record.
            request_path = run_dir / name / "requests" / f"{case.id}.txt"
            if not request_path.exists() and answer.get("user"):
                request_path.parent.mkdir(parents=True, exist_ok=True)
                request_path.write_text(answer["user"], encoding="utf-8")
            record: dict[str, Any] = {"schema": 1, "runId": run_id, "arm": name, "case": case.id,
                                      "split": case.split, "category": case.category,
                                      "expect": case.expect, "repeat": repeat,
                                      **{k: v for k, v in answer.items() if k != "user"}}
            if answer["status"] == "ok":
                shaped = shape(arm, answer["parsed"], body)
                proposal = (shaped.get("shaped") or {}).get("proposal")
                applied = apply(checker, case, proposal["ops"] if proposal else None)
                # A dropped proposal never reaches the device; what the device *would* have said
                # about it is still worth knowing, so it is applied here as raw ops too.
                raw_ops = ((answer["parsed"] or {}).get("proposal") or {}).get("ops") \
                    if isinstance(answer["parsed"], Mapping) else None
                if shaped.get("dropped") and isinstance(raw_ops, list):
                    record["rawApplied"] = {k: v for k, v in apply(checker, case, raw_ops).items()
                                            if k in ("status", "sentence")}
                record["shaped"] = shaped
                # The applied draft is left out: rescoring applies the stored ops again, for free.
                record["applied"] = {k: v for k, v in applied.items() if k not in ("draft", "yaml")}
                record["verdict"] = judge(case, checker, shaped, applied)
                verdict = record["verdict"]
                if args.repairs:
                    record["repairs"], record["final"] = repair_loop(
                        args.repairs, arm, checker, case, body, row, shaped, applied, record["verdict"])
                    calls += len(record["repairs"])
                    for step in record["repairs"]:
                        print(f"     repair {step['attempt']}: {step['problem'][:120]} → "
                              f"{'PASS' if step['verdict']['pass'] else step['verdict'].get('failure')}")
                mark = "PASS" if verdict["pass"] else f"FAIL {verdict['failure']}: {verdict.get('why')}"
                print(f"  r{repeat} {name:8s} {case.id:26s} {answer['seconds']:5.2f}s  {mark}"[:300])
            else:
                print(f"  r{repeat} {name:8s} {case.id:26s} {answer['status']}: {answer.get('detail')}")
            write(path, record)
            if calls >= args.max_calls:
                break
    finally:
        for checker in checkers.values():
            checker.close()
    print(f"\n{calls} calls; run: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
