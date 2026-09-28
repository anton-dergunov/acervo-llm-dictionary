"""`acervo_worker.py loop render` — make one loop by hand, and say how long each part took.

This exists to be run once on a fresh deployment, and its output is what sets the poll interval and
the timeout in `work/loop.py`. `docs/features/loops.md` §3 is explicit that those are
read from a measurement rather than picked from feel, which is the same rule
`python -m acervo.admin calls` exists for.

It runs in the **worker** container because that is where a by-hand job belongs — one entry point,
a new subcommand and never a new service — and because the generator publishes no port, so only
something on the compose network can reach it. The worker signs in with the owner's password, over
`POST /session` like any other client, and hands its *session* token to the generator as the render credential:
`POST /pronunciations/take` accepts a session as well as a render-scoped token, precisely so this is
possible without minting one by hand.

    docker compose -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker \
        loop render --owner-email learner@account.example.com --language es --words 12
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from typing import Any

from acervo.client import AcervoClient, AcervoError
from acervo.loops.client import Item, LoopError, LoopService

DEFAULT_URL = "http://lexibeat:8000/api/v1"
DEFAULT_SERVER = "http://server:8000"
# Long enough that a render waiting out a rate limit still finishes, and short enough that a hung one
# is not waited on all afternoon. The point of the exercise is to replace this with a measurement.
POLL_SECONDS = 5.0
MAX_WAIT_SECONDS = 3600.0


def _words(graph: dict[str, Any], language: str, count: int) -> list[Item]:
    """Loop-eligible words: a live lexeme in this language with a `primaryGloss`.

    Eligibility is that one field, for §2.8's reason — `shortGloss` may carry several distinct
    meanings and a loop must choose between them — so a word whose writer left it without one is
    simply not offered. Nothing fills it in later.
    """
    found: list[Item] = []
    # `pull_graph` answers the whole envelope — cursor, dataset id and `changes` — rather than the
    # collections alone, which is what a client needs to advance a cursor with.
    for lexeme in (graph.get("changes") or graph).get("lexemes", []):
        if lexeme.get("deleted") or lexeme.get("language") != language:
            continue
        gloss = (lexeme.get("primaryGloss") or "").strip()
        if not gloss:
            continue
        found.append(Item(
            source=str(lexeme.get("headword") or "").strip(),
            target=gloss,
            direction=(lexeme.get("emotion") or "").strip(),
        ))
        if len(found) >= count:
            break
    return found


def render(args: argparse.Namespace) -> int:
    password = os.environ.get("ACERVO_PASSWORD") or getpass.getpass("Acervo password: ")
    service = LoopService(args.lexibeat_url)

    try:
        schema = service.schema()
    except LoopError as failure:
        print(f"The loop generator said no: {failure.message}", file=sys.stderr)
        return 2
    print(f"generator  api {schema.api_version}  engine {schema.engine_version}")
    print(f"formats    {', '.join(one.id for one in schema.formats)}")
    if schema.sample_free:
        # Said loudly. Rendering goes ahead — that is the decision — but a track made on the
        # sample-free palette is not a slightly plainer version of the same thing.
        print("samples    NOT the pinned bundle, or not all of it — this loop will be thinner than")
        print("           the music was tuned against. Install it with ./deploy.sh --install-samples.")
    else:
        print(f"samples    bundle v{schema.bundle_version}, complete, so all "
              f"{len(schema.families)} families are available")

    with AcervoClient(args.server_url) as client:
        try:
            token = client.sign_in(args.owner_email, password)
        except AcervoError as failure:
            print(f"Could not sign in: {failure}", file=sys.stderr)
            return 2
        graph = client.pull_graph()
        words = _words(graph, args.language, args.words)

    if not words:
        print(f"No word in {args.language} has a primaryGloss, so no loop can be made of them.",
              file=sys.stderr)
        return 2
    print(f"words      {len(words)}: " + ", ".join(word.source for word in words[:6])
          + (" …" if len(words) > 6 else ""))
    directed = sum(1 for word in words if word.direction)
    print(f"           {directed} of them carry an emotion")

    started = time.monotonic()
    try:
        operation = service.start(
            items=words,
            source_language={"code": args.language, "name": args.language_name or args.language},
            target_language={"code": args.gloss_language, "name": args.gloss_language_name or args.gloss_language},
            token=token, delivery=args.delivery, format=args.format,
            switches=dict(_switch(one) for one in args.switch or []), family=args.family,
            seed=args.seed,
        )
    except LoopError as failure:
        print(f"The render was refused: {failure.message}", file=sys.stderr)
        return 2
    print(f"operation  {operation.id}")

    last = ""
    while not operation.finished:
        if time.monotonic() - started > MAX_WAIT_SECONDS:
            print("Gave up waiting after an hour.", file=sys.stderr)
            return 1
        time.sleep(POLL_SECONDS)
        try:
            operation = service.operation(operation.id)
        except LoopError as failure:
            print(f"Lost the render: {failure.message}", file=sys.stderr)
            return 1
        if operation.message != last:
            last = operation.message
            print(f"  {time.monotonic() - started:6.1f}s  {operation.fraction:5.1%}  {last}")

    elapsed = time.monotonic() - started
    if operation.status != "completed" or operation.result is None:
        print(f"\nThe render {operation.status}: {operation.error or 'no reason given'}", file=sys.stderr)
        return 1

    loop = operation.result
    audio, mime = service.track(loop.audio_url)
    utterances = len(words) * 6
    print(f"\nrendered   {elapsed:.1f}s for {loop.duration_seconds:.1f}s of audio "
          f"({elapsed / max(len(words), 1):.1f}s a word, {elapsed / max(utterances, 1):.1f}s an utterance)")
    print(f"bed        style {loop.style_id}  seed {loop.seed}  {loop.bpm:g} BPM  "
          f"fingerprint {loop.bed_fingerprint}")
    print(f"track      {mime}  {len(audio) / 1_000_000:.1f} MB  "
          f"{len(audio) * 8 / max(loop.duration_seconds, 1) / 1000:.0f} kbps")
    print(f"lines      {len(loop.cues)} over {len(loop.items)} words, format {loop.format}"
          + (f" (fell back from {loop.fallback_from})" if loop.fallback_from else ""))
    if args.out:
        with open(args.out, "wb") as handle:
            handle.write(audio)
        print(f"wrote      {args.out}")
    print("\nSet work/loop.py's poll and timeout from the elapsed time above, not from feel.")
    print("`python -m acervo.admin calls` on the server has the per-model breakdown.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="acervo_worker.py loop", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("render", help="make one loop and report how long each part took")
    one.add_argument("--owner-email", required=True)
    one.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL") or DEFAULT_SERVER)
    one.add_argument("--lexibeat-url", default=os.environ.get("ACERVO_LEXIBEAT_URL") or DEFAULT_URL)
    one.add_argument("--language", default="es", help="the language of the words")
    one.add_argument("--language-name", default="Spanish", help="what to call it in a director note")
    one.add_argument("--gloss-language", default="en")
    one.add_argument("--gloss-language-name", default="English")
    one.add_argument("--words", type=int, default=12)
    one.add_argument("--format", default="classic", help="one of the generator's formats")
    one.add_argument("--switch", action="append", metavar="NAME=VALUE",
                     help="a choice the format offers, e.g. repetitions=4 or remarks=false")
    one.add_argument("--family", default="auto")
    one.add_argument("--seed", type=int, default=None)
    # Plain by default because it is the cheap one: one recording a line, varied by the generator.
    # The server reads the owner's Settings ▸ Loops choice instead; this command has no settings.
    one.add_argument("--delivery", choices=("plain", "directed"), default="plain")
    one.add_argument("--out", default=None, help="write the finished MP3 here")

    args = parser.parse_args(argv)
    return render(args)


def _switch(given: str) -> tuple[str, bool | str]:
    """`name=value`, with true and false read as the on/off switches they are."""
    name, _, value = given.partition("=")
    lowered = value.strip().lower()
    return name.strip(), (lowered == "true") if lowered in ("true", "false") else value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
