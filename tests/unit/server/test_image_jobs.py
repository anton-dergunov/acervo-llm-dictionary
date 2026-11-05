"""Redraw, edit-and-draw and a new brief, as jobs a person asks for (`docs/architecture/jobs.md`).

The point of each is that it survives the owner leaving the word: a redraw asked for and then left
is present on return.
"""

from __future__ import annotations

import litellm
import pytest

from acervo.images.ids import image_prompt_id
from acervo.repository import jobs
from acervo.work.runner import Runner

from test_images import a_brief_for, brief, word
from provider_rows import VERTEX_IMAGE


@pytest.fixture(autouse=True)
def a_provider_that_draws(server, monkeypatch):
    server.add_provider(VERTEX_IMAGE)


@pytest.fixture
def drawn(server):
    """A word with two briefed senses and nothing drawn, and no enrichment of its own running."""
    entry, itch, chop, sentence = word(server)
    for job in jobs.open_jobs(server.owner):
        jobs.request_cancel(server.owner, job["id"])
    assert brief(server, entry, (itch, sentence["id"]), (chop, None)).status_code == 200
    return entry, itch, chop


@pytest.fixture
def runner(server) -> Runner:
    return Runner(server.settings)


def ask(server, kind, subject_kind, subject_id, **extra):
    return server.post("/jobs", {"kind": kind, "subject": {"kind": subject_kind, "id": subject_id}, **extra})


def prompt(server, sense_id):
    rows = server.pull().json()["data"]["changes"]["imagePrompts"]
    return next(row for row in rows if row["id"] == image_prompt_id(sense_id))


def test_a_redraw_asked_for_and_left_is_there_on_return(server, drawn, runner):
    entry, itch, _ = drawn
    answer = ask(server, "image.redraw", "imagePrompt", image_prompt_id(itch["id"]))
    assert answer.status_code == 202, answer.json()
    # Nobody is waiting on the request: the runner does the work whenever it gets there.
    runner.run_until_idle()
    finished = jobs.get(server.owner, answer.json()["data"]["id"])
    assert finished["state"] == "done"
    row = prompt(server, itch["id"])
    assert row["imageRef"].startswith(f"images/{entry['id']}/{row['id']}-")
    assert (server.media / row["imageRef"]).exists()


def test_edit_and_draw_carries_its_own_wording(server, drawn, runner):
    _, itch, _ = drawn
    answer = ask(server, "image.redraw", "imagePrompt", image_prompt_id(itch["id"]),
                 input={"prompt": "An onion on a board", "styleId": "ukiyo-e", "ignored": "x"})
    assert answer.json()["data"]["input"] == {"prompt": "An onion on a board", "styleId": "ukiyo-e"}
    runner.run_until_idle()
    row = prompt(server, itch["id"])
    assert (row["prompt"], row["styleId"]) == ("An onion on a board", "ukiyo-e")
    assert "An onion on a board" in server.painter.calls[-1]["prompt"]


def test_pressing_draw_twice_before_it_starts_draws_once_with_the_newer_wording(server, drawn, runner):
    _, itch, _ = drawn
    target = image_prompt_id(itch["id"])
    first = ask(server, "image.redraw", "imagePrompt", target, input={"prompt": "first"}).json()["data"]
    second = ask(server, "image.redraw", "imagePrompt", target, input={"prompt": "second"}).json()["data"]
    assert first["id"] == second["id"]
    runner.run_until_idle()
    assert len(server.painter.calls) == 1
    assert prompt(server, itch["id"])["prompt"] == "second"


def test_a_declined_redraw_is_recorded_on_the_picture_and_the_job(server, drawn, runner):
    _, itch, _ = drawn
    server.painter.data = None  # no image data: `call.image` reads this as a refusal
    job = ask(server, "image.redraw", "imagePrompt", image_prompt_id(itch["id"])).json()["data"]
    runner.run_until_idle()
    finished = jobs.get(server.owner, job["id"])
    assert (finished["state"], finished["error"]) == ("failed", "image_refused")
    assert prompt(server, itch["id"])["failureReason"]


def test_a_busy_image_provider_rests_the_redraw(server, drawn, runner):
    _, itch, _ = drawn
    server.painter.error = litellm.RateLimitError(message="quota", llm_provider="openai", model="gpt-image-1")
    job = ask(server, "image.redraw", "imagePrompt", image_prompt_id(itch["id"])).json()["data"]
    runner.run_until_idle()
    waiting = jobs.get(server.owner, job["id"])
    assert waiting["state"] == "queued"
    assert waiting["steps"][0]["error"] == "llm_rate_limited"
    # An allowance that ran out is not counted against the picture.
    assert prompt(server, itch["id"])["attempts"] == 0


def test_a_new_brief_rewrites_every_sense_of_the_word(server, drawn, runner):
    entry, itch, chop = drawn
    server.model.brief = a_brief_for((itch, None), (chop, None), style="ukiyo-e")
    job = ask(server, "image.rebrief", "lexeme", entry["id"]).json()["data"]
    runner.run_until_idle()
    assert jobs.get(server.owner, job["id"])["state"] == "done"
    assert prompt(server, itch["id"])["styleId"] == "ukiyo-e"
    assert prompt(server, chop["id"])["styleId"] == "ukiyo-e"


def test_a_new_brief_asked_from_a_ruled_out_sense_briefs_that_sense(server, drawn, runner):
    entry, itch, chop = drawn
    for one in (itch, chop):
        assert server.delete(f"/images/prompts/{image_prompt_id(one['id'])}").status_code == 200
    server.model.brief = a_brief_for((itch, None), (chop, None), style="ukiyo-e")
    job = ask(server, "image.rebrief", "lexeme", entry["id"], input={"senseId": chop["id"]}).json()["data"]
    runner.run_until_idle()
    assert jobs.get(server.owner, job["id"])["state"] == "done"
    assert prompt(server, chop["id"])["suppressed"] is False
    assert prompt(server, chop["id"])["styleId"] == "ukiyo-e"
    assert prompt(server, itch["id"])["suppressed"] is True, "the sense that did not ask stays ruled out"


def test_somebody_elses_picture_cannot_be_redrawn(server, other, drawn):
    _, itch, _ = drawn
    assert ask(other, "image.redraw", "imagePrompt", image_prompt_id(itch["id"])).status_code == 404
    assert ask(server, "image.redraw", "lexeme", image_prompt_id(itch["id"])).status_code == 400


def test_the_dialog_reads_a_pictures_whole_prompt(server, drawn, other):
    _, itch, _ = drawn
    answer = server.get(f"/images/prompts/{image_prompt_id(itch['id'])}")
    assert answer.status_code == 200
    row = answer.json()["data"]
    assert row["prompt"] in row["composedPrompt"]
    assert other.get(f"/images/prompts/{image_prompt_id(itch['id'])}").status_code == 404
