#!/usr/bin/env python3
"""Build the starter vocabularies' words on the free Gemini key, a day's allowance at a time.

    .venv/bin/python scripts/starter/build.py run                # the next work, until the day's calls are spent
    .venv/bin/python scripts/starter/build.py run --only es-MX --max-calls 20
    .venv/bin/python scripts/starter/build.py run --dry-run      # print what would be asked, call nothing
    .venv/bin/python scripts/starter/build.py status
    .venv/bin/python scripts/starter/build.py review es-MX       # mark a word list reviewed, so it is composed

The plan is `docs/plans/first-use/starter-vocabularies.md`; the concepts are
`docs/plans/first-use/starter-concepts.yaml`, the vocabularies `scripts/starter/vocabularies.yaml`.
Three steps, each skipped where its file already exists, so a run picks up wherever the last one
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
3. **Match**, once every word is composed: one call per topic maps each sense to a concept or to
   none (`prompts/match.md`).

The free key has two Flash-Lite models, each with its own daily allowance (about 500 calls). A model
is spent for the day when its 429 names a per-day quota, or after five rests in a row; when both
are, the run stops and says so. Spent models are remembered until midnight in California, when
Google resets them, so a second run the same day does not knock on a closed door.

Everything is written under `data/starter/` (ignored): per vocabulary `words/<topic>.json`,
`words.json`, `compose/<word>.json` (the request, the raw reply, the check's verdict, the draft),
`match/<topic>.json`; and `calls.jsonl`, one line per call. Prices in it are list prices: the free
key is not charged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from acervo.services.capture.compose import compose_parts  # noqa: E402
from acervo.services.capture.draft import draft_from  # noqa: E402
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
WORKERS = 3             # a compose takes 10-20 s, so one at a time would use half the minute's calls
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


# ── the day's allowance ─────────────────────────────────────────────────────


class DayOver(Exception):
    """Every model's allowance is spent until Google resets it."""


class Broken(Exception):
    """A failure no retry fixes: a rejected key, an unknown model, or failure after failure."""


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
    """Which models may still be asked today, remembered across runs in `spent.json`."""

    def __init__(self, path: Path, models: Iterable[str], clock: Callable[[], datetime] | None = None) -> None:
        self.path = path
        self.models = tuple(models)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        self.rests: dict[str, int] = {model: 0 for model in self.models}
        held = read_json(path) if path.exists() else {}
        self.until: dict[str, datetime] = {model: datetime.fromisoformat(value) for model, value in held.items()}

    def open(self, exclude: Iterable[str] = ()) -> list[str]:
        with self.lock:
            moment = self.clock()
            return [model for model in self.models
                    if model not in exclude and self.until.get(model, moment) <= moment]

    def spend(self, model: str, why: str) -> None:
        with self.lock:
            if self.until.get(model, self.clock()) > self.clock():
                return
            self.until[model] = next_reset(self.clock())
            write_json(self.path, {name: value.isoformat() for name, value in self.until.items()})
        print(f"  {model} is spent for today ({why}); it resets at "
              f"{self.until[model].astimezone(RESET_ZONE):%H:%M %Z}", flush=True)

    def rested(self, model: str) -> int:
        with self.lock:
            self.rests[model] += 1
            return self.rests[model]

    def answered(self, model: str) -> None:
        with self.lock:
            self.rests[model] = 0


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
    """The key, the pace, the allowance and the call log, shared by every worker of a run."""

    row: Any
    allowance: Allowance
    log: Path
    max_calls: int | None = None
    gate: Pace = field(default_factory=lambda: Pace(PER_MINUTE, cooldown=30.0, cap=600.0))
    calls: int = 0
    failures: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    stopped: threading.Event = field(default_factory=threading.Event)
    send: Callable[..., Any] = call.text

    def note(self, line: dict[str, Any]) -> None:
        with self.lock, self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def ask(self, system: str, user: str, *, step: str, vocabulary: str, item: str,
            exclude: Iterable[str] = ()) -> Asked:
        """One answer from the first open model not in `exclude`, waiting out per-minute refusals."""
        while True:
            if self.stopped.is_set():
                raise DayOver()
            models = self.allowance.open(exclude)
            if not models:
                if not self.allowance.open():
                    self.stopped.set()
                    raise DayOver()
                raise NoModel()
            model = models[0]
            with self.lock:
                if self.max_calls is not None and self.calls >= self.max_calls:
                    self.stopped.set()
                    raise DayOver()
                self.calls += 1
            self.gate.acquire()
            line = {"at": now(), "step": step, "vocabulary": vocabulary, "item": item, "model": model}
            started = time.monotonic()
            try:
                result = self.send(user, row=self.row, model=model, system=system, as_json=True, timeout=TIMEOUT)
            except ProviderError as error:
                seconds = round(time.monotonic() - started, 2)
                self.note(line | {"ok": False, "reason": error.reason, "seconds": seconds, "detail": error.detail[:600]})
                if isinstance(error, ProviderRefused):
                    self.stopped.set()
                    raise Broken(f"{model} refused the call ({error.reason}): {error.detail[:300]}") from None
                if error.reason == "rate_limited":
                    if per_day(error.detail):
                        self.allowance.spend(model, "Google says its daily allowance is used")
                    elif self.allowance.rested(model) >= RESTS_TO_SPEND:
                        self.allowance.spend(model, f"{RESTS_TO_SPEND} refusals in a row")
                    else:
                        self.gate.penalise(retry_after_of(error))
                    continue
                self.failed()
                raise Failed(model, error.reason, error.detail, retry=True) from None
            seconds = round(result.answer.seconds, 2)
            spent = result.answer.spent
            self.note(line | {"ok": True, "seconds": seconds, "costUsd": result.answer.cost_usd,
                              "in": spent.input_tokens, "out": spent.output_tokens,
                              "json": result.parsed is not None})
            self.gate.succeeded()
            self.allowance.answered(model)
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


def match_batches(folder: Path, concepts: dict[str, list[Concept]], topic_names: dict[str, str]
                  ) -> dict[str, tuple[list[Concept], list[dict[str, Any]]]]:
    """Per topic, its candidate concepts and the senses of the words chosen for its concepts."""
    by_id = {c.id: c for items in concepts.values() for c in items}
    senses_of: dict[str, list[dict[str, Any]]] = {}
    reach: dict[str, set[str]] = {}
    for path in sorted((folder / "compose").glob("*.json")):
        if path.name.endswith(".failed.json"):
            continue
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
        clock: Callable[[], datetime] | None = None) -> int:
    concepts = load_concepts()
    vocabularies, topic_names = load_vocabularies()
    chosen = selected(vocabularies, args.only)
    topics = [{"name": name} for name in topic_names.values()]
    headword_system = (BUILDER_PROMPTS / "headwords.md").read_text(encoding="utf-8")
    match_system = (BUILDER_PROMPTS / "match.md").read_text(encoding="utf-8")

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
        return 0

    row = load_local().find(PROVIDER)
    if not row.available:
        print(f"{PROVIDER} cannot be called here: {row.reason()}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    caller = Caller(row=row, allowance=Allowance(out / "spent.json", MODELS, clock), log=out / "calls.jsonl",
                    max_calls=args.max_calls)
    if send is not None:
        caller.send = send
    if not caller.allowance.open():
        print("Both models are spent for today; run again after midnight in California.")
        return 0
    write_json(out / "manifest.json", {"concepts": digest(CONCEPTS.read_text(encoding="utf-8")),
                                       "prompts": {"headwords": digest(headword_system), "match": digest(match_system),
                                                   "acervo_compose": digest(prompt_text(APP_PROMPTS, "acervo_compose"))}})

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

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
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
            batches = match_batches(state.folder, concepts, topic_names)
            each([lambda v=vocabulary, t=topic, c=cands, s=senses, f=state.folder:
                  match_job(caller, v, t, c, s, match_system, f)
                  for topic, (cands, senses) in batches.items() if topic not in state.matched])
    except DayOver:
        print(f"\nStopped after {caller.calls} call(s): "
              + ("the call limit for this run." if args.max_calls is not None and caller.calls >= args.max_calls
                 else "today's allowance is used; run again tomorrow."))
    except Broken as broken:
        print(f"\nStopped: {broken}", file=sys.stderr)
        status(args, out=out)
        return 1
    else:
        print(f"\nNothing left that can be done now, after {caller.calls} call(s).")
    status(args, out=out)
    return 0


def status(args: argparse.Namespace, *, out: Path = OUT) -> int:
    concepts = load_concepts()
    vocabularies, _ = load_vocabularies()
    pictured = {c.id for items in concepts.values() for c in items if c.picture}
    print(f"\n{'vocabulary':10s} {'words':>11s} {'composed':>13s} {'demoted':>8s} {'failed':>7s} "
          f"{'matched':>8s} {'no concept':>11s} {'uncovered':>10s}")
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
        print(f"{vocabulary['id']:10s} {words:>11s} {len(state.composed):>6d}/{total:<6d} {state.demoted:>8d} "
              f"{failed:>7d} {len(state.matched):>5d}/{len(concepts):<2d} {unmatched if senses else '-':>11} "
              f"{uncovered:>10}")
    log = out / "calls.jsonl"
    if log.exists():
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        today = datetime.now(RESET_ZONE).date()
        def on_reset_day(line: dict[str, Any]) -> bool:
            return datetime.fromisoformat(line["at"].replace("Z", "+00:00")).astimezone(RESET_ZONE).date() == today
        asked = [line for line in lines if "ok" in line]
        cost = sum(line.get("costUsd") or 0 for line in asked)
        print(f"\ncalls: {sum(1 for line in asked if on_reset_day(line))} today (California day), "
              f"{len(asked)} in all; list price ${cost:.2f} (the free key pays nothing)")
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
    running.add_argument("--workers", type=int, default=WORKERS)
    running.add_argument("--dry-run", action="store_true", help="print what would be asked; call nothing")
    showing = commands.add_parser("status", help="what is done, per vocabulary")
    showing.add_argument("--only")
    marking = commands.add_parser("review", help="mark a vocabulary's word list reviewed")
    marking.add_argument("vocabulary")
    args = parser.parse_args(argv)
    return {"run": run, "status": status, "review": review}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
