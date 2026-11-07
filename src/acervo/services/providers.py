"""The providers this server may call: read from the store, held to their family, and checked.

The binding between `acervo.models` — which knows what a provider *is* — and the two places one is
kept: its row in the database (`repository/providers.py`) and its key in the file beside it
(`services/provider_secrets.py`). `load` is what every model call reads, on every call and never
cached, so a provider added or a key replaced in Settings is the one the next call uses.

**A provider is stored only when its check works.** Saving a key makes one call that spends
nothing and says plainly whether the key works, and as whom. A key the provider refuses is a mistake
to fix, so it is refused here with the provider's own sentence and nothing is stored; a key that
stops working later is re-checked from Settings, and a provider whose key was refused is skipped by
every chain until it works again. Every check is written to the activity log, so `admin log
--failed` shows a refused key with what the provider said.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from acervo import activity
from acervo.errors import ApiError
from acervo.models import families, listing
from acervo.models.errors import ProviderError
from acervo.models.providers import (
    Checked, DocumentError, Provider, Providers, build, parse, suggested_id,
)
from acervo.repository import providers as store
from acervo.services import provider_secrets
from acervo.settings import Settings

# Which order draws on which kind a provider offers. Two orders share `audio` and two share `text`:
# the plain and expressive voices, and the text order and the quick look-up a photo tap makes.
ORDER_KINDS = {
    "text": "text",
    "quick": "text",
    "image": "image",
    "audioPlain": "audio",
    "audioExpressive": "audio",
    "ocr": "ocr",
}
SECRET_FIELDS = ("key", "credentials")


def load(settings: Settings) -> Providers:
    """Every provider, with its key, in the order added. One that cannot be read is left out and
    said so in the activity log — nothing should produce one, so it is a fact worth a line."""
    found, refused = build(store.listing(), provider_secrets.read(settings))
    for identifier, why in refused:
        activity.note("provider unreadable", failed=True, provider=identifier, message=why)
    return found


def find(settings: Settings, identifier: str) -> Provider:
    try:
        return load(settings).find(identifier)
    except KeyError:
        raise ApiError(404, "unknown_provider", f"This server has no provider called {identifier}.") from None


# ── what the owner is shown ──


def family_view(family: families.Family) -> dict[str, Any]:
    """One family, as "Add a provider" offers it."""
    return {
        "id": family.id,
        "label": family.label,
        "group": family.group,
        "hint": family.hint,
        "kinds": list(family.routes),
        # The kinds a key alone does not reach.
        "fileOnly": [kind for kind, route in family.routes.items() if route.file_only],
        "credential": family.credential,
        "keyLabel": family.key_label,
        "keyUrl": family.key_url,
        "voicesUrl": family.voices_url,
        "fields": [
            {"name": one.name, "label": one.label, "needed": one.needed, "default": one.default,
             "hint": one.hint, "choices": list(one.choices)}
            for one in family.fields
        ],
    }


def families_view() -> list[dict[str, Any]]:
    return [family_view(family) for family in families.FAMILIES]


def provider_view(provider: Provider) -> dict[str, Any]:
    """One provider, as Settings shows it. Never a key and never a credentials file: a key appears
    as its first and last four characters, a file as the account it names."""
    credential = provider.credential
    return {
        "id": provider.id,
        "family": provider.family.id,
        "label": provider.label,
        "kinds": list(provider.kinds),
        "settings": dict(provider.settings),
        "models": {
            kind: [_model_view(model) for model in models]
            for kind, models in provider.models.items()
        },
        "extra": dict(provider.extra),
        "credential": {
            "kind": "file" if credential.file else "key" if credential.key else "none",
            "hint": provider.key_hint(),
            "account": provider.identity(),
        },
        "check": None if provider.check is None else {
            "ok": provider.check.ok, "said": provider.check.said, "reason": provider.check.reason,
            "at": provider.checked_at,
        },
        "available": provider.available,
        "reason": provider.reason(),
        "usageUrl": provider.usage_url(),
    }


def _voice_view(voice: Any) -> dict[str, Any]:
    return {name: value for name, value in (("name", voice.name), ("label", voice.label),
                                            ("locale", voice.locale), ("gender", voice.gender),
                                            ("note", voice.note)) if value}


def _model_view(model: Any) -> dict[str, Any]:
    found: dict[str, Any] = {"id": model.id}
    if model.direction:
        found["direction"] = True
    if model.languages != "any":
        found["languages"] = list(model.languages)
    if model.voices:
        found["voices"] = [_voice_view(voice) for voice in model.voices]
    if model.allowance:
        found["allowance"] = dict(model.allowance)
    return found


# ── what a provider has, for the pickers ──


def offered_models(settings: Settings, identifier: str, kind: str) -> dict[str, Any]:
    """The models a provider says it has for a kind, for "Add a model". `listed` is false where it
    cannot say, and the owner then types the model's name."""
    provider = find(settings, identifier)
    if kind not in families.KINDS:
        raise ApiError(400, "invalid_input", f"There is no kind called {kind or 'that'}.")
    if not provider.family.serves(kind):
        raise ApiError(400, "unsupported_kind", f"{provider.label} does not do {kind}.")
    if not listing.lists(provider, kind):
        return {"kind": kind, "listed": False, "models": []}
    try:
        found = listing.models(provider, kind)
    except ProviderError as error:
        raise _listing_refused(provider, error, kind=kind) from None
    return {"kind": kind, "listed": True, "models": list(found)}


def offered_voices(settings: Settings, identifier: str, model: str) -> dict[str, Any]:
    """The voices one of a provider's speech models has: typed on the model, else the provider's
    own list. `listed` says which, so the page offers typing one only where it is the way."""
    provider = find(settings, identifier)
    found = provider.model("audio", model)
    if found is None:
        raise ApiError(400, "unknown_model", f"{provider.label} has no voice model called {model or 'that'}.")
    if found.voices or not listing.lists_voices(provider):
        return {"listed": False, "voices": [_voice_view(voice) for voice in found.voices]}
    try:
        voices = listing.voices(provider, model)
    except ProviderError as error:
        raise _listing_refused(provider, error, model=model) from None
    return {"listed": True, "voices": [_voice_view(voice) for voice in voices]}


def _listing_refused(provider: Provider, error: ProviderError, **about: str) -> ApiError:
    """A listing the provider turned away, in its own words. The envelope writes it down, with the
    provider and the reason beside it, so `admin log --failed` shows it."""
    reason, said = listing.refusal(provider, error)
    noted = {"provider": provider.id, "family": provider.family.id, "reason": reason, **about}
    if reason == "authentication":
        return ApiError(400, "key_refused", f"{said}.", noted=noted)
    return ApiError(502, "provider_listing_failed", f"{said}.", noted=noted)


# ── what the owner may change ──


def add(settings: Settings, body: Mapping[str, Any]) -> dict[str, Any]:
    """Check a new provider's key, and store the provider only if it works."""
    family_id = str(body.get("family") or "").strip()
    try:
        families.find(family_id)
    except KeyError:
        raise ApiError(400, "unknown_family", f"There is no provider family called {family_id or 'that'}.") from None
    taken = [row["id"] for row in store.listing()]
    identifier = str(body.get("id") or "").strip() or suggested_id(family_id, taken)
    if identifier in taken:
        raise ApiError(409, "provider_exists", f"There is already a provider called {identifier}.")
    document = {
        "id": identifier,
        "family": family_id,
        "label": body.get("label") or families.find(family_id).label,
        "settings": body.get("settings") or {},
        "models": body.get("models") or {},
        "extra": body.get("extra") or {},
    }
    secret = _secret(body)
    provider = _parsed(document, secret)
    checked = _checked(provider, "added")
    provider_secrets.put(settings, identifier, secret)
    if store.add(identifier, _stored(provider), checked.stored()) is None:
        raise ApiError(409, "provider_exists", f"There is already a provider called {identifier}.")
    activity.note("provider added", provider=identifier, family=family_id)
    return provider_view(find(settings, identifier))


def change(settings: Settings, identifier: str, body: Mapping[str, Any]) -> dict[str, Any]:
    """Change what the owner may change. A new key, or a changed setting, is checked again first.

    A model taken away is taken out of every order and voice choice in the same transaction, for
    the reason removing a whole provider is: an order naming a model nobody offers is refused.
    """
    current = find(settings, identifier)
    if "family" in body and body["family"] != current.family.id:
        raise ApiError(400, "invalid_input", "A provider's family cannot change; add another provider.")
    if "id" in body and body["id"] != identifier:
        raise ApiError(400, "invalid_input", "A provider's id cannot change: orders and voices name it.")
    stored = next(row for row in store.listing() if row["id"] == identifier)
    document = {
        "id": identifier,
        "family": current.family.id,
        **{name: body[name] if name in body else stored[name]
           for name in ("label", "settings", "models", "extra")},
    }
    replaced = any(name in body for name in SECRET_FIELDS)
    secret = _secret(body) if replaced else provider_secrets.read(settings).get(identifier)
    provider = _parsed(document, secret)
    checked = None
    if replaced or dict(provider.settings) != dict(current.settings):
        checked = _checked(provider, "changed")
    dropped = {
        order: [model for model in current.models_for(kind) if model not in provider.models_for(kind)]
        for order, kind in ORDER_KINDS.items()
    }
    if replaced:
        provider_secrets.put(settings, identifier, secret)
    store.change(identifier, _stored(provider), checked.stored() if checked else None,
                 dropped={order: models for order, models in dropped.items() if models},
                 dropped_voices=dropped["audioPlain"])
    activity.note("provider changed", provider=identifier, key=("replaced" if replaced else "kept"))
    return provider_view(find(settings, identifier))


def check(settings: Settings, identifier: str) -> dict[str, Any]:
    """Check a provider's key again and keep what it said, working or not: the page shows either."""
    provider = find(settings, identifier)
    checked = listing.check(provider)
    _note(provider, checked, "checked")
    store.record_check(identifier, checked.stored())
    return provider_view(find(settings, identifier))


def remove(settings: Settings, identifier: str) -> None:
    """Remove a provider, its key, and every order and voice choice that names it."""
    if not store.remove(identifier):
        raise ApiError(404, "unknown_provider", f"This server has no provider called {identifier}.")
    provider_secrets.put(settings, identifier, None)
    activity.note("provider removed", provider=identifier)


def _secret(body: Mapping[str, Any]) -> dict[str, Any]:
    """The key or credentials file a request sends. A file may arrive as its text, as uploaded."""
    secret: dict[str, Any] = {}
    if body.get("key"):
        secret["key"] = body["key"]
    if body.get("credentials"):
        credentials = body["credentials"]
        if isinstance(credentials, str):
            try:
                credentials = json.loads(credentials)
            except ValueError:
                raise ApiError(400, "invalid_input", "That credentials file is not JSON.") from None
        secret["credentials"] = credentials
    return secret


def _parsed(document: Mapping[str, Any], secret: Mapping[str, Any] | None) -> Provider:
    try:
        provider = parse(document, secret)
    except DocumentError as error:
        raise ApiError(400, "invalid_input", str(error)) from None
    missing = provider.reason()
    if missing:
        raise ApiError(400, "invalid_input", f"{missing}.")
    return provider


def _checked(provider: Provider, event: str) -> Checked:
    checked = listing.check(provider)
    _note(provider, checked, event)
    if not checked.ok:
        if checked.reason == "authentication":
            raise ApiError(400, "key_refused", f"{checked.said}. Nothing was saved.")
        raise ApiError(502, "provider_check_failed", f"{checked.said}. Nothing was saved.")
    return checked


def _note(provider: Provider, checked: Checked, event: str) -> None:
    activity.note(f"provider check ({event})", failed=not checked.ok, provider=provider.id,
                  family=provider.family.id, reason=checked.reason or "ok", message=checked.said)


def _stored(provider: Provider) -> dict[str, Any]:
    """What the row holds: the provider as parsed, so a stored document is always a clean one."""
    view = provider_view(provider)
    return {
        "family": provider.family.id,
        "label": provider.label,
        "settings": dict(provider.settings),
        "models": view["models"],
        "extra": dict(provider.extra),
    }
