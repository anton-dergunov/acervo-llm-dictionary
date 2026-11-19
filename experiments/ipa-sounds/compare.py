"""The blind listening page for the processed recordings: which version of each sounds best?

    .venv/bin/python experiments/ipa-sounds/compare.py --host "$(tailscale ip -4)" --port 8773

Standard library and PyYAML (the project's interpreter). For every card with a pick, the page plays
the Commons original as a labelled reference, then the three versions process.py built (as
recorded, gated, DeepFilterNet; all trimmed and set to the same loudness) under letters shuffled
per card, so nothing on screen or in an address says which is which. The noisiest recordings come
first. Each tap goes to results/processing-labels.json:

    {"ʂ": {"best": "B", "note": ""}, ...}

`best` is a letter or "same" (no audible difference). `process.py report` unblinds them. The
versions are served with `Range`, which Safari on an iPad asks for before it will play.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import review

HERE = Path(__file__).resolve().parent
COMPARE = HERE / "out" / "compare"
LABELS = HERE / "results" / "processing-labels.json"
FONT = HERE.parents[1] / "web" / "src" / "fonts" / "acervo-ipa.woff2"

_lock = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def items() -> list[dict[str, Any]]:
    key = _read(COMPARE / "key.json", {})
    stats = _read(COMPARE / "stats.json", {})
    cards = {card["id"]: card for card in review.cards()}
    found = []
    for row_id, entry in key.items():
        card = cards[row_id]
        picked = next(c for c in card["candidates"] if c["file"] == stats[row_id]["file"])
        found.append({"id": row_id, "n": entry["n"], "shown": card["shown"], "title": card["title"],
                      "section": card["section"], "file": picked["file"], "reference": picked["mp3"],
                      "letters": sorted(entry["letters"]), "snr": stats[row_id]["snr"]})
    return sorted(found, key=lambda item: item["snr"])


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
            body = {"items": items(), "labels": _read(LABELS, {})}
            return self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json")
        if self.path == "/ipa.woff2":
            return self._send(200, FONT.read_bytes(), "font/woff2")
        found = re.fullmatch(r"/a/(\d+)/([ABC])", self.path)
        if found:
            return self._audio(COMPARE / found[1] / f"{found[2]}.wav")
        self._send(404, b"not found", "text/plain")

    def _audio(self, path: Path) -> None:
        if not path.exists():
            return self._send(404, b"no such version", "text/plain")
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
        if self.path != "/label":
            return self._send(404, b"not found", "text/plain")
        try:
            change = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            row_id, field, value = change["id"], change["field"], change.get("value")
        except (ValueError, KeyError):
            return self._send(400, b"bad request", "text/plain")
        if row_id not in _read(COMPARE / "key.json", {}):
            return self._send(400, b"no such card", "text/plain")
        if field == "best" and value not in (None, "A", "B", "C", "same") or field not in ("best", "note"):
            return self._send(400, b"bad field or value", "text/plain")
        with _lock:
            labels = _read(LABELS, {})
            mine = labels.setdefault(row_id, {})
            if value in (None, ""):
                mine.pop(field, None)
            else:
                mine[field] = str(value)[:2000]
            if not mine:
                labels.pop(row_id)
            temporary = LABELS.with_suffix(".tmp")
            temporary.write_text(json.dumps(labels, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            temporary.replace(LABELS)
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPA Sounds Cleanup</title>
<style>
@font-face { font-family: "Acervo IPA"; src: url("/ipa.woff2") format("woff2"); font-display: swap; }
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
header .count { flex: 1; color: var(--muted); font-variant-numeric: tabular-nums; min-width: 160px; }
main { max-width: 760px; margin: 0 auto; padding: 16px; }
button { font: inherit; color: inherit; background: var(--chip); border: 1px solid var(--line);
  border-radius: 10px; min-height: 44px; min-width: 44px; padding: 0 14px; cursor: pointer; }
button.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
button:disabled { opacity: .4; cursor: default; }
.head { display: flex; align-items: center; gap: 20px; margin: 6px 0 14px; }
.symbol { font-family: "Acervo IPA", system-ui, sans-serif; font-size: 64px; line-height: 1.1; min-width: 92px;
  text-align: center; background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 6px 14px; }
.title { font-size: 21px; font-weight: 600; }
.sub { color: var(--muted); font-size: 14px; overflow-wrap: anywhere; }
h2 { font-size: 15px; color: var(--muted); font-weight: 600; margin: 20px 0 8px; text-transform: uppercase; letter-spacing: .06em; }
.ref, .versions { display: flex; gap: 10px; flex-wrap: wrap; }
.ref button { min-width: 200px; }
.version { flex: 1 1 0; min-width: 150px; background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 12px; display: flex; flex-direction: column; gap: 8px; align-items: stretch; }
.version.chosen { border-color: var(--good); box-shadow: 0 0 0 1px var(--good) inset; }
.letter { font-size: 26px; font-weight: 700; text-align: center; }
.choices { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
.choices button { flex: 1 1 0; }
textarea { width: 100%; font: inherit; font-size: 15px; color: var(--ink); background: var(--card);
  border: 1px solid var(--line); border-radius: 10px; padding: 8px; min-height: 44px; resize: vertical; margin-top: 14px; }
.legend { color: var(--muted); font-size: 14px; margin: 0; }
.nav { display: flex; gap: 10px; margin: 24px 0 40px; }
.nav button { flex: 1; }
.error { color: var(--warn); }
</style>
</head>
<body>
<header>
  <span class="count" id="count">Loading…</span>
  <span class="error" id="error"></span>
  <button id="todo">Next to rate</button>
</header>
<main id="main"></main>
<script>
const state = { items: [], labels: {}, at: 0 };
const audio = new Audio();
let playing = null, noteTimer = null;
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else if (v !== false && v != null) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) node.append(kid);
  return node;
};
const label = item => state.labels[item.id] || {};
const typing = () => document.activeElement && document.activeElement.tagName === "TEXTAREA";
async function save(item, field, value) {
  const mine = state.labels[item.id] = { ...label(item) };
  if (value == null || value === "") delete mine[field]; else mine[field] = value;
  try {
    const answer = await fetch("/label", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id, field, value }) });
    if (!answer.ok) throw new Error(await answer.text());
    document.getElementById("error").textContent = "";
  } catch (e) { document.getElementById("error").textContent = "Not saved: " + (e.message || "is the laptop awake?"); }
  if (field !== "note" || !typing()) render();
}
function play(src) {
  if (playing === src && !audio.paused) { audio.pause(); playing = null; render(); return; }
  audio.src = src; playing = src;
  audio.play().catch(() => { document.getElementById("error").textContent = "Could not play that file."; playing = null; render(); });
  render();
}
audio.addEventListener("ended", () => { playing = null; if (!typing()) render(); });
const playButton = (src, text) => $("button", { class: playing === src ? "on" : "", onclick: () => play(src) }, playing === src ? "■ Stop" : text);
function render() {
  const total = state.items.length, rated = state.items.filter(i => label(i).best).length;
  document.getElementById("count").textContent = `${rated} of ${total} rated · card ${state.at + 1}`;
  const item = state.items[state.at], main = document.getElementById("main");
  if (!item) { main.textContent = "Nothing to compare: run process.py build first."; return; }
  const mine = label(item), scroll = window.scrollY;
  main.replaceChildren(...[
    $("div", { class: "head" }, $("div", { class: "symbol" }, item.shown),
      $("div", {}, $("div", { class: "title" }, item.title), $("div", { class: "sub" }, `${item.section} · ${item.file}`))),
    $("h2", {}, "Reference"),
    $("div", { class: "ref" }, playButton(item.reference, "▶ Commons original")),
    $("h2", {}, "Versions"),
    $("p", { class: "legend" }, "Same length and loudness; only the noise handling differs. Which sounds best?"),
    $("div", { class: "versions" }, item.letters.map(letter => {
      const src = `/a/${item.n}/${letter}`;
      return $("div", { class: "version" + (mine.best === letter ? " chosen" : "") },
        $("div", { class: "letter" }, letter), playButton(src, "▶ Play"),
        $("button", { class: mine.best === letter ? "on" : "", onclick: () => save(item, "best", mine.best === letter ? null : letter) },
          mine.best === letter ? "Best" : "Pick"));
    })),
    $("div", { class: "choices" }, $("button", { class: mine.best === "same" ? "on" : "",
      onclick: () => save(item, "best", mine.best === "same" ? null : "same") }, "All sound the same")),
    (() => {
      const note = $("textarea", { placeholder: "Note (optional): e.g. B cuts the hiss off the sound itself", rows: 2 });
      note.value = mine.note || "";
      note.addEventListener("input", () => { clearTimeout(noteTimer); noteTimer = setTimeout(() => save(item, "note", note.value), 700); });
      return note;
    })(),
    $("div", { class: "nav" },
      $("button", { disabled: state.at === 0, onclick: () => go(state.at - 1) }, "← Previous"),
      $("button", { disabled: state.at === total - 1, onclick: () => go(state.at + 1) }, "Next →")),
  ].flat().filter(node => node != null));
  window.scrollTo(0, scroll);
}
function go(n) {
  audio.pause(); playing = null; state.at = n;
  try { localStorage.setItem("ipa-cleanup-at", String(n)); } catch (e) {}
  render(); window.scrollTo(0, 0);
}
document.getElementById("todo").addEventListener("click", () => {
  const n = state.items.length;
  for (let k = 1; k <= n; k++) { const i = (state.at + k) % n; if (!label(state.items[i]).best) return go(i); }
});
fetch("/data").then(r => r.json()).then(data => {
  Object.assign(state, data);
  let at = 0;
  try { at = Number(localStorage.getItem("ipa-cleanup-at")) || 0; } catch (e) {}
  state.at = Math.min(at, Math.max(0, state.items.length - 1));
  render();
});
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the blind page comparing the processed recordings.")
    parser.add_argument("--host", default="127.0.0.1", help="the laptop's Tailscale IP to reach it from a tablet")
    parser.add_argument("--port", type=int, default=8773)
    args = parser.parse_args()
    if not (COMPARE / "key.json").exists():
        raise SystemExit("no out/compare/key.json: run process.py build first")
    print(f"http://{args.host}:{args.port}/")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
