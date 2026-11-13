"""Build the IPA face the interface sets transcriptions in (`web/src/fonts/acervo-ipa.woff2`).

IBM Plex Mono has no phonetic letters, tone letters or combining marks, and the Noto Sans subsets
published as packages drop the rarer combining marks (U+032F in ʊ̯, for one). A browser draws a letter
and the marks on it from one face, so a mark missing from the fallback face boxes its letter too —
which is what Android showed. This takes the upstream Noto Sans variable font (SIL OFL 1.1, the
`OFL.txt` beside the output), pins it at the regular instance and keeps Latin with every IPA block, so
that one face holds any letter-plus-mark cluster a transcription can contain.

Usage (fontTools and brotli are build tools, not project dependencies):

    curl -LO 'https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf'
    uv run --with fonttools --with brotli scripts/build_ipa_font.py 'NotoSans[wdth,wght].ttf'
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

OUTPUT = Path(__file__).resolve().parent.parent / "web" / "src" / "fonts" / "acervo-ipa.woff2"

# Latin letters ride along because a cluster is drawn whole from one face: a "u" from Plex Mono
# cannot carry a breve below from this face.
RANGES = [
    (0x0020, 0x007E),  # Basic Latin
    (0x00A0, 0x024F),  # Latin-1 Supplement, Latin Extended-A and -B
    (0x0250, 0x02AF),  # IPA Extensions
    (0x02B0, 0x02FF),  # Spacing Modifier Letters: ʰ ː ˈ ˌ and the tone letters ˥ ˦ ˧ ˨ ˩
    (0x0300, 0x036F),  # Combining Diacritical Marks
    (0x1D00, 0x1DBF),  # Phonetic Extensions and their supplement
    (0x1DC0, 0x1DFF),  # Combining Diacritical Marks Supplement
    (0x2016, 0x2016),  # ‖ major group
    (0x203F, 0x203F),  # ‿ linking
    (0xA700, 0xA71F),  # Modifier Tone Letters
]


def build(source: Path, output: Path) -> None:
    font = TTFont(source)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": 400, "wdth": 100})
    options = subset.Options()
    options.layout_features = ["*"]  # mark positioning and the tone-letter contours
    options.flavor = "woff2"
    options.name_IDs = ["*"]  # keep the copyright and licence records
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[cp for low, high in RANGES for cp in range(low, high + 1)])
    subsetter.subset(font)
    output.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.save(output)
    print(f"{output}: {output.stat().st_size // 1024} KB, {len(font.getBestCmap())} characters")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="the upstream Noto Sans font file")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    build(args.source, args.output)


if __name__ == "__main__":
    main()
