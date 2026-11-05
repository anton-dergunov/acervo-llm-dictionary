"""Google's own APIs, reached by hand: one way to sign in per provider, and one way to fail.

Cloud Text-to-Speech and Cloud Vision are both outside LiteLLM. A Google Cloud provider signs in to
them with a key, sent as `x-goog-api-key` so it never sits in a URL, or with a credentials file —
a service account's key or a user's own sign-in — exchanged for an access token. Each provider holds
its own credential, so two Google Cloud providers can be two accounts; tokens are cached per
provider and per credential, and a replaced file is read again.

A user's own sign-in is refused by these APIs unless it names a quota project, so the provider's
project travels as `x-goog-user-project` with a file. The token never appears in an error.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any, NoReturn

import httpx

from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable

if TYPE_CHECKING:
    from acervo.models.providers import Provider

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DETAIL_LIMIT = 2000

_lock = threading.Lock()
_credentials: dict[tuple[str, str], Any] = {}


def headers(provider: "Provider", model: str) -> dict[str, str]:
    """What every call to a Google API carries: a key, or a current token and the quota project."""
    found = {"Content-Type": "application/json"}
    if provider.credential.key:
        found["x-goog-api-key"] = provider.credential.key
        return found
    if not provider.credential.file:
        raise ProviderRefused("unconfigured", f"{provider.label} has no key or credentials file",
                              provider_id=provider.id, model=model)
    found["Authorization"] = f"Bearer {token(provider, model)}"
    if project := provider.setting("project"):
        found["x-goog-user-project"] = project
    return found


def token(provider: "Provider", model: str) -> str:
    """A current access token from this provider's credentials file, refreshed only when it lapses."""
    import google.auth
    import google.auth.exceptions
    import google.auth.transport.requests

    held = (provider.id, provider.credential.digest())
    with _lock:
        try:
            credentials = _credentials.get(held)
            if credentials is None:
                credentials = _load(dict(provider.credential.file or {}), provider.setting("project"))
                _credentials[held] = credentials
            if not credentials.valid:
                credentials.refresh(google.auth.transport.requests.Request())
        except google.auth.exceptions.DefaultCredentialsError as error:
            _credentials.pop(held, None)
            fail(provider, model, "configuration", str(error), None)
        except google.auth.exceptions.RefreshError as error:
            _credentials.pop(held, None)
            fail(provider, model, "authentication", str(error), None)
        except google.auth.exceptions.TransportError as error:
            fail(provider, model, "unreachable", str(error), None)
        return str(credentials.token)


def _load(info: dict[str, Any], project: str) -> Any:
    """The file's credentials, by the loader for its own type.

    Only the two types Google writes for a person are accepted — a service account's key and a
    user's own sign-in — and `providers.parse` refuses any other before it is stored, so a file that
    names some other kind of credential is never handed to Google's generic loader.
    """
    import google.auth.exceptions
    from google.oauth2 import credentials as user, service_account

    kind = info.get("type")
    try:
        if kind == "service_account":
            found = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
        elif kind == "authorized_user":
            found = user.Credentials.from_authorized_user_info(info, scopes=[SCOPE])
        else:
            raise google.auth.exceptions.DefaultCredentialsError(f"credentials of type {kind!r} are not taken")
    except ValueError as error:
        raise google.auth.exceptions.DefaultCredentialsError(str(error)) from None
    return found.with_quota_project(project) if project else found


def forget_credentials() -> None:
    """Drop every cached token, so the next call reads its file again. Tests use it."""
    with _lock:
        _credentials.clear()


def post(provider: "Provider", model: str, url: str, body: dict[str, Any], timeout: float) -> httpx.Response:
    """One signed-in POST, with a transport failure already classified. A non-2xx is failed too."""
    try:
        response = httpx.post(url, headers=headers(provider, model), json=body, timeout=timeout)
    except httpx.TimeoutException as error:
        fail(provider, model, "unreachable", f"timed out: {error}", None)
    except httpx.HTTPError as error:
        fail(provider, model, "unreachable", str(error), None)
    if not response.is_success:
        fail(provider, model, None, detail(response), response.status_code)
    return response


def detail(response: httpx.Response) -> str:
    """Google's own error message, which names the missing API or quota project precisely."""
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
        return (message or json.dumps(payload, ensure_ascii=False))[:DETAIL_LIMIT]
    except ValueError:
        return (response.text or "").strip()[:DETAIL_LIMIT] or "empty response body"


def fail(provider: "Provider", model: str, reason: str | None, detail: str, status: int | None) -> NoReturn:
    from acervo.models.call import status_reason

    if reason is None:
        reason = status_reason(status)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, detail, provider_id=provider.id, model=model, status=status)  # type: ignore[arg-type]
