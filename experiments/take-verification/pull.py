"""Copy the server's recordings and the texts they should say down to `out/`, read-only.

    experiments/take-verification/.venv/bin/python experiments/take-verification/pull.py --host nas \
        --root /path/to/deployment

`--host` is an ssh alias and `--root` the deployment directory on it (the one holding `data/`);
neither is written into anything this experiment keeps. Copies the take cache, the call log, the
word clips and the story passages, and asks the database — opened `mode=ro`, never copied — for
the rows that name a recording's text. Everything lands in the gitignored `out/`, since it is the
owner's audio. Run again to pick up what was recorded since; rsync sends only the difference.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

QUERIES = {
    "pronunciations": "select id, target_kind, text, lang, emotion, audio_ref, audio_mime, provider_id, "
                      "model_id, voice from pronunciations where deleted=0",
    "story_parts": "select id, story, part_order, audio_provider_id, audio_model_id, audio_voice, "
                   "audio_segments from story_parts where deleted=0 and audio_segments != '[]'",
    "stories": "select id, language from stories where deleted=0",
    "loop_cues": "select c.loop, c.cue_order, c.role, c.language, c.text, c.take, c.start_seconds, "
                 "c.end_seconds, l.created_at as loop_created, l.audio_ref from loop_cues c "
                 "left join loops l on l.id=c.loop where c.deleted=0",
}


def run(*argv: str, stdout=None) -> None:
    subprocess.run(argv, check=True, stdout=stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    data = f"{args.root.rstrip('/')}/data"
    for name in ("takes", "logs", "media/audio", "media/stories", "db"):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    # `-a` keeps the mtime, which is what joins a take to the log line that recorded it.
    run("rsync", "-a", f"{args.host}:{data}/server/takes/", str(OUT / "takes") + "/")
    run("rsync", "-a", f"{args.host}:{data}/server/model-calls.log*", str(OUT / "logs") + "/")
    run("rsync", "-a", f"{args.host}:{data}/media/audio/", str(OUT / "media/audio") + "/")
    run("rsync", "-a", "--include=*/", "--include=*.ogg", "--include=*.mp3", "--include=*.flac",
        "--exclude=*", f"{args.host}:{data}/media/stories/", str(OUT / "media/stories") + "/")
    uri = f"file:{data}/server/acervo.db?mode=ro"
    for name, sql in QUERIES.items():
        with (OUT / "db" / f"{name}.json").open("wb") as handle:
            run("ssh", args.host, f"sqlite3 -json '{uri}' \"{sql}\"", stdout=handle)
    print("pulled into", OUT)


if __name__ == "__main__":
    main()
