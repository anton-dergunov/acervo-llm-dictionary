"""One word and its senses, assembled from wire-shaped records. The view every enrichment reads.

One view model with two feeders, the way `articleFor` and `articleFromDraft` both build one
`Article` on the client. `build_articles` takes the `changes` mapping the graph route speaks, so the
worker sweep feeds it a `client.pull_graph()` payload and a service feeds it rows the repository
projected — neither knows which. That is what keeps the interactive path and the unattended one on
one pipeline rather than two.

**It lives here rather than in `acervo.images` because it was never about pictures.** A clip
selector wants the same lexeme, the same senses and the same examples, and pronunciation audio will
want them next; what differs is the rule each applies afterwards. So this module holds the
assembling and nothing else, and each pipeline keeps its own judgement beside it —
`acervo.images.article.anchor_for` decides which example a picture illustrates, and no other package
has an opinion about that.

This module is **pure**: it imports nothing of Acervo's, opens no connection and reads no graph, and
`tests/unit/server/test_layering.py` enforces that. It and `acervo.models` are the two Acervo things
an enrichment package may import.

Deliberately a duplicate of the shape `web/src/selectors.ts` derives rather than a shared one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# A word the learner has set aside is not worth spending a model call on.
GENERATED_STATUSES = ("inbox", "active")


def live(records: Iterable[dict]) -> list[dict]:
    return [record for record in records if not record.get("deleted")]


@dataclass
class SenseView:
    id: str
    definition: str
    definition_lang: str
    domain: str | None
    glosses: list[dict]
    order: int
    examples: list[dict] = field(default_factory=list)


@dataclass
class ArticleView:
    lexeme: dict
    vocabulary: dict | None
    topics: list[str]
    senses: list[SenseView]

    @property
    def id(self) -> str:
        return self.lexeme["id"]

    @property
    def headword(self) -> str:
        return self.lexeme.get("headword", "")

    @property
    def lemma(self) -> str:
        """The dictionary form, falling back to the headword.

        Both readers of this want the same thing for the same reason: a dictionary and a caption
        corpus are keyed on the form a word is looked up under, not on the form it was met in.
        """
        return self.lexeme.get("lemma") or self.headword

    @property
    def language(self) -> str:
        return self.lexeme.get("language", "")

    @property
    def gloss_langs(self) -> list[str]:
        """The languages this vocabulary is translated into, most preferred first."""
        return (self.vocabulary or {}).get("glossLangs") or []


def build_articles(changes: dict[str, list[dict]], language: str | None = None) -> list[ArticleView]:
    """Every lexeme worth considering, with its senses and their examples attached."""
    vocabularies = {record["language"]: record for record in live(changes.get("vocabularies", []))}
    topics = {record["id"]: record for record in live(changes.get("topics", []))}
    lexemes = live(changes.get("lexemes", []))
    senses = live(changes.get("senses", []))
    examples = live(changes.get("examples", []))

    by_lexeme: dict[str, list[SenseView]] = {}
    for sense in sorted(senses, key=lambda record: (record.get("order", 0), record.get("id", ""))):
        view = SenseView(
            id=sense["id"],
            definition=sense.get("definition", ""),
            definition_lang=sense.get("definitionLang", ""),
            domain=sense.get("domain"),
            glosses=sense.get("glosses") or [],
            order=int(sense.get("order", 0) or 0),
        )
        by_lexeme.setdefault(sense["lexemeId"], []).append(view)

    index = {view.id: view for views in by_lexeme.values() for view in views}
    for example in examples:
        view = index.get(example.get("senseId", ""))
        if view is not None:
            view.examples.append(example)

    articles = []
    for lexeme in sorted(lexemes, key=lambda record: (record.get("headword", ""), record.get("id", ""))):
        if language and lexeme.get("language") != language:
            continue
        if lexeme.get("status") not in GENERATED_STATUSES:
            continue
        views = by_lexeme.get(lexeme["id"], [])
        if not views:
            continue
        articles.append(
            ArticleView(
                lexeme=lexeme,
                vocabulary=vocabularies.get(lexeme.get("language", "")),
                topics=[topics[topic]["name"] for topic in lexeme.get("topicIds", []) if topic in topics],
                senses=views,
            )
        )
    return articles


def article_for(changes: dict[str, list[dict]], lexeme_id: str) -> ArticleView | None:
    """The one word a request names, or nothing.

    Nothing covers three cases on purpose — no such word, somebody else's word, and a word set aside
    — because a caller that told them apart would be answering whether an id exists in another
    account.
    """
    return next((view for view in build_articles(changes) if view.id == lexeme_id), None)


def set_aside(changes: dict[str, list[dict]], lexeme_id: str) -> bool:
    """Whether these records — one owner's — hold this word live and set aside.

    Safe to say out loud where `article_for` is not: the records are the owner's own, so the answer
    is about their word, never about whether an id exists in another account.
    """
    return any(
        lexeme.get("id") == lexeme_id and lexeme.get("status") == "aside"
        for lexeme in live(changes.get("lexemes", []))
    )
