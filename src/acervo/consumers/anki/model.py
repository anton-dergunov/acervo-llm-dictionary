"""Acervo's two note types, and the difference between their shape and their look.

**A word note** tests what the word itself is: hearing it (`Listen`). **A meaning note** tests one
meaning: recognising it in a sentence (`Recognise`) and producing the word for it (`Produce`). A
sense's own note carries `Produce`, and `Recognise` too when the sense has no example; each example
has a meaning note of its own that carries `Recognise` alone. Which cards a note makes is decided by
its gate fields: Anki makes a card only when the front renders something, and every front is wrapped
in its gate.

**Shape and look are kept apart because Anki treats them apart.** Adding or renaming a field or a
card type is a schema change, and a schema change forces a full sync — exactly what the robot must
never choose for anyone (`docs/features/anki.md`, risk 2). Editing a template's HTML or the CSS is
not: it travels in an ordinary sync. So the fields and card types below are fixed and checked, and a
collection that differs is refused; the design is read from `templates/anki/` and brought up to date
by every push.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ModelMismatchError(RuntimeError):
    """The collection has an incompatible Acervo-owned note type."""


# Every note carries its identity. `AcervoNoteId` is the join (a lexeme, sense or example id);
# the other two say what the note's review state reports on.
IDENTITY_FIELDS = ("AcervoNoteId", "AcervoLexemeId", "AcervoSenseId")

# Fields that hold a file. A manifest names a path; the note holds the tag that plays or shows it —
# `<img src>` and `<audio src>` are what Anki's Check Media counts as a reference.
MEDIA_FIELDS = {
    "HeadwordAudio": "audio",
    "SentenceAudio": "audio",
    "DefinitionAudio": "audio",
    "Picture": "image",
}

_WORD_HEAD = ("Language", "Article", "Headword", "Reading", "IPA", "Grammar", "HeadwordAudio")


@dataclass(frozen=True)
class CardType:
    name: str
    front: str
    back: str


@dataclass(frozen=True)
class NoteKind:
    key: str
    name: str
    fields: tuple[str, ...]
    cards: tuple[CardType, ...]
    # The fields a note must fill for at least one card to exist.
    gates: tuple[str, ...]

    @property
    def content_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name in self.fields if name not in IDENTITY_FIELDS and name not in MEDIA_FIELDS
        )

    @property
    def media_fields(self) -> tuple[str, ...]:
        return tuple(name for name in self.fields if name in MEDIA_FIELDS)


WORD = NoteKind(
    key="word",
    name="Acervo Word",
    fields=(*IDENTITY_FIELDS, *_WORD_HEAD, "Glosses", "Senses", "Note"),
    cards=(CardType("Listen", "word-listen.front.html", "word-listen.back.html"),),
    gates=("HeadwordAudio",),
)

MEANING = NoteKind(
    key="meaning",
    name="Acervo Meaning",
    fields=(
        *IDENTITY_FIELDS, "Recognise", "Produce", *_WORD_HEAD,
        "Sentence", "SentenceAudio", "Translation", "Source", "Cloze",
        "Gloss", "GlossMore", "Domain", "SenseLabel", "Definition", "DefinitionAudio",
        "Picture", "Note", "Senses",
    ),
    cards=(
        CardType("Recognise", "meaning-recognise.front.html", "meaning-recognise.back.html"),
        CardType("Produce", "meaning-produce.front.html", "meaning-produce.back.html"),
    ),
    gates=("Recognise", "Produce"),
)

KINDS: dict[str, NoteKind] = {kind.key: kind for kind in (WORD, MEANING)}
SORT_FIELD = "Headword"
SCRIPT_MARKER = "<!-- acervo:script -->"


@dataclass(frozen=True)
class CardDesign:
    """What the cards look like, read from `templates/anki/`: the faces, one stylesheet shared by
    both note types, the script every face ends with, and the fonts the stylesheet names."""

    css: str
    faces: dict[str, str]
    fonts: tuple[Path, ...]

    @classmethod
    def load(cls, template_dir: str | Path) -> CardDesign:
        root = Path(template_dir) / "anki"
        script = (root / "cards.js").read_text(encoding="utf-8").strip()
        faces: dict[str, str] = {}
        for kind in KINDS.values():
            for card in kind.cards:
                for face in (card.front, card.back):
                    text = (root / face).read_text(encoding="utf-8").strip()
                    if SCRIPT_MARKER not in text:
                        raise ModelMismatchError(f"{face} does not say where the card script goes")
                    faces[face] = text.replace(SCRIPT_MARKER, f"<script>\n{script}\n</script>")
        return cls(
            css=(root / "cards.css").read_text(encoding="utf-8"),
            faces=faces,
            fonts=tuple(sorted((root / "fonts").glob("_*.woff2"))),
        )


def _templates_of(notetype: dict[str, Any]) -> list[dict[str, Any]]:
    return list(notetype.get("tmpls", []))


def schema_problems(notetype: dict[str, Any], kind: NoteKind) -> list[str]:
    """How a note type in the collection differs from `kind` in ways only a full sync could fix."""
    problems = []
    fields = tuple(field.get("name") for field in notetype.get("flds", []))
    if fields != kind.fields:
        problems.append(f"fields are {', '.join(map(str, fields))}")
    cards = tuple(template.get("name") for template in _templates_of(notetype))
    if cards != tuple(card.name for card in kind.cards):
        problems.append(f"card types are {', '.join(map(str, cards))}")
    return problems


def design_signature(notetype: dict[str, Any]) -> str:
    payload = {
        "css": notetype.get("css", ""),
        "templates": [
            [template.get("name"), template.get("qfmt"), template.get("afmt")]
            for template in _templates_of(notetype)
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _apply_design(notetype: dict[str, Any], kind: NoteKind, design: CardDesign) -> None:
    notetype["css"] = design.css
    for template, card in zip(_templates_of(notetype), kind.cards):
        template["qfmt"] = design.faces[card.front]
        template["afmt"] = design.faces[card.back]


def require_notetype(
    collection: Any, kind: NoteKind, design: CardDesign, *, update_design: bool
) -> tuple[dict[str, Any], bool]:
    """The note type for `kind`, refused if its shape differs. Its look is brought up to date when
    `update_design` is set, which is an ordinary change; the second value says whether it was."""
    held = collection.models.by_name(kind.name)
    if held is None:
        raise ModelMismatchError(
            f"The {kind.name!r} note type is missing; run bootstrap-upload or adopt-server first"
        )
    # A copy: Anki hands back its cached note type, and a look applied to that without being saved
    # would read as already current to the next caller.
    notetype = copy.deepcopy(held)
    problems = schema_problems(notetype, kind)
    if problems:
        raise ModelMismatchError(
            f"The {kind.name!r} note type differs from this robot version ({'; '.join(problems)}). "
            "Changing it needs a full sync, which routine synchronization never chooses"
        )
    before = design_signature(notetype)
    _apply_design(notetype, kind, design)
    if design_signature(notetype) == before:
        return notetype, False
    if not update_design:
        raise ModelMismatchError(f"The {kind.name!r} cards look different from this robot version")
    collection.models.update_dict(notetype)
    return collection.models.by_name(kind.name), True


def create_notetypes(collection: Any, design: CardDesign) -> dict[str, dict[str, Any]]:
    """Add both note types to a collection that has neither."""
    for kind in KINDS.values():
        if collection.models.by_name(kind.name) is not None:
            raise ModelMismatchError(f"The {kind.name!r} note type already exists")
    created = {}
    for kind in KINDS.values():
        notetype = collection.models.new(kind.name)
        for name in kind.fields:
            collection.models.add_field(notetype, collection.models.new_field(name))
        collection.models.set_sort_index(notetype, kind.fields.index(SORT_FIELD))
        for card in kind.cards:
            collection.models.add_template(notetype, collection.models.new_template(card.name))
        _apply_design(notetype, kind, design)
        collection.models.add(notetype)
        created[kind.key] = require_notetype(collection, kind, design, update_design=False)[0]
    return created


def install_fonts(collection: Any, design: CardDesign) -> int:
    """Put the stylesheet's fonts in the media folder, once. Returns how many were added."""
    added = 0
    for font in design.fonts:
        if collection.media.have(font.name):
            continue
        written = collection.media.write_data(font.name, font.read_bytes())
        if written != font.name:
            raise RuntimeError(f"Anki renamed the font {font.name} to {written}")
        added += 1
    return added
