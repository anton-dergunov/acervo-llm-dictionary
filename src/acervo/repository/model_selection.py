"""The owner's model chains. One row per owner, or none — and none is a real answer.

Unlike `sync_state`, absence here is not a gap to be filled: no record means "use the deployment
default". Nothing creates a row eagerly and there is no `ensure_` function, so every read is a pure
read with nothing to write when it is missing — a stronger guarantee than the cursor manages, not a
weaker one. Eager creation would have to invent a value, and both candidates are wrong: `{}` is
indistinguishable from absence, and snapshotting the deployment default would freeze a server
setting at the instant the account was made.

This module stores what it is given. It does not know the providers — which exist and which models
they offer is `acervo.models`'s question, and `acervo.services.models` is where a
document is held to it. Two validators would be one drift.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction

Pairs = tuple[tuple[str, str], ...]


def _pairs(stored: Any) -> Pairs:
    """A stored kind as pairs, dropping anything malformed rather than raising.

    A hand-edited row must not take the capture path down, and `chain.resolve` refuses what it
    cannot serve anyway — so the strict reading happens where it can produce a useful message.
    """
    if not isinstance(stored, list):
        return ()
    found: list[tuple[str, str]] = []
    for entry in stored:
        if not isinstance(entry, Mapping):
            continue
        provider, model = entry.get("provider"), entry.get("model")
        if isinstance(provider, str) and isinstance(model, str) and provider and model:
            found.append((provider, model))
    return tuple(found)


def _document(stored: Any) -> dict[str, Pairs]:
    """Kept empty lists and all: `[]` means "every model switched off", which is a choice.

    Dropping it would turn switching everything off into having chosen nothing, and the server would
    quietly carry on building entries with its own order.
    """
    if not isinstance(stored, Mapping):
        return {}
    return {kind: _pairs(value) for kind, value in stored.items() if isinstance(value, list)}


def chains(owner: str) -> dict[str, Pairs]:
    """This owner's chains by kind.

    A kind absent from the result means nothing has been chosen for it, and the deployment default
    applies. A kind present but **empty** means every model was switched off on purpose. The two are
    different answers and the caller must not collapse them.
    """
    with reading() as connection:
        row = connection.execute(
            select(tables.model_selection).where(tables.model_selection.c.owner == owner)
        ).mappings().first()
    return _document(row["chains"]) if row is not None else {}


def save(owner: str, changes: Mapping[str, Sequence[tuple[str, str]] | None]) -> dict[str, Pairs]:
    """Change only the kinds named. `None` forgets one, and the row goes when nothing is left.

    Forgetting matters: without it, once an owner has saved there is no way back to following the
    providers' own order, because unchecking everything is refused as an empty chain. The two states
    genuinely differ — when a provider is added, a defaulted owner picks it up and an owner who once
    chose explicitly does not.

    Read-modify-write inside one `transaction()`, which is `BEGIN IMMEDIATE`, so check-then-insert
    cannot interleave with a second save and the unique index is never reached in anger. Returns the
    whole stored document, so a caller echoes what is on disk without a read-after-write.
    """
    with transaction() as connection:
        row = connection.execute(
            select(tables.model_selection).where(tables.model_selection.c.owner == owner)
        ).mappings().first()

        document = _document(row["chains"]) if row is not None else {}
        for kind, pairs in changes.items():
            if pairs is None:
                document.pop(kind, None)
            else:
                document[kind] = tuple((provider, model) for provider, model in pairs)

        stored = {
            kind: [{"provider": provider, "model": model} for provider, model in pairs]
            for kind, pairs in document.items()
        }

        if not stored:
            if row is not None:
                connection.execute(
                    tables.model_selection.delete().where(
                        tables.model_selection.c.id == row["id"]
                    )
                )
            return {}

        if row is None:
            connection.execute(
                tables.model_selection.insert().values(
                    id=new_record_id(), owner=owner, chains=stored, edited_at=now_instant()
                )
            )
        else:
            connection.execute(
                tables.model_selection.update()
                .where(tables.model_selection.c.id == row["id"])
                .values(chains=stored, edited_at=now_instant())
            )
        return document
