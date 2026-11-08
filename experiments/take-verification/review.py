"""The listening page: does each recording say what it was asked to? Saved as you tap.

    experiments/take-verification/.venv/bin/python experiments/take-verification/review.py \
        --host "$(tailscale ip -4)" --port 8769

Standard library only, besides ffmpeg once per card. The cards are `sweep.py listen`'s, in its
shuffled order; why a card is there — which rule raised it, or that it is a control the rule passed
— never reaches the page. A clip's address is its card number. Each one is converted to a
loudness-matched WAV under `out/listen/` first, because Safari on an iPad will not play every Ogg
Opus, and served with `Range`, which it asks for before it plays. Whisper's transcripts are behind a
button, for after listening. Labels go to `out/labels.json` on every tap.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results"
VERDICTS = ("right", "wrong", "unsure")
FAULTS = ("a sound changed", "a word changed", "words added", "words missing", "said twice",
          "instruction read out", "garbled")
LANGUAGES = {"es-AR": "Spanish · Argentina", "es": "Spanish", "en-GB": "English · UK", "en": "English",
             "ru": "Russian", "zh-Hans": "Chinese"}
KINDS = {"take": "Loop line", "word": "Word pronunciation", "story": "Story passage"}

_lock = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def heard() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for path in sorted(RESULTS.glob("signals-*.jsonl")):
        model = path.stem.split("-", 1)[1]
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                found.setdefault(row["key"], {})[model] = row["heard"]
    return found


def loops() -> dict[tuple[str, int], list[str]]:
    """Where a loop line is heard: the loop's date and the moment, by its text and take."""
    found: dict[tuple[str, int], list[str]] = {}
    for cue in _read(OUT / "db/loop_cues.json", []):
        minutes, seconds = divmod(int(cue["start_seconds"]), 60)
        found.setdefault((cue["text"], int(cue["take"])), []).append(
            f"the loop made {cue['loop_created'][:10]}, at {minutes}:{seconds:02d}")
    return found


def cards() -> list[dict[str, Any]]:
    listed = _read(OUT / "listen.json", [])
    transcripts, used = heard(), loops()
    manifest = {}
    for line in (OUT / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        manifest[f"{row['kind']}/{row['id']}"] = row
    shown = []
    for number, card in enumerate(listed):
        take = manifest[card["key"]].get("take", 0)
        shown.append({
            "n": number, "key": card["key"], "kind": KINDS[card["kind"]], "text": card["text"],
            "language": LANGUAGES.get(card["lang"], card["lang"]), "lang": card["lang"].split("-")[0],
            "direction": card["direction"], "heard": transcripts.get(card["key"], {}),
            "loops": used.get((card["text"], take), [])[:3] if card["kind"] == "take" else [],
        })
    return shown


def prepare() -> None:
    (OUT / "listen").mkdir(exist_ok=True)
    for number, card in enumerate(_read(OUT / "listen.json", [])):
        target = OUT / "listen" / f"{number:03d}.wav"
        if not target.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(OUT / card["path"]),
                            "-af", "loudnorm=I=-20:TP=-1.5:LRA=11", "-ar", "24000", "-ac", "1", str(target)],
                           check=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None:
        pass

    def _send(self, status: int, body: bytes, kind: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — the stdlib's name
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/data":
            body = {"cards": cards(), "labels": _read(OUT / "labels.json", {}), "verdicts": VERDICTS, "faults": FAULTS}
            return self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json")
        found = re.fullmatch(r"/a/(\d{3})", self.path)
        if found:
            return self._audio(OUT / "listen" / f"{found[1]}.wav")
        self._send(404, b"not found", "text/plain")

    def _audio(self, path: Path) -> None:
        if not path.exists():
            return self._send(404, b"no such clip", "text/plain")
        data = path.read_bytes()
        wanted = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if not wanted:
            return self._send(200, data, "audio/wav", {"Accept-Ranges": "bytes"})
        start = int(wanted[1]) if wanted[1] else max(0, len(data) - int(wanted[2] or 0))
        end = min(int(wanted[2]), len(data) - 1) if wanted[1] and wanted[2] else len(data) - 1
        if start >= len(data):
            return self._send(416, b"", "audio/wav", {"Content-Range": f"bytes */{len(data)}"})
        self._send(206, data[start:end + 1], "audio/wav",
                   {"Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{len(data)}"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/rate":
            return self._send(404, b"not found", "text/plain")
        try:
            change = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            key, field, value = change["key"], change["field"], change.get("value")
        except (ValueError, KeyError):
            return self._send(400, b"bad request", "text/plain")
        if key not in {card["key"] for card in _read(OUT / "listen.json", [])}:
            return self._send(400, b"no such clip", "text/plain")
        with _lock:
            labels = _read(OUT / "labels.json", {})
            mine = labels.setdefault(key, {})
            if field == "verdict":
                if value in VERDICTS:
                    mine["verdict"] = value
                else:
                    mine.pop("verdict", None)
            elif field == "faults":
                mine["faults"] = [fault for fault in FAULTS if fault in (value or [])]
            elif field == "note":
                mine["note"] = str(value or "")[:1000]
            else:
                return self._send(400, b"no such field", "text/plain")
            _write(OUT / "labels.json", labels)
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recording Check</title>
<style>
:root {
  --bg: #f4f2ee; --card: #ffffff; --ink: #1f2421; --muted: #66706a; --line: #dcd8d0;
  --accent: #116a5a; --accent-ink: #ffffff; --chip: #eef0ec; --warn: #a3412c; --good: #116a5a;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161917; --card: #202523; --ink: #e8ebe8; --muted: #9aa49e; --line: #343b38;
    --accent: #4fb49c; --accent-ink: #0d1412; --chip: #2a302d; --warn: #e48a72; --good: #4fb49c;
  }
}
:root[data-theme="dark"] {
  --bg: #161917; --card: #202523; --ink: #e8ebe8; --muted: #9aa49e; --line: #343b38;
  --accent: #4fb49c; --accent-ink: #0d1412; --chip: #2a302d; --warn: #e48a72; --good: #4fb49c;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 17px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--bg); border-bottom: 1px solid var(--line);
  padding: 10px 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
header .count { flex: 1; color: var(--muted); font-variant-numeric: tabular-nums; }
main { max-width: 760px; margin: 0 auto; padding: 16px; }
button { font: inherit; color: inherit; background: var(--chip); border: 1px solid var(--line);
  border-radius: 10px; min-height: 44px; min-width: 44px; padding: 0 14px; cursor: pointer; }
button.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
button:disabled { opacity: .4; }
.group { text-transform: uppercase; letter-spacing: .08em; font-size: 13px; color: var(--muted); margin: 4px 0; }
.text { font-size: 26px; line-height: 1.35; margin: 4px 0 6px; }
.meta { color: var(--muted); margin-bottom: 6px; }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; margin: 14px 0; }
.panel.done { border-color: var(--good); }
.play { min-width: 120px; font-size: 19px; }
.row { display: flex; align-items: center; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
.row.verdict button { flex: 1 1 0; }
.row.verdict button.on.wrong { background: var(--warn); border-color: var(--warn); }
.faults button { font-size: 15px; }
.faults button.on { background: var(--warn); border-color: var(--warn); color: var(--accent-ink); }
textarea { width: 100%; font: inherit; font-size: 15px; color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 10px; padding: 8px; min-height: 44px; resize: vertical; }
.heard { color: var(--muted); font-size: 15px; margin: 8px 0 0; }
.heard b { color: var(--ink); font-weight: 500; }
.nav { display: flex; gap: 10px; justify-content: space-between; margin: 20px 0 40px; }
.nav button { flex: 1; }
.error { color: var(--warn); }
.legend { color: var(--muted); font-size: 14px; margin: 0; }
</style>
</head>
<body>
<header>
  <span class="count" id="count">Loading…</span>
  <span class="error" id="error"></span>
  <button id="unrated">Next unrated</button>
</header>
<main id="main"></main>
<script>
const state = { cards: [], labels: {}, verdicts: [], faults: [], at: 0, reveal: false };
const audio = new Audio();
let playing = false;
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else if (v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) node.append(kid);
  return node;
};
const label = card => state.labels[card.key] || {};
async function save(card, field, value) {
  const mine = state.labels[card.key] = state.labels[card.key] || {};
  if (value === null) delete mine[field]; else mine[field] = value;
  try {
    const answer = await fetch("/rate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: card.key, field, value }) });
    if (!answer.ok) throw new Error(answer.status);
    document.getElementById("error").textContent = "";
  } catch (e) { document.getElementById("error").textContent = "Not saved — is the laptop awake?"; }
  if (field !== "note" || !typing()) render();
}
function play(card) {
  if (playing && !audio.paused) { audio.pause(); playing = false; render(); return; }
  audio.src = `/a/${String(card.n).padStart(3, "0")}`; playing = true; audio.play(); render();
}
audio.addEventListener("ended", () => { playing = false; if (!typing()) render(); });
let noteTimer = null;
// Redraws nobody tapped for — a note saving, a take ending — wait while a note is being typed:
// rebuilding the card replaces the focused field, and an iPad closes its keyboard the moment the
// focused field leaves the page. A tap always redraws.
const typing = () => document.activeElement && document.activeElement.tagName === "TEXTAREA";
function render() {
  const done = state.cards.filter(c => label(c).verdict).length;
  document.getElementById("count").textContent = `${done} of ${state.cards.length} judged · clip ${state.at + 1}`;
  const card = state.cards[state.at];
  const main = document.getElementById("main");
  if (!card) { main.textContent = "Nothing to judge."; return; }
  const mine = label(card);
  const note = $("textarea", { placeholder: "What did it say instead? (optional)", rows: 1 });
  note.value = mine.note || "";
  note.addEventListener("input", () => { clearTimeout(noteTimer); noteTimer = setTimeout(() => save(card, "note", note.value), 700); });
  const heard = Object.entries(card.heard);
  main.replaceChildren(...[
    $("div", { class: "group" }, `${card.kind} · ${card.language}`),
    $("div", { class: "text", lang: card.lang }, card.text),
    card.direction ? $("div", { class: "meta" }, `Asked to sound: ${card.direction}`) : "",
    card.loops.length ? $("div", { class: "meta" }, `Heard in ${card.loops.join("; ")}`) : "",
    $("div", { class: "panel" + (mine.verdict ? " done" : "") },
      $("div", { class: "row" }, $("button", { class: "play" + (playing ? " on" : ""), onclick: () => play(card) },
        playing ? "■ Stop" : "▶ Play")),
      $("p", { class: "legend" }, "Wrong: a sound or a word of the text changed, or something added that is not a feeling. An exclamation around the word («Oh,», «¡Aah!») is right, and so is the accent."),
      $("div", { class: "row verdict" }, state.verdicts.map(v => $("button", {
        class: (mine.verdict === v ? "on " : "") + v, onclick: () => save(card, "verdict", mine.verdict === v ? null : v) }, v))),
      mine.verdict === "wrong" || mine.verdict === "unsure" ? $("div", { class: "row faults" }, state.faults.map(f => {
        const on = (mine.faults || []).includes(f);
        return $("button", { class: on ? "on" : "", onclick: () => save(card, "faults",
          on ? (mine.faults || []).filter(x => x !== f) : [...(mine.faults || []), f]) }, f);
      })) : "",
      note,
      $("div", { class: "row" }, $("button", { onclick: () => { state.reveal = !state.reveal; render(); } },
        state.reveal ? "Hide what Whisper heard" : "What Whisper heard")),
      state.reveal ? heard.map(([model, text]) => $("div", { class: "heard" }, `${model}: `, $("b", {}, text || "(nothing)"))) : ""),
    $("div", { class: "nav" },
      $("button", { disabled: state.at === 0, onclick: () => go(state.at - 1) }, "← Previous"),
      $("button", { disabled: state.at === state.cards.length - 1, onclick: () => go(state.at + 1) }, "Next →")),
  ].flat());
}
function go(n) {
  audio.pause(); playing = false; state.reveal = false; state.at = n;
  try { localStorage.setItem("take-verification-at", String(n)); } catch (e) {}
  render(); window.scrollTo(0, 0);
}
document.getElementById("unrated").addEventListener("click", () => {
  const n = state.cards.length;
  for (let k = 1; k <= n; k++) { const i = (state.at + k) % n; if (!label(state.cards[i]).verdict) return go(i); }
});
fetch("/data").then(r => r.json()).then(data => {
  Object.assign(state, data);
  let at = 0;
  try { at = Number(localStorage.getItem("take-verification-at")) || 0; } catch (e) {}
  state.at = Math.min(at, state.cards.length - 1);
  render();
});
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the listening page.")
    parser.add_argument("--host", default="127.0.0.1", help="the laptop's Tailscale IP to reach it from a tablet")
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    if not (OUT / "listen.json").exists():
        raise SystemExit("no out/listen.json: run `sweep.py listen` first")
    prepare()
    print(f"http://{args.host}:{args.port}/", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
