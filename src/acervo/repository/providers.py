"""The providers this server may call: their rows, without their keys.

This module stores documents it is given. Whether a document is a provider that can be used is the
family's question, asked in `acervo.services.providers` before anything reaches here; this module
cannot import `acervo.models` and does not need to. The keys are in `services/provider_secrets.py`'s
file, never in a row.

**Removing a provider removes it from every order and every voice choice, in the same
transaction.** A pair naming a provider that no longer exists is refused when a chain is walked —
it is a state nothing is supposed to produce — so leaving one behind would stop every capture until
the owner noticed which order still named it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select

from acervo.db import tables
from acervo.domain.ids import now_instant
from acervo.repository.session import reading, transaction

# Exactly what a row holds besides its bookkeeping, and what `add` and `change` accept.
FIELDS = ("family", "label", "settings", "models", "extra")


def listing() -> list[dict[str, Any]]:
    """Every provider, in the order they were added."""
    with reading() as connection:
        rows = connection.execute(
            select(tables.providers).order_by(tables.providers.c.position)
        ).mappings().all()
    return [dict(row) for row in rows]


def get(identifier: str) -> dict[str, Any] | None:
    with reading() as connection:
        row = connection.execute(
            select(tables.providers).where(tables.providers.c.id == identifier)
        ).mappings().first()
    return dict(row) if row is not None else None


def add(identifier: str, document: Mapping[str, Any], check: Mapping[str, Any]) -> dict[str, Any] | None:
    """Store a new provider after every other, with the check that let it in. None when the id is taken.

    Check-then-insert inside one `BEGIN IMMEDIATE`, so two adds cannot take one id or one position.
    """
    now = now_instant()
    with transaction() as connection:
        taken = connection.execute(
            select(tables.providers.c.id).where(tables.providers.c.id == identifier)
        ).first()
        if taken is not None:
            return None
        last = connection.execute(select(func.max(tables.providers.c.position))).scalar()
        row = {
            "id": identifier,
            **{name: document[name] for name in FIELDS},
            "position": (last or 0) + 1,
            "check": dict(check),
            "checked_at": now,
            "created_at": now,
            "edited_at": now,
        }
        connection.execute(tables.providers.insert().values(**row))
    return row


def change(identifier: str, document: Mapping[str, Any], check: Mapping[str, Any] | None = None, *,
           dropped: Mapping[str, Sequence[str]] | None = None,
           dropped_voices: Sequence[str] = ()) -> dict[str, Any] | None:
    """Replace what the owner may change, and forget the models it no longer offers.

    `dropped` is the models taken away, by the order that drew on them; `dropped_voices` the voice
    models among them. A new check is recorded with the change when one was made.
    """
    now = now_instant()
    values: dict[str, Any] = {name: document[name] for name in FIELDS if name != "family"}
    values["edited_at"] = now
    if check is not None:
        values["check"] = dict(check)
        values["checked_at"] = now
    with transaction() as connection:
        changed = connection.execute(
            tables.providers.update().where(tables.providers.c.id == identifier).values(**values)
        ).rowcount
        if changed and (dropped or dropped_voices):
            _forget(connection, identifier, dropped or {}, set(dropped_voices), now)
    return get(identifier) if changed else None


def record_check(identifier: str, check: Mapping[str, Any]) -> dict[str, Any] | None:
    with transaction() as connection:
        changed = connection.execute(
            tables.providers.update().where(tables.providers.c.id == identifier)
            .values(check=dict(check), checked_at=now_instant())
        ).rowcount
    return get(identifier) if changed else None


def remove(identifier: str) -> bool:
    """Delete a provider and every order and voice choice that names it. False when there was none."""
    with transaction() as connection:
        deleted = connection.execute(
            tables.providers.delete().where(tables.providers.c.id == identifier)
        ).rowcount
        if not deleted:
            return False
        _forget(connection, identifier, None, None, now_instant())
    return True


def _forget(connection: Any, identifier: str, models: Mapping[str, Sequence[str]] | None,
            voices: set[str] | None, now: str) -> None:
    """Take a provider — or, given `models` and `voices`, some of its models — out of every owner's
    orders and voice choices. None means every model it has."""
    def gone(provider: Any, model: Any, order: str | None = None) -> bool:
        if provider != identifier:
            return False
        if order is None:
            return voices is None or model in voices
        return models is None or model in (models.get(order) or ())

    for row in connection.execute(select(tables.model_selection)).mappings().all():
        chains = _without_pairs(row["chains"], gone)
        if chains != row["chains"]:
            connection.execute(
                tables.model_selection.update().where(tables.model_selection.c.id == row["id"])
                .values(chains=chains, edited_at=now)
            )
    for row in connection.execute(select(tables.pronunciation_settings)).mappings().all():
        values = {
            "voices": _without_voices(row["voices"], gone),
            "guide_voices": _without_voices(row["guide_voices"], gone),
            "first_voices": _without_firsts(row["first_voices"], gone),
            "guide_first_voices": _without_firsts(row["guide_first_voices"], gone),
        }
        if any(values[name] != row[name] for name in values):
            connection.execute(
                tables.pronunciation_settings.update()
                .where(tables.pronunciation_settings.c.id == row["id"])
                .values(**values, edited_at=now)
            )


def _without_pairs(chains: Any, gone: Any) -> Any:
    """Every chain without the pairs that are gone.

    A chain that held only that provider's pairs is forgotten rather than left empty: an empty chain
    means the owner switched the kind off, and removing a provider is not that choice. The kind
    follows the default order again, which is what it would have done had the owner never chosen.
    """
    if not isinstance(chains, Mapping):
        return chains
    kept: dict[str, Any] = {}
    for kind, pairs in chains.items():
        if not isinstance(pairs, list):
            kept[kind] = pairs
            continue
        left = [pair for pair in pairs
                if not (isinstance(pair, Mapping) and gone(pair.get("provider"), pair.get("model"), kind))]
        if left or not pairs:
            kept[kind] = left
    return kept


def _without_voices(voices: Any, gone: Any) -> Any:
    """`{provider: {model: {language: voice}}}` without the models that are gone."""
    if not isinstance(voices, Mapping):
        return voices
    kept: dict[str, Any] = {}
    for provider, by_model in voices.items():
        if not isinstance(by_model, Mapping):
            kept[provider] = by_model
            continue
        left = {model: chosen for model, chosen in by_model.items() if not gone(provider, model)}
        if left:
            kept[provider] = left
    return kept


def _without_firsts(firsts: Any, gone: Any) -> Any:
    """`{order: {language: [provider, model]}}` without the languages a gone voice read first."""
    if not isinstance(firsts, Mapping):
        return firsts
    return {
        order: {
            language: pair for language, pair in by_language.items()
            if not (isinstance(pair, list) and len(pair) == 2 and gone(pair[0], pair[1]))
        } if isinstance(by_language, Mapping) else by_language
        for order, by_language in firsts.items()
    }
