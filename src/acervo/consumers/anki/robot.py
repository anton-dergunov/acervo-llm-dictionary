from __future__ import annotations

import fcntl
import hashlib
import html
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from acervo.domain.ids import instant_of

from .naming import slugify_filename
from .progress import Progress
from .manifest import EMBEDDED, SyncManifest, SyncManifestNote
from .model import (
    KINDS, MEDIA_FIELDS, CardDesign, create_notetypes, install_fonts, require_notetype,
)


# Anki's `revlog.type`, by value.
REVIEW_KINDS = {0: "learn", 1: "review", 2: "relearn", 3: "filtered", 4: "manual", 5: "rescheduled"}


def _days(interval: int) -> float:
    """Anki's interval as days: positive values are days already, negative ones are seconds."""
    return float(interval) if interval >= 0 else round(-interval / 86400, 6)


class SyncSafetyError(RuntimeError):
    """An operation was refused to protect collection/review data."""


class RobotBusy(SyncSafetyError):
    """The collection is in use by another run of the robot; nothing was touched."""


class DuplicateIdentityError(RuntimeError):
    """An immutable Acervo note identity occurs more than once in Anki."""


@dataclass(frozen=True)
class RobotSettings:
    endpoint: str
    username: str
    password: str
    collection_path: Path
    backup_dir: Path
    template_dir: Path
    # How long media sync may go without moving before the robot gives up. Not a bound on the whole
    # upload: a first push sends thousands of files and takes as long as that takes.
    media_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.endpoint.endswith("/"):
            raise ValueError("The Anki sync endpoint must end with a trailing slash")
        if not self.username or not self.password:
            raise ValueError("Anki sync username and password are required")


def _sync_requirement_name(output: Any) -> str:
    names = {
        output.NO_CHANGES: "NO_CHANGES",
        output.NORMAL_SYNC: "NORMAL_SYNC",
        output.FULL_SYNC: "FULL_SYNC",
        output.FULL_DOWNLOAD: "FULL_DOWNLOAD",
        output.FULL_UPLOAD: "FULL_UPLOAD",
    }
    return names.get(output.required, f"UNKNOWN({output.required})")


class AnkiRobot:
    """A persistent headless Anki client that synchronizes before it mutates."""

    def __init__(self, settings: RobotSettings, progress: Progress | None = None):
        self.settings = settings
        self.design = CardDesign.load(settings.template_dir)
        self.progress = progress or Progress()

    @contextmanager
    def _exclusive_collection(self) -> Iterator[None]:
        self.settings.collection_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.settings.collection_path.parent / ".acervo-anki-robot.lock"
        with lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RobotBusy("The Anki robot is already running; try again when it has finished") from exc
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _open_collection(self) -> Any:
        from anki.collection import Collection

        return Collection(str(self.settings.collection_path))

    def _login(self, collection: Any) -> Any:
        return collection.sync_login(
            self.settings.username,
            self.settings.password,
            self.settings.endpoint,
        )

    def _wait_for_media(self, collection: Any) -> None:
        """Until media sync is done, saying how far it has got. Gives up only when it stops moving."""
        stall = self.settings.media_timeout_seconds
        deadline = time.monotonic() + stall
        seen = said = None
        while True:
            status = collection.media_sync_status()
            if not status.active:
                if said is not None:
                    self.progress.say("Media sync finished")
                return
            report = ", ".join(
                part for part in (status.progress.checked, status.progress.added,
                                  status.progress.removed) if part
            )
            now = time.monotonic()
            if report != seen:
                seen, deadline = report, now + stall
            if report and (said is None or now - said >= self.progress.every):
                self.progress.say(f"Media sync: {report}")
                said = now
            if now >= deadline:
                collection.abort_media_sync()
                raise TimeoutError(
                    f"Anki media synchronization made no progress for {int(stall)} seconds"
                    + (f" (last: {seen})" if seen else "")
                )
            time.sleep(0.1)

    def _normal_sync(self, collection: Any, auth: Any, *, stage: str) -> Any:
        self.progress.say(f"Anki: {stage}")
        output = collection.sync_collection(auth, sync_media=True)
        if output.required != output.NO_CHANGES:
            raise SyncSafetyError(
                f"{stage} requires {_sync_requirement_name(output)}; "
                "the robot will never choose a full-sync direction automatically"
            )
        self._wait_for_media(collection)
        return output

    def _backup(self, collection: Any, *, force: bool = True) -> bool:
        """A backup of the robot's collection. Unforced, Anki makes one only when its own interval
        has passed since the last, which is what a push every few minutes wants."""
        self.settings.backup_dir.mkdir(parents=True, exist_ok=True)
        return bool(
            collection.create_backup(
                backup_folder=str(self.settings.backup_dir),
                force=force,
                wait_for_completion=True,
            )
        )

    @staticmethod
    def _close(collection: Any) -> None:
        if getattr(collection, "db", None) is not None:
            collection.close()

    def _require_empty(self, collection: Any) -> Any:
        """Signed in, with both the robot's collection and the server's empty; else refused."""
        self.progress.say("Anki: signing in and checking the server is empty")
        auth = self._login(collection)
        if not collection.is_empty():
            raise SyncSafetyError(
                "bootstrap-upload requires an empty robot collection, and this one holds notes"
            )
        initial = collection.sync_collection(auth, sync_media=False)
        if initial.required != initial.NO_CHANGES:
            raise SyncSafetyError(
                "bootstrap-upload requires an empty Anki sync server, and this one holds a "
                "collection. A device that syncs to an empty server uploads its own, so if one "
                "synced since the reset, that is what is there: reset the Anki data again with "
                "Anki closed on every device, and open it only once the bootstrap has finished"
            )
        return auth

    def check_bootstrap(self) -> None:
        """Refuse a bootstrap now, before minutes are spent building cards it could not upload."""
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                self._require_empty(collection)
            finally:
                self._close(collection)

    def bootstrap_upload(
        self, manifest: SyncManifest, manifest_dir: Path
    ) -> dict[str, Any]:
        """Create the first server collection, accepting only FULL_UPLOAD."""
        manifest.validate_media(manifest_dir)
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                # Asked again, not trusted from `check_bootstrap`: a device may have uploaded while
                # the cards were being built.
                auth = self._require_empty(collection)
                create_notetypes(collection, self.design)
                fonts = install_fonts(collection, self.design)
                report = self._upsert(collection, manifest, manifest_dir)
                output = collection.sync_collection(auth, sync_media=False)
                if output.required != output.FULL_UPLOAD:
                    raise SyncSafetyError(
                        "bootstrap-upload expected Anki to require FULL_UPLOAD, got "
                        + _sync_requirement_name(output)
                    )
                self.progress.say("Anki: uploading the collection")
                collection.close_for_full_sync()
                collection.full_upload_or_download(
                    auth=auth,
                    server_usn=output.server_media_usn,
                    upload=True,
                )
                collection.reopen(after_full_sync=True)
                self.progress.say("Anki: collection uploaded; uploading its media")
                self._wait_for_media(collection)
                return {
                    "operation": "bootstrap-upload",
                    "sync": "full-upload-complete",
                    "fonts_added": fonts,
                    **report,
                }
            finally:
                self._close(collection)

    def adopt_server(self, *, confirm_no_other_clients: bool) -> dict[str, Any]:
        """Adopt a non-empty server and explicitly upload the new Acervo schema."""
        if not confirm_no_other_clients:
            raise SyncSafetyError(
                "adopt-server requires --confirm-no-other-clients"
            )
        if self.settings.collection_path.exists():
            raise SyncSafetyError(
                "adopt-server requires a new robot collection path; refusing to replace it"
            )
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                auth = self._login(collection)
                output = collection.sync_collection(auth, sync_media=False)
                if output.required != output.FULL_DOWNLOAD:
                    raise SyncSafetyError(
                        "adopt-server expected a non-empty server requiring FULL_DOWNLOAD, got "
                        + _sync_requirement_name(output)
                    )
                collection.close_for_full_sync()
                collection.full_upload_or_download(
                    auth=auth,
                    server_usn=output.server_media_usn,
                    upload=False,
                )
                collection.reopen(after_full_sync=True)
                self._wait_for_media(collection)
                self._backup(collection)
                create_notetypes(collection, self.design)
                install_fonts(collection, self.design)
                schema_output = collection.sync_collection(auth, sync_media=False)
                if schema_output.required not in (
                    schema_output.FULL_SYNC,
                    schema_output.FULL_UPLOAD,
                ):
                    raise SyncSafetyError(
                        "adopt-server expected a full upload choice after installing the "
                        f"Acervo note types, got {_sync_requirement_name(schema_output)}"
                    )
                collection.close_for_full_sync()
                collection.full_upload_or_download(
                    auth=auth,
                    server_usn=schema_output.server_media_usn,
                    upload=True,
                )
                collection.reopen(after_full_sync=True)
                self._wait_for_media(collection)
                return {
                    "operation": "adopt-server",
                    "sync": "full-download-and-schema-upload-complete",
                    "notes_preserved": collection.note_count(),
                }
            finally:
                self._close(collection)

    def push(self, manifest: SyncManifest, manifest_dir: Path, *, backup: bool = True) -> dict[str, Any]:
        """Sync down, update Acervo-owned notes, and sync up normally. `backup=False` leaves the
        backup to Anki's own interval rather than forcing one."""
        manifest.validate_media(manifest_dir)
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                self.progress.say("Anki: signing in")
                auth = self._login(collection)
                self._normal_sync(collection, auth, stage="pre-mutation sync")
                self.progress.say("Anki: backing up the robot's collection")
                self._backup(collection, force=backup)
                # A note type of the wrong shape is refused here, before anything is written. One of
                # the right shape but an older look is brought up to date: that is an ordinary change.
                redesigned = [
                    kind.name for kind in KINDS.values()
                    if require_notetype(collection, kind, self.design, update_design=True)[1]
                ]
                fonts = install_fonts(collection, self.design)
                report = self._upsert(collection, manifest, manifest_dir)
                self._normal_sync(collection, auth, stage="post-mutation sync")
                return {
                    "operation": "push", "sync": "complete", "redesigned": redesigned,
                    "fonts_added": fonts, **report,
                }
            finally:
                self._close(collection)

    def export_state(self, *, reviews_since: int | None = None) -> dict[str, Any]:
        """Sync down and export review state without mutating card content. With `reviews_since`,
        also every review of an Acervo card after that review id."""
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                auth = self._login(collection)
                self._normal_sync(collection, auth, stage="state-export sync")
                notes = self._notes_state(collection)
                notes.sort(key=lambda item: item["note_id"])
                exported = {
                    "operation": "export-state",
                    "sync": "complete",
                    "notes": notes,
                }
                if reviews_since is not None:
                    exported["reviews"] = self._reviews_since(collection, reviews_since)
                return exported
            finally:
                self._close(collection)

    @staticmethod
    def _reviews_since(collection: Any, since: int) -> list[dict[str, Any]]:
        """Every review Anki logged for an Acervo card after review id `since`, oldest first.

        Read straight from `revlog`, which is Anki's own record of every answer: its id is the
        review's time in milliseconds, its interval is in days when positive and in seconds when
        negative, and its type says what kind of review it was. A review of a card that no longer
        exists, or of a note Acervo did not make, has no word to belong to and is left out.
        """
        owners: dict[int, tuple[str, str | None, dict[int, str]]] = {}
        for kind in KINDS.values():
            notetype = collection.models.by_name(kind.name)
            if notetype is None:
                continue
            names = {int(template["ord"]): str(template["name"]) for template in notetype["tmpls"]}
            lexeme_at = kind.fields.index("AcervoLexemeId")
            sense_at = kind.fields.index("AcervoSenseId")
            for note_id, fields in collection.db.all(
                    "select id, flds from notes where mid = ?", notetype["id"]):
                values = fields.split("\x1f")
                owners[int(note_id)] = (values[lexeme_at], values[sense_at] or None, names)
        reviews = []
        for review_id, card_id, button, interval, last_interval, taken, kind, note_id, ordinal in \
                collection.db.all(
                    "select r.id, r.cid, r.ease, r.ivl, r.lastIvl, r.time, r.type, c.nid, c.ord "
                    "from revlog r join cards c on c.id = r.cid where r.id > ? order by r.id",
                    int(since)):
            owner = owners.get(int(note_id))
            if owner is None or not owner[0] or int(kind) not in REVIEW_KINDS:
                continue
            lexeme_id, sense_id, names = owner
            reviews.append({
                "reviewId": int(review_id),
                "cardId": int(card_id),
                "noteId": int(note_id),
                "lexemeId": lexeme_id,
                "senseId": sense_id,
                "cardType": names.get(int(ordinal), "Unknown"),
                "reviewedAt": instant_of(datetime.fromtimestamp(int(review_id) / 1000, tz=UTC)),
                "kind": REVIEW_KINDS[int(kind)],
                "button": int(button),
                "intervalDays": _days(interval),
                "lastIntervalDays": _days(last_interval),
                "durationMs": max(0, int(taken)),
            })
        return reviews

    @classmethod
    def _notes_state(cls, collection: Any) -> list[dict[str, Any]]:
        """Every Acervo note's cards and what the scheduler knows about each, by note."""
        notes = []
        for kind in KINDS.values():
            # Read-only: a collection whose cards look older is still read, not refused.
            notetype = collection.models.by_name(kind.name)
            if notetype is None:
                continue
            for anki_note_id in collection.models.nids(notetype["id"]):
                note = collection.get_note(anki_note_id)
                cards = [cls._card_state(collection, card) for card in note.cards()]
                notes.append(
                    {
                        "note_id": note["AcervoNoteId"],
                        "kind": kind.key,
                        "lexeme_id": note["AcervoLexemeId"],
                        "sense_id": note["AcervoSenseId"] or None,
                        "anki_note_id": int(note.id),
                        "card_ids": [card["anki_card_id"] for card in cards],
                        "cards": cards,
                    }
                )
        return notes

    @staticmethod
    def _card_state(collection: Any, card: Any) -> dict[str, Any]:
        memory = card.memory_state
        stability = getattr(memory, "stability", None) if memory is not None else None
        difficulty = getattr(memory, "difficulty", None) if memory is not None else None
        if stability is None and card.reps:
            try:
                computed = collection.compute_memory_state(card.id)
                stability = computed.stability
                difficulty = computed.difficulty
            except Exception:
                pass
        # Anki computes retrievability itself, from the same forgetting curve it schedules with.
        # Re-deriving it here would be a second implementation of a formula that changes with the
        # FSRS version, and getting it subtly wrong would look exactly like a correct answer.
        #
        # Only asked for when there is a memory state to compute it from. An unset protobuf float
        # reads as `0.0`, and a card whose scheduling FSRS knows nothing about would otherwise report
        # itself as certainly forgotten.
        retrievability = None
        if stability is not None:
            try:
                answer = collection.card_stats_data(card.id).fsrs_retrievability
                retrievability = float(answer) if answer else None
            except Exception:  # noqa: BLE001 - no FSRS, or no trained model; not a sync failure
                retrievability = None
        # The wire's own timestamp shape, not `isoformat()`: that gives `+00:00` and six fractional
        # digits, and the graph route accepts neither.
        last_review = (
            instant_of(datetime.fromtimestamp(card.last_review_time, tz=UTC))
            if card.last_review_time is not None
            else None
        )
        return {
            "anki_card_id": int(card.id),
            "card_type": str(card.template()["name"]),
            "reps": int(card.reps),
            "lapses": int(card.lapses),
            "queue": int(card.queue),
            "suspended": int(card.queue) == -1,
            "flag": int(card.user_flag()),
            "stability": stability,
            "difficulty": difficulty,
            "retrievability": retrievability,
            "last_review": last_review,
        }

    def _upsert(
        self, collection: Any, manifest: SyncManifest, manifest_dir: Path
    ) -> dict[str, Any]:
        notetypes = {
            key: require_notetype(collection, kind, self.design, update_design=False)[0]
            for key, kind in KINDS.items()
        }
        # Every Acervo note in the collection, of either type, by its identity. Read once, and
        # refused before anything is written if an identity occurs twice.
        existing: dict[str, Any] = {}
        for notetype in notetypes.values():
            for anki_note_id in collection.models.nids(notetype["id"]):
                note = collection.get_note(anki_note_id)
                identity = note["AcervoNoteId"]
                if identity in existing:
                    raise DuplicateIdentityError(
                        f"AcervoNoteId {identity!r} occurs more than once in Anki"
                    )
                existing[identity] = note
        for item in manifest.notes:
            held = existing.get(str(item.note_id))
            if held is not None and held.mid != notetypes[item.kind]["id"]:
                raise DuplicateIdentityError(
                    f"AcervoNoteId {item.note_id} belongs to an unexpected note type"
                )

        from anki.collection import AddNoteRequest

        created = updated = unchanged = media_added = 0
        rows: list[tuple[str, Any, str, list[int]]] = []
        additions: list[Any] = []
        changes: list[Any] = []
        moves: list[tuple[Any, int]] = []
        touched: set[int] = set()
        imported: dict[tuple[Path, str], str] = {}
        counter = self.progress.count("Anki: preparing notes", len(manifest.notes))
        for item in manifest.notes:
            identity = str(item.note_id)
            kind = KINDS[item.kind]
            note = existing.get(identity)
            is_new = note is None
            if is_new:
                note = collection.new_note(notetypes[item.kind])

            media, added = self._render_media(collection, item, manifest_dir, imported)
            media_added += added
            fields = {
                "AcervoNoteId": identity,
                "AcervoLexemeId": str(item.lexeme_id),
                "AcervoSenseId": str(item.sense_id or ""),
                **{name: media.get(name, item.fields.get(name, "")) for name in kind.content_fields},
                **{name: media.get(name, "") for name in kind.media_fields},
            }
            managed_tags = set(item.tags)
            preserved_tags = {
                tag for tag in note.tags if not tag.casefold().startswith("acervo::")
            }
            desired_tags = sorted(preserved_tags | managed_tags)
            deck_id = collection.decks.id(item.deck)
            changed = is_new or any(note[name] != value for name, value in fields.items())
            changed = changed or sorted(note.tags) != desired_tags
            card_ids_before = [int(card_id) for card_id in note.card_ids()] if not is_new else []
            deck_changed = False
            if not is_new:
                deck_changed = any(card.did != deck_id for card in note.cards())
                changed = changed or deck_changed

            for name, value in fields.items():
                note[name] = value
            note.tags = desired_tags
            if is_new:
                additions.append(AddNoteRequest(note=note, deck_id=deck_id))
                created += 1
            elif changed:
                changes.append(note)
                if deck_changed:
                    moves.append((note, deck_id))
                updated += 1
                touched.add(int(note.id))
            else:
                unchanged += 1
            rows.append((identity, note,
                         "created" if is_new else ("updated" if changed else "unchanged"),
                         card_ids_before))
            counter.step()

        # One operation each rather than one per note. Every Anki operation is its own transaction,
        # and the collection writes each one through to the disk, so a first push of thousands of
        # notes one at a time spent nearly all its time waiting on the NAS's disk. Added in manifest
        # order, which is the order Anki introduces new cards in.
        self.progress.say(f"Anki: saving {created} new and {updated} changed notes "
                          f"({unchanged} unchanged, {media_added} new media files)")
        if additions:
            collection.add_notes(additions)
        if changes:
            # A gate filled since the last push makes its card now; Anki does that on update.
            collection.update_notes(changes)
        for note, deck_id in moves:
            collection.set_deck(note.card_ids(), deck_id)
        results = [
            {
                "note_id": identity,
                "anki_note_id": int(note.id),
                "card_ids": [int(card_id) for card_id in note.card_ids()],
                "previous_card_ids": card_ids_before,
                "status": status,
            }
            for identity, note, status, card_ids_before in rows
        ]
        removed = self._remove_closed_cards(collection, touched)
        if removed:
            for result in results:
                result["card_ids"] = [card for card in result["card_ids"] if card not in removed]
        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "media_added": media_added,
            "cards_removed": len(removed),
            "notes": results,
        }

    @staticmethod
    def _remove_closed_cards(collection: Any, note_ids: set[int]) -> set[int]:
        """Cards of these notes whose gate has since been emptied.

        A sense's `Recognise` closes when it gains its first example, whose own note now asks that
        question. Anki keeps such a card, showing a blank front, until someone runs Empty Cards; it
        can no longer be answered, so its history has nothing left to describe. Only the notes this
        push updated are looked at, so nothing outside Acervo's own is ever removed.
        """
        if not note_ids:
            return set()
        report = collection.get_empty_cards()
        doomed = {
            int(card_id)
            for note in report.notes
            if int(note.note_id) in note_ids
            for card_id in note.card_ids
        }
        if doomed:
            collection.remove_cards_and_orphaned_notes(sorted(doomed))
        return doomed

    @staticmethod
    def _render_media(
        collection: Any, item: SyncManifestNote, manifest_dir: Path,
        seen: dict[tuple[Path, str], str] | None = None,
    ) -> tuple[dict[str, str], int]:
        """Each media field's file, imported under a content-addressed name, as the tag that shows
        or plays it. Returns the fields and how many files were new to the collection.

        `seen` carries the names already worked out in this push. A word's pictures appear on every
        one of its notes — each card's back shows all its senses — so without it the same files are
        read, hashed and handed to Anki again for every note that shows them."""
        rendered: dict[str, str] = {}
        added = 0
        seen = {} if seen is None else seen

        def imported(source: Path, fallback: str) -> str:
            nonlocal added
            known = seen.get((source, fallback))
            if known is not None:
                return known
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()[:20]
            suffix = source.suffix.lower()
            stem = slugify_filename(source.stem) or fallback
            desired_name = f"acervo-{digest}-{stem}{suffix}"
            # The name carries a digest of the bytes, so a file already held under it holds these.
            if not collection.media.have(desired_name):
                actual_name = collection.media.write_data(desired_name, data)
                if actual_name != desired_name:
                    raise RuntimeError(
                        f"Unexpected Anki media collision: {desired_name} became {actual_name}"
                    )
                added += 1
            seen[(source, fallback)] = html.escape(desired_name, quote=True)
            return seen[(source, fallback)]

        for field, source in item.media_sources(manifest_dir).items():
            name = imported(source, field.lower())
            rendered[field] = (
                f'<img src="{name}" alt="">'
                if MEDIA_FIELDS[field] == "image"
                else f'<audio src="{name}" preload="auto"></audio>'
            )
        names = {
            path: imported(source, "media")
            for path, source in item.embedded_sources(manifest_dir).items()
        }
        for field, text in item.fields.items():
            if names:
                rendered[field] = EMBEDDED.sub(
                    lambda found: f'src="{names.get(found.group(1), found.group(1))}"', text)
        return rendered, added


def result_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
