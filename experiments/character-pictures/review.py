"""The review pages: one character at a time, all its pictures side by side.

**`--choose`** (the full run): tap ★ on the best picture, or mark the character "none good —
redraw" with an optional note saying what is wrong. Nothing is scored. Choices go to
`out/full/choices.json` on every tap; `run.py batch --redraw` draws four more takes for the marked
characters, and they appear here beside the first four.

    .venv/bin/python experiments/character-pictures/review.py --choose --host "$(tailscale ip -4)"

**Without it**, the blind scoring page of rounds 1–3: each picture gets a score from 1 to 5 and two
yes / partly / no questions; one picture per character can be starred as the best, and a character
can be marked to redraw in a later pass.

    .venv/bin/python experiments/character-pictures/review.py --host "$(tailscale ip -4)"

On first start every character's planned pictures — each model, way and take — are shuffled into
letters with a fixed seed and written to the round's `key.json` (`out/round-N/`); the page is never
told which letter is which, and a picture's URL is `/img/<round>/<character index>/<letter>`, so
nothing on screen gives it away. The round is in the URL because pictures are cached for a day: without
it a browser shows the previous round's picture at the same index and letter. A picture appears once it is drawn, so the page can be opened while
`run.py draw` is still running; reload to see new ones. Answers go to the round's `labels.json` on
every tap, so closing the tab loses nothing. `run.py report` unblinds them.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import run

OUT = run.OUT
SEED = 20261112
QUESTIONS = run.QUESTIONS
ANSWERS = run.ANSWERS
SCORES = run.SCORES

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
            self._send(200, PAGE.replace("__STYLE__", STYLE).encode(), "text/html; charset=utf-8")
        elif self.path == "/data":
            characters = []
            for item in self.characters:
                drawn = [letter for letter in item["letters"]
                         if (file := _picture(self.key, item["character"], letter)) and file.exists()]
                characters.append({**item, "letters": drawn})
            body = {"round": run.STAGE, "characters": characters,
                    "labels": _read(OUT / "labels.json", {})}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json")
        elif self.path.startswith(("/img/", "/ref/")):
            try:
                parts = self.path.split("/")  # /img/<round>/<index>/<letter>, /ref/<round>/<index>
                if parts[2] != run.STAGE:
                    raise ValueError(parts[2])
                item = self.characters[int(parts[3])]
                file = (OUT / "strokes" / f"{item['character']}.png" if parts[1] == "ref"
                        else _picture(self.key, item["character"], parts[4]))
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
                if letter not in self.key[character]:
                    raise ValueError(update)
                if question == "score":
                    if answer not in ("", *SCORES):
                        raise ValueError(update)
                elif question not in QUESTIONS or answer not in (*ANSWERS, ""):
                    raise ValueError(update)
            if "best" in update and update["best"] not in ("", *self.key[character]):
                raise ValueError(update)
            if "redraw" in update and not isinstance(update["redraw"], bool):
                raise ValueError(update)
        except (ValueError, KeyError, TypeError):
            self._send(HTTPStatus.BAD_REQUEST, b"", "text/plain")
            return
        with _lock:
            labels = _read(OUT / "labels.json", {})
            label = labels.setdefault(character, {"pictures": {}, "best": "", "note": ""})
            if "answer" in update:
                answers = label["pictures"].setdefault(update["letter"], {})
                if update["answer"]:
                    answers[update["question"]] = update["answer"]
                else:
                    answers.pop(update["question"], None)
            if "best" in update:
                label["best"] = update["best"]
            if "note" in update:
                label["note"] = str(update["note"])[:2000]
            if "redraw" in update:
                label["redraw"] = update["redraw"]
            _write(OUT / "labels.json", labels)
        self._send(200, b"{}", "application/json")


STYLE = r""":root {
  --bg: #f6f2ea; --card: #fffdf8; --ink: #2a2622; --muted: #7a7166; --rule: #e2dacd;
  --accent: #3f6b4f; --accent-soft: #dfeadf; --mid: #a07a1f; --mid-soft: #f4ead2;
  --warn: #9a4b2f; --warn-soft: #f3e1d8; --star: #c98a00;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1a17; --card: #25221e; --ink: #ece6dc; --muted: #a39a8d; --rule: #3a352f;
    --accent: #8fc09f; --accent-soft: #2c3b30; --mid: #e0c27a; --mid-soft: #3d3524;
    --warn: #e3a184; --warn-soft: #43302a; --star: #f0c040;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header.bar { position: sticky; top: 0; z-index: 5; background: var(--bg);
  border-bottom: 1px solid var(--rule); padding: 8px 16px; display: flex; gap: 8px;
  align-items: center; }
header.bar .where { font-weight: 600; margin-right: auto; }
header.bar .count { color: var(--muted); font-size: 14px; }
main { max-width: 900px; margin: 0 auto; padding: 8px 16px 60px; }
button { font: inherit; border: 1px solid var(--rule); background: var(--card); color: var(--ink);
  border-radius: 999px; padding: 4px 12px; min-height: 36px; cursor: pointer; }
button:disabled { opacity: .4; cursor: default; }
button.on { background: var(--accent-soft); border-color: var(--accent); }
.strip { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0 10px; }
.strip button { min-width: 36px; min-height: 34px; padding: 0 6px; font-size: 18px;
  font-family: "PingFang SC", "Noto Sans SC", serif; border-radius: 8px; }
.strip button.some { background: var(--mid-soft); border-color: var(--mid); }
.strip button.done { background: var(--accent-soft); border-color: var(--accent); }
.strip button.here { outline: 2px solid var(--ink); outline-offset: 1px; }
.head { display: flex; gap: 14px; align-items: flex-start; }
.glyph { font-size: 64px; line-height: 1; font-family: "PingFang SC", "Noto Sans SC", serif; }
.facts { flex: 1; min-width: 0; }
.facts .def, .facts .hint { color: var(--muted); font-size: 14px; }
.ref { width: 96px; height: 96px; border: 1px solid var(--rule); border-radius: 8px;
  cursor: zoom-in; flex: none; background: #fff; }
details { margin: 6px 0; }
summary { cursor: pointer; color: var(--accent); font-weight: 600; font-size: 15px; }
details ol { margin: 6px 0; padding-left: 22px; font-size: 14px; }
details .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  margin-right: 6px; vertical-align: middle; }
details p { font-size: 14px; color: var(--muted); }
h3 { font-size: 15px; margin: 14px 0 6px; color: var(--muted); font-weight: 600; }
.grid { display: grid; grid-template-columns: repeat(var(--columns, 4), 1fr); gap: 10px; }
.tile { margin: 0; }
.frame { position: relative; }
.frame img { width: 100%; aspect-ratio: 1; object-fit: contain; border-radius: 8px; display: block;
  background: var(--rule); cursor: zoom-in; }
.frame svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none;
  display: none; }
body.overlay .frame svg { display: block; }
.badge { position: absolute; left: 5px; top: 5px; background: rgba(0,0,0,.6); color: #fff;
  font-size: 13px; font-weight: 700; border-radius: 999px; padding: 0 8px; pointer-events: none; }
.badge.done { background: var(--accent); }
.star { position: absolute; right: 4px; top: 4px; min-height: 32px; width: 32px; padding: 0;
  font-size: 18px; line-height: 1; background: rgba(255,255,255,.85); color: #999; border: none; }
.star.on { color: var(--star); background: rgba(255,255,255,.95); }
.tile.best .frame img { box-shadow: 0 0 0 3px var(--star); }
.redraw-row { display: flex; gap: 10px; align-items: center; margin: 14px 0 6px; color: var(--muted);
  font-size: 14px; }
.redraw-row button { flex: none; }
.scores { display: flex; gap: 3px; margin-top: 5px; }
.scores button { flex: 1; min-height: 34px; padding: 0; border-radius: 8px; font-size: 15px; }
.scores button[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--card); }
table { width: 100%; border-collapse: collapse; }
td, th { padding: 4px 3px; border-bottom: 1px solid var(--rule); text-align: left; }
th { font-size: 13px; color: var(--muted); font-weight: 600; }
td.pic { width: 64px; }
td.pic img { width: 56px; height: 56px; object-fit: contain; border-radius: 6px; display: block;
  background: var(--rule); cursor: zoom-in; }
td.letter { font-weight: 700; width: 24px; }
.seg { display: flex; gap: 2px; }
.seg button { flex: 1; min-height: 36px; padding: 0 2px; border-radius: 8px; font-size: 14px; }
.seg button[aria-pressed="true"].yes { background: var(--accent); border-color: var(--accent); color: var(--card); }
.seg button[aria-pressed="true"].partly { background: var(--mid); border-color: var(--mid); color: var(--card); }
.seg button[aria-pressed="true"].no { background: var(--warn); border-color: var(--warn); color: var(--card); }
.legend { font-size: 13px; color: var(--muted); margin: 0 0 6px; padding-left: 18px; }
textarea { width: 100%; min-height: 50px; font: inherit; border: 1px solid var(--rule);
  border-radius: 8px; padding: 8px; background: var(--card); color: var(--ink); margin-top: 12px; }
.saved { color: var(--muted); font-size: 13px; min-height: 18px; }
.foot { display: flex; justify-content: space-between; margin-top: 12px; }
.empty { color: var(--muted); }
#zoom { position: fixed; inset: 0; background: rgba(0,0,0,.98); display: none; z-index: 10;
  place-items: center; }
#zoom.open { display: grid; }
#zoom .frame { width: min(100vw, 100vh - 60px); }
#zoom .frame img { cursor: zoom-out; border-radius: 0; background: #fff; }
#zoom .top { position: absolute; top: 10px; left: 16px; right: 16px; display: flex; gap: 8px;
  align-items: center; color: #ddd; z-index: 1; }
#zoom .top .label { margin-right: auto; }
#zoom .top button { background: rgba(255,255,255,.12); color: #fff; border-color: rgba(255,255,255,.3); }
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Character pictures, blind</title>
<style>
__STYLE__</style>
</head>
<body>
<header class="bar">
  <button id="prev" aria-label="Previous character">‹</button>
  <span class="where" id="where">Loading…</span>
  <span class="count" id="count"></span>
  <button id="size" title="Pictures per row">▦ 4</button>
  <button id="overlay" title="Lay the exact strokes over every picture">Strokes</button>
  <button id="next" aria-label="Next character">›</button>
</header>
<main><div class="strip" id="strip"></div><div id="page"></div></main>
<div id="zoom" role="dialog" aria-label="Picture">
  <div class="top"><span class="label"></span>
    <button data-step="-1">‹</button><button data-step="1">›</button><button data-close>✕</button></div>
  <div class="frame"><img alt=""></div></div>
<script>
const QUESTIONS = [["strokes", "Strokes"], ["depicts", "Depicts"]];
const ANSWERS = ["yes", "partly", "no"];
const SCORES = ["1", "2", "3", "4", "5"];
const SVGNS = "http://www.w3.org/2000/svg";
let DATA, LABELS, HERE = 0;
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v; else if (k.startsWith("on")) node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid);
  return node;
};
const store = (k, v) => { try { v === undefined ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} };
const recall = k => { try { return localStorage.getItem(k); } catch { return null; } };

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

const label = c => LABELS[c] ??= { pictures: {}, best: "", note: "" };
const answers = (c, letter) => label(c).pictures[letter] ??= {};
const complete = (c, letter) =>
  QUESTIONS.every(([q]) => label(c).pictures[letter]?.[q]) && !!label(c).pictures[letter]?.score;
const characterState = item => {
  const done = item.letters.filter(l => complete(item.character, l)).length;
  return !item.letters.length ? "" : done === item.letters.length && label(item.character).best ? "done"
    : done || label(item.character).best ? "some" : "";
};

let statusLine;
async function save(body) {
  statusLine.textContent = "Saving…";
  try {
    const response = await fetch("/rate", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(response.status);
    statusLine.textContent = "Saved";
  } catch (error) { statusLine.textContent = "Not saved — is the laptop awake? (" + error.message + ")"; }
  updateCounts();
}

function updateCounts() {
  let done = 0, total = 0;
  for (const item of DATA.characters) for (const letter of item.letters) {
    total++; if (complete(item.character, letter)) done++;
  }
  document.getElementById("count").textContent = `${done} / ${total} judged`;
  document.querySelectorAll("#strip button").forEach((b, i) => {
    b.className = [characterState(DATA.characters[i]), i === HERE ? "here" : ""].join(" ");
  });
}

// ── the full-screen view, stepping through this character's pictures ──
let zoomList = [], zoomAt = 0, zoomItem = null;
function zoom(item, list, at) {
  zoomItem = item; zoomList = list; zoomAt = at; showZoom();
  document.getElementById("zoom").classList.add("open");
}
function showZoom() {
  const box = document.getElementById("zoom");
  const frame = box.querySelector(".frame");
  const [src, name] = zoomList[zoomAt];
  frame.querySelector("img").src = src;
  frame.querySelector("svg")?.remove();
  if (document.body.classList.contains("overlay") && zoomItem) frame.append(overlaySvg(zoomItem));
  box.querySelector(".label").textContent = `${zoomItem.character} · ${name} (${zoomAt + 1} of ${zoomList.length})`;
}
const zoomBox = document.getElementById("zoom");
zoomBox.querySelectorAll("[data-step]").forEach(b => b.onclick = e => {
  e.stopPropagation();
  zoomAt = (zoomAt + Number(b.dataset.step) + zoomList.length) % zoomList.length; showZoom();
});
zoomBox.querySelector("[data-close]").onclick = () => zoomBox.classList.remove("open");
zoomBox.querySelector("img").onclick = () => zoomBox.classList.remove("open");

function render() {
  const item = DATA.characters[HERE], c = item.character;
  const page = document.getElementById("page");
  page.replaceChildren();
  document.getElementById("where").textContent = `${c}  ·  ${HERE + 1} of ${DATA.characters.length}`;
  document.getElementById("prev").disabled = HERE === 0;
  document.getElementById("next").disabled = HERE === DATA.characters.length - 1;
  statusLine = $("div", { class: "saved" });
  const pictures = item.letters.map(letter => [`/img/${DATA.round}/${item.index}/${letter}`, letter]);

  const script = $("details", {}, $("summary", {}, "Stroke script and history"));
  const list = $("ol");
  item.lines.forEach((line, i) => list.append($("li", {},
    $("span", { class: "dot", style: `background:${item.colours[i]}` }), `${line.part} — `,
    $("span", { style: "color:var(--muted)" }, line.where))));
  script.append(list);
  if (item.history) script.append($("p", {}, item.history));
  page.append($("div", { class: "head" },
    $("div", { class: "glyph", lang: "zh-CN" }, c),
    $("div", { class: "facts" },
      $("div", {}, item.object),
      $("div", { class: "def" }, item.definition),
      $("div", { class: "hint" }, `Source: ${item.type} — “${item.hint}”`)),
    $("img", { class: "ref", src: `/ref/${DATA.round}/${item.index}`, alt: `${c}, its strokes coloured`,
      onclick: () => zoom(item, [[`/ref/${DATA.round}/${item.index}`, "the strokes as sent"]], 0) })), script);

  if (!item.letters.length) {
    page.append($("p", { class: "empty" }, "Nothing drawn yet for this character."));
    return;
  }

  // Compare: every picture at once, a score under each, and one best.
  page.append($("h3", {}, "How much do you like it, 1–5 — and ★ the best one"));
  const grid = $("div", { class: "grid" });
  const tiles = {};
  item.letters.forEach((letter, i) => {
    const badge = $("span", { class: "badge" + (complete(c, letter) ? " done" : "") }, letter);
    const star = $("button", { class: "star" + (label(c).best === letter ? " on" : ""),
      "aria-label": `Best: ${letter}` }, "★");
    star.onclick = () => {
      const next = label(c).best === letter ? "" : letter;
      label(c).best = next;
      for (const [l, t] of Object.entries(tiles)) {
        t.tile.classList.toggle("best", l === next);
        t.star.classList.toggle("on", l === next);
      }
      save({ character: c, best: next });
    };
    const scores = $("div", { class: "scores" });
    for (const score of SCORES) {
      const button = $("button", { "aria-pressed": String(answers(c, letter).score === score) }, score);
      button.onclick = () => {
        const next = answers(c, letter).score === score ? "" : score;
        if (next) answers(c, letter).score = next; else delete answers(c, letter).score;
        scores.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.textContent === next)));
        refreshBadges();
        save({ character: c, letter, question: "score", answer: next });
      };
      scores.append(button);
    }
    const tile = $("figure", { class: "tile" + (label(c).best === letter ? " best" : "") },
      $("div", { class: "frame" },
        $("img", { src: pictures[i][0], alt: `${c}, picture ${letter}`, onclick: () => zoom(item, pictures, i) }),
        overlaySvg(item), badge, star),
      scores);
    tiles[letter] = { tile, star, badge };
    grid.append(tile);
  });
  page.append(grid);
  function refreshBadges() {
    for (const [l, t] of Object.entries(tiles)) t.badge.className = "badge" + (complete(c, l) ? " done" : "");
  }

  // The two questions, one row a picture.
  page.append($("h3", {}, "Two questions per picture"),
    $("ol", { class: "legend" },
      $("li", {}, `Strokes — do its parts lie where ${c}'s strokes are, so it still reads as ${c}?`),
      $("li", {}, `Depicts — does it show what ${c} depicted: ${item.object}?`)));
  const table = $("table", {}, $("tr", {}, $("th", {}), $("th", {}),
    ...QUESTIONS.map(([, name]) => $("th", {}, name))));
  item.letters.forEach((letter, i) => {
    const row = $("tr", {},
      $("td", { class: "pic" }, $("img", { src: pictures[i][0], alt: letter, onclick: () => zoom(item, pictures, i) })),
      $("td", { class: "letter" }, letter));
    for (const [q] of QUESTIONS) {
      const seg = $("div", { class: "seg" });
      for (const answer of ANSWERS) {
        const button = $("button", { class: answer, "aria-pressed": String(answers(c, letter)[q] === answer) }, answer);
        button.onclick = () => {
          const next = answers(c, letter)[q] === answer ? "" : answer;
          if (next) answers(c, letter)[q] = next; else delete answers(c, letter)[q];
          seg.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.textContent === next)));
          refreshBadges();
          save({ character: c, letter, question: q, answer: next });
        };
        seg.append(button);
      }
      row.append($("td", {}, seg));
    }
    table.append(row);
  });
  page.append(table);

  // Marked for the later pass that redraws characters not yet good enough; the star stays.
  const redraw = $("button", { class: "redraw" + (label(c).redraw ? " on" : ""),
    "aria-pressed": String(!!label(c).redraw) }, "↻ Redraw later");
  redraw.onclick = () => {
    label(c).redraw = !label(c).redraw;
    redraw.classList.toggle("on", label(c).redraw);
    redraw.setAttribute("aria-pressed", String(label(c).redraw));
    save({ character: c, redraw: label(c).redraw });
  };
  page.append($("div", { class: "redraw-row" }, redraw,
    $("span", {}, "Not good enough yet: draw it again in a later pass, keeping the ★.")));
  const note = $("textarea", { placeholder: `Note on ${c} (optional)` });
  note.value = label(c).note || "";
  let timer;
  note.oninput = () => { clearTimeout(timer); timer = setTimeout(() => {
    label(c).note = note.value; save({ character: c, note: note.value }); }, 700); };
  page.append(note, statusLine, $("div", { class: "foot" },
    $("button", { onclick: () => go(HERE - 1), ...(HERE === 0 ? { disabled: "" } : {}) }, "‹ Previous"),
    $("button", { onclick: () => go(HERE + 1),
      ...(HERE === DATA.characters.length - 1 ? { disabled: "" } : {}) }, "Next character ›")));
  updateCounts();
}

function go(index) {
  if (index < 0 || index >= DATA.characters.length) return;
  HERE = index; store("character-pictures-at", String(index));
  history.replaceState(null, "", "#" + (index + 1));
  render(); window.scrollTo(0, 0);
}
document.getElementById("prev").onclick = () => go(HERE - 1);
document.getElementById("next").onclick = () => go(HERE + 1);

const overlayButton = document.getElementById("overlay");
function setOverlay(on) {
  document.body.classList.toggle("overlay", on);
  overlayButton.classList.toggle("on", on);
  store("character-pictures-overlay", on ? "1" : undefined);
}
overlayButton.onclick = () => setOverlay(!document.body.classList.contains("overlay"));
setOverlay(!!recall("character-pictures-overlay"));

const sizeButton = document.getElementById("size");
function setColumns(n) {
  document.documentElement.style.setProperty("--columns", n);
  sizeButton.textContent = `▦ ${n}`;
  store("character-pictures-columns", String(n));
}
sizeButton.onclick = () => {
  const now = Number(getComputedStyle(document.documentElement).getPropertyValue("--columns")) || 4;
  setColumns(now === 4 ? 2 : now + 1);
};
setColumns(Number(recall("character-pictures-columns")) || 4);

fetch("/data").then(r => r.json()).then(data => {
  DATA = data; LABELS = data.labels || {};
  const strip = document.getElementById("strip");
  data.characters.forEach((item, i) =>
    strip.append($("button", { lang: "zh-CN", onclick: () => go(i) }, item.character)));
  const fromHash = Number(location.hash.slice(1)) - 1;
  const remembered = Number(recall("character-pictures-at"));
  go(fromHash >= 0 ? fromHash : remembered >= 0 ? remembered : 0);
});
</script>
</body>
</html>
"""


# ── choosing: the full run ──────────────────────────────────────────────────


def choosable() -> list[dict[str, Any]]:
    """Every character of the full run, by its place in the catalogue (a stable index). The page
    lists those with pictures, looked up on every load, so new ones appear on a reload."""
    return [{"index": index, "character": entry["character"], "group": entry["group"]}
            for index, entry in enumerate(run.catalogue())]


class ChooseHandler(BaseHTTPRequestHandler):
    characters: list[dict[str, Any]] = []
    by_index: dict[int, dict[str, Any]] = {}

    def log_message(self, *_: Any) -> None:
        pass

    def _send(self, status: int, body: bytes, kind: str, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value: Any) -> None:
        self._send(200, json.dumps(value, ensure_ascii=False).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        parts = self.path.split("?")[0].split("/")
        if self.path in ("/", "/index.html"):
            self._send(200, CHOOSE_PAGE.replace("__STYLE__", STYLE).encode(), "text/html; charset=utf-8")
        elif self.path == "/data":
            listed = [{**item, "takes": takes} for item in self.characters
                      if (takes := run.drawn_takes(item["character"]))]
            self._json({"stage": run.STAGE, "groups": [name for name, _ in run.GROUPS],
                        "characters": listed, "choices": run.choices()})
        elif len(parts) == 3 and parts[1] == "char":
            try:
                item = self.by_index[int(parts[2])]
            except (ValueError, KeyError):
                self._send(404, b"", "text/plain")
                return
            character = item["character"]
            script = run._scripts()[character]
            entry = run.catalogue()[item["index"]]
            strokes = run._strokes(character)["strokes"]
            self._json({
                "character": character, "definition": entry["definition"], "hint": entry["hint"],
                "type": entry["type"], "object": str(script.get("object") or "").strip(),
                "history": str(script.get("history") or "").strip(),
                "lines": [{"where": str(line["where"]).strip(), "part": str(line["part"]).strip()}
                          for line in script.get("strokes") or []],
                "colours": [run.COLOURS[i % len(run.COLOURS)][1] for i in range(len(strokes))],
                "outlines": strokes,
            })
        elif len(parts) >= 4 and parts[1] in ("img", "ref") and parts[2] == run.STAGE:
            try:
                character = self.by_index[int(parts[3])]["character"]
                file = (run.reference(character) if parts[1] == "ref"
                        else run.picture_path(character, run.MODEL.id, "edit", int(parts[4])))
            except (ValueError, KeyError, IndexError):
                file = None
            if not file or not file.exists():
                self._send(404, b"", "text/plain")
                return
            self._send(200, file.read_bytes(), "image/png" if file.suffix == ".png" else "image/webp", cache=True)
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/choose":
            self._send(404, b"", "text/plain")
            return
        try:
            update = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            character = update["character"]
            takes = run.drawn_takes(character)
            if not takes:
                raise KeyError(character)
            if "best" in update and update["best"] not in (0, *takes):
                raise ValueError(update)
            if "redraw" in update and not isinstance(update["redraw"], bool):
                raise ValueError(update)
        except (ValueError, KeyError, TypeError):
            self._send(HTTPStatus.BAD_REQUEST, b"", "text/plain")
            return
        with _lock:
            marked = run.choices()
            label = marked.setdefault(character, {"best": 0, "redraw": False, "note": ""})
            if "best" in update:
                label["best"] = update["best"]
            if "redraw" in update:
                label["redraw"] = update["redraw"]
                # The redraw follows the takes seen when it was asked for (`run.wanted_takes`).
                label["redrawFrom"] = max(takes) if update["redraw"] else label.get("redrawFrom")
            if "note" in update:
                label["note"] = str(update["note"])[:2000]
            label["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _write(run.OUT / "choices.json", marked)
        self._json(label)


CHOOSE_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Character pictures</title>
<style>
__STYLE__
.groups { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 4px; align-items: center; }
.groups .sep { width: 10px; }
.groups button { font-size: 14px; min-height: 34px; }
.picker summary { font-size: 14px; margin: 4px 0; }
.tile .take { position: absolute; left: 5px; top: 5px; background: rgba(0,0,0,.6); color: #fff;
  font-size: 13px; font-weight: 700; border-radius: 999px; padding: 0 8px; pointer-events: none; }
.tile .take.new { background: var(--mid); }
.choose-row { display: flex; gap: 10px; align-items: center; margin: 14px 0 6px; flex-wrap: wrap; }
.choose-row .hint { color: var(--muted); font-size: 14px; }
button.redraw.on { background: var(--warn-soft); border-color: var(--warn); color: var(--warn); }
.strip button.redraw { background: var(--warn-soft); border-color: var(--warn); }
.foot { gap: 8px; }
.foot .grow { flex: 1; }
#zoom .top button.on { color: var(--star); border-color: var(--star); }
</style>
</head>
<body>
<header class="bar">
  <button id="prev" aria-label="Previous character">‹</button>
  <span class="where" id="where">Loading…</span>
  <span class="count" id="count"></span>
  <button id="size" title="Pictures per row">▦ 2</button>
  <button id="overlay" title="Lay the exact strokes over every picture">Strokes</button>
  <button id="next" aria-label="Next character">›</button>
</header>
<main>
  <div class="groups" id="groups"></div>
  <details class="picker" id="picker"><summary id="pickerLabel">Characters</summary><div class="strip" id="strip"></div></details>
  <div id="page"></div>
</main>
<div id="zoom" role="dialog" aria-label="Picture">
  <div class="top"><span class="label"></span>
    <button data-star>★ Best</button><button data-step="-1">‹</button><button data-step="1">›</button><button data-close>✕</button></div>
  <div class="frame"><img alt=""></div></div>
<script>
const SVGNS = "http://www.w3.org/2000/svg";
const NAMES = { g1: "Top 1,000", g2: "1,000–2,000", g3: "2,000–3,000", g4: "Rarer" };
let DATA, CHOICES, LIST = [], HERE = 0, GROUP = "g1", FILTER = "all", DETAIL = null;
const cache = new Map();
const $ = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v; else if (k.startsWith("on")) node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid);
  return node;
};
const store = (k, v) => { try { v === undefined ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} };
const recall = k => { try { return localStorage.getItem(k); } catch { return null; } };
const choice = c => CHOICES[c] ??= { best: 0, redraw: false, note: "" };

// "redraw": asked for, its pictures not drawn yet; once they are, the character is undecided again.
function state(item) {
  const label = CHOICES[item.character];
  if (label?.redraw) return Math.max(...item.takes) > (label.redrawFrom || 0) ? "undecided" : "redraw";
  return label?.best ? "chosen" : "undecided";
}
const inGroup = () => DATA.characters.filter(item => item.group === GROUP);
function rebuild() {
  LIST = inGroup().filter(item => FILTER === "all" || state(item) === FILTER);
}

function overlaySvg(detail) {
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", "0 0 1024 1024");
  const g = document.createElementNS(SVGNS, "g");
  g.setAttribute("transform", "translate(0 900) scale(1 -1)");
  for (const d of detail.outlines) {
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

let statusLine;
async function save(body) {
  statusLine.textContent = "Saving…";
  try {
    const response = await fetch("/choose", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(response.status);
    CHOICES[body.character] = await response.json();
    statusLine.textContent = "Saved";
  } catch (error) { statusLine.textContent = "Not saved — is the laptop awake? (" + error.message + ")"; }
  updateCounts();
}

function updateCounts() {
  const items = inGroup();
  const chosen = items.filter(i => state(i) === "chosen").length;
  const redraw = items.filter(i => state(i) === "redraw").length;
  document.getElementById("count").textContent = `${chosen} / ${items.length} chosen · ${redraw} redraw`;
  document.querySelectorAll("#strip button").forEach((b, i) => {
    const item = LIST[i];
    b.className = [state(item) === "chosen" ? "done" : state(item) === "redraw" ? "redraw" : "",
                   i === HERE ? "here" : ""].join(" ");
  });
  document.querySelectorAll("#groups button[data-group]").forEach(b => {
    const members = DATA.characters.filter(i => i.group === b.dataset.group);
    const left = members.filter(i => state(i) === "undecided").length;
    b.textContent = `${NAMES[b.dataset.group]} · ${left ? left + " to choose" : "done"}`;
  });
}

function drawControls() {
  const groups = document.getElementById("groups");
  groups.replaceChildren();
  for (const name of DATA.groups) {
    if (!DATA.characters.some(i => i.group === name)) continue;
    groups.append($("button", { "data-group": name, class: name === GROUP ? "on" : "",
      onclick: () => { GROUP = name; store("cp-group", name); rebuild(); drawControls(); go(0); } }));
  }
  groups.append($("span", { class: "sep" }));
  for (const [key, label] of [["all", "All"], ["undecided", "To choose"], ["redraw", "Redraw"], ["chosen", "Chosen"]]) {
    groups.append($("button", { class: key === FILTER ? "on" : "",
      onclick: () => { FILTER = key; store("cp-filter", key); rebuild(); drawControls(); go(0); } }, label));
  }
  const strip = document.getElementById("strip");
  strip.replaceChildren(...LIST.map((item, i) =>
    $("button", { lang: "zh", onclick: () => { go(i); document.getElementById("picker").open = false; } }, item.character)));
  document.getElementById("pickerLabel").textContent = `Characters (${LIST.length})`;
  updateCounts();
}

// ── the full-screen view ──
let zoomAt = 0;
const zoomBox = document.getElementById("zoom");
function zoom(at) { zoomAt = at; showZoom(); zoomBox.classList.add("open"); }
function showZoom() {
  const item = LIST[HERE], take = item.takes[zoomAt];
  const frame = zoomBox.querySelector(".frame");
  frame.querySelector("img").src = `/img/${DATA.stage}/${item.index}/${take}`;
  frame.querySelector("svg")?.remove();
  if (document.body.classList.contains("overlay") && DETAIL) frame.append(overlaySvg(DETAIL));
  zoomBox.querySelector(".label").textContent = `${item.character} · take ${take} (${zoomAt + 1} of ${item.takes.length})`;
  zoomBox.querySelector("[data-star]").classList.toggle("on", choice(item.character).best === take);
}
zoomBox.querySelectorAll("[data-step]").forEach(b => b.onclick = e => {
  e.stopPropagation();
  const n = LIST[HERE].takes.length;
  zoomAt = (zoomAt + Number(b.dataset.step) + n) % n; showZoom();
});
zoomBox.querySelector("[data-star]").onclick = e => {
  e.stopPropagation(); pick(LIST[HERE].takes[zoomAt]); showZoom();
};
zoomBox.querySelector("[data-close]").onclick = () => zoomBox.classList.remove("open");
zoomBox.querySelector("img").onclick = () => zoomBox.classList.remove("open");

let tiles = {};
function pick(take) {
  const c = LIST[HERE].character;
  const next = choice(c).best === take ? 0 : take;
  choice(c).best = next;
  for (const [t, tile] of Object.entries(tiles)) {
    tile.classList.toggle("best", Number(t) === next);
    tile.querySelector(".star").classList.toggle("on", Number(t) === next);
  }
  save({ character: c, best: next });
}

async function detail(item) {
  if (!cache.has(item.index)) cache.set(item.index, fetch(`/char/${item.index}`).then(r => r.json()));
  return cache.get(item.index);
}

async function render() {
  const page = document.getElementById("page");
  if (!LIST.length) {
    page.replaceChildren($("p", { class: "empty" }, "Nothing here: every character in this view is done, or none is drawn yet."));
    document.getElementById("where").textContent = NAMES[GROUP];
    updateCounts();
    return;
  }
  const item = LIST[HERE], c = item.character;
  document.getElementById("where").textContent = `${c}  ·  ${HERE + 1} of ${LIST.length}`;
  document.getElementById("prev").disabled = HERE === 0;
  document.getElementById("next").disabled = HERE === LIST.length - 1;
  DETAIL = await detail(item);
  if (LIST[HERE] !== item) return;  // moved on while it loaded
  page.replaceChildren();
  statusLine = $("div", { class: "saved" });
  const script = $("details", {}, $("summary", {}, "Stroke script and history"));
  const list = $("ol");
  DETAIL.lines.forEach((line, i) => list.append($("li", {},
    $("span", { class: "dot", style: `background:${DETAIL.colours[i]}` }), `${line.part} — `,
    $("span", { style: "color:var(--muted)" }, line.where))));
  script.append(list);
  if (DETAIL.history) script.append($("p", {}, DETAIL.history));
  page.append($("div", { class: "head" },
    $("div", { class: "glyph", lang: "zh" }, c),
    $("div", { class: "facts" },
      $("div", {}, DETAIL.object),
      $("div", { class: "def" }, DETAIL.definition),
      $("div", { class: "hint" }, `Source: ${DETAIL.type} — “${DETAIL.hint}”`)),
    $("img", { class: "ref", src: `/ref/${DATA.stage}/${item.index}`, alt: `${c}, its strokes` })), script);

  page.append($("h3", {}, "★ the best one — or none, and ask for a redraw"));
  const grid = $("div", { class: "grid" });
  tiles = {};
  const label = choice(c);
  item.takes.forEach((take, i) => {
    const star = $("button", { class: "star" + (label.best === take ? " on" : ""), "aria-label": `Best: take ${take}` }, "★");
    star.onclick = () => pick(take);
    const fresh = label.redrawFrom && take > label.redrawFrom;
    const tile = $("figure", { class: "tile" + (label.best === take ? " best" : "") },
      $("div", { class: "frame" },
        $("img", { src: `/img/${DATA.stage}/${item.index}/${take}`, alt: `${c}, take ${take}`, onclick: () => zoom(i) }),
        overlaySvg(DETAIL), $("span", { class: "take" + (fresh ? " new" : "") }, fresh ? `${take} new` : String(take)), star));
    tiles[take] = tile;
    grid.append(tile);
  });
  page.append(grid);

  const redraw = $("button", { class: "redraw" + (label.redraw ? " on" : ""), "aria-pressed": String(!!label.redraw) },
    "↻ None good — redraw");
  redraw.onclick = () => {
    label.redraw = !label.redraw;
    redraw.classList.toggle("on", label.redraw);
    redraw.setAttribute("aria-pressed", String(label.redraw));
    save({ character: c, redraw: label.redraw });
  };
  page.append($("div", { class: "choose-row" }, redraw,
    $("span", { class: "hint" }, "Four more takes are drawn; the ★ stays if you set one.")));
  const note = $("textarea", { placeholder: `What is wrong with ${c}'s pictures (optional)` });
  note.value = label.note || "";
  let timer;
  note.oninput = () => { clearTimeout(timer); timer = setTimeout(() => {
    label.note = note.value; save({ character: c, note: note.value }); }, 700); };
  const nextUndecided = () => {
    const at = LIST.findIndex((other, i) => i > HERE && state(other) === "undecided");
    go(at >= 0 ? at : HERE + 1);
  };
  page.append(note, statusLine, $("div", { class: "foot" },
    $("button", { onclick: () => go(HERE - 1), ...(HERE === 0 ? { disabled: "" } : {}) }, "‹ Previous"),
    $("span", { class: "grow" }),
    $("button", { onclick: nextUndecided }, "Next to choose ›"),
    $("button", { onclick: () => go(HERE + 1), ...(HERE === LIST.length - 1 ? { disabled: "" } : {}) }, "Next ›")));
  updateCounts();
  // The next character's pictures, fetched while this one is looked at.
  const ahead = LIST[HERE + 1];
  if (ahead) { detail(ahead); for (const take of ahead.takes) new Image().src = `/img/${DATA.stage}/${ahead.index}/${take}`; }
}

function go(index) {
  if (LIST.length && (index < 0 || index >= LIST.length)) return;
  HERE = Math.max(0, index);
  if (LIST[HERE]) { store("cp-at", LIST[HERE].character); history.replaceState(null, "", "#" + LIST[HERE].character); }
  render(); window.scrollTo(0, 0);
}
document.getElementById("prev").onclick = () => go(HERE - 1);
document.getElementById("next").onclick = () => go(HERE + 1);

const overlayButton = document.getElementById("overlay");
function setOverlay(on) {
  document.body.classList.toggle("overlay", on);
  overlayButton.classList.toggle("on", on);
  store("cp-overlay", on ? "1" : undefined);
}
overlayButton.onclick = () => setOverlay(!document.body.classList.contains("overlay"));
setOverlay(!!recall("cp-overlay"));

const sizeButton = document.getElementById("size");
function setColumns(n) {
  document.documentElement.style.setProperty("--columns", n);
  sizeButton.textContent = `▦ ${n}`;
  store("cp-columns", String(n));
}
sizeButton.onclick = () => {
  const now = Number(getComputedStyle(document.documentElement).getPropertyValue("--columns")) || 2;
  setColumns(now >= 4 ? 1 : now + 1);
};
setColumns(Number(recall("cp-columns")) || 2);

fetch("/data").then(r => r.json()).then(data => {
  DATA = data; CHOICES = data.choices || {};
  const wanted = decodeURIComponent(location.hash.slice(1)) || recall("cp-at");
  const found = DATA.characters.find(i => i.character === wanted);
  GROUP = found?.group || recall("cp-group") || DATA.characters[0]?.group || "g1";
  FILTER = found ? "all" : recall("cp-filter") || "all";
  rebuild(); drawControls();
  const at = found ? LIST.findIndex(i => i.character === found.character) : 0;
  go(at >= 0 ? at : 0);
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
    parser.add_argument("--choose", action="store_true",
                        help="the full run: choose the best picture or ask for a redraw; no scoring")
    args = parser.parse_args(argv)
    if args.choose:
        ChooseHandler.characters = choosable()
        ChooseHandler.by_index = {item["index"]: item for item in ChooseHandler.characters}
        drawn = sum(1 for item in ChooseHandler.characters if run.drawn_takes(item["character"]))
        print(f"{drawn} of {len(ChooseHandler.characters)} characters have pictures so far; "
              "reload the page to see new ones")
        handler: type[BaseHTTPRequestHandler] = ChooseHandler
    else:
        Handler.characters, Handler.key = build()
        drawn = sum(1 for item in Handler.characters for letter in item["letters"]
                    if (file := _picture(Handler.key, item["character"], letter)) and file.exists())
        print(f"{len(Handler.characters)} characters, {drawn} pictures drawn so far")
        handler = Handler
    print(f"open http://{args.host}:{args.port}/  — Ctrl-C to stop; every tap is saved")
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()

if __name__ == "__main__":
    main()
