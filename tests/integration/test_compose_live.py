"""Real compose calls: does each text model define a word in the language the vocabulary asks for?

Gated off, because it costs money. Run it after any change to `prompts/acervo_compose.md` or to the
compose request (`services/capture/compose.build_user_message`):

    RUN_LIVE_COMPOSE_TESTS=true .venv/bin/python -m pytest tests/integration/test_compose_live.py -v

Three setups, one word each, sent exactly as compose sends them (`compose_parts`) to every text model
in this machine's `providers.local.json`: a word defined in the learner's language, a word defined in
its own language, and a word defined in a third language in another script. Each reply must pass
compose's own check. The measured failure was a model writing the definitions in the word's
language whatever it was told (`experiments/definition-language/`). A model can still slip on one
word in fifty, so a single failure is worth re-running before it is believed; its sentence says what
was written.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from acervo.models import call
from acervo.models.errors import ProviderUnavailable
from acervo.models.local import LocalProvidersMissing, load_local
from acervo.services.capture.compose import compose_parts
from acervo.services.capture.vet import definition_doubt

pytestmark = pytest.mark.integration

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"

try:
    CATALOGUE = load_local()
except LocalProvidersMissing:
    from acervo.models.providers import Providers

    CATALOGUE = Providers()

SETUPS = {
    "learners-language": ({"language": "it", "definitionLang": "en", "glossLangs": ["en"], "notesLang": "en"},
                          {"language": "it", "headword": "la sedia", "lemma": "sedia", "pos": "noun"}),
    "words-own-language": ({"language": "es", "definitionLang": "es", "glossLangs": ["en"], "notesLang": "en"},
                           {"language": "es", "headword": "la silla", "lemma": "silla", "pos": "noun"}),
    "third-language": ({"language": "de", "definitionLang": "ru", "glossLangs": ["ru"], "notesLang": "ru"},
                       {"language": "de", "headword": "der Stuhl", "lemma": "Stuhl", "pos": "noun"}),
}


@pytest.fixture(scope="module", autouse=True)
def gated():
    if os.environ.get("RUN_LIVE_COMPOSE_TESTS") != "true":
        pytest.skip("set RUN_LIVE_COMPOSE_TESTS=true to spend real money on real compose calls")


def pairs() -> list[tuple[str, str]]:
    return [(row.id, model) for row in CATALOGUE.serving("text") for model in row.models_for("text")]


@pytest.mark.parametrize("setup", list(SETUPS))
@pytest.mark.parametrize(("identifier", "model"), pairs(), ids=lambda v: v.split("/")[-1])
def test_a_word_is_defined_in_the_language_the_vocabulary_asks_for(identifier, model, setup, tmp_path):
    row = CATALOGUE.find(identifier)
    if not row.available:
        pytest.skip(f"{identifier}: {row.reason()}")
    vocabulary, resolution = SETUPS[setup]
    resolution = {**resolution, "sentences": []}
    # No dictionary is installed, so only the language and the shape are judged here.
    system, user, check = compose_parts(PROMPTS, tmp_path, resolution, {}, {**vocabulary, "level": "A2"},
                                        [{"name": "Home"}])
    try:
        result = call.text(user, row=row, model=model, system=system, as_json=True)
    except ProviderUnavailable as error:
        if error.reason != "rate_limited":
            raise
        pytest.skip(f"{identifier}: reached, and out of quota")
    assert isinstance(result.parsed, dict), f"unparseable reply: {result.text[:200]!r}"
    senses = result.parsed.get("senses") or []
    doubts = [definition_doubt(s.get("definition"), vocabulary, resolution, [resolution["headword"]])
              for s in senses if isinstance(s, dict)]
    assert not any(doubts), [d[0] for d in doubts if d] + [s.get("definition") for s in senses]
    check(result.parsed)  # the rest of compose's check: glosses and notes in their languages too
