"""Photo capture on the server: reading a photo, the quick look-up, and keeping the photo.

Vision is stubbed at the adapter and SaT at the segmenter, so what runs for real is everything
Acervo owns: the image preparation, the chain walk, the page layout, the pending store, the capture
split and the promotion of a photo by the save that names it.
"""

from __future__ import annotations

import io
import os
import time

import pytest
from PIL import Image

from acervo.domain import SCHEMA_VERSION
from acervo.models import google_vision
from acervo.models.results import OcrWord
from acervo.ocr import segment
from acervo.services import photo as photo_service

from graph_records import DEVICE, lexeme, vocabulary
from provider_rows import GOOGLE

SENTENCE = "Esta operación, llevada a cabo en secreto, fue ordenada por el rey."


def jpeg(width=400, height=300, exif: bytes | None = None) -> bytes:
    image = Image.new("RGB", (width, height), (240, 236, 228))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85, **({"exif": exif} if exif else {}))
    return out.getvalue()


def vision_words(text: str) -> list[OcrWord]:
    found = []
    for index, piece in enumerate(text.split(" ")):
        x = 10 + index * 30
        found.append(OcrWord(
            text=piece, polygon=((x, 40), (x + 28, 40), (x + 28, 60), (x, 60)),
            confidence=0.97, break_after="space" if index < len(text.split(" ")) - 1 else "eol",
            block=0, paragraph=0,
        ))
    return found


class Splitter:
    def split(self, text):
        return [(0, len(text))] if text else []


@pytest.fixture
def reader(server, monkeypatch):
    """A server that can read photos: the Vision row credentialed, its adapter stubbed."""
    server.add_provider(GOOGLE)
    asked = []

    def read(row, model, data, *, language_hints=(), timeout=15.0):
        asked.append({"bytes": data, "hints": list(language_hints)})
        return vision_words(SENTENCE), 400, 300, "es"

    monkeypatch.setattr(google_vision, "read", read)
    segment.use(Splitter())
    server.push({"vocabularies": [vocabulary()]})
    server.asked = asked
    yield server
    segment.use(None)


def read_photo(server, data: bytes):
    return server.client.post(
        "/api/acervo/v1/photo/read", headers={**server.auth, "Content-Type": "image/jpeg"}, content=data
    )


def test_a_photo_is_read_into_a_page_and_kept_pending(reader):
    answer = read_photo(reader, jpeg())
    assert answer.status_code == 200, answer.json()
    page = answer.json()["data"]

    assert page["language"] == "es" and page["vocabulary"] is True
    assert page["readBy"] == {"provider": "google-cloud", "model": "document-text-detection"}
    assert page["text"] == SENTENCE
    assert page["sentences"][0]["text"] == SENTENCE
    assert page["words"][0]["polygons"][0][0] == [0.025, 0.13333]
    assert reader.asked[0]["hints"] == ["es"], "the owner's languages are the hints"

    reference = page["photoRef"]
    assert reference.startswith(f"photos/{reader.owner}/") and reference.endswith(".jpg")
    assert not (reader.media / reference).exists(), "not kept until a save names it"
    assert photo_service.pending_path(reader.media, reference).is_file()


def test_a_photo_that_is_already_clean_is_kept_byte_for_byte(reader):
    data = jpeg()
    page = read_photo(reader, data).json()["data"]
    assert photo_service.pending_path(reader.media, page["photoRef"]).read_bytes() == data


def test_a_photo_carrying_exif_or_too_large_is_re_encoded_without_it(reader):
    exif = Image.Exif()
    exif[0x0110] = "a phone"  # Model
    page = read_photo(reader, jpeg(3000, 1500, exif.tobytes())).json()["data"]
    kept = Image.open(photo_service.pending_path(reader.media, page["photoRef"]))
    assert max(kept.size) == 2048
    assert not kept.getexif()
    assert (page["width"], page["height"]) == (2048, 1024)


def test_what_is_not_a_picture_is_refused_before_any_call(reader):
    answer = read_photo(reader, b"not an image at all")
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "unreadable_image"
    assert reader.asked == []


def test_a_language_the_owner_has_no_vocabulary_for_is_named(reader, monkeypatch):
    monkeypatch.setattr(google_vision, "read", lambda *a, **k: (vision_words("Bonjour."), 400, 300, "fr"))
    page = read_photo(reader, jpeg()).json()["data"]
    assert (page["language"], page["vocabulary"]) == ("fr", False)


def test_with_no_reader_configured_the_photo_is_refused_in_the_readers_words(server):
    answer = read_photo(server, jpeg())
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "capture_unavailable"


def test_a_photo_is_served_to_its_owner_only_and_never_while_pending(reader, other):
    reference = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    pending = photo_service.pending_path(reader.media, reference).relative_to(reader.media)
    assert reader.client.get(f"/api/acervo/media/{pending}", headers=reader.auth).status_code == 404

    os.replace(reader.media / pending, reader.media / reference)
    assert reader.client.get(f"/api/acervo/media/{reference}", headers=reader.auth).status_code == 200
    assert reader.client.get(f"/api/acervo/media/{reference}", headers=other.auth).status_code == 404


# ── the quick look-up, and capture after it ─────────────────────────────────

RESOLUTION = {
    "language": "es", "headword": "llevar a cabo", "lemma": "llevar a cabo", "pos": "idiom",
    "sentences": [{"text": SENTENCE}], "gloss": "to carry out", "note": "",
}

ARTICLE = {
    "headword": "llevar a cabo", "lemma": "llevar a cabo", "pos": "idiom", "shortGloss": "to carry out",
    "senses": [{
        "definition": "Realizar algo.", "glosses": [{"lang": "en", "terms": ["to carry out"]}],
        "examples": [{"text": SENTENCE, "translation": "This operation…", "fromSentence": 0}],
    }],
}


def quick(server, **overrides):
    return server.post("/capture/resolve", {
        "schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "source": "photo", "text": SENTENCE,
        "selection": {"start": 16, "end": 23}, **overrides,
    })


def test_the_quick_look_up_marks_the_tap_and_walks_the_quick_chain(reader):
    reader.model.resolution = dict(RESOLUTION)
    answer = quick(reader)
    assert answer.status_code == 200, answer.json()
    body = answer.json()["data"]
    assert body["resolution"]["gloss"] == "to carry out"
    assert body["duplicates"] == [] and body["foldable"] is None

    call = reader.model.calls[-1]
    system = next(m["content"] for m in call["messages"] if m["role"] == "system")
    user = next(m["content"] for m in call["messages"] if m["role"] == "user")
    assert "*llevada*" in user, "the tapped word is pointed at"
    assert "gloss in en" in user, "the gloss language is stated"
    assert "A quick look-up" in system and "Text from a photograph" in system
    assert call["model"] == "gemini/gemini-3.5-flash-lite", "the quick chain leads with flash-lite"


def test_typed_capture_is_asked_without_either_photo_section(reader):
    reader.model.resolution = dict(RESOLUTION)
    reader.model.article = dict(ARTICLE)
    reader.capture(text=SENTENCE)
    system = next(m["content"] for m in reader.model.calls[0]["messages"] if m["role"] == "system")
    assert "A quick look-up" not in system and "Text from a photograph" not in system


def test_a_word_already_held_comes_back_with_what_can_be_folded_in(reader):
    reader.push({"lexemes": [lexeme(headword="llevar a cabo", lemma="llevar a cabo")]})
    reader.model.resolution = dict(RESOLUTION)
    body = quick(reader).json()["data"]
    assert [d["headword"] for d in body["duplicates"]] == ["llevar a cabo"]
    assert body["foldable"]["sentences"][0]["text"] == SENTENCE


def test_capture_takes_the_resolution_and_does_not_resolve_again(reader):
    reader.model.article = dict(ARTICLE)
    reference = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    region = {"words": [[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]], "sentence": []}
    answer = reader.capture(text=SENTENCE, resolution=RESOLUTION, photoRef=reference,
                            photoRegion=region, sourceKind="book")
    assert answer.status_code == 200, answer.json()
    assert len(reader.model.calls) == 1, "compose only"
    draft = answer.json()["data"]["draft"]
    attestation = draft["attestations"][0]
    assert (attestation["text"], attestation["photoRef"], attestation["photoRegion"]) == (
        SENTENCE, reference, region
    )
    assert attestation["sourceKind"] == "book"
    assert draft["senses"][0]["examples"][0]["sourceAttestationId"] == attestation["id"]


def test_a_resolution_naming_a_sentence_the_text_does_not_contain_is_refused(reader):
    forged = {**RESOLUTION, "sentences": [{"text": "Una frase que nadie leyó."}]}
    answer = reader.capture(text=SENTENCE, resolution=forged)
    assert answer.status_code == 400
    assert reader.model.calls == []


def test_a_photo_that_is_no_longer_on_the_server_is_refused_before_compose(reader):
    missing = f"photos/{reader.owner}/{'0' * 16}.jpg"
    answer = reader.capture(text=SENTENCE, resolution=RESOLUTION, photoRef=missing)
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "photo_missing"
    assert reader.model.calls == []


def test_a_sign_with_no_sentence_keeps_the_photo_by_itself(reader):
    reader.model.article = {**ARTICLE, "senses": [{**ARTICLE["senses"][0], "examples": [
        {"text": "Salida de emergencia.", "fromSentence": 0}]}]}
    reference = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    sign = {**RESOLUTION, "headword": "la salida", "lemma": "salida", "sentences": []}
    draft = reader.capture(text="SALIDA", resolution=sign, photoRef=reference).json()["data"]["draft"]
    assert [(a["text"], a["photoRef"]) for a in draft["attestations"]] == [("", reference)]
    example = draft["senses"][0]["examples"][0]
    assert example["origin"] == "llm", "nothing is drawn from a photo that carried no sentence"


# ── keeping the photo ───────────────────────────────────────────────────────


def save(server, draft):
    return server.post("/articles", {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "draft": draft})


def drafted(reader, reference, resolution=RESOLUTION):
    reader.model.article = dict(ARTICLE)
    return reader.capture(text=SENTENCE, resolution=resolution, photoRef=reference).json()["data"]["draft"]


def test_the_save_that_names_a_photo_keeps_it(reader):
    reference = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    answer = save(reader, drafted(reader, reference))
    assert answer.status_code == 200, answer.json()
    assert (reader.media / reference).is_file()
    assert not photo_service.pending_path(reader.media, reference).exists()
    stored = answer.json()["data"]["records"]["attestations"][0]
    assert stored["photoRef"] == reference


def test_a_second_word_from_the_same_photo_finds_it_already_kept(reader):
    reference = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    assert save(reader, drafted(reader, reference)).status_code == 200
    king = {**RESOLUTION, "headword": "el rey", "lemma": "rey", "pos": "noun"}
    second = {**drafted(reader, reference, king), "headword": "el rey", "lemma": "rey"}
    assert save(reader, second).status_code == 200


def test_a_save_that_fails_leaves_the_photo_pending(reader):
    reference = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    broken = drafted(reader, reference)
    broken["senses"][0]["glosses"] = []  # refused by the record validator, after the attestation
    assert save(reader, broken).status_code == 400
    assert photo_service.pending_path(reader.media, reference).is_file()
    assert not (reader.media / reference).exists()


def test_a_write_naming_a_photo_nobody_uploaded_is_refused(reader):
    reference = f"photos/{reader.owner}/{'a' * 16}.jpg"
    answer = save(reader, drafted(reader, read_photo(reader, jpeg()).json()["data"]["photoRef"]) | {
        "attestations": [{"id": None, "text": SENTENCE, "photoRef": reference, "sourceKind": "book"}],
    })
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "photo_missing"


def test_a_photo_of_another_owner_cannot_be_named(reader, other):
    reference = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    other.push({"vocabularies": [vocabulary()]})
    answer = save(other, drafted(reader, reference))
    assert answer.status_code == 400


def test_the_sweep_removes_pending_photos_nobody_added_after_a_day(reader):
    old = read_photo(reader, jpeg()).json()["data"]["photoRef"]
    fresh = read_photo(reader, jpeg(401, 300)).json()["data"]["photoRef"]
    stale = photo_service.pending_path(reader.media, old)
    day_ago = time.time() - 25 * 3600
    os.utime(stale, (day_ago, day_ago))

    assert photo_service.sweep(reader.settings) == 1
    assert not stale.exists()
    assert photo_service.pending_path(reader.media, fresh).is_file()


def test_warming_answers_at_once(reader):
    assert reader.post("/photo/warm", {}).json()["data"] == {"warming": True}


def test_a_crop_is_stored_byte_for_byte_and_not_read(reader):
    """A scrolled screenshot is kept as the square that was on screen, cropped on the device."""
    data = jpeg(300, 300)
    answer = reader.client.post(
        "/api/acervo/v1/photo/store", headers={**reader.auth, "Content-Type": "image/jpeg"}, content=data
    )
    assert answer.status_code == 200, answer.json()
    stored = answer.json()["data"]
    assert (stored["width"], stored["height"]) == (300, 300)
    assert photo_service.pending_path(reader.media, stored["photoRef"]).read_bytes() == data
    assert reader.asked == [], "storing is not reading"
