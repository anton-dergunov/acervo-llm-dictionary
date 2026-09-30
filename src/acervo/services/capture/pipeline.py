"""One capture, proposed: resolve, the vocabulary checks, the duplicate check, compose, the draft.

Shared by the interactive route, which returns the proposal for review, and the headless capture
job, which saves it to the Inbox. Nothing here writes.

It is two halves, split at the duplicate check: `understand` and then compose. A tapped word — on a
photo, or in something being read — asks for the first half alone (`look_up`) and brings its answer back to `/capture`, so the quick call is not a
second pipeline and compose does not pay for resolve twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acervo.domain.validation import POS_VALUES
from acervo.errors import ApiError
from acervo.models import Answer
from acervo.repository import graph
from acervo.services.capture.coerce import language_or_none, pick_choice, reference_of, trimmed
from acervo.services.capture.compose import compose
from acervo.services.capture.draft import draft_from
from acervo.services.capture.resolve import resolve
from acervo.settings import Settings

TEXT_LIMIT = 20000
SEPARATORS = {"", "---", "***", "___"}


def leading_blanks(lines: list[str]) -> int:
    """Blank lines and rules at the front of a window, skipped without a model call."""
    count = 0
    while count < len(lines) and lines[count].strip() in SEPARATORS:
        count += 1
    return count


def logical_block(lines: list[str]) -> int:
    """How far to skip when the front of a window could not be read as a word at all.

    Blocks in notes files are separated by a blank line or a rule often enough that this keeps a walk
    moving past junk without spending a call on every single line.
    """
    for index, line in enumerate(lines):
        if index and line.strip() in SEPARATORS:
            while index < len(lines) and lines[index].strip() in SEPARATORS:
                index += 1
            return index
    return len(lines)


def _passed_over(*calls: Answer) -> list[dict[str, str]]:
    """Which providers were asked before the one that answered, and why they were not it.

    A fall-through is otherwise completely silent. The entry names the model that wrote it, but a
    provider at the head of the owner's order that is quietly broken looks exactly like one they
    never chose — and they would go on believing it is the one building their words.

    Deduplicated across the two model calls: a provider that refused both is one thing that is
    wrong, not two.
    """
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for call in calls:
        for provider, model, reason in call.passed_over:
            seen.setdefault((provider, model), {"provider": provider, "model": model, "reason": reason})
    return list(seen.values())


def _foldable(resolution: dict[str, Any], body: dict[str, Any]) -> dict[str, Any] | None:
    """What this capture carried that the entry already held may not have.

    `resolution["sentences"]` is the learner's own text, corrected — a dictionary's examples never
    reach it (`coerce.reference_of`), which is exactly what makes folding it in safe: everything
    here can legitimately become an attestation on the stored word.

    None when the capture was just the word again, which is the common case and not worth offering.
    """
    sentences = resolution["sentences"]
    note = trimmed(body.get("note")) or None
    reference = reference_of(body)
    if not sentences and not note and reference is None:
        return None
    return {"sentences": sentences, "reference": reference is not None, "note": note}


@dataclass(frozen=True)
class Understanding:
    """The first half of a capture: what the text is about, and whether the owner already has it."""

    resolution: dict[str, Any]
    vocabulary: dict[str, Any]
    duplicates: list[dict[str, Any]]
    calls: tuple[Answer, ...]


def understand(
    settings: Settings, account: str, body: dict[str, Any], *, quick: bool = False
) -> Understanding:
    """Resolve, the vocabulary checks and the duplicate check — everything before compose.

    The order is contract: the vocabulary checks come before generation, so an unkept language never
    spends a model call; the duplicate check comes after resolve and before compose, so a repeat
    capture costs one call rather than two.

    A resolution the body already carries — from a quick look-up a moment ago — is held to the same
    checks as one resolve just returned, and resolve is not asked again (`given_resolution`).
    """
    vocabularies = graph.owner_vocabularies(account)
    given = None if quick else given_resolution(body)
    if given is not None:
        resolution, calls = given, ()
    else:
        resolution, resolving = resolve(settings, account, body, vocabularies, quick=quick)
        calls = (resolving,)

    vocabulary = next(
        (entry for entry in vocabularies if entry["language"] == resolution["language"]), None
    )
    if vocabulary is None:
        # Deliberately before generation: building an article for a language the owner does not keep
        # would spend a model call on something with nowhere to go.
        raise ApiError(
            409,
            "language_not_configured",
            f"This looks like {resolution['language']}, which you have no vocabulary for yet. "
            "Add it in Settings, then capture this again.",
        )
    if not vocabulary["glossLangs"]:
        raise ApiError(
            409,
            "language_not_configured",
            f"Your {resolution['language']} vocabulary has no translation language set, so an entry "
            "cannot be built. Choose one in Settings.",
        )

    duplicates = graph.duplicate_lexemes(
        account, resolution["language"], resolution["headword"], resolution["lemma"]
    )
    return Understanding(resolution, vocabulary, duplicates, calls)


def given_resolution(body: dict[str, Any]) -> dict[str, Any] | None:
    """The resolution a quick look-up returned, checked rather than trusted, or None.

    It came back from this server a moment ago, but it travelled through a device, so every field is
    read the way resolve reads a model's answer — and a sentence the body's text does not contain is
    refused, because it would become an attestation: a claim that the learner met the word there.
    """
    raw = body.get("resolution")
    if raw is None:
        return None
    refused = ApiError(400, "invalid_input", "That look-up no longer matches the text. Tap the word again.")
    if not isinstance(raw, dict):
        raise refused
    language = language_or_none(raw.get("language"))
    headword = trimmed(raw.get("headword"))[:240]
    if not language or not headword:
        raise refused
    text = " ".join(str(body.get("text") or "").split())
    sentences = []
    for item in raw.get("sentences") or []:
        sentence = trimmed(item.get("text")) if isinstance(item, dict) else ""
        if not sentence:
            continue
        if " ".join(sentence.split()) not in text:
            raise refused
        sentences.append({
            "text": sentence[:5000],
            "translation": (trimmed(item.get("translation")) or None) if isinstance(item, dict) else None,
        })
    return {
        "language": language,
        "headword": headword,
        "lemma": trimmed(raw.get("lemma"))[:240] or headword,
        "pos": pick_choice(raw.get("pos"), POS_VALUES, "noun"),
        "sentences": sentences,
        "note": trimmed(raw.get("note"))[:500] or None,
        "consumedLines": len(str(body.get("text") or "").split("\n")),
        "consumedText": None,
    }


def look_up(settings: Settings, account: str, body: dict[str, Any]) -> dict[str, Any]:
    """The quick look-up a tapped word makes: the first half of a capture, on the `quick` chain.

    One model call. It returns what the interface needs while the finger is still down — which word
    was meant and what it means here — and whether the owner already holds it, with the same
    `duplicates` and `foldable` `/capture` returns, so a word already held goes straight to folding
    this sentence in. Writes nothing.
    """
    understood = understand(settings, account, body, quick=True)
    return {
        "resolution": understood.resolution,
        "duplicates": understood.duplicates,
        "foldable": _foldable(understood.resolution, body) if understood.duplicates else None,
        "passedOver": _passed_over(*understood.calls),
    }


def propose(settings: Settings, account: str, body: dict[str, Any]) -> dict[str, Any]:
    """Resolve and compose one entry from `body`, and write nothing.

    What a person reviews in the Add view, and what the headless capture job saves. No transaction is
    held across either model call.
    """
    understood = understand(settings, account, body)
    resolution = understood.resolution
    if understood.duplicates:
        # A repeat capture is an addition, not an entry (`docs/features/capture.md`). Merging it
        # into the word it belongs to is the article conversation's job, and this branch already
        # knows everything that job needs: resolve has run, so the learner's own sentences are in
        # hand, separated from anything a dictionary supplied. No second model call, and no merge
        # path here — the interface opens the stored article and asks one ordinary question.
        return {
            "resolution": resolution, "duplicates": understood.duplicates, "draft": None,
            "passedOver": _passed_over(*understood.calls),
            "foldable": _foldable(resolution, body),
        }

    topics = graph.owner_topics(account)
    # The model that answered, not the one that was asked first: with a chain, those differ the
    # moment a provider is rate limited, and the entry must record the one that did the work.
    answer, composing = compose(settings, account, resolution, body, understood.vocabulary, topics)
    draft = draft_from(answer, resolution, body, understood.vocabulary, topics, composing.model)

    return {
        "resolution": resolution, "duplicates": [], "draft": draft,
        "passedOver": _passed_over(*understood.calls, composing),
        # Total rather than conditional: a field that is sometimes absent is a field every reader
        # has to guess about.
        "foldable": None,
    }
