"""The review page: one card per symbol, to pick its recording and judge its wording, saved as you tap.

    .venv/bin/python experiments/ipa-sounds/review.py --host "$(tailscale ip -4)" --port 8771

Standard library and PyYAML only. Each card shows a row of symbols.yaml as the app would (the symbol
in the app's IPA font, which joins tone letters into one line), then every candidate recording from
results/candidates.json with its licence and author. Recordings play straight from Commons' MP3
copies on upload.wikimedia.org (an iPad will not play Ogg); nothing is served from the laptop but the
page, its data and the font. A file under a licence the app cannot ship is shown but cannot be
picked. Every tap goes to results/labels.json, keyed by the row's id:

    {"ʂ": {"pick": "Voiceless retroflex sibilant.ogg", "text": "fine", "note": ""}, ...}

`pick` is a file name or "none" (nothing fits); `text` is fine, unclear or wrong.
"""

from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
FONT = HERE.parents[1] / "web" / "src" / "fonts" / "acervo-ipa.woff2"
VERDICTS = ("fine", "unclear", "wrong")

_lock = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)


def cards() -> list[dict[str, Any]]:
    """Every row of the table as the page shows it; ids match candidates.py's."""
    table = yaml.safe_load((HERE / "symbols.yaml").read_text(encoding="utf-8"))
    found = _read(RESULTS / "candidates.json", {"rows": {}})["rows"]
    out: list[dict[str, Any]] = []

    def add(section: str, row_id: str, shown: str, title: str, lines: list[tuple[str, str | None]]) -> None:
        out.append({"id": row_id, "section": section, "shown": shown, "title": title,
                    "lines": [[k, v] for k, v in lines if v], "candidates": found.get(row_id, [])})

    for section in ("consonants", "affricates", "vowels"):
        for e in table[section]:
            aliases = ", ".join(e.get("aliases", []))
            add(section, e["symbol"], e["symbol"], e["name"],
                [("How", e["how"]), ("Like", e.get("like")), ("Heard in", e.get("heard")),
                 ("Also written", aliases)])
    for e in table["combinations"]:
        add("letters with a mark", e["symbol"], e["symbol"], e["name"],
            [("How", e["how"]), ("Like", e.get("like")), ("Heard in", e.get("heard"))])
    for e in table["diacritics"]:
        add("diacritics", e["example"], e["example"], e["name"], [("How", e["how"])])
    for e in table["suprasegmentals"]:
        shown = e.get("example") or e["symbol"]
        add("stress, length, phrasing", f"mark {e['symbol']}", shown, e["name"], [("How", e["how"])])
    for c in table["tones"]["contours"]:
        add("tones", f"tone {c['letters']}", c["letters"], c["name"],
            [("How", c["how"]), ("Mandarin", c.get("mandarin"))])
    for m in table["tones"]["marks"]:
        add("tones", f"tone mark {m['example']}", m["example"], f"{m['name']} tone (mark)", [])
    for part in ("initials", "finals"):
        for p in table["pinyin"][part]:
            add(f"pinyin {part}", f"pinyin {p['letters']}", p["letters"], f"Pinyin {p['letters']} = /{p['ipa']}/",
                [("How", p["how"]), ("Example", p["example"])])
    for t in table["pinyin"]["tones"]:
        add("pinyin tones", f"pinyin tone {t['number']}", t["mark"], f"Pinyin tone {t['number']}",
            [("How", t["how"]), ("IPA", t["ipa"] or "none")])
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None:
        pass

    def _send(self, status: int, body: bytes, kind: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — the stdlib's name
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/data":
            body = {"cards": cards(), "labels": _read(RESULTS / "labels.json", {}), "verdicts": VERDICTS}
            return self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json")
        if self.path == "/ipa.woff2":
            return self._send(200, FONT.read_bytes(), "font/woff2", "max-age=86400")
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/label":
            return self._send(404, b"not found", "text/plain")
        try:
            change = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            row_id, field, value = change["id"], change["field"], change.get("value")
        except (ValueError, KeyError):
            return self._send(400, b"bad request", "text/plain")
        known = {card["id"]: card for card in cards()}
        if row_id not in known:
            return self._send(400, b"no such row", "text/plain")
        free = {c["file"] for c in known[row_id]["candidates"] if c["free"]}
        if field == "pick" and value not in (None, "none", *free):
            return self._send(400, b"not a freely licensed candidate", "text/plain")
        if field == "text" and value not in (None, *VERDICTS):
            return self._send(400, b"no such verdict", "text/plain")
        if field not in ("pick", "text", "note"):
            return self._send(400, b"no such field", "text/plain")
        with _lock:
            labels = _read(RESULTS / "labels.json", {})
            mine = labels.setdefault(row_id, {})
            if value in (None, ""):
                mine.pop(field, None)
            else:
                mine[field] = str(value)[:2000]
            if not mine:
                labels.pop(row_id)
            _write(RESULTS / "labels.json", labels)
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPA Sounds Review</title>
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
button, select { font: inherit; color: inherit; background: var(--chip); border: 1px solid var(--line);
  border-radius: 10px; min-height: 40px; min-width: 40px; padding: 0 12px; cursor: pointer; }
button.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
button:disabled { opacity: .4; cursor: default; }
.section { text-transform: uppercase; letter-spacing: .08em; font-size: 13px; color: var(--muted); }
.head { display: flex; align-items: center; gap: 20px; margin: 6px 0 10px; }
.symbol { font-family: "Acervo IPA", system-ui, sans-serif; font-size: 72px; line-height: 1.1;
  min-width: 96px; text-align: center; background: var(--card); border: 1px solid var(--line);
  border-radius: 14px; padding: 6px 14px; }
.title { font-size: 22px; font-weight: 600; }
.lines { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 6px 14px; }
.line { display: grid; grid-template-columns: 92px 1fr; gap: 10px; padding: 7px 0; border-top: 1px solid var(--line); }
.line:first-child { border-top: 0; }
.line .k { color: var(--muted); font-size: 15px; padding-top: 1px; }
.line .v { font-family: system-ui, sans-serif, "Acervo IPA"; }
h2 { font-size: 15px; color: var(--muted); font-weight: 600; margin: 22px 0 6px; text-transform: uppercase; letter-spacing: .06em; }
.row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.row > button { flex: 1 1 0; max-width: 170px; }
.cand { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 10px 12px; margin: 8px 0;
  display: grid; grid-template-columns: auto 1fr auto; gap: 4px 12px; align-items: center; }
.cand.picked { border-color: var(--good); box-shadow: 0 0 0 1px var(--good) inset; }
.cand .play { min-width: 84px; grid-row: span 2; }
.cand .pick { grid-row: span 2; }
.cand .file { font-size: 15px; overflow-wrap: anywhere; }
.cand .file a { color: inherit; }
.cand .lic { font-size: 14px; color: var(--muted); overflow-wrap: anywhere; }
.cand .lic .bad { color: var(--warn); font-weight: 600; }
.empty { color: var(--muted); font-style: italic; margin: 8px 0; }
.none { margin-top: 4px; }
textarea { width: 100%; font: inherit; font-size: 15px; color: var(--ink); background: var(--card);
  border: 1px solid var(--line); border-radius: 10px; padding: 8px; min-height: 44px; resize: vertical; margin-top: 10px; }
.nav { display: flex; gap: 10px; margin: 24px 0 40px; }
.nav button { flex: 1; }
.error { color: var(--warn); }
@media (max-width: 520px) {
  .symbol { font-size: 52px; min-width: 76px; }
  .line { grid-template-columns: 1fr; gap: 0; }
  .cand { grid-template-columns: auto 1fr; }
  .cand .pick { grid-column: 1 / -1; grid-row: auto; }
}
</style>
</head>
<body>
<header>
  <span class="count" id="count">Loading…</span>
  <span class="error" id="error"></span>
  <select id="jump" aria-label="Section"></select>
  <button id="todo">Next to do</button>
</header>
<main id="main"></main>
<script>
const state = { cards: [], labels: {}, verdicts: [], at: 0 };
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
const label = card => state.labels[card.id] || {};
const free = card => card.candidates.filter(c => c.free);
const done = card => !!label(card).text && (!free(card).length || !!label(card).pick);
// Redraws nobody tapped for wait while a note is being typed: an iPad closes its keyboard the
// moment the focused field leaves the page.
const typing = () => document.activeElement && document.activeElement.tagName === "TEXTAREA";
async function save(card, field, value) {
  const mine = state.labels[card.id] = { ...label(card) };
  if (value == null || value === "") delete mine[field]; else mine[field] = value;
  try {
    const answer = await fetch("/label", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: card.id, field, value }) });
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
const playable = c => c.mp3 || (/\.(mp3|wav)$/i.test(c.original) ? c.original : null);
function render() {
  const total = state.cards.length, finished = state.cards.filter(done).length;
  const card = state.cards[state.at];
  document.getElementById("count").textContent = `${finished} of ${total} done · card ${state.at + 1}`;
  document.getElementById("jump").value = card ? card.section : "";
  const main = document.getElementById("main");
  if (!card) { main.textContent = "Nothing to review."; return; }
  const mine = label(card), scroll = window.scrollY;
  const candidates = card.candidates.length ? card.candidates.map(c => {
    const src = playable(c);
    return $("div", { class: "cand" + (mine.pick === c.file ? " picked" : "") },
      $("button", { class: "play" + (playing === src ? " on" : ""), disabled: !src, onclick: () => play(src) },
        playing === src ? "■ Stop" : "▶ Play"),
      $("div", { class: "file" }, $("a", { href: c.page, target: "_blank", rel: "noopener" }, c.file)),
      $("button", { class: "pick" + (mine.pick === c.file ? " on" : ""), disabled: !c.free,
        onclick: () => save(card, "pick", mine.pick === c.file ? null : c.file) }, mine.pick === c.file ? "Picked" : "Pick"),
      $("div", { class: "lic" }, c.free ? c.license : $("span", { class: "bad" }, `${c.license || "no licence"}: cannot ship`),
        c.author ? ` · ${c.author}` : ""));
  }) : [$("p", { class: "empty" }, "No recording found on Commons.")];
  main.replaceChildren(...[
    $("div", { class: "section" }, card.section),
    $("div", { class: "head" }, $("div", { class: "symbol" }, card.shown), $("div", { class: "title" }, card.title)),
    card.lines.length ? $("div", { class: "lines" }, card.lines.map(([k, v]) =>
      $("div", { class: "line" }, $("span", { class: "k" }, k), $("span", { class: "v" }, v)))) : null,
    $("h2", {}, "Recording"),
    candidates,
    free(card).length ? $("div", { class: "row none" }, $("button", { class: mine.pick === "none" ? "on" : "",
      onclick: () => save(card, "pick", mine.pick === "none" ? null : "none") }, "None fits")) : null,
    $("h2", {}, "Wording"),
    $("div", { class: "row" }, state.verdicts.map(v => $("button", { class: mine.text === v ? "on" : "",
      onclick: () => save(card, "text", mine.text === v ? null : v) }, v))),
    (() => {
      const note = $("textarea", { placeholder: "Note (optional): what is wrong, or a better word", rows: 2 });
      note.value = mine.note || "";
      note.addEventListener("input", () => { clearTimeout(noteTimer); noteTimer = setTimeout(() => save(card, "note", note.value), 700); });
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
  try { localStorage.setItem("ipa-sounds-at", String(n)); } catch (e) {}
  render(); window.scrollTo(0, 0);
}
document.getElementById("todo").addEventListener("click", () => {
  const n = state.cards.length;
  for (let k = 1; k <= n; k++) { const i = (state.at + k) % n; if (!done(state.cards[i])) return go(i); }
});
document.getElementById("jump").addEventListener("change", e => go(state.cards.findIndex(c => c.section === e.target.value)));
fetch("/data").then(r => r.json()).then(data => {
  Object.assign(state, data);
  const sections = [...new Set(state.cards.map(c => c.section))];
  document.getElementById("jump").replaceChildren(...sections.map(s => $("option", { value: s }, s)));
  let at = 0;
  try { at = Number(localStorage.getItem("ipa-sounds-at")) || 0; } catch (e) {}
  state.at = Math.min(at, state.cards.length - 1);
  render();
});
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the IPA sounds review page.")
    parser.add_argument("--host", default="127.0.0.1", help="the laptop's Tailscale IP to reach it from a tablet")
    parser.add_argument("--port", type=int, default=8771)
    args = parser.parse_args()
    if not (RESULTS / "candidates.json").exists():
        raise SystemExit("no results/candidates.json: run candidates.py first")
    print(f"http://{args.host}:{args.port}/")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
