"""The first of the two calls: one text call per lexeme, covering all of its senses at once.

Batched per lexeme on purpose (`docs/features/sense-images.md` §03). A call that sees
every sense of `venom` at once can deliberately make the two pictures look nothing alike, which is
the only reason per-sense images beat one picture per word.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from acervo.models import ChainExhausted, TextResult, call, chain, journal
from acervo.models.errors import SHAPE_TRIES, ProviderUnavailable
from acervo.models.providers import Providers

from acervo.article import ArticleView

from .article import anchor_for
from .styles import StyleTable

# What the writer must return is stated in `prompts/acervo_image_brief.md`, with a worked example
# naming every field — and it is stated *there and only there*. No JSON Schema is sent: see
# AGENTS.md, "Constrained decoding is not used". `parse_reply` below is the contract that is
# actually enforced, and it checks what a schema never could — this article's own sense ids, and
# the styles this particular call offered.


@dataclass(frozen=True)
class SenseBrief:
    sense_id: str
    style_id: str
    anchor_example_id: str | None
    situation: str
    subject: str
    brief: str
    refused: bool
    refusal_reason: str | None


def _example_payload(example: dict, anchor_id: str | None) -> dict[str, Any]:
    return {
        "id": example.get("id"),
        "text": example.get("text"),
        "translation": example.get("translation"),
        "origin": example.get("origin"),
        "isAnchor": example.get("id") == anchor_id,
    }


def build_request(article: ArticleView, styles: StyleTable, weights: dict[str, float] | None = None,
                  boost_variety: bool = True) -> dict[str, Any]:
    """Everything the writer sees about one word, and every style it may choose from.

    `boost_variety` presents each style with a few of its example subjects, sampled per word, which
    pushes the writer toward styles it would otherwise pass over. Switched off, a style is offered
    on its own description alone. Both modes were reviewed and both produce good pictures, so this
    is a matter of taste rather than of correctness — which is exactly why it is a setting.
    """
    lexeme = article.lexeme
    vocabulary = article.vocabulary or {}
    senses = []
    for sense in article.senses:
        anchor = anchor_for(sense)
        senses.append(
            {
                "senseId": sense.id,
                # Named so the writer can see that the definition is in the language being learned
                # and the glosses are not: the definition rules, the glosses are hints.
                "definition": sense.definition,
                "definitionLang": sense.definition_lang,
                "domain": sense.domain,
                "glosses": sense.glosses,
                "examples": [_example_payload(example, anchor.get("id") if anchor else None)
                             for example in sense.examples],
            }
        )
    return {
        "headword": lexeme.get("headword"),
        "lemma": lexeme.get("lemma"),
        "language": lexeme.get("language"),
        "pos": lexeme.get("pos"),
        "register": lexeme.get("register"),
        "dialect": lexeme.get("dialect"),
        "shortGloss": lexeme.get("shortGloss"),
        "notes": lexeme.get("notes") or [],
        "glossLangs": vocabulary.get("glossLangs") or [],
        "senses": senses,
        "styles": [
            {"styleId": style.id, "label": style.label, "mono": style.mono,
             "suits": list(styles.hints(style, article.id)) if boost_variety else []}
            for style in styles.offer(weights, rotate=article.id)
        ],
    }


def parse_reply(payload: Any, article: ArticleView, offered: tuple[str, ...]) -> list[SenseBrief]:
    """Treat the reply as untrusted: an unknown style or sense id is an error, not a nudge.

    Takes the already-parsed document — unfencing and `json.loads` belong to `models.call`, which
    does them for every kind of reply. What is left here is the part a JSON schema cannot express:
    every check below is against *this article's* sense ids and the styles *this call* offered.
    """
    if payload is None:
        raise ValueError("The brief writer did not return JSON.")
    if not isinstance(payload, dict):
        raise ValueError("The brief writer did not return an object.")

    entries = payload.get("senses")
    if not isinstance(entries, list):
        raise ValueError("The brief writer returned no `senses` list.")

    by_sense = {sense.id: sense for sense in article.senses}
    known = set(by_sense)
    out: list[SenseBrief] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("A sense entry was not an object.")
        sense_id = str(entry.get("senseId", ""))
        if sense_id not in known:
            raise ValueError(f"The brief writer named an unknown sense {sense_id!r}.")
        refused = bool(entry.get("refused"))
        if refused:
            out.append(SenseBrief(sense_id, "", None, "", "", "", True,
                                  str(entry.get("refusalReason") or "unstated")))
            continue
        style_id = str(entry.get("styleId", ""))
        if style_id not in offered:  # an invented style names nothing, so it cannot be reproduced
            raise ValueError(
                f"The brief writer chose {style_id!r} for sense {sense_id}, which is not a style."
            )
        brief = str(entry.get("brief") or "").strip()
        if not brief:
            raise ValueError(f"The brief writer returned an empty brief for sense {sense_id}.")
        anchor = str(entry.get("anchorExampleId") or "")
        if anchor not in {example.get("id") for example in by_sense[sense_id].examples}:
            anchor = ""      # an id from another sense, or invented: it names nothing here
        out.append(SenseBrief(sense_id, style_id, anchor or None,
                              str(entry.get("situation") or "").strip(),
                              str(entry.get("subject") or "").strip(), brief, False, None))

    missing = known - {item.sense_id for item in out}
    if missing:
        raise ValueError(f"The brief writer skipped {len(missing)} sense(s).")
    return out


class BriefWriter:
    """One text call per lexeme, through the owner's chain rather than through a Vertex client.

    It is given resolved candidates rather than a chain to resolve: resolving once, at startup, is
    what makes a mistyped provider or a retired model refuse before any money is spent, instead of
    at the first word of a sweep.
    """

    def __init__(self, catalogue: Providers, candidates: Sequence[chain.Candidate],
                 template: str, styles: StyleTable,
                 weights: dict[str, float] | None = None, boost_variety: bool = True) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        # The prompt's text, not its file: the server appends the owner's rules to it first.
        self.template = template
        self.styles = styles
        self.weights = weights
        self.boost_variety = boost_variety

    def write(self, article: ArticleView) -> tuple[list[SenseBrief], dict[str, Any]]:
        """Write the briefs: one walk of the chain, and one more only for a malformed answer.

        **Whether to wait out a quota is not decided here.** The chain handles one provider being
        rate limited by moving to the next; a chain that is entirely over quota is the caller's
        condition to wait out — the server's job runner (`acervo/work/`) and the laptop image run
        each do that in the one place they decide retries. A ladder here was a second layer that
        neither of them knew about.

        A chain that failed because no model would hold the shape is re-sampled **once,
        immediately** — a second sample is worth one try and no more — and then reported.
        """
        for attempt in range(1, SHAPE_TRIES + 1):
            try:
                return self._write_once(article)
            except ChainExhausted as exhausted:
                if attempt == SHAPE_TRIES or not exhausted.waited_on_nothing:
                    raise
        raise AssertionError("unreachable")

    def _write_once(self, article: ArticleView) -> tuple[list[SenseBrief], dict[str, Any]]:
        request = build_request(article, self.styles, self.weights, self.boost_variety)
        offered = tuple(style["styleId"] for style in request["styles"])
        prompt = f"{self.template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"
        def ask(candidate: chain.Candidate) -> TextResult:
            answered = call.text(
                prompt, row=candidate.row, model=candidate.model, as_json=True,
                timeout=call.SHORT_TIMEOUT_SECONDS,
            )
            # Judged here, inside the chain's own callback, so a model that cannot hold the shape
            # is passed over rather than ending the run. Every check in `parse_reply` is about
            # whether *this* model followed instructions — an invented style, a skipped sense, an
            # empty brief — which is a fact about the model and exactly what the next row is for.
            # Parsed twice on the happy path, which is microseconds against a model call.
            try:
                parse_reply(answered.parsed, article, offered)
            except ValueError as unusable:
                # The reply travels with the complaint. "Unusable" on its own sent a real debugging
                # session into the code to guess; `it returned only senseId` ends it in one line.
                # Safe to carry because `ProviderError` redacts its detail at construction.
                raise ProviderUnavailable(
                    "unusable", f"{unusable} — got {journal.excerpt(answered.text)}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return answered

        result: TextResult = chain.walk(
            "text",
            [candidate.named for candidate in self.candidates],
            self.catalogue,
            ask,
            chain.stamped,
            caller="brief",
        )
        briefs = parse_reply(result.parsed, article, offered)
        answer = result.answer
        return briefs, {
            "provider": answer.provider_id,
            # The model that *answered*, not the one asked first. A fall-through that left this
            # naming the head of the chain would be a lie in every record it stamped.
            "model": answer.model,
            "seconds": round(answer.seconds, 2),
            "costUsd": answer.cost_usd,
            "attempts": [list(pair) for pair in answer.attempts],
            "passedOver": [list(item) for item in answer.passed_over],
            "warnings": list(answer.warnings),
            "stylesOffered": len(offered),
        }
