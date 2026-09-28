from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_input_bundle_contains_only_manifest_and_referenced_media(tmp_path: Path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "image.webp").write_bytes(b"image")
    (media / "audio.mp3").write_bytes(b"audio")
    (media / "thumb.webp").write_bytes(b"thumb")
    (tmp_path / "unrelated-private-file.txt").write_text("exclude", encoding="utf-8")
    manifest = tmp_path / "source.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "notes": [
                    {
                        "kind": "meaning",
                        "note_id": "note00000000001",
                        "lexeme_id": "lexeme000000001",
                        "sense_id": "sense0000000001",
                        "deck": "Test",
                        "fields": {"Recognise": "y", "Senses": '<img src="media/thumb.webp">'},
                        "tags": ["acervo::test"],
                        "media": {"Picture": "media/image.webp", "HeadwordAudio": "media/audio.mp3"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "input.tar.gz"

    subprocess.run(
        [
            # The project interpreter, not the shebang's: the scripts import the installed
            # `acervo` package and a bare `python3` is not the environment it is installed in.
            sys.executable,
            str(REPO_ROOT / "scripts/package_anki_sync_input.py"),
            str(manifest),
            str(output),
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    with tarfile.open(output) as archive:
        members = archive.getmembers()
    assert [member.name for member in members] == [
        "manifest.json",
        "media/audio.mp3",
        "media/image.webp",
        "media/thumb.webp",
    ]
    assert all(member.uid == 0 and member.gid == 0 for member in members)
    assert all(member.uname == "" and member.gname == "" for member in members)
