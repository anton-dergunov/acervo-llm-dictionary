"""The character-pictures full run: the account guard, one picture job at a time, progress lines.

The experiment's scripts import each other as top-level modules, so its directory goes on the path.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "character-pictures"))

import argon  # noqa: E402
import batch  # noqa: E402

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
ALLOWED = {"project": "allowed-project", "account": "learner@account.example.com", "profile": "blog", "cap": 295}


def _row(project: str = "allowed-project") -> SimpleNamespace:
    return SimpleNamespace(id="gcloud-test", setting=lambda name: project if name == "project" else None,
                           credential=SimpleNamespace(file={"type": "authorized_user", "client_id": "client"}))


@pytest.fixture
def allowed(monkeypatch):
    monkeypatch.setattr(batch, "billing", lambda: ALLOWED)
    monkeypatch.setenv("GCP_PROFILE", "blog")
    monkeypatch.setattr(batch, "_account_of", lambda info: ALLOWED["account"])
    monkeypatch.setattr(batch, "_tokeninfo", lambda token: {"azp": "client"})
    batch._verified.clear()


def _headers(project: str = "allowed-project", token: str = "t") -> dict[str, str]:
    return {"x-goog-user-project": project, "Authorization": f"Bearer {token}"}


def test_guard_accepts_only_the_billing_account(allowed, monkeypatch):
    batch.guard(_row(), _headers())  # the one account: no error

    with pytest.raises(batch.Stop, match="would bill project"):
        batch.guard(_row("other-project"), _headers("other-project"))
    with pytest.raises(batch.Stop, match="quota project"):
        batch.guard(_row(), _headers("other-project", "t2"))
    with pytest.raises(batch.Stop, match="key"):
        batch.guard(_row(), {"x-goog-api-key": "k"})
    monkeypatch.setenv("GCP_PROFILE", "personal")
    with pytest.raises(batch.Stop, match="profile"):
        batch.guard(_row(), _headers(token="t3"))
    monkeypatch.setenv("GCP_PROFILE", "blog")
    monkeypatch.setattr(batch, "_account_of", lambda info: "someone@else.example.com")
    with pytest.raises(batch.Stop, match="allows only"):
        batch.guard(_row(), _headers(token="t4"))


def _job(done: int, history: list[tuple[int, int]], submitted_minutes_ago: int, total: int = 250,
         state: str = "JOB_STATE_RUNNING") -> dict:
    return {"display": "character-pictures-g1-045-20261117t000000", "requests": [f"c/{i}" for i in range(total)],
            "done": done, "state": state,
            "submitted": (NOW - timedelta(minutes=submitted_minutes_ago)).isoformat(timespec="seconds"),
            "progress": [[(NOW - timedelta(minutes=ago)).isoformat(timespec="seconds"), count] for ago, count in history]}


def test_progress_line_gives_the_last_hour_and_the_age_of_the_last_picture():
    job = _job(118, [(300, 0), (90, 80), (30, 109), (6, 118)], 300)
    line = batch.job_progress(job, NOW)
    assert "g1-045" in line and "running 118/250" in line
    assert "+38 in the last hour" in line and "last picture 6 min ago" in line
    assert "STALLED" not in line


def test_a_job_with_no_new_picture_for_90_minutes_is_called_stalled():
    assert "STALLED?" in batch.job_progress(_job(40, [(400, 40)], 600), NOW)
    assert "STALLED?" in batch.job_progress(_job(0, [], 120), NOW)   # nothing since its submission
    assert "STALLED?" not in batch.job_progress(_job(0, [], 20), NOW)


def test_the_run_line_gives_pace_and_time_left():
    lines = batch.progress_lines([_job(120, [(120, 0), (5, 120)], 120)], drawn=1500, wanted=4470, now=NOW)
    assert len(lines) == 2
    assert "1,500 of 4,470 (33%)" in lines[1] and "60 an hour" in lines[1] and "about 47.5 h" in lines[1]
    assert "pace not known" in batch.progress_lines([_job(2, [(5, 2)], 10)], 10, 100, NOW)[1]


def test_submit_pictures_makes_at_most_max_jobs(monkeypatch):
    submitted: list[str] = []
    monkeypatch.setattr(batch, "allowance", lambda *a, **k: 1000.0)
    monkeypatch.setattr(batch, "_plan", lambda *a, **k: [("g1", f"c{i}/1") for i in range(5)])
    monkeypatch.setattr(batch, "bucket_for", lambda row: "bucket")
    monkeypatch.setattr(batch, "_list", lambda *a, **k: [])
    monkeypatch.setattr(batch, "save", lambda *a, **k: None)
    monkeypatch.setattr(batch, "submit", lambda row, job, prompts, known: submitted.append(job["display"]))
    state: dict = {"jobs": []}
    args = argparse.Namespace(job_size=2, cap=None)
    made = batch.submit_pictures(_row(), None, args, [], state, {}, max_jobs=1)
    assert len(made) == 1 and len(submitted) == 1 and len(made[0]["requests"]) == 2


def test_full_submits_no_picture_job_while_one_is_running(monkeypatch):
    calls: list[int] = []
    running = _job(10, [(5, 10)], 30)
    entry = {"character": "人", "group": "g1", "checked": True}
    monkeypatch.setattr(argon, "_account", lambda: (_row(), {}, {}))
    monkeypatch.setattr(argon, "load", lambda: {"tasks": {}, "jobs": []})
    monkeypatch.setattr(argon, "collect", lambda state, rows: [])
    monkeypatch.setattr(argon, "submit", lambda *a, **k: [])
    monkeypatch.setattr(argon, "targets", lambda *a, **k: [])
    monkeypatch.setattr(argon, "in_flight", lambda state: set())
    monkeypatch.setattr(argon, "_ledger", lambda row: "ledger")
    monkeypatch.setattr(argon.run, "prepare", lambda args: [entry])
    monkeypatch.setattr(argon.run, "prompts_for", lambda chosen: {})
    monkeypatch.setattr(argon.run, "drawn_pictures", lambda character: [])
    monkeypatch.setattr(argon.run, "catalogue", lambda: [entry])
    monkeypatch.setattr(argon.batch, "load", lambda: {"jobs": []})
    monkeypatch.setattr(argon.batch, "_collect", lambda state, rows: [running])
    monkeypatch.setattr(argon.batch, "submit_pictures", lambda *a, **k: calls.append(1) or [])
    argon.full(argparse.Namespace(takes=6, takes_for=None, dry_run=True, job_size=250, text_job_size=200, poll=0))
    assert calls == []

    monkeypatch.setattr(argon.batch, "_collect", lambda state, rows: [])
    argon.full(argparse.Namespace(takes=6, takes_for=None, dry_run=True, job_size=250, text_job_size=200, poll=0))
    assert calls, "with no picture job in flight the next one is planned"
