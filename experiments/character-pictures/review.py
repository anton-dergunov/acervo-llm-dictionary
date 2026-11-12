"""The blind scoring page: each character's pictures, labelled by letter, three questions each.

    .venv/bin/python experiments/character-pictures/review.py --host "$(tailscale ip -4)"

On first start every character's planned pictures — each model, way and take — are shuffled into
letters with a fixed seed and written to `out/key.json`; the page is never told which letter is
which, and a picture's URL is `/img/<character index>/<letter>`, so nothing on screen gives it
away. A picture appears once it is drawn, so the page can be opened while `run.py draw` is still
running; reload to see new ones. Answers go to `out/labels.json` on every tap, so closing the tab
loses nothing. `run.py report` unblinds them.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import run

OUT = run.OUT
SEED = 20261112
QUESTIONS = run.QUESTIONS
ANSWERS = run.ANSWERS

_lock = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def build() -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """The characters, and each one's letter → `model/way/take` key.

    The key is kept across restarts. A picture planned later — a model added to `MODELS` — is
    given the next free letter, so a letter that has been judged never comes to mean another one.
    """
    items = run.selected()
    scripts = run._scripts()
    key: dict[str, dict[str, str]] = _read(OUT / "key.json", {})
    for item in items:
        character = item["character"]
        planned = [f"{model.id}/{way}/{take}" for model in run.MODELS
                   for c, way, take in run._wanted(model, [item])]
        held = key.setdefault(character, {})
        new = [name for name in planned if name not in held.values()]
        random.Random(f"{SEED}:{character}:{len(held)}").shuffle(new)
        free = (letter for letter in string.ascii_uppercase if letter not in held)
        for name in new:
            held[next(free)] = name
    _write(OUT / "key.json", key)
    shown = []
    for index, item in enumerate(items):
        character = item["character"]
        strokes = run._strokes(character)["strokes"]
        shown.append({
            "index": index,
            "character": character,
            "definition": item["definition"],
            "hint": item["hint"],
            "type": item["type"],
            "object": item["object"],
            "history": (scripts[character].get("history") or "").strip(),
            "lines": item["lines"],
            "colours": [run.COLOURS[i % len(run.COLOURS)][1] for i in range(len(strokes))],
            "outlines": strokes,
            "letters": sorted(key[character]),
        })
    return shown, key


def _picture(key: dict[str, dict[str, str]], character: str, letter: str) -> Path | None:
    name = key.get(character, {}).get(letter)
    if not name:
        return None
    model, way, take = name.split("/")
    return run.picture_path(character, model, way, int(take))


class Handler(BaseHTTPRequestHandler):
    characters: list[dict[str, Any]] = []
    key: dict[str, dict[str, str]] = {}

    def log_message(self, *_: Any) -> None:  # the terminal is for errors, not every picture
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
            characters = []
            for item in self.characters:
                drawn = [letter for letter in item["letters"]
                         if (file := _picture(self.key, item["character"], letter)) and file.exists()]
                characters.append({**item, "letters": drawn})
            body = {"characters": characters, "labels": _read(OUT / "labels.json", {})}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json")
        elif self.path.startswith(("/img/", "/ref/")):
            try:
                parts = self.path.split("/")
                item = self.characters[int(parts[2])]
                file = (OUT / "strokes" / f"{item['character']}.png" if parts[1] == "ref"
                        else _picture(self.key, item["character"], parts[3]))
            except (ValueError, IndexError):
                file = None
            if not file or not file.exists():
                self._send(404, b"", "text/plain")
                return
            kind = "image/png" if file.suffix == ".png" else "image/webp"
            self._send(200, file.read_bytes(), kind, cache=True)
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/rate":
            self._send(404, b"", "text/plain")
            return
        try:
            update = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            character = update["character"]
            if character not in self.key:
                raise KeyError(character)
            if "answer" in update:
                letter, question, answer = update["letter"], update["question"], update["answer"]
                if letter not in self.key[character] or question not in QUESTIONS \
                        or answer not in (*ANSWERS, ""):
                    raise ValueError(update)
        except (ValueError, KeyError, TypeError):
            self._send(HTTPStatus.BAD_REQUEST, b"", "text/plain")
            return
        with _lock:
            labels = _read(OUT / "labels.json", {})
            label = labels.setdefault(character, {"pictures": {}, "note": ""})
            if "answer" in update:
                answers = label["pictures"].setdefault(update["letter"], {})
                if update["answer"]:
                    answers[update["question"]] = update["answer"]
                else:
                    answers.pop(update["question"], None)
            if "note" in update:
                label["note"] = str(update["note"])[:2000]
            _write(OUT / "labels.json", labels)
        self._send(200, b"{}", "application/json")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Character pictures, blind</title>
<style>
:root {
  --bg: #f6f2ea; --card: #fffdf8; --ink: #2a2622; --muted: #7a7166; --rule: #e2dacd;
  --accent: #3f6b4f; --accent-soft: #dfeadf; --mid: #a07a1f; --mid-soft: #f4ead2;
  --warn: #9a4b2f; --warn-soft: #f3e1d8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1a17; --card: #25221e; --ink: #ece6dc; --muted: #a39a8d; --rule: #3a352f;
    --accent: #8fc09f; --accent-soft: #2c3b30; --mid: #e0c27a; --mid-soft: #3d3524;
    --warn: #e3a184; --warn-soft: #43302a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 17px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header.bar { position: sticky; top: 0; z-index: 5; background: var(--bg);
  border-bottom: 1px solid var(--rule); padding: 10px 16px; display: flex; gap: 10px;
  align-items: center; flex-wrap: wrap; }
header.bar .count { font-weight: 600; margin-right: auto; }
main { max-width: 900px; margin: 0 auto; padding: 8px 16px 80px; }
section.card { background: var(--card); border: 1px solid var(--rule); border-radius: 14px;
  padding: 16px; margin: 18px 0; }
.head { display: flex; gap: 16px; align-items: flex-start; }
.glyph { font-size: 76px; line-height: 1; font-family: "PingFang SC", "Noto Sans SC", serif; }
.facts { flex: 1; min-width: 0; }
.facts .def { color: var(--muted); font-size: 15px; }
.facts .object { margin: 4px 0; }
.facts .hint { color: var(--muted); font-size: 14px; }
.ref { width: 120px; height: 120px; border: 1px solid var(--rule); border-radius: 8px;
  cursor: zoom-in; flex: none; }
details { margin: 8px 0; }
summary { cursor: pointer; color: var(--accent); font-weight: 600; }
details ol { margin: 6px 0; padding-left: 22px; font-size: 15px; }
details .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  margin-right: 6px; vertical-align: middle; }
details p { font-size: 15px; color: var(--muted); }
.questions { font-size: 14px; color: var(--muted); margin: 8px 0 4px; padding-left: 20px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 10px; }
figure { margin: 0; }
.frame { position: relative; }
.frame img { width: 100%; aspect-ratio: 1; object-fit: contain; border-radius: 8px; display: block;
  background: var(--rule); cursor: zoom-in; }
.frame svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none;
  display: none; }
body.overlay .frame svg { display: block; }
.letter { position: absolute; left: 6px; top: 6px; background: rgba(0,0,0,.6); color: #fff;
  font-size: 14px; font-weight: 700; border-radius: 999px; padding: 1px 9px; pointer-events: none; }
.letter.done { background: var(--accent); }
.q { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
.q .label { width: 78px; font-size: 14px; font-weight: 600; }
button { font: inherit; border: 1px solid var(--rule); background: var(--card); color: var(--ink);
  border-radius: 999px; padding: 4px 12px; min-height: 36px; cursor: pointer; font-size: 15px; }
.q button { flex: 1; padding: 4px 4px; }
button[aria-pressed="true"].yes { background: var(--accent); border-color: var(--accent); color: var(--card); }
button[aria-pressed="true"].partly { background: var(--mid); border-color: var(--mid); color: var(--card); }
button[aria-pressed="true"].no { background: var(--warn); border-color: var(--warn); color: var(--card); }
#overlay[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); }
textarea { width: 100%; min-height: 56px; font: inherit; border: 1px solid var(--rule);
  border-radius: 8px; padding: 8px; background: var(--bg); color: var(--ink); margin-top: 14px; }
.saved { color: var(--muted); font-size: 13px; min-height: 18px; }
.empty { color: var(--muted); }
#zoom { position: fixed; inset: 0; background: rgba(0,0,0,.92); display: none; z-index: 10;
  place-items: center; }
#zoom.open { display: grid; }
#zoom .frame { width: min(100vw, 100vh); }
#zoom img { cursor: zoom-out; border-radius: 0; }
#zoom .where { position: absolute; top: 12px; left: 16px; color: #ddd; font-size: 15px; z-index: 1; }
</style>
</head>
<body>
<header class="bar"><span class="count" id="count">Loading…</span>
  <button id="overlay" aria-pressed="false">Overlay strokes</button>
  <button id="next">Next unjudged ↓</button></header>
<main id="cards"></main>
<div id="zoom" role="dialog" aria-label="Picture"><span class="where"></span>
  <div class="frame"><img alt=""></div></div>
<script>
const QUESTIONS = [
  ["strokes", "Strokes"], ["depicts", "Depicts"], ["remember", "Remember"]];
const ANSWERS = ["yes", "partly", "no"];
let DATA, LABELS;
const SVGNS = "http://www.w3.org/2000/svg";
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v; else if (k.startsWith("on")) node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid);
  return node;
};

function overlaySvg(item) {
  // The character's exact strokes, in the frame every picture was asked to keep: a 1024 box, y up.
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", "0 0 1024 1024");
  const g = document.createElementNS(SVGNS, "g");
  g.setAttribute("transform", "translate(0 900) scale(1 -1)");
  for (const d of item.outlines) {
    const path = document.createElementNS(SVGNS, "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "rgba(233, 30, 99, 0.38)");
    path.setAttribute("stroke", "rgba(233, 30, 99, 0.9)");
    path.setAttribute("stroke-width", "6");
    g.append(path);
  }
  svg.append(g);
  return svg;
}

async function save(body, status) {
  status.textContent = "Saving…";
  try {
    const response = await fetch("/rate", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(response.status);
    status.textContent = "Saved";
  } catch (error) { status.textContent = "Not saved — is the laptop awake? (" + error.message + ")"; }
  updateCount();
}

const label = c => LABELS[c] ??= { pictures: {}, note: "" };
const complete = (c, letter) => QUESTIONS.every(([q]) => label(c).pictures[letter]?.[q]);

function updateCount() {
  let done = 0, total = 0;
  for (const item of DATA.characters) for (const letter of item.letters) {
    total++; if (complete(item.character, letter)) done++;
  }
  document.getElementById("count").textContent = `${done} of ${total} pictures judged`;
}

function zoom(src, where, item) {
  const box = document.getElementById("zoom");
  const frame = box.querySelector(".frame");
  frame.querySelector("img").src = src;
  frame.querySelector("svg")?.remove();
  if (item) frame.append(overlaySvg(item));
  box.querySelector(".where").textContent = where;
  box.classList.add("open");
}
document.getElementById("zoom").onclick = () => document.getElementById("zoom").classList.remove("open");

function render(item) {
  const c = item.character;
  const status = $("div", { class: "saved" });
  const ref = $("img", { class: "ref", src: `/ref/${item.index}`, alt: `${c}, its strokes coloured`,
    onclick: () => zoom(`/ref/${item.index}`, `${c} · the strokes as sent`) });
  const script = $("details", {}, $("summary", {}, "Stroke script and history"));
  const list = $("ol");
  item.lines.forEach((line, i) => list.append($("li", {},
    $("span", { class: "dot", style: `background:${item.colours[i]}` }), `${line.part} — `,
    $("span", { style: "color:var(--muted)" }, line.where))));
  script.append(list);
  if (item.history) script.append($("p", {}, item.history));
  const section = $("section", { class: "card", id: "c-" + item.index },
    $("div", { class: "head" }, $("div", { class: "glyph", lang: "zh-CN" }, c),
      $("div", { class: "facts" },
        $("div", { class: "object" }, item.object),
        $("div", { class: "def" }, item.definition),
        $("div", { class: "hint" }, `Source: ${item.type} — “${item.hint}”`)), ref),
    script,
    $("ol", { class: "questions" },
      $("li", {}, `Strokes — do its parts lie where ${c}'s strokes are, so it still reads as ${c}?`),
      $("li", {}, `Depicts — does it show what ${c} depicted: ${item.object}?`),
      $("li", {}, `Remember — would it help you remember ${c}, linking its strokes to that meaning?`)));

  const grid = $("div", { class: "grid" });
  if (!item.letters.length) grid.append($("p", { class: "empty" }, "Nothing drawn yet."));
  for (const letter of item.letters) {
    const src = `/img/${item.index}/${letter}`;
    const badge = $("span", { class: "letter" + (complete(c, letter) ? " done" : "") }, letter);
    const frame = $("div", { class: "frame" },
      $("img", { src, loading: "lazy", alt: `${c}, picture ${letter}`,
        onclick: () => zoom(src, `${c} · ${letter}`,
          document.body.classList.contains("overlay") ? item : null) }),
      overlaySvg(item), badge);
    const figure = $("figure", {}, frame);
    for (const [q, name] of QUESTIONS) {
      const row = $("div", { class: "q" }, $("span", { class: "label" }, name));
      for (const answer of ANSWERS) {
        const now = label(c).pictures[letter]?.[q] === answer;
        const button = $("button", { class: answer, "aria-pressed": String(now) }, answer);
        button.onclick = () => {
          const answers = label(c).pictures[letter] ??= {};
          const next = answers[q] === answer ? "" : answer;
          if (next) answers[q] = next; else delete answers[q];
          row.querySelectorAll("button").forEach(b =>
            b.setAttribute("aria-pressed", String(b.textContent === next)));
          badge.className = "letter" + (complete(c, letter) ? " done" : "");
          save({ character: c, letter, question: q, answer: next }, status);
        };
        row.append(button);
      }
      figure.append(row);
    }
    grid.append(figure);
  }
  section.append(grid);
  const note = $("textarea", { placeholder: `Note on ${c} (optional)` });
  note.value = label(c).note || "";
  let timer;
  note.oninput = () => { clearTimeout(timer); timer = setTimeout(() => {
    label(c).note = note.value; save({ character: c, note: note.value }, status); }, 700); };
  section.append(note, status);
  return section;
}

const overlayButton = document.getElementById("overlay");
function setOverlay(on) {
  document.body.classList.toggle("overlay", on);
  overlayButton.setAttribute("aria-pressed", String(on));
  try { localStorage.setItem("character-pictures-overlay", on ? "1" : ""); } catch {}
}
overlayButton.onclick = () => setOverlay(!document.body.classList.contains("overlay"));
try { setOverlay(!!localStorage.getItem("character-pictures-overlay")); } catch {}

document.getElementById("next").onclick = () => {
  for (const item of DATA.characters) for (const letter of item.letters) {
    if (!complete(item.character, letter)) {
      document.getElementById("c-" + item.index).scrollIntoView({ behavior: "smooth" });
      return;
    }
  }
};

fetch("/data").then(r => r.json()).then(data => {
  DATA = data; LABELS = data.labels || {};
  const list = document.getElementById("cards");
  data.characters.forEach(item => list.append(render(item)));
  updateCount();
});
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to listen on; the laptop's Tailscale IP to reach it from a tablet")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args(argv)
    Handler.characters, Handler.key = build()
    drawn = sum(1 for item in Handler.characters for letter in item["letters"]
                if (file := _picture(Handler.key, item["character"], letter)) and file.exists())
    print(f"{len(Handler.characters)} characters, {drawn} pictures drawn so far")
    print(f"open http://{args.host}:{args.port}/  — Ctrl-C to stop; answers are saved as you tap")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
