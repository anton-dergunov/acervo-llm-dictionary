"""Signing and reading Acervo's own tokens, and nothing else.

A leaf, deliberately. It knows JWT, a secret and a per-user key; it does not know what a request is,
where accounts are stored, or what a job does. That is what lets **both** sides use it: `api/auth.py`
mints a session from a route, and `services/loops.py` mints a render-scoped token from work that
`work/` may not import `api/` to reach.

Before this existed, minting lived in `api/auth.py`, and the loop pipeline needing a token would
have made `work/` reach back into the request path through a service — which is exactly the shape
`test_layering.py` forbids. Moving the signing rule here keeps it in one place rather than two.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

ALGORITHM = "HS256"

# Chosen rather than inherited. The client refreshes once at startup and never again, so a 7-day
# token signs out a phone left unopened for eight days.
SESSION_LIFETIME = timedelta(days=30)

# What a render-scoped token may do, and for how long.
#
# LexiBeat holds no provider credential: it is handed a token for **one render**, audienced to the
# one route it may call, and it lives in that process and nowhere else. An hour, because a
# twelve-word loop is seventy-odd model calls behind a chain that may be resting — long enough that a
# render which waits out a rate limit still finishes, short enough that a token lifted from a
# container is worth little. Measured against a real render: three words took 65 s, so twelve take
# about four and a half minutes and an hour is ample even with a chain resting between calls.
TAKE_AUDIENCE = "acervo:pronunciations/take"
# The other route a render calls home to: the writer, for a format that takes its lines from one.
WRITE_AUDIENCE = "acervo:loops/write"
RENDER_LIFETIME = timedelta(hours=1)


def resolve_secret(settings: Any) -> str:
    """The signing secret, minted and kept beside the database when the environment names none.

    A generated-per-start secret would sign everyone out on every restart, and requiring one to be
    configured would make a local run need configuring.
    """
    if settings.jwt_secret.strip():
        return settings.jwt_secret.strip()
    path = Path(settings.database_path).parent / "jwt-secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o600)
    return secret


def signing_key(secret: str, token_key: str) -> bytes:
    """The key one account's tokens are signed with.

    The per-user half is what makes a password change invalidate outstanding tokens — including an
    outstanding render token. Hashed rather than concatenated so the key is a full 32 bytes however
    short the configured secret is.
    """
    return hashlib.sha256(f"{secret}:{token_key}".encode()).digest()


def mint_session(secret: str, user: Mapping[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user["id"], "iat": int(now.timestamp()),
         "exp": int((now + SESSION_LIFETIME).timestamp())},
        signing_key(secret, user["token_key"]),
        algorithm=ALGORITHM,
    )


def mint_render(secret: str, user: Mapping[str, Any], render: str, rid: str = "") -> str:
    """A token good for one render's takes and lines, and nothing else."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user["id"],
            # Both routes a render calls home to, and nothing else: its takes, and its lines.
            "aud": [TAKE_AUDIENCE, WRITE_AUDIENCE],
            # Which render it was minted for. Not checked — the take route does not know what
            # renders exist — but it is what makes a token in a log traceable to the work that asked
            # for it.
            "render": render,
            # The id the work that asked is logged under (`acervo/trace.py`). The routes a render
            # calls home to take it up, so each take is filed with the job rather than as a request
            # from nowhere — with nothing for the generator to carry or to know about.
            **({"rid": rid} if rid else {}),
            "iat": int(now.timestamp()),
            "exp": int((now + RENDER_LIFETIME).timestamp()),
        },
        signing_key(secret, user["token_key"]),
        algorithm=ALGORITHM,
    )
