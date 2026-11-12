"""Fetch the pinned stroke data into a directory: one `<character>.json` each, the licence, and
`dataset.json` naming what it is.

The same file runs in two places, so there is one implementation of it: the server image's build,
which writes `/app/strokes` in a layer above Acervo's own code (a deploy never fetches it again),
and a laptop, which writes the ignored `vendor/strokes/` for a local server to read through
`ACERVO_STROKES_PATH`.

    python3 deploy/acervo/strokes/fetch.py                 # into vendor/strokes/
    python3 deploy/acervo/strokes/fetch.py /app/strokes    # what the Dockerfile runs
    python3 deploy/acervo/strokes/fetch.py --check         # verify what is there; no network

Only the standard library: the image runs this before anything is installed, and the laptop's
system Python has nothing else. The tarball is verified against the pin's digest before a single
file is written, and the directory is written beside its final name and renamed into place, so a
half-finished run never looks like a finished one.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PIN = HERE / "pin.json"
DEFAULT_DESTINATION = ROOT / "vendor" / "strokes"
MANIFEST = "dataset.json"


def dataset_name(pin: dict) -> str:
    return f"{pin['package']}@{pin['version']}"


def wanted(member: tarfile.TarInfo, licence: str) -> str | None:
    """The file name to write a tarball member under, or None to skip it.

    Only `package/<one character>.json` and the licence at the package root. Everything is written
    by this name and never by the member's own path, so nothing in the archive chooses where a file
    lands.
    """
    if not member.isfile():
        return None
    parts = member.name.split("/")
    if len(parts) != 2 or parts[0] != "package":
        return None
    name = parts[1]
    if name == licence:
        return name
    stem, dot, suffix = name.rpartition(".")
    if dot and suffix == "json" and len(stem) == 1 and ord(stem) >= 0x2E80:
        return name
    return None


def check(destination: Path, pin: dict) -> str | None:
    """Why the directory is not the pinned dataset, or None when it is."""
    manifest = destination / MANIFEST
    if not manifest.is_file():
        return f"{destination} holds no stroke data"
    found = json.loads(manifest.read_text(encoding="utf-8")).get("dataset")
    if found != dataset_name(pin):
        return f"{destination} holds {found}, the pin names {dataset_name(pin)}"
    return None


def fetch(destination: Path, pin: dict) -> int:
    print(f"fetch    {pin['tarball']}")
    with urllib.request.urlopen(pin["tarball"], timeout=120) as answer:
        payload = answer.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != pin["sha256"]:
        raise SystemExit(f"MISMATCH {pin['tarball']}\n         expected {pin['sha256']}\n         found    {digest}")

    partial = destination.with_name(destination.name + ".part")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    characters = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive:
            name = wanted(member, pin["licenceFile"])
            if name is None:
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            (partial / name).write_bytes(source.read())
            characters += name.endswith(".json")
    if not (partial / pin["licenceFile"]).is_file():
        raise SystemExit(f"{pin['tarball']} carries no {pin['licenceFile']}; refusing to ship it without its licence")
    (partial / MANIFEST).write_text(json.dumps({
        "dataset": dataset_name(pin), "licence": pin["licence"], "characters": characters,
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    shutil.rmtree(destination, ignore_errors=True)
    partial.rename(destination)
    print(f"verified {dataset_name(pin)}: {characters} characters in {destination}")
    return characters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("destination", nargs="?", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--pin", type=Path, default=PIN)
    parser.add_argument("--check", action="store_true", help="verify only; never touch the network")
    parser.add_argument("--force", action="store_true", help="fetch even when the directory verifies")
    arguments = parser.parse_args(argv)

    pin = json.loads(arguments.pin.read_text(encoding="utf-8"))
    problem = check(arguments.destination, pin)
    if arguments.check:
        if problem:
            print(problem, file=sys.stderr)
            return 1
        print(f"ok       {dataset_name(pin)} in {arguments.destination}")
        return 0
    if problem is None and not arguments.force:
        print(f"ok       {dataset_name(pin)} in {arguments.destination}")
        return 0
    fetch(arguments.destination, pin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
