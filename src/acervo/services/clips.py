"""Acervo's binding to the clip pipeline: the graph and the corpus in, clip examples out.

The other half of the split `acervo.clips` makes, and the same split `services/images.py` makes
against `acervo.images`. `acervo.clips` knows what a good clip is; this module knows whose word it
is, where the corpus answers, which chain judges and what Acervo's API calls a failure — and it
speaks the same `llm_*` codes, through the same `services.models.refusal`, because a clip that could
not be chosen and an entry that could not be written should fail alike.

Every operation is read (transaction) → search (**no** transaction) → model call (**no**
transaction) → write (transaction). A repository function is a transaction and owns its own session;
a model call of up to two minutes inside one would block every other request for as long as it ran.

Nothing here is a second write path. Rows go through `repository.graph.merge_graph`, the same route
a phone's writes take, with the same validation and the same revision allocation.
"""

from __future__ import annotations

from typing import Any

from acervo import trace
from acervo.article import ArticleView, article_for
from acervo.clips.corpus import Candidate, Corpus, CorpusError
from acervo.clips.ids import clip_example_id
from acervo.clips.select import ClipSelector, Selection
from acervo.domain.ids import now_instant
from acervo.errors import ApiError
from acervo.models import ChainExhausted, ProviderError, chain, load_catalogue
from acervo.repository import clip_settings, graph
from acervo.services.models import chain_for, refusal
from acervo.services.prompts import prompt_text
from acervo.services.rules import with_rules
from acervo.settings import Settings

# What a chosen clip is written as: an ordinary example whose origin says it was spoken.
CLIP_ORIGIN = "subtitle"

# One attempt, as in `services/images.py`: retrying is the job runner's decision.

# `searchEnabled` is checked by the thing that searches *on its own* — the `enrich` job — and
# deliberately not by the route below. A route searches what it
# is asked, because every caller of it other than those two is a person pressing a button.

CORPUS_REFUSALS: dict[str, tuple[int, str, str]] = {
    "unreachable": (502, "corpus_unreachable", "The spoken-usage corpus could not be reached, so nothing was added."),
    "unavailable": (503, "corpus_unavailable", "The spoken-usage corpus is temporarily unavailable, so nothing was added."),
    "refused": (502, "corpus_failed", "The spoken-usage corpus refused the request, so nothing was added."),
}


def _corpus(settings: Settings) -> Corpus:
    if not settings.speech_url:
        raise ApiError(
            503, "corpus_unconfigured",
            "This Acervo server has no spoken-usage corpus configured, so it cannot find clips.",
        )
    return Corpus(settings.speech_url, request_id=trace.current())


def _corpus_refusal(error: CorpusError) -> ApiError:
    status, code, message = CORPUS_REFUSALS[error.reason]
    return ApiError(status, code, message)


def _candidates(settings: Settings, owner: str) -> tuple[chain.Candidate, ...]:
    """The owner's text chain, resolved against this server's credentials.

    Resolved per call rather than cached, for `chain_for`'s reason: it is one indexed read against a
    local SQLite file set against a model call of up to two minutes, and caching it would mean a
    change in Settings ▸ Models took effect at some unpredictable later time.
    """
    try:
        resolved = chain.resolve("text", chain_for(settings, owner, "text"), load_catalogue())
    except ProviderError as error:
        raise refusal(error) from None
    if not resolved:
        raise refusal(chain.unconfigured("text", chain_for(settings, owner, "text"), load_catalogue()))
    return resolved


# ── settings ────────────────────────────────────────────────────────────────


def settings_view(settings: Settings, owner: str) -> dict[str, Any]:
    """What the owner chose, and whether this deployment could find a clip at all.

    The corpus reading travels with the settings rather than through a route of its own, exactly as
    the style table travels with Settings ▸ Pictures: the switch is meaningless without knowing
    whether anything is indexed, and one round trip cannot show a half-loaded screen.
    """
    chosen = clip_settings.settings(owner)
    corpus: dict[str, Any] = {"configured": bool(settings.speech_url), "reachable": False}
    if settings.speech_url:
        try:
            corpus = {"configured": True, "reachable": True, **Corpus(settings.speech_url, request_id=trace.current()).status()}
        except CorpusError as error:
            # A corpus that is down is a fact to show, not an error to raise: Settings must open and
            # say so, the way it does for a dictionary source that cannot be reached.
            corpus["error"] = error.reason
    return {**chosen, "corpus": corpus}


def apply_settings(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for field, column in (("searchEnabled", "search_enabled"),
                          ("selfContainedOnly", "self_contained_only")):
        if field in body:
            value = body[field]
            if not isinstance(value, bool):
                raise ApiError(400, "invalid_input", f"{field} must be true or false.")
            changes[column] = value
    clip_settings.save(owner, **changes)
    return settings_view(settings, owner)


# ── the one call ────────────────────────────────────────────────────────────


def find_clips(settings: Settings, owner: str, device: str, lexeme_id: str) -> dict[str, Any]:
    """One corpus search and one model call for one word, and the rows they produce.

    The order is deliberately the opposite of capture's (§2.5): the article is written first from
    the definition and the owner's own attestations, and only then does anything go looking for real
    speech that matches the senses it already has. Feeding caption fragments to the first call would
    condition the whole entry on the messiest input in the system, and the failure mode is invisible
    — a slightly worse definition, in every word, forever.
    """
    chosen = clip_settings.settings(owner)
    resolved = _candidates(settings, owner)
    records = graph.article_records(owner, lexeme_id)
    article = article_for(records, lexeme_id)
    if article is None:
        # One message for "no such word", "somebody else's word" and "a word you put away": telling
        # them apart would answer whether an id exists in another account.
        raise ApiError(404, "not_found", "That word is not in your vocabulary.")
    if not article.senses:
        raise ApiError(400, "no_senses", "A word with no senses has nothing to illustrate.")

    corpus = _corpus(settings)
    try:
        indexed = corpus.status()["indexedLanguages"]
    except CorpusError as error:
        raise _corpus_refusal(error) from None

    if article.language not in indexed:
        # Not a failure, and deliberately **not** marked as searched: the corpus may index this
        # language later, and no rescan ships (§2.12), so marking it would bury the word forever.
        return _answer(article, [], 0, None, searched=False, skipped="language_not_indexed")

    try:
        # The lemma, because that is the form a corpus is keyed on, exactly as a dictionary is.
        candidates = corpus.search(article.language, article.lemma)
    except CorpusError as error:
        if error.reason != "rejected":
            raise _corpus_refusal(error) from None
        # A 400 is the corpus answering: this query is one it will never accept — over five tokens,
        # or a language it does not know. That word's query will not get shorter, so it counts as
        # consulted and is *marked*, or the sweep spends a search on the same refusal forever.
        return _write(owner, device, article, records, [], 0, None, skipped="query_rejected")

    if not candidates:
        return _write(owner, device, article, records, [], 0, None)

    # The name inlined rather than held in a constant: `test_server_bundle_contents.py` scrapes
    # this exact call shape to prove the prompt ships in the release image, and a constant escapes it.
    template = prompt_text(
        settings.prompts_path, "acervo_clip_select",
        {"selfContainedOnly": chosen.self_contained_only},
    )
    selector = ClipSelector(load_catalogue(), resolved, with_rules(template, owner))
    gloss_lang = (article.gloss_langs or ["en"])[0]
    try:
        # Nothing is stamped on any path that raises, so a word refused here stays unconsulted and
        # a later job will find it again — which is exactly what must happen when no model answered.
        selections, dropped, usage = selector.select(article, candidates, gloss_lang)
    except ChainExhausted as exhausted:
        raise refusal(exhausted) from None
    except ProviderError as error:
        raise refusal(error) from None
    except ValueError as unusable:
        raise ApiError(
            502, "llm_unusable", "The language model did not return a usable clip selection."
        ) from unusable

    return _write(owner, device, article, records, selections, dropped, usage, gloss_lang)


def _write(owner: str, device: str, article: ArticleView, records: dict[str, list[dict]],
           selections: list[Selection], dropped: int, usage: dict[str, Any] | None,
           gloss_lang: str = "en", *, skipped: str | None = None) -> dict[str, Any]:
    """One transaction: the chosen examples and the mark saying this word has been consulted."""
    at = now_instant()
    # From the raw records rather than from the view, and the difference is a real bug rather than a
    # nicety: `build_articles` filters tombstones, which is right for the pipeline and wrong here. A
    # tombstoned row still holds its id and its revision, and a clip's id is *derived* — so writing
    # revision zero over it is refused as stale and that pair could never be written again.
    held = {row["id"]: row for row in records.get("examples", [])}
    examples = [
        _clip_row(selection, held, article, at, device, usage, gloss_lang)
        for selection in selections
    ]
    lexeme = {**article.lexeme, "clipsSearchedAt": at, "editedAt": at, "editedBy": device}

    changes: dict[str, list[dict]] = {"lexemes": [lexeme]}
    if examples:
        changes["examples"] = examples
    graph.merge_graph(owner, device, changes, enqueue=None)
    return _answer(article, examples, dropped, usage, searched=True, skipped=skipped)


def _clip_row(selection: Selection, held: dict[str, dict], article: ArticleView, at: str,
              device: str, usage: dict[str, Any] | None, gloss_lang: str) -> dict[str, Any]:
    candidate: Candidate = selection.candidate
    example_id = clip_example_id(selection.sense_id, candidate.segment_id)
    existing = held.get(example_id)
    # The sentence is the corpus's, verbatim. The matched form is re-checked rather than trusted
    # across a service boundary, and a form that is not in the text loses the form rather than being
    # stored as a lie.
    matched = candidate.matched_surface
    if matched and matched not in candidate.sentence:
        matched = ""
    return {
        "id": example_id,
        "senseId": selection.sense_id,
        "text": candidate.sentence,
        "textLang": article.language,
        "translation": selection.translation,
        "translationLang": gloss_lang if selection.translation else None,
        "origin": CLIP_ORIGIN,
        "sourceAttestationId": None,
        "modelId": (usage or {}).get("model"),
        "videoRef": candidate.video_url,
        "videoTitle": candidate.video_title,
        "videoChannel": candidate.channel,
        "videoStart": candidate.start_second,
        "videoEnd": candidate.end_second,
        "clipRef": candidate.segment_id,
        "imageRef": None,
        # A recorded speaker already sounds however they sounded; there is nothing to direct.
        "emotion": None,
        "note": None,
        "matchedForm": matched or None,
        "matchedTranslationForm": selection.matched_translation_form,
        # A tombstoned row is revived rather than left dead: the id is derived from the pair, so
        # there is no other row this clip could ever occupy.
        "deleted": False,
        "createdAt": (existing or {}).get("createdAt", at),
        "editedAt": at,
        "editedBy": device,
        "revision": (existing or {}).get("revision", 0),
    }


def _answer(article: ArticleView, examples: list[dict], dropped: int, usage: dict[str, Any] | None,
            *, searched: bool, skipped: str | None = None) -> dict[str, Any]:
    return {
        "lexemeId": article.id,
        "searched": searched,
        "skipped": skipped,
        "examples": examples,
        # Surfaced rather than swallowed: an id the request never offered is a prompt bug, and one
        # dropped silently is a prompt bug nobody finds.
        "dropped": dropped,
        "usage": usage,
    }
