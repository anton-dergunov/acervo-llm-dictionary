"""Write stories with the real prompts against a real model, and print them to be read.

The question this answers is not "is the story good" — that is `docs/plans/quality/story-quality.md`, and it
needs a method this does not have. It answers the cheaper questions that have to be settled first,
and that a stub test cannot reach:

- Does the model hold the shape at all, and how often does `parse_reply` refuse it?
- Does it actually use every word it was given, and report the forms it used **verbatim**?
- Are the parts the length the reader was built for, or does the page have to scroll?
- Does the translation come back with the same number of parts, in the same order?
- Do the image briefs restate the cast, or do they say "the same man as before"?

Everything it prints is meant to be read by a person. It deliberately draws no pictures: the briefs
are what is being checked here, and the pictures are the owner's call.

    export $(grep -v '^#' .env | xargs)   # or: set -a; . ./.env; set +a
    .venv/bin/python experiments/story-quality/run.py --words asombroso,panadería,ladrar --kind funny
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from acervo.models import chain, load_catalogue  # noqa: E402
from acervo.stories import illustrate, translate, types, write  # noqa: E402

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
LANGUAGES = {"es": "Spanish", "en": "English", "zh": "Chinese", "de": "German", "fr": "French"}

# Stand-in vocabulary. Real words, with the definitions a real article would carry, so the prompt is
# exercised on what it will actually be given rather than on bare headwords.
SAMPLE = {
    "asombroso": ("adj", "amazing, astonishing", "Que causa gran sorpresa o admiración."),
    "panadería": ("noun", "bakery", "Tienda donde se hace o se vende pan."),
    "ladrar": ("verb", "to bark", "Dar ladridos el perro."),
    "madrugar": ("verb", "to get up early", "Levantarse temprano, al amanecer."),
    "empeñarse": ("verb", "to insist, to be set on", "Insistir con obstinación en algo."),
    "hormiga": ("noun", "ant", "Insecto pequeño que vive en colonias."),
    "tejado": ("noun", "roof", "Parte superior de un edificio, cubierta de tejas."),
    "susurrar": ("verb", "to whisper", "Hablar en voz muy baja."),
}


def words_for(names: list[str], language: str) -> list[dict]:
    out = []
    for index, name in enumerate(names):
        pos, gloss, definition = SAMPLE.get(name, ("noun", "", ""))
        out.append({
            "id": f"lexemesample{index:03d}"[:15].ljust(15, "0"),
            "headword": name, "lemma": name, "pos": pos,
            "gloss": gloss, "definition": definition,
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--words", default="asombroso,panadería,ladrar")
    parser.add_argument("--language", default="es")
    parser.add_argument("--kind", default="funny", help="a story type id, or 'surprise'")
    parser.add_argument("--parts", type=int, default=4)
    parser.add_argument("--chain", default="gemini-free", help="comma-separated provider ids")
    parser.add_argument("--translate", action="store_true", help="also ask for the translation")
    parser.add_argument("--brief", action="store_true", help="also ask for the image briefs")
    parser.add_argument("--into", default="en", help="the language to translate into")
    args = parser.parse_args()

    catalogue = load_catalogue()
    chosen = [one.strip() for one in args.chain.split(",") if one.strip()]
    candidates = chain.resolve("text", chosen, catalogue)
    if not candidates:
        print(f"No usable pair for {chosen}. Is the key exported?", file=sys.stderr)
        return 2

    table = types.load_types()
    names = [one.strip() for one in args.words.split(",") if one.strip()]
    words = words_for(names, args.language)
    story_type = table.surprise("|".join(names)) if args.kind == "surprise" else table[args.kind]

    writer = write.StoryWriter(catalogue, candidates, (PROMPTS / "acervo_story_write.md").read_text())
    request = write.build_request(
        language=args.language, language_name=LANGUAGES.get(args.language, args.language),
        words=words, story_type_brief=story_type.brief, story_type_label=story_type.label,
        parts=args.parts,
    )

    started = time.monotonic()
    try:
        story, usage = writer.write(request, words)
    except write.StoryRefused as refused:
        print(f"REFUSED: {refused.reason}")
        return 1
    elapsed = time.monotonic() - started

    print("=" * 78)
    print(f"{story.emoji}  {story.title}    [{story_type.label}]")
    print(f"{usage['provider']}/{usage['model']} · {elapsed:.1f}s")
    print("=" * 78)
    for index, part in enumerate(story.parts, 1):
        sentences = write._sentences(part.text)
        print(f"\n{index}. {part.heading}   ({len(part.text)} chars, {sentences} sentences)")
        print(f"   {part.text}")

    total = sum(write._sentences(p.text) for p in story.parts)
    print(f"\n--- {len(story.parts)} parts, {total} sentences total ---")
    for word in words:
        found = story.forms.get(word["id"], ())
        mark = "OK  " if found else "MISS"
        print(f"  {mark} {word['headword']:<14} {', '.join(found) if found else '— NOT USED'}")

    if args.translate:
        translator = translate.Translator(
            catalogue, candidates, (PROMPTS / "acervo_story_translate.md").read_text()
        )
        done, tusage = translator.translate(
            translate.build_request(
                title=story.title, parts=story.parts,
                source_name=LANGUAGES.get(args.language, args.language),
                target_name=LANGUAGES.get(args.into, args.into), target_code=args.into,
            ),
            story.parts,
        )
        print(f"\n{'=' * 78}\nTRANSLATION — {done.title}   ({tusage['seconds']}s)\n{'=' * 78}")
        for index, part in enumerate(done.parts, 1):
            print(f"\n{index}. {part.heading}\n   {part.text}")

    if args.brief:
        briefer = illustrate.BriefWriter(
            catalogue, candidates, (PROMPTS / "acervo_story_brief.md").read_text()
        )
        briefed, busage = briefer.write(
            illustrate.build_request(
                title=story.title, parts=story.parts,
                language_name=LANGUAGES.get(args.language, args.language),
            ),
            story.parts,
        )
        print(f"\n{'=' * 78}\nIMAGE BRIEFS   ({busage['seconds']}s)\n{'=' * 78}")
        print(f"\nCAST:  {briefed.cast}\nWORLD: {briefed.world}")
        style = types.load_types().style_for(story_type, "sample")
        for index, brief in enumerate(briefed.briefs, 1):
            print(f"\n{index}. {brief}")
        print(f"\n(style that would be used: {style})")

    print(f"\n{json.dumps(usage, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
