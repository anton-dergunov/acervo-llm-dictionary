"""The owner-scoped graph: the cursor, revision allocation, the merge, and the tombstone sweep.

One strictly increasing sequence per owner, shared by all eleven tables and never one per table. A
record left at revision zero is invisible to every `revision > cursor` pull, permanently and
silently — the failure has no symptom until someone notices a word missing on another device weeks
later. The hook this replaces allocated in a save hook because the write route was not the only
writer; with the database in this process it collapses into one function every writer calls.

The sequence row's *id* is the dataset identity. Rebuilding the database mints a new one, which is
the only thing that stops a client asking for revisions the new database has not reached yet.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, func, or_, select

from acervo import notify
from acervo.db import tables
from acervo.db.tables import TABLES
from acervo.domain import validation
from acervo.domain.ids import DEVICE_ID, is_instant, is_record_id, new_record_id, now_instant
from acervo.domain.projection import (
    COLLECTION_BY_KEY,
    COLLECTIONS,
    WORD_COLLECTIONS,
    Collection,
    projected,
)
from acervo.errors import ApiError, RecordRefused
from acervo.repository import anki_settings, jobs
from acervo.repository.session import reading, transaction
from acervo.domain import SCHEMA_VERSION


# ── the cursor ──────────────────────────────────────────────────────────────


def _read_sequence(connection: Connection, owner: str) -> Mapping[str, Any] | None:
    return connection.execute(
        select(tables.sync_state).where(tables.sync_state.c.owner == owner)
    ).mappings().first()


def ensure_sequence(connection: Connection, owner: str) -> Mapping[str, Any]:
    """The owner's cursor row, created if this account somehow has none.

    `accounts.create` makes it, which is what lets a pull be a pure read. This exists for the account
    that predates that — it costs a write only in a case that should not happen, rather than on the
    most frequent request in the system.
    """
    row = _read_sequence(connection, owner)
    if row is not None:
        return row
    connection.execute(
        tables.sync_state.insert().values(id=new_record_id(), owner=owner, sequence=0)
    )
    return _read_sequence(connection, owner)  # type: ignore[return-value]


def allocate_revision(connection: Connection, owner: str) -> int:
    """Take this owner's next revision, in the transaction that writes the record it numbers."""
    row = ensure_sequence(connection, owner)
    following = int(row["sequence"]) + 1
    connection.execute(
        tables.sync_state.update()
        .where(tables.sync_state.c.id == row["id"])
        .values(sequence=following)
    )
    return following


# ── reading ─────────────────────────────────────────────────────────────────


def _owner_records(
    connection: Connection, collection: Collection, owner: str, since: int
) -> list[dict[str, Any]]:
    table = collection.table
    rows = connection.execute(
        select(table)
        .where(table.c.owner == owner, table.c.revision > since)
        .order_by(table.c.revision)
    ).mappings()
    return [projected(collection, row) for row in rows]


def _envelope(connection: Connection, owner: str, sequence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "datasetId": sequence["id"],
        "cursor": int(sequence["sequence"]),
        "serverTime": now_instant(),
    }


def pull(owner: str, since: int) -> dict[str, Any]:
    """Everything this owner holds past `since`, in revision order. Tombstones included."""
    with reading() as connection:
        sequence = _read_sequence(connection, owner)
    if sequence is None:
        with transaction() as connection:
            sequence = ensure_sequence(connection, owner)
    with reading() as connection:
        return {
            **_envelope(connection, owner, sequence),
            "changes": {
                collection.key: _owner_records(connection, collection, owner, since)
                for collection in COLLECTIONS
            },
        }


# ── writing ─────────────────────────────────────────────────────────────────


def require_device(value: Any) -> str:
    device = "" if value is None else str(value).strip()
    if not DEVICE_ID.match(device):
        raise ApiError(400, "invalid_input", "A valid device identifier is required.")
    return device


def require_schema_version(value: Any) -> None:
    try:
        given = int(value)
    except (TypeError, ValueError):
        given = -1
    if given != SCHEMA_VERSION:
        raise ApiError(
            409,
            "schema_version_mismatch",
            "This copy of Acervo is out of date and cannot synchronise. Update the app to continue.",
        )


def _require_instant(value: Any, label: str) -> str:
    instant = "" if value is None else str(value).strip()
    if not is_instant(instant):
        raise ApiError(
            400, "invalid_input", f"{label} must be an ISO-8601 UTC timestamp with milliseconds."
        )
    return instant


def _owned_or_free(
    connection: Connection, collection: Collection, owner: str, identifier: str
) -> Mapping[str, Any] | None:
    """The record this owner holds under `id`, or None. An id held by somebody else is a hard stop."""
    table = collection.table
    owned = connection.execute(
        select(table).where(table.c.id == identifier, table.c.owner == owner)
    ).mappings().first()
    if owned is not None:
        return owned
    # The second lookup. Skipping it is a silent cross-owner write.
    foreign = connection.execute(
        select(table.c.id).where(table.c.id == identifier)
    ).first()
    if foreign is not None:
        raise ApiError(400, "id_conflict", "That record identifier is already in use.")
    return None


def _lookup(connection: Connection):
    def find(name: str, identifier: str) -> Mapping[str, Any] | None:
        table = TABLES[name]
        return connection.execute(
            select(table).where(table.c.id == identifier)
        ).mappings().first()

    return find


# Brings the photo an attestation names into place: `(owner, reference) -> undo`. Supplied by the
# caller, because the files are the service layer's and this module never learns where media lives.
PlacePhoto = Callable[[str, str], Callable[[], None]]


def merge_record(
    connection: Connection,
    collection: Collection,
    owner: str,
    device: str,
    value: Mapping[str, Any],
    place_photo: PlacePhoto | None = None,
    undo: list[Callable[[], None]] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Apply one client record. Returns it, and whether it has just come into being.

    A record comes into being when it is inserted, and also when a tombstone is revived — a derived
    or re-used id makes those the same event for whoever needs to react to it.

    The whole batch is refused if anything here raises: a save is one article, and half an article is
    worse than none.
    """
    identifier = str(value.get("id") or "").strip()
    if not is_record_id(identifier):
        raise ApiError(400, "invalid_input", "Record ids must be 15 lowercase letters or digits.")
    stored = _owned_or_free(connection, collection, owner, identifier)
    try:
        claimed = int(value.get("revision") or 0)
    except (TypeError, ValueError):
        claimed = 0
    if stored is not None:
        if claimed != int(stored["revision"]):
            raise ApiError(
                409,
                "stale_record",
                "This entry was changed somewhere else. Refresh to see the current version, then "
                "try again.",
            )
    elif claimed != 0:
        # The client believes it is editing a record this database has never held. Nothing is ever
        # hard-deleted, so this means its cursor belongs to a different database.
        raise ApiError(
            409, "stale_record", "This entry no longer exists on the server. Refresh and try again."
        )

    row: dict[str, Any] = {
        "id": identifier,
        "owner": owner,
        # Set once, at insert, and never touched again.
        "created_at": stored["created_at"] if stored is not None
        else _require_instant(value.get("createdAt"), "Creation timestamp"),
        **collection.assign(value),
        "deleted": value.get("deleted") is True,
        "edited_at": _require_instant(value.get("editedAt"), "Change timestamp"),
        "edited_by": device,
    }

    try:
        validation.validate(collection.name, row, _lookup(connection))
    except RecordRefused as refusal:
        # The caller's mistake, not the server's, and it must abort the whole batch.
        raise ApiError(
            400, "invalid_record", f"{collection.key} {identifier}: {refusal}"
        ) from refusal

    if collection.key == "attestations":
        _photo_in_place(row, stored, place_photo, undo)

    row["revision"] = allocate_revision(connection, owner)
    table = collection.table
    if stored is None:
        connection.execute(table.insert().values(**row))
    else:
        # Never the key itself. With foreign keys on, SQLite treats `SET id = <the same id>` as a key
        # change and scans every child index for rows pointing at the old one — seven for a lexeme,
        # and the whole `image_prompts` table for an example.
        unchanged = {"id", "owner"}
        connection.execute(
            table.update()
            .where(table.c.id == identifier)
            .values(**{key: value for key, value in row.items() if key not in unchanged})
        )
    arrived = (stored is None or bool(stored["deleted"])) and not row["deleted"]
    return projected(collection, row), arrived


def _photo_in_place(
    row: Mapping[str, Any],
    stored: Mapping[str, Any] | None,
    place_photo: PlacePhoto | None,
    undo: list[Callable[[], None]] | None,
) -> None:
    """A row may not name a photo that is not on disk, so naming a new one is what puts it there.

    The photo is uploaded before any row names it and waits, pending, until a save does; the save is
    what moves it into place, inside this transaction, so the row and the file land together or not
    at all (`services/photo.py`). A reference that is already stored is not looked at again, which
    keeps an edit of the sentence, or a tombstone, from depending on the file system.
    """
    reference = str(row.get("photo_ref") or "")
    if not reference or row.get("deleted") or reference == ((stored or {}).get("photo_ref") or ""):
        return
    if place_photo is None:
        raise ApiError(400, "photo_missing", "This write cannot bring a photo with it.")
    reverse = place_photo(str(row["owner"]), reference)
    if undo is not None:
        undo.append(reverse)


@dataclass(frozen=True)
class Enqueue:
    """What a write that creates a word, or a sense of one, asks the server to do about it.

    `merge_graph` enqueues `enrich` in the **same transaction** as the write, which is what lets a
    save start enrichment without a queue ever being the only record that work is needed
    (`docs/architecture/jobs.md`). A client never asks for enrichment; it saves.
    """

    trigger: str = "save"
    parent: str | None = None


SAVE = Enqueue()


def _live_lexeme(connection: Connection, owner: str, lexeme_id: str) -> bool:
    return connection.execute(
        select(tables.lexemes.c.id).where(
            tables.lexemes.c.id == lexeme_id,
            tables.lexemes.c.owner == owner,
            tables.lexemes.c.deleted.is_(False),
        )
    ).first() is not None


def merge_graph(
    owner: str,
    device: str,
    changes: Mapping[str, Any],
    *,
    enqueue: Enqueue | None = SAVE,
    place_photo: PlacePhoto | None = None,
) -> dict[str, Any]:
    """Apply a change set in graph order, so a record's relations always resolve before it lands.

    A word that arrives, or gains a sense, is enqueued for enrichment in the same transaction unless
    `enqueue` is None — which is what an enrichment's own writes pass, and a bundle import that
    restores pictures before it asks for the rest. Editing a sense's text enqueues nothing: a picture
    that no longer fits is the owner's call, through Redraw.

    `place_photo` is what lets an attestation name a newly taken photo; without it such a write is
    refused. Whatever it moved is moved back if the transaction does not commit.

    A write to anything the Anki cards are made from also queues a push, when the owner has that on,
    in the same transaction and whatever `enqueue` says: a picture an enrichment draws changes a card
    as surely as an edit does. The push waits for the writes to stop (`jobs.enqueue_later`).
    """
    queued: list[dict[str, Any]] = []
    undo: list[Callable[[], None]] = []
    try:
        result, queued = _merged(owner, device, changes, enqueue, place_photo, undo)
    except BaseException:
        for reverse in reversed(undo):
            reverse()
        raise
    for job in queued:
        notify.queued(owner, job)
    notify.revision(owner, result["cursor"])
    return result


def _merged(
    owner: str,
    device: str,
    changes: Mapping[str, Any],
    enqueue: Enqueue | None,
    place_photo: PlacePhoto | None,
    undo: list[Callable[[], None]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    queued: list[dict[str, Any]] = []
    with transaction() as connection:
        written: dict[str, list[dict[str, Any]]] = {}
        words: dict[str, None] = {}
        for collection in COLLECTIONS:
            rows = []
            for value in changes.get(collection.key) or []:
                if not isinstance(value, Mapping):
                    continue
                record, arrived = merge_record(
                    connection, collection, owner, device, value, place_photo, undo
                )
                rows.append(record)
                if arrived and collection.key == "lexemes":
                    words[record["id"]] = None
                elif arrived and collection.key == "senses":
                    words[record["lexemeId"]] = None
            written[collection.key] = rows
        if any(written.get(key) for key in anki_settings.READ_BY_CARDS) and \
                anki_settings.pushing(connection, owner):
            push = jobs.enqueue_later(connection, owner, anki_settings.PUSH, trigger="save",
                                      subject_kind=anki_settings.SUBJECT, subject_id="push")
        else:
            push = None
        if enqueue is not None:
            queued = [
                jobs.enqueue_enrich(
                    connection, owner, lexeme_id, trigger=enqueue.trigger, parent=enqueue.parent
                )
                for lexeme_id in words
                if _live_lexeme(connection, owner, lexeme_id)
            ]
        sequence = ensure_sequence(connection, owner)
        result = {
            **_envelope(connection, owner, sequence),
            "records": written,
            # Which job will enrich each word this write created, so the caller can follow it.
            "enrich": {job["subject"]["id"]: job["id"] for job in queued},
        }
    return result, queued + ([push] if push else [])


def tombstone_all_words(owner: str, device: str) -> dict[str, Any]:
    """Tombstone every word and its descendants, retaining language and topic configuration.

    Loops go too, although they hang off no word: a loop every one of whose captions names a deleted
    word is a track nothing describes. That falls out of `WORD_COLLECTIONS` rather than being coded
    here, because loops sit last in `COLLECTIONS`.
    """
    at = now_instant()
    with transaction() as connection:
        count = 0
        for collection in WORD_COLLECTIONS:
            table = collection.table
            rows = connection.execute(
                select(table.c.id).where(table.c.owner == owner, table.c.deleted.is_(False))
            ).scalars().all()
            for identifier in rows:
                connection.execute(
                    table.update()
                    .where(table.c.id == identifier)
                    .values(
                        deleted=True,
                        edited_at=at,
                        edited_by=device,
                        # Each tombstone is a change like any other, so the cursor advances by one
                        # per record and every device learns about all of them.
                        revision=allocate_revision(connection, owner),
                    )
                )
                count += 1
        sequence = ensure_sequence(connection, owner)
        result = {**_envelope(connection, owner, sequence), "deleted": count}
    notify.revision(owner, result["cursor"])
    return result


# ── what capture needs to know about the owner ──────────────────────────────


def owner_vocabularies(owner: str) -> list[dict[str, Any]]:
    table = tables.vocabularies
    with reading() as connection:
        rows = connection.execute(
            select(table)
            .where(table.c.owner == owner, table.c.deleted.is_(False))
            .order_by(table.c.vocab_order)
        ).mappings()
        return [
            {
                "language": row["language"],
                "definitionLang": row["definition_lang"],
                "glossLangs": list(row["gloss_langs"] or []),
                "notesLang": row["notes_lang"],
                "displayName": (row["display_name"] or "").strip() or None,
            }
            for row in rows
        ]


def owner_topics(owner: str) -> list[dict[str, Any]]:
    table = tables.topics
    with reading() as connection:
        rows = connection.execute(
            select(table.c.id, table.c.name)
            .where(table.c.owner == owner, table.c.deleted.is_(False))
            .order_by(table.c.topic_order)
        ).mappings()
        return [{"id": row["id"], "name": row["name"]} for row in rows]


def duplicate_lexemes(owner: str, language: str, headword: str, lemma: str) -> list[dict[str, Any]]:
    """Words this owner already holds under either form.

    Case-insensitive, because the learner types `picar` and the store holds `Picar` just as often.
    """
    forms = [form.strip().lower() for form in (headword, lemma) if form and form.strip()]
    if not forms:
        return []
    table = tables.lexemes
    with reading() as connection:
        rows = connection.execute(
            select(table.c.id, table.c.headword, table.c.short_gloss)
            .where(
                table.c.owner == owner,
                table.c.language == language,
                table.c.deleted.is_(False),
                or_(
                    func.lower(table.c.headword).in_(forms),
                    func.lower(table.c.lemma).in_(forms),
                ),
            )
        ).mappings()
        return [
            {
                "id": row["id"],
                "headword": row["headword"],
                "shortGloss": (row["short_gloss"] or "").strip() or None,
            }
            for row in rows
        ]


def map_senses(owner: str, language: str) -> list[dict[str, Any]]:
    """Every live sense of every word this owner holds in one language, for the meaning map.

    A suppressed word is one the owner said they do not want, so it is not on their map; every other
    status is a word they hold. Senses carry no language of their own, so the word is joined in, and
    the rows come back in a stable order so a map's input is the same list every time it is read.
    """
    lexemes, senses = tables.lexemes, tables.senses
    with reading() as connection:
        rows = connection.execute(
            select(
                senses.c.id, senses.c.lexeme, senses.c.definition, senses.c.glosses,
                senses.c.sense_order, lexemes.c.headword, lexemes.c.pos,
            )
            .select_from(senses.join(lexemes, senses.c.lexeme == lexemes.c.id))
            .where(
                lexemes.c.owner == owner,
                senses.c.owner == owner,
                lexemes.c.language == language,
                lexemes.c.deleted.is_(False),
                senses.c.deleted.is_(False),
                lexemes.c.status != "suppressed",
            )
            .order_by(lexemes.c.id, senses.c.sense_order, senses.c.id)
        ).mappings()
        return [
            {
                "sense": row["id"],
                "lexeme": row["lexeme"],
                "headword": row["headword"],
                "pos": row["pos"],
                "definition": row["definition"],
                "glosses": list(row["glosses"] or []),
                "order": row["sense_order"],
            }
            for row in rows
        ]


def article_records(owner: str, lexeme_id: str) -> dict[str, list[dict[str, Any]]]:
    """One word and everything hanging off it, in the wire shape `build_articles` reads.

    The second feeder for `acervo.article`. The worker sweep builds its `ArticleView`s from a
    `client.pull_graph()` payload; the request path has the database right here and a pull of the
    whole graph to draw one picture would be absurd — so both produce the same `changes` mapping and
    neither knows which it was given. One view model, two feeders, exactly as `articleFor` and
    `articleFromDraft` work on the client.

    Tombstones are included rather than filtered, because `live()` in that module is what drops
    them and doing it twice in two places is how the two feeders would come to disagree.
    """
    wanted = {
        "lexemes": tables.lexemes.c.id,
        "senses": tables.senses.c.lexeme,
        "attestations": tables.attestations.c.lexeme,
        "imagePrompts": tables.image_prompts.c.lexeme,
        "pronunciations": tables.pronunciations.c.lexeme,
        "studyStates": tables.study_states.c.lexeme,
    }
    changes: dict[str, list[dict[str, Any]]] = {collection.key: [] for collection in COLLECTIONS}
    with reading() as connection:
        for key, column in wanted.items():
            collection = COLLECTION_BY_KEY[key]
            rows = connection.execute(
                select(collection.table).where(
                    collection.table.c.owner == owner, column == lexeme_id
                )
            ).mappings()
            changes[key] = [projected(collection, row) for row in rows]

        # Examples hang off senses, so they are reached through the ids just read rather than by a
        # join — which keeps this a query per collection and the shapes identical to a pull's.
        sense_ids = [sense["id"] for sense in changes["senses"]]
        if sense_ids:
            collection = COLLECTION_BY_KEY["examples"]
            rows = connection.execute(
                select(collection.table).where(
                    collection.table.c.owner == owner,
                    collection.table.c.sense.in_(sense_ids),
                )
            ).mappings()
            changes["examples"] = [projected(collection, row) for row in rows]

        collection = COLLECTION_BY_KEY["vocabularies"]
        rows = connection.execute(
            select(collection.table).where(collection.table.c.owner == owner)
        ).mappings()
        changes["vocabularies"] = [projected(collection, row) for row in rows]
    return changes


def sense_record(owner: str, sense_id: str) -> dict[str, Any] | None:
    """One live sense this owner holds, in the wire shape, or nothing.

    Nothing covers "no such sense", "somebody else's" and "deleted" alike, for `image_prompt`'s
    reason: telling them apart would answer whether an id exists in another account.
    """
    collection = COLLECTION_BY_KEY["senses"]
    with reading() as connection:
        row = connection.execute(
            select(collection.table).where(
                collection.table.c.id == sense_id,
                collection.table.c.owner == owner,
                collection.table.c.deleted.is_(False),
            )
        ).mappings().first()
    return projected(collection, row) if row is not None else None


def image_prompt(owner: str, prompt_id: str) -> dict[str, Any] | None:
    """One image prompt this owner holds, in the wire shape, or nothing.

    Nothing covers three cases the caller must not tell apart: no such row, a row belonging to
    somebody else, and a tombstone. Distinguishing them would answer "does this id exist in another
    account", which is not a question an owner-scoped route may answer.
    """
    collection = COLLECTION_BY_KEY["imagePrompts"]
    with reading() as connection:
        row = connection.execute(
            select(collection.table).where(
                collection.table.c.id == prompt_id,
                collection.table.c.owner == owner,
                collection.table.c.deleted.is_(False),
            )
        ).mappings().first()
    return projected(collection, row) if row is not None else None


def lexeme_of(owner: str, kind: str, identifier: str) -> str | None:
    """The word a live record of this owner's belongs to, or nothing.

    For a pronunciation route, which is addressed by the record it reads and needs the word before
    it can assemble anything. Nothing covers a missing, deleted or foreign record alike.
    """
    with reading() as connection:
        if kind == "lexeme":
            table = tables.lexemes
            column = table.c.id
        elif kind in ("sense", "attestation"):
            table = tables.senses if kind == "sense" else tables.attestations
            column = table.c.lexeme
        elif kind == "example":
            examples, senses = tables.examples, tables.senses
            return connection.execute(
                select(senses.c.lexeme)
                .select_from(examples.join(senses, examples.c.sense == senses.c.id))
                .where(
                    examples.c.id == identifier, examples.c.owner == owner,
                    examples.c.deleted.is_(False), senses.c.deleted.is_(False),
                )
            ).scalar()
        else:
            return None
        return connection.execute(
            select(column).where(
                table.c.id == identifier, table.c.owner == owner, table.c.deleted.is_(False)
            )
        ).scalar()


def pronunciation(owner: str, pronunciation_id: str) -> dict[str, Any] | None:
    """One pronunciation this owner holds, in the wire shape, tombstones included, or nothing.

    Tombstones are returned, unlike `image_prompt`, because the id is derived: recording a target
    again after its clip was removed must revive that row at its stored revision, and a writer that
    could not see the tombstone would mint an insert the database already holds.
    """
    collection = COLLECTION_BY_KEY["pronunciations"]
    with reading() as connection:
        row = connection.execute(
            select(collection.table).where(
                collection.table.c.id == pronunciation_id, collection.table.c.owner == owner
            )
        ).mappings().first()
    return projected(collection, row) if row is not None else None


def loop_items(owner: str, loop_id: str) -> list[dict[str, Any]]:
    """The words of one loop this owner holds, in the wire shape, in the order they are heard."""
    collection = COLLECTION_BY_KEY["loopItems"]
    table = collection.table
    with reading() as connection:
        rows = connection.execute(
            select(table)
            .where(table.c.owner == owner, table.c.loop == loop_id)
            .order_by(table.c.item_order, table.c.id)
        ).mappings()
        return [projected(collection, row) for row in rows]


def loop_cues(owner: str, loop_id: str) -> list[dict[str, Any]]:
    """The lines of one loop this owner holds, in the wire shape, in the order they are heard."""
    collection = COLLECTION_BY_KEY["loopCues"]
    table = collection.table
    with reading() as connection:
        rows = connection.execute(
            select(table)
            .where(table.c.owner == owner, table.c.loop == loop_id)
            .order_by(table.c.cue_order, table.c.id)
        ).mappings()
        return [projected(collection, row) for row in rows]


def next_loop_position(owner: str, language: str) -> int:
    """Where a new loop goes: after the last one in this language.

    Sparse and renumbered on reorder, with no uniqueness constraint — that is the data rule, and two
    loops that happened to land on one number are an ordering to tidy rather than a write to refuse.
    """
    table = tables.loops
    with reading() as connection:
        highest = connection.execute(
            select(func.max(table.c.loop_order)).where(
                table.c.owner == owner, table.c.language == language, table.c.deleted.is_(False)
            )
        ).scalar()
    return int(highest or 0) + 1


def _children_of(owner: str, key: str, parent: str, story_id: str) -> list[dict[str, Any]]:
    """One story's rows of a collection, in the order they are read.

    The two readers below are one function because they differ only in which table they open —
    `loop_items` above is written out separately because nothing else shares its shape, and two
    copies of this would have been two places to fix an ordering.
    """
    collection = COLLECTION_BY_KEY[key]
    table = collection.table
    with reading() as connection:
        rows = connection.execute(
            select(table)
            .where(table.c.owner == owner, table.c.story == story_id)
            .order_by(table.c[parent], table.c.id)
        ).mappings()
        return [projected(collection, row) for row in rows]


def story_parts(owner: str, story_id: str) -> list[dict[str, Any]]:
    """The parts of one story this owner holds, in the order they are read."""
    return _children_of(owner, "storyParts", "part_order", story_id)


def story_words(owner: str, story_id: str) -> list[dict[str, Any]]:
    """The words one story was asked to teach, in the order they were asked for."""
    return _children_of(owner, "storyWords", "word_order", story_id)


def next_story_position(owner: str, language: str) -> int:
    """Where a new story goes: after the last one in this language. See `next_loop_position`."""
    table = tables.stories
    with reading() as connection:
        highest = connection.execute(
            select(func.max(table.c.story_order)).where(
                table.c.owner == owner, table.c.language == language, table.c.deleted.is_(False)
            )
        ).scalar()
    return int(highest or 0) + 1


def owned_records(owner: str, key: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """This owner's records of one collection by id, tombstones included, in the wire shape.

    For a save that has to know whether an id it was handed belongs to the entry being saved, to a
    different one, or to nothing. An id another account holds is simply absent here; the merge
    refuses it on its own.
    """
    wanted = sorted({identifier for identifier in ids if identifier})
    if not wanted:
        return {}
    collection = COLLECTION_BY_KEY[key]
    with reading() as connection:
        rows = connection.execute(
            select(collection.table).where(
                collection.table.c.owner == owner, collection.table.c.id.in_(wanted)
            )
        ).mappings()
        return {row["id"]: projected(collection, row) for row in rows}


def held_ids(owner: str) -> set[str]:
    """Every record id this owner already holds, across all eleven tables."""
    found: set[str] = set()
    with reading() as connection:
        for collection in COLLECTIONS:
            table = collection.table
            found.update(
                connection.execute(select(table.c.id).where(table.c.owner == owner)).scalars()
            )
    return found
