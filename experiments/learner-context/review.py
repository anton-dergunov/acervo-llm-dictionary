#!/usr/bin/env python3
"""The blind review page: one sentence at a time, labelled as you tap, saved on every tap.

    .venv/bin/python experiments/learner-context/review.py serve runs/review \
        --from runs/first:none --from runs/third:light --host "$(tailscale ip -4)" --port 8766
    .venv/bin/python experiments/learner-context/review.py score runs/review

Standard library only. On first start a sample is drawn with a fixed seed — examples written for
*unrelated* words and parts of *unrelated* stories, in equal numbers from each `--from` source (a run
and one of its arms) — shuffled, and written to `review-key.json` in the review directory. The page shows only the learner's note, the word and
the sentence: never the arm, and an item's id is a digest, so nothing on screen or in the address bar
gives it away. Each tap goes to `labels.json` at once, so closing the tab loses nothing.
`score` unblinds the labels: the share a person called "about the note" per source, and how well the
keyword measure in `score.py` agrees with them (Cohen's κ), which is what says whether its numbers
can be trusted.

Two questions per sentence:

- **About the note?** Would you say this sentence was written *because* of what the learner said
  about themselves — the trip, Argentina, software; or work, email, football?
- **Slang where it does not belong?** Spanish only: a regional or colloquial form the word's entry
  had no need for.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

from score import examples_of, hand_labels, leaks, records

HERE = Path(__file__).resolve().parent
SEED = 20261104
EXAMPLES_PER_SOURCE = 30
PARTS_PER_SOURCE = 8

_lock = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sample(review: Path, sources: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The items in the order shown, and the key that unblinds them. Drawn once, then kept."""
    key_path = review / "review-key.json"
    data = yaml.safe_load((HERE / "words.yaml").read_text(encoding="utf-8"))
    if key_path.exists():
        key = _read(key_path, {})
        return [{"id": item_id, **{k: v for k, v in item.items() if k in ("note", "word", "text", "translation", "spanish")}}
                for item_id, item in sorted(key.items(), key=lambda pair: pair[1]["order"])], key
    if not sources:
        raise SystemExit("The first start needs at least one --from run:arm to draw the sample from.")

    pool: dict[tuple[str, str], list[dict[str, Any]]] = {}
    labels_of = []
    for source in sources:
        path, _, arm = source.partition(":")
        run = Path(path) if Path(path).is_absolute() or Path(path).exists() else HERE / path
        labels_of.append(f"{run.name}/{arm}")
        for record in records(run):
            if record["arm"] == arm:
                record["source"] = f"{run.name}/{arm}"
                pool_record(pool, record, data)
    chooser = random.Random(SEED)
    chosen: list[dict[str, Any]] = []
    for source in labels_of:
        for kind, wanted in (("example", EXAMPLES_PER_SOURCE), ("part", PARTS_PER_SOURCE)):
            items = pool.get((source, kind), [])
            chosen += chooser.sample(items, min(wanted, len(items)))
    chooser.shuffle(chosen)
    key = {}
    for order, item in enumerate(chosen):
        item_id = hashlib.sha256(f"{SEED}:{order}:{item['text']}".encode()).hexdigest()[:12]
        key[item_id] = item | {"order": order}
    review.mkdir(parents=True, exist_ok=True)
    _write(key_path, key)
    return sample(review, [])


def pool_record(pool: dict[tuple[str, str], list[dict[str, Any]]], record: dict[str, Any], data: dict[str, Any]) -> None:
    """The sentences one reply offers the sample: its examples, or its story's parts."""
    if not (record.get("ok") and isinstance(record.get("reply"), dict)) or record["group"] != "unrelated":
        return
    vocabulary = data["vocabularies"][record["language"]]
    base = {"arm": record["source"], "language": record["language"], "note": vocabulary["learnerNote"],
            "spanish": record["language"] == "es"}
    if record["kind"] == "entry":
        for example in examples_of(record["reply"]):
            pool.setdefault((record["source"], "example"), []).append(base | {
                "word": record["headword"], "text": example["text"], "translation": example.get("translation") or "",
                "keyword": leaks(f"{example['text']} {example.get('translation') or ''}", vocabulary["leak"])})
    else:
        for part in record["reply"].get("parts") or []:
            if isinstance(part, dict) and part.get("text"):
                pool.setdefault((record["source"], "part"), []).append(base | {
                    "word": "a story with " + ", ".join(record["headwords"]), "text": part["text"],
                    "translation": "", "keyword": leaks(part["text"], vocabulary["leak"])})


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Learner context review</title>
<style>
 body{font:17px/1.5 system-ui,sans-serif;margin:0;background:#f4f1ea;color:#1d2a26}
 main{max-width:720px;margin:0 auto;padding:20px 16px 80px}
 .note{font-size:14px;color:#566;background:#fff;border-radius:10px;padding:10px 14px}
 .item{background:#fff;border-radius:12px;padding:16px;margin:22px 0}
 .word{font-size:13px;color:#788;text-transform:uppercase;letter-spacing:.06em}
 .text{font-size:20px;margin:6px 0}.tr{color:#566}
 .q{display:flex;align-items:center;gap:8px;margin-top:12px;flex-wrap:wrap}
 .q span{flex:1 1 220px;font-size:15px}
 button{font:inherit;font-size:15px;padding:8px 16px;border-radius:8px;border:1px solid #bcc;background:#fff}
 button.on{background:#0f6e5f;color:#fff;border-color:#0f6e5f}
 .count{position:fixed;bottom:0;left:0;right:0;background:#1d2a26;color:#fff;text-align:center;padding:8px}
</style>
<main id="list"></main><div class="count" id="count"></div>
<script>
const ITEMS = __ITEMS__; const LABELS = __LABELS__;
function save(id, field, value) {
  LABELS[id] = {...(LABELS[id] || {}), [field]: value};
  fetch("/label", {method: "POST", body: JSON.stringify({id, field, value})});
  draw();
}
function choice(id, field, value, text) {
  const on = (LABELS[id] || {})[field] === value;
  return `<button class="${on ? "on" : ""}" onclick='save("${id}","${field}",${JSON.stringify(value)})'>${text}</button>`;
}
function esc(t) { return String(t).replace(/[&<>]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;"})[c]); }
function draw() {
  const done = ITEMS.filter((i) => (LABELS[i.id] || {}).about !== undefined).length;
  document.getElementById("count").textContent = `${done} of ${ITEMS.length} labelled`;
  document.getElementById("list").innerHTML = ITEMS.map((i) => `<section class="item">
    <div class="note">The learner wrote: ${esc(i.note)}</div>
    <div class="word" style="margin-top:12px">${esc(i.word)}</div>
    <div class="text">${esc(i.text)}</div><div class="tr">${esc(i.translation)}</div>
    <div class="q"><span>Written because of what the learner said about themselves?</span>
      ${choice(i.id, "about", true, "Yes")}${choice(i.id, "about", false, "No")}</div>
    ${i.spanish ? `<div class="q"><span>Regional or slang form the word did not need?</span>
      ${choice(i.id, "slang", true, "Yes")}${choice(i.id, "slang", false, "No")}</div>` : ""}
  </section>`).join("");
}
draw();
</script></html>"""


def serve(review: Path, sources: list[str], host: str, port: int) -> None:
    items, _ = sample(review, sources)
    labels_path = review / "labels.json"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/":
                self._send(HTTPStatus.NOT_FOUND, b"", "text/plain")
                return
            page = PAGE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False)) \
                       .replace("__LABELS__", json.dumps(_read(labels_path, {}), ensure_ascii=False))
            self._send(HTTPStatus.OK, page.encode(), "text/html; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/label":
                self._send(HTTPStatus.NOT_FOUND, b"", "text/plain")
                return
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if body.get("field") not in ("about", "slang") or not any(item["id"] == body.get("id") for item in items):
                self._send(HTTPStatus.BAD_REQUEST, b"", "text/plain")
                return
            with _lock:
                labels = _read(labels_path, {})
                labels.setdefault(body["id"], {})[body["field"]] = bool(body["value"])
                _write(labels_path, labels)
            self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")

    print(f"{len(items)} sentences. Open http://{host}:{port}/  (labels go to {labels_path})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("serve", "score"))
    parser.add_argument("review", help="the directory the sample, key and labels are kept in")
    parser.add_argument("--from", dest="sources", action="append", default=[], help="run:arm to sample")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    review = Path(args.review)
    review = review if review.is_absolute() or review.exists() else HERE / args.review
    if args.action == "serve":
        serve(review, args.sources, args.host, args.port)
        return
    result = hand_labels(_read(review / "labels.json", {}), _read(review / "review-key.json", {}))
    _write(review / "hand-labels.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
