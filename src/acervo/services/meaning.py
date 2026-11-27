"""The meaning map's binding layer: the graph in, a stored map out, and its regions named later.

`acervo.meaning` knows how to draw a map and nothing about whose. This module reads the owner's
senses, keeps the embedding cache and the drawn map beside the database (`Settings.maps_path`), and
says on the wire what a missing vocabulary is called. A map is of one vocabulary, by id: two of one
language are two maps.

**A map is computed when it is asked for and its input has changed**, never on a timer and never as a
job. It is local CPU for seconds — no model call, no allowance to wait on — and the job runner does
one thing at a time, so a map queued behind an import's enrichment would be an hour out of date. The
one slow draw is the first, when every sense of a vocabulary is embedded; after that only the senses
whose words changed are. One lock per owner and vocabulary keeps two devices from drawing the same map.

**Names come after, from a job**, because they are a model call: the map is stored with the words
nearest each region's centre as its labels and `names: "pending"`, and `map.name` fills the names in
when it runs. A name job for a layout that has since been replaced does nothing — the newer layout
asked for its own.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import numpy as np

from acervo.errors import ApiError
from acervo.meaning import artifact, names
from acervo.meaning.artifact import MapSense
from acervo.meaning.cache import EmbeddingCache
from acervo.meaning.encoder import Encoder, SentenceEncoder, load_pin
from acervo.meaning.text import digest, gloss_terms
from acervo.repository import graph
from acervo.services.models import llm_json
from acervo.services.prompts import prompt_text
from acervo.settings import Settings

NAMES_PROMPT = "acervo_map_names"
# How many members of each region the naming call sees, most central first: enough to name a place,
# few enough that thirty-eight groups stay one request.
NAMED_FROM = 25

_encoder: Encoder | None = None
_encoder_lock = threading.Lock()
_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def encoder() -> Encoder:
    global _encoder
    with _encoder_lock:
        if _encoder is None:
            _encoder = SentenceEncoder(load_pin())
        return _encoder


def use_encoder(replacement: Encoder | None) -> None:
    """Swap the encoder — for tests, which must not load torch — or reset it with `None`."""
    global _encoder
    with _encoder_lock:
        _encoder = replacement


def _lock(owner: str, vocabulary: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault((owner, vocabulary), threading.Lock())


def _map_path(settings: Settings, owner: str, vocabulary: str) -> Path:
    return Path(settings.maps_path) / "artifacts" / owner / f"{vocabulary}.json"


def _cache(settings: Settings, model: str) -> EmbeddingCache:
    return EmbeddingCache(Path(settings.maps_path) / "embeddings" / re.sub(r"[^A-Za-z0-9._-]+", "-", model))


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.part")
    partial.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, path)


def _vocabulary(owner: str, vocabulary_id: str) -> dict[str, Any]:
    for vocabulary in graph.owner_vocabularies(owner):
        if vocabulary["id"] == vocabulary_id:
            return vocabulary
    raise ApiError(404, "unknown_vocabulary", "That vocabulary is not one of yours, so there is no map of it.",
                   noted={"vocabulary": vocabulary_id})


def _senses(owner: str, vocabulary: str) -> list[MapSense]:
    return [
        MapSense(sense=row["sense"], lexeme=row["lexeme"], headword=row["headword"], pos=row["pos"] or "",
                 definition=row["definition"] or "", glosses=tuple(row["glosses"]))
        for row in graph.map_senses(owner, vocabulary)
    ]


def _embed(settings: Settings, model: Encoder, senses: list[MapSense], keys: list[str]) -> np.ndarray:
    """Unit vectors for every sense, encoding only what the cache has not seen."""
    cache = _cache(settings, model.model)
    found = [cache.find(key) for key in keys]
    missing = [i for i, vector in enumerate(found) if vector is None]
    if missing:
        fresh = model.encode([senses[i].text for i in missing])
        for i, vector in zip(missing, fresh):
            cache.store(keys[i], vector)
            found[i] = vector
    if not found:
        return np.zeros((0, 1), dtype=np.float32)
    matrix = np.stack([np.asarray(vector, dtype=np.float32) for vector in found])
    return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)


def version(body: dict[str, Any]) -> str:
    """What a device holds, as far as currency goes: the layout's fingerprint **and** whether its
    regions are named. Naming changes the map without changing the layout, so a device asking about
    the fingerprint alone would be told its unnamed map was current and never see the names."""
    return f"{body['fingerprint']}.{body.get('names', 'none')}"


def _answer(body: dict[str, Any], have: str | None) -> dict[str, Any]:
    if have and have == version(body):
        return {"current": True, "version": version(body)}
    return {**body, "version": version(body)}


def current_map(settings: Settings, owner: str, vocabulary_id: str, *,
                have: str | None = None) -> tuple[dict[str, Any], bool]:
    """This vocabulary's map as it stands now, and whether it was drawn by this call.

    `have` is the `version` a device already holds; when it is still current the answer says so and
    carries nothing else.
    """
    vocabulary = _vocabulary(owner, vocabulary_id)
    language = vocabulary["language"]
    senses = _senses(owner, vocabulary_id)
    model = encoder()
    keys = [digest(model.model, sense.text) for sense in senses]
    wanted = artifact.fingerprint(model.model, [(sense.sense, key) for sense, key in zip(senses, keys)])
    path = _map_path(settings, owner, vocabulary_id)
    stored = _read(path)
    if stored and stored.get("fingerprint") == wanted:
        return _answer(stored, have), False
    with _lock(owner, vocabulary_id):
        stored = _read(path)
        if stored and stored.get("fingerprint") == wanted:
            return _answer(stored, have), False
        vectors = _embed(settings, model, senses, keys)
        previous = {p["sense"]: (p["x"], p["y"]) for p in stored["points"]} if stored else None
        body = artifact.build(senses, vectors, previous=previous,
                              definition_lang=vocabulary.get("definitionLang") or language)
        body.update(language=language, model=model.model, fingerprint=wanted,
                    names="pending" if body["regions"] else "none")
        _write(path, body)
    return _answer(body, have), True


def _members(stored: dict[str, Any], owner: str, vocabulary: str, gloss_lang: str | None) -> dict[str, list[str]]:
    """Each region's senses as `headword — gloss`, most central first."""
    rows = {row["sense"]: row for row in graph.map_senses(owner, vocabulary)}

    def line(sense: str) -> str | None:
        row = rows.get(sense)
        if row is None:
            return None
        preferred = [g for g in row["glosses"] if g.get("lang") == gloss_lang] or row["glosses"]
        gloss = "; ".join(gloss_terms(preferred[:1])) or row["definition"]
        return f"{row['headword']} — {gloss}"

    out: dict[str, list[str]] = {}
    for region in stored["regions"]:
        key = "r" if region["level"] == "region" else "h"
        inside = [p for p in stored["points"] if p[key] == region["index"]]
        inside.sort(key=lambda p: -p["rank"])
        out[region["id"]] = [text for text in (line(p["sense"]) for p in inside[:NAMED_FROM]) if text]
    return out


def name_regions(settings: Settings, owner: str, vocabulary_id: str, wanted: str) -> str:
    """Ask a model to name the regions of the map drawn with fingerprint `wanted`.

    Returns `stale` when that map has been replaced, `nothing` when it has no regions, and `named`.
    The owner's standing rules are not appended: like resolve, this only labels, and a rule about how
    notes are written has no business deciding what a region is called.
    """
    path = _map_path(settings, owner, vocabulary_id)
    stored = _read(path)
    if not stored or stored.get("fingerprint") != wanted:
        return "stale"
    if not stored.get("regions"):
        return "nothing"
    vocabulary = _vocabulary(owner, vocabulary_id)
    definition_lang = vocabulary.get("definitionLang") or vocabulary["language"]
    named_in = next((v.get("displayName") for v in graph.owner_vocabularies(owner)
                     if v["language"] == definition_lang and v.get("displayName")), definition_lang)
    members = _members(stored, owner, vocabulary_id, (vocabulary.get("glossLangs") or [None])[0])
    user = f"Write every name in {named_in}.\n\n{names.groups(stored['regions'], members)}"
    reply, _ = llm_json(settings, owner, prompt_text(settings.prompts_path, NAMES_PROMPT), user,
                        caller="map_names")
    named = names.parse_reply(reply, [region["id"] for region in stored["regions"]])
    with _lock(owner, vocabulary_id):
        current = _read(path)
        if not current or current.get("fingerprint") != wanted:
            return "stale"
        for region in current["regions"]:
            if region["id"] in named:
                region["labels"]["name"] = named[region["id"]]
        current["names"] = "ready" if named else "none"
        _write(path, current)
    return "named"


def give_up_naming(settings: Settings, owner: str, vocabulary: str, wanted: str) -> None:
    """A naming that failed for good leaves the map with its central words, and says so, so a device
    stops waiting for names that are not coming."""
    path = _map_path(settings, owner, vocabulary)
    with _lock(owner, vocabulary):
        current = _read(path)
        if current and current.get("fingerprint") == wanted and current.get("names") == "pending":
            current["names"] = "none"
            _write(path, current)


def stored_map(settings: Settings, owner: str, vocabulary: str) -> dict[str, Any] | None:
    """The map as last drawn, without drawing — for `admin map show`."""
    return _read(_map_path(settings, owner, vocabulary))


def vectors(settings: Settings, owner: str, vocabulary: str) -> list[dict[str, Any]]:
    """Every sense with its text and vector, for the discovery experiment (`admin map export`)."""
    _vocabulary(owner, vocabulary)
    senses = _senses(owner, vocabulary)
    model = encoder()
    keys = [digest(model.model, sense.text) for sense in senses]
    matrix = _embed(settings, model, senses, keys)
    return [
        {"sense": sense.sense, "lexeme": sense.lexeme, "text": sense.text, "model": model.model,
         "vector": [round(float(v), 6) for v in row]}
        for sense, row in zip(senses, matrix)
    ]
