"""The concept card: what the brief writer is told about one shared concept.

A starter concept (`docs/plans/first-use/starter-concepts.yaml`) is one meaning that twenty
vocabularies share, so its one picture is drawn from the concept, not from any one word. The card is
built as a one-sense English article (`acervo.article.ArticleView`), so the app's own brief writer,
template and style table (`acervo.images.brief`, `prompts/acervo_image_brief.md`,
`config/image-styles.yaml`) take it unchanged:

- the lexeme is English: the headword en-US matched to the concept (or the concept's id without its
  suffix), its part of speech, the concept's English `sense` as the short gloss, and as notes the
  concept's `note` and the definitions three other vocabularies matched to it, which pin the meaning;
- the one sense's definition is the concept's `sense`, and its glosses the pinning vocabularies'
  headwords. It has **no examples**. With en-US's example sentences the writer drew the sentence,
  as the app does for a word's own picture: "My wife loves to read books in the evening" became a
  woman reading alone. With none it draws the meaning itself (a wedding band, a family resemblance),
  which a picture shown under twenty vocabularies needs (README, "Method").

Everything is read from the committed starter build: the concept list through
`scripts/starter/build.py`'s `load_concepts`, and every `data/starter/<id>/match/<topic>.json` entry
whose `concept` is the concept.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STARTER = ROOT / "data" / "starter"


def _builder():
    """`scripts/starter/build.py`, loaded by path under its own name (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("starter_build", ROOT / "scripts" / "starter" / "build.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up there
    spec.loader.exec_module(module)
    return module


build = _builder()

# The vocabularies whose matched definitions pin a concept's meaning, in the order they are tried:
# languages that cut meanings differently from English and from each other. Their definitions are in
# English. en-US is not among them: its definitions are written in Spanish, and it gives only the
# headword.
PINNING = ("es-ES", "de-DE", "ru", "ja-JP", "fr-FR", "zh-CN", "it-IT", "pt-BR", "ko-KR", "tr-TR", "pl-PL",
           "nl-NL", "es-MX", "el-GR", "hi-IN", "ar", "vi-VN", "id-ID", "th-TH")
PINS = 3


@dataclass
class Match:
    vocabulary: str
    language: str
    sense_id: str
    headword: str
    definition: str


@dataclass
class Card:
    id: str
    topic: str
    sense: str
    pos: str
    note: str | None
    headword: str
    pins: list[Match] = field(default_factory=list)   # the pinning vocabularies' matches
    vocabularies: int = 0                              # how many vocabularies matched it

    def summary(self) -> dict[str, Any]:
        """What the review page and the brief file show of the card."""
        return {"id": self.id, "topic": self.topic, "sense": self.sense, "pos": self.pos, "note": self.note,
                "headword": self.headword, "vocabularies": self.vocabularies,
                "pins": [{"vocabulary": m.vocabulary, "headword": m.headword, "definition": m.definition}
                         for m in self.pins]}


def _languages() -> dict[str, str]:
    vocabularies, _topics = build.load_vocabularies()
    return {v["id"]: v["language"] for v in vocabularies}


def _matches() -> dict[str, dict[str, list[dict]]]:
    """concept id → vocabulary id → its match entries for that concept."""
    found: dict[str, dict[str, list[dict]]] = {}
    for folder in sorted(p for p in STARTER.iterdir() if (p / "match").is_dir()):
        for path in sorted((folder / "match").glob("*.json")):
            for entry in json.loads(path.read_text(encoding="utf-8")).get("matches") or []:
                if entry.get("concept"):
                    found.setdefault(entry["concept"], {}).setdefault(folder.name, []).append(entry)
    return found


def cards() -> list[Card]:
    """Every concept that has a shared picture, in the concept list's order."""
    languages = _languages()
    matches = _matches()
    made = []
    for topic, concepts in build.load_concepts().items():
        for concept in concepts:
            if not concept.picture:
                continue
            by_vocabulary = matches.get(concept.id, {})
            en = (by_vocabulary.get("en-US") or [None])[0]
            headword = en["headword"] if en else concept.id.split("-")[0]
            pins = [Match(v, languages[v], e["id"], e["headword"], e["definition"])
                    for v in PINNING if (e := (by_vocabulary.get(v) or [None])[0])][:PINS]
            made.append(Card(concept.id, topic, concept.sense, concept.pos, concept.note, headword, pins,
                             len(by_vocabulary)))
    return made


def article(card: Card):
    """The card as the one-sense English article the brief writer reads."""
    from acervo.article import ArticleView, SenseView

    notes = [card.note] if card.note else []
    notes += [f"{m.vocabulary} «{m.headword}»: {m.definition}" for m in card.pins]
    glosses = [{"lang": m.language, "terms": [m.headword]} for m in card.pins]
    lexeme = {"id": card.id, "headword": card.headword, "lemma": card.headword, "language": "en",
              "pos": card.pos, "register": "neutral", "dialect": None, "shortGloss": card.sense, "notes": notes}
    sense = SenseView(id=card.id, definition=card.sense, definition_lang="en", domain=None,
                      glosses=glosses, order=0, examples=[])
    return ArticleView(lexeme=lexeme, vocabulary={"language": "en", "glossLangs": [m.language for m in card.pins]},
                       topics=[card.topic], senses=[sense])
