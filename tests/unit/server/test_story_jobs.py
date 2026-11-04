"""The `story` job: write, translate, brief, draw — and, when switched on, read aloud.

Reading aloud is switched **off** for everything here, by the `models` fixture: this file is about
the four steps that make a story, and `test_story_audio.py` is about the fifth. A step that is off
is skipped, which is itself pinned there.

The models are faked at `acervo.models.call`'s own seams — `completion` and `image_generation` —
so this exercises the real chain, the real parsers and the real writes, and never the network.

What is pinned here is the two things the four-step shape exists for: that three good steps survive
a fourth that fails, and that a retry redraws only the pictures that are actually missing.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest import mock

import litellm
import pytest
from graph_records import lexeme, sense, vocabulary

from acervo.repository import graph, image_settings, jobs, pronunciation_settings
from acervo.services import stories
from acervo.work import kinds
from acervo.work.runner import Runner

# A real PNG, as `conftest.ImageStub` uses: the renderer decodes what comes back before it
# re-encodes, so a byte string that is not an image fails inside Pillow rather than in the job.
PICTURE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def story_reply(parts: int = 4) -> dict:
    return {
        "title": "El perro asombroso",
        "emoji": "🐕",
        "parts": [
            {"heading": f"Parte viva {index}", "text": f"Marcos vio algo asombroso. Numero {index}."}
            for index in range(parts)
        ],
        "words": [{"lexemeId": "", "forms": ["asombroso"]}],
    }


def translation_reply(parts: int = 4) -> dict:
    return {
        "title": "The amazing dog",
        "parts": [{"heading": f"Live part {index}", "text": f"Marcos saw something amazing. {index}."}
                  for index in range(parts)],
    }


def brief_reply(parts: int = 4) -> dict:
    return {
        "cast": "MARCOS: a thin man in a green jacket.",
        "world": "A Spanish street on a Saturday morning.",
        "parts": [{"brief": f"A thin man in a green jacket stands in a street. Scene {index}."}
                  for index in range(parts)],
    }


class Models:
    """The text chain and the image chain, answering in the order the job asks."""

    def __init__(self) -> None:
        self.texts: list[dict] = []
        self.prompts: list[str] = []
        self.image_calls = 0
        self.image_fails_after: int | None = None
        self.image_rate_limited = False
        # Pictures asked for over the chat route, as a row that takes references is: the number of
        # reference pictures each carried, and the prompt it was sent with.
        self.referenced: list[tuple[int, str]] = []

    def completion(self, **kwargs):
        if "modalities" in kwargs:
            content = kwargs["messages"][-1]["content"]
            self.image_calls += 1
            self.referenced.append((sum(1 for one in content if one["type"] == "image_url"),
                                    content[-1]["text"]))
            url = "data:image/png;base64," + base64.b64encode(PICTURE).decode()
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    images=[{"image_url": {"url": url}}], content=""))],
                usage=None, _hidden_params={})
        self.prompts.append(kwargs["messages"][-1]["content"])
        payload = self.texts.pop(0)
        return litellm.ModelResponse(
            model=kwargs["model"],
            choices=[{"index": 0, "finish_reason": "stop",
                      "message": {"role": "assistant", "content": json.dumps(payload)}}],
        )

    def image_generation(self, **kwargs):
        self.image_calls += 1
        if self.image_rate_limited:
            raise litellm.RateLimitError(message="no allowance left", llm_provider="p", model="m")
        if self.image_fails_after is not None and self.image_calls > self.image_fails_after:
            # A *refusal* of this particular brief, not a rate limit. The two are deliberately
            # different here: a refusal is about the brief, so it is recorded on the part and the
            # loop goes on; an exhausted allowance stops the step without burning anybody's
            # retries, which `test_an_exhausted_allowance_costs_no_part_its_retries` pins.
            raise litellm.BadRequestError(message="that brief was declined", model="m",
                                          llm_provider="p")
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(PICTURE).decode())], usage=None
        )


@pytest.fixture
def models(server, monkeypatch) -> Models:
    stub = Models()
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    # The `server` fixture clears every provider but Gemini, which draws nothing. OpenAI is the
    # image row `test_images.py` credentials for the same reason.
    monkeypatch.setenv("OPENAI_API_KEY", "a-key")
    monkeypatch.setattr("acervo.models.call.completion", lambda **kw: stub.completion(**kw))
    monkeypatch.setattr("acervo.models.call.image_generation",
                        lambda **kw: stub.image_generation(**kw))

    # The real encoder runs, on a real PNG: it is the same WebP path a drawn picture takes, and
    # stubbing it would leave the bytes the digest is taken from untested.
    pronunciation_settings.save(server.owner, pregenerate={pronunciation_settings.STORIES: False})
    return stub


@pytest.fixture
def runner(server) -> Runner:
    return Runner(server.settings)


def only_the_story(server) -> None:
    """Clear the `enrich` jobs that saving a word queues.

    They are queued in the same transaction as the record, which is the design — but they would run
    first here and eat the replies stubbed for the story, so a test about the story job would
    silently be a test about enrichment.
    """
    for job in jobs.open_jobs(server.owner):
        if job["kind"] != "story":
            jobs.finish(job["id"], "cancelled")


def a_story(server, count: int = 2, style: str = "comic-book", learner: dict | None = None, **extra) -> dict:
    server.push({"vocabularies": [vocabulary(**(learner or {}))]})
    ids = []
    for index in range(count):
        entry = lexeme(headword="asombroso" if index == 0 else f"palabra{index}",
                       lemma="asombroso" if index == 0 else f"palabra{index}",
                       status="active", shortGloss=f"word {index}")
        server.push({"lexemes": [entry], "senses": [sense(entry["id"])]})
        ids.append(entry["id"])
    answer = server.post("/stories", {"deviceId": "device000000001", "language": "es",
                                      "lexemeIds": ids, "typeId": "funny",
                                      "styleId": style, **extra})
    assert answer.status_code == 202, answer.text
    only_the_story(server)
    return answer.json()["data"]["story"]


def test_the_kind_declares_its_five_steps_before_it_runs(server):
    """The progress strip names them while the job is queued, so they cannot be discovered late."""
    assert kinds.find("story").steps == (
        "story.write", "story.translate", "story.brief", "story.draw", "story.audio"
    )


def test_a_whole_story_is_written_translated_briefed_and_drawn(server, models, runner):
    story = a_story(server, 2)
    words = graph.story_words(server.owner, story["id"])
    reply = story_reply(4)
    reply["words"] = [{"lexemeId": words[0]["lexemeId"], "forms": ["asombroso"]}]
    models.texts = [reply, translation_reply(4), brief_reply(4)]

    runner.run_until_idle()

    held = graph.owned_records(server.owner, "stories", [story["id"]])[story["id"]]
    assert held["title"] == "El perro asombroso"
    assert held["titleTranslation"] == "The amazing dog"
    assert held["modelId"], "the entry records the model that answered"

    parts = graph.story_parts(server.owner, story["id"])
    assert len(parts) == 4
    assert all(part["translation"] for part in parts), "every part is translated"
    assert all(part["imagePrompt"] for part in parts), "every part is briefed"
    assert all(part["imageRef"] for part in parts), "every part is drawn"
    assert models.image_calls == 4, "one image call per part"

    # The word the story used is recorded with the form it used; the other is honestly empty.
    refreshed = graph.story_words(server.owner, story["id"])
    assert refreshed[0]["forms"] == ["asombroso"]
    assert refreshed[1]["forms"] == []


def test_the_story_is_written_for_the_reader_and_translated_without_them(server, models, runner):
    """The level, the variety and the note shape what the learner reads in the language; the
    translation renders that text and owes the learner nothing more."""
    story = a_story(server, 2, learner={"level": "A2", "region": "AR", "learnerNote": "I love football."})
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    runner.run_until_idle()

    write, translate = models.prompts[0], models.prompts[1]
    assert "## The reader" in write and "A2, elementary" in write and "I love football." in write
    # The request still sits directly under its own heading, after everything appended to the prompt.
    assert write.index("## The reader") < write.index("## The request\n\n{")
    assert "## The reader" not in translate and "## The story\n\n{" in translate


def _draw_step(server) -> dict:
    job = [one for one in jobs.recent(server.owner) if one["kind"] == "story"][0]
    return next(step for step in job["steps"] if step["name"] == "story.draw")


def test_the_draw_step_says_how_many_pictures_it_has_done(server, models, runner):
    """The interface turns this into "picture 2 of 4" and a single percentage. Nothing else in the
    job says how far through the pictures it is: the step used to note only what it had finished,
    once, at the end."""
    a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]

    runner.run_until_idle()

    draw = _draw_step(server)
    assert (draw["done"], draw["total"]) == (4, 4)


def test_trying_again_counts_from_the_pictures_already_drawn(server, models, runner):
    """Counted over every briefed part, so a retry that has one picture left starts at three of
    four rather than at nought of one — a percentage must not run backwards."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    models.image_fails_after = 3
    runner.run_until_idle()
    assert models.image_calls == 4

    models.image_fails_after = None
    seen: list[tuple[int, int]] = []
    real = stories.draw_pictures

    def spying(*args, progress=None, **kwargs):
        def record(done: int, total: int) -> None:
            seen.append((done, total))
            progress(done, total)

        return real(*args, progress=record, **kwargs)

    with mock.patch.object(stories, "draw_pictures", spying):
        jobs.enqueue(server.owner, "story", trigger="manual", subject_kind="story",
                     subject_id=story["id"])
        runner.run_until_idle()

    assert seen[0] == (3, 4), "starts from what is already on the page"
    assert seen[-1] == (4, 4)


def test_the_translation_says_which_of_its_words_render_each_word_the_story_used(server, models, runner):
    """Only what really appears in the translation is stored, and only words the story used were
    asked about: a word it could not work in has no form to find the counterpart of."""
    story = a_story(server, 2)
    words = graph.story_words(server.owner, story["id"])
    reply = story_reply(4)
    reply["words"] = [{"lexemeId": words[0]["lexemeId"], "forms": ["asombroso"]}]
    translation = translation_reply(4)
    translation["words"] = [
        {"lexemeId": words[0]["lexemeId"], "forms": ["amazing", "not anywhere in it"]},
        {"lexemeId": words[1]["lexemeId"], "forms": ["amazing"]},
    ]
    models.texts = [reply, translation, brief_reply(4)]

    runner.run_until_idle()

    refreshed = graph.story_words(server.owner, story["id"])
    assert refreshed[0]["translationForms"] == ["amazing"]
    assert refreshed[1]["translationForms"] == [], "an id it was never asked about is dropped"

    asked = models.prompts[1]
    assert '"usedAs"' in asked and words[0]["lexemeId"] in asked
    assert words[1]["lexemeId"] not in asked, "the word the story could not use was not asked about"


def test_a_translation_that_says_nothing_about_its_words_still_lands(server, models, runner):
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]

    runner.run_until_idle()

    parts = graph.story_parts(server.owner, story["id"])
    assert all(part["translation"] for part in parts)
    assert all(word["translationForms"] == [] for word in graph.story_words(server.owner, story["id"]))


def test_the_briefs_are_asked_for_in_one_call_covering_every_part(server, models, runner):
    """The load-bearing half of the design: a model that sees all four parts can keep the same
    character in the same coat, and one that sees one cannot."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    runner.run_until_idle()

    briefing = models.prompts[2]
    for index in range(4):
        assert f"Numero {index}" in briefing, "every part is in the one briefing call"


def test_a_story_whose_pictures_fail_is_still_a_story_you_can_read(server, models, runner):
    """Four steps exist so three can survive the fourth. A half-drawn story is readable; a
    half-written one is not."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    models.image_fails_after = 1  # the first lands, the rest are refused

    runner.run_until_idle()

    parts = graph.story_parts(server.owner, story["id"])
    assert sum(1 for part in parts if part["imageRef"]) == 1
    assert all(part["text"] and part["translation"] for part in parts), "the story survived"
    undrawn = [part for part in parts if not part["imageRef"]]
    assert all(part["failureReason"] for part in undrawn), "and each says why it has no picture"
    assert all(part["attempts"] == 1 for part in undrawn)


def test_an_exhausted_allowance_costs_no_part_its_retries(server, models, runner):
    """`services/images.py`'s rule: an allowance that ran out is not something wrong with the
    brief, so it must not use up a part's attempts. This loop adds the other half — the step stops
    rather than walking the same exhausted chain once per remaining part."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    models.image_rate_limited = True

    runner.run_until_idle()

    parts = graph.story_parts(server.owner, story["id"])
    assert all(part["attempts"] == 0 for part in parts), "nobody's retries were spent"
    assert models.image_calls == 1, "it stopped rather than collecting the same refusal four times"
    assert all(part["text"] for part in parts), "and the story it already wrote is intact"


def test_trying_again_redraws_only_the_pictures_that_are_missing(server, models, runner):
    """`story.draw` re-derives what is missing from the graph rather than being handed it, which is
    what makes a retry cost one picture rather than four."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    models.image_fails_after = 1
    runner.run_until_idle()
    assert models.image_calls == 4  # one drawn, three refused

    models.image_fails_after = None
    models.image_calls = 0
    jobs.enqueue(server.owner, "story", trigger="manual", subject_kind="story",
                 subject_id=story["id"])
    runner.run_until_idle()

    # The three that were missing, and **not** the one already drawn, nor a second story call.
    assert models.image_calls == 3
    parts = graph.story_parts(server.owner, story["id"])
    assert all(part["imageRef"] for part in parts)


def test_a_writer_that_refuses_is_terminal_rather_than_retried(server, models, runner):
    """The writer judged, so trying another model pays twice for the same answer."""
    story = a_story(server, 1)
    models.texts = [{"refused": True, "reason": "that word is a slur"}]

    runner.run_until_idle()

    job = [one for one in jobs.recent(server.owner) if one["kind"] == "story"][0]
    assert job["state"] == "failed"
    assert "slur" in (job["message"] or ""), "the writer's own words survive the hand-off"
    # And the story reads as one that was asked for and never written.
    assert graph.story_parts(server.owner, story["id"]) == []


# ── drawn from the earlier pictures ─────────────────────────────────────────


def continuity_reply() -> dict:
    """Marcos on the street; Ana alone in her flat; both on the street; Marcos in the flat."""
    return {
        "characters": [{"id": "marcos", "description": "a thin man in a green jacket"},
                       {"id": "ana", "description": "a woman with a red scarf"}],
        "scenes": [{"id": "street", "description": "a Spanish street"},
                   {"id": "flat", "description": "a small top-floor flat"}],
        "parts": [
            {"characters": ["marcos"], "scene": "street", "change": ""},
            {"characters": ["ana"], "scene": "flat", "change": ""},
            {"characters": ["marcos", "ana"], "scene": "street", "change": ""},
            {"characters": ["marcos"], "scene": "flat", "change": "that night"},
        ],
    }


@pytest.fixture
def references(monkeypatch):
    """The test image row, declared as one that takes reference pictures, as Vertex's does."""
    monkeypatch.setattr("acervo.models.catalogue.Row.image_references", lambda row: 14)


def test_a_later_picture_is_drawn_from_the_earlier_pictures_of_who_and_where_it_shows(
        server, models, runner, references):
    a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4), continuity_reply()]

    runner.run_until_idle()

    assert models.image_calls == 4
    # Parts 1 and 2 have nobody and nowhere seen before, so they take the ordinary route with no
    # references; part 3 is given part 1 (Marcos, the street) and part 2 (Ana); part 4 is given
    # part 1 (Marcos, as he was first drawn) and part 2 (the flat, last seen there).
    assert [count for count, _prompt in models.referenced] == [2, 2]
    last = models.referenced[-1][1]
    assert "Reference 1 is the picture from part 1" in last
    assert "Reference 2 is the picture from part 2" in last
    assert "ANA, who is not in this moment" in last
    assert "that night" in last
    assert "the picture wins" in last, "the picture comes first, the references second"
    assert _draw_step(server)["detail"]["referenced"] == 2


def test_switched_off_there_is_no_label_call_and_no_reference(server, models, runner, references):
    image_settings.save(server.owner, story_continuity="off")
    a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]

    runner.run_until_idle()

    assert models.image_calls == 4
    assert models.referenced == []
    assert models.texts == [] and len(models.prompts) == 3, "no fourth text call was made"


@pytest.mark.parametrize("setting, referenced", [("artwork", 0), ("all", 2)])  # "all" is the default
def test_a_photographic_style_is_left_out_unless_every_style_was_asked_for(
        server, models, runner, references, setting, referenced):
    image_settings.save(server.owner, story_continuity=setting)
    a_story(server, 1, style="cinematic-photoreal")
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    if referenced:
        models.texts.append(continuity_reply())

    runner.run_until_idle()

    assert models.image_calls == 4
    assert len(models.referenced) == referenced


def test_labels_that_cannot_be_had_cost_no_picture(server, models, runner, references):
    """The label call is opportunistic: a reply that will not parse means no references, and the
    story is drawn exactly as it was before references existed."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4), {"nonsense": True},
                    {"nonsense": True}]

    runner.run_until_idle()

    assert all(part["imageRef"] for part in graph.story_parts(server.owner, story["id"]))
    assert models.referenced == []


def test_a_row_that_takes_no_references_draws_every_part_the_ordinary_way(server, models, runner):
    a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4), continuity_reply()]

    runner.run_until_idle()

    assert models.image_calls == 4
    assert models.referenced == [], "the labels are made, and nothing is sent that cannot be read"


def test_the_pair_that_drew_the_first_picture_is_asked_first_for_the_rest():
    one, two = (SimpleNamespace(model="model/a"), SimpleNamespace(model="model/b"))
    rows = [{"imageRef": "x.webp", "imageModelId": "model/b"}, {"imageRef": ""}]
    assert stories._pinned((one, two), rows) == (two, one)
    assert stories._pinned((one, two), [{"imageRef": ""}]) == (one, two), "nothing drawn, no pin"


def test_the_owners_guidance_reaches_the_writer(server, models, runner):
    a_story(server, 1, guidance="Tell it from the dog's side.")
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]

    runner.run_until_idle()

    assert '"guidance": "Tell it from the dog\'s side."' in models.prompts[0]
    assert "The reader's own guidance" in models.prompts[0], "and the prompt says what it is for"
