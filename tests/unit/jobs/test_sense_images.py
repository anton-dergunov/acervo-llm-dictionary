"""The pure halves of the sense-image stage: ids, style menus, reply parsing, and the plan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acervo.article import build_articles
from acervo.images.article import anchor_for, drawn_senses
from acervo.images.brief import build_request, parse_reply
from acervo.images.compose import FRAME, compose, prompt_version
from acervo.images.ids import ID_LENGTH, image_prompt_id, image_reference, seed_for
from acervo.images.styles import load_styles
from acervo.jobs.images.run import Store, plan

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES = REPO_ROOT / "config" / "image-styles.yaml"
TEMPLATE = REPO_ROOT / "prompts" / "acervo_image_brief.md"


def sync_fields(revision: int = 1) -> dict:
    return {
        "deleted": False, "createdAt": "2026-09-01T00:00:00.000Z",
        "editedAt": "2026-09-01T00:00:00.000Z", "editedBy": "dev", "revision": revision,
    }


def changes() -> dict:
    return {
        "vocabularies": [{"id": "v00000000000001", "language": "es", "definitionLang": "es",
                          "glossLangs": ["en"], "notesLang": "en", **sync_fields()}],
        "topics": [{"id": "t00000000000001", "name": "Nature", **sync_fields()}],
        "lexemes": [
            {"id": "l00000000000001", "language": "es", "headword": "el veneno", "lemma": "veneno",
             "pos": "noun", "status": "inbox", "topicIds": ["t00000000000001"], "notes": [],
             "shortGloss": "venom", **sync_fields()},
            {"id": "l00000000000002", "language": "es", "headword": "retirado", "lemma": "retirado",
             "pos": "adj", "status": "aside", "topicIds": [], "notes": [], **sync_fields()},
            {"id": "l00000000000003", "language": "en", "headword": "venom", "lemma": "venom",
             "pos": "noun", "status": "active", "topicIds": [], "notes": [], **sync_fields()},
        ],
        "senses": [
            {"id": "s00000000000001", "lexemeId": "l00000000000001", "definition": "Fluido tóxico.",
             "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["venom"]}], "domain": None,
             "order": 0, **sync_fields()},
            {"id": "s00000000000002", "lexemeId": "l00000000000001", "definition": "Amargura extrema.",
             "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["bitterness"]}],
             "domain": None, "order": 1, **sync_fields()},
            {"id": "s00000000000003", "lexemeId": "l00000000000002", "definition": "Jubilado.",
             "definitionLang": "es", "glosses": [], "domain": None, "order": 0, **sync_fields()},
            {"id": "s00000000000004", "lexemeId": "l00000000000003", "definition": "Toxic fluid.",
             "definitionLang": "en", "glosses": [], "domain": None, "order": 0, **sync_fields()},
        ],
        "examples": [
            {"id": "e00000000000001", "senseId": "s00000000000001", "text": "Una serpiente inyecta veneno.",
             "translation": "A snake injects venom.", "origin": "llm", **sync_fields()},
            {"id": "e00000000000002", "senseId": "s00000000000001", "text": "El veneno me quemó.",
             "translation": "The venom burned me.", "origin": "attestation", **sync_fields()},
            {"id": "e00000000000003", "senseId": "s00000000000002", "text": "Habla con veneno.",
             "translation": "She speaks with venom.", "origin": "subtitle",
             "videoRef": "https://youtu.be/od_YtGbRC48", "clipRef": "seg_1f4c9a2b7e6d5c3a0b91",
             **sync_fields()},
        ],
        "attestations": [],
        "imagePrompts": [],
        "studyStates": [],
    }


def test_the_derived_id_is_the_one_the_interface_derives_too():
    """The other half of the check is `web/src/ids.test.ts`, which pins these same values.

    Two engines converge on one row only because both compute the same id from the sense. When the
    interface minted a random one instead, importing a bundle produced *two* rows for one sense —
    the document's and the restored picture's — which reads as a duplicate picture rather than as an
    error, so nothing catches it but this.
    """
    assert image_prompt_id("sensepicaritch0") == "otxot3jm55or06a"
    assert image_prompt_id("oj3y4cakuelbgrd") == "0088hcytqci2gl0"
    assert image_prompt_id("a") == "rtggsgprao8u2o3"
    assert image_prompt_id("") == "5el2yfarsw7agle"


def test_ids_are_acervo_shaped_and_stable():
    minted = image_prompt_id("s00000000000001")
    assert len(minted) == ID_LENGTH
    assert minted.isalnum() and minted.islower()
    assert minted == image_prompt_id("s00000000000001")
    assert minted != image_prompt_id("s00000000000002")


def test_a_retry_draws_a_different_seed():
    assert seed_for("s00000000000001", 1) == seed_for("s00000000000001", 1)
    assert seed_for("s00000000000001", 1) != seed_for("s00000000000001", 2)


def test_every_style_is_offered():
    styles = load_styles(STYLES)
    assert [style.id for style in styles.offer()] == [style.id for style in styles.styles]


def test_a_zero_weight_switches_a_style_off():
    styles = load_styles(STYLES)
    weights = {style.id: 0.0 for style in styles.styles}
    for style in styles.styles[:2]:
        weights[style.id] = 1.0
    assert {style.id for style in styles.offer(weights)} == {style.id for style in styles.styles[:2]}


def test_the_style_hints_are_a_shifting_sample():
    """Round 5 sent each style's whole hint as one sentence and it became a lookup table.

    A short sample per lexeme keeps the associations without letting a style be matched on.
    """
    styles = load_styles(STYLES)
    assert all(len(style.when) >= 6 for style in styles.styles)
    clay = styles["claymation"]
    first, second = styles.hints(clay, "lex000000000001"), styles.hints(clay, "lex000000000002")
    assert len(first) == 3 and set(first) <= set(clay.when)
    assert first != second                                     # varies per word
    assert first == styles.hints(clay, "lex000000000001")       # but is stable for one word

    request = build_request(build_articles(changes(), "es")[0], styles)
    assert all(len(item["suits"]) == 3 for item in request["styles"])


def test_the_style_that_authored_scenes_is_gone():
    """Round 1: leaded glass implies a building, so it kept relocating the scene to a church."""
    assert "stained-glass" not in load_styles(STYLES)


def test_only_the_senses_worth_drawing_are_in_scope():
    articles = build_articles(changes(), "es")
    assert [article.headword for article in articles] == ["el veneno"]      # retired is out, en is out
    assert len(articles[0].senses) == 2


def test_the_learners_own_sentence_is_the_anchor():
    articles = build_articles(changes(), "es")
    anchor = anchor_for(articles[0].senses[0])
    assert anchor["id"] == "e00000000000002"                                 # attestation beats llm


def test_a_clip_anchors_a_picture_when_it_is_the_only_sentence():
    """Sense two has one example and it is a clip, so the picture is drawn from the clip's sentence.

    A clip's sentence makes a good scene, and the picture and the clip share one card.
    """
    sense = build_articles(changes(), "es")[0].senses[1]
    assert [example["origin"] for example in sense.examples] == ["subtitle"]
    assert anchor_for(sense)["origin"] == "subtitle"


def test_a_written_sentence_outranks_a_clip():
    sense = build_articles(changes(), "es")[0].senses[1]
    written = {**sense.examples[0], "id": "e00000000000099", "origin": "tatoeba"}
    richer = type(sense)(**{**sense.__dict__, "examples": [sense.examples[0], written]})
    assert anchor_for(richer)["id"] == "e00000000000099"


def test_a_generated_sentence_outranks_a_borrowed_one():
    """It is written for *this* sense, in the vocabulary's own languages, carrying a translation and
    both matched forms. Tatoeba and Wiktionary are chosen for neither and read worse."""
    from acervo.images.article import EXAMPLE_PREFERENCE

    assert EXAMPLE_PREFERENCE["llm"] < EXAMPLE_PREFERENCE["tatoeba"] < EXAMPLE_PREFERENCE["wiktionary"]
    assert EXAMPLE_PREFERENCE["subtitle"] == max(EXAMPLE_PREFERENCE.values())


def test_the_owners_topics_do_not_steer_the_picture():
    """Topics are the owner's filing system, not a fact about the word."""
    request = build_request(build_articles(changes(), "es")[0], load_styles(STYLES))
    assert "topics" not in request


def test_an_anchor_from_another_sense_is_dropped():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    payload, offered = _reply(article, styles, patch={1: {"anchorExampleId": "e00000000000002"}})
    briefs = parse_reply(payload, article, offered)
    assert briefs[1].anchor_example_id is None      # that example belongs to sense one


def test_an_anchor_from_this_sense_is_kept():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    payload, offered = _reply(article, styles, patch={0: {"anchorExampleId": "e00000000000002"}})
    assert parse_reply(payload, article, offered)[0].anchor_example_id == "e00000000000002"


def test_the_request_offers_every_style_and_marks_the_anchor():
    styles = load_styles(STYLES)
    request = build_request(build_articles(changes(), "es")[0], styles)
    assert len(request["senses"]) == 2
    assert len(request["styles"]) == len(styles.styles)
    marked = [item for item in request["senses"][0]["examples"] if item["isAnchor"]]
    assert [item["id"] for item in marked] == ["e00000000000002"]


def _reply(article, styles, **overrides) -> tuple[dict, tuple[str, ...]]:
    offered = tuple(style.id for style in styles.offer())
    senses = [
        {"senseId": sense.id, "styleId": offered[index], "anchorExampleId": None,
         "situation": "A specific thing happening.", "subject": "the thing",
         "brief": "A scene.", "refused": False, "refusalReason": None}
        for index, sense in enumerate(article.senses)
    ]
    for index, patch in overrides.get("patch", {}).items():
        senses[index].update(patch)
    return {"senses": senses}, offered


def test_a_well_formed_reply_parses():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    payload, offered = _reply(article, styles)
    briefs = parse_reply(payload, article, offered)
    assert [item.sense_id for item in briefs] == [sense.id for sense in article.senses]
    assert all(not item.refused for item in briefs)
    assert briefs[0].subject == "the thing"
    assert briefs[0].situation == "A specific thing happening."


def test_a_reply_that_was_not_json_is_refused():
    """Unfencing and `json.loads` belong to `models.call`, which does them for every kind of reply
    and hands back None when the text was not readable. This is what that None means here."""
    article = build_articles(changes(), "es")[0]
    with pytest.raises(ValueError, match="did not return JSON"):
        parse_reply(None, article, ())


def test_an_invented_style_is_refused():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    payload, offered = _reply(article, styles, patch={0: {"styleId": "no-such-style"}})
    with pytest.raises(ValueError, match="not a style"):
        parse_reply(payload, article, offered)


def test_a_skipped_sense_is_refused():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    payload, offered = _reply(article, styles)
    payload["senses"] = payload["senses"][:1]
    with pytest.raises(ValueError, match="skipped"):
        parse_reply(payload, article, offered)


def test_a_refusal_needs_no_style_or_brief():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    payload, offered = _reply(article, styles, patch={
        1: {"refused": True, "styleId": "", "brief": None, "refusalReason": "hate insignia"}})
    briefs = parse_reply(payload, article, offered)
    assert briefs[1].refused and briefs[1].refusal_reason == "hate insignia"


def test_the_composed_prompt_carries_the_style_and_bans_text():
    styles = load_styles(STYLES)
    prompt = compose("A snake's fang, one glowing droplet.", styles["oil-painting"])
    assert "impasto oil" in prompt
    assert FRAME in prompt
    assert "no letters" in prompt.lower()


def test_the_prompt_version_moves_when_the_styles_do(tmp_path: Path):
    styles = load_styles(STYLES)
    first = prompt_version(TEMPLATE, styles.digest)
    assert first != prompt_version(TEMPLATE, "deadbeef0000")
    other = tmp_path / "template.txt"
    other.write_text("different", encoding="utf-8")
    assert first != prompt_version(other, styles.digest)


def test_a_drawn_sense_is_not_planned_again(tmp_path: Path):
    articles = build_articles(changes(), "es")
    store = Store(tmp_path)
    assert len(plan(articles, store, drawn=set())) == 2

    store.image_path(image_prompt_id("s00000000000001")).write_bytes(b"webp")
    assert [job.sense_id for job in plan(articles, store, drawn=set())] == ["s00000000000002"]

    # Deleting the picture is how a rejection is expressed, and it comes back into the plan.
    store.image_path(image_prompt_id("s00000000000001")).unlink()
    assert len(plan(articles, store, drawn=set())) == 2


def test_a_sense_the_graph_already_holds_an_image_for_is_skipped(tmp_path: Path):
    payload = changes()
    payload["imagePrompts"] = [{
        "id": "p00000000000001", "lexemeId": "l00000000000001", "senseId": "s00000000000001",
        "prompt": "A scene.", "styleId": "oil-painting", "seed": 1, "modelId": "m",
        "promptVersion": "v", "imageRef": "images/l1/p1.webp", "imageModelId": "m",
        **sync_fields(),
    }]
    assert len(plan(build_articles(payload, "es"), Store(tmp_path), drawn=drawn_senses(payload))) == 1


LITE = ("vertex", "lite")
KLEIN = ("cloudflare", "klein")


def test_each_pair_has_its_own_bucket():
    """Measured: about one image per minute PER MODEL, so two run at twice the rate.

    Keyed by the pair rather than the bare model id, because an adapter row names its models
    unprefixed and two providers offering the same id would otherwise share one gate."""
    from acervo.models.pacing import ModelPool
    pool = ModelPool([(LITE, 1), (KLEIN, 1)])
    assert sorted([pool.acquire(), pool.acquire()]) == sorted([LITE, KLEIN])
    assert pool.gates[LITE].delay() > 0 and pool.gates[KLEIN].delay() > 0


def test_a_quota_pause_is_per_pair_not_pool_wide():
    from acervo.models.pacing import ModelPool
    pool = ModelPool([(LITE, 60), (KLEIN, 60)])
    pool.penalise(LITE)
    assert pool.gates[LITE].delay() > 0
    assert pool.acquire() == KLEIN      # the other pair keeps working


def test_a_provider_that_says_how_long_to_wait_is_believed_over_the_doubling():
    """Cloudflare's image allowance is a daily one that hard stops. Doubling from 30s caps at five
    minutes, which is a lot of 429s between now and midnight."""
    from acervo.models.pacing import ModelPool
    pool = ModelPool([(KLEIN, 60)])
    assert pool.penalise(KLEIN, retry_after=1800.0) == 1800.0


def test_the_definition_is_labelled_with_its_own_language():
    """An English gloss carries metaphors the original word does not: `estar fundado` is not about
    earth, but "to be grounded in" is, and the picture followed the gloss."""
    request = build_request(build_articles(changes(), "es")[0], load_styles(STYLES))
    sense = request["senses"][0]
    assert sense["definitionLang"] == "es"
    assert sense["definition"] == "Fluido tóxico."
    assert sense["glosses"] == [{"lang": "en", "terms": ["venom"]}]


def test_a_refusal_is_not_planned_again(tmp_path: Path):
    """§06: declining a sense is a finished outcome. Re-planning it spends a call to rediscover it."""
    articles = build_articles(changes(), "es")
    store = Store(tmp_path)
    assert len(plan(articles, store, drawn=set())) == 2

    store.write(store.refusal_path(image_prompt_id("s00000000000001")),
                {"refusalReason": "sexualised imagery"})
    assert [job.sense_id for job in plan(articles, store, drawn=set())] == ["s00000000000002"]
    assert len(plan(articles, store, drawn=set(), redo=True)) == 2        # unless asked


def test_a_provider_block_is_not_planned_again(tmp_path: Path):
    """A blocked prompt is terminal. Ten senses were lost to a text 429 and one to an image block;
    only the first kind should come back."""
    articles = build_articles(changes(), "es")
    store = Store(tmp_path)
    blocked = image_prompt_id("s00000000000001")
    store.write(store.record_path(blocked), {"id": blocked, "imageRef": None, "blocked": True})
    transient = image_prompt_id("s00000000000002")
    store.write(store.record_path(transient),
                {"id": transient, "imageRef": None, "failureReason": "429 RESOURCE_EXHAUSTED"})

    assert [job.sense_id for job in plan(articles, store, drawn=set())] == ["s00000000000002"]
    assert len(plan(articles, store, drawn=set(), redo=True)) == 2


def test_the_laptop_run_waits_out_a_chain_that_is_entirely_over_quota():
    """A text 429 used to lose every sense of that lexeme outright. With a chain the first 429 is
    answered by the next provider, so the run waits only when every pair has refused — and the run
    is where that waiting lives, not the brief writer."""
    from acervo.jobs.images.run import Runner
    from acervo.models import ChainExhausted, ProviderUnavailable

    class Flaky:
        calls = 0

        def write(self, article):
            self.calls += 1
            if self.calls < 3:
                raise ChainExhausted((("vertex", "m"),), ProviderUnavailable("rate_limited", "429"))
            return ["ok"], {"model": "m"}

    runner, slept = Runner.__new__(Runner), []
    runner.writer, runner.wait = Flaky(), slept.append
    briefs, _ = runner._write(build_articles(changes(), "es")[0])
    assert briefs == ["ok"] and runner.writer.calls == 3
    assert slept == [15.0, 30.0]               # and it backs off rather than hammering


def test_a_brief_failure_that_is_not_quota_is_raised_at_once():
    from acervo.images.brief import BriefWriter

    class Broken(BriefWriter):
        def __init__(self):
            self.calls = 0

        def _write_once(self, article):
            self.calls += 1
            raise ValueError("the brief writer did not return JSON")

    writer = Broken()
    with pytest.raises(ValueError):
        writer.write(build_articles(changes(), "es")[0])
    assert writer.calls == 1


def _stored(store: Store, sense_id: str, data: bytes = b"webp", **overrides) -> str:
    """A record, and the reference it would carry for `data` — which is what `verify` checks."""
    identifier = image_prompt_id(sense_id)
    record = {
        "id": identifier, "senseId": sense_id, "lexemeId": "x",
        "imageRef": image_reference("x", identifier, data),
    }
    record.update(overrides)
    store.write(store.record_path(identifier), record)
    return identifier


def test_a_file_that_is_not_what_its_reference_names_is_a_fault(tmp_path: Path):
    """The reference carries a digest of the bytes, so a picture swapped in the run directory after
    it was drawn is caught here rather than published under a name promising something else."""
    from acervo.jobs.images.verify import verify
    store = Store(tmp_path)
    identifier = _stored(store, "s00000000000001")
    store.image_path(identifier).write_bytes(b"different bytes entirely")
    report = verify(store)
    assert not report.ok
    assert "reference does not name the bytes on disk" in report.problems


def test_a_consistent_run_directory_verifies(tmp_path: Path):
    from acervo.jobs.images.verify import verify
    store = Store(tmp_path)
    identifier = _stored(store, "s00000000000001")
    store.image_path(identifier).write_bytes(b"webp")
    report = verify(store)
    assert report.ok and report.drawn == 1 and report.images == 1


def test_verify_catches_what_would_break_the_import(tmp_path: Path):
    from acervo.jobs.images.verify import verify
    store = Store(tmp_path)

    _stored(store, "s00000000000001")                      # claims an image that is not there
    orphan = _stored(store, "s00000000000002", imageRef=None)
    store.image_path(orphan).write_bytes(b"webp")          # image whose record claims none
    store.image_path("zzzzzzzzzzzzzzz").write_bytes(b"webp")  # image with no record at all
    store.write(store.record_path("nnnnnnnnnnnnnnn"),
                {"id": "nnnnnnnnnnnnnnn", "senseId": "s00000000000003", "imageRef": None})

    report = verify(store)
    assert not report.ok
    assert set(report.problems) == {
        "record claims an image that is not on disk",
        "image on disk whose record claims none",
        "image with no record",
        "id is not derived from its senseId",
    }


def test_a_blocked_record_is_not_a_problem(tmp_path: Path):
    """`snort` was blocked by the provider. A sense with no image is complete, not a fault."""
    from acervo.jobs.images.verify import verify
    store = Store(tmp_path)
    _stored(store, "s00000000000001", imageRef=None, blocked=True, failureReason="IMAGE_SAFETY")
    report = verify(store)
    assert report.ok and report.blocked == 1 and report.drawn == 0


# ── the chain, at the two call sites ────────────────────────────────────────
# The providers, the adapter and the pacing were built by the provider package; what these
# cover is that the image job actually goes through them and records what answered.


def _candidates(*pairs):
    """Resolved candidates over throwaway providers, which nothing calls."""
    from acervo.models import chain
    from acervo.models.providers import Providers, parse

    rows = tuple(
        parse({"id": provider, "family": "cloudflare", "settings": {"accountId": "a" * 32},
               "models": {"text": [model], "image": [model]}}, {"key": "a-throwaway-token-0123"})
        for provider, model in dict.fromkeys((pair[0], pair[1]) for pair in pairs)
    )
    catalogue = Providers(rows)
    return catalogue, chain.resolve("image", list(pairs), catalogue)


def _drawing(answers):
    """A renderer that answers from a script, one entry per call, keyed by pair."""
    from acervo.images.render import Rendered

    class Scripted:
        def __init__(self):
            self.size = (1024, 1024)
            self.asked = []

        def draw(self, prompt, seed, candidate):
            self.asked.append(candidate.named)
            outcome = answers[candidate.named]
            if isinstance(outcome, BaseException):
                raise outcome
            # The bytes, not a file: the run writes them, and the server path is a digest of them.
            return Rendered(b"webp", outcome)

    return Scripted()


def _answer(provider, model):
    from acervo.models.results import Answer
    return Answer(provider_id=provider, model=model, seconds=0.1, cost_usd=0.03,
                  attempts=((provider, model),))


def _runner(tmp_path, renderer, candidates, briefs, **extra):
    from acervo.jobs.images.run import Runner

    styles = load_styles(STYLES)

    class Writer:
        def write(self, article):
            return briefs(article, styles), {"model": "brief-model", "costUsd": 0.001}

    return Runner(store=Store(tmp_path), writer=Writer(), renderer=renderer, styles=styles,
                  template_path=TEMPLATE, candidates=candidates, workers=1, rate_limit=0,
                  report=lambda _line: None, **extra), styles


def _one_brief(article, styles):
    from acervo.images.brief import SenseBrief
    offered = tuple(style.id for style in styles.offer())
    return [SenseBrief(sense.id, offered[0], None, "A situation.", "the thing", "A scene.",
                       False, None)
            for sense in article.senses]


def test_an_image_chain_falls_through_and_the_record_names_the_pair_that_drew(tmp_path):
    """The locked provenance contract, at the one call site that can fall through."""
    from acervo.models import ProviderUnavailable

    _catalogue, candidates = _candidates(("vertex", "lite"), ("cloudflare", "klein"))
    renderer = _drawing({
        ("vertex", "lite"): ProviderUnavailable("rate_limited", "429", provider_id="vertex"),
        ("cloudflare", "klein"): _answer("cloudflare", "klein"),
    })
    runner, _ = _runner(tmp_path, renderer, candidates, _one_brief)
    articles = build_articles(changes(), "es")
    jobs = plan(articles, runner.store, drawn=set())[:1]
    result = runner.run(jobs)

    assert result["drawn"] == 1
    record = runner.store.read(runner.store.record_path(jobs[0].prompt_id))
    assert record["imageModelId"] == "klein"
    # Both pairs are in the record, so a fall-through is visible rather than invisible.
    assert record["run"]["attempts"] == [["vertex", "lite"], ["cloudflare", "klein"]]
    assert record["run"]["usage"]["provider"] == "cloudflare"


def test_a_brief_kept_from_an_earlier_run_keeps_the_model_that_wrote_it(tmp_path):
    """Stamping today's chain onto a cached brief is provenance that is wrong exactly when it is
    most wanted — after the chain has changed."""
    _catalogue, candidates = _candidates(("cloudflare", "klein"))
    renderer = _drawing({("cloudflare", "klein"): _answer("cloudflare", "klein")})
    runner, styles = _runner(tmp_path, renderer, candidates, _one_brief)
    articles = build_articles(changes(), "es")
    jobs = plan(articles, runner.store, drawn=set())[:1]

    # A brief on disk, written by a model that is no longer in the chain.
    runner.store.write(runner.store.brief_path(jobs[0].article.id), {
        "lexemeId": jobs[0].article.id, "promptVersion": runner.version,
        "usage": {"model": "a-retired-model"},
        "senses": [{"senseId": sense.id, "styleId": tuple(s.id for s in styles.offer())[0],
                    "anchorExampleId": None, "situation": "", "subject": "",
                    "brief": "A scene.", "refused": False, "refusalReason": None}
                   for sense in jobs[0].article.senses],
    })
    runner.run(jobs)
    record = runner.store.read(runner.store.record_path(jobs[0].prompt_id))
    assert record["modelId"] == "a-retired-model"


def test_a_provider_that_declines_is_recorded_and_the_sweep_continues(tmp_path):
    from acervo.models import ProviderRefused

    _catalogue, candidates = _candidates(("cloudflare", "klein"))
    renderer = _drawing({
        ("cloudflare", "klein"): ProviderRefused("refused", "the prompt was blocked"),
    })
    runner, _ = _runner(tmp_path, renderer, candidates, _one_brief)
    jobs = plan(build_articles(changes(), "es"), runner.store, drawn=set())[:1]
    result = runner.run(jobs)

    assert result["refused"] == 1 and result["stopped"] is None
    assert runner.store.read(runner.store.record_path(jobs[0].prompt_id))["blocked"] is True


def test_a_bad_credential_stops_the_run_rather_than_blocking_every_sense(tmp_path):
    """A chain falls through on 429 and never on authentication. The sweep must do the same, or a
    mistyped key marks two thousand senses as permanently undrawable."""
    from acervo.models import ProviderRefused

    _catalogue, candidates = _candidates(("cloudflare", "klein"))
    renderer = _drawing({
        ("cloudflare", "klein"): ProviderRefused("authentication", "that token is not valid"),
    })
    runner, _ = _runner(tmp_path, renderer, candidates, _one_brief)
    jobs = plan(build_articles(changes(), "es"), runner.store, drawn=set())
    result = runner.run(jobs)

    assert result["stopped"] and "not valid" in result["stopped"]
    assert result["drawn"] == 0
    # Only the job that met the refusal wrote anything; the rest returned untouched.
    assert not runner.store.read(runner.store.record_path(jobs[0].prompt_id)).get("blocked")
    assert runner.store.read(runner.store.record_path(jobs[-1].prompt_id)) is None


def test_the_configured_size_reaches_the_call(tmp_path):
    """The defect `image-generation-research.md` recorded: the pipeline generated at its default
    and resized afterwards. Asserted on the request, because the output file cannot tell you what
    was asked for."""
    from acervo.images.render import Renderer
    from acervo.models import call

    asked = {}

    def fake_image(prompt, *, row, model=None, seed=None, size=None, timeout=None):
        asked.update({"size": size, "seed": seed})
        from acervo.models.results import ImageResult
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (512, 512)).save(buffer, format="PNG")
        return ImageResult(data=buffer.getvalue(), mime="image/png",
                           answer=_answer("cloudflare", "klein"))

    _catalogue, candidates = _candidates(("cloudflare", "klein"))
    import unittest.mock
    with unittest.mock.patch.object(call, "image", fake_image):
        drawn = Renderer(size=(512, 512)).draw("a scene", 17, candidates[0])
    assert drawn.data[:4] == b"RIFF", "the master comes back as encoded WebP bytes"
    assert asked["size"] == (512, 512)
    assert asked["seed"] == 17


# ── the retry loop: what is worth waiting for ───────────────────────────────


def _writer():
    from acervo.images.brief import BriefWriter
    from acervo.models.providers import Providers

    return BriefWriter(Providers(), (), TEMPLATE.read_text(encoding="utf-8"), load_styles(STYLES))


def _exhausted(*reasons: str):
    from acervo.models.errors import ChainExhausted, ProviderUnavailable

    last = ProviderUnavailable(reasons[-1], "no", provider_id="p", model="m")
    return ChainExhausted((("p", "m"),), last, reasons)


def test_a_chain_that_only_answered_badly_is_retried_at_once_and_then_reported(monkeypatch):
    """No sleep, and only one extra walk.

    The ladder in `write` exists to outlast a quota, and `3424a95` let `unusable` inherit it. But a
    malformed answer is not waiting for anything — the same prompt and the same models produce the
    same malformed answer four minutes later — so the 465 seconds bought nothing and turned one bad
    schema into what read as a hung request. Re-sampling once is worth it; a third draw says what
    the second did.
    """
    from acervo.models.errors import ChainExhausted

    walks = []
    def once(article):
        walks.append(1)
        raise _exhausted("unusable", "unusable")
    monkeypatch.setattr(_writer().__class__, "_write_once", staticmethod(once))

    with pytest.raises(ChainExhausted):
        _writer().write(object())
    assert len(walks) == 2


def test_a_chain_that_ran_out_of_quota_is_left_to_the_caller_to_wait_out(monkeypatch):
    """The writer makes one walk. Waiting is the job runner's decision, or the laptop run's."""
    from acervo.models.errors import ChainExhausted

    walks = []
    def once(article):
        walks.append(1)
        raise _exhausted("rate_limited")
    monkeypatch.setattr(_writer().__class__, "_write_once", staticmethod(once))

    with pytest.raises(ChainExhausted):
        _writer().write(object())
    assert len(walks) == 1
