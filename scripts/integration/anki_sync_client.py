#!/usr/bin/env python3
"""Independent headless client used by the Docker integration suite."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from anki.collection import Collection


def wait_media(collection: Collection, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while True:
        status = collection.media_sync_status()
        if not status.active:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("media sync timed out")
        time.sleep(0.1)


def login(collection: Collection, args: argparse.Namespace):
    return collection.sync_login(args.username, args.password, args.endpoint)


def download(collection: Collection, auth, args: argparse.Namespace) -> None:
    output = collection.sync_collection(auth, sync_media=False)
    if output.required != output.FULL_DOWNLOAD:
        raise AssertionError(f"expected FULL_DOWNLOAD, got {output.required}")
    collection.close_for_full_sync()
    collection.full_upload_or_download(
        auth=auth, server_usn=output.server_media_usn, upload=False
    )
    collection.reopen(after_full_sync=True)
    collection.sync_media(auth)
    wait_media(collection)


def normal_sync(collection: Collection, auth) -> None:
    output = collection.sync_collection(auth, sync_media=True)
    if output.required != output.NO_CHANGES:
        raise AssertionError(f"normal sync required {output.required}")
    wait_media(collection)


def snapshot(collection: Collection) -> dict:
    notes = []
    notetype = collection.models.by_name("Acervo Meaning")
    if notetype:
        for note_id in collection.models.nids(notetype["id"]):
            note = collection.get_note(note_id)
            cards = note.cards()
            shown = "".join(note[name] for name in ("Picture", "HeadwordAudio", "SentenceAudio"))
            notes.append(
                {
                    "note_id": note["AcervoNoteId"],
                    "sentence": note["Sentence"],
                    "translation": note["Translation"],
                    "tags": sorted(note.tags),
                    "anki_note_id": int(note.id),
                    "card_ids": [int(card.id) for card in cards],
                    "reps": [int(card.reps) for card in cards],
                    "lapses": [int(card.lapses) for card in cards],
                    "flags": [int(card.user_flag()) for card in cards],
                    "media": sorted(collection.media.files_in_str(note.mid, shown)),
                }
            )
    return {"notes": sorted(notes, key=lambda item: item["note_id"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["download", "sync", "review-state", "schema-drift"])
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--username", default=os.environ.get("ACERVO_ANKI_SYNC_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("ACERVO_ANKI_SYNC_PASSWORD"))
    parser.add_argument("--collection", type=Path, required=True)
    args = parser.parse_args()
    if not args.username or not args.password:
        parser.error("sync credentials must be provided through flags or the environment")
    args.collection.parent.mkdir(parents=True, exist_ok=True)
    collection = Collection(str(args.collection))
    try:
        auth = login(collection, args)
        if args.command == "download":
            download(collection, auth, args)
        elif args.command == "sync":
            normal_sync(collection, auth)
        elif args.command == "review-state":
            normal_sync(collection, auth)
            notetype = collection.models.by_name("Acervo Meaning")
            note_id = collection.models.nids(notetype["id"])[0]
            card = collection.get_note(note_id).cards()[0]
            card.reps = 9
            card.lapses = 3
            card.flags = (card.flags & ~0b111) | 2
            collection.update_card(card)
            normal_sync(collection, auth)
        else:
            normal_sync(collection, auth)
            # A change of shape, not of look: a push brings an older look up to date by itself,
            # and only a field or card type it did not make is what it must refuse.
            notetype = collection.models.by_name("Acervo Meaning")
            collection.models.add_field(notetype, collection.models.new_field("Drift"))
            collection.models.update_dict(notetype)
            collection.set_schema_modified()
            output = collection.sync_collection(auth, sync_media=False)
            if output.required not in (output.FULL_SYNC, output.FULL_UPLOAD):
                raise AssertionError(f"expected full sync after schema drift, got {output.required}")
            collection.close_for_full_sync()
            collection.full_upload_or_download(
                auth=auth, server_usn=output.server_media_usn, upload=True
            )
            collection.reopen(after_full_sync=True)
        print(json.dumps(snapshot(collection), sort_keys=True))
        return 0
    finally:
        if collection.db is not None:
            collection.close()


if __name__ == "__main__":
    raise SystemExit(main())
