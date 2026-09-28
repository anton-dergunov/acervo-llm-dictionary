"""What Anki knows about a word's scheduling, as Acervo records it.

The content goes out and the FSRS state comes back: this is the second half. One row per
*(lexeme, sense, system)*: a sense's row gathers the cards of its own note and of every example
note under it, since each asks about that one meaning; the word's row, with no sense, holds its
Listen card. Keyed by system so a second learning tool never collides with Anki.

The robot already exports everything a row needs; this decides how cards collapse into one row, what
has nowhere to go, and which rows no longer describe anything.
"""

from __future__ import annotations

from typing import Any

from acervo.domain.ids import new_record_id, now_instant

SYSTEM = "anki"

# Exported per card and deliberately not stored. `queue`, `suspended` and `flag` are Anki's own
# review furniture with no column here, and inventing columns for them means rebuilding the database
# for information Acervo does not read.
UNSTORED = ("queue", "suspended", "flag")


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def collapse(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """A note's cards as the one set of numbers a row holds.

    The Acervo note type has exactly one template, so in practice this collapses one card. The rule
    still has to be written down for the day it does not: counts add up, because every review of
    every card was a review of this word; the memory state comes from the *least stable* card,
    because that is the one that will come up first and the one that says how well the word is
    actually known; and the last review is the most recent of any of them.
    """
    if not cards:
        return {
            "reps": 0, "lapses": 0, "stability": 0.0, "difficulty": 0.0,
            "retrievability": 0.0, "lastReview": None,
        }
    weakest = min(cards, key=lambda card: _number(card.get("stability")))
    reviews = [card.get("last_review") for card in cards if card.get("last_review")]
    return {
        "reps": sum(int(card.get("reps") or 0) for card in cards),
        "lapses": sum(int(card.get("lapses") or 0) for card in cards),
        "stability": _number(weakest.get("stability")),
        "difficulty": _number(weakest.get("difficulty")),
        # Bounded to (0, 1] by the schema; a card never reviewed has no retrievability rather than a
        # zero, and zero would read as "certainly forgotten".
        "retrievability": min(1.0, max(0.0, _number(weakest.get("retrievability")))),
        "lastReview": max(reviews) if reviews else None,
    }


Key = tuple[str, str | None]


def study_states(
    exported: dict[str, Any],
    held: dict[Key, dict[str, Any]],
    live_lexemes: set[str],
    live_senses: dict[str, str],
    *,
    device_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The `studyStates` change set for one `export-state`, and the notes left out of it.

    `held` is what the account already has, by *(lexeme, sense)*, and it is what makes this an
    update rather than a first write: a record the graph holds must state the revision it was edited
    from, and must keep the id and `createdAt` it already has. `live_senses` maps each live sense to
    its word.

    A note whose word or sense the account does not hold is skipped rather than refused. That is an
    ordinary state, not a mismatch: a word removed in Acervo keeps its cards in the collection until
    someone deletes them there, and one such note must not stop the other nine hundred.

    **A held row that no note reports on any more is tombstoned.** The collection is read whole, so a
    row without cards describes a note that is gone — a collection wiped and rebuilt, or cards
    removed by hand — and keeping its numbers would report a memory that no longer exists.
    """
    at = now_instant()
    groups: dict[Key, list[dict[str, Any]]] = {}
    skipped: list[str] = []
    for note in exported.get("notes") or []:
        lexeme_id = str(note.get("lexeme_id") or "")
        if not lexeme_id:
            continue
        sense_id = note.get("sense_id") or None
        if lexeme_id not in live_lexemes or (sense_id and live_senses.get(sense_id) != lexeme_id):
            skipped.append(str(note.get("note_id") or lexeme_id))
            continue
        groups.setdefault((lexeme_id, sense_id), []).append(note)

    changes: list[dict[str, Any]] = []
    for (lexeme_id, sense_id), notes in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1] or "")):
        stored = held.get((lexeme_id, sense_id))
        # The note named after what the row reports on — the sense's own, or the word's — is the one
        # a row points at; every card of every note in the group is listed.
        own = sense_id or lexeme_id
        notes.sort(key=lambda note: (str(note.get("note_id")) != own, str(note.get("note_id"))))
        cards = [card for note in notes for card in note.get("cards") or []]
        changes.append(
            {
                "id": stored["id"] if stored else new_record_id(),
                "lexemeId": lexeme_id,
                "senseId": sense_id,
                "system": SYSTEM,
                "noteId": int(notes[0].get("anki_note_id") or 0),
                "cardIds": [int(identifier) for note in notes for identifier in note.get("card_ids") or []],
                **collapse(cards),
                "syncedAt": at,
                "deleted": False,
                "createdAt": stored["createdAt"] if stored else at,
                "editedAt": at,
                "editedBy": device_id,
                "revision": int(stored["revision"]) if stored else 0,
            }
        )
    for key, record in sorted(held.items(), key=lambda item: str(item[1].get("id"))):
        if key not in groups and not record.get("deleted"):
            changes.append({**record, "deleted": True, "editedAt": at, "editedBy": device_id,
                            "revision": int(record["revision"])})
    return changes, skipped


def held_by_key(changes: dict[str, list[dict]]) -> dict[Key, dict[str, Any]]:
    """This account's existing Anki rows, by *(lexeme, sense)*. A tombstoned one is reused rather
    than replaced: the id is still taken, and a second row for the same key is not what it means.
    Where the key holds two rows, the live one is kept."""
    found: dict[Key, dict[str, Any]] = {}
    for record in changes.get("studyStates") or []:
        if record.get("system") != SYSTEM:
            continue
        key = (str(record["lexemeId"]), record.get("senseId") or None)
        if key not in found or (found[key].get("deleted") and not record.get("deleted")):
            found[key] = record
    return found
