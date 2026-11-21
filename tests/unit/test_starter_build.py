"""The starter builder (`scripts/starter/build.py`) against a fake model: no key, no network."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from acervo.models.errors import ProviderRefused, ProviderUnavailable
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


def article(headword: str, definition: str | None = None) -> dict[str, Any]:
    return {
        "headword": headword, "lemma": headword, "pos": "noun", "gender": None, "emoji": "🙂",
        "topics": ["Body"], "shortGloss": "word", "primaryGloss": "word", "notes": [],
        "senses": [{"definition": definition or f"a meaning of {headword}", "emoji": "🙂",
                    "glosses": [{"lang": "en", "terms": ["word"]}], "examples": []}],
    }


class Model:
    """Answers each builder step the way a well-behaved model would; tests override `refuse`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.refuse: dict[str, str] = {}   # model -> detail of a 429 it answers with
        self.definition: str | None = None  # what compose defines every sense as, if not English
        self.translation = "A meaning in English."  # what translate answers for every sense

    def __call__(self, user: str, *, row: Any, model: str, system: str, as_json: bool, timeout: float) -> TextResult:
        self.calls.append((model, user))
        if model in self.refuse:
            raise ProviderUnavailable("rate_limited", self.refuse[model], provider_id="gemini-api", model=model)
        if "Concepts (id | part of speech | meaning | note)" in user:
            ids = re.findall(r"^([a-z-]+) \|", user, re.M)
            parsed: Any = {"words": [{"concept": i, "headword": HEADWORDS[i], "lemma": HEADWORDS[i], "pos": "noun"}
                                     for i in ids]}
        elif "Write every definition in:" in user:
            sense_ids = re.findall(r"^([a-z0-9]{15}) \|", user, re.M)
            parsed = {"definitions": {sense: self.translation for sense in sense_ids}}
        elif "Senses (sense id" in user:
            sense_ids = re.findall(r"^([a-z0-9]{15}) \|", user, re.M)
            parsed = {"matches": {sense: ("mother" if "мать" in line else None)
                                  for sense, line in zip(sense_ids, re.findall(r"^[a-z0-9]{15} \|.*$", user, re.M))}}
        else:
            parsed = article(re.search(r"^Headword: (.+)$", user, re.M).group(1), self.definition)
        answer = Answer(provider_id="gemini-api", model=model, seconds=0.1, cost_usd=0.001, spent=Spent(10, 20))
        return TextResult(text=json.dumps(parsed, ensure_ascii=False), parsed=parsed, answer=answer)


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Model]:
    monkeypatch.setattr(build, "load_concepts", lambda path=None: CONCEPTS)
    monkeypatch.setattr(build, "PER_MINUTE", 0)
    monkeypatch.delenv(build.KEYS_ENV, raising=False)
    monkeypatch.setattr(build, "DICTIONARIES", tmp_path / "no-dictionaries")

    class Row:
        available = True

    monkeypatch.setattr(build, "load_local", lambda: type("P", (), {"find": lambda self, _: Row()})())
    return tmp_path / "out", Model()


def run(out: Path, model: Model, **options: Any) -> int:
    args = argparse.Namespace(only="ru", max_calls=None, workers=1, dry_run=False, keys=None,
                              parallel_keys=3, no_fallback=False, wait=False)
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


def _composed_before_the_check(out: Path, model: Model, definition: str) -> None:
    """A composed, unmatched vocabulary whose drafts define in the wrong language, as the words
    composed before compose checked a definition's language do."""
    assert run(out, model) == 0
    build.review(argparse.Namespace(vocabulary="ru"), out=out)
    assert run(out, model) == 0
    for path in (out / "ru" / "compose").glob("*.json"):
        composed = json.loads(path.read_text())
        for sense in composed["draft"]["senses"]:
            sense["definition"] = definition
        path.write_text(json.dumps(composed, ensure_ascii=False))
    for path in (out / "ru" / "match").glob("*.json"):
        path.unlink()


def test_definitions_in_the_wrong_language_are_translated_before_the_senses_are_matched(
        setup: tuple[Path, Model]) -> None:
    out, model = setup
    _composed_before_the_check(out, model, "Часть тела от плеча до кисти.")
    asked = len(model.calls)
    assert run(out, model) == 0
    steps = ["translate" if "Write every definition in:" in user else "match" for _, user in model.calls[asked:]]
    assert "translate" in steps and "match" in steps
    assert steps == sorted(steps, key=lambda step: step != "translate"), "every translation comes before a match"

    composed = [json.loads(p.read_text()) for p in (out / "ru" / "compose").glob("*.json")]
    assert all(s["definition"] == "A meaning in English." for c in composed for s in c["draft"]["senses"])
    (record,) = composed[0]["translations"]
    assert record["from"] == "Часть тела от плеча до кисти." and record["to"] == "A meaning in English."
    assert all("Часть тела" not in reply["text"] for c in composed for reply in c["replies"]), \
        "the raw replies are what the model said, and are not rewritten"
    matches = [m for p in (out / "ru" / "match").glob("*.json") for m in json.loads(p.read_text())["matches"]]
    assert matches and all(m["definition"] == "A meaning in English." for m in matches)

    asked = len(model.calls)
    assert run(out, model) == 0
    assert len(model.calls) == asked, "nothing is translated twice"


def test_a_translated_match_file_is_updated_in_place(setup: tuple[Path, Model]) -> None:
    """A vocabulary matched before its definitions were translated keeps its matches, with the new text."""
    out, model = setup
    assert run(out, model) == 0
    build.review(argparse.Namespace(vocabulary="ru"), out=out)
    assert run(out, model) == 0
    for path in (out / "ru" / "compose").glob("*.json"):
        composed = json.loads(path.read_text())
        composed["draft"]["senses"][0]["definition"] = "Часть тела."
        path.write_text(json.dumps(composed, ensure_ascii=False))
    before = {p.name: json.loads(p.read_text())["matches"] for p in (out / "ru" / "match").glob("*.json")}
    assert run(out, model) == 0
    after = {p.name: json.loads(p.read_text())["matches"] for p in (out / "ru" / "match").glob("*.json")}
    assert {n: [m["concept"] for m in ms] for n, ms in after.items()} == \
        {n: [m["concept"] for m in ms] for n, ms in before.items()}
    assert all(m["definition"] == "A meaning in English." for ms in after.values() for m in ms)


def test_a_translation_still_in_the_wrong_language_is_tried_again_then_left_for_matching(
        setup: tuple[Path, Model]) -> None:
    out, model = setup
    _composed_before_the_check(out, model, "Часть тела от плеча до кисти.")
    model.translation = "Часть тела."
    assert run(out, model) == 0
    attempts = json.loads((out / "ru" / "translate.failed.json").read_text())
    assert attempts and set(attempts.values()) == {build.GIVE_UP_AFTER}
    assert list((out / "ru" / "match").glob("*.json")), "a definition no model translates does not block matching"
    composed = [json.loads(p.read_text()) for p in (out / "ru" / "compose").glob("*.json")]
    assert all("translations" not in c for c in composed)


def test_a_translation_reply_naming_an_unknown_sense_is_refused_and_one_left_out_is_counted() -> None:
    vocabulary = {"id": "ru", "language": "ru", "definitionLang": "en", "glossLangs": ["en"], "level": "A2"}
    items = [{"id": "a" * 15, "headword": "рука"}, {"id": "b" * 15, "headword": "мать"}]
    with pytest.raises(ValueError, match="unknown sense"):
        build.read_translations({"definitions": {"c" * 15: "A hand."}}, items, vocabulary)
    usable, refused = build.read_translations({"definitions": {"a" * 15: "The arm and the hand."}}, items, vocabulary)
    assert usable == {"a" * 15: "The arm and the hand."} and refused == {"b" * 15: "left out"}
    usable, refused = build.read_translations({"definitions": {"a" * 15: "Рука.", "b" * 15: "A female parent."}},
                                              items, vocabulary)
    assert list(usable) == ["b" * 15] and "Cyrillic script" in refused["a" * 15]


def test_a_daily_refusal_moves_to_the_second_model_then_stops_the_day(setup: tuple[Path, Model]) -> None:
    out, model = setup
    model.refuse[FIRST] = "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert run(out, model) == 0
    assert {m for m, _ in model.calls} == {FIRST, SECOND}
    assert (out / "ru" / "words.json").exists()
    assert f"k1/{FIRST}" in json.loads((out / "spent.json").read_text())

    model.refuse[SECOND] = model.refuse[FIRST]
    build.review(argparse.Namespace(vocabulary="ru"), out=out)
    asked = len(model.calls)
    assert run(out, model) == 0
    assert set(json.loads((out / "spent.json").read_text())) == {f"k1/{FIRST}", f"k1/{SECOND}"}
    assert not list((out / "ru").glob("compose/*.json"))
    assert run(out, model) == 0
    assert len(model.calls) == asked + 1, "a spent model is not asked again the same day"


def test_spent_lanes_open_again_after_midnight_in_california(tmp_path: Path) -> None:
    moment = [datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)]
    lanes = [f"k1/{FIRST}", f"k1/{SECOND}"]
    allowance = build.Allowance(tmp_path / "spent.json", lanes, clock=lambda: moment[0])
    allowance.spend(lanes[0], "test")
    assert [allowance.is_open(lane) for lane in lanes] == [False, True]
    moment[0] = datetime(2026, 11, 21, 7, 59, tzinfo=timezone.utc)   # 23:59 in California
    assert [allowance.is_open(lane) for lane in lanes] == [False, True]
    assert allowance.next_open() == datetime(2026, 11, 21, 8, 0, tzinfo=timezone.utc)
    moment[0] = datetime(2026, 11, 21, 8, 1, tzinfo=timezone.utc)
    again = build.Allowance(tmp_path / "spent.json", lanes, clock=lambda: moment[0])
    assert all(again.is_open(lane) for lane in lanes) and again.next_open() is None


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
    key = build.Key("k1", None)
    caller = build.Caller(keys=[key], allowance=build.Allowance(tmp_path / "spent.json", [key.lane(m) for m in build.MODELS]),
                          log=tmp_path / "calls.jsonl")
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


# ── several keys ────────────────────────────────────────────────────────────


KEYS = "\n".join(["# a comment", "", *(f"# account {n}\nGEMINI_API_KEY_{n}=AQ.key{n}abcdefgh" for n in range(1, 6))])


def keys_file(tmp_path: Path, text: str = KEYS) -> Path:
    path = tmp_path / "keys.env"
    path.write_text(text)
    return path


def test_keys_are_read_in_file_order_and_the_last_is_the_fallback(tmp_path: Path) -> None:
    assert [label for label, _ in build.read_keys(keys_file(tmp_path))] == ["k1", "k2", "k3", "k4", "k5"]
    keys = build.keys_for(str(keys_file(tmp_path)))
    assert [k.fallback for k in keys] == [False] * 4 + [True]
    assert [k.label for k in build.keys_for(str(keys_file(tmp_path)), fallback=False)] == ["k1", "k2", "k3", "k4"]
    assert build.shown("AQ.key1abcdefgh") == "AQ.k…efgh"


@pytest.mark.parametrize("text", ["GEMINI_API_KEY_1=AQ.a\nGEMINI_API_KEY_1=AQ.b", "GEMINI_API_KEY_1=AQ.a\nGEMINI_API_KEY_2=AQ.a",
                                  "SOMETHING=AQ.a"])
def test_a_keys_file_with_a_duplicate_or_a_stray_line_is_refused(tmp_path: Path, text: str) -> None:
    with pytest.raises(ValueError):
        build.read_keys(keys_file(tmp_path, text))


def test_only_the_keys_in_parallel_are_asked_and_the_next_takes_over_when_one_is_spent(
        setup: tuple[Path, Model], tmp_path: Path) -> None:
    out, model = setup
    keys = build.keys_for(str(keys_file(tmp_path)))
    asked: list[str] = []

    def send(user: str, *, row: Any, model: str, **_: Any) -> TextResult:
        asked.append(row.id)
        if row.id == "gemini-k1":
            raise ProviderUnavailable("rate_limited", "Quota: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                      provider_id=row.id, model=model)
        return Model()(user, row=row, model=model, system="", as_json=True, timeout=1)

    caller = build.Caller(keys=keys, allowance=build.Allowance(out / "spent.json", [k.lane(m) for k in keys for m in build.MODELS]),
                          log=tmp_path / "calls.jsonl", parallel_keys=2)
    caller.send = send
    for _ in range(6):
        caller.ask("s", "Concepts (id | part of speech | meaning | note)\narm | noun | y", step="t", vocabulary="v", item="i")
    # k1 is spent on both models, so k2 and k3 are the two in use; k4, k5 (fallback) are never asked.
    assert set(asked) <= {"gemini-k1", "gemini-k2", "gemini-k3"} and "gemini-k4" not in asked
    assert {r for r in asked[2:]} <= {"gemini-k2", "gemini-k3"}
    assert json.loads((tmp_path / "calls.jsonl").read_text().splitlines()[-1])["key"] in {"k2", "k3"}


def test_the_fallback_is_asked_only_when_the_other_keys_are_spent(tmp_path: Path) -> None:
    keys = [build.Key("k1", None), build.Key("k2", None, fallback=True)]
    allowance = build.Allowance(tmp_path / "spent.json", [k.lane(m) for k in keys for m in build.MODELS])
    caller = build.Caller(keys=keys, allowance=allowance, log=tmp_path / "calls.jsonl")
    assert [k.label for k, _ in caller.eligible(())] == ["k1"]
    for model in build.MODELS:
        allowance.spend(keys[0].lane(model), "test")
    assert [k.label for k, _ in caller.eligible(())] == ["k2"]
    for model in build.MODELS:
        allowance.spend(keys[1].lane(model), "test")
    assert not caller.any_open()


def test_a_rejected_key_is_dropped_and_the_others_carry_on(tmp_path: Path) -> None:
    keys = [build.Key("k1", "bad"), build.Key("k2", "good")]
    caller = build.Caller(keys=keys, allowance=build.Allowance(tmp_path / "spent.json", [k.lane(m) for k in keys for m in build.MODELS]),
                          log=tmp_path / "calls.jsonl")

    def send(user: str, *, row: Any, model: str, **_: Any) -> TextResult:
        if row == "bad":
            raise ProviderRefused("auth", "API key not valid", provider_id="gemini-api", model=model)
        return Model()(user, row=row, model=model, system="", as_json=True, timeout=1)

    caller.send = send
    caller.ask("s", "Concepts (id | part of speech | meaning | note)\narm | noun | y", step="t", vocabulary="v", item="i")
    assert caller.dropped == {"k1"} and not caller.stopped.is_set()
    lines = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [(line["key"], line["ok"]) for line in lines] == [("k1", False), ("k2", True)]


def test_wait_sleeps_to_the_reset_and_then_carries_on(setup: tuple[Path, Model], tmp_path: Path) -> None:
    out, model = setup
    moment = [datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        moment[0] += timedelta(seconds=seconds)

    model.refuse[FIRST] = model.refuse[SECOND] = "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    original = model.__call__

    def send(*args: Any, **kwargs: Any) -> TextResult:
        if moment[0] >= datetime(2026, 11, 21, 8, 0, tzinfo=timezone.utc):
            model.refuse.clear()
        return original(*args, **kwargs)

    args = argparse.Namespace(only="ru", max_calls=None, workers=1, dry_run=False, keys=None,
                              parallel_keys=3, no_fallback=False, wait=True)
    assert build.run(args, out=out, send=send, clock=lambda: moment[0], sleep=sleep) == 0
    assert sum(slept) >= 12 * 3600 and max(slept) <= 30.0
    assert (out / "ru" / "words.json").exists(), "after the reset the words were asked for"
