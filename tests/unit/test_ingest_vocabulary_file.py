"""The notes-file walk, against a stubbed server that speaks `/captures` and `/jobs`.

The server does the work now (`docs/architecture/jobs.md`). What is left to pin here is the
transport: what each submission carries, how far a checkpoint advances on the server's word, and
that nothing in the script paces or retries.
"""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "ingest_vocabulary_file", REPO_ROOT / "scripts" / "ingest_vocabulary_file.py"
)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


NOTES = """inquisitive - любознательный
Inquisitive about coffee? - Хотите узнать больше о кофе?

---

turmoil - суматоха
Since then I have been navigating the job market.

Toil - тяжёлый труд
Consonant - согласный
"""
LINES = len(NOTES.splitlines())


def saved(headword: str, lines: int) -> dict:
    return {"outcome": "saved", "headword": headword, "lines": lines, "lexemeId": "a" * 15}


def finished(consumed: int, *words: dict, state: str = "done", **extra) -> list[dict]:
    """What `GET /jobs/{id}` answers: once still running, then finished."""
    step = {"name": "capture", "state": "done" if state == "done" else "failed",
            "detail": {"consumedLines": consumed, "words": list(words)}}
    running = {"state": "running", "steps": [{**step, "state": "running",
                                              "detail": {"consumedLines": 0, "words": []}}]}
    return [running, {"state": state, "steps": [step], "error": None, "message": None, **extra}]


class Stub:
    """Stands in for the server: one scripted job per submission, and proposals for a dry run."""

    def __init__(self, *jobs: list[dict], proposals: list[dict] | None = None) -> None:
        self.jobs = list(jobs)
        self.proposals = proposals or []
        self.submissions: list[dict] = []
        self.captures: list[dict] = []
        self.polls = 0
        self.current: list[dict] = []

    def post(self, path: str, payload: dict) -> tuple[dict, int]:
        if path.endswith("/session"):
            return {"data": {"token": "t", "user": {"id": "o", "email": "e"}}}, 200
        if path.endswith("/captures"):
            self.submissions.append(payload)
            self.current = self.jobs.pop(0)
            return {"data": {"id": f"job{len(self.submissions):012d}", "state": "queued"}}, 202
        if path.endswith("/capture"):
            self.captures.append(payload)
            return {"data": self.proposals.pop(0)}, 200
        return {"error": {"code": "not_found", "message": path}}, 404

    def get(self, path: str) -> tuple[dict, int]:
        if "/graph" in path:
            return {"data": {"changes": {"vocabularies": [
                {"id": "vocaben00000001", "language": "en", "displayName": "English", "deleted": False},
                {"id": "vocabstarter001", "language": "en", "displayName": "English · Everyday words", "deleted": False},
            ]}}}, 200
        self.polls += 1
        answer = self.current.pop(0) if len(self.current) > 1 else self.current[0]
        return {"data": answer}, 200


@pytest.fixture
def server(monkeypatch):
    holder: dict = {}
    monkeypatch.setattr(ingest, "POLL_SECONDS", 0)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):  # noqa: N802 - silence the default access log
            pass

        def reply(self, body: dict, status: int) -> None:
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
            length = int(self.headers.get("Content-Length", 0))
            self.reply(*holder["stub"].post(self.path, json.loads(self.rfile.read(length) or b"{}")))

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
            self.reply(*holder["stub"].get(self.path))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    holder["url"] = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield holder
    httpd.shutdown()


def run(server, source: Path, checkpoints: Path, monkeypatch, *extra: str) -> int:
    monkeypatch.setenv("ACERVO_PASSWORD", "secret")
    monkeypatch.setattr("sys.argv", [
        "ingest_vocabulary_file.py", str(source),
        "--server-url", server["url"], "--owner-email", "learner@account.example.com",
        "--checkpoint-dir", str(checkpoints), *extra,
    ])
    return ingest.main()


@pytest.fixture
def notes(tmp_path) -> Path:
    source = tmp_path / "English vocabulary.md"
    source.write_text(NOTES, encoding="utf-8")
    return source


def test_names_the_vocabulary_the_words_go_in_by_its_name(server, notes, tmp_path, monkeypatch, capsys):
    server["stub"] = Stub(finished(LINES, saved("inquisitive", 2)))
    assert run(server, notes, tmp_path / "state", monkeypatch, "--vocabulary", "english · everyday words") == 0
    assert server["stub"].submissions[0]["vocabulary"] == "vocabstarter001"

    server["stub"] = Stub()
    assert run(server, notes, tmp_path / "other", monkeypatch, "--vocabulary", "Inglés") == 2
    assert "You have no vocabulary called Inglés (you have: English, English · Everyday words)" in capsys.readouterr().err


def test_says_how_to_name_the_vocabulary_when_the_server_could_not_choose(server, notes, tmp_path, monkeypatch, capsys):
    server["stub"] = Stub(finished(0, state="failed", error="vocabulary_ambiguous",
                                   message="This looks like en, and you keep 2 vocabularies in it (English, English · Everyday words). Choose which one it goes in."))
    assert run(server, notes, tmp_path / "state", monkeypatch) == 1
    err = capsys.readouterr().err
    assert "(English, English · Everyday words)" in err and "--vocabulary NAME" in err


def test_submits_the_file_and_follows_the_job_without_touching_the_notes(server, notes, tmp_path, monkeypatch, capsys):
    server["stub"] = Stub(finished(
        LINES, saved("inquisitive", 2), saved("turmoil", 2), saved("toil", 1), saved("consonant", 1)
    ))

    assert run(server, notes, tmp_path / "state", monkeypatch) == 0

    assert notes.read_text(encoding="utf-8") == NOTES
    [request] = server["stub"].submissions
    assert request["text"] == "\n".join(NOTES.splitlines())
    assert (request["mode"], request["window"], request["complete"]) == ("stream", 40, True)
    output = capsys.readouterr().out
    assert "✓ inquisitive" in output and "✓ consonant" in output
    assert "4 created" in output
    # The job was followed rather than assumed finished.
    assert server["stub"].polls >= 2


def test_the_file_goes_in_chunks_and_each_starts_where_the_server_stopped(server, notes, tmp_path, monkeypatch):
    server["stub"] = Stub(
        # The first chunk ends mid-entry, so the server leaves its tail for the next submission.
        finished(5, saved("inquisitive", 2)),
        finished(LINES - 5, saved("turmoil", 2), saved("toil", 1), saved("consonant", 1)),
    )

    assert run(server, notes, tmp_path / "state", monkeypatch, "--chunk-lines", "6", "--window-lines", "3") == 0

    first, second = server["stub"].submissions
    assert first["complete"] is False
    assert len(first["text"].split("\n")) == 6
    assert second["text"].startswith("turmoil")
    assert second["complete"] is True


def test_resumes_from_the_checkpoint_rather_than_starting_again(server, notes, tmp_path, monkeypatch, capsys):
    checkpoints = tmp_path / "state"
    server["stub"] = Stub(finished(2, saved("inquisitive", 2)))
    assert run(server, notes, checkpoints, monkeypatch, "--limit", "1") == 0
    assert server["stub"].submissions[0]["limit"] == 1

    server["stub"] = Stub(finished(3, saved("turmoil", 2)))
    assert run(server, notes, checkpoints, monkeypatch, "--limit", "1") == 0
    # Two lines in: the blank and the rule after `inquisitive` are the server's to skip.
    assert server["stub"].submissions[0]["text"].split("\n")[:2] == ["", "---"]

    # And --restart deliberately ignores what was already done.
    server["stub"] = Stub(finished(2, saved("inquisitive", 2)))
    assert run(server, notes, checkpoints, monkeypatch, "--limit", "1", "--restart") == 0
    assert server["stub"].submissions[0]["text"].startswith("inquisitive")


def test_consume_cuts_what_the_server_finished_out_of_the_file(server, notes, tmp_path, monkeypatch):
    server["stub"] = Stub(finished(7, saved("inquisitive", 2), saved("turmoil", 2)))

    assert run(server, notes, tmp_path / "state", monkeypatch, "--consume", "--limit", "2") == 0

    remaining = notes.read_text(encoding="utf-8")
    assert "inquisitive" not in remaining and "turmoil" not in remaining
    assert remaining.strip().startswith("Toil")
    # The original is recoverable, which is what makes cutting safe to offer at all.
    assert "inquisitive" in notes.with_suffix(".md.bak").read_text(encoding="utf-8")


def test_duplicates_and_unreadable_blocks_are_reported(server, notes, tmp_path, monkeypatch, capsys):
    server["stub"] = Stub(finished(
        LINES,
        {"outcome": "duplicate", "headword": "inquisitive", "lines": 2, "existing": ["inquisitive"]},
        {"outcome": "failed", "error": "unreadable_input", "message": "Not a word.", "lines": 2},
        saved("toil", 1), saved("consonant", 1),
    ))
    assert run(server, notes, tmp_path / "state", monkeypatch) == 0
    output = capsys.readouterr().out
    assert "already in your vocabulary" in output
    assert "✗ Not a word." in output
    assert "2 created, 1 already known, 1 skipped" in output


def test_a_failed_job_stops_the_run_and_keeps_only_what_the_server_finished(server, notes, tmp_path, monkeypatch, capsys):
    checkpoints = tmp_path / "state"
    server["stub"] = Stub(finished(
        2, saved("inquisitive", 2), state="failed",
        error="language_not_configured", message="The account has no en vocabulary.",
    ))

    assert run(server, notes, checkpoints, monkeypatch) == 1
    assert "no en vocabulary" in capsys.readouterr().err
    assert ingest.read_offset(ingest.checkpoint_path(checkpoints, notes), notes) == 2


def test_nothing_in_the_script_paces_or_retries(server, notes, tmp_path, monkeypatch, capsys):
    """The server waits out a busy provider; the script only follows."""
    busy = {"state": "queued", "notBefore": "2026-09-17T12:00:00.000Z",
            "steps": [{"name": "capture", "state": "waiting", "detail": {"words": []}}]}
    server["stub"] = Stub([busy, *finished(LINES, saved("inquisitive", 2))])

    assert run(server, notes, tmp_path / "state", monkeypatch) == 0
    assert len(server["stub"].submissions) == 1
    assert "the provider is busy" in capsys.readouterr().out
    source = (REPO_ROOT / "scripts" / "ingest_vocabulary_file.py").read_text(encoding="utf-8")
    assert "Pace" not in source and "RETRY" not in source


def test_checkpoints_are_specific_to_the_resolved_source_path(server, tmp_path, monkeypatch, capsys):
    first = tmp_path / "one" / "notes.md"
    second = tmp_path / "two" / "notes.md"
    for source in (first, second):
        source.parent.mkdir()
        source.write_text(NOTES, encoding="utf-8")
    checkpoints = tmp_path / "state"

    for source in (first, second):
        server["stub"] = Stub(finished(2, saved("inquisitive", 2)))
        assert run(server, source, checkpoints, monkeypatch, "--limit", "1") == 0
    assert len(list(checkpoints.glob("notes.md.*.json"))) == 2


def test_the_topic_and_language_are_passed_through_for_the_server_to_check(server, notes, tmp_path, monkeypatch):
    server["stub"] = Stub(finished(LINES))
    assert run(server, notes, tmp_path / "state", monkeypatch, "--topic", "Slang", "--language", "en") == 0
    request = server["stub"].submissions[0]
    # Files already filed under a heading know their own topic better than the model can infer it.
    assert request["topics"] == ["Slang"]
    assert request["language"] == "en"


def test_a_dry_run_proposes_creates_nothing_and_leaves_no_checkpoint(server, notes, tmp_path, monkeypatch, capsys):
    checkpoints = tmp_path / "state"
    server["stub"] = Stub(proposals=[{
        "resolution": {"headword": "inquisitive", "consumedLines": 2},
        "duplicates": [], "draft": {"headword": "inquisitive", "senses": [{}]},
    }])

    assert run(server, notes, checkpoints, monkeypatch, "--dry-run", "--limit", "1") == 0
    assert not checkpoints.exists()
    assert server["stub"].submissions == []
    assert "not created" in capsys.readouterr().out


def test_a_chunk_never_carries_more_text_than_the_server_accepts():
    lines = ["x" * 3000] * 20
    chunk = ingest.chunk_of(lines, 0, 20)
    assert len("\n".join(chunk)) <= ingest.TEXT_LIMIT
    assert chunk
