#!/usr/bin/env python3
"""Walk a messy vocabulary notes file into Acervo's Inbox.

A thin transport (`docs/architecture/jobs.md`): it submits the file a chunk at a time to
`POST /captures` and follows the job the server makes of it. The server works out where each entry
ends, stops at words you already have, files the rest in the Inbox and enriches them — and waits out
a busy provider itself. This script holds no prompt, no pacing and no retries; it only remembers how
far the server got.

The source file is never modified unless you ask for it:

    # resumable, and leaves the notes byte-identical
    scripts/ingest_vocabulary_file.py "~/notes/English vocabulary.md" \\
        --server-url https://acervo.example.com --owner-email learner@account.example.com

    # cuts each processed entry out of the file, so what is left is the queue
    scripts/ingest_vocabulary_file.py copy-of-notes.md --consume ...

The words go in your only vocabulary of their language. Where you keep several — your own English and
a starter — name the one they go in with `--vocabulary "English"`; without it the server stops and
says which it was choosing between.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from acervo.client import AcervoClient, AcervoError

DEVICE_ID = "ingestscript01"
DEFAULT_CHECKPOINTS = Path.home() / ".acervo" / "ingest"
# The server refuses a capture longer than this, so a chunk is cut to fit.
TEXT_LIMIT = 20000
POLL_SECONDS = 2.0
OPEN = ("queued", "running")


def vocabulary_named(client: AcervoClient, name: str) -> tuple[str | None, list[str]]:
    """The id of the account's vocabulary shown as `name` (or kept for that language tag), and the
    names it has, for saying what it could have been."""
    held = [entry for entry in client.pull_graph()["changes"].get("vocabularies", [])
            if not entry.get("deleted")]
    wanted = name.strip().casefold()
    shown = [str(entry.get("displayName") or entry["language"]) for entry in held]
    for entry, label in zip(held, shown):
        if wanted in (label.casefold(), str(entry["language"]).casefold()):
            return str(entry["id"]), shown
    return None, shown


def checkpoint_path(directory: Path, source: Path) -> Path:
    resolved = str(source.resolve())
    identity = hashlib.sha256(resolved.encode()).hexdigest()[:12]
    return directory / f"{source.resolve().name}.{identity}.json"


def read_offset(path: Path, source: Path) -> int:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    # A checkpoint against a file that has since changed length is meaningless, and resuming from
    # it would skip or repeat entries silently.
    if state.get("file") != str(source.resolve()) or state.get("lines") != count_lines(source):
        return 0
    return int(state.get("offset", 0))


def write_offset(path: Path, source: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"file": str(source.resolve()), "lines": count_lines(source), "offset": offset}),
        encoding="utf-8",
    )


def count_lines(source: Path) -> int:
    return len(source.read_text(encoding="utf-8").splitlines())


def chunk_of(lines: list[str], offset: int, size: int) -> list[str]:
    """The next submission: up to `size` lines, and never more text than the server accepts."""
    chunk = lines[offset:offset + size]
    while len(chunk) > 1 and len("\n".join(chunk)) > TEXT_LIMIT:
        chunk = chunk[: len(chunk) // 2]
    return chunk


def describe(word: dict) -> str:
    lines = word.get("lines", 0)
    span = f"{lines} {'line' if lines == 1 else 'lines'}"
    if word.get("outcome") == "saved":
        return f"  ✓ {word.get('headword')}  ({span})"
    if word.get("outcome") == "duplicate":
        existing = ", ".join(word.get("existing") or [])
        return f"  · {word.get('headword')}  already in your vocabulary as {existing} — skipped"
    return f"  ✗ {word.get('message') or word.get('error')}  — skipped {span}"


def follow(client: AcervoClient, job_id: str, printed: int) -> tuple[dict, int]:
    """Poll a job to its end, printing each word as the server reports it."""
    while True:
        job = client.job(job_id)
        words = ((job.get("steps") or [{}])[0].get("detail") or {}).get("words") or []
        for word in words[printed:]:
            print(describe(word), flush=True)
        printed = len(words)
        if job.get("state") not in OPEN:
            return job, printed
        waiting = next((step for step in job.get("steps") or [] if step.get("state") == "waiting"), None)
        if waiting is not None and job.get("notBefore"):
            print(f"  … the provider is busy; the server resumes at {job['notBefore']}", flush=True)
        time.sleep(POLL_SECONDS)


def dry_run(client: AcervoClient, source: Path, offset: int, args: argparse.Namespace) -> int:
    """Propose entries one window at a time and create nothing — the synchronous review route."""
    lines = source.read_text(encoding="utf-8").splitlines()
    shown = 0
    while offset < len(lines) and (not args.limit or shown < args.limit):
        if not lines[offset].strip() or lines[offset].strip() in {"---", "***", "___"}:
            offset += 1
            continue
        window = lines[offset:offset + args.window_lines]
        try:
            result = client.capture(
                device_id=DEVICE_ID, mode="stream", text="\n".join(window),
                language=args.language or None, topics=args.topic, sourceKind="unknown",
                vocabulary=args.vocabulary_id,
            )
        except AcervoError as error:
            print(f"\n{error}", file=sys.stderr)
            return 1
        resolution = result.get("resolution") or {}
        consumed = min(max(1, int(resolution.get("consumedLines") or 1)), len(window))
        draft = result.get("draft") or {}
        senses = len(draft.get("senses") or [])
        if result.get("duplicates"):
            print(f"  · {resolution.get('headword')}  already in your vocabulary — would be skipped")
        else:
            print(f"  ~ {draft.get('headword', resolution.get('headword'))}  "
                  f"({senses} {'sense' if senses == 1 else 'senses'}, {consumed} lines) — not created")
        shown += 1
        offset += consumed
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="the notes file to walk")
    parser.add_argument("--server-url", default=os.getenv("ACERVO_SERVER_URL", ""))
    parser.add_argument("--owner-email", default=os.getenv("ACERVO_OWNER_EMAIL", ""))
    parser.add_argument("--window-lines", type=int, default=40,
                        help="how many lines the server looks at for one entry (default: 40)")
    parser.add_argument("--chunk-lines", type=int, default=400,
                        help="how many lines each submission carries (default: 400)")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many entries")
    parser.add_argument("--language", default="", help="a hint, verified by the server")
    parser.add_argument("--vocabulary", default="",
                        help="the vocabulary the words go in, by its name, where you keep several of their language")
    parser.add_argument("--topic", action="append", default=[],
                        help="the topic this file is already filed under; may be repeated")
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINTS,
                        help="where progress is remembered, outside the notes themselves")
    parser.add_argument("--restart", action="store_true", help="ignore the checkpoint and start again")
    parser.add_argument("--dry-run", action="store_true",
                        help="build entries and show them, but create nothing")
    parser.add_argument("--consume", action="store_true",
                        help="cut each processed entry out of the source file (a .bak is written first)")
    args = parser.parse_args()

    source: Path = args.file.expanduser()
    if not source.is_file():
        print(f"No such file: {source}", file=sys.stderr)
        return 2
    if args.window_lines < 1 or args.chunk_lines < args.window_lines:
        print("--window-lines must be at least 1, and --chunk-lines at least as many", file=sys.stderr)
        return 2

    server_url = args.server_url.strip() or input("Acervo server URL: ").strip()
    email = args.owner_email.strip() or input("Account email: ").strip()
    password = os.getenv("ACERVO_PASSWORD") or getpass.getpass("Account password: ")
    if not server_url or not email or not password:
        print("A server, an account and a password are required", file=sys.stderr)
        return 2

    client = AcervoClient(server_url)
    try:
        client.sign_in(email, password)
    except AcervoError as error:
        print(f"Could not sign in: {error}", file=sys.stderr)
        return 1

    args.vocabulary_id = None
    if args.vocabulary:
        try:
            args.vocabulary_id, names = vocabulary_named(client, args.vocabulary)
        except AcervoError as error:
            print(f"Could not read your vocabularies: {error}", file=sys.stderr)
            return 1
        if args.vocabulary_id is None:
            print(f"You have no vocabulary called {args.vocabulary} (you have: {', '.join(names) or 'none'})",
                  file=sys.stderr)
            return 2

    marker = checkpoint_path(args.checkpoint_dir, source)
    # In consume mode the file itself is the progress, so an offset would double-count.
    offset = 0 if (args.consume or args.restart) else read_offset(marker, source)
    if args.dry_run:
        return dry_run(client, source, offset, args)

    if args.consume:
        backup = source.with_suffix(source.suffix + ".bak")
        if not backup.exists():
            backup.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  backup written to {backup}")

    counts = {"saved": 0, "duplicate": 0, "failed": 0}
    while True:
        lines = source.read_text(encoding="utf-8").splitlines()
        done = sum(counts.values())
        if offset >= len(lines) or (args.limit and done >= args.limit):
            break
        chunk = chunk_of(lines, offset, args.chunk_lines)
        complete = offset + len(chunk) >= len(lines)
        try:
            job = client.submit_capture(
                device_id=DEVICE_ID, mode="stream", text="\n".join(chunk),
                window=args.window_lines, complete=complete,
                limit=(args.limit - done) if args.limit else 0,
                language=args.language or None, topics=args.topic, sourceKind="unknown",
                vocabulary=args.vocabulary_id,
            )
            job, _ = follow(client, job["id"], 0)
        except AcervoError as error:
            print(f"\n{error}", file=sys.stderr)
            return 1

        progress = (job.get("steps") or [{}])[0].get("detail") or {}
        consumed = min(int(progress.get("consumedLines") or 0), len(chunk))
        for word in progress.get("words") or []:
            counts[word.get("outcome", "failed")] = counts.get(word.get("outcome", "failed"), 0) + 1

        if args.consume:
            remaining = lines[consumed:]
            source.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
        else:
            offset += consumed
            write_offset(marker, source, offset)

        if job.get("state") != "done":
            print(f"\nThe server stopped: {job.get('message') or job.get('error')}", file=sys.stderr)
            if job.get("error") == "vocabulary_ambiguous":
                print("Name the one the words go in with --vocabulary NAME.", file=sys.stderr)
            return 1
        if consumed == 0:
            # Nothing a whole window could hold was left in this chunk; the tail is the next one's.
            if complete:
                break
            print("\nThe server made no progress on this chunk; try a larger --chunk-lines.",
                  file=sys.stderr)
            return 1

    total = count_lines(source)
    print(f"\n{counts['saved']} created, {counts['duplicate']} already known, "
          f"{counts['failed']} skipped. Their pictures, clips and audio are being made on the server.")
    if args.consume:
        print(f"{total} lines left in {source.name}.")
    else:
        print(f"At line {offset} of {total} — {source.name} is unchanged; rerun to continue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
