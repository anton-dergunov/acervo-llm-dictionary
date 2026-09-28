from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .model import KINDS, MEDIA_FIELDS


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RecordId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]{15}$")]

SCHEMA_VERSION = 2
# A file a content field shows itself — a sense's picture in a word's list of senses.
EMBEDDED = re.compile(r'\bsrc="([^"]+)"')


class SyncManifestNote(BaseModel):
    """One Acervo-owned note to create or update in Anki.

    `fields` are the note's content as HTML, by field name, and `media` the files its media fields
    show or play, as paths relative to the manifest. A content field may show a file too, as
    `src="media/…"`; it is imported like the others and the reference rewritten to its name in
    Anki. A field left out is written empty. The identity fields are never given here: they come
    from the ids.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["word", "meaning"]
    note_id: RecordId
    lexeme_id: RecordId
    sense_id: RecordId | None = None
    deck: NonEmptyString
    fields: dict[str, str] = Field(default_factory=dict)
    media: dict[str, NonEmptyString] = Field(default_factory=dict)
    tags: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_note(self) -> SyncManifestNote:
        kind = KINDS[self.kind]
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must be unique")
        unmanaged = [tag for tag in self.tags if not tag.startswith("acervo::")]
        if unmanaged:
            raise ValueError("manifest tags must use the acervo:: namespace")
        if (self.kind == "meaning") != (self.sense_id is not None):
            raise ValueError("a meaning note names its sense and a word note does not")
        unknown = sorted(set(self.fields) - set(kind.content_fields))
        if unknown:
            raise ValueError(f"{kind.name} has no content field {', '.join(unknown)}")
        unknown = sorted(set(self.media) - set(kind.media_fields))
        if unknown:
            raise ValueError(f"{kind.name} has no media field {', '.join(unknown)}")
        # A note that would make no card is refused by Anki, and after the rest have been written.
        if not any(self.fields.get(gate, "").strip() or self.media.get(gate) for gate in kind.gates):
            raise ValueError(f"{self.note_id} would make no card: fill one of {', '.join(kind.gates)}")
        return self

    def media_sources(self, manifest_dir: Path) -> dict[str, Path]:
        """Each media field's file, refusing a path that leaves the payload."""
        return {field: _source(manifest_dir, value, field) for field, value in self.media.items()}

    def embedded_sources(self, manifest_dir: Path) -> dict[str, Path]:
        """Each file a content field shows, by the path the field names it with."""
        return {
            value: _source(manifest_dir, value, field)
            for field, text in self.fields.items()
            for value in EMBEDDED.findall(text)
        }

    @staticmethod
    def media_kind(field: str) -> str:
        return MEDIA_FIELDS[field]


class SyncManifest(BaseModel):
    """Versioned rendered-note input for the Anki robot. The notes' order is the order new cards
    are introduced in."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    notes: list[SyncManifestNote] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_version_and_identities(self) -> SyncManifest:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported manifest schema_version {self.schema_version}; expected {SCHEMA_VERSION}"
            )
        identities = [note.note_id for note in self.notes]
        if len(identities) != len(set(identities)):
            raise ValueError("note_id values must be unique within a manifest")
        return self

    @classmethod
    def load(cls, path: str | Path) -> tuple[SyncManifest, Path]:
        manifest_path = Path(path).expanduser().resolve()
        manifest = cls.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        manifest.validate_media(manifest_path.parent)
        return manifest, manifest_path.parent

    def validate_media(self, manifest_dir: Path) -> None:
        for note in self.notes:
            note.media_sources(manifest_dir)
            note.embedded_sources(manifest_dir)


def _source(manifest_dir: Path, value: str, field: str) -> Path:
    """A payload file, refusing a path that is absolute, leaves the payload or is not there."""
    root = manifest_dir.resolve()
    relative = Path(value)
    if relative.is_absolute() or "://" in value:
        raise ValueError(f"{field} must name a file relative to the manifest: {value}")
    source = (root / relative).resolve()
    if not source.is_relative_to(root):
        raise ValueError(f"{field} escapes the manifest directory: {value}")
    if not source.is_file():
        raise FileNotFoundError(source)
    return source
