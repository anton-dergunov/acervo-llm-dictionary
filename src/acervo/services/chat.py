"""One turn of conversation about one word.

The device assembles what is discussed and sends it; this layer holds the credentials, owns the
prompt, and writes nothing. That split is deliberate (`docs/features/article-chat.md` §4):
`web/src/yaml.ts` is the only place the article projection is understood, so a server-side
serialiser would be a second implementation of it, drifting from the first the moment a field is
added. The document that arrives came from that owner's own replica and goes nowhere but into their
own prompt.

Two subject kinds, two prompts, and they differ in exactly two places: which file is read, and which
of `proposal` / `capture` survives. An article subject may be proposed against; a dictionary entry
may not, because there is nothing editable on screen.

Everything the model returns is untrusted. The rule from `capture/coerce.py` applies unchanged —
coerce what can be coerced, drop what cannot — with one addition: a malformed proposal drops the
*whole* proposal and leaves the prose, because half an edit is worse than none and the answer is
still worth reading. A dropped proposal is never silent: the answer carries `proposalProblem`, one
sentence saying why, and the proposal it rejected, so the device can ask once more with the sentence
in hand (`docs/features/article-chat.md` §5.5), and the call journal records both.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from acervo import activity
from acervo.errors import ApiError
from acervo.models import journal
from acervo.models.call import HEDGE_SECONDS
from acervo.repository import graph
from acervo.services.capture.coerce import (
    REFERENCE_LIMIT,
    pick_optional_choice,
    text_list,
    trimmed,
)
from acervo.services.models import llm_json
from acervo.services.prompts import prompt_text
from acervo.services.reader import vocabulary_for, with_reader
from acervo.settings import Settings

DOCUMENT_LIMIT = 32000
TURN_LIMIT = 8
NEIGHBOUR_LIMIT = 20
REPLY_LIMIT = 1200
FOLLOW_UP_LIMIT = 3
FOLLOW_UP_CHARS = 40
OP_LIMIT = 24
# How many times the device may send a turn back with what was wrong with its answer. Stated here so
# the route can refuse a third; the loop itself is the device's (`AskDock.tsx`).
REPAIR_LIMIT = 2
# How much of a failed answer the journal keeps. Far more than `journal.EXCERPT`: the question a
# failed edit raises is *which* operation was wrong, and four hundred characters stop before it.
FAILED_ANSWER_CHARS = 8000


REFERENCE_MODES = ("faithful", "expand")

# What each operation must carry to be worth sending to a client, as (field, kind). This is the
# *shape* only — whether `sense:kq2…` names a record, whether `notes` may be set on it, and whether
# the value is of the right type are questions about the document's meaning, and the document is a
# YAML string this layer deliberately does not parse. `web/src/articleEdit.ts` answers those.
#
# Every operation carries a `target`. On `set` and `remove` it names a record; on `add` and
# `reorder` the record does not exist yet, so it names a kind and `_ADD_SHAPE` says what else that
# kind needs.
_OP_SHAPE: dict[str, tuple[tuple[str, type], ...]] = {
    "set": (("target", str), ("field", str)),
    "add": (("target", str),),
    "remove": (("target", str),),
    "reorder": (("target", str), ("ids", list)),
}

# What an operation's own keys are called, so a field named like one is never read as its value.
_OP_KEYS = frozenset({"op", "target", "field", "value", "in", "after", "ref", "ids", "reason",
                      "fromAttestation"})

_ADD_SHAPE: dict[str, tuple[tuple[str, type], ...]] = {
    "sense": (("value", dict),),
    "example": (("in", str), ("value", dict)),
    "attestation": (("ref", str), ("value", dict)),
}

# A follow-up that says nothing back wastes the only one-tap slot there is on a phone. The prompt
# forbids these; this is the cap it cannot argue with, in the spirit of every other limit here.
# Matched against the **whole** string, never as a substring, so "Thanks, now add an example"
# survives — which is the one thing this must not get wrong.
_ACKNOWLEDGEMENTS = frozenset({
    "looks good", "look good", "thanks", "thank you", "perfect", "great", "nice", "ok", "okay",
    "got it", "sounds good", "makes sense", "cool", "no thanks", "nothing else", "all good",
    "thats helpful", "that's helpful", "good to know", "understood", "fine", "agreed", "yes",
    "no", "noted",
})


UNUSABLE = "The language model did not return a usable answer, so nothing was changed."


def run_chat(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    subject = _subject(body)
    name = "acervo_chat" if subject["kind"] == "article" else "acervo_chat_reference"
    try:
        answer, call = llm_json(
            settings, owner,
            with_reader(prompt_text(settings.prompts_path, name), owner,
                        vocabulary_for(graph.owner_vocabularies(owner), subject["language"])),
            _user_turn(subject, body), caller="chat", hedge_after=HEDGE_SECONDS,
        )
    except ApiError as refused:
        # `llm_json`'s own two messages end "so nothing was created", which is true of every other
        # caller and false of this one: chat creates nothing, ever. Re-phrase those two rather than
        # forking `REFUSALS` — that table is a contract the file ingestion retries against by code,
        # and the seven mapped refusals keep their wording untouched.
        if refused.code in ("llm_empty", "llm_unusable"):
            raise ApiError(refused.status, refused.code, UNUSABLE) from None
        raise
    if not isinstance(answer, Mapping):
        _journal(subject, body, None, answer, failed=True, problem="not a JSON object")
        raise ApiError(502, "llm_unusable", UNUSABLE)
    try:
        shaped = _shaped(answer, subject, call.model)
    except ApiError:
        _journal(subject, body, None, answer, failed=True, problem="no reply")
        raise
    _journal(subject, body, shaped, answer, failed=bool(shaped.get("proposalProblem")),
             problem=shaped.get("proposalProblem"))
    return shaped


def _journal(subject: dict[str, Any], body: dict[str, Any], shaped: dict[str, Any] | None,
             answer: Any, failed: bool, problem: str | None) -> None:
    """One line per turn: what the answer was, and — when it could not be used — all of it.

    A repair is logged with the sentence that sent it back, so the device's refusals, which happen
    nowhere near the server, are on the record too.
    """
    repair = _repair(body)
    proposal = (shaped or {}).get("proposal")
    intent = answer.get("intent") if isinstance(answer, Mapping) else None
    result = "unusable" if shaped is None else "dropped" if problem else \
        "proposed" if proposal else "capture" if shaped.get("capture") else "answered"
    journal.outcome(
        "chat", failed or bool(repair), subject=subject["kind"], result=result,
        intent=intent if isinstance(intent, str) else None,
        ops=len(proposal["ops"]) if proposal else None,
        repair=repair["attempt"] if repair else None,
        repairFor=repair["problem"] if repair else None,
        problem=problem,
    )
    if repair and repair["previous"]:
        # The proposal the device refused, which reached no log on its own way through: the server
        # had passed it as well formed.
        journal.logger.warning("chat sent back %s", journal.excerpt(repair["previous"], FAILED_ANSWER_CHARS))
    if failed or repair:
        journal.logger.warning("chat answer %s", journal.excerpt(
            json.dumps(answer, ensure_ascii=False), FAILED_ANSWER_CHARS))


def report_refusal(owner: str, body: dict[str, Any]) -> dict[str, Any]:
    """A proposal the device would not apply, after it had sent the turn back as often as it may.

    The refusal happened on the device, nowhere near a log; this is where it is written down, under
    the turn's own request id, beside the calls and the repairs that led to it. Writes nothing else.
    """
    problem = trimmed(body.get("problem"))
    if not problem:
        raise ApiError(400, "invalid_input", "That report does not say what was refused.")
    proposal = body.get("proposal")
    ops = proposal.get("ops") if isinstance(proposal, Mapping) else None
    activity.note(
        "chat proposal refused", failed=True, problem=problem[:REPLY_LIMIT],
        ops=len(ops) if isinstance(ops, list) else None,
        proposal=json.dumps(proposal, ensure_ascii=False) if proposal is not None else None,
    )
    return {}


def _subject(body: dict[str, Any]) -> dict[str, Any]:
    raw = body.get("subject")
    if not isinstance(raw, Mapping):
        raise ApiError(400, "invalid_input", "That request does not say what it is about.")
    kind = trimmed(raw.get("kind"))
    if kind == "article":
        document = trimmed(raw.get("document"))
        if not document:
            raise ApiError(400, "invalid_input", "That request carries no entry to talk about.")
        return {
            "kind": "article",
            "lexemeId": trimmed(raw.get("lexemeId")),
            "language": trimmed(raw.get("language")) or None,
            "document": document[:DOCUMENT_LIMIT],
            "focus": trimmed(raw.get("focus")) or None,
        }
    if kind == "reference":
        headword = trimmed(raw.get("headword"))
        if not headword:
            raise ApiError(400, "invalid_input", "That request carries no word to talk about.")
        return {
            "kind": "reference",
            "headword": headword,
            "language": trimmed(raw.get("language")) or None,
        }
    raise ApiError(400, "invalid_input", "That request is about something Acervo does not recognise.")


def _turns(body: dict[str, Any]) -> list[dict[str, str]]:
    """The transcript, oldest first, capped. The last `you` turn is the question being asked.

    An `acervo` turn that offered a change says what became of it. Without that line the next turn
    reads its own "here is a change…" and believes the entry changed, when the device may have
    refused the proposal or the learner never opened it — and then "don't rewrite" is a complaint it
    cannot place.
    """
    raw = body.get("turns")
    if not isinstance(raw, list):
        return []
    kept: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        text = trimmed(item.get("text"))
        if not text:
            continue
        role = "you" if trimmed(item.get("role")) == "you" else "acervo"
        offered = item.get("offered")
        if role == "acervo" and isinstance(offered, Mapping):
            text = f"{text}\n  {_offered_line(offered)}"
        kept.append({"role": role, "text": text})
    return kept[-TURN_LIMIT:]


def _offered_line(offered: Mapping[str, Any]) -> str:
    summary = trimmed(offered.get("summary")) or "a change"
    outcome = trimmed(offered.get("outcome"))
    if outcome == "applied":
        became = "applied, so the entry above already includes it"
    elif outcome == "refused":
        reason = trimmed(offered.get("reason"))
        became = "NOT applied, nothing changed" + (f": {reason}" if reason else "")
    elif outcome == "discarded":
        # Not "NOT applied": the prompt reads that as a request still standing, and this one the
        # learner looked at and turned down.
        became = "discarded by the learner, nothing changed"
    else:
        became = "not reviewed, nothing changed"
    return f"[offered a change: {summary} — {became}]"


def _repair(body: dict[str, Any]) -> dict[str, Any] | None:
    """What was wrong with the answer the device is sending back, if it is sending one back."""
    raw = body.get("repair")
    if not isinstance(raw, Mapping):
        return None
    problem = trimmed(raw.get("problem"))
    if not problem:
        return None
    attempt = raw.get("attempt")
    attempt = attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else 1
    if not 1 <= attempt <= REPAIR_LIMIT:
        raise ApiError(400, "invalid_input",
                       f"A turn can be sent back at most {REPAIR_LIMIT} times, so nothing was changed.")
    previous = raw.get("previous")
    return {"problem": problem[:REPLY_LIMIT], "attempt": attempt,
            "previous": json.dumps(previous, ensure_ascii=False)[:DOCUMENT_LIMIT // 4]
            if previous is not None else None}


def _neighbours(body: dict[str, Any]) -> list[dict[str, str]]:
    """Headword and gloss only — enough to say "you already have «el traje»", and nothing more."""
    raw = body.get("neighbours")
    if not isinstance(raw, list):
        return []
    kept: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        headword = trimmed(item.get("headword"))
        if not headword:
            continue
        kept.append({"headword": headword, "shortGloss": trimmed(item.get("shortGloss"))})
        if len(kept) == NEIGHBOUR_LIMIT:
            break
    return kept


def _user_turn(subject: dict[str, Any], body: dict[str, Any]) -> str:
    reference = trimmed(body.get("reference"))[:REFERENCE_LIMIT]
    sources = text_list(body.get("referenceSources"))
    neighbours = _neighbours(body)
    turns = _turns(body)

    return "\n".join(
        line
        for line in [
            "The learner's own entry for this word, in the projection Acervo stores.\n"
            "THIS IS THE SOURCE OF TRUTH, and the only thing you may propose changing:\n"
            "```\n" + subject["document"] + "\n```"
            if subject["kind"] == "article"
            else "",
            "They tapped this part of the entry, so keep any edit inside it: " + subject["focus"]
            if subject["kind"] == "article" and subject["focus"]
            else "",
            "The dictionary entry they are reading: " + subject["headword"]
            if subject["kind"] == "reference"
            else "",
            "Its language: " + subject["language"]
            if subject["kind"] == "reference" and subject["language"]
            else "",
            "",
            "Other words this learner already has, so you can point at one by name:\n"
            + "\n".join(
                f"- {item['headword']}" + (f" — {item['shortGloss']}" if item["shortGloss"] else "")
                for item in neighbours
            )
            if neighbours
            else "",
            "\nExternal dictionary entries open on the same screen"
            + (f" (from {', '.join(sources)})" if sources else "")
            + ". READ-ONLY reference,\noften poor, and never something you may propose changing:\n"
            "```\n" + reference + "\n```"
            if reference
            else "",
            "\nThe conversation so far, oldest first. The last line is what they are asking now:\n"
            + "\n".join(f"{item['role']}: {item['text']}" for item in turns)
            if turns
            else "",
            _repair_block(_repair(body)),
        ]
        if line != ""
    )


def _repair_block(repair: dict[str, Any] | None) -> str:
    if not repair:
        return ""
    return (
        "\nYOUR PREVIOUS ANSWER TO THIS SAME LAST LINE COULD NOT BE USED, so nothing was changed:\n"
        f"{repair['problem']}\n"
        + (f"The proposal you returned was:\n{repair['previous']}\n" if repair["previous"] else "")
        + "Answer the same last line again. Return the whole JSON object, with exactly that problem "
        "fixed and everything else as it should have been."
    )


def _shaped(answer: Mapping[str, Any], subject: dict[str, Any], model: str) -> dict[str, Any]:
    reply = trimmed(answer.get("reply"))
    if not reply:
        raise ApiError(502, "llm_unusable", UNUSABLE)
    follow_ups = [
        text[:FOLLOW_UP_CHARS] for text in text_list(answer.get("followUps")) if _useful(text)
    ]
    intent = answer.get("intent")
    shaped: dict[str, Any] = {
        "reply": reply[:REPLY_LIMIT],
        "followUps": follow_ups[:FOLLOW_UP_LIMIT],
        "proposal": None,
        "proposalProblem": None,
        "rejected": None,
        "capture": _capture(answer.get("capture")) if subject["kind"] == "reference" else None,
        "modelId": model,
    }
    # Which of the two survives is the whole difference between the subject kinds. A dictionary entry
    # is not the learner's to edit, so a proposal against one is dropped rather than refused: the
    # prose is still worth reading.
    if subject["kind"] != "article":
        return shaped
    raw = answer.get("proposal")
    proposal, problem = _proposal(raw)
    if proposal is None and problem is None and intent == "edit":
        problem = ("Your answer said `intent: \"edit\"` but carried no `proposal`. A turn that asks "
                   "for a change gets the operations that make it.")
    shaped["proposal"] = proposal
    shaped["proposalProblem"] = problem
    shaped["rejected"] = raw if problem and isinstance(raw, Mapping) else None
    return shaped


def _proposal(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """The proposal, or why there is none. No proposal and no problem is a plain answer."""
    if raw is None:
        return None, None
    if not isinstance(raw, Mapping):
        return None, "`proposal` must be an object with `summary` and `ops`, or null."
    ops = raw.get("ops")
    if not isinstance(ops, list) or not ops:
        return None, "The proposal carried no `ops` list."
    if len(ops) > OP_LIMIT:
        return None, (f"The proposal carried {len(ops)} operations; at most {OP_LIMIT} are allowed. "
                      "Change only what the last line asked for.")
    shaped: list[dict[str, Any]] = []
    for index, item in enumerate(ops, start=1):
        op, problem = _op(item)
        # One malformed operation drops the whole proposal. A partly-readable edit set is exactly
        # the thing `applyOps` refuses on the device, and shipping it would only move the refusal
        # somewhere the reader cannot tell a model's mistake from Acervo's.
        if op is None:
            return None, f"Operation {index} {problem}: {json.dumps(item, ensure_ascii=False)[:300]}"
        shaped.append(op)
    return {"summary": trimmed(raw.get("summary")), "ops": shaped}, None


def _op(raw: Any) -> tuple[dict[str, Any] | None, str]:
    """An operation in its wire shape, or what is wrong with it, said so a model can fix it."""
    if not isinstance(raw, Mapping):
        return None, "is not an object"
    name = trimmed(raw.get("op"))
    required = _OP_SHAPE.get(name)
    if required is None:
        return None, "has an `op` that is not one of set, add, remove or reorder"
    op: dict[str, Any] = {"op": name}
    for field, kind in required:
        value = raw.get(field)
        if kind is str:
            text = trimmed(value)
            if not text:
                return None, f"is a `{name}` with no `{field}`"
            op[field] = text
        elif not isinstance(value, kind):
            return None, f"is a `{name}` whose `{field}` is not a list"
        else:
            op[field] = value
    if name == "reorder":
        # One kind of reordering exists. A target this layer does not know is a mistake to surface,
        # not a thing to pass on.
        if op["target"] != "senses":
            return None, "is a `reorder` whose `target` is not \"senses\""
        ids = [trimmed(item) for item in op["ids"]]
        if not ids or not all(ids):
            return None, "is a `reorder` with an empty id in `ids`"
        op["ids"] = ids
    if name == "set":
        # `value` is the one field with no shape at all: a string, a list of strings, a list of
        # gloss objects, or null, depending on which field is being set. The device knows which.
        #
        # It must be *present*. Read as absent-means-null, `{"field": "translation", "translation":
        # "…"}` — a shape a real model writes — would set the translation to nothing and erase it.
        # The value under the field's own name is read instead, for the reason `fromAttestation` is
        # read from two places below: the intent is unambiguous and the answer is untrusted input.
        if "value" in raw:
            op["value"] = raw["value"]
        elif op["field"] in raw and op["field"] not in _OP_KEYS:
            op["value"] = raw[op["field"]]
        else:
            return None, "is a `set` with no `value` (the new value goes in `value`, even when it is null)"
    if name == "add":
        required = _ADD_SHAPE.get(op["target"])
        # An unknown kind drops the whole proposal, exactly as an unknown operation name does.
        if required is None:
            return None, "is an `add` whose `target` is not sense, example or attestation"
        for field, kind in required:
            value = raw.get(field)
            if kind is str:
                text = trimmed(value)
                if not text:
                    return None, f"is an `add` of {op['target']} with no `{field}`"
                op[field] = text
            elif not isinstance(value, kind):
                return None, f"is an `add` of {op['target']} whose `{field}` is not an object"
            else:
                op[field] = value
        if op["target"] == "sense":
            op["after"] = trimmed(raw.get("after")) or None
        if op["target"] == "example":
            # Accepted beside `in` or inside `value`, because a real model puts it in both places.
            # This is not compatibility machinery: the answer is untrusted input and reading it
            # generously is what `capture/coerce.py` exists for. Getting it wrong is *silent* — the
            # applier would derive `origin: "llm"` for a sentence the learner actually met, which is
            # a provenance lie no validation would catch.
            nested = op["value"].pop("fromAttestation", None)
            op["fromAttestation"] = trimmed(raw.get("fromAttestation")) or trimmed(nested) or None
    if name == "remove":
        op["reason"] = trimmed(raw.get("reason"))
    return op, ""


def _useful(text: str) -> bool:
    """Is this follow-up worth the slot it occupies?"""
    bare = "".join(letter for letter in text.casefold() if letter.isalnum() or letter in " '").strip()
    return bool(bare) and bare not in _ACKNOWLEDGEMENTS


def _capture(raw: Any) -> dict[str, Any] | None:
    """The argument list for the capture the interface already performs from an external article."""
    if not isinstance(raw, Mapping):
        return None
    headword = trimmed(raw.get("headword"))
    if not headword:
        return None
    return {
        "headword": headword,
        "note": trimmed(raw.get("note")),
        "referenceMode": pick_optional_choice(raw.get("referenceMode"), REFERENCE_MODES),
    }
