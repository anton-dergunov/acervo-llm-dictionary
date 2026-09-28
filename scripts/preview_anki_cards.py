#!/usr/bin/env python3
"""Render a manifest's cards as Anki would, into plain HTML files a browser can open.

For looking at the card design without a phone: it builds a throwaway collection, installs the
current note types and fonts, adds the manifest's notes exactly as the robot would, and writes each
card's front and back, light and night, beside the media they name. Nothing is synced anywhere.

    python scripts/preview_anki_cards.py path/to/manifest.json OUTPUT_DIR
"""

from __future__ import annotations

import argparse
import html
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acervo.consumers.anki.manifest import SyncManifest  # noqa: E402
from acervo.consumers.anki.model import create_notetypes, install_fonts  # noqa: E402
from acervo.consumers.anki.robot import AnkiRobot, RobotSettings  # noqa: E402

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body class="card{night}"><div id="qa">{content}</div></body></html>
"""


def render(manifest_path: Path, output: Path, template_dir: Path) -> list[Path]:
    from anki.collection import Collection

    manifest, manifest_dir = SyncManifest.load(manifest_path)
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with tempfile.TemporaryDirectory() as scratch:
        robot = AnkiRobot(RobotSettings(
            endpoint="http://preview.invalid/", username="preview", password="preview",
            collection_path=Path(scratch) / "collection.anki2", backup_dir=Path(scratch) / "backups",
            template_dir=template_dir,
        ))
        collection = Collection(str(robot.settings.collection_path))
        try:
            create_notetypes(collection, robot.design)
            install_fonts(collection, robot.design)
            report = robot._upsert(collection, manifest, manifest_dir)
            for media in Path(collection.media.dir()).iterdir():
                shutil.copy2(media, output / media.name)
            number = 0
            links = []
            for note in report["notes"]:
                for card_id in note["card_ids"]:
                    card = collection.get_card(card_id)
                    number += 1
                    name = card.template()["name"].lower()
                    for face, content in (("front", card.question()), ("back", card.answer())):
                        for night in ("", " nightMode"):
                            path = output / f"{number:03d}-{name}-{face}{'-night' if night else ''}.html"
                            path.write_text(PAGE.format(title=f"{note['note_id']} · {name} · {face}",
                                                        night=night, content=content), encoding="utf-8")
                            written.append(path)
                    links.append(
                        f"<li>{number:03d} · {html.escape(name)} · {html.escape(note['note_id'])}: "
                        + " ".join(f'<a href="{number:03d}-{name}-{face}{night}.html">{face}{night}</a>'
                                   for face in ("front", "back") for night in ("", "-night"))
                        + "</li>"
                    )
            (output / "index.html").write_text(
                "<!doctype html><meta charset='utf-8'><title>Acervo cards</title><ol>"
                + "".join(links) + "</ol>", encoding="utf-8")
        finally:
            collection.close()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--template-dir", type=Path, default=ROOT / "templates")
    args = parser.parse_args(argv)
    written = render(args.manifest.expanduser().resolve(), args.output.expanduser().resolve(),
                     args.template_dir.expanduser().resolve())
    print(f"{len(written)} pages in {args.output}; open index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
