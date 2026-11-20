"""Clean and level the chosen recordings, and lay them out for a blind listen.

    experiments/ipa-sounds/.venv/bin/python experiments/ipa-sounds/process.py fetch    # download the picks
    experiments/ipa-sounds/.venv/bin/python experiments/ipa-sounds/process.py build    # three versions each
    experiments/ipa-sounds/.venv/bin/python experiments/ipa-sounds/process.py report   # unblind the labels
    experiments/ipa-sounds/.venv/bin/python experiments/ipa-sounds/process.py final    # the files to ship

The experiment's own environment (`.venv` here: numpy, scipy, soundfile, pyloudnorm, noisereduce,
deepfilternet with torch) keeps the denoiser out of the project's requirements.

`fetch` downloads the original of every file picked in results/labels.json to out/originals/
(paced, once). `build` makes three versions of each:

- `plain`: as recorded;
- `gate`: stationary spectral gating (noisereduce), the noise profile taken from the recording's
  own quietest stretches, reducing the noise by 80% rather than to nothing; left as recorded where
  there is no silence to learn from, where the silence is digital zeros, or where it would take more
  than 1.5 dB off the sound itself (see `gate`);
- `dfn`: DeepFilterNet 3, a speech-enhancement model, its attenuation capped at 24 dB.

All three are then treated alike: cut to the sound with a little silence either side (the bounds
found once, on `plain`, so every version is the same length), faded in and out over 10 ms, and set
to the same loudness. Loudness is ITU BS.1770 (K-weighted, gated) on 100 ms blocks, since many
recordings are shorter than the standard 400 ms; the target is TARGET_LUFS, and the gain stops where
the true peak (4× oversampled) would pass PEAK_CEILING, so nothing clips. A recording that cannot
reach the target without clipping stays quieter, and the report names it.

The versions go to out/compare/<n>/ under letters shuffled per card (out/compare/key.json), for
compare.py. `report` writes results/processing-summary.json: per card the version the owner chose,
the noise floor and signal-to-noise ratio measured, and the gain applied.

`final` encodes the version each card ships (`chosen`) into the app, web/src/ipa/sounds/, as Ogg
Opus the way stored pronunciations are (`acervo/pronunciation/encode.py`: libsndfile, compression
0.8), each named by a digest of its bytes. It writes each row's `sound` and the credits
(`recordings`) into the app's table, web/src/ipa/symbols.json, and the record of what it did, per
card the version and file and per file its size and length, into results/recordings.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile
from scipy.signal import resample_poly

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results"
APP = HERE.parents[1] / "web" / "src" / "ipa"
RATE = 48000
TARGET_LUFS = -20.0
PEAK_CEILING = -1.0  # dBTP
USER_AGENT = "AcervoIPASurvey/0.1 (one-off survey of IPA recordings for a language-learning app)"
VERSIONS = ("plain", "gate", "dfn")
OPUS_COMPRESSION = 0.8  # acervo/pronunciation/encode.py's COMPRESSION: the app's pronunciations, same codec and setting
CHANGED = {"plain": "trimmed and level-adjusted", "gate": "trimmed, noise-reduced and level-adjusted",
           "dfn": "trimmed, noise-reduced and level-adjusted"}


def picks() -> list[dict]:
    """Every card with a picked recording, in the order of results/labels.json, with its candidate entry."""
    labels = json.loads((RESULTS / "labels.json").read_text(encoding="utf-8"))
    rows = json.loads((RESULTS / "candidates.json").read_text(encoding="utf-8"))["rows"]
    found = []
    for row_id, label in labels.items():
        pick = label.get("pick")
        if pick in (None, "none"):
            continue
        candidate = next(c for c in rows[row_id] if c["file"] == pick)
        found.append({"id": row_id, **candidate})
    return found


def original_path(file: str) -> Path:
    return OUT / "originals" / file


def fetch() -> None:
    """Download each picked original once. Through curl: Wikimedia's media servers throttled Python's
    client to one file in several minutes, while curl with the same User-Agent was served at once."""
    for number, pick in enumerate(picks(), 1):
        path = original_path(pick["file"])
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".part")
        for attempt in range(6):
            status = subprocess.run(["curl", "-s", "-A", USER_AGENT, "-o", str(partial), "-w", "%{http_code}",
                                     pick["original"]], capture_output=True, text=True).stdout
            if status == "200":
                partial.replace(path)
                break
            print(f"  {status} on {pick['file']}, waiting 300 s", file=sys.stderr)
            time.sleep(300)
        else:
            partial.unlink(missing_ok=True)
            raise SystemExit(f"could not download {pick['file']}")
        print(f"{number} {pick['file']}", file=sys.stderr)
        time.sleep(8.0)


def decode(path: Path) -> np.ndarray:
    """Mono float32 at RATE, whatever the container."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def frame_db(signal: np.ndarray, frame: int = RATE // 50) -> np.ndarray:
    count = max(1, len(signal) // frame)
    frames = signal[: count * frame].reshape(count, frame)
    return 10 * np.log10(np.mean(frames ** 2, axis=1) + 1e-12)


def measure(signal: np.ndarray) -> dict:
    """Noise floor (10th percentile of 20 ms frames), loudest frame, and where the sound is."""
    db = frame_db(signal)
    floor, top = float(np.percentile(db, 10)), float(db.max())
    active = np.flatnonzero(db > max(top - 40, floor + 10))
    start, end = (int(active[0]), int(active[-1]) + 1) if len(active) else (0, len(db))
    frame = RATE // 50
    return {"floor": floor, "top": top, "snr": top - floor,
            "start": max(0, start * frame - int(0.12 * RATE)), "end": min(len(signal), end * frame + int(0.2 * RATE))}


def quiet_stretch(signal: np.ndarray, floor: float) -> np.ndarray | None:
    """The recording's quietest frames joined: its noise, for the gate to learn from."""
    frame = RATE // 50
    db = frame_db(signal, frame)
    quiet = [signal[i * frame:(i + 1) * frame] for i in np.flatnonzero(db < floor + 3)]
    return np.concatenate(quiet) if len(quiet) * frame >= RATE // 10 else None


def gate(signal: np.ndarray, found: dict) -> tuple[np.ndarray, str | None]:
    """The gated recording, or the recording untouched and why. A gate learns the noise from the
    recording's silences, so it is skipped where there is none to learn from (a sustained vowel cut
    tight), where the silence is digital zeros (nothing to remove: the gate then took the sound for
    noise, −14 dB on ə, a, ɔ̃), and where it would take more than 1.5 dB off the sound itself."""
    import noisereduce
    if found["floor"] < -90:
        return signal, "digital silence: no noise to remove"
    if found["snr"] < 25:
        return signal, "no silence to learn the noise from"
    noise = quiet_stretch(signal, found["floor"])
    if noise is None:
        return signal, "no silence to learn the noise from"
    gated = noisereduce.reduce_noise(y=signal, sr=RATE, y_noise=noise, stationary=True, prop_decrease=0.8).astype(np.float32)
    cut = slice(found["start"], found["end"])
    if loudness(gated[cut]) < loudness(signal[cut]) - 1.5:
        return signal, "gating took part of the sound itself"
    return gated, None


_dfn = None


def dfn(signal: np.ndarray) -> np.ndarray:
    global _dfn
    import torch
    from df.enhance import enhance, init_df
    if _dfn is None:
        model, state, _ = init_df(log_level="ERROR")
        _dfn = (model, state)
    model, state = _dfn
    tensor = torch.from_numpy(signal).unsqueeze(0)
    return enhance(model, state, tensor, atten_lim_db=24).squeeze(0).numpy().astype(np.float32)


def true_peak_db(signal: np.ndarray) -> float:
    return float(20 * np.log10(np.max(np.abs(resample_poly(signal, 4, 1))) + 1e-12))


def loudness(signal: np.ndarray) -> float:
    meter = pyloudnorm.Meter(RATE, block_size=0.100)
    padded = signal if len(signal) >= RATE // 10 else np.pad(signal, (0, RATE // 10 - len(signal)))
    return float(meter.integrated_loudness(padded))


def finish(signal: np.ndarray, start: int, end: int) -> tuple[np.ndarray, dict]:
    """Cut to the sound, fade the edges, and bring it to the target loudness without clipping."""
    cut = signal[start:end].copy()
    fade = int(0.01 * RATE)
    cut[:fade] *= np.linspace(0, 1, fade)
    cut[-fade:] *= np.linspace(1, 0, fade)
    measured, peak = loudness(cut), true_peak_db(cut)
    wanted = TARGET_LUFS - measured
    gain = min(wanted, PEAK_CEILING - peak)
    return (cut * 10 ** (gain / 20)).astype(np.float32), {
        "loudness": round(measured, 1), "truePeak": round(peak, 1), "gain": round(gain, 1),
        "short": round(wanted - gain, 1),
    }


def build() -> None:
    compare = OUT / "compare"
    compare.mkdir(parents=True, exist_ok=True)
    shuffle = random.Random(20261118)
    key, stats = {}, {}
    for number, pick in enumerate(picks()):
        signal = decode(original_path(pick["file"]))
        found = measure(signal)
        gated, skipped = gate(signal, found)
        versions = {"plain": signal, "gate": gated, "dfn": dfn(signal)}
        letters = list("ABC")
        shuffle.shuffle(letters)
        folder = compare / str(number)
        folder.mkdir(exist_ok=True)
        key[pick["id"]] = {"n": number, "letters": {}}
        stats[pick["id"]] = {"file": pick["file"], "floor": round(found["floor"], 1), "snr": round(found["snr"], 1),
                             "gateSkipped": skipped, "versions": {}}
        for letter, version in zip(letters, VERSIONS):
            out, info = finish(versions[version][: len(signal)], found["start"], found["end"])
            soundfile.write(folder / f"{letter}.wav", out, RATE, subtype="PCM_24")
            key[pick["id"]]["letters"][letter] = version
            stats[pick["id"]]["versions"][version] = info
        print(f"{number} {pick['id']}: snr {found['snr']:.0f} dB, floor {found['floor']:.0f} dBFS", file=sys.stderr)
    (compare / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    (compare / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")


def report() -> None:
    key = json.loads((OUT / "compare" / "key.json").read_text(encoding="utf-8"))
    stats = json.loads((OUT / "compare" / "stats.json").read_text(encoding="utf-8"))
    labels_path = RESULTS / "processing-labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    cards = {}
    for row_id, entry in key.items():
        label = labels.get(row_id, {})
        best = label.get("best")
        cards[row_id] = {**stats[row_id], "chosen": "same" if best == "same" else entry["letters"].get(best),
                         "letters": entry["letters"], "note": label.get("note")}
    tally: dict[str, int] = {}
    for card in cards.values():
        tally[str(card["chosen"])] = tally.get(str(card["chosen"]), 0) + 1
    summary = {"about": "Per card: the version of its recording the owner chose blind (plain, gate, dfn or same), "
                        "the noise floor and signal-to-noise ratio of the original, and per version the loudness "
                        "measured, true peak, gain applied and how far it fell short of the target to avoid clipping.",
               "targetLufs": TARGET_LUFS, "peakCeiling": PEAK_CEILING, "tally": tally, "cards": cards}
    out = RESULTS / "processing-summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(tally), f"wrote {out}")


def chosen(row_id: str, stats: dict, key: dict, labels: dict) -> str:
    """The version a card ships: the owner's blind pick where they made one, else the rule their picks
    settled (README, "Third round"). The gate where it ran: it keeps breath, friction and rasp that
    DeepFilterNet takes for noise (10 of 12 picks on the cards it changes most). DeepFilterNet where
    the gate had no silence to learn from: the only version without the hiss (15 of 16 picks). As
    recorded where the silence is digital zeros, since there is no hiss to remove."""
    best = labels.get(row_id, {}).get("best")
    if best in key[row_id]["letters"]:
        return key[row_id]["letters"][best]
    skipped = stats[row_id]["gateSkipped"]
    if skipped is None:
        return "gate"
    return "plain" if skipped.startswith("digital") else "dfn"


def author(candidate: dict, recorded: dict[str, str]) -> str:
    """The author as a credit line should name them: Commons' metadata, cleaned of the sentences its
    tools wrap round a name, or for the files whose metadata names nobody, the recorder their
    description page states (results/authors.json)."""
    import re
    raw = " ".join(candidate["author"].split())
    if not raw:
        return recorded[candidate["file"]]
    for pattern in (r"No machine-readable author provided\. (.+) assumed \(based on copyright claims\)\.",
                    r"Recorded by (.+?)\.?", r"Speaker: (\S+) Recorder: \1", r"User:(.+)",
                    r"The original uploader was (.+) at English Wikipedia\."):
        found = re.fullmatch(pattern, raw)
        if found:
            return found[1]
    return raw


def table_rows(table: dict):
    """Every row of the app's table with the id its card has here (review.py's ids)."""
    for section in ("consonants", "affricates", "combinations", "vowels"):
        for entry in table[section]:
            yield entry["symbol"], entry
    for entry in table["diacritics"]:
        yield entry["example"], entry
    for entry in table["suprasegmentals"]:
        yield f"mark {entry['symbol']}", entry
    for entry in table["tones"]["contours"]:
        yield f"tone {entry['letters']}", entry
    for entry in table["tones"]["marks"]:
        yield f"tone mark {entry['example']}", entry
    for part in ("initials", "finals"):
        for entry in table["pinyin"][part]:
            yield f"pinyin {entry['letters']}", entry
    for entry in table["pinyin"]["tones"]:
        yield f"pinyin tone {entry['number']}", entry


def final() -> None:
    """Encode the chosen version of every card, once per distinct file, and write the credits."""
    key = json.loads((OUT / "compare" / "key.json").read_text(encoding="utf-8"))
    stats = json.loads((OUT / "compare" / "stats.json").read_text(encoding="utf-8"))
    labels_path = RESULTS / "processing-labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    recorded = json.loads((RESULTS / "authors.json").read_text(encoding="utf-8"))["authors"]
    target = APP / "sounds"
    if target.exists():
        for old in target.glob("*.ogg"):
            old.unlink()
    target.mkdir(parents=True, exist_ok=True)
    # Once per recording and version, not per card: cards share recordings (the Mandarin syllables
    # especially), and an Ogg stream carries a random serial number, so encoding the same audio twice
    # gives two files with different digests.
    cards, files, encoded, total = {}, {}, {}, 0
    for pick in picks():
        row_id = pick["id"]
        version = chosen(row_id, stats, key, labels)
        if (pick["file"], version) in encoded:
            cards[row_id] = {"file": encoded[pick["file"], version], "version": version}
            continue
        letter = next(k for k, v in key[row_id]["letters"].items() if v == version)
        samples, rate = soundfile.read(OUT / "compare" / str(key[row_id]["n"]) / f"{letter}.wav", dtype="float32")
        out = io.BytesIO()
        with soundfile.SoundFile(out, "w", samplerate=rate, channels=1, format="OGG", subtype="OPUS",
                                 compression_level=OPUS_COMPRESSION) as writing:
            writing.write(samples)
        data = out.getvalue()
        name = hashlib.sha256(data).hexdigest()[:16] + ".ogg"
        encoded[pick["file"], version] = name
        (target / name).write_bytes(data)
        total += len(data)
        files[name] = {"source": pick["file"], "author": author(pick, recorded), "licence": pick["license"],
                       "licenceUrl": pick.get("licenseUrl"), "page": pick["page"], "changes": CHANGED[version],
                       "bytes": len(data), "seconds": round(len(samples) / rate, 2)}
        cards[row_id] = {"file": name, "version": version}
    tally: dict[str, int] = {}
    for card in cards.values():
        tally[card["version"]] = tally.get(card["version"], 0) + 1
    manifest = {"about": "The recording each card plays (`file`, in web/src/ipa/sounds/, named by a digest of its bytes) and "
                         "the version of it chosen (README, \"Third round\"); per file its Commons source, author, "
                         "licence, how it was changed, size and length. Ogg Opus, as the app's pronunciations.",
                "codec": "Ogg Opus, libsndfile compression 0.8, mono 48 kHz", "tally": tally,
                "totalBytes": total, "cards": cards, "files": dict(sorted(files.items()))}
    table_path = APP / "symbols.json"
    table = json.loads(table_path.read_text(encoding="utf-8"))
    for row_id, entry in table_rows(table):
        entry.pop("sound", None)
        # A diacritic's card is its example (pʰ for aspiration, ɫ for velarization, which is also
        # the letter ɫ's card): it plays that example.
        if row_id in cards:
            entry["sound"] = cards[row_id]["file"]
    table["recordings"] = {name: {k: file[k] for k in ("source", "author", "licence", "licenceUrl", "page", "changes")}
                           for name, file in sorted(files.items())}
    table_path.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (RESULTS / "recordings.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(tally), f"{len(files)} files, {total / 1e6:.2f} MB, in {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=("fetch", "build", "report", "final"))
    {"fetch": fetch, "build": build, "report": report, "final": final}[parser.parse_args().step]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
