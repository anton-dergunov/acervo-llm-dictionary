"""The providers a laptop tool uses: `providers.local.json`, in the shape the server stores.

The scripts, the experiments and the live tests run on this machine rather than on the server, so
they cannot read the server's store. They read this file instead: the same provider documents, in
the order they are listed, with each one's secret inline — `"key"`, or `"credentials"` holding a
Google credentials file. It is gitignored, and the server never reads it.

One convenience the server's shape does not have: `"credentials"` may be a path to the file rather
than the file, because a Google sign-in on a laptop already lives in one
(`gcloud auth application-default login`).

    {"providers": [
      {"id": "gemini-api", "family": "gemini-api",
       "models": {"text": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]}, "key": "…"},
      {"id": "cloudflare", "family": "cloudflare", "settings": {"accountId": "…"},
       "models": {"image": ["@cf/black-forest-labs/flux-2-klein-4b"]}, "key": "…"}
    ]}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acervo.models.providers import Providers, build

LOCAL_PATH = Path(__file__).resolve().parents[3] / "providers.local.json"
SECRET_FIELDS = ("key", "credentials")


class LocalProvidersMissing(FileNotFoundError):
    """No `providers.local.json` where a laptop tool looked for one."""


def load_local(path: Path | str | None = None) -> Providers:
    """Every provider in the file, in the order listed. A provider that cannot be read stops the
    run with what is wrong with it, since on a laptop the person who can fix it is reading."""
    where = Path(path) if path else LOCAL_PATH
    try:
        document = json.loads(where.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LocalProvidersMissing(
            f"{where} does not exist. It lists the providers this machine may call, with their keys; "
            "see the docstring of acervo/models/local.py for its shape."
        ) from None
    entries = document.get("providers") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{where} must hold {{\"providers\": [...]}}")
    rows: list[dict[str, Any]] = []
    secrets: dict[str, dict[str, Any]] = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: every provider must be an object")
        secret = {name: entry[name] for name in SECRET_FIELDS if entry.get(name)}
        if isinstance(secret.get("credentials"), str):
            secret["credentials"] = json.loads(Path(secret["credentials"]).expanduser().read_text(encoding="utf-8"))
        rows.append({**{name: value for name, value in entry.items() if name not in SECRET_FIELDS},
                     "position": position})
        secrets[str(entry.get("id"))] = secret
    providers, refused = build(rows, secrets)
    if refused:
        identifier, why = refused[0]
        raise ValueError(f"{where}: provider {identifier!r}: {why}")
    return providers
