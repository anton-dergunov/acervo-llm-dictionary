"""The one model call: which recorded utterance, if any, is a good example of which sense.

One call per *lexeme*, covering all of its senses against one bounded candidate set. The model is
the last and best quality gate, not the retrieval mechanism (`docs/features/spoken-clips.md` §2.7):
the corpus does IR over millions of segments because it must, and Acervo spends one frontier call
per word on the judgement a feature cannot make — reading a messy fragment and deciding whether it
is really an instance of *this* sense.

Three things follow, and all three are the point.

**Refusing is the default, not the failure.** A thin corpus must produce articles with no clips,
never articles with bad clips. A sense with no selection is a successful outcome and is not counted
as anything.

**The stored text is the corpus's sentence, verbatim.** The model chooses; it never rewrites, trims
or joins (§2.6). Where a passage starts and ends is an open research question in the other
repository, and a model that quietly re-cut it would make those measurements meaningless and break
the audit that `clipRef` exists for.

**An id the request did not offer is dropped and counted, never a refusal of the whole word.** This
is the deliberate difference from `images/brief.parse_reply`, which raises: a hallucinated id is a
prompt bug to fix, and refusing the batch would throw away the good selections with it.

This package stands alone. It imports `acervo.models`, `acervo.article` and its own corpus client,
and nothing else of Acervo's — so the request path and the batch sweep are two callers of one
pipeline rather than two pipelines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from acervo.article import ArticleView
from acervo.models import ChainExhausted, TextResult, call, chain, journal
from acervo.models.catalogue import Catalogue
from acervo.models.errors import SHAPE_TRIES, ProviderUnavailable

from .corpus import Candidate

# What the selector must return is stated in `prompts/acervo_clip_select.md`, with a worked example
# naming every field, including the `segmentId: null` that is how a sense declines. No JSON Schema
# is sent — this was the caller that measured the cost of sending one (AGENTS.md, "Constrained
# decoding is not used"): constrained, its translations came back at 266 to 1039 characters with
# three calls in four timing out; unconstrained, 61 characters every time, which is what a faithful
# translation of those sentences weighs.
#
# `parse_reply` is the contract that is enforced, and it checks what a schema could not: *this*
# article's sense ids, the segments *this* call offered, and that a translation is a translation
# rather than the model's own drafting.


@dataclass(frozen=True)
class Selection:
    """One sense's clip, and the article line that goes under it.

    The translation comes from this same call (spoken-clips §2.13), in `glossLangs[0]`, exactly as
    `acervo_compose.md` produces one beside every generated example. No second call and no second
    provider configuration: the retrieval service can translate too, but what *it* produces is the
    player's interactive alignment, which Acervo stores none of.
    """

    sense_id: str
    candidate: Candidate
    translation: str | None
    matched_translation_form: str | None


def _example_payload(example: dict) -> dict[str, Any]:
    return {
        "text": example.get("text"),
        "translation": example.get("translation"),
        "origin": example.get("origin"),
    }


def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
    """What the model is told about one segment.

    Every field here is prompt weight, so every one has to earn its place —
    `docs/plans/quality/clip-selection.md` names this set as the first thing to vary. The
    provenance fields are here because a learner judging *naturalness* would want them: an
    automatic caption of streamed Rioplatense conversation is a different kind of evidence from an
    authored subtitle on a scripted lesson.
    """
    return {
        "segmentId": candidate.segment_id,
        "sentence": candidate.sentence,
        "matchedForm": candidate.matched_surface,
        "channel": candidate.channel,
        "speechStyle": list(candidate.speech_style),
        "variety": list(candidate.varieties),
        "captionKind": candidate.caption_kind,
        "boundary": candidate.boundary_reason,
    }


def build_request(article: ArticleView, candidates: Sequence[Candidate],
                  gloss_lang: str) -> dict[str, Any]:
    """Everything the selector sees: one word, its senses, and the segments retrieved for it.

    The senses are described the way `prompts/acervo_image_brief.md` describes them, and for the
    reason that prompt learned the hard way — the definition in the language being learned is the
    authority and the glosses are hints that can mislead. Judging a fragment against an English
    gloss finds instances of the English word instead of the Spanish one.
    """
    lexeme = article.lexeme
    return {
        "headword": article.headword,
        "lemma": article.lemma,
        "language": article.language,
        "pos": lexeme.get("pos"),
        "register": lexeme.get("register"),
        "shortGloss": lexeme.get("shortGloss"),
        # The language the article's own translation line must be written in.
        "translationLang": gloss_lang,
        "senses": [
            {
                "senseId": sense.id,
                # Named so the model can see that the definition is in the language being learned
                # and the glosses are not: the definition rules, the glosses are hints.
                "definition": sense.definition,
                "definitionLang": sense.definition_lang,
                "domain": sense.domain,
                "glosses": sense.glosses,
                "examples": [_example_payload(example) for example in sense.examples],
            }
            for sense in article.senses
        ],
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
    }


def candidate_text(by_segment: dict[str, Candidate], segment_id: str) -> str:
    """The sentence a translation is meant to be of, for measuring it against."""
    candidate = by_segment.get(segment_id)
    return candidate.sentence if candidate else ""


def parse_reply(payload: Any, article: ArticleView,
                offered: Sequence[Candidate]) -> tuple[list[Selection], int]:
    """The selections, and how many the reply named that the request never offered.

    The count is surfaced rather than swallowed: an invented id is a prompt bug, and one that is
    dropped silently is a prompt bug nobody finds.
    """
    if not isinstance(payload, dict):
        raise ValueError("The clip selector did not return an object.")
    entries = payload.get("senses")
    if not isinstance(entries, list):
        raise ValueError("The clip selector returned no `senses` list.")
    # **Refusing is an answer; saying nothing is not, and the two must not look alike.** A reply of
    # `segmentId: null` for every sense is the expected outcome for most words and passes straight
    # through below. An *empty list* is not that: it answers nothing at all, and because the caller
    # stamps `clipsSearchedAt` on a clean return and §2.12 ships no rescan, letting it through marks
    # the word consulted-and-empty for good. Deliberately only the empty case — an id this article
    # does not have stays dropped-and-counted, never a refusal of the whole word.
    if article.senses and not entries:
        raise ValueError("The clip selector returned no senses at all.")

    by_segment = {candidate.segment_id: candidate for candidate in offered}
    known = {sense.id for sense in article.senses}
    taken: set[str] = set()
    out: list[Selection] = []
    dropped = 0

    for entry in entries:
        if not isinstance(entry, dict):
            dropped += 1
            continue
        sense_id = str(entry.get("senseId") or "")
        segment_id = str(entry.get("segmentId") or "")
        if not segment_id:
            continue        # a refusal, which is the expected outcome for most words
        if sense_id not in known or sense_id in taken or segment_id not in by_segment:
            dropped += 1
            continue
        taken.add(sense_id)
        candidate = by_segment[segment_id]
        translation = str(entry.get("translation") or "").strip() or None
        # **What a translation of this passage cannot be.** Both checks are failures seen from a real
        # model rather than hazards imagined: one run of a sentence into the next field —
        # "…something to eat., segmentId: seg_4270b0…" — and one failure to stop, rambling past the
        # end of the sentence into filler. Either one stored reaches the article as prose with
        # rubbish in it, and because the clip search is one-shot at save nothing would ever replace
        # it.
        #
        # Raised rather than dropped, unlike a hallucinated id: a model that runs fields together or
        # cannot end a string does it to every entry it writes, which is a fact about the model and
        # exactly what the pair behind it is for. The length bound is generous on purpose — a
        # faithful translation runs to roughly the length of its source, so three times it is not a
        # long translation, it is a model that did not stop.
        if translation and (segment_id in translation or "segmentId" in translation):
            raise ValueError(
                f"The clip selector wrote the segment id into the translation for sense {sense_id}."
            )
        if translation and len(translation) > max(240, 3 * len(candidate_text(by_segment, segment_id))):
            raise ValueError(
                f"The clip selector did not stop writing the translation for sense {sense_id}."
            )
        # **A copy of the passage is not a translation of it**, and this one was not imagined
        # either: asked for English, a model returned the Spanish passage back, verbatim, for every
        # sense it picked. It passes every other check here — it is complete, it stops, it carries
        # no segment id — and it reaches the article as a translation line identical to the sentence
        # above it, which is the one reader who cannot tell. The player then aligns the passage
        # against itself.
        #
        # Exact rather than approximate, so it needs no threshold and no per-language table, and it
        # is the whole of what can be checked without ground truth: that a translation is *missing
        # part* of its passage is the open question in
        # `docs/plans/quality/translation-completeness-check.md`; that it is *not a translation at all* is
        # decidable here and now. Guarded on the two languages actually differing, because asking
        # for a translation into the passage's own language is a different mistake made somewhere
        # else, and on a length that a proper noun standing alone cannot reach.
        source = candidate_text(by_segment, segment_id).strip()
        target = (article.gloss_langs or [""])[0]
        if (translation and translation == source and len(source) >= 25
                and target and target != article.language):
            raise ValueError(
                f"The clip selector copied the passage instead of translating it for sense {sense_id}."
            )
        matched = str(entry.get("matchedTranslationForm") or "").strip() or None
        # The invariant is verbatim, untrimmed and un-normalised. A form that does not hold loses
        # the form rather than being stored as a lie — the rule the capture path already follows.
        if matched and not (translation and matched in translation):
            matched = None
        out.append(Selection(sense_id, candidate, translation, matched))

    return out, dropped


class ClipSelector:
    """One text call per lexeme, through the owner's chain.

    Given resolved candidates and the prompt *text* rather than a chain to resolve and a path to
    read: this package may not read `Settings`, and resolving once is what makes a mistyped provider
    refuse before any money is spent instead of at the first word of a sweep.
    """

    def __init__(self, catalogue: Catalogue, candidates: Sequence[chain.Candidate],
                 template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def select(self, article: ArticleView, candidates: Sequence[Candidate],
               gloss_lang: str) -> tuple[list[Selection], int, dict[str, Any]]:
        """One walk of the chain, and one more only for a malformed answer.

        A chain entirely over quota is raised for the caller to wait out, as in `BriefWriter.write`:
        retrying is the job runner's decision, made in one place.
        """
        for attempt in range(1, SHAPE_TRIES + 1):
            try:
                return self._select_once(article, candidates, gloss_lang)
            except ChainExhausted as exhausted:
                if attempt == SHAPE_TRIES or not exhausted.waited_on_nothing:
                    raise
        raise AssertionError("unreachable")

    def _select_once(self, article: ArticleView, candidates: Sequence[Candidate],
                     gloss_lang: str) -> tuple[list[Selection], int, dict[str, Any]]:
        request = build_request(article, candidates, gloss_lang)
        prompt = f"{self.template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"

        def ask(candidate: chain.Candidate) -> TextResult:
            answered = call.text(
                prompt, row=candidate.row, model=candidate.model, as_json=True,
                timeout=call.SHORT_TIMEOUT_SECONDS,
            )
            # Judged inside the chain's callback, exactly as `images/brief.py` judges its own, so a
            # model that cannot hold the shape is passed over instead of having its answer accepted.
            # This one matters more than the brief's: an unusable reply here is indistinguishable
            # from an honest refusal, and the caller stamps `clipsSearchedAt` on a clean return with
            # nothing ever re-searching. Parsed twice on the happy path, which is microseconds
            # against a model call.
            try:
                parse_reply(answered.parsed, article, candidates)
            except ValueError as unusable:
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
            caller="clips",
        )
        selections, dropped = parse_reply(result.parsed, article, candidates)
        answer = result.answer
        return selections, dropped, {
            "provider": answer.provider_id,
            # The model that *answered*, not the one asked first. A fall-through that left this
            # naming the head of the chain would be a lie in every record it stamped.
            "model": answer.model,
            "seconds": round(answer.seconds, 2),
            "costUsd": answer.cost_usd,
            "candidatesOffered": len(candidates),
        }
