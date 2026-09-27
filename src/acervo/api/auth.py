"""Sessions.

Nothing depends on the old token format — the web client stores an opaque string, the macOS host puts
it in `UserDefaults` untouched, and nothing anywhere decodes it — so the replacement is chosen on
merit rather than compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jwt
from fastapi import Request

from acervo.errors import ApiError
from acervo.repository import accounts
from acervo.settings import Settings
from acervo.tokens import (
    ALGORITHM,
    RENDER_LIFETIME,
    TAKE_AUDIENCE,
    WRITE_AUDIENCE,
    mint_render,
    resolve_secret,
    signing_key,
)

# Re-exported so the many callers of `auth.mint` and `auth.TAKE_AUDIENCE` keep reading naturally.
# The signing itself lives in `acervo.tokens`, a leaf both this and `services/loops.py` can reach —
# `work/` may not import `api/`, and a render mints its own token.
__all__ = [
    "ALGORITHM", "RENDER_LIFETIME", "TAKE_AUDIENCE", "UNAUTHENTICATED", "WRITE_AUDIENCE",
    "account_for", "bearer_token", "mint", "mint_render", "owner", "owner_id",
    "resolve_secret", "take_owner", "write_owner",
]

UNAUTHENTICATED = ApiError(401, "unauthenticated", "Sign in to continue.")


def mint(secret: str, user: Mapping[str, Any]) -> str:
    from acervo.tokens import mint_session

    return mint_session(secret, user)


def bearer_token(request: Request) -> str:
    """The token from either header shape.

    Existing callers are split between `Bearer <token>` and a bare token, and `HTTPBearer` answers a
    bare one with a 403 that no client handles.
    """
    header = request.headers.get("authorization", "").strip()
    if not header:
        return ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return header


def account_for(secret: str, token: str, audience: str | None = None) -> Mapping[str, Any]:
    """The account a token names, or 401.

    `audience` is what a render-scoped token is *allowed* to be: pass it on the one route that
    accepts one, and leave it off everywhere else. A token carrying an audience is refused wherever
    it is not named, which is what keeps a render token from becoming a session.
    """
    if not token:
        raise UNAUTHENTICATED
    try:
        # The signing key depends on the account, so the subject has to be read before the signature
        # can be checked. Nothing is trusted from this first pass but the id it points at.
        claimed = jwt.decode(token, options={"verify_signature": False})
        user = accounts.by_id(str(claimed.get("sub") or ""))
        if user is None:
            raise UNAUTHENTICATED
        carried = claimed.get("aud")
        # One audience or several — a render's token names both routes it calls home to — and the
        # route asking must be among them.
        named = carried if isinstance(carried, list) else [carried]
        if carried is not None and audience not in named:
            raise UNAUTHENTICATED
        jwt.decode(
            token, signing_key(secret, user["token_key"]), algorithms=[ALGORITHM],
            audience=audience, options={"verify_aud": carried is not None},
        )
    except ApiError:
        raise
    except jwt.PyJWTError:
        raise UNAUTHENTICATED from None
    return user


def owner(request: Request) -> Mapping[str, Any]:
    """FastAPI dependency: the signed-in account, or 401."""
    return account_for(request.app.state.jwt_secret, bearer_token(request))


def take_owner(request: Request) -> Mapping[str, Any]:
    """The account behind a take request: an ordinary session, or a render-scoped token.

    Both, deliberately. The owner's own session is strictly more privileged than a render token, so
    refusing it would buy nothing and would mean the route could not be exercised without minting a
    token by hand. What the audience buys is the other direction: a render token is *only* this.
    """
    return account_for(request.app.state.jwt_secret, bearer_token(request), audience=TAKE_AUDIENCE)


def write_owner(request: Request) -> Mapping[str, Any]:
    """The account behind a writer request: a session, or a render-scoped token, as `take_owner`."""
    return account_for(request.app.state.jwt_secret, bearer_token(request), audience=WRITE_AUDIENCE)


def owner_id(request: Request) -> str:
    return owner(request)["id"]
