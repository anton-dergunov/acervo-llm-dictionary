#!/usr/bin/env python3
"""Package one validated Anki sync manifest and only its referenced media."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path

from acervo.consumers.anki.manifest import SyncManifest


def portable_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    return info


def build_archive(manifest_path: Path, output_path: Path) -> None:
    manifest, manifest_dir = SyncManifest.load(manifest_path)
    media: dict[Path, Path] = {}
    for note in manifest.notes:
        for source in [*note.media_sources(manifest_dir).values(),
                       *note.embedded_sources(manifest_dir).values()]:
            media[source] = source.relative_to(manifest_dir.resolve())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        archive.add(manifest_path, arcname="manifest.json", filter=portable_tar_info)
        for source, relative in sorted(media.items(), key=lambda item: item[1].as_posix()):
            archive.add(source, arcname=relative.as_posix(), filter=portable_tar_info)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_archive(args.manifest.expanduser().resolve(), args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
