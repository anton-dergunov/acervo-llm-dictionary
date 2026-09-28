"""Saving an article: a parsed document in, one atomic write out (`docs/architecture/jobs.md`).

The one writer of articles. The device parses the YAML — `web/src/yaml.ts` stays the only place the
projection is understood — and sends the resulting `ArticleDraft` as JSON; everything from there on
is here, so the interface, the headless capture job and any future client save the same way.

The diff is by the ids the document carries, and needs no content matching: a record carrying an id
is the one it names, a record without one is new, and a stored record the document no longer
mentions is tombstoned rather than erased — which is what lets undo put it back. Nothing is recreated
to avoid a diff; ids stay put across an edit.

**The device says what it edited from.** `base` maps every record of the entry its replica held to
the revision it held it at. That revision is what each write states, so a document edited from a
stale replica is refused by the merge rather than laid over a newer row; and only records in `base`
are tombstoned, so a sense added on another device and not yet pulled here is never removed by a
document that could not have mentioned it. A headless save has no replica and sends no `base`; it
is diffed against the stored rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from acervo.clips.ids import clip_example_id
from acervo.domain.ids import is_record_id, new_record_id, now_instant
from acervo.errors import ApiError
from acervo.images.ids import image_prompt_id
from acervo.repository import graph

LEXEME_FIELDS = (
    "language", "headword", "lemma", "reading", "ipa", "pos", "gender", "register", "dialect",
    "emoji", "status", "shortGloss", "primaryGloss", "emotion",
)
SENSE_FIELDS = ("definition", "definitionLang", "glosses", "domain", "emoji", "order")
ATTESTATION_FIELDS = (
    "text", "translation", "sourceUrl", "sourceTitle", "sourceKind", "photoRef", "photoRegion",
)
EXAMPLE_FIELDS = (
    "text", "textLang", "translation", "translationLang", "origin", "sourceAttestationId", "modelId",
    "videoRef", "videoTitle", "videoChannel", "videoStart", "videoEnd", "clipRef", "imageRef",
    "emotion", "note", "matchedForm", "matchedTranslationForm",
)
# What a document says about a picture. `attempts`, `failureReason` and `suppressed` are
# deliberately absent: they are facts about what the server did, carried through from the stored row,
# so editing a word's YAML cannot un-suppress a picture or zero an attempt counter.
IMAGE_FIELDS = (
    "exampleId", "prompt", "styleId", "seed", "modelId", "promptVersion", "imageRef", "imageModelId",
)


def refused(message: str) -> ApiError:
    return ApiError(400, "invalid_document", message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ApiError(400, "invalid_input", f"{label} must be an object.")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ApiError(400, "invalid_input", f"{label} must be a list.")
    return value


def _id(value: Any, label: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not is_record_id(value):
        raise ApiError(400, "invalid_input", f"{label} is not a record id.")
    return value


def _fields(source: Mapping[str, Any], names: Iterable[str]) -> dict[str, Any]:
    return {name: source.get(name) for name in names}


class _Save:
    """One save's working state: what is stored, what the document keeps, and what changes."""

    def __init__(self, owner: str, device: str, draft: Mapping[str, Any], minted: set[str],
                 base: Mapping[str, int] | None) -> None:
        self.base = base
        self.owner = owner
        self.device = device
        self.draft = draft
        self.minted = minted
        self.at = now_instant()
        self.changes: dict[str, list[dict[str, Any]]] = {}

    def stamp(self, existing: Mapping[str, Any] | None) -> dict[str, Any]:
        return {
            "deleted": False,
            "createdAt": (existing or {}).get("createdAt") or self.at,
            "editedAt": self.at,
            "editedBy": self.device,
            # The revision the edit is based on. The merge refuses the write if it has moved on.
            "revision": self.revision(existing),
        }

    def revision(self, existing: Mapping[str, Any] | None) -> int:
        if existing is None:
            return 0
        if self.base is not None and existing["id"] in self.base:
            return self.base[existing["id"]]
        return int(existing.get("revision", 0))

    def knew(self, record: Mapping[str, Any]) -> bool:
        """Whether the document's author could have mentioned this record."""
        return self.base is None or record["id"] in self.base

    def change(self, key: str, record: dict[str, Any]) -> None:
        self.changes.setdefault(key, []).append(record)


def save_article(
    owner: str,
    device: str,
    draft: Any,
    minted: Iterable[str] = (),
    *,
    enqueue: graph.Enqueue | None = graph.SAVE,
    status: str | None = None,
    base: Any = None,
    place_photo: graph.PlacePhoto | None = None,
) -> dict[str, Any]:
    """Apply one parsed document as one write. Returns the merge's answer and the lexeme id.

    `minted` names ids this save is *creating* rather than naming, and is empty for every caller but
    one. A document editing a stored entry may not carry ids its producer minted; a chat proposal that
    adds an example drawn from a sentence you just supplied needs both records in one save, so the
    exception is an **argument**, never a field, and a hand-typed document cannot claim it.

    `status` overrides the document's, for the headless capture that files everything in the Inbox.
    """
    draft = _mapping(draft, "The document")
    if base is not None:
        base = _mapping(base, "The base revisions")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in base.values()):
            raise ApiError(400, "invalid_input", "Base revisions must be whole numbers.")
    work = _Save(owner, device, draft, {m for m in minted if isinstance(m, str)}, base)

    draft_id = _id(draft.get("id"), "The entry id")
    stored = graph.article_records(owner, draft_id) if draft_id else {}
    existing_lexeme = next((row for row in stored.get("lexemes", []) if row["id"] == draft_id), None)
    if draft_id and (existing_lexeme is None or existing_lexeme["deleted"]):
        raise refused("This document names an entry that is not in your vocabulary, so it was not saved.")
    lexeme_id = draft_id or new_record_id()
    minting = draft_id is None

    topics = graph.owner_topics(owner)
    by_name = {topic["name"].strip().lower(): topic["id"] for topic in topics}
    topic_ids = []
    for name in _list(draft.get("topics"), "Topics"):
        key = str(name).strip().lower()
        if key not in by_name:
            known = ", ".join(sorted(topic["name"] for topic in topics)) or "none yet"
            raise ApiError(
                400, "unknown_topic",
                f'There is no topic called "{name}". Topics are created deliberately; '
                f"the ones you have are: {known}.",
            )
        topic_ids.append(by_name[key])

    work.change("lexemes", {
        **(existing_lexeme or {}),
        "id": lexeme_id,
        **_fields(draft, LEXEME_FIELDS),
        **({"status": status} if status else {}),
        "topicIds": topic_ids,
        "notes": _list(draft.get("notes"), "Notes"),
        # Server-written state: a document cannot assert it, so a save carries whatever is stored and
        # a new word starts never-consulted.
        "clipsSearchedAt": (existing_lexeme or {}).get("clipsSearchedAt"),
        **work.stamp(existing_lexeme),
    })

    # Everything the document may name, whoever it belongs to among this owner's records.
    attestations = [_mapping(a, "An attestation") for a in _list(draft.get("attestations"), "Attestations")]
    senses = [_mapping(s, "A sense") for s in _list(draft.get("senses"), "Senses")]
    loose_images = [_mapping(i, "A picture") for i in _list(draft.get("images"), "Pictures")]
    examples = [
        (sense, _mapping(e, "An example"))
        for sense in senses for e in _list(sense.get("examples"), "Examples")
    ]
    sense_images = [
        (sense, _mapping(i, "A picture"))
        for sense in senses for i in _list(sense.get("images"), "Pictures")
    ]
    held = {
        "attestations": graph.owned_records(
            owner, "attestations", [_id(a.get("id"), "An attestation id") for a in attestations]),
        "senses": graph.owned_records(
            owner, "senses", [_id(s.get("id"), "A sense id") for s in senses]),
        "examples": graph.owned_records(
            owner, "examples", [_id(e.get("id"), "An example id") for _, e in examples]),
        "imagePrompts": graph.owned_records(
            owner, "imagePrompts",
            [_id(i.get("id"), "A picture id") for _, i in sense_images]
            + [_id(i.get("id"), "A picture id") for i in loose_images]),
    }
    # An example belongs to this entry when the sense it is stored under does. That also allows
    # moving one between senses of the same entry: the id is kept, the parent changes.
    example_parents = graph.owned_records(
        owner, "senses", [row["senseId"] for row in held["examples"].values()])

    def claim(key: str, identifier: str | None, belongs) -> dict[str, Any] | None:
        """The stored record a document id names, refusing one that is not this entry's.

        An id naming nothing at all is refused too — except in a brand-new article, which cannot
        legitimately reference a stored child, so every id it carries is one its producer minted.
        """
        if identifier is None:
            return None
        existing = held[key].get(identifier)
        if existing is None:
            if not minting and identifier not in work.minted:
                raise refused(
                    f"This document names a record that is not in your vocabulary ({identifier}), "
                    "so it was not saved."
                )
            return None
        if not belongs(existing):
            raise refused(f"The id {identifier} belongs to a different entry, so this document was not saved.")
        return existing

    def derived(key: str, identifier: str) -> dict[str, Any] | None:
        """The stored row a derived id already names — the second writer finds the first's row.

        Tombstones included: the id is a function of the sense, so a removed row is the only row
        this record could ever occupy, and writing revision zero over it would be refused as stale.
        """
        return next((row for row in stored.get(key, []) if row["id"] == identifier), None)

    kept: dict[str, set[str]] = {"senses": set(), "examples": set(), "attestations": set(), "imagePrompts": set()}

    def picture(image: Mapping[str, Any], sense_id: str | None) -> None:
        identifier = _id(image.get("id"), "A picture id")
        existing = claim("imagePrompts", identifier, lambda row: row["lexemeId"] == lexeme_id)
        # Derived from the sense, never random: it is what lets a saved document and the server's own
        # enrichment write for a sense without coordinating.
        if identifier is None and sense_id:
            identifier = image_prompt_id(sense_id)
            existing = derived("imagePrompts", identifier)
        identifier = identifier or new_record_id()
        kept["imagePrompts"].add(identifier)
        work.change("imagePrompts", {
            "attempts": 0,
            "failureReason": None,
            "suppressed": False,
            **(existing or {}),
            "id": identifier,
            "lexemeId": lexeme_id,
            "senseId": sense_id,
            **_fields(image, IMAGE_FIELDS),
            **work.stamp(existing),
        })

    for attestation in attestations:
        identifier = _id(attestation.get("id"), "An attestation id")
        existing = claim("attestations", identifier, lambda row: row["lexemeId"] == lexeme_id)
        identifier = identifier or new_record_id()
        kept["attestations"].add(identifier)
        captured = str(attestation.get("capturedAt") or "").strip()
        work.change("attestations", {
            **(existing or {}),
            "id": identifier,
            "lexemeId": lexeme_id,
            **_fields(attestation, ATTESTATION_FIELDS),
            # Editable like any other field; a new one that does not name a moment is captured now.
            "capturedAt": captured or (existing or {}).get("capturedAt") or work.at,
            **work.stamp(existing),
        })

    for sense in senses:
        identifier = _id(sense.get("id"), "A sense id")
        existing = claim("senses", identifier, lambda row: row["lexemeId"] == lexeme_id)
        sense_id = identifier or new_record_id()
        kept["senses"].add(sense_id)
        work.change("senses", {
            **(existing or {}),
            "id": sense_id,
            "lexemeId": lexeme_id,
            **_fields(sense, SENSE_FIELDS),
            **work.stamp(existing),
        })

        for example in _list(sense.get("examples"), "Examples"):
            example = _mapping(example, "An example")
            identifier = _id(example.get("id"), "An example id")
            current = claim(
                "examples", identifier,
                lambda row: (example_parents.get(row["senseId"]) or {}).get("lexemeId") == lexeme_id,
            )
            clip = example.get("clipRef")
            # A clip's id is derived from its sense and the segment it quotes, so two writers that
            # pick the same segment converge on one row. Everything else is random.
            if identifier is None and isinstance(clip, str) and clip:
                identifier = clip_example_id(sense_id, clip)
                current = derived("examples", identifier)
            identifier = identifier or new_record_id()
            kept["examples"].add(identifier)
            work.change("examples", {
                **(current or {}),
                "id": identifier,
                "senseId": sense_id,
                **_fields(example, EXAMPLE_FIELDS),
                **work.stamp(current),
            })

        for image in _list(sense.get("images"), "Pictures"):
            picture(_mapping(image, "A picture"), sense_id)

    for image in loose_images:
        picture(image, None)

    # Whatever the document stopped mentioning. A tombstone rather than a deletion, because a pull
    # asks for `revision > cursor` and a row that is simply gone has no revision left to send.
    def tombstone(key: str, record: Mapping[str, Any]) -> None:
        work.change(key, {**record, **work.stamp(record), "deleted": True})

    def live(key: str) -> list[dict[str, Any]]:
        return [row for row in stored.get(key, []) if not row["deleted"] and work.knew(row)]

    stored_senses = {row["id"] for row in live("senses")}
    for row in live("senses"):
        if row["id"] not in kept["senses"]:
            tombstone("senses", row)
    for row in live("attestations"):
        if row["id"] not in kept["attestations"]:
            tombstone("attestations", row)
    # Covers both an example removed on its own and one carried away by its sense — and not one the
    # document moved to another of this entry's senses, which is already written above.
    for row in live("examples"):
        if row["senseId"] in stored_senses and row["id"] not in kept["examples"]:
            tombstone("examples", row)
    for row in live("imagePrompts"):
        if row["id"] not in kept["imagePrompts"]:
            tombstone("imagePrompts", row)
    # A clip of something the document removed reads words that no longer exist. The headword's
    # clip is never among them: the lexeme stays, and an edited headword only makes its clip stale.
    targets = {"sense": kept["senses"], "example": kept["examples"], "attestation": kept["attestations"]}
    for row in live("pronunciations"):
        if row["targetKind"] in targets and row["targetId"] not in targets[row["targetKind"]]:
            tombstone("pronunciations", row)
    # A meaning the document removed takes its study state with it; the word's own row stays. Not
    # through `live()`: no document mentions a study state, so the author never "knew" one.
    removed = stored_senses - kept["senses"]
    for row in stored.get("studyStates", []):
        if not row["deleted"] and row["senseId"] in removed:
            tombstone("studyStates", row)

    written = graph.merge_graph(
        owner, device, work.changes, enqueue=enqueue, place_photo=place_photo
    )
    return {**written, "lexemeId": lexeme_id, "jobId": written["enrich"].get(lexeme_id)}
