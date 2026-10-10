"""`POST /pronunciations/take`: one line of a loop, as the master, cached by what it records.

The seam LexiBeat gets its voice through while holding no provider credential of its own. What is
stubbed is the provider and only the provider, exactly as in `test_pronunciations.py`.
"""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest
from graph_records import vocabulary

from acervo.api.auth import TAKE_AUDIENCE, mint_render
from acervo.pronunciation import takes
from acervo.repository import accounts

MP3 = b"ID3\x04\x00an-mp3-of-some-length"


def wav(words: str) -> bytes:
    frames = bytearray()
    for index in range(2_400 * max(len(words), 1)):
        frames += struct.pack("<h", int(12_000 * math.sin(2 * math.pi * 220 * index / 24_000)))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24_000)
        out.writeframes(bytes(frames))
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def a_voice(server, monkeypatch, tmp_path):
    credentials = tmp_path / "service-account.json"
    credentials.write_text("{}")
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project-name")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(credentials))
    monkeypatch.delenv("ACERVO_VERTEX_ACCOUNT", raising=False)
    calls: list[dict] = []

    def speech(row, model, words, **kwargs):
        calls.append({"provider": row.id, "model": model, "words": words, **kwargs})
        failure = getattr(speech, "failure", None)
        if failure is not None:
            raise failure
        answer = getattr(speech, "answer", None)
        return answer if answer is not None else (wav(words), "audio/wav")

    monkeypatch.setattr("acervo.models.google_tts.speech", speech)
    speech.calls = calls
    server.speech = speech
    server.push({"vocabularies": [vocabulary()]})
    return speech


def ask(server, **overrides):
    body = {"text": "asco", "language": "es", "direction": "repulsed, recoiling slightly", "take": 0}
    return server.post("/pronunciations/take", {**body, **overrides})


# ── the master ──────────────────────────────────────────────────────────────


def test_a_take_comes_back_as_the_lossless_master_and_not_as_a_clip(server):
    """The one place in Acervo that keeps audio uncompressed on purpose: a take is about to be
    stretched, pitched and mixed into a track that is itself encoded."""
    answer = ask(server)
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"].startswith("audio/flac")
    assert answer.content[:4] == b"fLaC"
    assert answer.headers["cache-control"] == "no-store"
    # Smaller than the WAV it came from, and bigger than the Opus a *clip* would have been.
    assert len(answer.content) < len(wav("asco"))


def test_the_answer_names_who_said_it_and_whether_the_direction_landed(server):
    answer = ask(server)
    assert answer.headers["x-acervo-provider"] == "google-tts"
    assert answer.headers["x-acervo-model"] == "gemini-3.1-flash-tts-preview"
    assert answer.headers["x-acervo-direction"] == "sent"
    assert server.speech.calls[-1]["style"]


def test_the_generators_note_reaches_the_voice_whole(server):
    """A take's `direction` is not an adjective, and it must not be framed as one.

    It is the generator's entire director note for this repetition, pace and pitch included, and the
    pace and pitch are the *only* things that differ between a word's three takes. It used to go into
    the example template's `sounding {emotion}` slot, which made a sentence that was not one and then
    cancelled that clause with a "Keep a natural pace" of its own — so every take of a word came back
    read the same way, whether or not the word carried an emotion.
    """
    note = ("Speak warmly, as if teaching someone, but clearly, slightly briskly, "
            "with a slightly brighter pitch.")
    ask(server, direction=note, text="la balsa")

    style = server.speech.calls[-1]["style"]
    assert note in style
    assert "Spanish" in style
    assert "sounding Speak" not in style
    assert "natural pace" not in style


def test_the_voice_header_means_one_thing_on_both_paths(server):
    """The voice *asked for*, empty when the owner chose none — and the same on a hit and a miss.

    A cache hit cannot know what answered, so reporting the answering voice on a fresh recording
    would make one header mean two things depending on something the caller cannot see.
    """
    fresh = ask(server, text="una palabra nueva")
    cached = ask(server, text="una palabra nueva")
    assert fresh.headers["x-acervo-voice"] == cached.headers["x-acervo-voice"] == ""

    server.put("/pronunciations/settings", {
        "voices": {"google-tts": {"gemini-3.1-flash-tts-preview": {"es": "Kore"}}}
    })
    chosen = ask(server, text="otra palabra")
    assert chosen.headers["x-acervo-voice"] == "Kore"
    assert ask(server, text="otra palabra").headers["x-acervo-voice"] == "Kore"


def test_no_direction_at_all_reads_as_none_rather_than_dropped(server):
    answer = ask(server, direction=None)
    assert answer.headers["x-acervo-direction"] == "none"
    assert server.speech.calls[-1]["style"] is None


def test_a_dropped_direction_is_an_answer_rather_than_a_failure(server):
    """A deployment with no instruction-following voice still gets loops — three distinguishable
    takes and no emotion — because LexiBeat varies them itself when it is told the direction went
    nowhere. The requirement is met by this contract rather than by a branch on either side."""
    assert server.put("/pronunciations/settings", {"delivery": {"loops": "plain"}}).status_code == 200
    answer = ask(server)
    assert answer.status_code == 200
    assert answer.headers["x-acervo-direction"] == "dropped"
    assert answer.headers["x-acervo-model"] == "wavenet"
    assert server.speech.calls[-1]["style"] is None


def test_an_expressive_order_with_no_directed_voice_drops_the_direction_and_is_found_again(server):
    """The clear order reads for it, and the take it records is keyed on what was sent — nothing —
    so the second request for the same line is served from disk rather than paid for again."""
    server.put("/models/selection", {"chains": {
        "audioExpressive": [{"provider": "google-tts", "model": "standard"}],
        "audioPlain": [{"provider": "google-tts", "model": "wavenet"}],
    }})
    first = ask(server)
    assert first.headers["x-acervo-direction"] == "dropped"
    assert first.headers["x-acervo-model"] == "wavenet"
    calls = len(server.speech.calls)
    again = ask(server)
    assert again.content == first.content and len(server.speech.calls) == calls


def test_a_take_recorded_plainly_is_not_served_once_a_directed_voice_answers_again(server):
    """One day without a directed voice must not leave a line flat in every later loop that uses the
    same words: the plain take is looked for only when no directed voice can read."""
    directed = server.put("/models/selection", {"chains": {
        "audioExpressive": [{"provider": "google-tts", "model": "standard"}],
        "audioPlain": [{"provider": "google-tts", "model": "wavenet"}],
    }})
    assert directed.status_code == 200
    assert ask(server).headers["x-acervo-direction"] == "dropped"
    server.put("/models/selection", {"chains": {"audioExpressive": None}})
    calls = len(server.speech.calls)
    again = ask(server)
    assert again.headers["x-acervo-direction"] == "sent"
    assert again.headers["x-acervo-model"] == "gemini-3.1-flash-tts-preview"
    assert len(server.speech.calls) == calls + 1


def test_directed_voices_out_of_reach_serve_the_plain_take_already_recorded(server):
    from acervo.models.errors import ProviderUnavailable

    server.put("/pronunciations/settings", {"delivery": {"loops": "plain"}})
    plain = ask(server)
    server.put("/pronunciations/settings", {"delivery": {"loops": "expressive"}})
    server.speech.failure = ProviderUnavailable("rate_limited", "quota", provider_id="google-tts", model="any")
    calls = len(server.speech.calls)
    answer = ask(server)
    assert answer.status_code == 200 and answer.content == plain.content
    assert answer.headers["x-acervo-direction"] == "dropped"
    assert {call["model"] for call in server.speech.calls[calls:]} == {
        "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-tts"}, "only the directed voices were asked"


def test_an_answer_that_arrived_compressed_is_passed_through_untouched(server):
    server.speech.answer = (MP3, "audio/mpeg")
    answer = ask(server)
    assert answer.content == MP3
    assert answer.headers["content-type"].startswith("audio/mpeg")


# ── the cache ───────────────────────────────────────────────────────────────


def test_the_same_line_is_recorded_once_and_served_from_disk_after(server):
    first = ask(server)
    calls = len(server.speech.calls)
    second = ask(server)
    assert second.content == first.content
    assert len(server.speech.calls) == calls, "the second ask should not have reached a provider"


def test_each_take_of_one_line_is_its_own_recording(server):
    """The subtle one. The director note quantises a continuous prosody into adjectives, so two
    takes can carry byte-identical instructions; without the index in the key the cache would hand
    back one recording for both and the repetition would sound *more* mechanical, not less."""
    ask(server, take=0)
    calls = len(server.speech.calls)
    assert ask(server, take=1).status_code == 200
    assert len(server.speech.calls) == calls + 1


def test_a_different_direction_is_a_different_recording(server):
    ask(server, direction="repulsed")
    calls = len(server.speech.calls)
    ask(server, direction="delighted")
    assert len(server.speech.calls) == calls + 1


def test_takes_land_in_the_cache_beside_the_database_and_never_in_the_media_volume(server):
    ask(server)
    kept, size = takes.usage(server.settings.takes_path)
    assert kept == 1 and size > 0
    assert not list(server.media.rglob("*.flac"))


def test_a_take_is_not_read_from_a_stored_pronunciation(server):
    """Tempting and wrong: a stored clip is Opus compressed for a phone, and stretching it would put
    a second lossy generation in front of the master."""
    answer = ask(server, direction=None)
    assert answer.content[:4] == b"fLaC"
    assert answer.content[:4] != b"OggS"


# ── what is refused ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("overrides", [
    {"text": ""}, {"text": "x" * 501}, {"language": "not a tag"},
    {"take": -1}, {"take": 99}, {"take": "first"},
])
def test_a_request_that_cannot_be_spoken_is_refused(server, overrides):
    assert ask(server, **overrides).status_code == 400


# ── the token ───────────────────────────────────────────────────────────────


def test_a_render_token_may_call_this_route(server):
    user = accounts.by_id(server.owner)
    token = mint_render(server.client.app.state.jwt_secret, user, render="loopmorning0001")
    answer = server.client.post(
        "/api/acervo/v1/pronunciations/take",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "asco", "language": "es", "direction": None, "take": 0},
    )
    assert answer.status_code == 200, answer.text
    assert answer.content[:4] == b"fLaC"


def test_a_render_token_may_call_nothing_else(server):
    """What the audience buys. A token lifted from the loop container is *only* this route."""
    user = accounts.by_id(server.owner)
    token = mint_render(server.client.app.state.jwt_secret, user, render="loopmorning0001")
    headers = {"Authorization": f"Bearer {token}"}
    assert server.client.get("/api/acervo/v1/graph?schemaVersion=11&since=0", headers=headers).status_code == 401
    assert server.client.get("/api/acervo/v1/pronunciations/settings", headers=headers).status_code == 401


def test_an_ordinary_session_may_call_it_too(server):
    """The owner's own session is strictly more privileged, so refusing it would buy nothing."""
    assert ask(server).status_code == 200


def test_an_unsigned_or_absent_token_is_refused(server):
    assert server.client.post("/api/acervo/v1/pronunciations/take", json={}).status_code == 401
    assert server.client.post(
        "/api/acervo/v1/pronunciations/take", headers={"Authorization": "Bearer nonsense"}, json={}
    ).status_code == 401


def test_the_audience_is_the_route_it_names(server):
    assert TAKE_AUDIENCE == "acervo:pronunciations/take"


# ── the guide's voice ───────────────────────────────────────────────────────

GEMINI = "gemini-3.1-flash-tts-preview"


def test_a_guide_line_is_said_by_the_guide_voice_and_a_native_one_is_not(server):
    server.put("/pronunciations/settings", {
        "voices": {"google-tts": {GEMINI: {"es": "Kore", "en": "Kore"}}},
        "guideVoices": {"google-tts": {GEMINI: {"en": "Charon"}}},
    })
    guide = ask(server, text="disgust", language="en", role="guide")
    assert guide.headers["x-acervo-voice"] == "Charon"
    assert server.speech.calls[-1]["voice"] == "Charon"
    # The same English words as a native line — an English vocabulary's own word — keep the voice
    # chosen for English, and are a recording of their own rather than the guide's take.
    native = ask(server, text="disgust", language="en", role="native")
    assert native.headers["x-acervo-voice"] == "Kore"
    assert server.speech.calls[-1]["voice"] == "Kore"
    assert ask(server, text="asco").headers["x-acervo-voice"] == "Kore"


def test_without_a_guide_voice_every_line_is_said_by_the_one_voice(server):
    server.put("/pronunciations/settings", {
        "voices": {"google-tts": {GEMINI: {"en": "Puck"}}}})
    assert ask(server, text="disgust", language="en", role="guide").headers["x-acervo-voice"] == "Puck"


def test_a_role_that_is_neither_is_refused(server):
    answer = ask(server, role="narrator")
    assert answer.status_code == 400
    assert "native or guide" in answer.json()["error"]["message"]


def test_the_settings_offer_voices_in_the_language_the_guide_speaks(server):
    view = server.get("/pronunciations/settings").json()["data"]
    assert view["languages"] == ["es"] and view["guideLanguages"] == ["en"]
    gemini = next(entry for entry in view["orders"]["expressive"] if entry["model"] == GEMINI)
    assert "Charon" in gemini["voices"]["en"]
    assert view["guideVoices"] == {}
    refused = server.put("/pronunciations/settings", {
        "guideVoices": {"google-tts": {GEMINI: {"en": "Nobody"}}}})
    assert refused.json()["error"]["code"] == "unknown_voice"
