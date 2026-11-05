"""The passages, turned into exactly what the shipped selector is given.

Nothing here builds a request or parses a reply: `acervo.clips.select.build_request` and
`parse_reply` do both, so what is measured is the pipeline rather than a copy of it. This module
only assembles the two things they take — an `ArticleView` and a list of `Candidate` — from the
tracked `passages.json`.

A clause list is stored as the text of each clause, and the spans are computed here by walking the
source, because a partition that is written as character offsets drifts the first time anybody
corrects a comma.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from acervo.article import ArticleView, build_articles
from acervo.clips.corpus import Candidate

HERE = Path(__file__).resolve().parent
PASSAGES = HERE / "passages.json"

SYNC = {
    "deleted": False, "createdAt": "2026-09-01T00:00:00.000Z",
    "editedAt": "2026-09-01T00:00:00.000Z", "editedBy": "experiment", "revision": 1,
}


@dataclass(frozen=True)
class Clause:
    """One clause of a source passage, and what its presence looks like in one target language."""

    text: str
    start: int
    end: int
    anchors: tuple[str, ...]

    @property
    def weight(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Passage:
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def sentence(self) -> str:
        return self.raw["sentence"]

    @property
    def source_lang(self) -> str:
        return self.raw["sourceLang"]

    @property
    def targets(self) -> list[str]:
        return list(self.raw["targets"])

    @property
    def expect(self) -> str:
        return self.raw["expect"]

    def clauses(self, target_lang: str) -> list[Clause]:
        """The partition, with spans derived by walking the source.

        Asserted rather than trusted: if the clause texts stop reconstructing the sentence, every
        coverage number computed from them is meaningless, and it must fail here rather than quietly
        score 0.9.
        """
        out: list[Clause] = []
        cursor = 0
        for clause in self.raw["clauses"]:
            text = clause["src"]
            assert self.sentence[cursor:cursor + len(text)] == text, (
                f"{self.id}: clause {text!r} is not at offset {cursor}")
            out.append(Clause(text, cursor, cursor + len(text),
                              tuple(clause["any"][target_lang])))
            cursor += len(text)
        assert cursor == len(self.sentence), f"{self.id}: clauses do not reach the end"
        return out


def load() -> list[Passage]:
    payload = json.loads(PASSAGES.read_text(encoding="utf-8"))
    return [Passage(row) for row in payload["passages"]]


def by_id() -> dict[str, Passage]:
    return {passage.id: passage for passage in load()}


# ── what the selector is given ──────────────────────────────────────────────


def _ids(passage: Passage) -> tuple[str, str, str]:
    """Stable, 15-character, lowercase alphanumeric, as every Acervo id is."""
    stem = "".join(c for c in passage.id.lower() if c.isalnum())[:9].ljust(9, "0")
    return f"v{stem}00000"[:15], f"l{stem}00000"[:15], f"s{stem}00000"[:15]


def article_for(passage: Passage, target_lang: str, *, with_decoy: bool) -> ArticleView:
    """One lexeme, one or two senses, and the example each sense already has.

    The decoy is the passage's own neighbouring sense — the shape that makes refusing meaningful,
    since a selector that cannot tell two senses apart has somewhere wrong to put the clip. Left out
    in translate mode, where the question is what the translation says rather than where it goes.

    **The examples are here because leaving them out was a real gap.** A production request carries
    every sense with the examples it already holds, and this experiment's first version sent none —
    so the requests it measured were a shape the server never actually sends. An example's own
    translation is included only when it is in the language being asked for; a row translating into
    Japanese gets the example's text alone rather than an authored Japanese sentence nobody here can
    check.
    """
    vocabulary_id, lexeme_id, sense_id = _ids(passage)
    senses = [{
        "id": sense_id, "lexemeId": lexeme_id, "order": 0, "domain": None,
        "definition": passage.raw["sense"]["definition"],
        "definitionLang": passage.raw["sense"]["definitionLang"],
        "glosses": passage.raw["sense"]["glosses"], **SYNC,
    }]
    if with_decoy:
        senses.append({
            "id": sense_id[:-1] + "2", "lexemeId": lexeme_id, "order": 1, "domain": None,
            "definition": passage.raw["decoySense"]["definition"],
            "definitionLang": passage.raw["decoySense"]["definitionLang"],
            "glosses": passage.raw["decoySense"]["glosses"], **SYNC,
        })
    changes = {
        "vocabularies": [{
            "id": vocabulary_id, "language": passage.source_lang,
            "definitionLang": passage.source_lang, "glossLangs": [target_lang],
            "notesLang": target_lang, **SYNC,
        }],
        "topics": [],
        "lexemes": [{
            "id": lexeme_id, "language": passage.source_lang, "headword": passage.raw["headword"],
            "lemma": passage.raw["lemma"], "pos": passage.raw["pos"], "status": "inbox",
            "topicIds": [], "notes": [], "shortGloss": passage.raw["shortGloss"], **SYNC,
        }],
        "senses": senses,
        "examples": _examples_for(passage, senses, target_lang),
        "attestations": [], "imagePrompts": [], "studyStates": [],
    }
    articles = build_articles(changes, passage.source_lang)
    assert len(articles) == 1
    return articles[0]


def _examples_for(passage: Passage, senses: list[dict], target_lang: str) -> list[dict]:
    """One generated example per sense, as `acervo_compose.md` would have written it."""
    example = passage.raw.get("example")
    if not example:
        return []
    translation = example.get("translations", {}).get(target_lang)
    return [{
        "id": f"x{sense['id'][1:]}"[:15], "senseId": sense["id"],
        "text": example["text"], "textLang": passage.source_lang,
        "translation": translation, "translationLang": target_lang if translation else None,
        "origin": "llm", "modelId": "gemini-3.5-flash-lite", **SYNC,
    } for sense in senses[:1]]


def candidate_for(passage: Passage, rank: int = 1) -> Candidate:
    """The passage as the corpus would have handed it over."""
    provenance = passage.raw["provenance"]
    start = passage.sentence.find(passage.raw["matchedForm"])
    assert start >= 0, f"{passage.id}: the matched form is not in the sentence"
    return Candidate(
        segment_id=provenance["segmentId"],
        sentence=passage.sentence,
        matched_surface=passage.raw["matchedForm"],
        char_start=start,
        char_end=start + len(passage.raw["matchedForm"]),
        clip_start=float(provenance["clipStart"]),
        clip_end=float(provenance["clipEnd"]),
        video_url=provenance["videoUrl"],
        video_title=provenance["videoTitle"],
        channel=provenance["channel"],
        caption_kind=provenance["captionKind"],
        speech_style=tuple(provenance["speechStyle"]),
        varieties=tuple(provenance["variety"]),
        boundary_reason=provenance["boundary"],
        rank=rank,
    )


def pool_for(passage: Passage, others: Sequence[Passage]) -> list[Candidate]:
    """A select-mode candidate list: the passage, plus distractors from the same language.

    Assembled rather than retrieved, and the write-up says so. It is valid for the paired
    before/after comparison, which is what the refusal-rate guard needs, and invalid as an absolute
    production refusal rate.
    """
    same = [other for other in others
            if other.id != passage.id and other.source_lang == passage.source_lang]
    pool = [candidate_for(passage, rank=1)]
    pool += [candidate_for(other, rank=index) for index, other in enumerate(same, start=2)]
    return pool
