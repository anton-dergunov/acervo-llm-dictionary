"""Which encoding should a stored pronunciation be in? A blind listening test.

Two commands:

    python experiments/pronunciation-encoding/run.py make     # synthesise, encode, shuffle, write the sheet
    python experiments/pronunciation-encoding/run.py reveal   # only once the sheet is filled in

**One master per piece, encoded every way.** The first attempt asked the API for the same sentence in
each encoding and compared those, and that was wrong: a Gemini voice *re-performs* the line on every
call — the same request came back 16,992 bytes one minute and 22,176 the next — so the candidates
differed by performance as much as by codec. So each piece is synthesised **once**, uncompressed, and
every candidate is that one master encoded locally. Google's own files are still fetched and measured,
to show that its bitrates are what the local encodes are set to.

**Blind by construction.** Every candidate is decoded back to a plain 24 kHz WAV under a shuffled id,
so a file extension cannot name the codec while the artifacts — the thing being judged — survive
decoding untouched, which is what a player does anyway before the sound reaches an ear.

The API is called directly rather than through `acervo.models`, deliberately: this test needs
encodings and sample rates the catalogue does not declare, and an experiment that had to change the
shipped row in order to measure it would be measuring the change. `experiments/` may not be imported
by anything that ships (`tests/unit/server/test_layering.py`), and this keeps that trivially true.

Nothing here is a second pipeline: the outcome is one value in the Google Cloud family (`src/acervo/models/families.py`).
"""

from __future__ import annotations

import base64
import json
import random
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# Two short words and two sentences meant to be *said*: a codec's artifacts are easiest to hear on a
# sibilant and on the decay at the end of a phrase, and hardest on a monotone.
WORD_VOICE = {"model": "wavenet", "name": "es-ES-Wavenet-F", "languageCode": "es-ES"}
SENTENCE_VOICE = {"model": "gemini-3.1-flash-tts-preview", "name": "Kore", "languageCode": "es-ES"}


@dataclass(frozen=True)
class Piece:
    id: str
    kind: str
    text: str
    voice: dict
    style: str | None


PIECES = (
    Piece("word-1", "word", "picar", WORD_VOICE, None),
    Piece("word-2", "word", "la sobremesa", WORD_VOICE, None),
    Piece(
        "sentence-1", "sentence", "¡Me pica todo el cuerpo desde que volví del campo!", SENTENCE_VOICE,
        "Read this Spanish sentence aloud the way a native speaker would say it in the moment, "
        "sounding exasperated, scratching and complaining to a friend.",
    ),
    Piece(
        "sentence-2", "sentence", "Espero que se mejoren pronto. Un abrazo a toda la familia.", SENTENCE_VOICE,
        "Read this Spanish sentence aloud the way a native speaker would say it in the moment, "
        "sounding warm and tender, a goodbye full of care.",
    ),
)

# The candidates, each applied to the one master. The first is the master itself — the ceiling, and
# the hidden anchor: a listener who scores it low is guessing, which is worth knowing.
#
# The three middle rates are not arbitrary. They are what Cloud TTS actually returns: `MP3` is 32 kbps
# from a Gemini voice and 64 kbps from a WaveNet one, and `OGG_OPUS` came back at 30–35 kbps. The last
# is the control that settles whose fault a metallic sound is — if 128 kbps MP3 sounds clean and 32
# does not, it is the bitrate; if the master sounds metallic too, it is the model and no encoding
# will help.
CANDIDATES = (
    ("LINEAR16", ["-c:a", "pcm_s16le"], "wav"),
    ("MP3_32", ["-c:a", "libmp3lame", "-b:a", "32k"], "mp3"),
    ("MP3_64", ["-c:a", "libmp3lame", "-b:a", "64k"], "mp3"),
    ("OPUS_32", ["-c:a", "libopus", "-b:a", "32k"], "ogg"),
    ("MP3_128", ["-c:a", "libmp3lame", "-b:a", "128k"], "mp3"),
)

# Fetched and measured, never listened to: what the API's own encoders produce for the same request,
# and what asking for 48 kHz does to a voice that is 24 kHz natively.
ASIDE = (("api-MP3", "MP3", None), ("api-OGG_OPUS", "OGG_OPUS", None), ("api-MP3-48k", "MP3", 48000),
         ("api-M4A", "M4A", None))
API_EXTENSIONS = {"MP3": "mp3", "OGG_OPUS": "ogg", "M4A": "m4a", "LINEAR16": "wav"}


def credentials() -> tuple[str, str]:
    import google.auth
    import google.auth.transport.requests

    project = _project()
    found, _ = google.auth.default(scopes=[SCOPE], quota_project_id=project)
    found.refresh(google.auth.transport.requests.Request())
    return found.token, project


def _project() -> str:
    """The quota project Cloud TTS insists on, from the environment or from the login itself."""
    import os

    named = (os.environ.get("ACERVO_VERTEX_PROJECT") or "").strip()
    if named:
        return named
    path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return json.loads(path.read_text(encoding="utf-8")).get("quota_project_id", "")


def synthesize(token: str, project: str, piece: Piece, encoding: str, sample_rate: int | None = None) -> bytes:
    audio: dict = {"audioEncoding": encoding}
    if sample_rate:
        audio["sampleRateHertz"] = sample_rate
    body: dict = {
        "input": {"text": piece.text},
        "voice": {"languageCode": piece.voice["languageCode"], "name": piece.voice["name"]},
        "audioConfig": audio,
    }
    if piece.voice["model"].startswith("gemini"):
        body["voice"]["modelName"] = piece.voice["model"]
    if piece.style:
        body["input"]["prompt"] = piece.style
    answer = httpx.post(
        SYNTHESIZE_URL,
        headers={"Authorization": f"Bearer {token}", "x-goog-user-project": project,
                 "Content-Type": "application/json"},
        json=body, timeout=120.0,
    )
    if not answer.is_success:
        raise RuntimeError(f"{answer.status_code} {' '.join(answer.text.split())[:120]}")
    return base64.b64decode(answer.json()["audioContent"])


def measured(path: Path) -> dict:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,bit_rate",
         "-show_entries", "stream=sample_rate,codec_name", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    found = json.loads(probe.stdout)
    stream = (found.get("streams") or [{}])[0]
    fmt = found.get("format") or {}
    seconds = float(fmt.get("duration") or 0)
    size = path.stat().st_size
    return {
        "bytes": size,
        "seconds": round(seconds, 2),
        "codec": stream.get("codec_name"),
        "sampleRate": int(stream.get("sample_rate") or 0),
        "kbps": round(size * 8 / seconds / 1000) if seconds else 0,
        "bytesPerSecond": round(size / seconds) if seconds else 0,
    }


def encode(source: Path, destination: Path, arguments: list[str]) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-ar", "24000", "-ac", "1",
         *arguments, str(destination)],
        check=True,
    )


def make() -> None:
    masters, encoded, blind = OUT / "masters", OUT / "encoded", OUT / "blind"
    for directory in (masters, encoded, blind):
        directory.mkdir(parents=True, exist_ok=True)
    token, project = credentials()
    print(f"project: {'set' if project else 'MISSING'}\n")

    facts: list[dict] = []
    aside: list[dict] = []
    for piece in PIECES:
        master = masters / f"{piece.id}.wav"
        master.write_bytes(synthesize(token, project, piece, "LINEAR16"))
        print(f"{piece.id:11} master {measured(master)['seconds']:5}s")

        for name, arguments, extension in CANDIDATES:
            path = encoded / f"{piece.id}-{name}.{extension}"
            encode(master, path, arguments)
            facts.append({"piece": piece.id, "candidate": name, "file": path.name, **measured(path)})
            print(f"  {name:9} {facts[-1]['bytes']:7}B {facts[-1]['kbps']:4} kbps")

        for name, encoding, rate in ASIDE:
            path = encoded / f"{piece.id}-{name}.{API_EXTENSIONS[encoding]}"
            try:
                path.write_bytes(synthesize(token, project, piece, encoding, sample_rate=rate))
            except RuntimeError as refused:
                print(f"  {name:9} refused: {refused}")
                aside.append({"piece": piece.id, "candidate": name, "refused": str(refused)})
                continue
            aside.append({"piece": piece.id, "candidate": name, "file": path.name, **measured(path)})
            print(f"  {name:9} {aside[-1]['bytes']:7}B {aside[-1]['kbps']:4} kbps   (measured, not listened to)")

    shuffled = list(facts)
    seed = random.randrange(10_000)
    random.Random(seed).shuffle(shuffled)
    key = []
    for index, fact in enumerate(shuffled, start=1):
        listener = f"a{index:02d}"
        # Back to a common WAV: the artifacts survive, the container does not give the codec away.
        encode(encoded / fact["file"], blind / f"{listener}.wav", ["-c:a", "pcm_s16le"])
        key.append({"id": listener, **fact})

    (OUT / "key.json").write_text(
        json.dumps({"seed": seed, "pieces": [asdict(piece) for piece in PIECES],
                    "candidates": key, "aside": aside}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _sheet(key)
    print(f"\n{len(key)} blind files in {blind}\nSheet: {OUT / 'listen.md'}")


def _sheet(key: list[dict]) -> None:
    """What the listener sees: which text each group says, and nothing else."""
    lines = [
        "# Blind listening sheet — pronunciation encoding",
        "",
        "Every file in a group is the **same performance**, encoded differently. Score each out of",
        "five for how *clean* it sounds — no metallic edge, no watery sibilants, no smearing at the",
        "end of a phrase — and add a word or two if you like. One file in each group is the",
        "uncompressed original; if you cannot tell which, that is a result in itself.",
        "",
        "```bash",
        "cd experiments/pronunciation-encoding/out/blind",
        "```",
        "",
        "Fill in the score column, then tell Claude the sheet is done — the mapping is revealed only",
        "when the whole sheet is.",
        "",
    ]
    by_piece: dict[str, list[str]] = {}
    for entry in key:
        by_piece.setdefault(entry["piece"], []).append(entry["id"])
    for piece in PIECES:
        ids = sorted(by_piece.get(piece.id, []))
        lines += [
            f"## {piece.id} — “{piece.text}”",
            "",
            f"`for f in {' '.join(ids)}; do echo $f; afplay $f.wav; done`",
            "",
            "| file | score /5 | what you hear |",
            "| --- | --- | --- |",
            *[f"| {one} |  |  |" for one in ids],
            "",
        ]
    (OUT / "listen.md").write_text("\n".join(lines), encoding="utf-8")


def _scores() -> dict[str, tuple[str, str]]:
    """The filled-in sheet, if it has been filled in: id -> (score, remark)."""
    sheet = OUT / "listen.md"
    found: dict[str, tuple[str, str]] = {}
    if not sheet.exists():
        return found
    for line in sheet.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| a"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[1]:
            found[cells[0]] = (cells[1], cells[2] if len(cells) > 2 else "")
    return found


# What a whole vocabulary would cost, at the ceiling `docs/README.md` sizes for.
HEADWORDS, SENTENCES = 10_000, 30_000


def reveal() -> None:
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    scores = _scores()
    rows = key["candidates"]

    print("\n## What each file was\n")
    print("| file | piece | candidate | kbps | bytes | score | what you heard |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in sorted(rows, key=lambda one: one["id"]):
        score, remark = scores.get(row["id"], ("", ""))
        print(f"| {row['id']} | {row['piece']} | {row['candidate']} | {row['kbps']} | {row['bytes']} "
              f"| {score} | {remark} |")

    print("\n## By candidate\n")
    print("| candidate | mean score | word B/s | sentence B/s | 10k words | 30k sentences |")
    print("| --- | --- | --- | --- | --- | --- |")
    for candidate, _arguments, _extension in CANDIDATES:
        mine = [row for row in rows if row["candidate"] == candidate]
        given = [float(scores[row["id"]][0].split("/")[0])
                 for row in mine
                 if scores.get(row["id"], ("", ""))[0].split("/")[0].replace(".", "", 1).isdigit()]
        words = [row for row in mine if row["piece"].startswith("word")]
        sentences = [row for row in mine if row["piece"].startswith("sentence")]
        per = lambda group, field: round(sum(row[field] for row in group) / len(group)) if group else 0
        print(f"| {candidate} | {round(sum(given) / len(given), 2) if given else '—'} "
              f"| {per(words, 'bytesPerSecond')} | {per(sentences, 'bytesPerSecond')} "
              f"| {per(words, 'bytes') * HEADWORDS / 1e6:.0f} MB "
              f"| {per(sentences, 'bytes') * SENTENCES / 1e6:.0f} MB |")

    print("\n## What the API's own encoders produced (measured, not listened to)\n")
    print("| piece | request | bytes | kbps | codec | sample rate |")
    print("| --- | --- | --- | --- | --- | --- |")
    for row in key.get("aside", []):
        if row.get("refused"):
            print(f"| {row['piece']} | {row['candidate']} | refused: {row['refused']} | | | |")
        else:
            print(f"| {row['piece']} | {row['candidate']} | {row['bytes']} | {row['kbps']} "
                  f"| {row['codec']} | {row['sampleRate']} |")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "make"
    if command == "make":
        make()
    elif command == "reveal":
        reveal()
    else:
        raise SystemExit("usage: run.py [make|reveal]")
