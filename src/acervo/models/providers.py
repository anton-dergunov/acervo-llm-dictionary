"""A provider the owner added: one account, one credential, its models, and the family that speaks to it.

The server keeps these rows in its database and their secrets in a file beside it; a laptop tool
keeps them in `providers.local.json` (`local.py`). Either way this module turns a stored document
and its secret into a `Provider`, and never reads the environment.

**The unit of choice is a (provider, model) pair**, as before: a free tier is metered per model, so
two models with 500 requests a day each are a thousand, and the second is reached by the first one's
429. With nothing chosen the walk is provider by provider in the order they were added and, inside
each, model by model in the order they were added.

`parse` is the one validator of a provider document, and its messages are written for the owner:
the binding layer shows them as they are.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping, Sequence

from acervo.models import locales, redact
from acervo.models.families import EXPRESSIVE_CHAIN, KINDS, Family, Route, find as family

__all__ = [
    "Checked", "Credential", "DocumentError", "EXPRESSIVE_CHAIN", "GENDERS", "HINT_EDGE",
    "HINT_MINIMUM", "Model", "Provider", "Providers", "Voice", "parse", "build",
]

GENDERS = ("female", "male", "neutral")
ALLOWANCE_UNITS = ("calls", "pictures", "characters", "photos", "tokens")
ALLOWANCE_PERIODS = ("day", "month")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
# The credential types Google writes: a service account's key, and a user's own sign-in.
CREDENTIAL_TYPES = ("service_account", "authorized_user")

# Enough of a key to tell two of them apart, and never enough to use. Four at each end of a
# thirty-nine character token leaves thirty-one unknown — and it is the difference between "a key is
# set" and "*that* key is set", which is the question asked when a rotation half-happened.
HINT_EDGE = 4
# Below this a quarter of the value would be showing.
HINT_MINIMUM = 16


class DocumentError(ValueError):
    """A provider document that cannot be stored or used, said for the owner."""


@dataclass(frozen=True)
class Voice:
    """One voice. Only the name is required; the rest is for the person choosing — "Kore · female ·
    firm" — and the locale is its accent, or None for a voice that speaks any locale it is told."""

    name: str
    locale: str | None = None
    gender: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Model:
    """One model as the owner added it: only what varies between models and can be checked on the
    provider's own page."""

    id: str
    # Whether a voice takes a free-text delivery direction, in a field of its own so it is never
    # read aloud. Only such a voice reads the expressive order.
    direction: bool = False
    # `"any"`, or the locales it speaks — which are also the locales it is sent, nearest first.
    languages: str | tuple[str, ...] = "any"
    # Typed in only where the provider cannot list them.
    voices: tuple[Voice, ...] = ()
    allowance: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Credential:
    """A key, or a Google credentials file. Never shown, never logged, never in the database."""

    key: str | None = None
    file: Mapping[str, Any] | None = None

    @property
    def present(self) -> bool:
        return bool(self.key or self.file)

    def digest(self) -> str:
        """Which credential this is, without being it: a cache key that changes when it is replaced."""
        text = json.dumps({"key": self.key, "file": self.file}, sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def secrets(self) -> tuple[str, ...]:
        found = [self.key or ""]
        for name in ("private_key", "refresh_token", "client_secret", "private_key_id"):
            value = (self.file or {}).get(name)
            if isinstance(value, str):
                found.append(value)
        return tuple(value for value in found if value)


@dataclass(frozen=True)
class Checked:
    """What the last check said: whether the key works, in the provider's own words, and as whom."""

    ok: bool
    said: str
    reason: str | None = None
    account: str | None = None

    def stored(self) -> dict[str, Any]:
        return {"ok": self.ok, "said": self.said, "reason": self.reason, "account": self.account}


@dataclass(frozen=True)
class Provider:
    id: str
    family: Family
    label: str
    settings: Mapping[str, str]
    models: Mapping[str, tuple[Model, ...]]
    extra: Mapping[str, Any] = field(default_factory=dict)
    credential: Credential = Credential()
    check: Checked | None = None
    checked_at: str | None = None
    position: int = 0

    def __post_init__(self) -> None:
        # Every value this provider could leak, known to the redactor before any call can fail.
        redact.remember(self.credential.secrets())

    # ── what it offers ──

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(kind for kind in KINDS if self.models.get(kind))

    def serves(self, kind: str) -> bool:
        return bool(self.models.get(kind))

    def models_for(self, kind: str) -> tuple[str, ...]:
        """Every model this provider offers for a kind, in the order they were added."""
        return tuple(model.id for model in self.models.get(kind, ()))

    def model(self, kind: str, identifier: str) -> Model | None:
        return next((one for one in self.models.get(kind, ()) if one.id == identifier), None)

    def route(self, kind: str) -> Route:
        return self.family.routes[kind]

    # ── how it is called ──

    def setting(self, name: str) -> str:
        value = (self.settings.get(name) or "").strip()
        found = self.family.field(name)
        return value or (found.default or "" if found else "")

    def params_for(self, kind: str) -> dict[str, Any]:
        """The family's parameters for this kind, then the owner's `extra`, which wins."""
        return {**dict(self.family.params.get(kind) or {}), **dict(self.extra)}

    def timeout_for(self, kind: str, default: float) -> float:
        stated = self.family.timeouts.get(kind)
        return float(stated) if isinstance(stated, (int, float)) and stated > 0 else default

    @property
    def json_mode(self) -> str:
        if self.family.field("jsonMode"):
            return "native" if self.setting("jsonMode") == "native" else "prompt"
        return self.family.json_mode

    def image_capabilities(self) -> Mapping[str, Any]:
        return self.family.image

    def image_references(self) -> int:
        """How many reference pictures this provider's image models take alongside a prompt.

        A family fact: a model sent pictures it cannot read either refuses the call or ignores
        them, and ignoring them silently draws a stranger where a returning character was asked for.
        """
        count = self.family.image.get("references", 0)
        return count if isinstance(count, int) and not isinstance(count, bool) else 0

    def wire_model(self, kind: str, model: str) -> str:
        """The model as LiteLLM names it: the family's prefix and the provider's own id."""
        return f"{self.route(kind).prefix}{model}"

    def base_url(self) -> str | None:
        return self.filled(self.family.base_url)

    def usage_url(self) -> str | None:
        return self.filled(self.family.usage_url)

    def filled(self, template: str | None) -> str | None:
        if not template:
            return None
        names = _PLACEHOLDER.findall(template)
        if any(not self.setting(name) for name in names):
            return None
        return _PLACEHOLDER.sub(lambda match: self.setting(match.group(1)), template).rstrip("/")

    def transport(self, kind: str) -> dict[str, Any]:
        """What a LiteLLM call to this provider carries: the credential and the endpoint."""
        if self.route(kind).vertex:
            # Vertex takes a credentials file and nothing else, per call rather than from a
            # process-wide default, so two Google Cloud providers can be two accounts.
            return {
                "vertex_credentials": json.dumps(dict(self.credential.file or {})),
                "vertex_project": self.setting("project"),
                "vertex_location": self.setting("location"),
            }
        settings: dict[str, Any] = {}
        if self.credential.key:
            settings["api_key"] = self.credential.key
        elif self.family.credential in ("optional", "none") and self.route(kind).prefix == "openai/":
            # OpenAI's client will not start without a key, and a local server takes any.
            settings["api_key"] = "none"
        if (endpoint := self.base_url()) is not None:
            settings["api_base"] = endpoint
        return settings

    # ── whether it can be asked ──

    def reason(self) -> str | None:
        """Why this provider cannot be asked, or None. Never a value, only what is missing."""
        credential = self.family.credential
        if credential == "key" and not self.credential.key:
            return f"{self.label} has no {self.family.key_label}"
        if credential == "key-or-file" and not self.credential.present:
            return f"{self.label} has no key or credentials file"
        for one in self.family.fields:
            if one.needed == "always" or (one.needed == "file" and self.credential.file):
                if not self.setting(one.name):
                    return f"{self.label} needs its {one.label[0].lower()}{one.label[1:]}"
        # A key the provider refused is a mistake to fix, and nothing is sent until it is: asking
        # anyway would spend every call on the same refusal.
        if self.check is not None and not self.check.ok and self.check.reason == "authentication":
            return f"{self.label} refused its key when it was last checked"
        return None

    @property
    def available(self) -> bool:
        return self.reason() is None

    def key_hint(self) -> str | None:
        """The key as its first and last four characters, or None when there is none."""
        value = self.credential.key
        if not value:
            return None
        if len(value) < HINT_MINIMUM:
            return "…"
        return f"{value[:HINT_EDGE]}…{value[-HINT_EDGE:]}"

    def identity(self) -> str | None:
        """Whose credentials file this is, where the file says. Only the naming fields are read."""
        named = (self.credential.file or {}).get("client_email") or (self.credential.file or {}).get("account")
        return str(named) if isinstance(named, str) and named else None

    # ── voices ──

    def takes_direction(self, model: str) -> bool:
        found = self.model("audio", model)
        return bool(found and found.direction)

    def voices(self, model: str, *, strict: bool = False) -> tuple[Voice, ...]:
        """This model's voices: typed on the model, else the provider's own list.

        A list that cannot be read is empty unless `strict`, so a page that shows voices still
        renders; the call that needs one asks strictly and fails with the provider's sentence.
        """
        found = self.model("audio", model)
        if found and found.voices:
            return found.voices
        from acervo.models import listing

        try:
            return listing.voices(self, model)
        except Exception:
            if strict:
                raise
            return ()

    def accepted(self, model: str) -> tuple[str, ...]:
        """The locales this model may be sent: the ones typed on it, else the provider's own list."""
        found = self.model("audio", model)
        if found and isinstance(found.languages, tuple):
            return found.languages
        from acervo.models import listing

        try:
            return listing.locales(self)
        except Exception:
            return ()

    def speaks(self, model: str, language: str) -> bool:
        """Whether this model can say something in this BCP-47 language, by the provider's account."""
        found = self.model("audio", model)
        if found and isinstance(found.languages, tuple):
            return any(_within(language, declared) for declared in found.languages)
        voices = self.voices(model)
        if voices and all(voice.locale for voice in voices):
            return any(locales.same_language(str(voice.locale), language) for voice in voices)
        return True

    def voice_options(self, model: str, locale: str) -> tuple[tuple[Voice, str], ...]:
        """Every voice this model offers for the language of `locale`, best first, each with how
        well it serves that locale (`locales.MATCHES`).

        A voice with a locale has that accent; one with none speaks any, and is told which when its
        model takes a direction. The provider's order is kept within a match, so its first voice
        stays the default.
        """
        instruction = self.takes_direction(model)
        found: list[tuple[Voice, str]] = []
        for voice in self.voices(model):
            if voice.locale and not locales.same_language(voice.locale, locale):
                continue
            regional = voice.locale if voice.locale and locales.parse(voice.locale).region else None
            found.append((voice, locales.match(regional, locale, instruction=instruction)
                          if voice.locale is None or regional else "unstated"))
        return tuple(sorted(found, key=lambda pair: locales.rank(pair[1])))

    def voices_for(self, model: str, locale: str) -> tuple[str, ...]:
        """The names of the voices this model offers for `locale`, the default first."""
        return tuple(voice.name for voice, _ in self.voice_options(model, locale))

    def locale_for(self, model: str, locale: str, voice: str | None = None) -> str:
        """The language code to send with `voice` (or the default voice) for `locale`, in the
        provider's own spelling — `cmn-CN` for `zh-Hans-CN`.

        A voice made for one locale is sent with that locale. A voice that speaks any is sent the
        nearest locale the model accepts — `es-US` for Argentina, which shares `es-419` with it, and
        the language's main locale when no accent is chosen. One that names none is sent the tag.
        """
        options = self.voice_options(model, locale)
        chosen = next((one for one, _ in options if one.name == voice), None) if voice else None
        chosen = chosen or (options[0][0] if options else None)
        if chosen and chosen.locale:
            wanted = chosen.locale
        else:
            accepted = [tag for tag in self.accepted(model) if locales.same_language(tag, locale)]
            ancestry = {str(tag) for tag in locales.lineage(locale)}
            ranked = sorted(accepted, key=lambda tag: (
                locales.rank(locales.match(tag, locale, instruction=False)),
                str(locales.likely(tag)) not in ancestry,
            ))
            wanted = ranked[0] if ranked else locale
        wire = self.family.audio.get("wire") or {}
        return str(next((code for tag, code in wire.items()
                         if locales.likely(tag) == locales.likely(wanted)), wanted))


def _within(language: str, declared: str) -> bool:
    """`es-AR` is within `es` and within `es-419`'s language; `zh-Hant-TW` is within `zh`."""
    named = locales.parse(declared)
    if not named.script and not named.region:
        return locales.parse(language).language == named.language
    return locales.same_language(language, declared)


@dataclass(frozen=True)
class Providers:
    """Every provider, in the order they were added."""

    rows: tuple[Provider, ...] = ()

    def __iter__(self) -> Iterator[Provider]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def find(self, identifier: str) -> Provider:
        for row in self.rows:
            if row.id == identifier:
                return row
        raise KeyError(identifier)

    def serving(self, kind: str) -> tuple[Provider, ...]:
        return tuple(row for row in self.rows if row.serves(kind))


# ── reading a document ──


def _text(value: Any, what: str, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentError(f"{what} is missing.")
    if len(value) > limit:
        raise DocumentError(f"{what} is too long.")
    return value.strip()


def _voices(value: Any, where: str) -> tuple[Voice, ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list):
        raise DocumentError(f"The voices of {where} must be a list.")
    found = []
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            found.append(Voice(entry.strip()))
            continue
        if not (isinstance(entry, Mapping) and isinstance(entry.get("name"), str) and entry["name"].strip()
                and set(entry) <= {"name", "locale", "gender", "note"}
                and entry.get("gender") in (None, *GENDERS)
                and all(entry.get(name) is None or isinstance(entry[name], str) for name in ("locale", "note"))):
            raise DocumentError(f"Every voice of {where} needs a name, and may say its locale and gender.")
        found.append(Voice(entry["name"].strip(), entry.get("locale") or None, entry.get("gender"),
                           entry.get("note") or None))
    return tuple(found)


def _allowance(value: Any, where: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not (isinstance(value, Mapping) and isinstance(value.get("amount"), int)
            and not isinstance(value.get("amount"), bool) and value["amount"] > 0
            and value.get("unit") in ALLOWANCE_UNITS and value.get("per") in ALLOWANCE_PERIODS
            and set(value) <= {"amount", "unit", "per"}):
        raise DocumentError(f"The free allowance of {where} needs an amount, a unit and a day or month.")
    return dict(value)


def _model(kind: str, entry: Any, owner: str) -> Model:
    if isinstance(entry, str):
        entry = {"id": entry}
    if not isinstance(entry, Mapping):
        raise DocumentError(f"Every {kind} model of {owner} needs an id.")
    identifier = _text(entry.get("id"), f"A {kind} model's id")
    where = f"{owner}'s {identifier}"
    unknown = set(entry) - {"id", "direction", "languages", "voices", "allowance"}
    if unknown:
        raise DocumentError(f"{where} has fields a model does not take: {', '.join(sorted(unknown))}.")
    direction = entry.get("direction", False)
    if not isinstance(direction, bool):
        raise DocumentError(f"Whether {where} takes a direction must be true or false.")
    if direction and kind != "audio":
        raise DocumentError(f"Only a voice takes a direction, and {where} is not one.")
    languages = entry.get("languages", "any")
    if languages != "any":
        if not (isinstance(languages, list) and languages
                and all(isinstance(tag, str) and tag.strip() for tag in languages)):
            raise DocumentError(f"The languages of {where} must be \"any\" or a list of language tags.")
        languages = tuple(tag.strip() for tag in languages)
    return Model(identifier, direction, languages, _voices(entry.get("voices"), where),
                 _allowance(entry.get("allowance"), where))


def _credential(found: Family, secret: Mapping[str, Any] | None) -> Credential:
    secret = secret or {}
    key = secret.get("key")
    file = secret.get("credentials")
    if key is not None and (not isinstance(key, str) or not key.strip() or any(c.isspace() for c in key.strip())):
        raise DocumentError("A key is one line of letters, digits and punctuation.")
    if file is not None:
        if found.credential != "key-or-file":
            raise DocumentError(f"{found.label} takes a key, not a credentials file.")
        if not (isinstance(file, Mapping) and file.get("type") in CREDENTIAL_TYPES):
            raise DocumentError("That is not a Google credentials file: it names no service account or sign-in.")
    if key and file:
        raise DocumentError(f"{found.label} takes a key or a credentials file, not both.")
    if found.credential == "none" and key:
        raise DocumentError(f"{found.label} takes no key.")
    return Credential(key.strip() if isinstance(key, str) else None, dict(file) if file else None)


def parse(document: Mapping[str, Any], secret: Mapping[str, Any] | None = None) -> Provider:
    """One provider document and its secret, held to its family. `DocumentError` says what is wrong."""
    if not isinstance(document, Mapping):
        raise DocumentError("A provider must be an object.")
    identifier = document.get("id")
    if not isinstance(identifier, str) or not _SLUG.match(identifier):
        raise DocumentError("A provider's id is up to forty lowercase letters, digits and hyphens.")
    try:
        found = family(str(document.get("family") or ""))
    except KeyError:
        raise DocumentError(f"There is no provider family called {document.get('family')!r}.") from None
    label = _text(document.get("label") or found.label, "A provider's name", 80)
    settings = document.get("settings") or {}
    if not isinstance(settings, Mapping) or not all(isinstance(v, str) for v in settings.values()):
        raise DocumentError(f"{label}'s settings must be text.")
    unknown = set(settings) - {one.name for one in found.fields}
    if unknown:
        raise DocumentError(f"{found.label} has no setting called {sorted(unknown)[0]}.")
    for one in found.fields:
        value = (settings.get(one.name) or "").strip()
        if one.choices and value and value not in one.choices:
            raise DocumentError(f"{label}'s {one.label.lower()} must be one of {', '.join(one.choices)}.")
    credential = _credential(found, secret)
    models_document = document.get("models") or {}
    if not isinstance(models_document, Mapping):
        raise DocumentError(f"{label}'s models must be grouped by kind.")
    models: dict[str, tuple[Model, ...]] = {}
    for kind, entries in models_document.items():
        if kind not in KINDS:
            raise DocumentError(f"There is no kind called {kind}.")
        if not found.serves(kind):
            raise DocumentError(f"{found.label} does not do {kind}.")
        if entries in (None, []):
            continue
        if not isinstance(entries, list):
            raise DocumentError(f"{label}'s {kind} models must be a list.")
        if found.routes[kind].file_only and not credential.file:
            raise DocumentError(f"{found.label} reaches {kind} only with a credentials file.")
        parsed = tuple(_model(kind, entry, label) for entry in entries)
        if len({model.id for model in parsed}) != len(parsed):
            raise DocumentError(f"{label} lists the same {kind} model twice.")
        models[kind] = parsed
    extra = document.get("extra") or {}
    if not isinstance(extra, Mapping):
        raise DocumentError(f"{label}'s extra parameters must be a JSON object.")
    check = document.get("check")
    checked = None
    if isinstance(check, Mapping) and isinstance(check.get("ok"), bool):
        checked = Checked(check["ok"], str(check.get("said") or ""), check.get("reason"), check.get("account"))
    position = document.get("position")
    return Provider(
        id=identifier, family=found, label=label,
        settings={name: value.strip() for name, value in settings.items() if value.strip()},
        models=models, extra=dict(extra), credential=credential, check=checked,
        checked_at=document.get("checked_at") or document.get("checkedAt"),
        position=position if isinstance(position, int) else 0,
    )


def build(documents: Iterable[Mapping[str, Any]], secrets: Mapping[str, Mapping[str, Any]],
          ) -> tuple[Providers, list[tuple[str, str]]]:
    """Every stored provider, in the order added, and any that could not be read with why."""
    rows: list[Provider] = []
    refused: list[tuple[str, str]] = []
    for document in sorted(documents, key=lambda one: one.get("position") or 0):
        try:
            rows.append(parse(document, secrets.get(str(document.get("id")))))
        except DocumentError as error:
            refused.append((str(document.get("id")), str(error)))
    return Providers(tuple(rows)), refused


def suggested_id(family_id: str, taken: Sequence[str]) -> str:
    """A slug from the family, numbered when it is taken: `cloudflare`, then `cloudflare-2`."""
    base = family_id
    if base not in taken:
        return base
    number = 2
    while f"{base}-{number}" in taken:
        number += 1
    return f"{base}-{number}"
