"""`acervo_worker.py loop render`, driven end to end against fakes.

It had no test, and so it shipped calling `LoopService.start` without `delivery` — a required
argument — and raised `TypeError` before it sent anything, on the one command a fresh deployment is
told to run first.
"""

from __future__ import annotations

import pytest

from acervo.loops import cli
from acervo.loops.client import Format, Loop, Operation, Schema


class FakeService:
    def __init__(self, url: str) -> None:
        self.started: dict = {}

    def schema(self) -> Schema:
        return Schema(api_version="2.0.0", engine_version="1.5.0", production_bundle=True,
                      bundle_version="3", formats=(Format("classic", "Classic drill", "…"),),
                      families=(), max_items=24)

    def start(self, **kwargs) -> Operation:
        self.started.update(kwargs)
        FakeService.last = self
        return self.operation("op")

    def operation(self, operation_id: str) -> Operation:
        result = Loop(audio_url="/audio", audio_mime="audio/mpeg", duration_seconds=10.0,
                      format="classic", fallback_from=None, style_id="meditative", seed=7,
                      engine_version="1.5.0", bed_fingerprint="0" * 16, bpm=80.0, items=(),
                      cues=())
        return Operation(id=operation_id, status="completed", successful=True, fraction=1.0,
                         message="Loop ready", error=None, result=result)

    def track(self, url: str) -> tuple[bytes, str]:
        return b"ID3" + bytes(100), "audio/mpeg"


class FakeClient:
    def __init__(self, url: str) -> None:
        pass

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *exc) -> None:
        pass

    def sign_in(self, email: str, password: str) -> str:
        return "session-token"

    def pull_graph(self) -> dict:
        return {"changes": {"lexemes": [
            {"id": "a" * 15, "language": "es", "headword": "asco", "primaryGloss": "disgust",
             "emotion": "repulsed", "deleted": False},
        ]}}


@pytest.mark.parametrize("given, sent", [([], "plain"), (["--delivery", "directed"], "directed")])
def test_a_render_by_hand_says_how_it_will_be_spoken(monkeypatch, capsys, given, sent) -> None:
    monkeypatch.setattr(cli, "LoopService", FakeService)
    monkeypatch.setattr(cli, "AcervoClient", FakeClient)
    monkeypatch.setenv("ACERVO_PASSWORD", "x")
    assert cli.main(["render", "--owner-email", "learner@account.example.com", *given]) == 0
    assert FakeService.last.started["delivery"] == sent
    assert "bundle v3, complete" in capsys.readouterr().out
