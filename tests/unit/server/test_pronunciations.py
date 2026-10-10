"""Pronouncing a record from a route, and what a clip is while its record changes under it.

Against the real service over a throwaway media directory. What is stubbed is the provider and only
the provider: Cloud TTS's adapter answers with fixed bytes and records what it was asked, so a test
can say which voice read a headword and whether an emotion reached the example.
"""

from __future__ import annotations

import io
import logging
import math
import struct
import wave

import pytest

from acervo.models.errors import ProviderRefused, ProviderUnavailable
from acervo.pronunciation.ids import pronunciation_id

from graph_records import attestation, example, lexeme, sense, vocabulary

DEVICE = "device000000001"
MP3 = b"ID3\x04\x00an-mp3-of-some-length"


def wav(words: str) -> bytes:
    """What Cloud TTS actually answers now: an uncompressed 24 kHz master, one that Opus can chew.

    Long enough per character that a re-encode is visibly smaller, and different per text so two
    clips cannot be confused for one another.
    """
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
    """Cloud TTS is credentialed and answers, so the catalogue's recommended orders stand."""
    credentials = tmp_path / "service-account.json"
    credentials.write_text("{}")
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project-name")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(credentials))
    monkeypatch.delenv("ACERVO_VERTEX_ACCOUNT", raising=False)
    calls: list[dict] = []

    def speech(row, model, words, **kwargs):
        calls.append({"provider": row.id, "model": model, "words": words, **kwargs})
        if model in speech.refusing:
            raise speech.refusing[model]
        failure = getattr(speech, "failure", None)
        if failure is not None:
            raise failure
        answer = getattr(speech, "answer", None)
        if answer is not None:
            return answer
        return wav(words), "audio/wav"

    monkeypatch.setattr("acervo.models.google_tts.speech", speech)
    speech.calls = calls
    # {model: error}: that model alone refuses, and the rest answer.
    speech.refusing = {}
    server.speech = speech
    return speech


def word(server, **overrides):
    entry = lexeme(status="active", **overrides)
    itch = sense(entry["id"], definition="Producir comezón.", definitionLang="es", order=0)
    sentence = example(
        itch["id"], text="¡Me pica todo!", translation="Everything itches!", translationLang="en",
        emotion="exasperated, scratching and complaining",
    )
    met = attestation(entry["id"])
    answer = server.push({
        "vocabularies": [vocabulary()], "lexemes": [entry], "senses": [itch],
        "attestations": [met], "examples": [sentence],
    })
    assert answer.status_code == 200, answer.json()
    return entry, itch, sentence, met


def say(server, collection, identifier, again=False):
    return server.post(f"/pronunciations/{collection}/{identifier}", {"deviceId": DEVICE, "again": again})


# ── a record ────────────────────────────────────────────────────────────────


def test_pressing_play_writes_the_file_and_a_row_at_the_derived_id(server):
    entry, itch, sentence, met = word(server)
    answer = say(server, "lexemes", entry["id"])
    assert answer.status_code == 200, answer.json()
    clip = answer.json()["data"]

    assert clip["id"] == pronunciation_id("lexeme", entry["id"])
    assert clip["targetKind"] == "lexeme" and clip["targetId"] == entry["id"]
    assert clip["text"] == "picar" and clip["lang"] == "es"
    assert clip["providerId"] == "google-tts" and clip["modelId"] == "wavenet"
    assert clip["voice"] == "es-ES-Wavenet-F"
    # Asked for uncompressed, stored as Opus: `pronunciation/encode.py`, measured blind in
    # `experiments/pronunciation-encoding/`.
    assert clip["audioMime"] == "audio/ogg" and clip["emotion"] is None
    assert clip["audioRef"].startswith(f"audio/{entry['id']}/{clip['id']}-") and clip["audioRef"].endswith(".ogg")
    kept = (server.media / clip["audioRef"]).read_bytes()
    assert kept[:4] == b"OggS"
    assert len(kept) < len(wav("picar")) / 3

    pulled = server.pull().json()["data"]["changes"]["pronunciations"]
    assert [row["id"] for row in pulled] == [clip["id"]]


def test_a_current_clip_is_reused_rather_than_recorded_twice(server):
    entry, *_ = word(server)
    first = say(server, "lexemes", entry["id"]).json()["data"]
    second = say(server, "lexemes", entry["id"]).json()["data"]
    assert len(server.speech.calls) == 1
    assert second["audioRef"] == first["audioRef"] and second["revision"] == first["revision"]


def test_an_edited_record_makes_its_clip_stale_and_the_next_press_records_the_new_words(server):
    entry, itch, sentence, _ = word(server)
    first = say(server, "examples", sentence["id"]).json()["data"]
    stored = next(row for row in server.pull().json()["data"]["changes"]["examples"] if row["id"] == sentence["id"])
    assert server.push({"examples": [{**stored, "text": "¡Me pica la espalda!"}]}).status_code == 200

    second = say(server, "examples", sentence["id"]).json()["data"]
    assert second["id"] == first["id"]
    assert second["text"] == "¡Me pica la espalda!"
    assert second["audioRef"] != first["audioRef"]
    assert not (server.media / first["audioRef"]).exists(), "the file the row no longer names is removed"
    assert (server.media / second["audioRef"]).exists()


def test_record_again_replaces_a_current_clip_at_the_same_id(server):
    entry, *_ = word(server)
    server.speech.calls.clear()
    first = say(server, "lexemes", entry["id"]).json()["data"]
    again = say(server, "lexemes", entry["id"], again=True).json()["data"]
    assert len(server.speech.calls) == 2
    assert again["id"] == first["id"] and again["revision"] > first["revision"]


def test_an_example_is_read_by_the_expressive_order_with_its_emotion_as_a_direction(server):
    entry, itch, sentence, _ = word(server)
    clip = say(server, "examples", sentence["id"]).json()["data"]
    asked = server.speech.calls[-1]
    assert asked["model"] == "gemini-3.1-flash-tts-preview"
    assert "exasperated, scratching and complaining" in asked["style"]
    assert "Spanish" in asked["style"]
    assert "¡Me pica todo!" not in asked["style"], "the direction must never carry the words themselves"
    assert clip["emotion"] == "exasperated, scratching and complaining"
    assert clip["voice"] == "Kore"


def test_a_headword_and_a_definition_get_no_direction_at_all(server):
    entry, itch, *_ = word(server)
    say(server, "lexemes", entry["id"])
    say(server, "senses", itch["id"])
    assert [call["style"] for call in server.speech.calls] == [None, None]
    assert server.speech.calls[-1]["language"] == "es"


def test_choosing_the_clear_order_for_examples_reads_them_plainly_and_cheaply(server):
    """The switch this replaces only stopped the *direction* being sent, so turning emotion off
    still spent the expensive voice on every sentence. Choosing the order is now the whole of it."""
    entry, itch, sentence, _ = word(server)
    assert server.put("/pronunciations/settings", {"delivery": {"examples": "plain"}}).status_code == 200
    clip = say(server, "examples", sentence["id"]).json()["data"]
    assert server.speech.calls[-1]["style"] is None
    assert clip["emotion"] is None
    # And the cheap voice actually read it: the order changed, not just what was sent to it.
    assert clip["modelId"] == "wavenet"


def test_delivery_takes_only_the_two_orders_and_the_three_uses(server):
    word(server)
    for body in ({"delivery": {"examples": "shouty"}}, {"delivery": {"nothing": "plain"}},
                 {"delivery": "expressive"}):
        assert server.put("/pronunciations/settings", body).status_code == 400


def test_an_expressive_order_with_no_directed_voice_is_read_by_the_clear_one(server, caplog):
    """A voice that cannot take a direction is skipped rather than asked, so it can never record a
    clip as though no emotion had been asked for — and when that leaves nobody, the clear order
    reads, plainly, and the log says so."""
    entry, itch, sentence, _ = word(server)
    server.put("/models/selection", {"chains": {
        "audioExpressive": [{"provider": "google-tts", "model": "standard"}],
        "audioPlain": [{"provider": "google-tts", "model": "wavenet"}],
    }})
    with caplog.at_level(logging.INFO, logger="acervo.models.calls"):
        clip = say(server, "examples", sentence["id"]).json()["data"]
    assert [call["model"] for call in server.speech.calls] == ["wavenet"], "the saved plain voice was skipped"
    assert server.speech.calls[-1]["style"] is None
    assert clip["modelId"] == "wavenet" and clip["emotion"] is None
    assert any("result=undirected" in record.getMessage() and "reason=no_directed_voice" in record.getMessage()
               for record in caplog.records)


def test_directed_voices_that_are_all_out_of_reach_hand_over_to_the_clear_order(server, caplog):
    entry, itch, sentence, _ = word(server)
    for model in ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-tts"):
        server.speech.refusing[model] = ProviderUnavailable("rate_limited", "quota", provider_id="google-tts", model=model)
    with caplog.at_level(logging.INFO, logger="acervo.models.calls"):
        clip = say(server, "examples", sentence["id"]).json()["data"]
    assert clip["modelId"] == "wavenet" and clip["emotion"] is None
    assert server.speech.calls[-1]["style"] is None
    assert any("result=undirected" in record.getMessage() and "reason=rate_limited" in record.getMessage()
               for record in caplog.records)


def test_a_pair_the_catalogue_stopped_offering_is_stepped_over_and_the_rest_of_the_order_reads(server, caplog):
    """A saved order outlives the rows it names. When one of them stopped offering speech, the order
    still naming it refused every word before any voice was asked — with the voice behind it able to
    read them. The pair is stepped over, and the call log says which."""
    from acervo.repository import model_selection

    entry, *_ = word(server)
    model_selection.save(server.owner, {"audioPlain": [
        ("gemini-free", "gemini/gemini-3.1-flash-tts-preview"), ("google-tts", "standard"),
    ]})
    with caplog.at_level(logging.INFO, logger="acervo.models.calls"):
        answer = say(server, "lexemes", entry["id"])
    assert answer.status_code == 200, answer.json()
    assert answer.json()["data"]["modelId"] == "standard"
    skipped = [record.getMessage() for record in caplog.records if "result=skipped" in record.getMessage()]
    assert skipped and "reason=retired" in skipped[0] and "order=audioPlain" in skipped[0]
    assert "pair=gemini-free:gemini/gemini-3.1-flash-tts-preview" in skipped[0]
    assert model_selection.chains(server.owner)["audioPlain"][0][0] == "gemini-free", "kept as saved"
    # The pane is told what will happen — a voice answers — and may save the order without the pair.
    assert server.get("/models").json()["data"]["chains"]["audioPlain"]["reason"] is None
    saved = server.put("/models/selection", {"chains": {
        "audioPlain": [{"provider": "google-tts", "model": "standard"}]}})
    assert saved.status_code == 200


def test_an_order_naming_only_pairs_no_longer_offered_reads_as_though_none_were_chosen(server):
    from acervo.repository import model_selection

    entry, itch, sentence, _ = word(server)
    model_selection.save(server.owner, {
        "audioPlain": [("vertex", "gemini-2.5-flash-preview-tts")],
        "audioExpressive": [("gemini-free", "gemini/gemini-3.1-flash-tts-preview")],
    })
    assert say(server, "lexemes", entry["id"]).json()["data"]["modelId"] == "wavenet"
    clip = say(server, "examples", sentence["id"]).json()["data"]
    assert clip["modelId"] == "gemini-3.1-flash-tts-preview" and clip["emotion"]


def test_an_order_saved_empty_is_still_every_voice_switched_off(server):
    entry, *_ = word(server)
    server.put("/models/selection", {"chains": {"audioPlain": []}})
    answer = say(server, "lexemes", entry["id"])
    assert answer.status_code == 503 and not server.speech.calls


def test_a_refusal_keeps_what_the_provider_said_for_the_log_and_not_for_the_owner(server, caplog):
    entry, *_ = word(server)
    server.speech.failure = ProviderRefused(
        "configuration", "es-ES-Wavenet-Z is not a voice", provider_id="google-tts", model="wavenet")
    with caplog.at_level(logging.INFO):
        answer = say(server, "lexemes", entry["id"])
    assert answer.json()["error"]["code"] == "llm_configuration"
    assert "Wavenet-Z" not in answer.json()["error"]["message"]
    lines = [record.getMessage() for record in caplog.records]
    assert any("pronounce-word outcome" in line and 'detail="es-ES-Wavenet-Z is not a voice"' in line
               for line in lines)
    assert any(line.startswith("refused ") and "Wavenet-Z" in line for line in lines), "the activity log too"


def test_a_rejected_credential_is_not_routed_around(server):
    """Falling through a rejected key would only spend another allowance on the same mistake."""
    entry, itch, sentence, _ = word(server)
    server.speech.refusing["gemini-3.1-flash-tts-preview"] = ProviderRefused(
        "authentication", "bad key", provider_id="google-tts", model="gemini-3.1-flash-tts-preview")
    answer = say(server, "examples", sentence["id"])
    assert answer.status_code >= 400
    assert "wavenet" not in {call["model"] for call in server.speech.calls}


def test_a_language_no_model_in_the_order_speaks_is_its_own_refusal(server):
    entry = lexeme(language="fr", headword="piquer", lemma="piquer", status="active")
    assert server.push({"lexemes": [entry]}).status_code == 200
    server.put("/models/selection", {"chains": {"audioPlain": [{"provider": "google-tts", "model": "wavenet"}]}})
    answer = say(server, "lexemes", entry["id"])
    assert answer.status_code == 422
    assert answer.json()["error"]["code"] == "no_voice_for_language"
    assert "French" in answer.json()["error"]["message"]


def test_a_rate_limit_is_the_same_code_every_other_model_speaks(server):
    entry, *_ = word(server)
    server.put("/models/selection", {"chains": {"audioPlain": [{"provider": "google-tts", "model": "wavenet"}]}})
    server.speech.failure = ProviderUnavailable("rate_limited", "quota", provider_id="google-tts", model="wavenet")
    answer = say(server, "lexemes", entry["id"])
    assert answer.json()["error"]["code"] == "llm_rate_limited"
    assert "speech model" in answer.json()["error"]["message"]
    assert not list(server.media.rglob("*.ogg")), "nothing is written when nothing was spoken"


def test_a_provider_that_already_compressed_its_answer_is_stored_as_it_arrived(server):
    """Aura answers MP3. Re-encoding a lossy stream into another codec would add a second generation
    of artifacts to save a few kilobytes, which is the opposite of the point."""
    entry, *_ = word(server)
    server.speech.answer = (MP3, "audio/mpeg")
    clip = say(server, "lexemes", entry["id"]).json()["data"]
    assert clip["audioMime"] == "audio/mpeg" and clip["audioRef"].endswith(".mp3")
    assert (server.media / clip["audioRef"]).read_bytes() == MP3


def test_the_media_route_serves_the_clip_to_its_owner_only(server):
    entry, *_ = word(server)
    clip = say(server, "lexemes", entry["id"]).json()["data"]
    served = server.client.get(f"/api/acervo/media/{clip['audioRef']}", headers=server.auth)
    assert served.status_code == 200 and served.content.startswith(b"OggS")
    assert server.client.get(f"/api/acervo/media/{clip['audioRef']}").status_code == 401


def test_another_owners_record_cannot_be_pronounced(server, other):
    entry, *_ = word(server)
    assert other.post(f"/pronunciations/lexemes/{entry['id']}", {"deviceId": DEVICE}).status_code == 404
    assert say(server, "vibes", entry["id"]).status_code == 404


def test_an_attestation_is_read_in_its_words_language(server):
    entry, itch, sentence, met = word(server)
    clip = say(server, "attestations", met["id"]).json()["data"]
    assert clip["lang"] == "es" and clip["text"] == met["text"]


# ── a selection ─────────────────────────────────────────────────────────────


def test_a_selection_is_spoken_and_never_stored(server):
    """Compressed on the way out even though nothing is kept: it is downloaded before it can be
    heard, and a master is four times the wait for audio that lives one playback."""
    word(server)
    answer = server.post("/pronunciations/utterance", {"text": "Everything itches!", "language": "en"})
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "audio/ogg"
    assert answer.content[:4] == b"OggS"
    assert len(answer.content) < len(wav("Everything itches!")) / 3
    assert answer.headers["x-acervo-voice"] == "en-US-Wavenet-C"
    assert server.pull().json()["data"]["changes"]["pronunciations"] == []


def test_a_selection_must_say_what_language_it_is_in(server):
    assert server.post("/pronunciations/utterance", {"text": "hola", "language": ""}).status_code == 400
    assert server.post("/pronunciations/utterance", {"text": "", "language": "es"}).status_code == 400


# ── settings and restoring ──────────────────────────────────────────────────


def test_settings_follow_the_default_until_chosen_and_are_per_owner(server, other):
    word(server)
    view = server.get("/pronunciations/settings").json()["data"]
    assert view["chosen"] is False
    # No word is recorded in advance until asked; a story is, because that is what a narrator is for.
    assert view["pregenerate"] == {
        "headword": False, "definitions": False, "examples": False, "stories": True,
    }
    # Words read by the clear, even voice; examples, loops and stories by the one that takes a direction.
    assert view["delivery"] == {
        "words": "plain", "examples": "expressive", "loops": "expressive", "stories": "expressive",
    }
    assert view["languages"] == ["es"]
    plain = {(entry["provider"], entry["model"]): entry for entry in view["orders"]["plain"]}
    assert plain[("google-tts", "wavenet")]["voices"]["es"][0] == "es-ES-Wavenet-F"

    saved = server.put("/pronunciations/settings", {
        "pregenerate": {"headword": True},
        "voices": {"google-tts": {"wavenet": {"es": "es-ES-Wavenet-E"}}},
    }).json()["data"]
    assert saved["chosen"] is True and saved["pregenerate"]["headword"] is True
    assert saved["pregenerate"]["stories"] is True, "what was not named keeps its default"
    stories_off = server.put("/pronunciations/settings", {
        "pregenerate": {"stories": False}, "delivery": {"stories": "plain"},
    }).json()["data"]
    assert stories_off["pregenerate"]["stories"] is False and stories_off["delivery"]["stories"] == "plain"
    assert other.get("/pronunciations/settings").json()["data"]["chosen"] is False


def test_a_chosen_voice_is_the_one_that_reads(server):
    entry, *_ = word(server)
    server.put("/pronunciations/settings", {"voices": {"google-tts": {"wavenet": {"es": "es-ES-Wavenet-E"}}}})
    clip = say(server, "lexemes", entry["id"]).json()["data"]
    assert server.speech.calls[-1]["voice"] == "es-ES-Wavenet-E"
    assert clip["voice"] == "es-ES-Wavenet-E"


def test_a_voice_the_catalogue_does_not_offer_is_refused(server):
    answer = server.put("/pronunciations/settings", {"voices": {"google-tts": {"wavenet": {"es": "en-US-Wavenet-C"}}}})
    assert answer.json()["error"]["code"] == "unknown_voice"


def test_an_exported_clip_is_put_back_with_who_recorded_it(server):
    entry, *_ = word(server)
    answer = server.client.put(
        f"/api/acervo/v1/pronunciations/lexemes/{entry['id']}/audio",
        params={"text": "picar", "providerId": "google-tts", "modelId": "wavenet", "voice": "es-ES-Wavenet-F"},
        headers={**server.auth, "X-Acervo-Device": DEVICE, "Content-Type": "audio/mpeg"},
        content=MP3,
    )
    assert answer.status_code == 200, answer.json()
    clip = answer.json()["data"]
    assert clip["modelId"] == "wavenet" and clip["voice"] == "es-ES-Wavenet-F"
    # A bundle's clip is put back byte for byte, whatever it was recorded as: it is already a file.
    assert clip["audioMime"] == "audio/mpeg"
    assert server.speech.calls == [], "restoring spends nothing"
    # And it is current, so pressing play reuses it.
    say(server, "lexemes", entry["id"])
    assert server.speech.calls == []


def test_a_clip_of_words_the_record_no_longer_holds_is_refused(server):
    entry, *_ = word(server)
    answer = server.client.put(
        f"/api/acervo/v1/pronunciations/lexemes/{entry['id']}/audio",
        params={"text": "picaron", "providerId": "google-tts", "modelId": "wavenet"},
        headers={**server.auth, "X-Acervo-Device": DEVICE}, content=MP3,
    )
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "stale_clip"


# ── the call log ────────────────────────────────────────────────────────────


def test_every_request_leaves_one_outcome_line_saying_what_happened(server, caplog):
    entry, itch, sentence, _ = word(server)
    with caplog.at_level(logging.INFO, logger="acervo.models.calls"):
        say(server, "examples", sentence["id"])
        say(server, "examples", sentence["id"])
    outcomes = [record.getMessage() for record in caplog.records if " outcome " in record.getMessage()]
    assert len(outcomes) == 2
    assert outcomes[0].startswith("pronounce-sentence outcome target=example:")
    assert "source=generated" in outcomes[0] and "result=stored" in outcomes[0]
    assert "pair=google-tts:gemini-3.1-flash-tts-preview" in outcomes[0] and "style=yes" in outcomes[0]
    assert 'text="¡Me pica todo!"' in outcomes[0]
    assert "source=reused" in outcomes[1]
