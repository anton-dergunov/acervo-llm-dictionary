"""The Anki loop, bound to this server: the vocabulary pushed out as cards, review state read back.

`consumers/anki/` knows Anki and nothing of Acervo's storage; this is where the two meet
(`docs/features/anki.md`). The graph is read and written in-process, through the same `merge_graph`
the graph route calls — same validation, same revision allocation — and the review history through
the same parse and record the reviews route uses. One pipeline, entered from two places: the jobs in
`work/anki.py`, which run a push after the vocabulary changes and a pull every hour, and the
`acervo.admin anki` commands, which run the same functions by hand.

The robot is just another sync client and holds a collection of its own, in the directory the
one-shot worker mounts too; its lock keeps a job and a hand-run command from ever using it at once.
"""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from acervo.consumers.anki.build import build, write_payload
from acervo.consumers.anki.manifest import SyncManifest
from acervo.consumers.anki.progress import Progress
from acervo.consumers.anki.robot import AnkiRobot, RobotBusy, RobotSettings
from acervo.consumers.anki.state import SYSTEM, held_by_key, study_states
from acervo.errors import ApiError
from acervo.repository import anki_settings, graph, reviews
from acervo.services import reviews as review_history
from acervo.settings import Settings

DEVICE = "acervoanki"
PICTURE_SIZE = 768
# The history is sent from a month before where the server's ends: a review made offline reaches the
# collection days after reviews made since, and one already held adds nothing.
REVIEW_LOOKBACK_MS = 30 * 86_400_000
REVIEW_BATCH = 2000


def robot(settings: Settings, progress: Progress | None = None) -> AnkiRobot:
    if not settings.anki_configured:
        raise ApiError(409, "anki_unconfigured",
                       "This server has no Anki sync server configured, so there is no Anki to reach.")
    data = settings.anki_data_path
    return AnkiRobot(
        RobotSettings(
            endpoint=settings.anki_sync_endpoint,
            username=settings.anki_sync_username,
            password=settings.anki_sync_password,
            collection_path=data / "collection.anki2",
            backup_dir=data / "backups",
            template_dir=settings.anki_template_path,
            media_timeout_seconds=settings.anki_media_timeout,
        ),
        progress,
    )


@contextmanager
def _building(directory: Path) -> Iterator[None]:
    """The kept payload, to one push at a time. It is written before the robot takes its own lock,
    so a push the server runs and one run by hand would otherwise write and prune it together."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".building.lock").open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as busy:
            raise RobotBusy("Another push to Anki is running; try again when it has finished") from busy
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _payload(settings: Settings, owner: str, progress: Progress) -> tuple[SyncManifest, Path, dict]:
    """The owner's cards, written into the kept payload directory, and what went into them. The
    caller holds `_building` on that directory for as long as it uses what is written there."""
    progress.say("Reading the vocabulary")
    changes = graph.pull(owner, 0)["changes"]
    built = build(changes, media_root=settings.media_path)
    if not built.notes:
        raise ApiError(409, "anki_nothing", "There are no words ready for cards yet.")
    kinds: dict[str, int] = {}
    for note in built.notes:
        key = "words" if note["kind"] == "word" else (
            "senses" if note["note_id"] == note["sense_id"] else "examples")
        kinds[key] = kinds.get(key, 0) + 1
    progress.say(f"Built {len(built.notes)} notes ("
                 + ", ".join(f"{count} {key}" for key, count in sorted(kinds.items()))
                 + f") naming {len(built.media)} media files"
                 + (f"; {len(built.missing)} files are missing" if built.missing else ""))
    directory = _payload_directory(settings)
    path = write_payload(built, directory, picture_size=PICTURE_SIZE, progress=progress)
    manifest, manifest_dir = SyncManifest.load(path)
    return manifest, manifest_dir, {"notes": len(built.notes), **kinds, "media": len(built.media),
                                    "missingMedia": len(built.missing)}


def _payload_directory(settings: Settings) -> Path:
    """Kept from one push to the next, per picture size, so only what is new is scaled or copied."""
    return settings.anki_data_path / "payload" / str(PICTURE_SIZE)


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    """The robot's report without its per-note list, which runs to thousands of entries."""
    return {key: value for key, value in result.items() if key != "notes"}


def push(settings: Settings, owner: str, progress: Progress | None = None, *,
         backup: bool = True) -> dict[str, Any]:
    """Bring Anki up to date with the vocabulary: new notes added, changed ones updated, and the
    card design refreshed. Review scheduling is Anki's and is never touched."""
    progress = progress or Progress()
    robot_ = robot(settings, progress)
    with _building(_payload_directory(settings)):
        manifest, manifest_dir, built = _payload(settings, owner, progress)
        result = robot_.push(manifest, manifest_dir, backup=backup)
    return {**_summary(result), "built": built}


def bootstrap(settings: Settings, owner: str, progress: Progress | None = None) -> dict[str, Any]:
    """Make the first collection, on an empty Anki server, and switch the loop on."""
    progress = progress or Progress()
    robot_ = robot(settings, progress)
    # Asked before minutes are spent building cards it could not upload.
    robot_.check_bootstrap()
    with _building(_payload_directory(settings)):
        manifest, manifest_dir, built = _payload(settings, owner, progress)
        result = robot_.bootstrap_upload(manifest, manifest_dir)
    anki_settings.save(owner, push=True, pull=True)
    return {**_summary(result), "built": built}


def pull(settings: Settings, owner: str, progress: Progress | None = None) -> dict[str, Any]:
    """Read Anki's review state into study states, and its review log into the history.

    Only rows whose report changed are written (`consumers/anki/state.py`), so an hourly pull of a
    quiet day writes nothing and no device downloads anything."""
    progress = progress or Progress()
    robot_ = robot(settings, progress)
    latest = reviews.latest(owner, SYSTEM)
    exported = robot_.export_state(reviews_since=max(0, latest - REVIEW_LOOKBACK_MS) if latest else 0)
    changes = graph.pull(owner, 0)["changes"]
    live = {str(lexeme["id"]) for lexeme in changes.get("lexemes") or [] if not lexeme.get("deleted")}
    senses = {str(sense["id"]): str(sense["lexemeId"])
              for sense in changes.get("senses") or [] if not sense.get("deleted")}
    rows, skipped = study_states(exported, held_by_key(changes), live, senses, device_id=DEVICE)
    retired = sum(1 for row in rows if row["deleted"])
    found = exported.get("reviews") or []
    progress.say(f"Read {len(exported.get('notes') or [])} notes and {len(found)} reviews; "
                 f"{len(rows) - retired} study states changed, {retired} retired")
    if rows:
        graph.merge_graph(owner, DEVICE, {"studyStates": rows}, enqueue=None)
    added = 0
    for start in range(0, len(found), REVIEW_BATCH):
        system, batch = review_history.parse(
            {"system": SYSTEM, "reviews": found[start:start + REVIEW_BATCH]})
        added += reviews.record(owner, system, batch)["added"]
    return {"notes": len(exported.get("notes") or []), "written": len(rows) - retired,
            "retired": retired, "skipped": len(skipped), "reviewsRead": len(found),
            "reviewsAdded": added}


def export_state(settings: Settings, progress: Progress | None = None) -> dict[str, Any]:
    """What `pull` would read, printed rather than stored."""
    return robot(settings, progress).export_state(reviews_since=0)


def adopt_server(settings: Settings, progress: Progress | None = None) -> dict[str, Any]:
    """Take over an Anki server a device has already uploaded to, installing Acervo's note types."""
    return robot(settings, progress).adopt_server(confirm_no_other_clients=True)



def apply_settings(settings: Settings, owner: str, body: dict[str, Any]) -> anki_settings.AnkiSettings:
    """Settings ▸ Anki's two switches. Neither can be turned on where there is no Anki to reach."""
    wanted = {name: body.get(name) for name in ("push", "pull") if name in body}
    if not wanted or any(not isinstance(value, bool) for value in wanted.values()):
        raise ApiError(400, "invalid_input", "push and pull are each on or off.")
    if any(wanted.values()):
        robot(settings)  # refuses, saying why, on a server with no Anki behind it
    return anki_settings.save(owner, **wanted)
