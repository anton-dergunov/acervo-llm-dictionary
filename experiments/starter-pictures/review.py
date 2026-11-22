"""The review page: one concept at a time, its latest picture, Good or Redraw.

    .venv/bin/python experiments/starter-pictures/review.py --host "$(tailscale ip -4)"

Open the printed address on the tablet. Each screen shows a concept's English sense, its note, the
words three vocabularies matched to it, the style and the brief, and the picture. **✓ Good** saves
and moves to the next concept not yet labelled; **↻ Redraw** saves and opens a note box for what is
wrong (a lettering, the wrong meaning, a culture-bound scene), then **Next**. Every tap is written to
`results/labels.json` at once, so closing the tab loses nothing; a label names the take it judged, so
a redrawn concept comes back unlabelled with its new take. Reload to see pictures drawn since.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import run

_lock = threading.Lock()
CONCEPT = re.compile(r"^[a-z0-9-]+$")


def items() -> list[dict[str, Any]]:
    import cards

    labelled = run.labels()
    out = []
    for card in cards.cards():
        brief = run.read_brief(card.id) or {}
        takes = run.takes(card.id)
        label = labelled.get(card.id) or {}
        current = bool(takes) and label.get("take") == takes[-1]
        out.append({**card.summary(), "styleLabel": brief.get("styleLabel"), "brief": brief.get("brief"),
                    "refused": brief.get("refusalReason") if brief.get("refused") else None,
                    "takes": takes, "label": label.get("label") if current else None,
                    "note": label.get("note") if current else None,
                    "earlier": label if label and not current else None, "conceptNote": card.note})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None:
        pass

    def _send(self, status: int, body: bytes, kind: str, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/data":
            self._send(200, json.dumps(items(), ensure_ascii=False).encode(), "application/json")
        elif match := re.match(r"^/img/([a-z0-9-]+)/(\d+)$", self.path):
            path = run.picture_path(match[1], int(match[2]))
            if path.exists():
                self._send(200, path.read_bytes(), "image/webp", cache=True)
            else:
                self._send(404, b"not drawn", "text/plain")
        else:
            self._send(404, b"no such page", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/label":
            self._send(404, b"no such page", "text/plain")
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        concept, label = str(body.get("concept", "")), body.get("label")
        if not CONCEPT.match(concept) or label not in ("good", "redraw", None):
            self._send(HTTPStatus.BAD_REQUEST, b"bad label", "text/plain")
            return
        takes = run.takes(concept)
        if not takes:
            self._send(HTTPStatus.BAD_REQUEST, b"not drawn yet", "text/plain")
            return
        with _lock:
            labelled = run.labels()
            if label is None:
                labelled.pop(concept, None)
            else:
                labelled[concept] = {"label": label, "take": takes[-1], "note": str(body.get("note") or "").strip(),
                                     "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            run.write_json(run.LABELS, dict(sorted(labelled.items())))
        self._send(200, b'{"ok": true}', "application/json")


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Concept pictures</title>
<style>
:root { --bg:#f6f4ef; --fg:#1d1b18; --muted:#6b665d; --line:#ddd7cc; --card:#fff;
        --good:#2e7d32; --redraw:#c62828; --accent:#3b5bdb; }
@media (prefers-color-scheme: dark) { :root { --bg:#161513; --fg:#ece8e1; --muted:#a39d92; --line:#36332e;
        --card:#211f1c; --good:#66bb6a; --redraw:#ef5350; --accent:#8ea2ff; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.4 -apple-system, system-ui, sans-serif;
       -webkit-text-size-adjust:100%; }
main { max-width:760px; margin:0 auto; padding:12px 16px 24px; }
.bar { display:flex; justify-content:space-between; align-items:baseline; gap:8px; color:var(--muted); font-size:14px; }
h1 { margin:6px 0 2px; font-size:24px; }
.sense { font-size:18px; margin:0 0 8px; }
.meta { color:var(--muted); font-size:14px; }
figure { margin:8px 0; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden;
         aspect-ratio:1/1; width:min(100%, 58vh); margin-inline:auto; display:flex; align-items:center; justify-content:center; }
figure img { width:100%; height:100%; object-fit:contain; display:block; }
figure .none { color:var(--muted); padding:24px; text-align:center; }
.buttons { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:10px 0; }
.nav { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; }
button { font:inherit; font-size:19px; padding:16px 10px; border-radius:10px; border:1px solid var(--line);
         background:var(--card); color:var(--fg); touch-action:manipulation; }
button.good { border-color:var(--good); color:var(--good); font-weight:600; }
button.redraw { border-color:var(--redraw); color:var(--redraw); font-weight:600; }
button.good.on { background:var(--good); color:#fff; }
button.redraw.on { background:var(--redraw); color:#fff; }
button:disabled { opacity:.4; }
.status { text-align:center; font-weight:600; min-height:1.4em; }
textarea { width:100%; font:inherit; padding:10px; border-radius:8px; border:1px solid var(--line);
           background:var(--card); color:var(--fg); min-height:64px; }
.context { border-top:1px solid var(--line); margin-top:12px; padding-top:8px; font-size:15px; }
.context dt { color:var(--muted); font-size:13px; margin-top:6px; }
.context dd { margin:0; }
.pin b { font-weight:600; }
</style></head>
<body><main>
<div class="bar"><span id="pos"></span><span id="tally"></span></div>
<h1 id="id"></h1>
<p class="sense"><span id="sense"></span> <span class="meta" id="pos-topic"></span></p>
<figure id="figure"></figure>
<div class="status" id="status"></div>
<div class="buttons">
  <button class="good" id="good">✓ Good</button>
  <button class="redraw" id="redraw">↻ Redraw</button>
</div>
<div id="note-box" hidden>
  <textarea id="note" placeholder="What is wrong? (optional)"></textarea>
</div>
<div class="nav">
  <button id="prev">‹ Prev</button>
  <button id="todo">Next to label</button>
  <button id="next">Next ›</button>
</div>
<dl class="context" id="context"></dl>
</main>
<script>
let items = [], at = 0;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function remember() { try { localStorage.setItem("at", items[at] ? items[at].id : ""); } catch (e) {} }
function recall() { try { return localStorage.getItem("at"); } catch (e) { return null; } }

async function load() {
  items = await (await fetch("/data")).json();
  const saved = recall();
  const found = items.findIndex(i => i.id === saved);
  at = found >= 0 ? found : Math.max(0, items.findIndex(i => i.takes.length && !i.label));
  show();
}
function tally() {
  const drawn = items.filter(i => i.takes.length);
  const good = drawn.filter(i => i.label === "good").length, redraw = drawn.filter(i => i.label === "redraw").length;
  $("tally").textContent = `${good} good · ${redraw} redraw · ${drawn.length - good - redraw} to label · ${drawn.length}/${items.length} drawn`;
}
function show() {
  const i = items[at];
  remember(); tally();
  $("pos").textContent = `${at + 1} / ${items.length}`;
  $("id").textContent = i.id;
  $("sense").textContent = i.sense;
  $("pos-topic").textContent = `${i.pos} · ${i.topic}`;
  const take = i.takes[i.takes.length - 1];
  $("figure").innerHTML = take
    ? `<img alt="" src="/img/${i.id}/${take}">`
    : `<div class="none">${i.refused ? "The brief writer refused: " + esc(i.refused) : "Not drawn yet"}</div>`;
  $("good").disabled = $("redraw").disabled = !take;
  $("good").classList.toggle("on", i.label === "good");
  $("redraw").classList.toggle("on", i.label === "redraw");
  $("status").textContent = take ? (i.label ? (i.label === "good" ? "Good" : "Redraw") : "")
    + (i.takes.length > 1 ? ` (take ${take})` : "") : "";
  $("note-box").hidden = i.label !== "redraw";
  $("note").value = i.note || "";
  let context = "";
  if (i.conceptNote) context += `<dt>Note</dt><dd>${esc(i.conceptNote)}</dd>`;
  context += `<dt>Matched in</dt>` + i.pins.map(p =>
    `<dd class="pin">${esc(p.vocabulary)} <b>${esc(p.headword)}</b>: ${esc(p.definition)}</dd>`).join("");
  context += `<dt>English headword</dt><dd>${esc(i.headword)} · matched in ${i.vocabularies} vocabularies</dd>`;
  if (i.styleLabel) context += `<dt>Style</dt><dd>${esc(i.styleLabel)}</dd>`;
  if (i.brief) context += `<dt>Brief</dt><dd>${esc(i.brief)}</dd>`;
  if (i.earlier) context += `<dt>Earlier take ${i.earlier.take}</dt><dd>${esc(i.earlier.label)}${i.earlier.note ? ": " + esc(i.earlier.note) : ""}</dd>`;
  $("context").innerHTML = context;
  window.scrollTo(0, 0);
}
async function save(label, note) {
  const i = items[at];
  const response = await fetch("/label", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({concept: i.id, label, note})});
  if (!response.ok) { $("status").textContent = "Not saved: " + await response.text(); return false; }
  i.label = label; i.note = note || "";
  return true;
}
function go(index) { if (index >= 0 && index < items.length) { at = index; show(); } }
function nextToLabel() {
  for (let k = 1; k <= items.length; k++) {
    const index = (at + k) % items.length;
    if (items[index].takes.length && !items[index].label) return go(index);
  }
  $("status").textContent = "Everything drawn is labelled";
}
async function leave() {   // a redraw note typed and not yet sent goes with the move
  const i = items[at];
  if (i.label === "redraw" && $("note").value.trim() !== (i.note || "")) await save("redraw", $("note").value);
}
$("good").onclick = async () => { if (await save("good", "")) nextToLabel(); };
$("redraw").onclick = async () => { if (await save("redraw", $("note").value)) { show(); $("note").focus(); } };
$("prev").onclick = async () => { await leave(); go(at - 1); };
$("next").onclick = async () => { await leave(); go(at + 1); };
$("todo").onclick = async () => { await leave(); nextToLabel(); };
$("note").onblur = () => { if (items[at].label === "redraw") save("redraw", $("note").value); };
load();
</script></body></html>
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1", help='Where to listen; `"$(tailscale ip -4)"` for the tablet')
    parser.add_argument("--port", type=int, default=8771)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"review page: http://{args.host}:{args.port}/  (Ctrl-C to stop; labels go to {run.LABELS})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
