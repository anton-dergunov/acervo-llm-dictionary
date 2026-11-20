"""The starter builder (`scripts/starter/build.py`) against a fake model: no key, no network."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from acervo.models.errors import ProviderUnavailable
from acervo.models.results import Answer, Spent, TextResult
from acervo.services.capture.compose import compose_parts
from acervo.services.models import Demoted, Unusable
from acervo.services.prompts import prompt_text
from acervo.services.reader import reader_section

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("starter_build", REPO_ROOT / "scripts" / "starter" / "build.py")
build = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = build
_spec.loader.exec_module(build)

FIRST, SECOND = build.MODELS
CONCEPTS = {
    "body": [
        build.Concept("arm", "body", "the limb from shoulder to hand", "noun", None, (), True),
        build.Concept("hand", "body", "the part at the end of the arm", "noun", None, (), True),
    ],
    "people": [build.Concept("mother", "people", "a female parent", "noun", None, (), True)],
}
HEADWORDS = {"arm": "рука", "hand": "рука", "mother": "мать"}


def article(headword: str) -> dict[str, Any]:
    return {
        "headword": headword, "lemma": headword, "pos": "noun", "gender": None, "emoji": "🙂",
        "topics": ["Body"], "shortGloss": "word", "primaryGloss": "word", "notes": [],
        "senses": [{"definition": f"a meaning of {headword}", "emoji": "🙂",
                    "glosses": [{"lang": "en", "terms": ["word"]}], "examples": []}],
    }


class Model:
    """Answers each builder step the way a well-behaved model would; tests override `refuse`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.refuse: dict[str, str] = {}   # model -> detail of a 429 it answers with

    def __call__(self, user: str, *, row: Any, model: str, system: str, as_json: bool, timeout: float) -> TextResult:
        self.calls.append((model, user))
        if model in self.refuse:
            raise ProviderUnavailable("rate_limited", self.refuse[model], provider_id="gemini-api", model=model)
        if "Concepts (id | part of speech | meaning | note)" in user:
            ids = re.findall(r"^([a-z-]+) \|", user, re.M)
            parsed: Any = {"words": [{"concept": i, "headword": HEADWORDS[i], "lemma": HEADWORDS[i], "pos": "noun"}
                                     for i in ids]}
        elif "Senses (sense id" in user:
            sense_ids = re.findall(r"^([a-z0-9]{15}) \|", user, re.M)
            parsed = {"matches": {sense: ("mother" if "мать" in line else None)
                                  for sense, line in zip(sense_ids, re.findall(r"^[a-z0-9]{15} \|.*$", user, re.M))}}
        else:
            parsed = article(re.search(r"^Headword: (.+)$", user, re.M).group(1))
        answer = Answer(provider_id="gemini-api", model=model, seconds=0.1, cost_usd=0.001, spent=Spent(10, 20))
        return TextResult(text=json.dumps(parsed, ensure_ascii=False), parsed=parsed, answer=answer)


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Model]:
    monkeypatch.setattr(build, "load_concepts", lambda path=None: CONCEPTS)
    monkeypatch.setattr(build, "PER_MINUTE", 0)
    monkeypatch.setattr(build, "DICTIONARIES", tmp_path / "no-dictionaries")

    class Row:
        available = True

    monkeypatch.setattr(build, "load_local", lambda: type("P", (), {"find": lambda self, _: Row()})())
    return tmp_path / "out", Model()


def run(out: Path, model: Model, **options: Any) -> int:
    args = argparse.Namespace(only="ru", max_calls=None, workers=1, dry_run=False)
    for name, value in options.items():
        setattr(args, name, value)
    return build.run(args, out=out, send=model)


def test_a_word_list_waits_for_review_then_composes_and_matches(setup: tuple[Path, Model]) -> None:
    out, model = setup
    assert run(out, model) == 0
    words = json.loads((out / "ru" / "words.json").read_text())["words"]
    # рука serves two concepts and becomes one word carrying both.
    assert [(w["headword"], w["concepts"]) for w in words] == [("рука", ["arm", "hand"]), ("мать", ["mother"])]
    assert len(model.calls) == 2 and not (out / "ru" / "compose").exists()

    build.review(argparse.Namespace(vocabulary="ru"), out=out)
    assert run(out, model) == 0
    composed = sorted((out / "ru" / "compose").glob("*.json"))
    assert len(composed) == 2
    hand = next(json.loads(p.read_text()) for p in composed if "рука" in p.read_text())
    assert "each of these meanings: the limb from shoulder to hand; the part at the end of the arm" in \
        hand["request"]["user"]
    matches = [m for p in (out / "ru" / "match").glob("*.json") for m in json.loads(p.read_text())["matches"]]
    assert sorted(m["concept"] or "-" for m in matches) == ["-", "mother"]

    asked = len(model.calls)
    assert run(out, model) == 0
    assert len(model.calls) == asked, "a finished vocabulary is never asked again"


def test_a_daily_refusal_moves_to_the_second_model_then_stops_the_day(setup: tuple[Path, Model]) -> None:
    out, model = setup
    model.refuse[FIRST] = "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert run(out, model) == 0
    assert {m for m, _ in model.calls} == {FIRST, SECOND}
    assert (out / "ru" / "words.json").exists()
    assert FIRST in json.loads((out / "spent.json").read_text())

    model.refuse[SECOND] = model.refuse[FIRST]
    build.review(argparse.Namespace(vocabulary="ru"), out=out)
    asked = len(model.calls)
    assert run(out, model) == 0
    assert set(json.loads((out / "spent.json").read_text())) == {FIRST, SECOND}
    assert not list((out / "ru").glob("compose/*.json"))
    assert run(out, model) == 0
    assert len(model.calls) == asked + 1, "a spent model is not asked again the same day"


def test_spent_models_open_again_after_midnight_in_california(tmp_path: Path) -> None:
    moment = [datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)]
    allowance = build.Allowance(tmp_path / "spent.json", build.MODELS, clock=lambda: moment[0])
    allowance.spend(FIRST, "test")
    assert allowance.open() == [SECOND]
    moment[0] = datetime(2026, 11, 21, 7, 59, tzinfo=timezone.utc)   # 23:59 in California
    assert allowance.open() == [SECOND]
    moment[0] = datetime(2026, 11, 21, 8, 1, tzinfo=timezone.utc)
    assert build.Allowance(tmp_path / "spent.json", build.MODELS, clock=lambda: moment[0]).open() == list(build.MODELS)


def _compose_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, verdicts: dict[str, Exception | None]) -> Path:
    """Compose one word where each model's answer meets the given verdict."""
    def parts(*args: Any, **kwargs: Any):
        def check(parsed: Any):
            verdict = verdicts[parsed["by"]]
            if verdict is not None:
                raise verdict
            from acervo.services.capture.vet import Vetted
            return Vetted(article("мать"))
        return "system", "Headword: мать", check

    def send(user: str, *, model: str, **_: Any) -> TextResult:
        answer = Answer(provider_id="gemini-api", model=model, seconds=0.1, cost_usd=None)
        return TextResult(text="{}", parsed={"by": model}, answer=answer)

    monkeypatch.setattr(build, "compose_parts", parts)
    tmp_path.mkdir(parents=True, exist_ok=True)
    caller = build.Caller(row=None, allowance=build.Allowance(tmp_path / "spent.json", build.MODELS),
                          log=tmp_path / "calls.jsonl", gate=build.Pace(0))
    caller.send = send
    word = {"key": "mat", "headword": "мать", "lemma": "мать", "pos": "noun", "concepts": ["mother"],
            "senses": ["a female parent"], "topics": ["People"]}
    vocabulary = {"id": "ru", "language": "ru", "definitionLang": "en", "glossLangs": ["en"], "level": "A2"}
    build.compose_job(caller, vocabulary, word, [{"name": "People"}], tmp_path)
    return tmp_path / "compose"


def test_a_doubted_answer_asks_the_other_model_and_keeps_the_first_doubt(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    doubt = Demoted("the dictionary disagrees", checked=None, by="dictionary")
    from acervo.services.capture.vet import Vetted
    doubt.checked = Vetted(article("мать"))
    folder = _compose_with(monkeypatch, tmp_path, {FIRST: doubt, SECOND: None})
    saved = json.loads((folder / "mat.json").read_text())
    assert saved["outcome"] == "passed" and saved["model"].endswith(SECOND)

    folder = _compose_with(monkeypatch, tmp_path / "both", {FIRST: doubt, SECOND: doubt})
    saved = json.loads((folder / "mat.json").read_text())
    assert saved["outcome"] == "demoted" and saved["model"].endswith(FIRST)


def test_an_answer_no_model_gets_right_is_tried_again_then_left_out(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    refusal = Unusable("the glosses are in Cyrillic script")
    for attempt in range(1, build.GIVE_UP_AFTER + 1):
        folder = _compose_with(monkeypatch, tmp_path, {FIRST: refusal, SECOND: refusal})
        assert json.loads((folder / "mat.failed.json").read_text())["attempts"] == attempt
    state = build.State(vocabulary={}, folder=tmp_path, topics_done=set(),
                        words=[{"key": "mat"}], reviewed=True, composed=set(), demoted=0,
                        failed={"mat": build.GIVE_UP_AFTER}, matched={})
    assert state.to_compose == [] and state.composing_done


def test_a_match_naming_an_unknown_concept_or_leaving_a_sense_out_is_refused() -> None:
    candidates = CONCEPTS["body"]
    senses = [{"id": "a" * 15}, {"id": "b" * 15}]
    assert build.read_matches({"matches": {"a" * 15: "arm", "b" * 15: None}}, candidates, senses) == \
        {"a" * 15: "arm", "b" * 15: None}
    with pytest.raises(ValueError, match="unknown concept"):
        build.read_matches({"matches": {"a" * 15: "leg", "b" * 15: None}}, candidates, senses)
    with pytest.raises(ValueError, match="left out"):
        build.read_matches({"matches": {"a" * 15: "arm"}}, candidates, senses)


def test_a_headword_reply_with_an_invented_concept_or_part_of_speech_is_refused() -> None:
    concepts = CONCEPTS["body"]
    words, missing = build.read_headwords(
        {"words": [{"concept": "arm", "headword": "рука", "pos": "noun"}]}, concepts)
    assert words[0]["lemma"] == "рука" and missing == ["hand"]
    with pytest.raises(ValueError, match="unknown concept"):
        build.read_headwords({"words": [{"concept": "leg", "headword": "нога", "pos": "noun"}]}, concepts)
    with pytest.raises(ValueError, match="part of speech"):
        build.read_headwords({"words": [{"concept": "arm", "headword": "рука", "pos": "prep"}]}, concepts)


def test_the_builder_sends_composes_own_prompt_and_reader_section(tmp_path: Path) -> None:
    vocabulary = {"language": "es", "definitionLang": "en", "glossLangs": ["en"], "level": "A2", "region": "MX"}
    resolution = {"language": "es", "headword": "la madre", "lemma": "madre", "pos": "noun", "sentences": []}
    system, user, _ = compose_parts(REPO_ROOT / "prompts", tmp_path, resolution, {}, vocabulary, [])
    assert system == prompt_text(REPO_ROOT / "prompts", "acervo_compose") + "\n\n" + reader_section(vocabulary)
    assert "Headword: la madre" in user
