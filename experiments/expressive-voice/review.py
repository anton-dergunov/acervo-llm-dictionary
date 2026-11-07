"""The blind listening page: each item's takes side by side under letters, saved as you tap.

    .venv/bin/python experiments/expressive-voice/review.py --host "$(tailscale ip -4)" --port 8767

Standard library only. The takes are the loudness-matched copies `run.py blind` made, and the
letter → take key stays in `out/key.json`: the page is never told which letter is which, and a
take's address is `/a/<item>/<letter>`, so nothing on screen or in the address bar gives a voice
away. Labels go to `out/labels.json` on every tap, so closing the tab loses nothing. Audio is
served with `Range`, which Safari on an iPad asks for before it will play. `run.py report`
unblinds the labels.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXPRESSIVE_VOICE_OUT") or HERE / "out")
ORDER = ("feeling", "story", "accent", "words")
SCALES = ("right", "feeling", "accent")
FLAGS = ("read aloud", "said twice", "other words")
LANGUAGES = {"es-AR": "Spanish · Argentina", "es-ES": "Spanish · Spain", "en-GB": "English · UK",
             "ru": "Russian", "es": "Spanish", "en": "English"}

_lock = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def items() -> list[dict[str, Any]]:
    """What the page shows: the text and what was asked, and the letters — never the voices."""
    key = _read(OUT / "key.json", {})
    found = []
    for item in json.loads((HERE / "set.json").read_text(encoding="utf-8"))["items"]:
        if item["id"] not in key:
            continue
        accented = "-" in item["language"]
        if item["group"] == "accent":
            asked = "No feeling asked: the accent alone."
        elif item["group"] == "words":
            asked = "A word or phrase on its own, no feeling."
        elif item["group"] == "story":
            asked = f"Story passage, read as: {item['note']}"
        else:
            asked = f"Feeling: {item['note']}"
        found.append({"id": item["id"], "group": item["group"], "text": item["text"], "asked": asked,
                      "language": LANGUAGES.get(item["language"], item["language"]),
                      "scales": ["right", *(["feeling"] if item["note"] else []), *(["accent"] if accented else [])],
                      "letters": sorted(key[item["id"]])})
    return sorted(found, key=lambda item: (ORDER.index(item["group"]), item["id"]))


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
            body = {"items": items(), "labels": _read(OUT / "labels.json", {}), "flags": FLAGS}
            return self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json")
        found = re.fullmatch(r"/a/([a-z]\d\d)/([A-F])", self.path)
        if found:
            return self._audio(OUT / "blind" / found[1] / f"{found[2]}.wav")
        self._send(404, b"not found", "text/plain")

    def _audio(self, path: Path) -> None:
        if not path.exists():
            return self._send(404, b"no such take", "text/plain")
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
            item, letter, field, value = change["item"], change.get("letter"), change["field"], change.get("value")
        except (ValueError, KeyError):
            return self._send(400, b"bad request", "text/plain")
        key = _read(OUT / "key.json", {})
        if item not in key or (field != "best" and letter not in key[item]):
            return self._send(400, b"no such take", "text/plain")
        with _lock:
            labels = _read(OUT / "labels.json", {})
            mine = labels.setdefault(item, {})
            if field == "best":
                if value in key[item]:
                    mine["_best"] = value
                else:
                    mine.pop("_best", None)
            elif field in SCALES:
                take = mine.setdefault(letter, {})
                if value in (1, 2, 3):
                    take[field] = value
                else:
                    take.pop(field, None)
            elif field == "flags":
                mine.setdefault(letter, {})["flags"] = [flag for flag in FLAGS if flag in (value or [])]
            elif field == "note":
                mine.setdefault(letter, {})["note"] = str(value or "")[:1000]
            else:
                return self._send(400, b"no such field", "text/plain")
            _write(OUT / "labels.json", labels)
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Listening</title>
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
  border-radius: 10px; min-height: 40px; min-width: 40px; padding: 0 12px; cursor: pointer; }
button.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
button:disabled { opacity: .4; }
.group { text-transform: uppercase; letter-spacing: .08em; font-size: 13px; color: var(--muted); margin: 4px 0; }
.text { font-size: 24px; line-height: 1.35; margin: 4px 0 6px; }
.meta { color: var(--muted); margin-bottom: 14px; }
.take { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px; margin: 12px 0; }
.take.done { border-color: var(--good); }
.top { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.letter { font-weight: 700; font-size: 22px; width: 28px; }
.play { min-width: 92px; }
.row { display: flex; align-items: center; gap: 8px; margin: 6px 0; flex-wrap: wrap; }
.row .name { width: 72px; color: var(--muted); font-size: 15px; }
.row button { min-width: 0; flex: 1 1 0; max-width: 150px; font-size: 15px; padding: 0 6px; }
.flags button { flex: 0 1 auto; max-width: none; }
.flags button.on { background: var(--warn); border-color: var(--warn); color: var(--accent-ink); }
textarea { width: 100%; font: inherit; font-size: 15px; color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 10px; padding: 8px; min-height: 40px; resize: vertical; }
.best { margin-top: 18px; }
.nav { display: flex; gap: 10px; justify-content: space-between; margin: 20px 0 40px; }
.nav button { flex: 1; }
.error { color: var(--warn); }
.legend { color: var(--muted); font-size: 14px; margin: 0 0 6px; }
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
const state = { items: [], labels: {}, flags: [], at: 0 };
const audio = new Audio();
let playing = null;
const SCALE = {
  right: ["Right", ["wrong", "a slip", "right"]],
  feeling: ["Feeling", ["flat / wrong", "some", "carries it"]],
  accent: ["Accent", ["not it", "partly", "clearly"]],
};
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else if (v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) node.append(kid);
  return node;
};
const take = (item, letter) => ((state.labels[item.id] || {})[letter]) || {};
const complete = item => item.letters.every(l => item.scales.every(s => take(item, l)[s]));
async function save(item, letter, field, value) {
  const mine = state.labels[item.id] = state.labels[item.id] || {};
  if (field === "best") { if (value) mine._best = value; else delete mine._best; }
  else { const t = mine[letter] = mine[letter] || {}; if (value === null) delete t[field]; else t[field] = value; }
  try {
    const answer = await fetch("/rate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item: item.id, letter, field, value }) });
    if (!answer.ok) throw new Error(answer.status);
    document.getElementById("error").textContent = "";
  } catch (e) { document.getElementById("error").textContent = "Not saved — is the laptop awake?"; }
  render();
}
function play(item, letter, button) {
  const src = `/a/${item.id}/${letter}`;
  if (playing === src && !audio.paused) { audio.pause(); playing = null; render(); return; }
  audio.src = src; playing = src; audio.play(); render();
}
audio.addEventListener("ended", () => { playing = null; render(); });
let noteTimer = null;
function render() {
  const done = state.items.filter(complete).length;
  document.getElementById("count").textContent = `${done} of ${state.items.length} rated · item ${state.at + 1}`;
  const item = state.items[state.at];
  const main = document.getElementById("main");
  if (!item) { main.textContent = "Nothing to rate."; return; }
  const scroll = window.scrollY;
  main.replaceChildren(...[
    $("div", { class: "group" }, `${item.group} · ${item.language}`),
    $("div", { class: "text", lang: item.language.startsWith("Spanish") ? "es" : item.language.startsWith("Russian") ? "ru" : "en" }, item.text),
    $("div", { class: "meta" }, item.asked),
    $("p", { class: "legend" }, "Right: the words, the language and nothing extra. Accent: the one named above."),
    item.letters.map(letter => {
      const t = take(item, letter), src = `/a/${item.id}/${letter}`;
      const rows = item.scales.map(scale => $("div", { class: "row" }, $("span", { class: "name" }, SCALE[scale][0]),
        SCALE[scale][1].map((word, n) => $("button", { class: t[scale] === n + 1 ? "on" : "",
          onclick: () => save(item, letter, scale, t[scale] === n + 1 ? null : n + 1) }, word))));
      const flags = $("div", { class: "row flags" }, state.flags.map(flag => {
        const on = (t.flags || []).includes(flag);
        return $("button", { class: on ? "on" : "", onclick: () => save(item, letter, "flags",
          on ? (t.flags || []).filter(f => f !== flag) : [...(t.flags || []), flag]) }, flag);
      }));
      const note = $("textarea", { placeholder: "Note (optional)", rows: 1 });
      note.value = t.note || "";
      note.addEventListener("input", () => { clearTimeout(noteTimer); noteTimer = setTimeout(() => save(item, letter, "note", note.value), 700); });
      return $("div", { class: "take" + (item.scales.every(s => t[s]) ? " done" : "") },
        $("div", { class: "top" }, $("span", { class: "letter" }, letter),
          $("button", { class: "play" + (playing === src ? " on" : ""), onclick: e => play(item, letter, e.target) },
            playing === src ? "■ Stop" : "▶ Play")),
        rows, flags, note);
    }),
    $("div", { class: "row best" }, $("span", { class: "name" }, "Best"),
      item.letters.map(letter => $("button", { class: (state.labels[item.id] || {})._best === letter ? "on" : "",
        onclick: () => save(item, null, "best", (state.labels[item.id] || {})._best === letter ? null : letter) }, letter))),
    $("div", { class: "nav" },
      $("button", { disabled: state.at === 0, onclick: () => go(state.at - 1) }, "← Previous"),
      $("button", { disabled: state.at === state.items.length - 1, onclick: () => go(state.at + 1) }, "Next →")),
  ].flat());
  window.scrollTo(0, scroll);
}
function go(n) {
  audio.pause(); playing = null; state.at = n;
  try { localStorage.setItem("expressive-voice-at", String(n)); } catch (e) {}
  render(); window.scrollTo(0, 0);
}
document.getElementById("unrated").addEventListener("click", () => {
  const n = state.items.length;
  for (let k = 1; k <= n; k++) { const i = (state.at + k) % n; if (!complete(state.items[i])) return go(i); }
});
fetch("/data").then(r => r.json()).then(data => {
  Object.assign(state, data);
  let at = 0;
  try { at = Number(localStorage.getItem("expressive-voice-at")) || 0; } catch (e) {}
  state.at = Math.min(at, state.items.length - 1);
  render();
});
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the blind listening page.")
    parser.add_argument("--host", default="127.0.0.1", help="the laptop's Tailscale IP to reach it from a tablet")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if not (OUT / "key.json").exists():
        raise SystemExit("no out/key.json: run `run.py blind` first")
    print(f"http://{args.host}:{args.port}/")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
