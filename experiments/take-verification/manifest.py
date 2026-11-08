"""One row per recording, with the text it should say: `out/manifest.jsonl`.

    experiments/take-verification/.venv/bin/python experiments/take-verification/manifest.py

A take is named by a one-way digest, so its text comes from the call log: every `pronounce-take …
result=recorded` line names the text, language, direction and take, and its `bytes=` is the size
of the FLAC it stored. The store sets the file's mtime and a cache hit never rewrites it, so a line
is joined to the file of the same size written within `WINDOW` seconds before it. A line with two
candidates, or a file with no line, is dropped and counted rather than guessed. Word clips and
story passages are named by their rows directly.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import soundfile

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
WINDOW = 15.0

FIELD = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')


def parse(line: str) -> tuple[float, dict[str, str]] | None:
    if "pronounce-take outcome" not in line or "result=recorded" not in line:
        return None
    stamp = datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=timezone.utc)
    fields = {key: (json.loads(value) if value.startswith('"') else value)
              for key, value in FIELD.findall(line[24:])}
    return stamp.timestamp(), fields


def whisper_language(tag: str) -> str:
    return tag.split("-")[0].lower()


def seconds(path: Path) -> float:
    try:
        info = soundfile.info(str(path))
        return round(info.frames / info.samplerate, 3)
    except Exception:
        return 0.0


def takes() -> tuple[list[dict], Counter]:
    counts: Counter = Counter()
    files: dict[int, list[tuple[float, Path]]] = {}
    for path in (OUT / "takes").rglob("*"):
        if path.is_file() and not path.name.endswith(".part"):
            stat = path.stat()
            files.setdefault(stat.st_size, []).append((stat.st_mtime, path))
    counts["files"] = sum(len(group) for group in files.values())
    used: set[Path] = set()
    rows = []
    for log in sorted((OUT / "logs").glob("model-calls.log*"), reverse=True):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = parse(line)
            if parsed is None:
                continue
            counts["lines"] += 1
            stamp, fields = parsed
            near = [path for mtime, path in files.get(int(fields.get("bytes", -1)), [])
                    if -2.0 <= stamp - mtime <= WINDOW and path not in used]
            if len(near) != 1:
                counts["ambiguous" if near else "no_file"] += 1
                continue
            used.add(near[0])
            rows.append({
                "kind": "take", "id": near[0].stem[:16], "path": str(near[0].relative_to(OUT)),
                "text": fields["text"], "lang": whisper_language(fields["lang"]), "tag": fields["lang"],
                "direction": fields.get("emotion") or "", "take": int(fields.get("take", 0)),
                "pair": fields.get("pair", ""), "voice": fields.get("voice", ""), "recorded": line[:19],
            })
    counts["joined"] = len(rows)
    counts["unjoined_files"] = counts["files"] - len(used)
    return rows, counts


def words() -> list[dict]:
    rows = []
    for row in json.loads((OUT / "db/pronunciations.json").read_text(encoding="utf-8") or "[]"):
        path = OUT / "media" / row["audio_ref"]
        if path.is_file():
            rows.append({
                "kind": "word", "id": row["id"], "path": str(path.relative_to(OUT)), "text": row["text"],
                "lang": whisper_language(row["lang"]), "tag": row["lang"], "direction": row["emotion"] or "",
                "take": 0, "pair": f"{row['provider_id']}:{row['model_id']}", "voice": row["voice"],
            })
    return rows


def stories() -> list[dict]:
    rows = []
    language = {story["id"]: story["language"]
                for story in json.loads((OUT / "db/stories.json").read_text(encoding="utf-8") or "[]")}
    for part in json.loads((OUT / "db/story_parts.json").read_text(encoding="utf-8") or "[]"):
        for index, segment in enumerate(json.loads(part["audio_segments"])):
            path = OUT / "media" / segment["audioRef"]
            if not path.is_file():
                continue
            rows.append({
                "kind": "story", "id": f"{part['id']}-{index:02d}", "path": str(path.relative_to(OUT)),
                "text": segment["text"].strip(),
                "lang": whisper_language(language.get(part["story"], "")), "tag": language.get(part["story"], ""), "direction": segment.get("direction") or "",
                "take": 0, "pair": f"{part['audio_provider_id']}:{part['audio_model_id']}", "voice": part["audio_voice"],
            })
    return rows


def main() -> None:
    take_rows, counts = takes()
    rows = take_rows + words() + stories()
    for row in rows:
        row["seconds"] = seconds(OUT / row["path"])
    with (OUT / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("takes:", dict(counts))
    print("rows:", dict(Counter(row["kind"] for row in rows)))
    print("take languages:", dict(Counter(row["tag"] for row in take_rows)))
    if "--sample" in sys.argv:
        import random
        for row in random.Random(1).sample(take_rows, 5):
            print(row["path"], "|", row["text"], "|", row["tag"])


if __name__ == "__main__":
    main()
