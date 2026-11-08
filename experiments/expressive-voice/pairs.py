"""Round 2: does any tag move ElevenLabs' accent at all? Two takes of one text, heard as a pair.

    .venv/bin/python experiments/expressive-voice/pairs.py bill       # English credits; spends nothing
    .venv/bin/python experiments/expressive-voice/pairs.py record     # the English takes
    experiments/expressive-voice/.venv/bin/python experiments/expressive-voice/transcribe.py --pairs
    .venv/bin/python experiments/expressive-voice/pairs.py blind      # loudness-matched A/B + key
    .venv/bin/python experiments/expressive-voice/pairs.py serve --host "$(tailscale ip -4)"
    .venv/bin/python experiments/expressive-voice/pairs.py report     # after listening

Round 1 asked for a rating of "Argentine" take by take, and only two of its accent-alone texts held
a sound that differs («ll», «y» before a vowel). A pair asks something the owner can answer for any
text: of these two, which sounds Argentine (or British)? If a tag moves the accent, the take sent
the Argentine tag is picked; if it does not, the two sound alike.

- **Spanish costs nothing:** round 1 recorded every accent text on Eleven v4 under an Argentine tag
  and a Spain tag, three ways (`current`, `calm`, `named`), and Gemini under both directions.
- **English:** Sarah, an American voice, under `British English accent` and `American English
  accent`; Gemini under its accent sentence for `en-GB` and `en-US`. Two sentences: a third, the word
  "hogwash", did not fit the 356 credits left on 8 Nov 2026.
- **Gemini's pairs are the calibration:** if its two takes are not told apart, the contrast is not
  audible in that text and a pair says nothing about ElevenLabs.

The page hides which system made a pair and which take is which; the key stays in
`out/pairs/key.json`. Labels go to `out/pairs/labels.json` on every tap; `report` unblinds them into
`results/pairs.md` and copies both into `results/`.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import review
import run
from acervo.pronunciation import speak

PAIRS = run.OUT / "pairs"
TAKES = run.RESULTS / "pairs-takes.jsonl"
TRANSCRIPTS = run.RESULTS / "pairs-transcripts.jsonl"
SEED = f"{run.SEED}:pairs"

# Spanish: round 1's accent items, Argentina's and Spain's of the same text.
SPANISH = [(f"a{n:02d}", f"a{n + 7:02d}") for n in range(1, 8)]
SPANISH_SOURCES = ("v4-current", "v4-calm", "v4-named", "gemini")

# English: two sentences from the set, each read as British and as American.
ENGLISH = ("f10", "f12")
ENGLISH_TAKES = {
    # source: (system id, language, the tag ElevenLabs is sent; None for Gemini's own sentence)
    "v4-british": ("v4", "en-GB", "British English accent"),
    "v4-american": ("v4", "en-US", "American English accent"),
    "gemini-gb": ("gemini", "en-GB", None),
    "gemini-us": ("gemini", "en-US", None),
}
ENGLISH_PAIRS = {"v4-named": ("v4-british", "v4-american"), "gemini": ("gemini-gb", "gemini-us")}

# A tag "moves the accent" when the tagged variety is picked in nearly all its pairs, and Gemini's
# pairs, on the same texts, show the contrast can be heard at all.
THRESHOLD = {"es": 6, "en": 2}
ANSWERS = ("A", "B", "same", "unsure")
FLAGS = ("said twice", "read aloud", "other words")

_lock = threading.Lock()


def master(key: str) -> Path:
    return run.OUT / "masters" / f"{key.replace('/', '_')}.wav"


def definitions() -> list[dict[str, Any]]:
    """Every pair: which take is the target (Argentine / British) and which the other."""
    by_item = {item["id"]: item for item in run.items()}
    found = []
    for target, other in SPANISH:
        for source in SPANISH_SOURCES:
            found.append({"language": "es", "question": "Argentine", "item": target, "source": source,
                          "text": by_item[target]["text"], "audible": bool(run.SHEISMO.search(by_item[target]["text"].lower())),
                          "target": f"{target}/{source}/1", "other": f"{other}/{source}/1"})
    for item in ENGLISH:
        for source, (british, american) in ENGLISH_PAIRS.items():
            found.append({"language": "en", "question": "British", "item": item, "source": source,
                          "text": by_item[item]["text"], "audible": True,
                          "target": f"{item}/{british}/1", "other": f"{item}/{american}/1"})
    return found


# ── record ──────────────────────────────────────────────────────────────────


def planned() -> list[dict[str, Any]]:
    by_item = {item["id"]: item for item in run.items()}
    return [{"item": item, "source": source, "text": by_item[item]["text"], "system": system,
             "language": language, "tag": tag}
            for item in ENGLISH for source, (system, language, tag) in ENGLISH_TAKES.items()]


def style(row: dict[str, Any]) -> speak.Direction:
    """Gemini: the accent sentence Acervo sends for this language. ElevenLabs: the tag under test."""
    sentence = speak.direction(run.template(run.ACCENT), "", row["language"])
    return speak.Direction(str(sentence), row["tag"]) if row["tag"] else sentence


def billed(row: dict[str, Any]) -> int:
    from acervo.models.elevenlabs import worded

    return len(worded(row["text"], row["tag"]))


def recorded() -> dict[str, dict[str, Any]]:
    if not TAKES.exists():
        return {}
    rows = [json.loads(line) for line in TAKES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {f"{row['item']}/{row['source']}/1": row for row in rows}


def bill(args: argparse.Namespace) -> None:
    providers = run.catalogue()
    left = run.credits(providers)
    todo = [row for row in planned() if f"{row['item']}/{row['source']}/1" not in recorded()]
    cost = sum(billed(row) for row in todo if run.BY_ID[row["system"]].provider == "elevenlabs")
    print(json.dumps({"credits": left, "allowed": int(left["left"] * (1 - run.MARGIN)), "cost": cost,
                      "takes": [f"{row['item']}/{row['source']}" for row in todo]}, indent=1))


def record(args: argparse.Namespace) -> None:
    providers = run.catalogue()
    have = recorded()
    todo = [row for row in planned() if f"{row['item']}/{row['source']}/1" not in have]
    cost = sum(billed(row) for row in todo if run.BY_ID[row["system"]].provider == "elevenlabs")
    left = run.credits(providers)["left"]
    if cost > left * (1 - run.MARGIN):
        sys.exit(f"ElevenLabs: these takes cost {cost} credits and {left} are left; nothing recorded")
    print(f"ElevenLabs: {cost} of {left} credits; {len(todo)} takes to record")
    TAKES.parent.mkdir(parents=True, exist_ok=True)
    for row in todo:
        system = run.BY_ID[row["system"]]
        key = f"{row['item']}/{row['source']}/1"
        started = time.monotonic()
        try:
            spoken = run.say(providers, system.provider, system.model, system.voice, row["text"], row["language"], style(row))
        except Exception as error:  # noqa: BLE001 — the provider's sentence is the finding
            print(f"  {key}: {run.failure(error)[:200]}")
            continue
        path = master(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if spoken.result.mime not in ("audio/wav", "audio/x-wav"):
            raw = path.with_suffix("." + speak.extension_for(spoken.result.mime))
            raw.write_bytes(spoken.result.data)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), str(path)], check=True)
            raw.unlink()
        else:
            path.write_bytes(spoken.result.data)
        entry = {"item": row["item"], "system": row["system"], "variant": row["source"].split("-", 1)[1],
                 "source": row["source"], "take": 1, "language": row["language"], "provider": system.provider,
                 "model": spoken.result.answer.model, "voice": spoken.result.voice,
                 "sent": str(spoken.direction) if spoken.direction else None,
                 "characters": billed(row) if system.provider == "elevenlabs" else len(row["text"]),
                 "seconds": run.seconds_of(path), "wait": round(time.monotonic() - started, 2)}
        with TAKES.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  {key}  {entry['seconds']}s  sent={(entry['sent'] or '')[:60]!r}")


# ── blind ───────────────────────────────────────────────────────────────────


def blind(args: argparse.Namespace) -> None:
    """Number the pairs in a shuffled order and put each pair's takes under A and B at random."""
    key = run._read(PAIRS / "key.json", {})
    if key:
        print(f"{len(key)} pairs already keyed; a label never comes to mean another pair")
    else:
        found = definitions()
        missing = [take for pair in found for take in (pair["target"], pair["other"]) if not master(take).exists()]
        if missing:
            sys.exit(f"{len(missing)} takes not recorded yet, e.g. {missing[0]}: run `record` first")
        shuffle = random.Random(SEED)
        shuffle.shuffle(found)
        for n, pair in enumerate(found, start=1):
            target = shuffle.choice("AB")
            key[f"p{n:02d}"] = {**pair, "letters": {target: pair["target"], "B" if target == "A" else "A": pair["other"]}}
        run._write(PAIRS / "key.json", key)
    for pair_id, pair in key.items():
        for letter, take in pair["letters"].items():
            target = PAIRS / pair_id / f"{letter}.wav"
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(master(take)), "-af",
                            "loudnorm=I=-20:TP=-1.5:LRA=11", "-ar", "24000", "-ac", "1", str(target)], check=True)
    print(f"{len(key)} pairs in {PAIRS}")


# ── the page ────────────────────────────────────────────────────────────────


def shown() -> list[dict[str, Any]]:
    """What the page is told: the text and the question, never the system or which take is which."""
    key = run._read(PAIRS / "key.json", {})
    return [{"id": pair_id, "text": pair["text"], "lang": pair["language"],
             "language": "Spanish" if pair["language"] == "es" else "English",
             "question": f"Which one sounds {pair['question']}?"} for pair_id, pair in key.items()]


class Handler(review.Handler):
    def do_GET(self) -> None:  # noqa: N802 — the stdlib's name
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/data":
            body = {"pairs": shown(), "labels": run._read(PAIRS / "labels.json", {}), "flags": FLAGS}
            return self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json")
        found = re.fullmatch(r"/a/(p\d\d)/([AB])", self.path)
        if found:
            return self._audio(PAIRS / found[1] / f"{found[2]}.wav")
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/rate":
            return self._send(404, b"not found", "text/plain")
        try:
            change = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            pair, field, value, letter = change["pair"], change["field"], change.get("value"), change.get("letter")
        except (ValueError, KeyError):
            return self._send(400, b"bad request", "text/plain")
        if pair not in run._read(PAIRS / "key.json", {}):
            return self._send(400, b"no such pair", "text/plain")
        with _lock:
            labels = run._read(PAIRS / "labels.json", {})
            mine = labels.setdefault(pair, {})
            if field == "pick":
                if value in ANSWERS:
                    mine["pick"] = value
                else:
                    mine.pop("pick", None)
            elif field == "flags" and letter in ("A", "B"):
                mine.setdefault("flags", {})[letter] = [flag for flag in FLAGS if flag in (value or [])]
            elif field == "note":
                mine["note"] = str(value or "")[:1000]
            else:
                return self._send(400, b"no such field", "text/plain")
            run._write(PAIRS / "labels.json", labels)
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")


STYLE = review.PAGE[review.PAGE.index("<style>"):review.PAGE.index("</style>") + len("</style>")]

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accent Pairs</title>
""" + STYLE + r"""
<style>
.question { font-size: 20px; font-weight: 600; margin: 16px 0 6px; }
.answers button { max-width: none; }
</style>
</head>
<body>
<header>
  <span class="count" id="count">Loading…</span>
  <span class="error" id="error"></span>
  <button id="unrated">Next unanswered</button>
</header>
<main id="main"></main>
<script>
const state = { pairs: [], labels: {}, flags: [], at: 0 };
const audio = new Audio();
let playing = null;
const WORDS = { A: "A", B: "B", same: "They sound the same", unsure: "Can't tell" };
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else if (v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) node.append(kid);
  return node;
};
const mine = pair => state.labels[pair.id] || {};
async function save(pair, field, value, letter) {
  const m = state.labels[pair.id] = state.labels[pair.id] || {};
  if (field === "flags") { m.flags = m.flags || {}; m.flags[letter] = value; }
  else if (value === null) delete m[field]; else m[field] = value;
  try {
    const answer = await fetch("/rate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pair: pair.id, field, value, letter }) });
    if (!answer.ok) throw new Error(answer.status);
    document.getElementById("error").textContent = "";
  } catch (e) { document.getElementById("error").textContent = "Not saved — is the laptop awake?"; }
  if (field !== "note" || !typing()) render();
}
function play(pair, letter) {
  const src = `/a/${pair.id}/${letter}`;
  if (playing === src && !audio.paused) { audio.pause(); playing = null; render(); return; }
  audio.src = src; playing = src; audio.play(); render();
}
audio.addEventListener("ended", () => { playing = null; if (!typing()) render(); });
let noteTimer = null;
// Redraws nobody tapped for — a note saving, a take ending — wait while a note is being typed:
// rebuilding the card replaces the focused field, and an iPad closes its keyboard the moment the
// focused field leaves the page. A tap always redraws.
const typing = () => document.activeElement && document.activeElement.tagName === "TEXTAREA";
function render() {
  const done = state.pairs.filter(p => mine(p).pick).length;
  document.getElementById("count").textContent = `${done} of ${state.pairs.length} answered · pair ${state.at + 1}`;
  const pair = state.pairs[state.at];
  const main = document.getElementById("main");
  if (!pair) { main.textContent = "No pairs."; return; }
  const scroll = window.scrollY, m = mine(pair);
  main.replaceChildren(...[
    $("div", { class: "group" }, pair.language),
    $("div", { class: "text", lang: pair.lang }, pair.text),
    $("p", { class: "legend" }, "The same text, read twice. Listen to both, as often as you like."),
    ["A", "B"].map(letter => {
      const src = `/a/${pair.id}/${letter}`, flags = (m.flags || {})[letter] || [];
      return $("div", { class: "take" },
        $("div", { class: "top" }, $("span", { class: "letter" }, letter),
          $("button", { class: "play" + (playing === src ? " on" : ""), onclick: () => play(pair, letter) },
            playing === src ? "■ Stop" : "▶ Play")),
        $("div", { class: "row flags" }, state.flags.map(flag => {
          const on = flags.includes(flag);
          return $("button", { class: on ? "on" : "", onclick: () => save(pair, "flags",
            on ? flags.filter(f => f !== flag) : [...flags, flag], letter) }, flag);
        })));
    }),
    $("div", { class: "question" }, pair.question),
    $("div", { class: "row answers" }, Object.entries(WORDS).map(([value, word]) =>
      $("button", { class: m.pick === value ? "on" : "", onclick: () => save(pair, "pick", m.pick === value ? null : value) }, word))),
    (() => { const note = $("textarea", { placeholder: "Note (optional)", rows: 1 }); note.value = m.note || "";
      note.addEventListener("input", () => { clearTimeout(noteTimer); noteTimer = setTimeout(() => save(pair, "note", note.value), 700); });
      return note; })(),
    $("div", { class: "nav" },
      $("button", { disabled: state.at === 0, onclick: () => go(state.at - 1) }, "← Previous"),
      $("button", { disabled: state.at === state.pairs.length - 1, onclick: () => go(state.at + 1) }, "Next →")),
  ].flat());
  window.scrollTo(0, scroll);
}
function go(n) {
  audio.pause(); playing = null; state.at = n;
  try { localStorage.setItem("accent-pairs-at", String(n)); } catch (e) {}
  render(); window.scrollTo(0, 0);
}
document.getElementById("unrated").addEventListener("click", () => {
  const n = state.pairs.length;
  for (let k = 1; k <= n; k++) { const i = (state.at + k) % n; if (!mine(state.pairs[i]).pick) return go(i); }
});
fetch("/data").then(r => r.json()).then(data => {
  Object.assign(state, data);
  let at = 0;
  try { at = Number(localStorage.getItem("accent-pairs-at")) || 0; } catch (e) {}
  state.at = Math.min(at, state.pairs.length - 1);
  render();
});
</script>
</body>
</html>
"""


def serve(args: argparse.Namespace) -> None:
    if not (PAIRS / "key.json").exists():
        sys.exit("no out/pairs/key.json: run `pairs.py blind` first")
    print(f"http://{args.host}:{args.port}/")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


# ── report ──────────────────────────────────────────────────────────────────


def report(args: argparse.Namespace) -> None:
    key = run._read(PAIRS / "key.json", {})
    labels = run._read(PAIRS / "labels.json", {})
    heard = {}
    for path in (run.RESULTS / "transcripts.jsonl", TRANSCRIPTS):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                heard[row["key"]] = row
    rows = []
    for pair_id, pair in key.items():
        label = labels.get(pair_id) or {}
        target = next(letter for letter, take in pair["letters"].items() if take == pair["target"])
        pick = label.get("pick")
        rows.append({"pair": pair_id, **{k: pair[k] for k in ("language", "item", "source", "text", "audible", "target", "other")},
                     "pick": pick, "answer": None if pick is None else
                     "target" if pick == target else "other" if pick in ("A", "B") else pick,
                     "flags": {pair["letters"][letter]: flags for letter, flags in (label.get("flags") or {}).items() if flags},
                     "note": label.get("note") or "",
                     "whisper": {take: {k: heard.get(take, {}).get(k) for k in ("twice", "instruction", "different", "text")}
                                 for take in (pair["target"], pair["other"])}})
    answered = [row for row in rows if row["answer"]]
    question = {"es": "Argentine", "en": "British"}
    lines = ["# Expressive voice, round 2: does a tag move ElevenLabs' accent?", "",
             f"Unblinded by `pairs.py report`: {len(answered)} of {len(rows)} pairs answered. Each pair is one "
             "text read under two accents; the owner said which sounds Argentine (Spanish) or British (English), "
             "or that they sound the same, or could not tell. Gemini's pairs are the calibration: they show "
             "whether the contrast can be heard in these texts at all.", ""]
    for language in ("es", "en"):
        mine = [row for row in answered if row["language"] == language]
        if not mine:
            continue
        lines += [f"## {'Spanish: Argentina against Spain' if language == 'es' else 'English: British against American'}", "",
                  f"| Take | Pairs | Picked the {question[language]} one | Picked the other | The same | Can't tell | Verdict |",
                  "|---|---|---|---|---|---|---|"]
        sources = sorted({row["source"] for row in mine}, key=lambda s: (s == "gemini", s))
        calibrated = sum(1 for row in mine if row["source"] == "gemini" and row["answer"] == "target") >= THRESHOLD[language]
        for source in sources:
            here = [row for row in mine if row["source"] == source]
            hits = sum(1 for row in here if row["answer"] == "target")
            if source == "gemini":
                verdict = "audible" if calibrated else "**contrast not heard: no verdict on ElevenLabs**"
            elif not calibrated:
                verdict = "–"
            else:
                verdict = "**moves the accent**" if hits >= THRESHOLD[language] else "does not move it"
            lines.append(f"| {source} | {len(here)} | {hits} | {sum(1 for r in here if r['answer'] == 'other')} "
                         f"| {sum(1 for r in here if r['answer'] == 'same')} | {sum(1 for r in here if r['answer'] == 'unsure')} | {verdict} |")
        lines += ["", f"A tag moves the accent when the {question[language]} take is picked in at least "
                  f"{THRESHOLD[language]} of its pairs and Gemini's pairs reach the same.", ""]
        if language == "es":
            lines += ["By whether the text holds «ll» or «y» before a vowel:", "",
                      "| Take | With ll/y: picked Argentine | Without: picked Argentine |", "|---|---|---|"]
            for source in sources:
                here = [row for row in mine if row["source"] == source]
                yes, no = [r for r in here if r["audible"]], [r for r in here if not r["audible"]]
                lines.append(f"| {source} | {sum(r['answer'] == 'target' for r in yes)}/{len(yes)} "
                             f"| {sum(r['answer'] == 'target' for r in no)}/{len(no)} |")
            lines.append("")
    lines += ["## Every pair", "", "| Pair | Take | Text | Answer | Flags and note |", "|---|---|---|---|---|"]
    for row in sorted(rows, key=lambda r: (r["language"], r["item"], r["source"])):
        extra = [f"{take}: {', '.join(flags)}" for take, flags in row["flags"].items()]
        extra += [f"“{row['note'].strip()}”"] if row["note"].strip() else []
        lines.append(f"| {row['pair']} | {row['source']} | {row['text'][:50]} | {row['answer'] or '–'} | {'; '.join(extra)} |")
    caught = [(take, w) for row in rows for take, w in row["whisper"].items() if w.get("twice") or w.get("instruction") or w.get("different")]
    lines += ["", "## Whisper on the pairs' takes", "",
              *([f"- `{take}`: “{w['text']}”" for take, w in dict(caught).items()] or ["Nothing said twice, read aloud or different."]), ""]
    if not labels:
        print("\n".join(lines))
        print("\nNo labels yet: nothing written. Listen on the page first.")
        return
    (run.RESULTS / "pairs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    run._write(run.RESULTS / "pairs-summary.json", rows)
    shutil.copy(PAIRS / "labels.json", run.RESULTS / "pairs-labels.json")
    shutil.copy(PAIRS / "key.json", run.RESULTS / "pairs-key.json")
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bill").set_defaults(run=bill)
    commands.add_parser("record").set_defaults(run=record)
    commands.add_parser("blind").set_defaults(run=blind)
    found = commands.add_parser("serve")
    found.add_argument("--host", default="127.0.0.1", help="the laptop's Tailscale IP to reach it from a tablet")
    found.add_argument("--port", type=int, default=8768)
    found.set_defaults(run=serve)
    commands.add_parser("report").set_defaults(run=report)
    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
