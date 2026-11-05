#!/usr/bin/env python3
"""Apply the measured `primaryGloss`/`emotion` fix to the owner's REAL, already-captured words.

This is the one script in this experiment that writes to the live server. Everything else here
(`run.py`, `score.py`) only ever calls a model and reads what comes back. This one calls
`POST /graph` — the same route, same validation, same revision allocation a phone gets
(`src/acervo/client.py`) — because `compose` never re-runs on an existing lexeme: shipping the fixed
prompt only helps words captured *after* it ships, and nothing else touches `primaryGloss`/`emotion`
on a record that already has them. This script is that "something else," run once, by hand.

**Nothing is written by default.** Every run without `--apply` only pulls, classifies and prints what
it *would* change — the two costly, hard-to-undo mistakes here are asking the model for nothing
(wasted calls) and writing something wrong to 1,000+ real records, and the second is the one this
guards against.

**Narrow repair stays narrow.** A lexeme selected because its `primaryGloss` is wrong is asked ONLY
to redo `primaryGloss`; a lexeme selected because its `emotion` is empty is asked ONLY to redo
`emotion`. Neither call touches the other field, and neither touches senses, notes, examples or
anything else on the record — the full pulled record is sent back on write with only the one field
changed, because the graph's write contract has no partial patch: an incoming lexeme change replaces
every column (`domain/projection.py::_assign_lexeme`), so anything not resent is wiped.

**Every proposed value is checked before it is written**, not just generated: a `primaryGloss` that
still collapses a multi-word headword to one word, or an `emotion` that isn't `null` and isn't 3-12
plain words, is logged and left alone rather than written — the old (bad) value survives to be looked
at by hand, which is better than a second bad value nobody chose.

**The field rules are read from the shipped prompt at call time**, not copied here, so this script
cannot drift from what `prompts/acervo_compose.md` actually says.

Run from anywhere with network access to the server — this is an ordinary HTTPS client, exactly what
the app itself is. No NAS, no Docker, no SSH.

    set -a; . ./.env; set +a
    PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \\
      experiments/primary-gloss-emotion-tuning/backfill_apply.py \\
      --server-url https://acervo.example.com --owner-email learner@account.example.com
        # dry run: prints what it would do, writes nothing, spends nothing

    ... same command + --apply
        # spends gemini-free calls and writes; prints a before/after count when it's done
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from score import has_emoji, primary_shape, words_of

from acervo.client import AcervoClient, AcervoError
from acervo.domain.ids import now_instant
from acervo.models.local import load_local
from acervo.models import call
from acervo.models.errors import ProviderError
from acervo.models.pacing import Pace

HERE = Path(__file__).resolve().parent
COMPOSE_PROMPT = HERE.parents[1] / "prompts" / "acervo_compose.md"
DEVICE_ID = "backfillfieldsscript"  # matches ^[a-z0-9]{1,32}$ (domain/ids.py)
PROVIDER = "gemini-api"
RATE_PER_MINUTE = 8
WRITE_BATCH = 15  # push_graph is all-or-nothing per call; keep each write's blast radius small
GEN_BATCH = 8  # words per model call — small enough that one bad JSON reply is cheap to redo


def field_rule(name: str) -> str:
    """The live `- \\`name\\` — ...` bullet from the shipped prompt, so this script can't drift from it."""
    text = COMPOSE_PROMPT.read_text(encoding="utf-8")
    match = re.search(rf"^- `{name}`.*?(?=\n- `|\n##)", text, re.DOTALL | re.MULTILINE)
    if not match:
        raise SystemExit(f"could not find the `{name}` field rule in {COMPOSE_PROMPT}")
    return match.group(0).strip()


def index_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row[key], []).append(row)
    return out


def first_sense_term(lexeme_id: str, senses_by_lexeme: dict[str, list[dict]], gloss_lang: str) -> str:
    senses = sorted(senses_by_lexeme.get(lexeme_id, []), key=lambda s: s.get("order") or 0)
    for sense in senses:
        for gloss in sense.get("glosses") or []:
            if gloss.get("lang") == gloss_lang and gloss.get("terms"):
                return gloss["terms"][0]
    return ""


def classify(lexemes: list[dict], include_review: bool) -> tuple[list[dict], list[dict]]:
    wanted_primary_shapes = {"auto_fail", "review"} if include_review else {"auto_fail"}
    needs_primary, needs_emotion = [], []
    for lex in lexemes:
        if lex["deleted"] or lex["language"].split("-")[0] == "zh":
            continue  # `primary_shape` and the whitespace word count don't mean anything for Chinese
        if lex.get("primaryGloss") and primary_shape(lex["headword"], lex["primaryGloss"], lex["language"]) in wanted_primary_shapes:
            needs_primary.append(lex)
        if lex.get("primaryGloss") and not lex.get("emotion"):
            needs_emotion.append(lex)
    return needs_primary, needs_emotion


def build_prompt(kind: str, batch: list[dict], vocab_by_language: dict[str, dict],
                  senses_by_lexeme: dict[str, list[dict]]) -> tuple[str, str]:
    rule = field_rule("primaryGloss" if kind == "primary" else "emotion")
    system = (
        "You are fixing ONE field on vocabulary entries that already exist. Follow this rule "
        f"exactly, and change nothing else:\n\n{rule}\n\n"
        f'Return one JSON object mapping each entry\'s "id" to its new {"primaryGloss" if kind == "primary" else "emotion"} '
        "value (a string, or null for emotion when the rule says null). Return every id you were given. "
        "No prose, no code fences."
    )
    lines = []
    for lex in batch:
        vocab = vocab_by_language.get(lex["language"], {})
        gloss_lang = (vocab.get("glossLangs") or ["en"])[0]
        entry = {
            "id": lex["id"], "language": lex["language"], "headword": lex["headword"],
            "lemma": lex["lemma"], "pos": lex["pos"], "glossInto": gloss_lang,
            "shortGloss": lex.get("shortGloss") or "",
        }
        if kind == "primary":
            entry["currentFirstSenseTerm"] = first_sense_term(lex["id"], senses_by_lexeme, gloss_lang)
        else:
            entry["primaryGloss"] = lex.get("primaryGloss") or ""
        lines.append(entry)
    user = json.dumps(lines, ensure_ascii=False, indent=2)
    return system, user


def valid_proposal(kind: str, lex: dict, value: Any) -> str | None:
    """The value to write, or None if it should be left alone."""
    if kind == "primary":
        if not isinstance(value, str) or not value.strip():
            return None
        if primary_shape(lex["headword"], value, lex["language"]) == "auto_fail":
            return None  # still bad — don't replace one wrong value with another
        return value.strip()
    # emotion
    if value is None:
        return None  # a considered `null` is a legitimate answer, not a fix to apply
    if not isinstance(value, str) or not value.strip():
        return None
    words = words_of(value)
    if not (3 <= len(words) <= 12) or has_emoji(value):
        return None
    return value.strip()


def generate(kind: str, targets: list[dict], vocab_by_language: dict, senses_by_lexeme: dict,
             gate: Pace, row: Any) -> dict[str, str]:
    """id -> accepted new value, for whichever ids in `targets` produced a usable, passing answer."""
    accepted: dict[str, str] = {}
    for start in range(0, len(targets), GEN_BATCH):
        batch = targets[start:start + GEN_BATCH]
        system, user = build_prompt(kind, batch, vocab_by_language, senses_by_lexeme)
        gate.acquire()
        try:
            result = call.text(user, row=row, system=system, as_json=True, timeout=90.0)
        except ProviderError as failure:
            if failure.reason == "rate_limited":
                gate.penalise()
            print(f"  [{kind}] batch at {start}: {failure.reason} — skipped, rerun later", file=sys.stderr)
            continue
        gate.succeeded()
        reply = result.parsed if isinstance(result.parsed, dict) else {}
        by_id = {lex["id"]: lex for lex in batch}
        for lex_id, value in reply.items():
            lex = by_id.get(lex_id)
            if lex is None:
                continue  # an id the batch didn't contain — a hallucination, dropped rather than trusted
            checked = valid_proposal(kind, lex, value)
            if checked is not None:
                accepted[lex_id] = checked
        missing = set(by_id) - set(reply)
        if missing:
            print(f"  [{kind}] batch at {start}: {len(missing)} id(s) missing from the reply", file=sys.stderr)
    return accepted


def push_updates(client: AcervoClient, kind: str, by_id: dict[str, dict], accepted: dict[str, str]) -> int:
    """Writes, and updates `by_id` in place for every record that actually lands.

    `by_id` is shared between the primary and emotion passes in `--only both`. The write contract has
    no partial patch (`_assign_lexeme` reads every column fresh), so a later write for the SAME
    lexeme must resend whatever the FIRST write already changed — reading a stale, pre-first-write
    copy of `by_id` would silently revert it. `editedAt` is likewise not server-injected on update
    (`repository/graph.py::merge_record` requires it from the incoming value, via `_require_instant`)
    and must be set fresh on every write. And the `revision` a second write must send is the one the
    FIRST write was just given back — sending the pre-write revision a second time reads as editing a
    record that has since moved, and is refused as `stale_record`. So this reads the server's own
    response, not its own guess, to update `by_id`.
    """
    field = "primaryGloss" if kind == "primary" else "emotion"
    ids = list(accepted)
    written = 0
    for start in range(0, len(ids), WRITE_BATCH):
        chunk_ids = ids[start:start + WRITE_BATCH]
        records = []
        for lex_id in chunk_ids:
            record = dict(by_id[lex_id])  # the exact pulled shape — every field the write contract needs
            record[field] = accepted[lex_id]
            record["editedAt"] = now_instant()
            records.append(record)
        try:
            response = client.push_graph({"lexemes": records}, device_id=DEVICE_ID)
        except AcervoError as failure:
            print(f"  [{kind}] write batch at {start} refused ({failure.code}): {failure} — skipped",
                  file=sys.stderr)
            continue
        written += len(records)
        for fresh in response.get("records", {}).get("lexemes", []):
            by_id[fresh["id"]] = fresh  # carries the revision the server just allocated
    return written


def report(label: str, before: list[dict], after_by_id: dict[str, dict], kind: str) -> None:
    if not before:
        print(f"  {label}: nothing to report")
        return
    def still_bad(lex: dict) -> bool:
        if kind == "primary":
            return primary_shape(lex["headword"], lex.get("primaryGloss") or "", lex["language"]) == "auto_fail"
        return not lex.get("emotion")
    before_bad = sum(1 for lex in before if still_bad(lex))
    after_bad = sum(1 for lex in before if still_bad(after_by_id.get(lex["id"], lex)))
    print(f"  {label}: {before_bad}/{len(before)} bad before -> {after_bad}/{len(before)} bad after")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--password-env", help="read the account password from this env var instead of a prompt")
    parser.add_argument("--only", choices=["primary", "emotion", "both"], default="both")
    parser.add_argument("--include-review", action="store_true",
                        help="also attempt primaryGloss's 2-word-collapse 'review' cases, not just auto_fail")
    parser.add_argument("--limit", type=int, help="cap how many lexemes of EACH kind to touch this run")
    parser.add_argument("--apply", action="store_true", help="write for real (default: dry run)")
    args = parser.parse_args()

    password = os.environ[args.password_env] if args.password_env else getpass.getpass(
        f"Password for {args.owner_email}: ")

    client = AcervoClient(args.server_url)
    client.sign_in(args.owner_email, password)
    graph = client.pull_graph(since=0)
    changes = graph["changes"]
    lexemes = changes.get("lexemes", [])
    vocab_by_language = {v["language"]: v for v in changes.get("vocabularies", []) if not v["deleted"]}
    senses_by_lexeme = index_by([s for s in changes.get("senses", []) if not s["deleted"]], "lexemeId")
    by_id = {lex["id"]: lex for lex in lexemes}

    needs_primary, needs_emotion = classify(lexemes, args.include_review)
    if args.limit:
        needs_primary, needs_emotion = needs_primary[:args.limit], needs_emotion[:args.limit]

    print(f"pulled {len(lexemes)} lexeme(s)")
    print(f"primaryGloss candidates: {len(needs_primary)}")
    print(f"emotion candidates: {len(needs_emotion)}")
    if not args.apply:
        print("\n--dry-run (default): nothing generated, nothing written. Add --apply to spend and write.")
        return 0

    row = load_local().find(PROVIDER)
    gate = Pace(RATE_PER_MINUTE, cooldown=30.0, cap=600.0)

    if args.only in ("primary", "both") and needs_primary:
        print(f"\ngenerating primaryGloss for {len(needs_primary)} word(s)...")
        accepted = generate("primary", needs_primary, vocab_by_language, senses_by_lexeme, gate, row)
        written = push_updates(client, "primary", by_id, accepted)
        print(f"  accepted {len(accepted)}, wrote {written}")

    if args.only in ("emotion", "both") and needs_emotion:
        print(f"\ngenerating emotion for {len(needs_emotion)} word(s)...")
        accepted = generate("emotion", needs_emotion, vocab_by_language, senses_by_lexeme, gate, row)
        written = push_updates(client, "emotion", by_id, accepted)
        print(f"  accepted {len(accepted)}, wrote {written}")

    print("\nre-pulling to double-check the result...")
    time.sleep(1.0)
    after = client.pull_graph(since=0)["changes"].get("lexemes", [])
    after_by_id = {lex["id"]: lex for lex in after}
    if args.only in ("primary", "both"):
        report("primaryGloss", needs_primary, after_by_id, "primary")
    if args.only in ("emotion", "both"):
        report("emotion", needs_emotion, after_by_id, "emotion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
