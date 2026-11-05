#!/usr/bin/env python3
"""Draw one picture for each sense of each word, on this laptop.

Phase A of `docs/features/sense-images.md`. It reads the vocabulary graph from the server and writes
nothing back: the output is a local directory of JSON records and WebP masters that a later import
turns into `imagePrompt` rows. That separation is deliberate — the point of this phase is to iterate
on the prompt and spend the Vertex credits while they exist, not to change the database.

Resumable by looking at the filesystem. A sense whose picture is already there is skipped; delete
the picture and the next run writes a fresh brief and draws it again with a new seed. The graph is
re-read every run, so words ingested since last time are picked up with no extra step.

    # who is about to be billed
    scripts/generate_images.py check

    # what would be drawn
    scripts/generate_images.py plan --language es \
        --server-url https://acervo.example.com --owner-email learner@account.example.com

    # draw the first ten
    scripts/generate_images.py run --language es --limit 10 \
        --server-url https://acervo.example.com --owner-email learner@account.example.com

    # look at them
    scripts/generate_images.py sheet && open output/images/sheet.html
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import webbrowser
from pathlib import Path

from acervo.client import AcervoClient, AcervoError
from acervo.article import build_articles
from acervo.images.article import anchor_for, drawn_senses
from acervo.images.brief import BriefWriter
from acervo.images.compose import prompt_version
from acervo.images.render import Renderer
from acervo.images.styles import load_styles
from acervo.jobs.images.publish import BATCH, publish
from acervo.jobs.images.run import Runner, Store, plan
from acervo.jobs.images.sheet import write_sheet
from acervo.jobs.images.verify import verify
from acervo.models import chain
from acervo.models.local import load_local

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "output" / "images"
DEFAULT_STYLES = REPO_ROOT / "config" / "image-styles.yaml"
DEFAULT_TEMPLATE = REPO_ROOT / "prompts" / "acervo_image_brief.md"
def parse_chain(text: str) -> list[chain.Choice] | None:
    """`--image-chain cloudflare,vertex` or `--image-chain cloudflare:@cf/…`, or nothing.

    A bare provider id means every model that provider offers, in the order listed, which is what
    `chain.resolve` already understands.
    """
    chosen: list[chain.Choice] = []
    for item in (part.strip() for part in text.split(",")):
        if not item:
            continue
        provider, _, model = item.partition(":")
        chosen.append((provider, model) if model else provider)
    return chosen or None


def owner_chain(args: argparse.Namespace, kind: str) -> list[chain.Choice] | None:
    """The chain the owner chose in Settings, or None to use this machine's own order.

    Only an *owner* chain is carried across. The server also answers with the order it would use
    itself, and that one is resolved against the server's providers rather than this laptop's. The
    owner's pairs name the server's provider ids, so `providers.local.json` should use the same ids
    for them to mean anything here.

    An owner chain that is empty is not a gap: it means every image model was switched off on
    purpose, and the sweep must stop rather than quietly fall back to this machine's order.
    """
    if not getattr(args, "server_url", ""):
        return None
    password = os.environ.get("ACERVO_PASSWORD") or getpass.getpass("Acervo password: ")
    try:
        with AcervoClient(args.server_url) as client:
            client.sign_in(args.owner_email, password)
            readout = client.models()
    except AcervoError as error:
        print(f"note: the server did not say which models you chose ({error}); "
              f"using the order in providers.local.json for {kind}", file=sys.stderr)
        return None
    found = (readout.get("chains") or {}).get(kind) or {}
    if found.get("source") != "owner":
        return None
    return [(pair["provider"], pair["model"]) for pair in found.get("pairs") or []]


def resolve_chain(args: argparse.Namespace, kind: str, flag: str) -> tuple[chain.Candidate, ...]:
    """Resolve once, before anything is spent.

    A mistyped provider or a model it does not offer refuses here rather than at the first word of a
    sweep — which is the whole reason this resolves at startup instead of per call.
    """
    chosen = parse_chain(flag) if flag else owner_chain(args, kind)
    catalogue = load_local()
    candidates = chain.resolve(kind, chosen, catalogue)
    if not candidates:
        raise SystemExit(chain.unconfigured(kind, chosen, catalogue).detail
                         or f"Nothing in providers.local.json can produce {kind}.")
    return candidates


def confirm_unnamed_credentials(candidates, assume_yes: bool) -> None:
    """Ask before spending a Google sign-in that does not say whose it is.

    A service account's key names its account, and `check` prints it. A user's own sign-in — the
    file `gcloud auth application-default login` writes — does not record which login wrote it, so
    on that path, and only on it, "Bill this account?" is still worth asking.
    """
    unnamed = [candidate.row for candidate in candidates
               if candidate.row.credential.file and candidate.row.identity() is None]
    if not unnamed or assume_yes:
        return
    for row in {row.id: row for row in unnamed}.values():
        print(f"{row.label} will spend whichever Google account signed in to write its credentials "
              f"file, and the file does not say which.")
    if input("Draw anyway? [y/N] ").strip().lower() not in {"y", "yes"}:
        raise SystemExit("Stopped without spending anything.")


def load_graph(args: argparse.Namespace):
    """The articles in scope, and the senses that already hold a picture."""
    password = os.environ.get("ACERVO_PASSWORD") or getpass.getpass("Acervo password: ")
    with AcervoClient(args.server_url) as client:
        client.sign_in(args.owner_email, password)
        # One pull, and nothing else: this stage reads the graph and writes only to the filesystem.
        changes = client.pull_graph()["changes"]
    return build_articles(changes, args.language), drawn_senses(changes)


def command_check(args: argparse.Namespace) -> int:
    """What this machine would use, and as whom. Calls nothing and spends nothing.

    No prices: nobody in this repository knows what a picture costs, and a table here would be
    wrong the first time a provider changed one. Each answer reports what it was billed, and
    `usageUrl` in Settings ▸ Providers is where the running total is read.
    """
    styles = load_styles(args.styles)
    print(f"Styles          {len(styles.styles)} ({styles.digest})")
    print(f"Prompt version  {prompt_version(args.template, styles.digest)}")
    catalogue = load_local()
    for kind in ("text", "image"):
        for candidate in chain.resolve(kind, parse_chain(getattr(args, f"{kind}_chain", "")), catalogue):
            account = candidate.row.identity()
            print(f"{kind:<15} {candidate.row.label} · {candidate.model}"
                  + (f"  ({account})" if account else ""))
        for row in catalogue.serving(kind):
            if (why := row.reason()) is not None:
                print(f"{'':<15} {row.label} is unavailable — {why}")
    return 0


def command_plan(args: argparse.Namespace) -> int:
    articles, drawn = load_graph(args)
    store = Store(args.output)
    jobs = plan(articles, store, drawn=drawn, redo=args.redo, only=args.only.split(','))
    senses = sum(len(article.senses) for article in articles)
    print(f"{len(articles)} words, {senses} senses in scope"
          + (f" (language {args.language})" if args.language else ""))
    print(f"{len(jobs)} senses have no picture yet")
    for job in jobs[: args.limit or 20]:
        anchor = anchor_for(job.sense)
        line = anchor.get("text") if anchor else job.sense.definition
        print(f"  {job.article.headword:<28} {(line or '')[:70]}")
    if args.limit and len(jobs) > args.limit:
        print(f"  … and {len(jobs) - args.limit} more")
    return 0


def command_run(args: argparse.Namespace) -> int:
    brief_chain = resolve_chain(args, "text", args.brief_chain)
    image_chain = resolve_chain(args, "image", args.image_chain)
    confirm_unnamed_credentials([*brief_chain, *image_chain], args.yes)

    articles, drawn = load_graph(args)
    store = Store(args.output)
    jobs = plan(articles, store, drawn=drawn, redo=args.redo, only=args.only.split(','))
    if args.limit:
        jobs = jobs[: args.limit]
    if not jobs:
        print("Every sense in scope already has a picture.")
        return 0

    styles = load_styles(args.styles)
    catalogue = load_local()
    runner = Runner(
        store=store,
        writer=BriefWriter(catalogue, brief_chain, Path(args.template).read_text(encoding="utf-8"), styles),
        renderer=Renderer(size=(args.size, args.size)),
        styles=styles,
        template_path=args.template,
        candidates=image_chain,
        workers=args.workers,
        rate_limit=args.rate_limit,
        attempts=args.attempts,
    )
    drawn_by = ", ".join(f"{c.row.id}/{c.model}" for c in image_chain)
    print(f"Drawing {len(jobs)} senses at {args.size}² · {args.workers} workers · "
          f"{args.rate_limit or '∞'}/min per pair → {store.root}")
    print(f"  briefs by  {', '.join(f'{c.row.id}/{c.model}' for c in brief_chain)}")
    print(f"  pictures by {drawn_by}")
    result = runner.run(jobs)
    print(f"\n{result['drawn']} drawn, {result['refused']} refused, {result['failed']} failed "
          f"in {result['seconds']}s ({result['throttled']} quota waits)")
    for (provider, model), count in sorted(result["byPair"].items()):
        print(f"  {count:>4} × {provider}  {model}")
    # What the providers said, never a table in this repository. A provider that does not price its
    # answer is counted rather than guessed at: Cloudflare inside its free allocation genuinely
    # costs nothing, and outside it the price is per neuron, which the response does not carry.
    print(f"Billed ${result['costUsd']:.2f}"
          + (f" · {result['unpriced']} calls reported no cost" if result["unpriced"] else ""))
    if result["stopped"]:
        print(f"Stopped early: {result['stopped']}", file=sys.stderr)

    sheet = write_sheet(store)
    print(f"Contact sheet: {sheet}")
    if args.open:
        webbrowser.open(sheet.as_uri())
    return 1 if result["stopped"] else 0


def command_verify(args: argparse.Namespace) -> int:
    store = Store(args.output)
    report = verify(store)
    print(f"{report.images} images · {report.records} records · {report.drawn} drawn · "
          f"{report.refused} refused by the writer · {report.blocked} blocked by the provider")
    for kind, subjects in sorted(report.problems.items()):
        print(f"  [FAIL] {kind}: {len(subjects)} -> {', '.join(subjects[:5])}")
    print("safe to import" if report.ok else "NOT safe to import")
    return 0 if report.ok else 1


def command_sheet(args: argparse.Namespace) -> int:
    sheet = write_sheet(Store(args.output), args.to, args.limit)
    print(sheet)
    if args.open:
        webbrowser.open(sheet.as_uri())
    return 0


def command_publish(args: argparse.Namespace) -> int:
    """Write the rows and copy the images. Verified first, and all-or-nothing about the checks."""
    password = os.environ.get("ACERVO_PASSWORD") or getpass.getpass("Acervo password: ")
    store = Store(args.output)
    with AcervoClient(args.server_url) as client:
        client.sign_in(args.owner_email, password)
        outcome = publish(
            store, client, media=args.media, device_id=args.device_id, batch=args.batch
        )
    if not outcome.ok:
        return 1
    print(
        f"Published {outcome.written} image prompts and {outcome.copied} files; "
        f"{outcome.held} already held, {outcome.undrawn} have no picture."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--styles", type=Path, default=DEFAULT_STYLES)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    sub = parser.add_subparsers(dest="command", required=True)

    def graph_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
        target.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
        target.add_argument("--language", default="es",
                            help="Only this vocabulary language. Empty string for all.")
        target.add_argument("--limit", type=int, default=0)
        target.add_argument("--redo", action="store_true",
                            help="Include senses that already have a picture.")
        target.add_argument("--only", default="",
                            help="Comma-separated headwords, sense ids or image ids to restrict to.")

    checker = sub.add_parser("check", help="Say which providers a run would use, and as whom")
    checker.add_argument("--text-chain", default="", help="Override the brief chain for this reading.")
    checker.add_argument("--image-chain", default="", help="Override the image chain for this reading.")

    planner = sub.add_parser("plan", help="List the senses that have no picture yet")
    graph_arguments(planner)

    runner = sub.add_parser("run", help="Write briefs and draw pictures")
    graph_arguments(runner)
    runner.add_argument("--workers", type=int, default=3)
    runner.add_argument("--rate-limit", type=int, default=1,
                        help="Image calls per minute PER PAIR. Measured ceiling is 1. 0 removes it.")
    # Deliberately a flag rather than a catalogue field: a rate limit is a fact about *this
    # account* on *this model*, not about the provider, and a number in a tracked file is a lie the
    # day a quota increase comes through.
    runner.add_argument("--brief-chain", default="",
                        help="Providers to write briefs with, e.g. `vertex,gemini-free`. "
                             "Default: your chain from the server, else the order in providers.local.json.")
    runner.add_argument("--image-chain", default="",
                        help="Providers to draw with, e.g. `cloudflare,vertex` or "
                             "`cloudflare:@cf/black-forest-labs/flux-2-klein-4b`.")
    runner.add_argument("--size", type=int, default=1024,
                        help="Square master in pixels. 512 is the cheap Cloudflare sweep.")
    runner.add_argument("--attempts", type=int, default=12,
                        help="Tries per sense when the project is over quota.")
    runner.add_argument("--yes", action="store_true",
                        help="Do not ask about credentials that cannot name their account")
    runner.add_argument("--open", action="store_true", help="Open the contact sheet when finished")

    sub.add_parser("verify", help="Check the run directory is internally consistent before import")

    publisher = sub.add_parser("publish", help="Write a verified run into the graph and the media directory")
    publisher.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
    publisher.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
    publisher.add_argument("--media", type=Path, required=True,
                           help="The media directory the server serves; images are fanned out under it.")
    publisher.add_argument("--device-id", default="imagepublish01")
    publisher.add_argument("--batch", type=int, default=BATCH,
                           help="Records per write. One stale record refuses a whole batch.")

    sheet = sub.add_parser("sheet", help="Rebuild the contact sheet from what is on disk")
    sheet.add_argument("--limit", type=int, default=0, help="Show only the newest N images.")
    sheet.add_argument("--to", type=Path, default=None, help="Write somewhere other than sheet.html.")
    sheet.add_argument("--open", action="store_true")

    args = parser.parse_args()
    handlers = {"check": command_check, "plan": command_plan, "run": command_run,
                "publish": command_publish, "sheet": command_sheet, "verify": command_verify}
    try:
        return handlers[args.command](args)
    except AcervoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
