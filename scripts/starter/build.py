#!/usr/bin/env python3
"""Build the starter vocabularies' words on free Gemini keys, a day's allowance at a time.

    .venv/bin/python scripts/starter/build.py run                # the next work, until the day's calls are spent
    .venv/bin/python scripts/starter/build.py run --keys keys.env --wait   # several keys; sleep through the reset
    .venv/bin/python scripts/starter/build.py run --only es-MX --max-calls 20
    .venv/bin/python scripts/starter/build.py run --dry-run      # print what would be asked, call nothing
    .venv/bin/python scripts/starter/build.py status
    .venv/bin/python scripts/starter/build.py review es-MX       # mark a word list reviewed, so it is composed

The plan is `docs/plans/first-use/starter-vocabularies.md`; the concepts are
`docs/plans/first-use/starter-concepts.yaml`, the vocabularies `scripts/starter/vocabularies.yaml`.
Four steps, each skipped where its work is already done, so a run picks up wherever the last one
stopped:

1. **Words**: one call per (vocabulary, topic) picks the word(s) for each concept
   (`prompts/headwords.md`). When every topic is in, they are merged into `words.json`, one word
   per headword and part of speech, carrying every concept it serves. `words.json` is then the
   list to review and correct by hand; it is never rewritten while it exists.
2. **Compose**, once `words.reviewed` exists: one word at a time, asked **exactly what compose
   asks** (`services/capture/compose.compose_parts`) and checked by compose's own checks, then made
   into a draft by `draft_from`. Resolve is skipped: the word list already says the headword, lemma
   and part of speech. The concept's meaning goes in as the learner's note, so the sense the picture
   is for is not left out.
3. **Translate**, once every word is composed: the definitions compose's check now doubts or refuses
   for their language (`vet.definition_doubt`) are written again in `definitionLang`, one call per
   topic (`prompts/translate.md`), seeing each sense's word, glosses and other definitions. The draft
   and the match files take the new text; the compose file keeps what it replaced under
   `translations`, and its `replies` are never touched. A sense no model translates after three tries
   is left as it is (`translate.failed.json`), so it cannot stop matching.
4. **Match**, once nothing is left to translate: one call per topic maps each sense to a concept or
   to none (`prompts/match.md`).

A free key has two Flash-Lite models, each with its own daily allowance (about 500 calls), and a
per-minute meter of its own. A model is spent for the day when its 429 names a per-day quota, or after
five rests in a row; when every model of every key is, the run stops and says so. Spent models are
remembered until midnight in California, when Google resets them (08:00 UTC in winter), so a second
run the same day does not knock on a closed door. `--wait` sleeps until then and carries on.

Keys: `--keys FILE` (or the environment variable `STARTER_GEMINI_KEYS`) names a dotenv file of
`GEMINI_API_KEY_<n>=…` lines, one per Google account. Without either, the one `gemini-api` key in
`providers.local.json` is used. At most `--parallel-keys` keys (default 3) are asked at once, in file
order; when one is spent the next takes its place. The last key is a fallback, asked only when no other
key has an open model; `--no-fallback` leaves it out. A key's label (`k<n>`) is all that is logged.

Everything is written under `data/starter/`, and committed as the build's raw results: per
vocabulary `words/<topic>.json`, `words.json`, `compose/<word>.json` (the request, the raw reply, the
check's verdict, the draft, and any `translations`), `match/<topic>.json`, `translate.failed.json`;
and `calls.jsonl`, one line per call. Prices in it are list prices: the free key is not charged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acervo.domain.validation import POS_VALUES  # noqa: E402
from acervo.models import call  # noqa: E402
from acervo.models.cooldown import retry_after_of  # noqa: E402
from acervo.models.errors import ProviderError, ProviderRefused  # noqa: E402
from acervo.models.local import load_local  # noqa: E402
from acervo.models.locales import language_name  # noqa: E402
from acervo.models.pacing import Pace  # noqa: E402
from acervo.models.providers import DocumentError, parse as parse_provider  # noqa: E402
from acervo.services.capture.compose import compose_parts  # noqa: E402
from acervo.services.capture.draft import draft_from  # noqa: E402
from acervo.services.capture.vet import definition_doubt  # noqa: E402
from acervo.services.models import Demoted, Unusable  # noqa: E402
from acervo.services.prompts import prompt_text  # noqa: E402

CONCEPTS = ROOT / "docs" / "plans" / "first-use" / "starter-concepts.yaml"
VOCABULARIES = HERE / "vocabularies.yaml"
BUILDER_PROMPTS = HERE / "prompts"
APP_PROMPTS = ROOT / "prompts"
DICTIONARIES = ROOT / "data" / "dictionaries" / "out"
OUT = ROOT / "data" / "starter"

PROVIDER = "gemini-api"
MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
PER_MINUTE = 8          # the free tier meters the key, not the model (experiments/compose-lesson-line)
WORKERS_PER_KEY = 3     # a compose takes 10-20 s, so one at a time would use half the minute's calls
PARALLEL_KEYS = 3       # keys asked at once; one account's quota is not asked to carry the others'
KEYS_ENV = "STARTER_GEMINI_KEYS"
RESET_MARGIN = timedelta(minutes=1)   # waited past the reset, so the first call is not early
TIMEOUT = 120.0
RESTS_TO_SPEND = 5      # rests in a row that mark a model spent when Google never said "per day"
FAILURES_TO_STOP = 10   # failures in a row, of any model, that mean something is broken
GIVE_UP_AFTER = 3       # runs a word may fail its checks on every model before it is left out
RESET_ZONE = ZoneInfo("America/Los_Angeles")


# ── small helpers ───────────────────────────────────────────────────────────


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def slug(value: str) -> str:
    """A file name for a word in any script: its Latin letters if it has some, and a digest always."""
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    letters = "-".join("".join(c if c.isalnum() else " " for c in plain).split())[:40]
    return f"{letters}-{digest(value)[:8]}" if letters else digest(value)[:12]


# ── what the builder works from ─────────────────────────────────────────────


@dataclass(frozen=True)
class Concept:
    id: str
    topic: str
    sense: str
    pos: str
    note: str | None
    also: tuple[str, ...]
    picture: bool


def load_concepts(path: Path = CONCEPTS) -> dict[str, list[Concept]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        topic: [Concept(id=item["id"], topic=topic, sense=item["sense"], pos=item["pos"], note=item.get("note"),
                        also=tuple(item.get("also") or ()), picture=item.get("pic") != "none")
                for item in items]
        for topic, items in document.items()
    }


def load_vocabularies(path: Path = VOCABULARIES) -> tuple[list[dict[str, Any]], dict[str, str]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = document["defaults"]
    return [{**defaults, **item} for item in document["vocabularies"]], document["topics"]


def record_for(vocabulary: dict[str, Any]) -> dict[str, Any]:
    """What compose is told about the vocabulary: no learner note, as on a starter account."""
    keys = ("language", "definitionLang", "glossLangs", "notesLang", "level", "region")
    return {key: vocabulary[key] for key in keys if vocabulary.get(key) is not None}


# ── the keys ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Key:
    """One free key: a label for the logs (`k3`), the provider row that holds it, and whether it is held back."""

    label: str
    row: Any
    fallback: bool = False

    def lane(self, model: str) -> str:
        return f"{self.label}/{model}"


KEY_LINE = re.compile(r"^GEMINI_API_KEY_(\d+)\s*=\s*(\S+)\s*$")


def read_keys(path: Path) -> list[tuple[str, str]]:
    """`(label, key)` for each `GEMINI_API_KEY_<n>=…` line, in file order; anything else is a comment."""
    found: list[tuple[str, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        matched = KEY_LINE.match(text.strip("'\""))
        if not matched:
            raise ValueError(f"{path}:{number}: expected GEMINI_API_KEY_<n>=<key>, a comment or a blank line")
        label, value = f"k{int(matched[1])}", matched[2].strip("'\"")
        if any(label == one or value == key for one, key in found):
            raise ValueError(f"{path}:{number}: {label} or its key appears twice")
        found.append((label, value))
    return found


def keys_for(file: str | None, *, fallback: bool = True) -> list[Key]:
    """The keys to use: the file named, or the one in the environment, or the laptop's one gemini-api key."""
    file = file or os.environ.get(KEYS_ENV)
    if not file:
        return [Key("k1", load_local().find(PROVIDER))]
    held = read_keys(Path(file).expanduser())
    if not held:
        raise ValueError(f"{file} holds no GEMINI_API_KEY_<n> line")
    keys = []
    for label, value in held:
        document = {"id": f"gemini-{label}", "family": PROVIDER, "models": {"text": list(MODELS)}}
        try:
            keys.append(Key(label, parse_provider(document, {"key": value})))
        except DocumentError as error:
            raise ValueError(f"{label}: {error}") from None
    if len(keys) > 1:
        keys[-1] = Key(keys[-1].label, keys[-1].row, fallback=True)
        if not fallback:
            keys.pop()
    return keys


def shown(key: str) -> str:
    """A key's first and last four characters, which is all of it that is ever printed."""
    return f"{key[:4]}…{key[-4:]}"


# ── the day's allowance ─────────────────────────────────────────────────────


class DayOver(Exception):
    """Every model's allowance is spent until Google resets it."""


class Broken(Exception):
    """A failure no retry fixes: every key rejected, an unknown model, or failure after failure."""


class NoModel(Exception):
    """Every model not yet tried by this job is spent."""


def next_reset(at: datetime) -> datetime:
    local = at.astimezone(RESET_ZONE)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def per_day(detail: str) -> bool:
    """Google names the quota it refused on: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`."""
    return "perday" in detail.replace("_", "").replace("-", "").lower()


class Allowance:
    """Which lanes (`k1/gemini-3.5-flash-lite`: a key's model) may still be asked today, remembered
    across runs in `spent.json`."""

    def __init__(self, path: Path, lanes: Iterable[str], clock: Callable[[], datetime] | None = None) -> None:
        self.path = path
        self.lanes = tuple(lanes)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        self.rests: dict[str, int] = {lane: 0 for lane in self.lanes}
        held = read_json(path) if path.exists() else {}
        self.until: dict[str, datetime] = {lane: datetime.fromisoformat(value) for lane, value in held.items()}

    def is_open(self, lane: str) -> bool:
        with self.lock:
            moment = self.clock()
            return self.until.get(lane, moment) <= moment

    def spend(self, lane: str, why: str) -> None:
        with self.lock:
            if self.until.get(lane, self.clock()) > self.clock():
                return
            self.until[lane] = next_reset(self.clock())
            write_json(self.path, {name: value.isoformat() for name, value in self.until.items()})
        print(f"  {lane} is spent for today ({why}); it resets at "
              f"{self.until[lane].astimezone(RESET_ZONE):%H:%M %Z}", flush=True)

    def rested(self, lane: str) -> int:
        with self.lock:
            self.rests[lane] = self.rests.get(lane, 0) + 1
            return self.rests[lane]

    def answered(self, lane: str) -> None:
        with self.lock:
            self.rests[lane] = 0

    def next_open(self) -> datetime | None:
        """When the first lane now spent opens again, or None if none is spent."""
        with self.lock:
            moment = self.clock()
            later = [self.until[lane] for lane in self.lanes if self.until.get(lane, moment) > moment]
            return min(later) if later else None


# ── one call ────────────────────────────────────────────────────────────────


@dataclass
class Asked:
    model: str
    parsed: Any
    text: str
    seconds: float
    cost: float | None
    tokens: tuple[int, int]


class Failed(Exception):
    """One model's answer could not be used, or it did not answer for a reason worth retrying."""

    def __init__(self, model: str, reason: str, detail: str, *, retry: bool) -> None:
        super().__init__(detail)
        self.model, self.reason, self.detail, self.retry = model, reason, detail, retry


@dataclass
class Caller:
    """The keys, their paces, the allowance and the call log, shared by every worker of a run."""

    keys: list[Key]
    allowance: Allowance
    log: Path
    max_calls: int | None = None
    parallel_keys: int = PARALLEL_KEYS
    gates: dict[str, Pace] = field(default_factory=dict)
    dropped: set[str] = field(default_factory=set)
    calls: int = 0
    failures: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    stopped: threading.Event = field(default_factory=threading.Event)
    send: Callable[..., Any] = call.text

    def __post_init__(self) -> None:
        # The free tier meters the key, not the model, so one gate per key.
        for key in self.keys:
            self.gates.setdefault(key.label, Pace(PER_MINUTE, cooldown=30.0, cap=600.0))

    def note(self, line: dict[str, Any]) -> None:
        with self.lock, self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def open_lanes(self, key: Key) -> list[str]:
        return [model for model in MODELS if self.allowance.is_open(key.lane(model))]

    def any_open(self) -> bool:
        return any(self.open_lanes(key) for key in self.keys if key.label not in self.dropped)

    def eligible(self, exclude: Iterable[str]) -> list[tuple[Key, str]]:
        """The keys that may be asked now, in order, each with the model to ask: at most `parallel_keys`
        of them, and the fallback only when no other key has an open model."""
        live = [key for key in self.keys if key.label not in self.dropped and self.open_lanes(key)]
        main = [key for key in live if not key.fallback]
        chosen = []
        for key in main or live:
            model = next((m for m in self.open_lanes(key) if m not in exclude), None)
            if model is not None:
                chosen.append((key, model))
        return chosen[:self.parallel_keys]

    def ask(self, system: str, user: str, *, step: str, vocabulary: str, item: str,
            exclude: Iterable[str] = ()) -> Asked:
        """One answer from the first free key's first open model not in `exclude`, waiting out per-minute refusals."""
        exclude = tuple(exclude)
        while True:
            if self.stopped.is_set():
                raise DayOver()
            if not self.any_open():
                self.stopped.set()
                raise DayOver()
            candidates = self.eligible(exclude)
            if not candidates:
                raise NoModel()
            taken = next(((key, model) for key, model in candidates if self.gates[key.label].try_acquire()), None)
            if taken is None:
                time.sleep(0.25)
                continue
            key, model = taken
            lane = key.lane(model)
            with self.lock:
                if self.max_calls is not None and self.calls >= self.max_calls:
                    self.stopped.set()
                    raise DayOver()
                self.calls += 1
            line = {"at": now(), "step": step, "vocabulary": vocabulary, "item": item, "key": key.label, "model": model}
            started = time.monotonic()
            try:
                result = self.send(user, row=key.row, model=model, system=system, as_json=True, timeout=TIMEOUT)
            except ProviderError as error:
                seconds = round(time.monotonic() - started, 2)
                self.note(line | {"ok": False, "reason": error.reason, "seconds": seconds, "detail": error.detail[:600]})
                if isinstance(error, ProviderRefused):
                    # A rejected key is left out; the others carry on.
                    with self.lock:
                        self.dropped.add(key.label)
                        left = [k for k in self.keys if k.label not in self.dropped]
                    print(f"  {key.label} is dropped: {model} refused the call ({error.reason}): "
                          f"{error.detail[:200]}", flush=True)
                    if not left:
                        self.stopped.set()
                        raise Broken(f"every key was refused; the last said ({error.reason}): "
                                     f"{error.detail[:300]}") from None
                    continue
                if error.reason == "rate_limited":
                    if per_day(error.detail):
                        self.allowance.spend(lane, "Google says its daily allowance is used")
                    elif self.allowance.rested(lane) >= RESTS_TO_SPEND:
                        self.allowance.spend(lane, f"{RESTS_TO_SPEND} refusals in a row")
                    else:
                        self.gates[key.label].penalise(retry_after_of(error))
                    continue
                self.failed()
                raise Failed(model, error.reason, error.detail, retry=True) from None
            seconds = round(result.answer.seconds, 2)
            spent = result.answer.spent
            self.note(line | {"ok": True, "seconds": seconds, "costUsd": result.answer.cost_usd,
                              "in": spent.input_tokens, "out": spent.output_tokens,
                              "json": result.parsed is not None})
            self.gates[key.label].succeeded()
            self.allowance.answered(lane)
            return Asked(model, result.parsed, result.text, seconds, result.answer.cost_usd,
                         (spent.input_tokens, spent.output_tokens))

    def failed(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= FAILURES_TO_STOP:
                self.stopped.set()
                raise Broken(f"{FAILURES_TO_STOP} calls failed in a row; see the last lines of {self.log}")

    def succeeded(self) -> None:
        with self.lock:
            self.failures = 0


# ── step 1: words ───────────────────────────────────────────────────────────


def headword_message(vocabulary: dict[str, Any], concepts: list[Concept]) -> str:
    lines = [
        f"Target language: {language_name(vocabulary['language'])} ({vocabulary['language']})",
        f"Variety: {vocabulary['variety']}",
        f"Level: {vocabulary['level']}",
        "",
        "Concepts (id | part of speech | meaning | note):",
        *(f"{c.id} | {c.pos} | {c.sense}" + (f" | {c.note}" if c.note else "") for c in concepts),
    ]
    return "\n".join(lines)


def read_headwords(parsed: Any, concepts: list[Concept]) -> tuple[list[dict[str, Any]], list[str]]:
    """The words a reply gives, and the concepts it left out. Refuses a reply that is not usable."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("words"), list):
        raise ValueError("the reply has no `words` list")
    known = {c.id for c in concepts}
    words: list[dict[str, Any]] = []
    for item in parsed["words"]:
        if not isinstance(item, dict):
            raise ValueError("a word is not an object")
        concept = str(item.get("concept") or "").strip()
        headword = " ".join(str(item.get("headword") or "").split())
        lemma = " ".join(str(item.get("lemma") or "").split()) or headword
        pos = str(item.get("pos") or "").strip().lower()
        if concept not in known:
            raise ValueError(f"unknown concept {concept!r}")
        if not headword:
            raise ValueError(f"no headword for {concept}")
        if pos not in POS_VALUES:
            raise ValueError(f"{headword}: part of speech {pos!r} is not one of {', '.join(POS_VALUES)}")
        words.append({"concept": concept, "headword": headword, "lemma": lemma, "pos": pos})
    missing = sorted(known - {word["concept"] for word in words})
    return words, missing


def merge_words(per_topic: dict[str, dict[str, Any]], concepts: dict[str, list[Concept]],
                topic_names: dict[str, str]) -> list[dict[str, Any]]:
    """One word per (headword, part of speech), carrying every concept it was chosen for."""
    by_id = {c.id: c for items in concepts.values() for c in items}
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for topic in concepts:
        for item in per_topic[topic]["words"]:
            concept = by_id[item["concept"]]
            key = (unicodedata.normalize("NFC", item["headword"]), item["pos"])
            word = merged.setdefault(key, {
                "key": slug(f"{key[0]}|{key[1]}"), "headword": key[0], "lemma": item["lemma"],
                "pos": item["pos"], "concepts": [], "senses": [], "topics": [],
            })
            if concept.id not in word["concepts"]:
                word["concepts"].append(concept.id)
                word["senses"].append(concept.sense)
            for name in (concept.topic, *concept.also):
                if topic_names[name] not in word["topics"]:
                    word["topics"].append(topic_names[name])
    return list(merged.values())


def words_job(caller: Caller, vocabulary: dict[str, Any], topic: str, concepts: list[Concept],
              system: str, folder: Path) -> None:
    path = folder / "words" / f"{topic}.json"
    user = headword_message(vocabulary, concepts)
    tried: list[str] = []
    for _ in MODELS:
        try:
            asked = caller.ask(system, user, step="words", vocabulary=vocabulary["id"], item=topic, exclude=tried)
        except NoModel:
            return
        except Failed as failure:
            tried.append(failure.model)
            continue
        tried.append(asked.model)
        try:
            words, missing = read_headwords(asked.parsed, concepts)
        except ValueError as why:
            caller.note({"at": now(), "step": "words", "vocabulary": vocabulary["id"], "item": topic,
                         "model": asked.model, "unusable": str(why)})
            continue
        caller.succeeded()
        write_json(path, {"vocabulary": vocabulary["id"], "topic": topic, "model": f"{PROVIDER}:{asked.model}",
                          "at": now(), "prompt": digest(system), "request": user, "reply": asked.text,
                          "words": words, "missing": missing})
        print(f"[{vocabulary['id']}] words {topic}: {len(words)} words"
              + (f", {len(missing)} concepts missing" if missing else ""), flush=True)
        return


# ── step 2: compose ─────────────────────────────────────────────────────────


def compose_request(word: dict[str, Any]) -> dict[str, Any]:
    senses = word["senses"]
    note = (f"Make sure one of the senses is this meaning: {senses[0]}." if len(senses) == 1 else
            "Make sure the senses include each of these meanings: " + "; ".join(senses) + ".")
    return {"topics": word["topics"], "note": note}


def compose_job(caller: Caller, vocabulary: dict[str, Any], word: dict[str, Any], topics: list[dict[str, str]],
                folder: Path) -> None:
    path = folder / "compose" / f"{word['key']}.json"
    failure_path = path.with_suffix(".failed.json")
    record = record_for(vocabulary)
    resolution = {"language": vocabulary["language"], "headword": word["headword"], "lemma": word["lemma"],
                  "pos": word["pos"], "sentences": []}
    request = compose_request(word)
    system, user, check = compose_parts(APP_PROMPTS, DICTIONARIES, resolution, request, record, topics)

    tried: list[str] = []
    replies: list[dict[str, Any]] = []
    kept: tuple[Asked, Demoted] | None = None
    passed: tuple[Asked, Any] | None = None
    retry = False
    for _ in MODELS:
        try:
            asked = caller.ask(system, user, step="compose", vocabulary=vocabulary["id"], item=word["headword"],
                               exclude=tried)
        except NoModel:
            retry = True
            break
        except Failed as failure:
            tried.append(failure.model)
            retry = retry or failure.retry
            continue
        tried.append(asked.model)
        reply = {"model": asked.model, "seconds": asked.seconds, "costUsd": asked.cost,
                 "tokens": asked.tokens, "text": asked.text}
        replies.append(reply)
        if asked.parsed is None:
            reply["verdict"] = {"outcome": "unusable", "why": "the reply is not JSON"}
            continue
        try:
            vetted = check(asked.parsed)
        except Demoted as doubt:
            reply["verdict"] = {"outcome": "demoted", "why": str(doubt), "by": doubt.by}
            kept = kept or (asked, doubt)
            continue
        except Unusable as refusal:
            reply["verdict"] = {"outcome": "unusable", "why": str(refusal)}
            continue
        reply["verdict"] = {"outcome": "passed", "fixed": vetted.fixed, "dropped": vetted.dropped}
        passed = (asked, vetted)
        break

    chosen = passed or ((kept[0], kept[1].checked) if kept else None)
    if chosen is None:
        if retry:
            return  # nothing written: a later run asks again
        attempts = (read_json(failure_path)["attempts"] if failure_path.exists() else 0) + 1
        write_json(failure_path, {"word": word, "attempts": attempts, "at": now(), "replies": replies})
        print(f"[{vocabulary['id']}] compose {word['headword']}: failed its checks on every model "
              f"(attempt {attempts} of {GIVE_UP_AFTER})", flush=True)
        return
    caller.succeeded()
    asked, vetted = chosen
    draft = draft_from(vetted.answer, resolution, request, record, topics, f"{PROVIDER}:{asked.model}")
    write_json(path, {
        "vocabulary": vocabulary["id"], "word": word, "at": now(), "model": f"{PROVIDER}:{asked.model}",
        "prompt": digest(system), "request": {"resolution": resolution, "request": request, "user": user},
        "outcome": "passed" if passed else "demoted", "replies": replies, "draft": draft,
    })
    failure_path.unlink(missing_ok=True)
    print(f"[{vocabulary['id']}] compose {word['headword']}: {len(draft['senses'])} senses, "
          f"{'passed' if passed else 'demoted'} on {asked.model}", flush=True)


# ── step 3: match ───────────────────────────────────────────────────────────


def composed_files(folder: Path) -> list[Path]:
    return [path for path in sorted((folder / "compose").glob("*.json")) if not path.name.endswith(".failed.json")]


def match_batches(folder: Path, concepts: dict[str, list[Concept]], topic_names: dict[str, str]
                  ) -> dict[str, tuple[list[Concept], list[dict[str, Any]]]]:
    """Per topic, its candidate concepts and the senses of the words chosen for its concepts."""
    by_id = {c.id: c for items in concepts.values() for c in items}
    senses_of: dict[str, list[dict[str, Any]]] = {}
    reach: dict[str, set[str]] = {}
    for path in composed_files(folder):
        composed = read_json(path)
        chosen_for = [by_id[c] for c in composed["word"]["concepts"]]
        home = chosen_for[0].topic
        draft = composed["draft"]
        senses_of.setdefault(home, []).extend(
            {"id": sense["id"], "headword": draft["headword"], "pos": draft["pos"],
             "definition": sense["definition"],
             "glosses": "; ".join(", ".join(gloss["terms"]) for gloss in sense["glosses"])}
            for sense in draft["senses"])
        # Every topic any of the word's concepts lives in or is filed under, so a word chosen for
        # two concepts in two topics can match either.
        reach.setdefault(home, {home}).update(t for c in chosen_for for t in (c.topic, *c.also))
    batches: dict[str, tuple[list[Concept], list[dict[str, Any]]]] = {}
    for topic, senses in senses_of.items():
        candidates = [c for items in concepts.values() for c in items
                      if c.topic in reach[topic] or set(c.also) & reach[topic]]
        batches[topic] = (candidates, senses)
    return batches


def match_message(vocabulary: dict[str, Any], candidates: list[Concept], senses: list[dict[str, Any]]) -> str:
    return "\n".join([
        f"Language of the words: {language_name(vocabulary['language'])} ({vocabulary['language']})",
        "",
        "Concepts (id | part of speech | meaning):",
        *(f"{c.id} | {c.pos} | {c.sense}" for c in candidates),
        "",
        "Senses (sense id | headword | part of speech | definition | glosses):",
        *(f"{s['id']} | {s['headword']} | {s['pos']} | {s['definition']} | {s['glosses']}" for s in senses),
    ])


def read_matches(parsed: Any, candidates: list[Concept], senses: list[dict[str, Any]]) -> dict[str, str | None]:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("matches"), dict):
        raise ValueError("the reply has no `matches` object")
    known = {c.id for c in candidates}
    sent = {s["id"] for s in senses}
    matches: dict[str, str | None] = {}
    for sense, concept in parsed["matches"].items():
        if sense not in sent:
            raise ValueError(f"unknown sense id {sense!r}")
        if concept is not None and concept not in known:
            raise ValueError(f"unknown concept {concept!r}")
        matches[sense] = concept
    missing = sent - set(matches)
    if missing:
        raise ValueError(f"{len(missing)} sense(s) left out")
    return matches


def match_job(caller: Caller, vocabulary: dict[str, Any], topic: str, candidates: list[Concept],
              senses: list[dict[str, Any]], system: str, folder: Path) -> None:
    path = folder / "match" / f"{topic}.json"
    user = match_message(vocabulary, candidates, senses)
    tried: list[str] = []
    for _ in MODELS:
        try:
            asked = caller.ask(system, user, step="match", vocabulary=vocabulary["id"], item=topic, exclude=tried)
        except NoModel:
            return
        except Failed as failure:
            tried.append(failure.model)
            continue
        tried.append(asked.model)
        try:
            matches = read_matches(asked.parsed, candidates, senses)
        except ValueError as why:
            caller.note({"at": now(), "step": "match", "vocabulary": vocabulary["id"], "item": topic,
                         "model": asked.model, "unusable": str(why)})
            continue
        caller.succeeded()
        # Import re-mints every id, so each match also says which sense it is in words.
        write_json(path, {"vocabulary": vocabulary["id"], "topic": topic, "model": f"{PROVIDER}:{asked.model}",
                          "at": now(), "prompt": digest(system), "request": user, "reply": asked.text,
                          "matches": [{**sense, "concept": matches[sense["id"]]} for sense in senses]})
        print(f"[{vocabulary['id']}] match {topic}: {sum(1 for v in matches.values() if v)} of "
              f"{len(matches)} senses matched", flush=True)
        return


# ── step 2b: translate the definitions written in the wrong language ────────

TRANSLATE_BATCH = 40          # senses in one call, at most; a word's senses are never split
WRITING = threading.Lock()    # two batches of one topic both update its match file


def misdefined(composed: dict[str, Any], vocabulary: dict[str, Any]) -> list[dict[str, Any]]:
    """The draft's senses compose's check now doubts or refuses for their language
    (`vet.definition_doubt`): what compose would no longer let through unremarked."""
    resolution = composed["request"]["resolution"]
    draft = composed["draft"]
    quoted = [resolution["headword"], resolution["lemma"], draft.get("headword") or "", draft.get("reading") or ""]
    record = record_for(vocabulary)
    return [sense for sense in draft["senses"]
            if definition_doubt(sense["definition"], record, resolution, quoted) is not None]


def translate_attempts(folder: Path) -> dict[str, int]:
    path = folder / "translate.failed.json"
    return read_json(path) if path.exists() else {}


def translate_batches(folder: Path, vocabulary: dict[str, Any], concepts: dict[str, list[Concept]]
                      ) -> dict[str, list[dict[str, Any]]]:
    """Per batch (`<topic>` or `<topic>.<n>`), the senses to translate, each with what the translation
    sees: the word, its glosses and its other definitions. A sense tried `GIVE_UP_AFTER` times is left."""
    by_id = {c.id: c for items in concepts.values() for c in items}
    attempts = translate_attempts(folder)
    per_topic: dict[str, list[list[dict[str, Any]]]] = {}
    for path in composed_files(folder):
        composed = read_json(path)
        wrong = [s for s in misdefined(composed, vocabulary) if attempts.get(s["id"], 0) < GIVE_UP_AFTER]
        if not wrong:
            continue
        draft = composed["draft"]
        home = by_id[composed["word"]["concepts"][0]].topic
        per_topic.setdefault(home, []).append([
            {"id": sense["id"], "file": path.name, "headword": draft["headword"], "pos": draft["pos"],
             "glosses": "; ".join(", ".join(g["terms"]) for g in sense["glosses"]),
             "definition": sense["definition"],
             "others": [s["definition"] for s in draft["senses"] if s["id"] != sense["id"]]}
            for sense in wrong])
    batches: dict[str, list[dict[str, Any]]] = {}
    for topic, words in per_topic.items():
        chunk: list[dict[str, Any]] = []
        chunks = [chunk]
        for senses in words:
            if chunk and len(chunk) + len(senses) > TRANSLATE_BATCH:
                chunk = []
                chunks.append(chunk)
            chunk.extend(senses)
        for index, items in enumerate(chunks):
            batches[topic if index == 0 else f"{topic}.{index + 1}"] = items
    return batches


def translate_message(vocabulary: dict[str, Any], items: list[dict[str, Any]]) -> str:
    target = record_for(vocabulary)["definitionLang"]
    return "\n".join([
        f"Language of the words: {language_name(vocabulary['language'])} ({vocabulary['language']})",
        f"Write every definition in: {language_name(target)} ({target})",
        "",
        "Senses (sense id | headword | part of speech | glosses | definition as written | "
        "the word's other definitions):",
        *(f"{s['id']} | {s['headword']} | {s['pos']} | {s['glosses']} | {s['definition']} | "
          + (" / ".join(s["others"]) or "(none)") for s in items),
    ])


def read_translations(parsed: Any, items: list[dict[str, Any]], vocabulary: dict[str, Any]
                      ) -> tuple[dict[str, str], dict[str, str]]:
    """The usable translations by sense id, and why each other sense was not translated. A reply
    naming a sense it was not given is refused whole, as a match is."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("definitions"), dict):
        raise ValueError("the reply has no `definitions` object")
    sent = {s["id"]: s for s in items}
    unknown = set(parsed["definitions"]) - set(sent)
    if unknown:
        raise ValueError(f"unknown sense id {sorted(unknown)[0]!r}")
    record = record_for(vocabulary)
    usable: dict[str, str] = {}
    refused: dict[str, str] = {}
    for sense_id, item in sent.items():
        text = parsed["definitions"].get(sense_id)
        if not isinstance(text, str) or not text.strip():
            refused[sense_id] = "left out"
            continue
        resolution = {"language": vocabulary["language"], "headword": item["headword"]}
        doubt = definition_doubt(text.strip(), record, resolution, [item["headword"]])
        if doubt:
            refused[sense_id] = doubt[0]
            continue
        usable[sense_id] = text.strip()
    return usable, refused


def apply_translations(folder: Path, items: list[dict[str, Any]], usable: dict[str, str], model: str,
                       prompt: str) -> None:
    """Each translated definition replaces the draft's, which keeps a record of what it replaced; the
    replies are untouched. The match files carry the definition too, because import finds a match by
    headword and definition (the plan's step 7)."""
    at = now()
    with WRITING:
        for name in sorted({s["file"] for s in items if s["id"] in usable}):
            path = folder / "compose" / name
            composed = read_json(path)
            for sense in composed["draft"]["senses"]:
                if sense["id"] in usable:
                    composed.setdefault("translations", []).append(
                        {"sense": sense["id"], "from": sense["definition"], "to": usable[sense["id"]],
                         "model": f"{PROVIDER}:{model}", "prompt": prompt, "at": at})
                    sense["definition"] = usable[sense["id"]]
            write_json(path, composed)
        for path in sorted((folder / "match").glob("*.json")):
            matched = read_json(path)
            changed = False
            for entry in matched["matches"]:
                if entry["id"] in usable and entry["definition"] != usable[entry["id"]]:
                    entry["definition"] = usable[entry["id"]]
                    changed = True
            if changed:
                write_json(path, matched)


def translate_job(caller: Caller, vocabulary: dict[str, Any], batch: str, items: list[dict[str, Any]],
                  system: str, folder: Path) -> None:
    user = translate_message(vocabulary, items)
    tried: list[str] = []
    answered_badly = False
    for _ in MODELS:
        try:
            asked = caller.ask(system, user, step="translate", vocabulary=vocabulary["id"], item=batch, exclude=tried)
        except NoModel:
            return
        except Failed as failure:
            tried.append(failure.model)
            continue
        tried.append(asked.model)
        try:
            usable, refused = read_translations(asked.parsed, items, vocabulary)
        except ValueError as why:
            caller.note({"at": now(), "step": "translate", "vocabulary": vocabulary["id"], "item": batch,
                         "model": asked.model, "unusable": str(why)})
            answered_badly = True
            continue
        caller.succeeded()
        apply_translations(folder, items, usable, asked.model, digest(system))
        if refused:
            caller.note({"at": now(), "step": "translate", "vocabulary": vocabulary["id"], "item": batch,
                         "model": asked.model, "refused": refused})
            count_attempts(folder, refused)
        print(f"[{vocabulary['id']}] translate {batch}: {len(usable)} of {len(items)} definitions"
              + (f"; {len(refused)} again next time" if refused else ""), flush=True)
        return
    if answered_badly:
        # Every model answered and none could be read: an attempt, so a batch no model gets right is
        # not asked every day. Failures to answer (a 503, a timeout) count for nothing.
        count_attempts(folder, [s["id"] for s in items])
        print(f"[{vocabulary['id']}] translate {batch}: no reply could be read", flush=True)


def count_attempts(folder: Path, sense_ids: Iterable[str]) -> None:
    with WRITING:
        attempts = translate_attempts(folder)
        for sense_id in sense_ids:
            attempts[sense_id] = attempts.get(sense_id, 0) + 1
        write_json(folder / "translate.failed.json", attempts)


# ── the state of a vocabulary, read from its files ──────────────────────────


@dataclass
class State:
    vocabulary: dict[str, Any]
    folder: Path
    topics_done: set[str]
    words: list[dict[str, Any]] | None
    reviewed: bool
    composed: set[str]
    demoted: int
    failed: dict[str, int]
    matched: dict[str, list[dict[str, Any]]]

    @property
    def to_compose(self) -> list[dict[str, Any]]:
        return [w for w in self.words or [] if w["key"] not in self.composed
                and self.failed.get(w["key"], 0) < GIVE_UP_AFTER]

    @property
    def composing_done(self) -> bool:
        return self.words is not None and not self.to_compose


def state_of(vocabulary: dict[str, Any], out: Path) -> State:
    folder = out / vocabulary["id"]
    composed, demoted, failed = set(), 0, {}
    for path in (folder / "compose").glob("*.json"):
        if path.name.endswith(".failed.json"):
            failed[path.name[: -len(".failed.json")]] = read_json(path)["attempts"]
            continue
        composed.add(path.stem)
        demoted += read_json(path)["outcome"] == "demoted"
    words_path = folder / "words.json"
    return State(
        vocabulary=vocabulary, folder=folder,
        topics_done={path.stem for path in (folder / "words").glob("*.json")},
        words=read_json(words_path)["words"] if words_path.exists() else None,
        reviewed=(folder / "words.reviewed").exists(),
        composed=composed, demoted=demoted, failed=failed,
        matched={path.stem: read_json(path)["matches"] for path in (folder / "match").glob("*.json")},
    )


def ensure_word_list(state: State, concepts: dict[str, list[Concept]], topic_names: dict[str, str]) -> None:
    """Write `words.json` once every topic is in. Never over an existing one: it may hold corrections."""
    if state.words is not None or set(concepts) - state.topics_done:
        return
    per_topic = {topic: read_json(state.folder / "words" / f"{topic}.json") for topic in concepts}
    words = merge_words(per_topic, concepts, topic_names)
    missing = sorted(c for one in per_topic.values() for c in one["missing"])
    write_json(state.folder / "words.json", {"vocabulary": state.vocabulary["id"], "at": now(),
                                             "missing": missing, "words": words})
    state.words = words
    print(f"[{state.vocabulary['id']}] word list ready: {len(words)} words"
          + (f", {len(missing)} concepts without a word" if missing else "")
          + f". Review {state.folder / 'words.json'}, then: build.py review {state.vocabulary['id']}", flush=True)


# ── commands ────────────────────────────────────────────────────────────────


def selected(vocabularies: list[dict[str, Any]], only: str | None) -> list[dict[str, Any]]:
    if not only:
        return vocabularies
    wanted = [name.strip() for name in only.split(",") if name.strip()]
    unknown = set(wanted) - {v["id"] for v in vocabularies}
    if unknown:
        raise SystemExit(f"unknown vocabulary: {', '.join(sorted(unknown))}")
    return [v for v in vocabularies if v["id"] in wanted]


def run(args: argparse.Namespace, *, out: Path = OUT, send: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None, sleep: Callable[[float], None] = time.sleep) -> int:
    concepts = load_concepts()
    vocabularies, topic_names = load_vocabularies()
    chosen = selected(vocabularies, args.only)
    topics = [{"name": name} for name in topic_names.values()]
    headword_system = (BUILDER_PROMPTS / "headwords.md").read_text(encoding="utf-8")
    match_system = (BUILDER_PROMPTS / "match.md").read_text(encoding="utf-8")
    translate_system = (BUILDER_PROMPTS / "translate.md").read_text(encoding="utf-8")

    if args.dry_run:
        first = chosen[0]
        topic, items = next(iter(concepts.items()))
        print(f"── words: {first['id']} / {topic} ──\n{headword_message(first, items)}\n")
        word = {"headword": "(from the word list)", "lemma": "(from the word list)", "pos": items[0].pos,
                "senses": [items[0].sense], "topics": [topic_names[topic]]}
        resolution = {"language": first["language"], "headword": word["headword"], "lemma": word["lemma"],
                      "pos": word["pos"], "sentences": []}
        system, user, _ = compose_parts(APP_PROMPTS, DICTIONARIES, resolution, compose_request(word),
                                        record_for(first), topics)
        reader = system[len(prompt_text(APP_PROMPTS, "acervo_compose")):].strip()
        print(f"── compose: {first['id']}, after the compose prompt ──\n{reader}\n\n{user}")
        for vocabulary in chosen:
            translations = translate_batches(out / vocabulary["id"], vocabulary, concepts) \
                if (out / vocabulary["id"] / "compose").exists() else {}
            if translations:
                senses = sum(len(items) for items in translations.values())
                print(f"\n── translate: {vocabulary['id']}, {senses} definitions in {len(translations)} calls ──")
                if vocabulary is next(v for v in chosen if (out / v["id"] / "compose").exists()):
                    print(translate_message(vocabulary, next(iter(translations.values()))))
        return 0

    try:
        keys = keys_for(args.keys, fallback=not args.no_fallback)
    except (ValueError, OSError) as error:
        print(f"The keys cannot be read: {error}", file=sys.stderr)
        return 1
    unusable = [key for key in keys if not key.row.available]
    for key in unusable:
        print(f"{key.label} cannot be called here: {key.row.reason()}", file=sys.stderr)
    keys = [key for key in keys if key not in unusable]
    if not keys:
        return 1
    out.mkdir(parents=True, exist_ok=True)
    allowance = Allowance(out / "spent.json", [key.lane(model) for key in keys for model in MODELS], clock)
    workers = args.workers or WORKERS_PER_KEY * min(args.parallel_keys, len(keys))
    print("keys: " + ", ".join(f"{key.label}{' (fallback)' if key.fallback else ''}" for key in keys)
          + f"; {args.parallel_keys} at a time, {workers} workers")
    write_json(out / "manifest.json", {"concepts": digest(CONCEPTS.read_text(encoding="utf-8")),
                                       "prompts": {"headwords": digest(headword_system), "match": digest(match_system),
                                                   "translate": digest(translate_system),
                                                   "acervo_compose": digest(prompt_text(APP_PROMPTS, "acervo_compose"))}})
    asked = 0
    while True:
        caller = Caller(keys=keys, allowance=allowance, log=out / "calls.jsonl", parallel_keys=args.parallel_keys,
                        max_calls=None if args.max_calls is None else args.max_calls - asked)
        if send is not None:
            caller.send = send
        if not caller.any_open():
            outcome = "spent"
        else:
            outcome = one_pass(caller, workers, args, out, chosen, concepts, topic_names, topics,
                               headword_system, match_system, translate_system)
            if outcome == "broken":
                return 1
        asked += caller.calls
        if outcome == "limit":
            print(f"\nStopped after {asked} call(s): the call limit for this run.")
        elif outcome == "spent":
            if args.wait:
                wait_for_reset(allowance, clock or (lambda: datetime.now(timezone.utc)), sleep)
                continue
            print(f"\nStopped after {asked} call(s): today's allowance is used; run again tomorrow, "
                  "or use --wait to sleep until the reset.")
        else:
            print(f"\nNothing left that can be done now, after {asked} call(s).")
        break
    status(args, out=out)
    return 0


def wait_for_reset(allowance: Allowance, clock: Callable[[], datetime], sleep: Callable[[float], None]) -> None:
    """Sleep until the first spent lane opens, judged by the wall clock so a sleeping laptop does not lose it."""
    opens = allowance.next_open()
    if opens is None:
        return
    target = opens + RESET_MARGIN
    print(f"\nEvery key is spent for today. Resuming at {target.astimezone(RESET_ZONE):%H:%M %Z} "
          f"({target:%H:%M} UTC, {target.astimezone():%H:%M} here); Ctrl-C to stop.", flush=True)
    while (left := (target - clock()).total_seconds()) > 0:
        sleep(min(30.0, left))


def one_pass(caller: Caller, workers: int, args: argparse.Namespace, out: Path, chosen: list[dict[str, Any]],
             concepts: dict[str, list[Concept]], topic_names: dict[str, str], topics: list[dict[str, str]],
             headword_system: str, match_system: str, translate_system: str) -> str:
    """The next work until it is done or the keys are spent: "idle", "spent", "limit" or "broken"."""

    def each(jobs: list[Callable[[], None]]) -> None:
        """The jobs on a few workers; the first DayOver or Broken stops the rest."""
        problems: list[BaseException] = []

        def wrapped(job: Callable[[], None]) -> None:
            if caller.stopped.is_set():
                return
            try:
                job()
            except (DayOver, Broken) as stop:
                caller.stopped.set()
                problems.append(stop)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(wrapped, jobs))
        broken = next((p for p in problems if isinstance(p, Broken)), None)
        if broken:
            raise broken
        if problems:
            raise DayOver()

    try:
        jobs: list[Callable[[], None]] = []
        for vocabulary in chosen:
            state = state_of(vocabulary, out)
            for topic, items in concepts.items():
                if topic not in state.topics_done:
                    jobs.append(lambda v=vocabulary, t=topic, i=items, f=state.folder:
                                words_job(caller, v, t, i, headword_system, f))
        each(jobs)
        for vocabulary in chosen:
            ensure_word_list(state_of(vocabulary, out), concepts, topic_names)

        for vocabulary in chosen:
            state = state_of(vocabulary, out)
            if not state.reviewed:
                continue
            each([lambda v=vocabulary, w=word, f=state.folder: compose_job(caller, v, w, topics, f)
                  for word in state.to_compose])
            state = state_of(vocabulary, out)
            if not state.composing_done:
                continue
            # Translated before matched, so the matcher reads every definition in one language. A
            # sense whose translation is refused is counted, so the rounds end and matching follows.
            for _ in range(GIVE_UP_AFTER):
                translations = translate_batches(state.folder, vocabulary, concepts)
                if not translations:
                    break
                each([lambda v=vocabulary, b=batch, i=items, f=state.folder:
                      translate_job(caller, v, b, i, translate_system, f)
                      for batch, items in translations.items()])
            if translate_batches(state.folder, vocabulary, concepts):
                continue
            batches = match_batches(state.folder, concepts, topic_names)
            each([lambda v=vocabulary, t=topic, c=cands, s=senses, f=state.folder:
                  match_job(caller, v, t, c, s, match_system, f)
                  for topic, (cands, senses) in batches.items() if topic not in state.matched])
    except DayOver:
        return "limit" if caller.max_calls is not None and caller.calls >= caller.max_calls else "spent"
    except Broken as broken:
        print(f"\nStopped: {broken}", file=sys.stderr)
        status(args, out=out)
        return "broken"
    return "idle"


def status(args: argparse.Namespace, *, out: Path = OUT) -> int:
    concepts = load_concepts()
    vocabularies, _ = load_vocabularies()
    pictured = {c.id for items in concepts.values() for c in items if c.picture}
    print(f"\n{'vocabulary':10s} {'words':>11s} {'composed':>13s} {'demoted':>8s} {'failed':>7s} "
          f"{'wrong lang':>10s} {'matched':>8s} {'no concept':>11s} {'uncovered':>10s}")
    for vocabulary in selected(vocabularies, getattr(args, "only", None)):
        state = state_of(vocabulary, out)
        if state.words is None:
            words = f"{len(state.topics_done)}/{len(concepts)} topics"
        else:
            words = f"{len(state.words)}" + (" ✓" if state.reviewed else " review")
        total = len(state.words or [])
        failed = sum(1 for n in state.failed.values() if n >= GIVE_UP_AFTER)
        senses = [m for matches in state.matched.values() for m in matches]
        unmatched = sum(1 for m in senses if not m["concept"])
        covered = {m["concept"] for m in senses if m["concept"]}
        uncovered = len(pictured - covered) if state.matched else "-"
        # Definitions compose's check now doubts for their language: the translate step's work.
        wrong = sum(len(misdefined(read_json(path), vocabulary)) for path in composed_files(state.folder)) \
            if state.composed else "-"
        print(f"{vocabulary['id']:10s} {words:>11s} {len(state.composed):>6d}/{total:<6d} {state.demoted:>8d} "
              f"{failed:>7d} {wrong:>10} {len(state.matched):>5d}/{len(concepts):<2d} "
              f"{unmatched if senses else '-':>11} {uncovered:>10}")
    log = out / "calls.jsonl"
    if log.exists():
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        today = datetime.now(RESET_ZONE).date()
        def on_reset_day(line: dict[str, Any]) -> bool:
            return datetime.fromisoformat(line["at"].replace("Z", "+00:00")).astimezone(RESET_ZONE).date() == today
        asked = [line for line in lines if "ok" in line]
        cost = sum(line.get("costUsd") or 0 for line in asked)
        print(f"\ncalls: {sum(1 for line in asked if on_reset_day(line))} today (California day), "
              f"{len(asked)} in all; list price ${cost:.2f} (the free keys pay nothing)")
        per_key: dict[str, int] = {}
        for line in asked:
            if line.get("key") and line.get("ok") and on_reset_day(line):
                per_key[line["key"]] = per_key.get(line["key"], 0) + 1
        spent = read_json(out / "spent.json") if (out / "spent.json").exists() else {}
        moment = datetime.now(timezone.utc)
        closed = sorted(lane for lane, until in spent.items() if datetime.fromisoformat(until) > moment)
        if per_key or closed:
            print("answered today per key: " + (", ".join(f"{k} {n}" for k, n in sorted(per_key.items())) or "none"))
            print("spent until the reset: " + (", ".join(closed) or "nothing"))
    return 0


def review(args: argparse.Namespace, *, out: Path = OUT) -> int:
    vocabularies, _ = load_vocabularies()
    vocabulary = selected(vocabularies, args.vocabulary)[0]
    folder = out / vocabulary["id"]
    if not (folder / "words.json").exists():
        print(f"{vocabulary['id']} has no word list yet.", file=sys.stderr)
        return 1
    (folder / "words.reviewed").write_text(now() + "\n", encoding="utf-8")
    print(f"{vocabulary['id']}: word list marked reviewed; the next run composes it.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    running = commands.add_parser("run", help="do the next work until the day's allowance is used")
    running.add_argument("--only", help="vocabulary ids, comma-separated (es-MX,ru)")
    running.add_argument("--max-calls", type=int, help="stop after this many calls")
    running.add_argument("--workers", type=int, help=f"default {WORKERS_PER_KEY} per key asked at once")
    running.add_argument("--keys", help=f"a dotenv file of GEMINI_API_KEY_<n> lines (or ${KEYS_ENV})")
    running.add_argument("--parallel-keys", type=int, default=PARALLEL_KEYS, help="keys asked at once")
    running.add_argument("--no-fallback", action="store_true", help="never use the last key in the file")
    running.add_argument("--wait", action="store_true", help="when every key is spent, sleep until the reset and go on")
    running.add_argument("--dry-run", action="store_true", help="print what would be asked; call nothing")
    showing = commands.add_parser("status", help="what is done, per vocabulary")
    showing.add_argument("--only")
    marking = commands.add_parser("review", help="mark a vocabulary's word list reviewed")
    marking.add_argument("vocabulary")
    args = parser.parse_args(argv)
    return {"run": run, "status": status, "review": review}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
