"""The management CLI.

Registration is closed, so this is the only way an account comes into being. It writes through the
service layer rather than over HTTP, which is why it needs no password of its own and no superuser:
there is no superuser to have.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from collections import defaultdict
from typing import Any

from acervo import seed_data
from acervo.domain.projection import COLLECTION_BY_NAME, projected
from acervo.models import journal
from acervo.repository import accounts, graph, jobs
from acervo.repository.session import open_database
from acervo.settings import Settings, settings as read_settings

SEED_DEVICE = "acervoseed"


def _read_password(prompt: str) -> str:
    """The password, from a terminal or from a pipe, but always after saying it wants one.

    `docker exec -i` without `-t` gives a pipe, not a terminal — so echo cannot be suppressed and
    `getpass` is not an option. Printing the prompt anyway is what separates "waiting for you" from
    "hung": without it the command sits silent with the cursor on a blank line, which is exactly what
    it looks like when something has locked up.
    """
    print(prompt, end="", file=sys.stderr, flush=True)
    if sys.stdin.isatty():
        # A terminal, so the typing can be hidden. `getpass` writes its own prompt; ours has already
        # gone to stderr, so it is given an empty one.
        password = getpass.getpass("")
    else:
        password = sys.stdin.readline().rstrip("\n")
    print(file=sys.stderr)
    return password


def create_account(settings: Settings, email: str) -> int:
    open_database(settings.database_path)
    password = _read_password(f"Password for {email}: ")
    if sys.stdin.isatty():
        if password != getpass.getpass("Repeat it: "):
            print("The passwords do not match.", file=sys.stderr)
            return 2
    try:
        created = accounts.create(email, password)
    except (ValueError, accounts.AccountExists) as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    # Deliberately not the record id. It is the `ownerId` on every record this account will hold,
    # not a secret — but an unexplained 15-character string next to a password prompt reads like one,
    # and nobody typing this command has a use for it.
    print(f"Created {created['email']}.")
    return 0


def seed(settings: Settings, email: str) -> int:
    open_database(settings.database_path)
    owner = accounts.by_email(email)
    if owner is None:
        print(f"No account for {email}. Create one first with `accounts create`.", file=sys.stderr)
        return 2

    held = graph.held_ids(owner["id"])
    changes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for name, row in seed_data.demo_records(owner["id"]):
        if row["id"] in held:
            # The graph route is not the old per-record create: re-posting a stored record at
            # revision zero is a stale write, not a no-op. Skipping by id is what makes a second run
            # harmless.
            skipped += 1
            continue
        collection = COLLECTION_BY_NAME[name]
        changes[collection.key].append(projected(collection, {**row, "revision": 0}))

    written = sum(len(records) for records in changes.values())
    if written:
        # Disposable demonstration words: enriching them would spend the owner's allowances on
        # vocabulary nobody meant to keep.
        graph.merge_graph(owner["id"], SEED_DEVICE, changes, enqueue=None)
    print(f"Seeded {written} records for {email}; {skipped} already held.")
    return 0


def show_takes(settings: Settings) -> int:
    from acervo.pronunciation import takes

    kept, size = takes.usage(settings.takes_path)
    print(f"{kept} takes, {size / 1_000_000:.1f} MB, in {settings.takes_path}")
    return 0


def prune_takes(settings: Settings, older_than_days: float, dry_run: bool) -> int:
    """Empty the take cache by hand, which is the only thing that ever empties it.

    The store is unbounded on purpose. A twelve-word loop is about seventy takes of a few hundred
    kilobytes, so a year of daily loops is single-digit gigabytes — small beside the dictionaries and
    the media volume, and both of those are managed the same way: deliberately, when you care.
    Sweeping it on a timer would quietly time-limit the thing the cache exists for, which is that a
    render abandoned half way resumes against the takes it already paid for.
    """
    from acervo.pronunciation import takes

    kept, size = takes.usage(settings.takes_path)
    if dry_run:
        stale, freed = takes.prune(settings.takes_path, older_than_days, dry_run=True)
        print(f"{stale} of {kept} takes are older than {older_than_days:g} days "
              f"({freed / 1_000_000:.1f} of {size / 1_000_000:.1f} MB). Nothing was deleted.")
        return 0
    gone, freed = takes.prune(settings.takes_path, older_than_days)
    print(f"Deleted {gone} of {kept} takes, freeing {freed / 1_000_000:.1f} MB.")
    return 0


def _owner(email: str | None) -> str | None:
    """The account a command is about: the one named, or the only one there is. None, having said
    why, when there is no such account or more than one to choose from."""
    if email:
        account = accounts.by_email(email)
        if account is None:
            print(f"There is no account for {email}.", file=sys.stderr)
            return None
        return account["id"]
    held = accounts.all_ids()
    if len(held) != 1:
        print("This server holds more than one account; name one with --owner-email.", file=sys.stderr)
        return None
    return held[0]


def anki_command(settings: Settings, command: str, email: str | None) -> int:
    """Anki by hand: the same functions the push and pull jobs run (`services/anki.py`), printing
    what they do on stderr and the result on stdout.

    A job and a command never use the robot's collection at once — whichever comes second is told the
    robot is busy — so running one of these while the server is up is safe."""
    from acervo.services import anki

    open_database(settings.database_path)
    try:
        if command == "export-state":
            result = anki.export_state(settings)
        elif command == "adopt-server":
            result = anki.adopt_server(settings)
        else:
            owner = _owner(email)
            if owner is None:
                return 2
            result = {"bootstrap": anki.bootstrap, "push": anki.push, "pull": anki.pull}[command](
                settings, owner)
    except Exception as failure:  # noqa: BLE001 - every refusal is reported in its own words
        print(f"Anki {command} failed: {getattr(failure, 'message', '') or failure}", file=sys.stderr)
        return 2
    print(json.dumps({"operation": command, **result}, indent=2, ensure_ascii=False, default=str))
    return 0


def show_story(settings: Settings, story_id: str, email: str | None) -> int:
    """A story's parts as they are stored: the text, the passages, and what each was read as.

    A reading command, and the one place a story's *audio* can be looked at without a browser. What
    it is for is the question the interface cannot answer — whether a passage carries the direction
    the writer wrote, or an empty one because the voice that answered could not take it, and where
    each passage sits in the recording.
    """
    owner = _owner(email)
    if owner is None:
        return 2

    story = graph.owned_records(owner, "stories", [story_id]).get(story_id)
    if story is None:
        print(f"There is no story {story_id} in that account.", file=sys.stderr)
        return 2
    parts = [row for row in graph.story_parts(owner, story_id) if not row.get("deleted")]
    words = [row for row in graph.story_words(owner, story_id) if not row.get("deleted")]
    print(f"{story.get('emoji') or ''} {story.get('title') or '(untitled)'}   {story_id}")
    print(f"{story.get('language')}  ·  {len(parts)} parts  ·  {len(words)} words"
          f"  ·  written by {story.get('modelId') or '-'}")
    for part in sorted(parts, key=lambda row: row.get("position", 0)):
        segments = part.get("audioSegments") or []
        directed = sum(1 for one in segments if (one.get("direction") or "").strip())
        print(f"\n{'-' * 76}\nPART {part.get('position', 0) + 1}  {part.get('heading') or ''}   {part['id']}")
        print(f"  picture: {part.get('imageRef') or '(none)'}"
              f"{'  ' + (part.get('failureReason') or '') if part.get('failureReason') else ''}")
        print(f"  recording: {part.get('audioRef') or '(none)'}")
        if part.get("audioRef"):
            print(f"             {part.get('audioProviderId')}:{part.get('audioModelId')}"
                  f"  voice {part.get('audioVoice')}  ·  {len(segments)} passages, {directed} directed")
        print(f"  text: {part.get('text') or ''}")
        for index, one in enumerate(segments, 1):
            print(f"    {index:>2}. [{float(one.get('start') or 0):6.2f}-{float(one.get('end') or 0):6.2f}] "
                  f"{one.get('direction') or '(no direction sent)'}")
            print(f"        {(one.get('text') or '').strip()!r}")
    return 0


def serve(settings: Settings, host: str, port: int) -> int:
    import uvicorn

    from acervo.access_log import quiet_health_probes
    from acervo.api.app import API_ROOT, create_app

    config = uvicorn.Config(create_app(settings), host=host, port=port, log_level="info")
    quiet_health_probes(f"{API_ROOT}/health")
    uvicorn.Server(config).run()
    return 0


def providers() -> int:
    """Print which providers this machine can use, and whose account each one spends.

    The same reading on a laptop and inside the server container, so "am I about to spend my work
    Google account?" has one answer arrived at one way. It calls nothing and spends nothing: every
    line comes from the catalogue and the environment.
    """
    from acervo.models import load_catalogue
    from acervo.models.catalogue import identity, key_hint, reason, row_settings

    for row in load_catalogue():
        why = reason(row)
        print(f"{'yes' if why is None else 'no ':>3}  {row.label}")
        print(f"     kinds     {', '.join(row.kinds)}")
        for kind in row.kinds:
            print(f"     {kind:<9} {', '.join(row.models_for(kind))}")
        # The same three facts Settings ▸ Providers renders, so the terminal reading and the pane
        # cannot disagree about which credential is deployed. Four characters at each end of a key
        # is the whole disclosure, here as there.
        if row.keyEnv:
            print(f"     key       {row.keyEnv} {key_hint(row) or '(not set)'}")
        elif row.authEnv:
            print(f"     key       {row.authEnv} (a credentials file)")
        for name, value in row_settings(row):
            print(f"     setting   {name}={value or '(not set)'}")
        if (account := identity(row)) is not None:
            print(f"     account   {account}")
        if why is not None:
            print(f"     why not   {why}")
    return 0


def call_timings(settings: Settings) -> int:
    """How long each job actually takes, per model, from the call log.

    The reading a timeout should be set from. A bound picked by feel is either so long that a dead
    connection reads as a hung page — two minutes of "Writing a brief…" for a brief that takes two
    seconds — or so short that a legitimately slow answer is thrown away. The durations have been
    recorded all along; this is the part that was missing.
    """
    path = settings.call_log_path
    if not path or not path.exists():
        print(f"No call log at {path or '(disabled)'}.")
        return 1
    # Rotated files too, oldest first, so a summary is not silently a summary of the last few hours.
    lines: list[str] = []
    for backup in sorted(path.parent.glob(f"{path.name}.*"), reverse=True):
        lines.extend(backup.read_text(encoding="utf-8", errors="replace").splitlines())
    lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())

    rows = journal.summarise(lines)
    if not rows:
        print(f"{len(lines)} line(s) in {path}, none of them a model call.")
        return 1
    print(f"{'job':10} {'provider:model':46} {'ok':>4} {'fail':>5} "
          f"{'median':>7} {'p95':>7} {'worst':>7} {'lost':>8}")
    for row in rows:
        print(f"{row.caller:10} {row.pair:46} {row.answered:4d} {row.failed:5d} "
              f"{row.at(.5):6.2f}s {row.at(.95):6.2f}s {row.at(1):6.2f}s {row.lost:7.2f}s")
    slowest = max(row.at(1.0) for row in rows)
    print(f"\nSlowest answer seen: {slowest:.2f}s. A timeout wants headroom over that, not over a "
          f"guess — and a call past it is not slow, it is gone.")
    return 0


def open_jobs(settings: Settings, as_json: bool) -> int:
    """What a deploy reads before it touches anything: how many jobs are open, and of what kind."""
    open_database(settings.database_path)
    held = jobs.open_jobs()
    by_kind: dict[str, int] = defaultdict(int)
    for job in held:
        by_kind[job["kind"]] += 1
    if as_json:
        print(json.dumps({"open": len(held), "byKind": dict(sorted(by_kind.items()))}))
    elif not held:
        print("No jobs are open.")
    else:
        kinds = ", ".join(f"{count} {kind}" for kind, count in sorted(by_kind.items()))
        print(f"{len(held)} job(s) open ({kinds}).")
    return 0


def list_jobs(settings: Settings, limit: int = 30) -> int:
    """Recent jobs and why the failed ones failed.

    It listed only *open* jobs and printed neither `error` nor `message`, so the one thing an
    operator comes here for — a render that failed and the sentence saying why — was the one thing
    it could not show. The message is indented under its job rather than run onto the row, because a
    provider's own wording is a sentence and not a column.
    """
    open_database(settings.database_path)
    held = jobs.latest(limit)
    if not held:
        print("No jobs have run.")
        return 0
    for job in held:
        subject = job["subject"] or {}
        print(f"{job['id']}  {job['state']:<10} {job['kind']:<16} "
              f"{subject.get('kind', '')}:{subject.get('id', '')}  {job['createdAt']}")
        if job.get("error") or job.get("message"):
            said = " ".join(str(job.get("message") or "").split())
            print(f"    {job.get('error') or ''}{': ' if job.get('error') and said else ''}{said}")
    return 0


def cancel_jobs(settings: Settings, job_id: str | None, wait: float) -> int:
    """Cancel every open job (or one), and wait for the runner to let go of the running ones.

    Cancellation is cooperative: the runner stops at its next check, between model calls. A call
    already in flight is abandoned rather than waited out — after `wait` seconds the job is closed
    as cancelled whether or not the runner has agreed, because the process is about to stop anyway.
    """
    open_database(settings.database_path)
    if job_id is None:
        running = jobs.cancel_all()
    else:
        job = next((j for j in jobs.open_jobs() if j["id"] == job_id), None)
        if job is None:
            print(f"No open job {job_id}.", file=sys.stderr)
            return 2
        jobs.request_cancel(job["ownerId"], job_id)
        running = [job] if job["state"] == "running" else []
    deadline = time.monotonic() + max(0.0, wait)
    while running and time.monotonic() < deadline:
        still = {j["id"] for j in jobs.open_jobs() if j["state"] == "running"}
        running = [j for j in running if j["id"] in still]
        if running:
            time.sleep(0.5)
    if running:
        abandoned = jobs.abandon_running()
        print(f"Abandoned {abandoned} job(s) still in a model call.")
    print("Cancelled." if job_id else "Every open job is cancelled.")
    return 0


def show_map(settings: Settings, email: str, language: str) -> int:
    """A language's map as last drawn: its fingerprint, its size, and whether its regions are named.

    Reading only. It never draws: that is the route's, which is the one place that knows when a map
    is out of date.
    """
    from acervo.services import meaning

    open_database(settings.database_path)
    owner = accounts.by_email(email)
    if owner is None:
        print(f"No account for {email}.", file=sys.stderr)
        return 2
    stored = meaning.stored_map(settings, owner["id"], language)
    if stored is None:
        print(f"No {language} map has been drawn for {email} yet; opening the map draws it.")
        return 0
    regions = [r for r in stored["regions"] if r["level"] == "region"]
    print(f"{language}  ·  {stored['senses']} senses  ·  {stored['words']} words  ·  "
          f"{len(regions)} regions  ·  names {stored['names']}")
    print(f"fingerprint {stored['fingerprint']}  ·  model {stored['model']}")
    for region in stored["regions"]:
        labels = region["labels"]
        indent = "    " if region["level"] == "hood" else ""
        print(f"{indent}{region['id']:>4}  {region['count']:>4}  {labels.get('name') or '-':<32}"
              f"{' · '.join(labels.get('words') or [])}")
    return 0


def export_map(settings: Settings, email: str, language: str, output: str) -> int:
    """Every sense of a language with the text and the vector the map was drawn from, one JSON line
    each — for the discovery experiment, which then needs no encoder of its own."""
    import json

    from acervo.services import meaning

    open_database(settings.database_path)
    owner = accounts.by_email(email)
    if owner is None:
        print(f"No account for {email}.", file=sys.stderr)
        return 2
    rows = meaning.vectors(settings, owner["id"], language)
    with open(output, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} senses to {output}.")
    return 0


def enqueue_missing(settings: Settings, email: str, language: str, limit: int, dry_run: bool) -> int:
    """Queue ordinary `enrich` jobs for words that are missing something.

    The corner case the event-driven design leaves: words that existed before it, or an import that
    asked for nothing. It is the same job, the same steps and the same progress view as a save's —
    not a second pipeline — and nothing runs it on a schedule.
    """
    from acervo.work.enrich import incomplete

    open_database(settings.database_path)
    owner = accounts.by_email(email)
    if owner is None:
        print(f"No account for {email}.", file=sys.stderr)
        return 2
    words = incomplete(settings, owner["id"], language=language, limit=limit)
    for word in words:
        print(f"{word['headword']}  {', '.join(word['lacking'])}")
        if not dry_run:
            jobs.enqueue(owner["id"], "enrich", trigger="backfill",
                         subject_kind="lexeme", subject_id=word["id"])
    what = "would be enriched" if dry_run else "queued"
    print(f"{len(words)} word(s) {what}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="acervo.admin", description="Manage an Acervo server.")
    commands = parser.add_subparsers(dest="command", required=True)

    account_parser = commands.add_parser("accounts", help="accounts")
    account_commands = account_parser.add_subparsers(dest="account_command", required=True)
    create = account_commands.add_parser("create", help="create an account, reading the password from stdin")
    create.add_argument("--email", required=True)

    seed_parser = commands.add_parser("seed", help="insert disposable demonstration vocabulary")
    seed_parser.add_argument("--owner-email", required=True)

    commands.add_parser("providers", help="what this machine can call, and as whom")

    anki_parser = commands.add_parser("anki", help="Anki by hand: what the push and pull jobs do")
    anki_commands = anki_parser.add_subparsers(dest="anki_command", required=True)
    for name, text in (
        ("bootstrap", "make the first collection on an empty Anki server, and switch the loop on"),
        ("push", "bring Anki up to date with the vocabulary now"),
        ("pull", "read Anki's review state and history now"),
        ("export-state", "print what a pull would read, storing nothing"),
        ("adopt-server", "take over an Anki server a device has already uploaded to"),
    ):
        one = anki_commands.add_parser(name, help=text)
        one.add_argument("--owner-email", default=None,
                         help="whose vocabulary, where the server holds more than one account")

    commands.add_parser("calls", help="how long each job takes per model, from the call log")

    jobs_parser = commands.add_parser("jobs", help="the work the server is doing")
    job_commands = jobs_parser.add_subparsers(dest="job_command", required=True)
    open_parser = job_commands.add_parser("open", help="how many jobs are open")
    open_parser.add_argument("--json", action="store_true")
    job_commands.add_parser("list", help="every open job")
    cancel_parser = job_commands.add_parser("cancel", help="cancel open jobs")
    which = cancel_parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true")
    which.add_argument("job_id", nargs="?")
    cancel_parser.add_argument(
        "--wait", type=float, default=30.0,
        help="seconds to wait for the runner before abandoning a job still in a model call",
    )
    enqueue_parser = job_commands.add_parser("enqueue", help="queue work for words that lack it")
    enqueue_parser.add_argument("kind", choices=("enrich",))
    enqueue_parser.add_argument("--missing", action="store_true", required=True,
                                help="every word missing a clip search, a picture or a recording")
    enqueue_parser.add_argument("--owner-email", required=True)
    enqueue_parser.add_argument("--language", default="", help="only this vocabulary")
    enqueue_parser.add_argument("--limit", type=int, default=0, help="at most this many words")
    enqueue_parser.add_argument("--dry-run", action="store_true", help="print them and queue nothing")

    story_parser = commands.add_parser("stories", help="stories, as they are stored")
    story_commands = story_parser.add_subparsers(dest="story_command", required=True)
    show_story_parser = story_commands.add_parser("show", help="one story's parts, passages and directions")
    show_story_parser.add_argument("story_id", help="the story's record id")
    show_story_parser.add_argument("--owner-email", default=None,
                                   help="whose story, where the server holds more than one account")

    takes_parser = commands.add_parser("takes", help="the loop take cache")
    take_commands = takes_parser.add_subparsers(dest="take_command", required=True)
    take_commands.add_parser("show", help="how many takes are kept, and what they weigh")
    prune_parser = take_commands.add_parser("prune", help="delete takes untouched for a while")
    prune_parser.add_argument("--older-than", type=float, default=90,
                              help="in days; a take a render used recently survives")
    prune_parser.add_argument("--dry-run", action="store_true", help="say what would go, delete nothing")

    map_parser = commands.add_parser("map", help="the meaning map")
    map_commands = map_parser.add_subparsers(dest="map_command", required=True)
    show_map_parser = map_commands.add_parser("show", help="a language's map as last drawn")
    export_map_parser = map_commands.add_parser("export", help="texts and vectors, for the discovery experiment")
    for one in (show_map_parser, export_map_parser):
        one.add_argument("--owner-email", required=True)
        one.add_argument("--language", required=True)
    export_map_parser.add_argument("--output", required=True, help="a JSON-lines file to write")

    serve_parser = commands.add_parser("serve", help="run the HTTP service")
    serve_parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - the container's own port
    serve_parser.add_argument("--port", type=int, default=8000)

    arguments = parser.parse_args(argv)
    settings = read_settings()
    if arguments.command == "calls":
        return call_timings(settings)
    if arguments.command == "accounts":
        return create_account(settings, arguments.email)
    if arguments.command == "seed":
        return seed(settings, arguments.owner_email)
    if arguments.command == "providers":
        return providers()
    if arguments.command == "anki":
        return anki_command(settings, arguments.anki_command, arguments.owner_email)
    if arguments.command == "stories":
        return show_story(settings, arguments.story_id, arguments.owner_email)
    if arguments.command == "map":
        if arguments.map_command == "show":
            return show_map(settings, arguments.owner_email, arguments.language)
        return export_map(settings, arguments.owner_email, arguments.language, arguments.output)
    if arguments.command == "takes":
        if arguments.take_command == "show":
            return show_takes(settings)
        return prune_takes(settings, arguments.older_than, arguments.dry_run)
    if arguments.command == "jobs":
        if arguments.job_command == "open":
            return open_jobs(settings, arguments.json)
        if arguments.job_command == "list":
            return list_jobs(settings)
        if arguments.job_command == "enqueue":
            return enqueue_missing(settings, arguments.owner_email, arguments.language,
                                   arguments.limit, arguments.dry_run)
        return cancel_jobs(settings, None if arguments.all else arguments.job_id, arguments.wait)
    return serve(settings, arguments.host, arguments.port)


if __name__ == "__main__":
    raise SystemExit(main())
