from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from .build import DEFAULT_DECK, build, write_payload
from .manifest import SyncManifest
from .robot import AnkiRobot, RobotSettings, result_json
from .state import SYSTEM, held_by_key, study_states

REVIEW_LOOKBACK_MS = 30 * 86_400_000


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
    )
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap-upload")
    bootstrap.add_argument("manifest", type=Path)
    adopt = commands.add_parser("adopt-server")
    adopt.add_argument("--confirm-no-other-clients", action="store_true")
    push = commands.add_parser("push")
    push.add_argument("manifest", type=Path)
    exported = commands.add_parser("export-state")
    exported.add_argument("--reviews-since", type=int, default=None,
                          help="Also print every review after this review id (0 for all)")
    # The write half. `export-state` stays the read-only diagnostic it has always been; this is the
    # one that puts the answer where the interface can show it.
    pull = commands.add_parser(
        "pull-state", help="Write Anki's review state into Acervo as study states"
    )
    pull.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
    pull.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
    pull.add_argument("--device-id", default="ankiworker0001")
    pull.add_argument("--dry-run", action="store_true", help="Report what would be written.")

    # Cards out. `build-manifest` writes the payload to look at; `push-vocabulary` builds it and
    # pushes it in one step, inside the worker, which is where the pictures and recordings are.
    written = commands.add_parser(
        "build-manifest", help="Write the vocabulary's cards as a manifest and the files it names"
    )
    written.add_argument("output", type=Path)
    written.add_argument("--graph", type=Path, help="A saved graph pull to read instead of the server")
    pushed = commands.add_parser(
        "push-vocabulary", help="Build the vocabulary's cards and push them to Anki"
    )
    pushed.add_argument("--bootstrap", action="store_true",
                        help="Create the first server collection instead (an empty account only)")
    pushed.add_argument("--dry-run", action="store_true", help="Build and report, push nothing.")
    for command in (written, pushed):
        command.add_argument("--language", action="append", default=[],
                             help="A language to include (repeatable); every language by default")
        command.add_argument("--deck", default=DEFAULT_DECK,
                             help="Deck name; {language} is the language's name")
        command.add_argument("--picture-size", type=int, default=768,
                             help="Longest side of a picture in pixels; 0 keeps the master")
        command.add_argument("--media-root", type=Path,
                             default=os.environ.get("ACERVO_MEDIA_PATH") or None)
        command.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
        command.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
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


def _signed_in(args: argparse.Namespace):
    from acervo.client import AcervoClient

    password = os.environ.get("ACERVO_OWNER_PASSWORD", "")
    if not args.server_url or not args.owner_email or not password:
        raise ValueError(
            "Set --server-url, --owner-email and ACERVO_OWNER_PASSWORD to reach the vocabulary"
        )
    client = AcervoClient(args.server_url)
    client.sign_in(args.owner_email, password)
    return client


def _graph(args: argparse.Namespace) -> dict:
    if getattr(args, "graph", None):
        payload = json.loads(args.graph.read_text(encoding="utf-8"))
        return payload.get("changes", payload)
    with _signed_in(args) as client:
        return client.pull_graph().get("changes") or {}


def build_payload(args: argparse.Namespace, output: Path) -> dict:
    """The vocabulary's cards, written under `output`, and what went into them."""
    changes = _graph(args)
    built = build(
        changes,
        languages=args.language or None,
        media_root=args.media_root,
        deck=args.deck,
    )
    if not built.notes:
        raise ValueError("There are no active words to make cards from")
    path = write_payload(built, output, picture_size=args.picture_size or None)
    kinds: dict[str, int] = {}
    for note in built.notes:
        key = "words" if note["kind"] == "word" else ("senses" if note["note_id"] == note["sense_id"] else "examples")
        kinds[key] = kinds.get(key, 0) + 1
    return {"manifest": str(path), "notes": len(built.notes), **kinds, "media": len(built.media),
            "missing_media": built.missing}


def push_vocabulary(args: argparse.Namespace, robot: AnkiRobot) -> dict:
    with tempfile.TemporaryDirectory(prefix="acervo-anki-") as scratch:
        built = build_payload(args, Path(scratch))
        if args.dry_run:
            return {"operation": "push-vocabulary", "dry_run": True, **built}
        manifest, manifest_dir = SyncManifest.load(built["manifest"])
        result = (robot.bootstrap_upload(manifest, manifest_dir) if args.bootstrap
                  else robot.push(manifest, manifest_dir))
        return {**result, "built": {key: value for key, value in built.items() if key != "manifest"}}


def pull_state(args: argparse.Namespace, robot: AnkiRobot) -> dict:
    """Sync down, read the scheduling, and write it through the graph route like any other client.

    A job's write path is a client's write path: same route, same validation, same revision
    allocation as a phone. The credential is the owner's own account, because every record is
    owner-scoped and a second account could not write against the owner's lexemes at all.
    """
    from acervo.client import AcervoClient

    password = os.environ.get("ACERVO_OWNER_PASSWORD", "")
    if not args.server_url or not args.owner_email or not password:
        raise ValueError(
            "Set --server-url, --owner-email and ACERVO_OWNER_PASSWORD to write study state"
        )
    with AcervoClient(args.server_url) as client:
        client.sign_in(args.owner_email, password)
        # The history is sent from a month before where the server's ends: a review made offline
        # reaches the collection days after reviews made since, and one already held adds nothing.
        latest = client.latest_review(SYSTEM)
        exported = robot.export_state(
            reviews_since=max(0, latest - REVIEW_LOOKBACK_MS) if latest else 0)
        changes = client.pull_graph().get("changes") or {}
        live = {
            str(lexeme["id"]) for lexeme in changes.get("lexemes") or [] if not lexeme.get("deleted")
        }
        senses = {
            str(sense["id"]): str(sense["lexemeId"])
            for sense in changes.get("senses") or [] if not sense.get("deleted")
        }
        rows, skipped = study_states(
            exported, held_by_key(changes), live, senses, device_id=args.device_id
        )
        retired = sum(1 for row in rows if row["deleted"])
        reviews = exported.get("reviews") or []
        if args.dry_run:
            return {"operation": "pull-state", "written": 0, "would_write": len(rows) - retired,
                    "would_retire": retired, "skipped": skipped, "reviews_read": len(reviews),
                    "dry_run": True}
        if rows:
            client.push_graph({"studyStates": rows}, device_id=args.device_id)
        history = client.push_reviews(SYSTEM, reviews) if reviews else {"added": 0}
    return {"operation": "pull-state", "written": len(rows) - retired, "retired": retired,
            "skipped": skipped, "reviews_read": len(reviews), "reviews_added": history["added"]}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build-manifest":
            print(result_json({"operation": "build-manifest",
                               **build_payload(args, args.output.expanduser().resolve())}))
            return 0
        robot = AnkiRobot(_settings(args))
        if args.command in ("bootstrap-upload", "push"):
            manifest, manifest_dir = SyncManifest.load(args.manifest)
            result = (
                robot.bootstrap_upload(manifest, manifest_dir)
                if args.command == "bootstrap-upload"
                else robot.push(manifest, manifest_dir)
            )
        elif args.command == "adopt-server":
            result = robot.adopt_server(
                confirm_no_other_clients=args.confirm_no_other_clients
            )
        elif args.command == "pull-state":
            result = pull_state(args, robot)
        elif args.command == "push-vocabulary":
            result = push_vocabulary(args, robot)
        else:
            result = robot.export_state(reviews_since=args.reviews_since)
        print(result_json(result))
        return 0
    except Exception as exc:
        print(f"Acervo Anki robot failed: {exc}", file=sys.stderr)
        return 2
