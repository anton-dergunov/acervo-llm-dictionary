"""`GET /map/{language}` and `map.name`: a map drawn when it is asked for and its words changed,
kept beside the database, and named by a model afterwards."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from graph_records import lexeme, sense, vocabulary

from acervo.repository import jobs
from acervo.services import meaning
from acervo.work.runner import Runner


class FakeEncoder:
    """A vector from the text's digest: deterministic, and nothing like torch."""

    model = "fake-encoder"

    def __init__(self) -> None:
        self.encoded: list[str] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.encoded.extend(texts)
        rows = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
            row = np.random.default_rng(seed).normal(size=16)
            rows.append(row / np.linalg.norm(row))
        return np.array(rows, dtype=np.float32)


@pytest.fixture
def encoder():
    fake = FakeEncoder()
    meaning.use_encoder(fake)
    yield fake
    meaning.use_encoder(None)


def words(server, count: int, *, senses_each: int = 1, **lexeme_overrides) -> list[dict]:
    server.push({"vocabularies": [vocabulary()]})
    lexemes, senses = [], []
    for index in range(count):
        entry = lexeme(headword=f"palabra{index}", lemma=f"palabra{index}", status="active", **lexeme_overrides)
        lexemes.append(entry)
        for order in range(senses_each):
            senses.append(sense(entry["id"], order=order, definition=f"Definición {index}.{order}.",
                                glosses=[{"lang": "en", "terms": [f"word {index} {order}"]}]))
    assert server.push({"lexemes": lexemes, "senses": senses}).status_code == 200
    return senses


def held(server, key: str, record_id: str) -> dict:
    return next(r for r in server.pull().json()["data"]["changes"][key] if r["id"] == record_id)


def map_jobs(server) -> list[dict]:
    return [job for job in jobs.open_jobs(server.owner) if job["kind"] == "map.name"]


def test_a_map_is_drawn_once_and_then_read(server, encoder):
    words(server, 6, senses_each=2)
    first = server.get("/map/es")
    assert first.status_code == 200
    body = first.json()["data"]
    assert body["senses"] == 12 and body["words"] == 6 and len(body["points"]) == 12
    assert len(encoder.encoded) == 12
    again = server.get("/map/es").json()["data"]
    assert again["fingerprint"] == body["fingerprint"]
    assert len(encoder.encoded) == 12, "an unchanged vocabulary must not be embedded again"


def test_a_device_holding_the_current_map_is_told_so_and_sent_nothing(server, encoder):
    words(server, 4)
    held = server.get("/map/es").json()["data"]["version"]
    assert server.get(f"/map/es?have={held}").json()["data"] == {"current": True, "version": held}
    assert "points" in server.get("/map/es?have=something-older").json()["data"]


def test_a_map_whose_regions_were_named_since_is_not_current(server, encoder):
    """Naming changes the map and not its layout, so a device holding the unnamed map must be sent
    the named one — asking by fingerprint alone, it never was."""
    words(server, 80, senses_each=2)
    unnamed = server.get("/map/es").json()["data"]
    assert unnamed["version"].endswith(".pending")
    meaning.give_up_naming(server.settings, server.owner, "es", unnamed["fingerprint"])
    again = server.get(f"/map/es?have={unnamed['version']}").json()["data"]
    assert "points" in again and again["names"] == "none" and again["version"] != unnamed["version"]


def test_the_map_carries_positions_and_ids_but_no_vectors_and_no_sense_text(server, encoder):
    words(server, 4)
    body = server.get("/map/es").json()["data"]
    assert set(body["points"][0]) == {"sense", "lexeme", "x", "y", "r", "h", "rank", "nb"}
    assert "Definición" not in json.dumps(body)


def test_editing_what_a_sense_says_embeds_that_sense_alone(server, encoder):
    senses = words(server, 5)
    before = server.get("/map/es").json()["data"]["fingerprint"]
    record = held(server, "senses", senses[2]["id"])
    server.push({"senses": [{**record, "definition": "Una definición nueva."}]})
    encoder.encoded.clear()
    after = server.get("/map/es").json()["data"]
    assert after["fingerprint"] != before
    assert len(encoder.encoded) == 1 and "Una definición nueva." in encoder.encoded[0]


def test_an_edit_that_changes_nothing_embedded_changes_nothing(server, encoder):
    senses = words(server, 3)
    before = server.get("/map/es").json()["data"]["fingerprint"]
    record = held(server, "senses", senses[0]["id"])
    server.push({"senses": [{**record, "emoji": "\U0001F52A"}]})
    assert server.get("/map/es").json()["data"]["fingerprint"] == before


def test_a_deleted_sense_leaves_the_map(server, encoder):
    senses = words(server, 4)
    server.get("/map/es")
    record = held(server, "senses", senses[1]["id"])
    server.push({"senses": [{**record, "deleted": True}]})
    body = server.get("/map/es").json()["data"]
    assert senses[1]["id"] not in {p["sense"] for p in body["points"]} and body["senses"] == 3


def test_a_suppressed_word_is_not_on_the_map(server, encoder):
    words(server, 3)
    unwanted = lexeme(headword="no", lemma="no", status="suppressed")
    server.push({"lexemes": [unwanted], "senses": [sense(unwanted["id"])]})
    body = server.get("/map/es").json()["data"]
    assert unwanted["id"] not in {p["lexeme"] for p in body["points"]}


def test_a_language_with_no_vocabulary_has_no_map(server, encoder):
    words(server, 2)
    answer = server.get("/map/fr")
    assert answer.status_code == 404 and answer.json()["error"]["code"] == "unknown_language"


def test_a_small_map_has_no_regions_and_asks_for_no_names(server, encoder):
    words(server, 10)
    body = server.get("/map/es").json()["data"]
    assert body["regions"] == [] and body["names"] == "none"
    assert map_jobs(server) == []


def test_a_large_map_has_regions_and_asks_for_names_once(server, encoder):
    words(server, 80, senses_each=2)
    body = server.get("/map/es").json()["data"]
    assert body["names"] == "pending"
    assert {r["level"] for r in body["regions"]} == {"region", "hood"}
    assert all(r["labels"]["words"] for r in body["regions"])
    assert len(map_jobs(server)) == 1
    server.get("/map/es")
    assert len(map_jobs(server)) == 1, "reading an unchanged map must not ask for names again"


def test_the_naming_job_names_the_regions_it_was_asked_about(server, encoder):
    words(server, 80, senses_each=2)
    body = server.get("/map/es").json()["data"]
    for job in jobs.open_jobs(server.owner):
        if job["kind"] != "map.name":
            jobs.finish(job["id"], "cancelled")
    ids = [r["id"] for r in body["regions"]]
    server.model.text = json.dumps({**{one: f"lugar {one}" for one in ids}, "r99": "invented"})
    Runner(server.settings).run_until_idle()
    named = server.get("/map/es").json()["data"]
    assert named["names"] == "ready" and named["fingerprint"] == body["fingerprint"]
    assert {r["labels"]["name"] for r in named["regions"]} == {f"lugar {one}" for one in ids}
    asked = server.model.calls[-1]["messages"]
    assert "Write every name in Spanish." in asked[-1]["content"]
    assert "palabra" in asked[-1]["content"], "the model is shown the words, which the map itself does not carry"


def test_naming_a_map_that_has_been_redrawn_does_nothing(server, encoder):
    words(server, 80, senses_each=2)
    server.get("/map/es")
    calls = len(server.model.calls)
    assert meaning.name_regions(server.settings, server.owner, "es", "an-older-fingerprint") == "stale"
    assert len(server.model.calls) == calls


def test_a_naming_that_fails_for_good_stops_the_map_waiting(server, encoder):
    words(server, 80, senses_each=2)
    body = server.get("/map/es").json()["data"]
    meaning.give_up_naming(server.settings, server.owner, "es", body["fingerprint"])
    assert server.get("/map/es").json()["data"]["names"] == "none"


def test_a_new_layout_is_drawn_in_the_frame_of_the_last(server, encoder):
    words(server, 80, senses_each=2)
    first = {p["sense"]: (p["x"], p["y"]) for p in server.get("/map/es").json()["data"]["points"]}
    more = lexeme(headword="nueva", lemma="nueva", status="active")
    server.push({"lexemes": [more], "senses": [sense(more["id"], definition="Algo nuevo.")]})
    second = server.get("/map/es").json()["data"]
    shared = [p for p in second["points"] if p["sense"] in first]
    shift = np.median([np.hypot(p["x"] - first[p["sense"]][0], p["y"] - first[p["sense"]][1]) for p in shared])
    # The fake encoder's vectors are noise, so warm start and alignment have no real manifold to agree
    # on and this only checks the frame — a mirrored map moves about half its width (~500). Sampled
    # over 200 unrelated word sets, a correctly aligned noise map still moved as much as 338 of 1000;
    # `test_meaning.py` measures the warm start itself, on vectors with structure, far more tightly.
    assert shift < 400, f"the map moved {shift:.0f} of 1000 for one new word"


def test_the_export_for_the_discovery_experiment_is_every_sense_its_text_and_its_vector(server, encoder):
    senses = words(server, 3, senses_each=2)
    server.get("/map/es")
    encoder.encoded.clear()
    rows = meaning.vectors(server.settings, server.owner, "es")
    assert {row["sense"] for row in rows} == {s["id"] for s in senses}
    assert all(row["text"].startswith("palabra") and len(row["vector"]) == 16 for row in rows)
    assert encoder.encoded == [], "the export reads the cache the map filled"
