"""The robot from a manifest, for the one-shot worker, and cards from a saved graph, for a laptop.

Keeping Anki up to date with the vocabulary is the server's own work (`services/anki.py`): a push
after the vocabulary changes, a read every hour, and `acervo.admin anki` to do either by hand. What
is left here needs no vocabulary at all — a manifest carried in from outside and the collection's
state read back, which are what the sync smoke test drives, and the cards a saved graph would make,
for `scripts/preview_anki_cards.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from .build import DEFAULT_DECK, build, write_payload
from .manifest import SyncManifest
from .progress import Progress
from .robot import AnkiRobot, RobotSettings, result_json


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize Acervo-rendered notes through a headless Anki client."
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("ACERVO_ANKI_SYNC_ENDPOINT"),
        help="Self-hosted Anki base URL, including trailing slash",
    )
    parser.add_argument(
        "--collection",
        type=Path,
        default=Path(
            os.environ.get(
                "ACERVO_ANKI_COLLECTION",
                "/var/lib/acervo/worker/collection.anki2",
            )
        ),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "ACERVO_ANKI_BACKUP_DIR",
                "/var/lib/acervo/worker/backups",
            )
        ),
    )
    parser.add_argument(
        "--template-dir",
        type=Path,
        default=Path(os.environ.get("ACERVO_ANKI_TEMPLATE_DIR", _repository_root() / "templates")),
    )
    parser.add_argument(
        "--media-timeout",
        type=float,
        default=float(os.environ.get("ACERVO_ANKI_MEDIA_TIMEOUT", "120")),
        help="Seconds media sync may go without progress before giving up",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap-upload")
    bootstrap.add_argument("manifest", type=Path)
    push = commands.add_parser("push")
    push.add_argument("manifest", type=Path)
    exported = commands.add_parser("export-state", help="Print the collection's review state")
    exported.add_argument("--reviews-since", type=int, default=None,
                          help="Also print every review after this review id (0 for all)")

    written = commands.add_parser(
        "build-manifest", help="Write a saved graph's cards as a manifest and the files it names"
    )
    written.add_argument("output", type=Path)
    written.add_argument("--graph", type=Path, required=True,
                         help="A saved graph pull (GET /graph) to make the cards from")
    written.add_argument("--language", action="append", default=[],
                         help="A language to include (repeatable); every language by default")
    written.add_argument("--deck", default=DEFAULT_DECK,
                         help="Deck name; {language} is the language's name")
    written.add_argument("--picture-size", type=int, default=768,
                         help="Longest side of a picture in pixels; 0 keeps the master")
    written.add_argument("--media-root", type=Path,
                         default=os.environ.get("ACERVO_MEDIA_PATH") or None)
    return parser


def _settings(args: argparse.Namespace) -> RobotSettings:
    endpoint = args.endpoint
    if not endpoint:
        raise ValueError("Set --endpoint or ACERVO_ANKI_SYNC_ENDPOINT")
    return RobotSettings(
        endpoint=endpoint,
        username=os.environ.get("ACERVO_ANKI_SYNC_USERNAME", ""),
        password=os.environ.get("ACERVO_ANKI_SYNC_PASSWORD", ""),
        collection_path=args.collection.expanduser().resolve(),
        backup_dir=args.backup_dir.expanduser().resolve(),
        template_dir=args.template_dir.expanduser().resolve(),
        media_timeout_seconds=args.media_timeout,
    )


def build_payload(args: argparse.Namespace, output: Path, progress: Progress) -> dict:
    """A saved graph's cards, written under `output`, and what went into them."""
    payload = json.loads(args.graph.read_text(encoding="utf-8"))
    changes = payload.get("changes", payload)
    built = build(
        changes,
        languages=args.language or None,
        media_root=args.media_root,
        deck=args.deck,
    )
    if not built.notes:
        raise ValueError("There are no active words to make cards from")
    kinds: dict[str, int] = {}
    for note in built.notes:
        key = "words" if note["kind"] == "word" else ("senses" if note["note_id"] == note["sense_id"] else "examples")
        kinds[key] = kinds.get(key, 0) + 1
    path = write_payload(built, output, picture_size=args.picture_size or None, progress=progress)
    return {"manifest": str(path), "notes": len(built.notes), **kinds, "media": len(built.media),
            "missing_media": built.missing}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build-manifest":
            print(result_json({"operation": "build-manifest",
                               **build_payload(args, args.output.expanduser().resolve(),
                                               Progress())}))
            return 0
        robot = AnkiRobot(_settings(args))
        if args.command == "export-state":
            print(result_json(robot.export_state(reviews_since=args.reviews_since)))
            return 0
        manifest, manifest_dir = SyncManifest.load(args.manifest)
        result = (
            robot.bootstrap_upload(manifest, manifest_dir)
            if args.command == "bootstrap-upload"
            else robot.push(manifest, manifest_dir)
        )
        print(result_json(result))
        return 0
    except Exception as exc:
        print(f"Acervo Anki robot failed: {exc}", file=sys.stderr)
        return 2
