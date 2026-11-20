#!/usr/bin/env python3
"""Verify the built Acervo PWA without starting a server."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"


def main() -> None:
    manifest_path = DIST / "manifest.webmanifest"
    assert manifest_path.is_file(), "build the web application first"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "Acervo"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "."
    assert manifest["prefer_related_applications"] is False
    assert {app["platform"] for app in manifest["related_applications"]} == {"webapp"}
    purposes = {icon.get("purpose", "any") for icon in manifest["icons"]}
    assert {"any", "maskable"} <= purposes
    for icon in manifest["icons"]:
        assert (DIST / icon["src"]).is_file(), f"missing {icon['src']}"

    index = (DIST / "index.html").read_text(encoding="utf-8")
    assert "<title>Acervo</title>" in index
    assert '<meta name="apple-mobile-web-app-capable" content="yes"' in index
    assert '<meta name="apple-mobile-web-app-title" content="Acervo"' in index
    assert re.search(r'(?:src|href)="\./', index), "assets must be relative for the native host"

    service_worker = (DIST / "sw.js").read_text(encoding="utf-8")
    assert "index.html" in service_worker
    assert '"SKIP_WAITING"' in service_worker, (
        "the waiting worker must activate only after the explicit update message"
    )
    assert "clientsClaim" not in service_worker, "updates must remain explicit"
    assert r"/^\/api\//" in service_worker and r"/^\/_\//" in service_worker
    # The IPA guide's recordings and the make dialogs' pictures are read offline like every other
    # read, so every one of them must be in the precache list, not only fetched when first needed.
    for kind in ("*.ogg", "*.webp"):
        built = sorted((DIST / "assets").glob(kind))
        assert built or kind == "*.webp", f"no {kind} in the build: the IPA guide's recordings are missing"
        missing = [path.name for path in built if f"assets/{path.name}" not in service_worker]
        assert not missing, f"{len(missing)} {kind} files are not precached, e.g. {missing[:3]}"
    assert not any(path.suffix == ".zip" for path in DIST.rglob("*")), (
        "native downloads must not be staged into the PWA"
    )

    # One stylesheet, because a *second* one can only arrive by being dynamically imported — and a
    # dynamically imported stylesheet is broken in the native host. Vite preloads it through a helper
    # that resolves the path relative to the importing chunk, and with `base: "./"` that chunk lives
    # in `assets/`, so `assets/styles-x.css` is fetched as `acervo://app/assets/assets/styles-x.css`.
    # The app then dies on "Unable to preload CSS" and stays dead until the web view is reloaded by
    # hand. Import stylesheets statically; the entry's own CSS file is the right place for them.
    stylesheets = sorted(path.name for path in (DIST / "assets").glob("*.css"))
    assert len(stylesheets) == 1, (
        f"expected one stylesheet, found {stylesheets}. A dynamically imported stylesheet is "
        "preloaded from the wrong path under the acervo:// scheme; import it statically instead."
    )

    print("Acervo PWA verification passed")


if __name__ == "__main__":
    main()
