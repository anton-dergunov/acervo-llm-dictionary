#!/usr/bin/env python3
"""Draw the make dialogs' pictures, on this laptop.

Three groups, read from tracked files and written into the web bundle (`web/src/art/`) and the
prototype (`design/ui-prototype/img/art/`), one small WebP per catalogue id:

- **styles** — a sample of every picture style in `config/image-styles.yaml`: the same subject from
  `design/dialog-art.yaml`, drawn with that style's own brief, so each tile shows what the choice
  changes and nothing else;
- **kinds** — a vignette for each kind of story in `config/story-types.yaml`;
- **music** — a vignette for each of LexiBeat's bed families.

The prompts for kinds and music are `design/dialog-art.yaml`, one line per id plus a house style
they share. A picture already on disk is kept unless `--force` or `--only` names it, so adding a
style and running this again draws that one style. Which provider draws is the same chain
`generate_images.py` uses: the flag, else the order of `providers.local.json`. A contact sheet is
written beside the masters to look at before anything is committed.

    .venv/bin/python scripts/draw_dialog_art.py --dry-run
    .venv/bin/python scripts/draw_dialog_art.py --image-chain vertex
    .venv/bin/python scripts/draw_dialog_art.py --only styles/pixel-art --force

When one picture will not come right, draw several versions of it and choose. `--variants N` draws
N versions of each picture named, as masters beside the others and a sheet of them side by side,
and changes nothing in the bundle; `--pick group/id=n` makes version n the tile.

    .venv/bin/python scripts/draw_dialog_art.py --only music/meditative --variants 3
    .venv/bin/python scripts/draw_dialog_art.py --pick music/meditative=2
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
import numpy as np
from PIL import Image

from acervo.images.compose import compose
from acervo.images.render import Renderer
from acervo.images.styles import load_styles
from acervo.models import chain
from acervo.models.errors import ProviderError, ProviderRefused
from acervo.models.local import load_local

REPO = Path(__file__).resolve().parent.parent
PROMPTS = REPO / "design" / "dialog-art.yaml"
STORY_TYPES = REPO / "config" / "story-types.yaml"
WEB_ART = REPO / "web" / "src" / "art"
PROTOTYPE_ART = REPO / "design" / "ui-prototype" / "img" / "art"
MASTERS = REPO / "output" / "dialog-art"

# A tile is drawn at about 92 CSS pixels, and a grid tile at about 150; 320 covers both at 2x.
TILE = 320
QUALITY = 82


def prompts() -> dict[str, dict[str, str]]:
    """Every picture to draw, as `{group: {id: prompt}}`."""
    spec = yaml.safe_load(PROMPTS.read_text(encoding="utf-8"))
    house = " ".join(spec["house"].split())
    subject = " ".join(spec["style_subject"].split())
    styles = load_styles()
    kinds = yaml.safe_load(STORY_TYPES.read_text(encoding="utf-8"))
    kind_ids = list((kinds.get("types") or kinds).keys())
    missing = [kind for kind in kind_ids if kind not in spec["kinds"]]
    if missing:
        print(f"No vignette written for kinds {missing} in {PROMPTS.name}; they keep their emoji.", file=sys.stderr)
    return {
        "styles": {style.id: compose(subject, style) for style in styles.styles},
        "kinds": {kind: f"{spec['kinds'][kind].strip().rstrip('.')}. {house}" for kind in kind_ids if kind in spec["kinds"]},
        "music": {family: f"{motif.strip().rstrip('.')}. {house}" for family, motif in spec["music"].items()},
    }


def trimmed(picture: Image.Image) -> Image.Image:
    """The picture without a plain margin around it. Asked for a vignette, the model often paints an
    inset on a blank card however the prompt says otherwise, and on a 92-pixel tile that margin is a
    sixth of the picture. A row or column is margin when little of it differs from the corner's
    colour — counted rather than bounded, so the card's paper grain does not count as painting — and
    the picture is cropped to the largest square inside what is left."""
    pixels = np.asarray(picture, dtype=np.int16)
    corner = pixels[2, 2]
    painted = np.abs(pixels - corner).sum(axis=2) > 40
    rows = np.where(painted.mean(axis=1) > 0.25)[0]
    columns = np.where(painted.mean(axis=0) > 0.25)[0]
    if not len(rows) or not len(columns):
        return picture
    top, bottom, left, right = rows[0], rows[-1] + 1, columns[0], columns[-1] + 1
    width, height = right - left, bottom - top
    if min(width, height) > 0.96 * picture.size[0]:
        return picture
    side = min(width, height)
    x = left + (width - side) // 2
    y = top + (height - side) // 2
    inset = max(2, side // 80)
    return picture.crop((int(x + inset), int(y + inset), int(x + side - inset), int(y + side - inset)))


def tile(master: bytes) -> bytes:
    with Image.open(io.BytesIO(master)) as image:
        picture = trimmed(image.convert("RGB")).resize((TILE, TILE), Image.LANCZOS)
        out = io.BytesIO()
        picture.save(out, format="WEBP", quality=QUALITY, method=6)
    return out.getvalue()


def draw(prompt: str, seed: int, candidates: tuple[chain.Candidate, ...]) -> tuple[bytes, str]:
    """One picture from the first pair that answers; a refusal or an outage moves to the next."""
    renderer = Renderer()
    failures = []
    for candidate in candidates:
        # A busy provider is waited for, a little longer each time: fifty pictures in a few minutes
        # is more than an image model's per-minute quota, and the next pair may be no better.
        for attempt in range(5):
            try:
                rendered = renderer.draw(prompt, seed, candidate)
                return rendered.data, f"{candidate.row.id}/{candidate.model}"
            except ProviderRefused as error:
                failures.append(f"{candidate.row.id}/{candidate.model} refused: {error}")
                break
            except ProviderError as error:
                failures.append(f"{candidate.row.id}/{candidate.model}: {str(error).splitlines()[0]}")
                time.sleep(20 * (attempt + 1))
    raise RuntimeError("; ".join(failures) or "no image model to ask")


def install(group: str, key: str, master: bytes) -> int:
    """Write a master's tile into the bundle and the prototype; returns its size."""
    small = tile(master)
    for root in (WEB_ART, PROTOTYPE_ART):
        (root / group).mkdir(parents=True, exist_ok=True)
        (root / group / f"{key}.webp").write_bytes(small)
    return len(small)


def variants_sheet(drawn: list[tuple[str, str, int]], path: Path) -> None:
    """Each picture's versions side by side, numbered as `--pick` takes them."""
    rows = []
    for group, key in dict.fromkeys((group, key) for group, key, _ in drawn):
        cells = "".join(
            f'<figure><img src="{html.escape(str(MASTERS / group / f"{key}.{n}.webp"))}"><figcaption>{n}</figcaption></figure>'
            for g, k, n in drawn if (g, k) == (group, key))
        rows.append(f"<h2>{group}/{key}</h2><div class=g>{cells}</div>")
    path.write_text(
        "<!doctype html><meta charset=utf-8><title>Dialog art versions</title><style>"
        "body{font:14px system-ui;margin:24px;background:#EDF1F0}.g{display:grid;grid-template-columns:repeat(auto-fill,280px);gap:14px}"
        "img{width:280px;height:280px;border-radius:10px;display:block}figure{margin:0}figcaption{color:#40534E;margin-top:4px}"
        "</style>" + "".join(rows), encoding="utf-8")


def sheet(groups: dict[str, dict[str, str]], path: Path) -> None:
    rows = []
    for group, entries in groups.items():
        cells = "".join(
            f'<figure><img src="{html.escape(str(WEB_ART / group / f"{key}.webp"))}"><figcaption>{html.escape(key)}</figcaption></figure>'
            for key in entries if (WEB_ART / group / f"{key}.webp").exists())
        rows.append(f"<h2>{group}</h2><div class=g>{cells}</div>")
    path.write_text(
        "<!doctype html><meta charset=utf-8><title>Dialog art</title><style>"
        "body{font:14px system-ui;margin:24px;background:#EDF1F0}.g{display:grid;grid-template-columns:repeat(auto-fill,160px);gap:14px}"
        "img{width:160px;height:160px;border-radius:10px;display:block}figure{margin:0}figcaption{color:#40534E;margin-top:4px}"
        "</style>" + "".join(rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image-chain", default="", help="e.g. vertex, or vertex:gemini-3.1-flash-lite-image")
    parser.add_argument("--only", nargs="*", default=[], help="group/id or group, e.g. styles/pixel-art music")
    parser.add_argument("--force", action="store_true", help="draw again what is already on disk")
    parser.add_argument("--dry-run", action="store_true", help="list what would be drawn, and spend nothing")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--sheet", type=Path, default=MASTERS / "sheet.html")
    parser.add_argument("--variants", type=int, default=0, help="draw N versions of each, to choose from")
    parser.add_argument("--pick", nargs="*", default=[], help="group/id=n: make version n the tile")
    args = parser.parse_args(argv)

    groups = prompts()
    if args.pick:
        for choice in args.pick:
            name, _, number = choice.partition("=")
            group, _, key = name.partition("/")
            master = MASTERS / group / f"{key}.{number}.webp"
            if not number or not master.exists():
                raise SystemExit(f"There is no version {number or '?'} of {name}: draw it with --variants first.")
            (MASTERS / group / f"{key}.webp").write_bytes(master.read_bytes())
            print(f"{name} is now version {number} ({install(group, key, master.read_bytes()) // 1024} KB)")
        sheet(groups, args.sheet)
        return 0
    wanted = []
    for group, entries in groups.items():
        for key, prompt in entries.items():
            named = not args.only or group in args.only or f"{group}/{key}" in args.only
            exists = (WEB_ART / group / f"{key}.webp").exists()
            if named and (args.force or bool(args.only) or not exists):
                wanted.append((group, key, prompt))
    copies = max(1, args.variants)
    if args.variants:
        wanted = [(group, key, prompt, n) for group, key, prompt in wanted for n in range(1, copies + 1)]
    else:
        wanted = [(group, key, prompt, 0) for group, key, prompt in wanted]
    print(f"{len(wanted)} to draw.")
    if args.dry_run:
        for group, key, prompt, n in wanted:
            print(f"  {group}/{key}{f' version {n}' if n else ''}: {prompt[:120]}…")
        return 0

    chosen = [tuple(part.split(":", 1)) if ":" in part else part
              for part in args.image_chain.split(",") if part.strip()] or None
    candidates = chain.resolve("image", chosen, load_local())
    if not candidates:
        raise SystemExit("Nothing in providers.local.json can draw.")

    def one(item: tuple[str, str, str, int]) -> str:
        group, key, prompt, n = item
        named = f"{group}/{key}/{n}" if n else f"{group}/{key}"
        seed = int.from_bytes(hashlib.sha256(named.encode()).digest()[:4], "big") % 2_000_000_000
        try:
            master, who = draw(prompt, seed, candidates)
        except RuntimeError as error:
            return f"FAILED {group}/{key}: {error}"
        (MASTERS / group).mkdir(parents=True, exist_ok=True)
        if n:
            (MASTERS / group / f"{key}.{n}.webp").write_bytes(master)
            return f"drew {group}/{key} version {n} with {who}"
        (MASTERS / group / f"{key}.webp").write_bytes(master)
        return f"drew {group}/{key} with {who} ({install(group, key, master) // 1024} KB)"

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for line in pool.map(one, wanted):
            print(line, flush=True)
    MASTERS.mkdir(parents=True, exist_ok=True)
    if args.variants:
        drawn = [(group, key, n) for group, key, _, n in wanted if (MASTERS / group / f"{key}.{n}.webp").exists()]
        versions = MASTERS / "versions.html"
        variants_sheet(drawn, versions)
        print(f"Versions to choose from: {versions}")
        return 0
    sheet(groups, args.sheet)
    print(f"Contact sheet: {args.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
