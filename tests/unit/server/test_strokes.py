"""The stroke data the Write sheet draws and checks characters with (`docs/features/writing.md`)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PIN = ROOT / "deploy" / "acervo" / "strokes" / "pin.json"
DATASET = "hanzi-writer-data@2.0.1"
REN = {"strokes": ["M 1 1 L 2 2 Z", "M 3 3 L 4 4 Z"], "medians": [[[1, 1], [2, 2]], [[3, 3], [4, 4]]]}


@pytest.fixture
def held(server, tmp_path, monkeypatch):
    directory = tmp_path / "strokes"
    directory.mkdir()
    (directory / "dataset.json").write_text(json.dumps({"dataset": DATASET}))
    (directory / "人.json").write_text(json.dumps(REN), encoding="utf-8")
    (directory / "女.json").write_text(json.dumps({**REN, "radStrokes": [0, 1], "extra": True}), encoding="utf-8")
    monkeypatch.setattr(server.settings, "strokes_path", directory)
    return server


def activity_lines(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "acervo.activity"]


def test_it_answers_each_character_it_holds_with_its_strokes_and_medians(held):
    answer = held.get("/strokes", params={"characters": "人女"})
    assert answer.status_code == 200
    body = answer.json()["data"]
    assert body["dataset"] == DATASET
    assert body["characters"]["人"] == REN
    assert body["missing"] == []


def test_it_passes_the_radical_on_and_nothing_the_interface_does_not_draw_with(held):
    entry = held.get("/strokes", params={"characters": "女"}).json()["data"]["characters"]["女"]
    assert entry["radStrokes"] == [0, 1]
    assert "extra" not in entry


def test_a_character_it_does_not_hold_is_named_and_written_down(held, caplog):
    with caplog.at_level("WARNING", logger="acervo.activity"):
        body = held.get("/strokes", params={"characters": "人𠮷人"}).json()["data"]
    assert list(body["characters"]) == ["人"]
    assert body["missing"] == ["𠮷"]
    assert any("strokes missing" in line and "characters=𠮷" in line for line in activity_lines(caplog))


def test_a_server_built_without_the_dataset_says_so_and_writes_it_down(server, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(server.settings, "strokes_path", tmp_path / "nowhere")
    with caplog.at_level("WARNING", logger="acervo.activity"):
        answer = server.get("/strokes", params={"characters": "人"})
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "strokes_unavailable"
    assert "no stroke data" in answer.json()["error"]["message"]
    assert any("code=strokes_unavailable" in line for line in activity_lines(caplog))


@pytest.mark.parametrize("asked, code", [("", "characters_required"), ("人a", "not_chinese"),
                                         ("../x", "not_chinese")])
def test_it_refuses_what_is_not_a_list_of_chinese_characters(held, asked, code):
    answer = held.get("/strokes", params={"characters": asked})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == code


def test_a_batch_is_bounded(held):
    many = "".join(chr(0x4E00 + index) for index in range(201))
    answer = held.get("/strokes", params={"characters": many})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "too_many_characters"


def test_it_needs_a_session(held):
    assert held.client.get("/api/acervo/v1/strokes", params={"characters": "人"}).status_code == 401


# ── the fetcher the image and a laptop share ────────────────────────────────


def fetcher():
    spec = importlib.util.spec_from_file_location("strokes_fetch", PIN.parent / "fetch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_fetcher_writes_only_single_characters_and_the_licence(tmp_path):
    import tarfile

    module = fetcher()

    def member(name: str) -> tarfile.TarInfo:
        info = tarfile.TarInfo(name)
        info.type = tarfile.REGTYPE
        return info

    assert module.wanted(member("package/人.json"), "ARPHICPL.TXT") == "人.json"
    assert module.wanted(member("package/ARPHICPL.TXT"), "ARPHICPL.TXT") == "ARPHICPL.TXT"
    for name in ("package/package.json", "package/APL/gb/ARPHICPL.TXT", "package/../人.json", "other/人.json",
                 "package/a.json", "package/人人.json"):
        assert module.wanted(member(name), "ARPHICPL.TXT") is None, name


def test_the_fetcher_checks_a_directory_against_the_pin(tmp_path):
    module = fetcher()
    pin = json.loads(PIN.read_text())
    assert "no stroke data" in module.check(tmp_path, pin)
    (tmp_path / "dataset.json").write_text(json.dumps({"dataset": "hanzi-writer-data@1.0.0"}))
    assert "the pin names" in module.check(tmp_path, pin)
    (tmp_path / "dataset.json").write_text(json.dumps({"dataset": module.dataset_name(pin)}))
    assert module.check(tmp_path, pin) is None


def test_the_interface_expects_the_dataset_the_pin_names():
    """The device keys what it keeps by dataset, so a pin moved without the interface would leave
    every device asking for records it can never find under the name it uses."""
    pin = json.loads(PIN.read_text())
    store = (ROOT / "web" / "src" / "writing" / "strokeStore.ts").read_text(encoding="utf-8")
    assert f'export const STROKE_DATASET = "{pin["package"]}@{pin["version"]}";' in store
