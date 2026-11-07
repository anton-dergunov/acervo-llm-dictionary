"""Drawing a sense picture from a route, and the states a picture can be in.

Against the real service and the real WebP encoder over a throwaway media directory: what is stubbed
is the provider, and only the provider. A test that stubbed the encoder too would assert that this
file's own mock returns bytes.
"""

from __future__ import annotations

import json

import litellm
import pytest

from acervo.errors import ApiError
from acervo.images.ids import image_prompt_id
from acervo.services.images import MAX_ATTEMPTS, brief_lexeme, render_prompt

from conftest import PNG_OTHER
from graph_records import attestation, example, lexeme, sense, vocabulary
from provider_rows import VERTEX_IMAGE

DEVICE = "device000000001"


@pytest.fixture(autouse=True)
def a_provider_that_draws(server, monkeypatch):
    """The default chain is `gemini-free`, which deliberately offers no image model — its free tier
    allows zero image requests, so listing one would put a row in the chain that can only 429.

    Set *after* the `server` fixture, which clears every provider but Gemini, and it takes effect
    without a restart because `settings` is deliberately re-read on every request.
    """
    server.add_provider(VERTEX_IMAGE)


def word(server, **overrides):
    """One word with two senses and an example, pushed and ready to be drawn."""
    entry = lexeme(**overrides)
    itch = sense(entry["id"], definition="Producir comezón.", order=0)
    chop = sense(entry["id"], definition="Cortar en trozos.", order=1)
    source = attestation(entry["id"])
    sentence = example(
        itch["id"], text=source["text"], translation=source["translation"], translationLang="en",
        origin="attestation", sourceAttestationId=source["id"], modelId=None,
    )
    answer = server.push({
        "vocabularies": [vocabulary()],
        "lexemes": [entry], "senses": [itch, chop],
        "attestations": [source], "examples": [sentence],
    })
    assert answer.status_code == 200, answer.json()
    return entry, itch, chop, sentence


class Answered:
    """A service call, read the way these tests were written to read a route's answer.

    Writing a brief and drawing a picture are jobs now (`work/images.py`), not routes — but what
    they *do* is these service functions, and what a refusal carries is an `ApiError`'s status and
    code. This keeps the assertions about both, one call closer to the work.
    """

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> dict:
        return self.body

    @property
    def text(self) -> str:
        return json.dumps(self.body)


def called(action, *args, **kwargs) -> Answered:
    try:
        return Answered(200, {"data": action(*args, **kwargs)})
    except ApiError as refusal:
        return Answered(refusal.status, {"error": {"code": refusal.code, "message": refusal.message}})


def render(server, prompt_id, **overrides):
    """One image call for one picture, as `image.redraw` makes it."""
    return called(render_prompt, server.settings, server.owner, DEVICE, prompt_id, overrides or None)


def a_brief_for(*senses, style="oil-painting"):
    return {"senses": [
        {"senseId": one["id"], "styleId": style, "anchorExampleId": anchor,
         "situation": "a kitchen", "subject": "an onion", "brief": f"A picture for {one['id']}"}
        for one, anchor in senses
    ]}


def brief(server, entry, *senses, **overrides):
    """One text call for the whole word, as `image.rebrief` makes it."""
    server.model.brief = a_brief_for(*senses, **overrides)
    return called(brief_lexeme, server.settings, server.owner, DEVICE, entry["id"])


def rows(answer):
    return {row["senseId"]: row for row in answer.json()["data"]["imagePrompts"]}


# ── the two calls ───────────────────────────────────────────────────────────


def test_one_text_call_covers_every_sense_of_the_word(server):
    entry, itch, chop, sentence = word(server)
    answer = brief(server, entry, (itch, sentence["id"]), (chop, None))

    assert answer.status_code == 200, answer.json()
    assert len(server.model.calls) == 1, "batching per lexeme is the reason per-sense pictures work"
    written = rows(answer)
    assert set(written) == {itch["id"], chop["id"]}
    assert written[itch["id"]]["prompt"] == f"A picture for {itch['id']}"
    # Nothing has been drawn yet: a brief is what to draw, not the drawing.
    assert written[itch["id"]]["imageRef"] is None
    assert written[itch["id"]]["attempts"] == 0


def test_the_picture_records_the_sentence_it_was_built_from(server):
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    assert written[itch["id"]]["exampleId"] == sentence["id"]
    # A sense with no example still gets a picture; the definition and gloss are enough.
    assert written[chop["id"]]["exampleId"] is None


def test_the_id_is_derived_from_the_sense_so_two_engines_converge(server):
    """The whole reason a client loop and a worker sweep need no coordination."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    assert written[itch["id"]]["id"] == image_prompt_id(itch["id"])


def test_briefing_twice_updates_the_same_rows_rather_than_making_more(server):
    entry, itch, chop, sentence = word(server)
    first = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    second = rows(brief(server, entry, (itch, sentence["id"]), (chop, None), style="ukiyo-e"))
    assert first[itch["id"]]["id"] == second[itch["id"]]["id"]
    assert second[itch["id"]]["styleId"] == "ukiyo-e"
    assert second[itch["id"]]["revision"] > first[itch["id"]]["revision"]

    held = server.pull().json()["data"]["changes"]["imagePrompts"]
    assert len([row for row in held if not row["deleted"]]) == 2


def test_a_render_writes_the_file_and_the_row(server):
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))

    answer = render(server, written[itch["id"]]["id"])
    assert answer.status_code == 200, answer.json()
    row = answer.json()["data"]

    reference = row["imageRef"]
    assert reference.startswith(f"images/{entry['id']}/{written[itch['id']]['id']}-")
    assert reference.endswith(".webp"), "the name carries a digest of the bytes it holds"
    assert row["imageModelId"], "the record names the model that answered"
    assert row["attempts"] == 1
    assert row["failureReason"] is None

    drawn = server.media / row["imageRef"]
    assert drawn.is_file() and drawn.read_bytes()[:4] == b"RIFF"
    assert not list(drawn.parent.glob("*.part")), "the staging file is moved, never left behind"


def test_the_media_route_serves_what_was_just_drawn(server):
    """The picture has to come back through the authenticated route, because that is the only way
    the interface can reach it — `<img src>` cannot carry a bearer token."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    row = render(server, written[itch["id"]]["id"]).json()["data"]

    served = server.client.get(f"/api/acervo/media/{row['imageRef']}", headers=server.auth)
    assert served.status_code == 200
    assert served.content[:4] == b"RIFF"
    assert server.client.get(f"/api/acervo/media/{row['imageRef']}").status_code == 401


def test_drawing_again_names_a_new_file_and_removes_the_one_the_row_named(server):
    """A redraw is a different file, which is the whole of why a device sees the new picture.

    The name carries a digest of the bytes, so nothing overwrites in place and nothing cached under
    the old name is served for the new picture. The file the row no longer names goes once the row
    naming its successor has landed, so at most one picture per sense is kept.
    """
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    prompt_id = written[itch["id"]]["id"]

    first = render(server, prompt_id).json()["data"]
    server.painter.data = PNG_OTHER
    second = render(server, prompt_id).json()["data"]

    assert second["imageRef"] != first["imageRef"]
    assert not (server.media / first["imageRef"]).exists()
    assert (server.media / second["imageRef"]).is_file()
    assert second["attempts"] == 2
    # The attempt count is mixed into the seed, so deleting a picture you disliked and drawing again
    # gives a genuinely different one rather than the same picture back. It is stored either way:
    # whether it reaches the provider is the row's business — the OpenAI row drawing here declares
    # `seed: "ignored"`, so nothing is sent and `call.image` says so in the answer's warnings.
    assert second["seed"] != first["seed"]
    assert "seed" not in server.painter.calls[-1]
    assert len(list((server.media / f"images/{entry['id']}").iterdir())) == 1


def test_drawing_the_same_picture_again_lands_on_the_same_file(server):
    """A redraw that comes out byte-for-byte identical is one file, not a file deleted after it was
    written. The name is a digest, so the old reference and the new one are the same string, and
    removing "the file the row used to name" would remove the picture that is current."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    prompt_id = written[itch["id"]]["id"]

    first = render(server, prompt_id).json()["data"]
    second = render(server, prompt_id).json()["data"]

    assert second["imageRef"] == first["imageRef"]
    assert (server.media / second["imageRef"]).is_file()
    assert len(list((server.media / f"images/{entry['id']}").iterdir())) == 1


def test_a_row_that_cannot_be_written_leaves_the_picture_that_is_current(server, monkeypatch):
    """The file lands before the row, so a row that fails leaves an orphan rather than a picture the
    owner never got. The one they are looking at has to survive it."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    prompt_id = written[itch["id"]]["id"]
    first = render(server, prompt_id).json()["data"]

    from acervo.services import images as service

    def refuse(*args, **kwargs):
        raise ApiError(409, "stale_revision", "Somebody else wrote this first.")

    server.painter.data = PNG_OTHER
    monkeypatch.setattr(service, "_write", refuse)
    with pytest.raises(ApiError):
        render_prompt(server.settings, server.owner, DEVICE, prompt_id)

    assert (server.media / first["imageRef"]).is_file(), "the picture on screen is still there"
    assert len(list((server.media / f"images/{entry['id']}").iterdir())) == 1


def test_editing_the_brief_draws_it_without_a_second_text_call(server):
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    before = len(server.model.calls)

    answer = render(server, written[itch["id"]]["id"],
                    prompt="A nose, enormous", styleId="film-noir")
    assert answer.status_code == 200, answer.json()
    assert answer.json()["data"]["prompt"] == "A nose, enormous"
    assert answer.json()["data"]["styleId"] == "film-noir"
    assert len(server.model.calls) == before, "edit-and-draw costs no text call"
    assert "A nose, enormous" in server.painter.calls[-1]["prompt"]


def test_the_composed_prompt_is_rebuilt_rather_than_stored(server):
    """§04 stores the brief, the style and the version; the full prompt is a function of those plus
    the tracked files. The regenerate screen wants to show it, so it is rebuilt, not a column."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    row = written[itch["id"]]
    assert row["composedPrompt"].startswith(row["prompt"])
    assert "no letters" in row["composedPrompt"], "the frame is appended to every prompt"
    held = server.pull().json()["data"]["changes"]["imagePrompts"][0]
    assert "composedPrompt" not in held, "it is not a stored field"


# ── the states a picture can be in ──────────────────────────────────────────


def test_a_provider_refusal_is_recorded_rather_than_raised(server):
    """A provider that looks at the prompt and declines is a finished outcome for that wording. It
    is not suppressed, because a different brief may well pass — which is what editing is for."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    server.painter.data = None  # no image data: `call.image` reads this as a refusal

    answer = render(server, written[itch["id"]]["id"])
    assert answer.status_code == 200, answer.json()
    row = answer.json()["data"]
    assert row["imageRef"] is None
    assert row["attempts"] == 1
    assert row["failureReason"]
    assert row["suppressed"] is False


def test_a_rate_limit_does_not_spend_one_of_the_senses_retries(server):
    """An allowance that ran out says nothing about this sense, so counting it against the sense
    would let a bad afternoon exhaust every retry a word had."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    server.painter.error = litellm.RateLimitError(
        message="provider details that must stay private", llm_provider="stub", model="gpt-image-1"
    )

    answer = render(server, written[itch["id"]]["id"])
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "llm_rate_limited"
    assert "provider details" not in answer.text

    held = server.pull().json()["data"]["changes"]["imagePrompts"]
    assert [row["attempts"] for row in held if row["senseId"] == itch["id"]] == [0]


def test_a_writer_refusal_becomes_a_row_so_nothing_asks_again(server):
    entry, itch, chop, sentence = word(server)
    server.model.brief = {"senses": [
        {"senseId": itch["id"], "refused": True, "refusalReason": "nothing to picture here"},
        {"senseId": chop["id"], "styleId": "oil-painting", "brief": "An onion, quartered"},
    ]}
    written = rows(called(brief_lexeme, server.settings, server.owner, DEVICE, entry["id"]))

    refused = written[itch["id"]]
    assert refused["prompt"] == ""
    assert refused["suppressed"] is True
    assert refused["failureReason"] == "nothing to picture here"
    assert written[chop["id"]]["suppressed"] is False


def test_a_tombstoned_row_is_revived_rather_than_blocking_the_sense_forever(server):
    """The id is derived from the sense, so a tombstoned row is the only row this brief could ever
    occupy — and writing revision zero over it would be refused as stale. Editing a word's YAML and
    dropping its imagePrompts block is enough to produce one."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    buried = written[itch["id"]]

    # What `repository.saveArticle` does to a prompt the saved document did not mention.
    held = [row for row in server.pull().json()["data"]["changes"]["imagePrompts"]
            if row["id"] == buried["id"]][0]
    assert server.push({"imagePrompts": [{**held, "deleted": True}]}).status_code == 200

    again = brief(server, entry, (itch, sentence["id"]), (chop, None), style="ukiyo-e")
    assert again.status_code == 200, again.json()
    revived = rows(again)[itch["id"]]
    assert revived["id"] == buried["id"]
    assert revived["styleId"] == "ukiyo-e"
    assert [row for row in server.pull().json()["data"]["changes"]["imagePrompts"]
            if row["id"] == buried["id"]][0]["deleted"] is False


def test_a_suppressed_sense_is_not_re_briefed(server):
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    assert server.delete(f"/images/prompts/{written[itch['id']]['id']}").status_code == 200

    again = rows(brief(server, entry, (itch, sentence["id"]), (chop, None), style="ukiyo-e"))
    assert itch["id"] not in again, "the owner has ruled on this sense"
    assert chop["id"] in again


def test_asking_from_a_ruled_out_sense_briefs_it_again_and_lifts_the_ruling(server):
    """Write a new brief, pressed in that sense's own picture dialog, takes the ruling back the way
    Draw does. Before, the job skipped the sense and finished "done" having changed nothing there."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    for row in written.values():
        assert server.delete(f"/images/prompts/{row['id']}").status_code == 200

    server.model.brief = a_brief_for((itch, sentence["id"]), (chop, None), style="ukiyo-e")
    again = rows(called(brief_lexeme, server.settings, server.owner, DEVICE, entry["id"],
                        revive=chop["id"]))
    assert set(again) == {chop["id"]}, "only the sense that asked; the other ruling stands"
    assert again[chop["id"]]["suppressed"] is False
    assert again[chop["id"]]["styleId"] == "ukiyo-e"


def test_deleting_a_picture_removes_the_file_and_rules_the_sense_out(server):
    """Deliberately not a tombstone: the id is derived from the sense, so a tombstoned row would be
    invisible to the sweep, re-briefed, and re-minted at the same id."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    prompt_id = written[itch["id"]]["id"]
    reference = render(server, prompt_id).json()["data"]["imageRef"]
    assert (server.media / reference).is_file()

    answer = server.delete(f"/images/prompts/{prompt_id}")
    assert answer.status_code == 200
    assert answer.json()["data"]["imageRef"] is None
    assert answer.json()["data"]["suppressed"] is True
    assert not (server.media / reference).exists()

    held = [row for row in server.pull().json()["data"]["changes"]["imagePrompts"]
            if row["id"] == prompt_id]
    assert held and held[0]["deleted"] is False, "the row stays, saying the owner ruled on it"


# ── the owner's own picture ─────────────────────────────────────────────────


def test_an_attached_picture_carries_no_rendering_model(server):
    """Provenance modelled, never flagged — the same way an example the learner wrote carries no
    `modelId`, and nothing anywhere has a "the user supplied this" boolean."""
    from conftest import PNG

    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    prompt_id = written[itch["id"]]["id"]

    answer = server.send(f"/images/senses/{itch['id']}/picture", PNG)
    assert answer.status_code == 200, answer.json()
    row = answer.json()["data"]

    assert row["imageRef"] and row["imageModelId"] is None
    assert row["suppressed"] is True, "choosing a picture stops anything drawing over it"
    assert not server.painter.calls, "attaching is not a model call"
    # Re-encoded to the same master, so one article is not a mix of formats and sizes.
    assert (server.media / row["imageRef"]).read_bytes()[:4] == b"RIFF"


def test_drawing_over_an_attached_picture_stamps_the_version_it_was_composed_under(server):
    """A picture the owner attached has no brief, no style and no prompt version. Editing one in and
    drawing has to stamp all three, or the validator refuses the write with a message about the
    prompt version rather than about anything the owner did."""
    from conftest import PNG

    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    prompt_id = written[itch["id"]]["id"]
    server.send(f"/images/senses/{itch['id']}/picture", PNG)

    answer = render(server, prompt_id, prompt="A nose, enormous", styleId="film-noir")
    assert answer.status_code == 200, answer.json()
    row = answer.json()["data"]
    assert row["prompt"] == "A nose, enormous" and row["promptVersion"].startswith("img-")
    assert row["imageModelId"], "it is a drawn picture now, not the attached one"


def test_a_declined_prompt_is_kept_so_the_reason_has_something_to_sit_beside(server):
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    server.painter.data = None

    row = render(server, written[itch["id"]]["id"],
                 prompt="Something the provider will not draw", styleId="film-noir").json()["data"]
    assert row["prompt"] == "Something the provider will not draw"
    assert row["styleId"] == "film-noir"
    assert row["failureReason"] and row["imageRef"] is None


def test_a_picture_can_be_attached_to_a_sense_that_has_never_been_briefed(server):
    """The case the sense-keyed route exists for: no row, no brief, and no reason to spend a text
    call before putting your own picture there. The id is derived, so the row is minted at the id it
    was always going to have."""
    from conftest import PNG

    entry, itch, chop, sentence = word(server)
    answer = server.send(f"/images/senses/{chop['id']}/picture", PNG)
    assert answer.status_code == 200, answer.json()
    row = answer.json()["data"]

    assert row["id"] == image_prompt_id(chop["id"])
    assert row["senseId"] == chop["id"] and row["lexemeId"] == entry["id"]
    assert row["prompt"] == "" and row["styleId"] == ""
    assert row["imageRef"] and row["imageModelId"] is None
    assert row["suppressed"] is True
    assert not server.model.calls, "no text call was spent"
    assert (server.media / row["imageRef"]).read_bytes()[:4] == b"RIFF"


def test_a_restored_picture_keeps_the_model_that_drew_it_and_stays_replaceable(server):
    """What an import needs, and the half that was missing from the export round trip.

    A bundle carries the picture files and the model that drew each one; without naming it, every
    restored picture would read as one the owner had chosen — no provenance, and suppressed, so
    nothing would ever redraw two thousand of them.
    """
    from conftest import PNG

    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))

    answer = server.send(f"/images/senses/{itch['id']}/picture", PNG, drawn_by="vertex/imagen-4")
    assert answer.status_code == 200, answer.json()
    row = answer.json()["data"]

    assert row["imageModelId"] == "vertex/imagen-4"
    assert row["suppressed"] is False, "a restored picture is an ordinary drawn one"
    # The brief the bundle carried is still there, so it can be redrawn from.
    assert row["prompt"] == written[itch["id"]]["prompt"]
    assert not server.painter.calls, "restoring draws nothing"


def webp(size):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(buffer, format="WEBP", quality=80)
    return buffer.getvalue()


def test_a_picture_that_already_is_a_master_is_stored_byte_for_byte(server):
    """What every picture an import puts back is. Re-encoding it cost the server half a second a
    picture — most of an import's half hour — and a second generation of artifacts."""
    entry, itch, chop, sentence = word(server)
    master = webp((1024, 1024))
    row = server.send(f"/images/senses/{itch['id']}/picture", master,
                      drawn_by="vertex/imagen-4").json()["data"]
    assert (server.media / row["imageRef"]).read_bytes() == master


def test_a_webp_larger_than_the_master_is_still_brought_down_to_it(server):
    import io

    from PIL import Image

    entry, itch, chop, sentence = word(server)
    large = webp((2048, 2048))
    row = server.send(f"/images/senses/{itch['id']}/picture", large).json()["data"]
    stored = (server.media / row["imageRef"]).read_bytes()
    assert stored != large
    with Image.open(io.BytesIO(stored)) as image:
        assert image.format == "WEBP" and image.size == (1024, 1024)


def test_a_picture_the_owner_chose_is_told_apart_by_having_no_model(server):
    from conftest import PNG

    entry, itch, chop, sentence = word(server)
    brief(server, entry, (itch, sentence["id"]), (chop, None))
    row = server.send(f"/images/senses/{itch['id']}/picture", PNG).json()["data"]
    assert row["imageModelId"] is None
    assert row["suppressed"] is True, "choosing a picture stops anything drawing over it"


def test_another_accounts_sense_cannot_be_given_a_picture(server, other):
    from conftest import PNG

    entry, itch, chop, sentence = word(server)
    assert other.send(f"/images/senses/{itch['id']}/picture", PNG).status_code == 404


def test_a_file_that_is_not_an_image_is_refused(server):
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    answer = server.send(f"/images/senses/{itch['id']}/picture", b"not a picture")
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "unreadable_image"


# ── whose picture it is ─────────────────────────────────────────────────────


def test_another_accounts_picture_is_not_found_rather_than_forbidden(server, other):
    """One answer for "no such id", "somebody else's" and "deleted": telling them apart would say
    whether an id exists in another account."""
    entry, itch, chop, sentence = word(server)
    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    prompt_id = written[itch["id"]]["id"]

    assert render(other, prompt_id).status_code == 404
    assert called(brief_lexeme, other.settings, other.owner, DEVICE, entry["id"]).status_code == 404
    assert other.delete(f"/images/prompts/{prompt_id}").status_code == 404


def test_a_word_set_aside_is_not_briefed_and_its_owner_is_told_why(server, other):
    entry, itch, chop, sentence = word(server)
    stored = next(row for row in server.pull().json()["data"]["changes"]["lexemes"]
                  if row["id"] == entry["id"])
    assert server.push({"lexemes": [{**stored, "status": "aside"}]}).status_code == 200

    answer = called(brief_lexeme, server.settings, server.owner, DEVICE, entry["id"])
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "set_aside"
    assert called(brief_lexeme, other.settings, other.owner, DEVICE, entry["id"]).status_code == 404


def test_the_routes_need_a_signed_in_owner(server):
    entry, *_ = word(server)
    assert server.client.get("/api/acervo/v1/images/settings").status_code == 401
    assert server.client.get(f"/api/acervo/v1/images/prompts/{image_prompt_id(entry['id'])}").status_code == 401


# ── settings ────────────────────────────────────────────────────────────────


def test_no_record_means_following_the_deployment_default(server):
    view = server.get("/images/settings").json()["data"]
    assert view["chosen"] is False
    assert view["stylesOff"] == []
    assert view["drawEnabled"] is True
    assert view["boostVariety"] is True
    assert view["storyContinuity"] == "all"
    assert view["maxAttempts"] == MAX_ATTEMPTS
    assert {style["id"] for style in view["styles"]} >= {"oil-painting", "film-noir"}
    assert view["available"] is True


def test_which_stories_draw_from_their_earlier_pictures_is_one_of_three_answers(server):
    for answer in ("artwork", "off", "all"):
        saved = server.put("/images/settings", {"storyContinuity": answer})
        assert saved.status_code == 200, saved.json()
        assert server.get("/images/settings").json()["data"]["storyContinuity"] == answer
    refused = server.put("/images/settings", {"storyContinuity": "photographic"})
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "invalid_input"


def test_the_styles_say_which_of_them_are_photographs(server):
    """The setting's default leaves these out, so the screen names them."""
    styles = {style["id"]: style for style in server.get("/images/settings").json()["data"]["styles"]}
    assert {one for one, style in styles.items() if style["photographic"]} == {
        "cinematic-photoreal", "golden-hour", "film-noir", "neon-cyberpunk"}


def test_switching_drawing_off_is_stored_and_leaves_the_buttons_working(server):
    """It governs the two things that draw by themselves, and nothing else. Gating the routes would
    take away the reason to switch it off: a word with no pictures, and then the one you want."""
    entry, itch, chop, sentence = word(server)
    assert server.put("/images/settings", {"drawEnabled": False}).status_code == 200
    assert server.get("/images/settings").json()["data"]["drawEnabled"] is False

    written = rows(brief(server, entry, (itch, sentence["id"]), (chop, None)))
    answer = render(server, written[itch["id"]]["id"])
    assert answer.status_code == 200, answer.json()
    assert answer.json()["data"]["imageRef"]


def test_a_switched_off_style_is_never_offered(server):
    entry, itch, chop, sentence = word(server)
    kept = "ukiyo-e"
    view = server.get("/images/settings").json()["data"]
    off = [style["id"] for style in view["styles"] if style["id"] != kept]

    assert server.put("/images/settings", {"stylesOff": off}).status_code == 200
    brief(server, entry, (itch, sentence["id"]), (chop, None), style=kept)

    asked = server.model.calls[-1]["messages"][-1]["content"]
    assert f'"styleId": "{kept}"' in asked
    assert '"styleId": "oil-painting"' not in asked


def test_boost_variety_is_what_decides_whether_a_style_carries_examples(server):
    entry, itch, chop, sentence = word(server)

    brief(server, entry, (itch, sentence["id"]), (chop, None))
    assert '"suits": []' not in server.model.calls[-1]["messages"][-1]["content"]

    server.put("/images/settings", {"boostVariety": False})
    brief(server, entry, (itch, sentence["id"]), (chop, None))
    assert '"suits": []' in server.model.calls[-1]["messages"][-1]["content"]


def test_switching_every_style_off_is_refused_where_it_can_still_be_explained(server):
    """`StyleTable.offer` raises on an empty menu, which would refuse every brief from then on with
    an error about the style table rather than about the choice that caused it."""
    view = server.get("/images/settings").json()["data"]
    answer = server.put("/images/settings", {"stylesOff": [s["id"] for s in view["styles"]]})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "no_styles_left"


def test_a_style_this_server_does_not_have_is_refused(server):
    answer = server.put("/images/settings", {"stylesOff": ["art-deco-airbrush"]})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "unknown_style"


def test_settings_are_per_owner(server, other):
    server.put("/images/settings", {"boostVariety": False})
    assert other.get("/images/settings").json()["data"]["boostVariety"] is True
    assert other.get("/images/settings").json()["data"]["chosen"] is False


def test_a_server_with_no_image_provider_says_so_instead_of_offering_a_button(server, monkeypatch):
    server.remove_provider("vertex")
    assert server.get("/images/settings").json()["data"]["available"] is False
