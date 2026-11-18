"""The packed-blob artifact: how a compiled dictionary is laid out on disk.

Chosen by measurement in `docs/research/external-dictionaries.md` §11 — a packed blob plus a sidecar
index beat SQLite by 1.53x on total device bytes for the same corpus, and DEFLATE in frames of 256
entries beats per-entry compression by 57 % while keeping a lookup to one ~65 KiB frame decode.

`web/src/dictionary.ts` reads what this writes, and so does `Artifact` below for the server's own
checks. The two files are the same format described twice, so a change here is a change there. A
`fields` payload is the JSON of `model.Entry`: besides the fields it always had, a wiktextract entry
may carry `ipas` (every transcription, one per variety, when there is more than one) and `genders`.

Two details that are load-bearing and easy to get subtly wrong:

* **Keys are ordered by their UTF-8 bytes**, never by locale collation and never by the platform's
  own string comparison. JavaScript compares UTF-16 code units, which disagrees with UTF-8 byte
  order above the BMP, so a reader binary-searching one order over an index built in the other
  silently fails to find real entries.
* **Front-coding destroys random access**, which a binary search needs. Every `RESTART_INTERVAL`-th
  key is therefore stored whole and its offset recorded, so a search binary-searches the restart
  table and then scans at most one bucket.
"""

from __future__ import annotations

import hashlib
import io
import json
import mmap
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

MAGIC = b"ACVD"
FORMAT_VERSION = 1
#: Entries per compressed frame. 256 is the measured optimum (§11.0a): frames of 1024 save a further
#: 2 % but quadruple what a single lookup allocates, which is the wrong trade on a phone.
FRAME_SIZE = 256
#: Keys between restart points. 16 costs ~6 % of key bytes and bounds an intra-bucket scan.
RESTART_INTERVAL = 16
TIERS = ("fields", "html")


def write_varint(buffer: io.BytesIO, value: int) -> None:
    """LEB128, unsigned. Every length and offset in the index is written this way."""
    if value < 0:
        raise ValueError(f"varint values are unsigned, got {value}")
    while True:
        byte = value & 0x7F
        value >>= 7
        buffer.write(bytes([byte | 0x80] if value else [byte]))
        if not value:
            return


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Returns `(value, next_offset)`. The mirror of `write_varint`, used by the tests."""
    value = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7


@dataclass
class SourceEntry:
    """One headword as a converter produces it, before anything is packed.

    `aliases` are additional keys that resolve to this same entry — the traditional form of a
    simplified Chinese headword, or a normalised spelling of an accented one. They cost one index
    record each and no payload at all, which is why the reader can afford to offer them.
    """

    key: str
    payload: bytes
    aliases: Sequence[str] = ()


@dataclass
class BuildReport:
    entry_count: int = 0
    key_count: int = 0
    frame_count: int = 0
    blob_bytes: int = 0
    index_bytes: int = 0
    dropped_fields: set[str] = field(default_factory=set)
    unmapped_pos: set[str] = field(default_factory=set)
    skipped: int = 0
    #: Source entries that were folded into an earlier one sharing their headword. Not a defect:
    #: CC-CEDICT writes one line per reading, so simplified 行 arrives twice, and both articles
    #: belong to the same lookup.
    merged_entries: int = 0


def normalised_alias(key: str) -> str | None:
    """A case- and accent-tolerant spelling, when it differs from the key itself.

    Stored as an ordinary alias rather than handled in the reader, so the matching rule lives in the
    artifact and both sides cannot drift apart.
    """
    import unicodedata

    folded = unicodedata.normalize("NFC", key).casefold()
    return folded if folded != key else None


def _sort_key(key: str) -> bytes:
    return key.encode("utf-8")


def build_artifact(
    entries: Iterable[SourceEntry],
    *,
    destination: Path,
    dictionary_id: str,
    tier: str,
    metadata: dict,
    frame_size: int = FRAME_SIZE,
    restart_interval: int = RESTART_INTERVAL,
    report: BuildReport | None = None,
) -> BuildReport:
    """Write `<id>.dict`, `<id>.idx` and `<id>.json` into `destination`.

    Streams: payloads are spilled to a temporary file as they arrive, so the largest source (1.19 GB)
    is never resident. Only the per-entry index records are held, because the sources are not sorted
    by headword and the index has to be.
    """
    if tier not in TIERS:
        raise ValueError(f"unknown payload tier {tier!r}")
    destination.mkdir(parents=True, exist_ok=True)
    # The converter streams into this same report as it goes, so the fields it had to drop are
    # already recorded by the time the metadata is written.
    report = report if report is not None else BuildReport()

    with tempfile.TemporaryDirectory(prefix=f"acervo-dict-{dictionary_id}-") as scratch:
        spill_path = Path(scratch) / "payloads.bin"
        # (key bytes, alias keys, offset in the spill file, length) — the payload itself stays on
        # disk. For the largest corpus this list is the whole memory cost of the build.
        records: list[tuple[bytes, tuple[str, ...], int, int]] = []
        with open(spill_path, "wb") as spill:
            cursor = 0
            for entry in entries:
                if not entry.key or not entry.payload:
                    report.skipped += 1
                    continue
                spill.write(entry.payload)
                records.append((_sort_key(entry.key), tuple(entry.aliases), cursor, len(entry.payload)))
                cursor += len(entry.payload)

        records.sort(key=lambda record: record[0])
        merged = _merge_by_key(records)
        report.entry_count = len(merged)
        report.merged_entries = len(records) - len(merged)

        blob_path = destination / f"{dictionary_id}.dict"
        joiner = JOINERS[tier]
        with open(spill_path, "rb") as spill, open(blob_path, "wb") as blob:
            source = mmap.mmap(spill.fileno(), 0, access=mmap.ACCESS_READ) if records else None
            frame_lengths: list[int] = []
            payload_lengths: list[int] = []
            try:
                buffer: list[bytes] = []
                for _, _, spans in merged:
                    payload = joiner([source[offset:offset + length] for offset, length in spans])
                    payload_lengths.append(len(payload))
                    buffer.append(payload)
                    if len(buffer) >= frame_size:
                        frame_lengths.append(_write_frame(blob, buffer))
                        buffer = []
                if buffer:
                    frame_lengths.append(_write_frame(blob, buffer))
            finally:
                if source is not None:
                    source.close()

        report.frame_count = len(frame_lengths)
        report.blob_bytes = blob_path.stat().st_size

        keys = _collect_keys(merged)
        report.key_count = len(keys)
        index = _pack_index(
            tier=tier,
            entry_count=len(merged),
            frame_lengths=frame_lengths,
            payload_lengths=payload_lengths,
            keys=keys,
            frame_size=frame_size,
            restart_interval=restart_interval,
        )
        index_path = destination / f"{dictionary_id}.idx"
        index_path.write_bytes(index)
        report.index_bytes = len(index)

    _write_metadata(destination / f"{dictionary_id}.json", blob_path, index_path, metadata, report,
                    tier=tier, frame_size=frame_size, restart_interval=restart_interval)
    return report


def _write_frame(blob: io.BufferedWriter, payloads: list[bytes]) -> int:
    """One frame: the payloads concatenated, raw DEFLATE, no header of its own.

    Raw (`wbits=-15`) rather than zlib-wrapped so the frame carries no redundant 6 bytes and
    `fflate.inflateSync` reads it directly.
    """
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    frame = compressor.compress(b"".join(payloads)) + compressor.flush()
    blob.write(frame)
    return len(frame)


def _merge_by_key(
    records: Sequence[tuple[bytes, tuple[str, ...], int, int]],
) -> list[tuple[bytes, tuple[str, ...], list[tuple[int, int]]]]:
    """Fold consecutive records sharing a headword into one entry.

    A headword genuinely has more than one article in several sources — CC-CEDICT writes a separate
    line per reading, so simplified 行 arrives once for *háng* and once for *xíng* — and keeping only
    the first would have silently lost 3 % of that dictionary. The records are already sorted, so
    duplicates are adjacent and this stays a single pass with nothing extra resident.
    """
    merged: list[tuple[bytes, tuple[str, ...], list[tuple[int, int]]]] = []
    for key, aliases, offset, length in records:
        if merged and merged[-1][0] == key:
            previous_key, previous_aliases, spans = merged[-1]
            spans.append((offset, length))
            combined = previous_aliases + tuple(a for a in aliases if a not in previous_aliases)
            merged[-1] = (previous_key, combined, spans)
            continue
        merged.append((key, tuple(aliases), [(offset, length)]))
    return merged


def _join_fields(payloads: list[bytes]) -> bytes:
    """Each `fields` payload is a JSON array of articles, so merging is splicing the arrays."""
    if len(payloads) == 1:
        return payloads[0]
    bodies = [payload[1:-1] for payload in payloads]
    return b"[" + b",".join(bodies) + b"]"


JOINERS = {"fields": _join_fields, "html": b"".join}


def _collect_keys(
    merged: Sequence[tuple[bytes, tuple[str, ...], list[tuple[int, int]]]],
) -> list[tuple[bytes, int]]:
    """Every lookup key, sorted by UTF-8 bytes, each pointing at the entry it resolves to.

    A headword always wins a collision with an alias, and the first alias wins a collision with a
    later one, so the result does not depend on which entry happened to be read first.
    """
    seen: dict[bytes, int] = {}
    for index, (key, _, _) in enumerate(merged):
        seen.setdefault(key, index)
    for index, (key, aliases, _) in enumerate(merged):
        for alias in aliases:
            if alias:
                seen.setdefault(_sort_key(alias), index)
        generated = normalised_alias(key.decode("utf-8"))
        if generated:
            seen.setdefault(_sort_key(generated), index)
    return sorted(seen.items())


def _pack_index(
    *,
    tier: str,
    entry_count: int,
    frame_lengths: Sequence[int],
    payload_lengths: Sequence[int],
    keys: Sequence[tuple[bytes, int]],
    frame_size: int,
    restart_interval: int,
) -> bytes:
    """Header, then four varint sections in a fixed order.

    Section offsets are not stored: each section's length is in the header and they follow the header
    in order, so a reader that has parsed the header knows where everything starts.
    """
    frames = io.BytesIO()
    for length in frame_lengths:
        write_varint(frames, length)

    # Where each frame's run of payload lengths starts. Without this a reader would have to hold
    # every entry's length to locate one — about 2 MiB for the largest dictionary, which does not
    # survive ten dictionaries being installed at once. With it, a lookup range-reads one frame's
    # worth of varints, and what stays resident is a few hundred KiB per dictionary.
    payloads = io.BytesIO()
    frame_offsets = io.BytesIO()
    for position, length in enumerate(payload_lengths):
        if position % frame_size == 0:
            write_varint(frame_offsets, payloads.tell())
        write_varint(payloads, length)

    key_bytes = io.BytesIO()
    restarts = io.BytesIO()
    previous = b""
    for position, (key, entry_index) in enumerate(keys):
        if position % restart_interval == 0:
            write_varint(restarts, key_bytes.tell())
            shared = 0
        else:
            shared = _shared_prefix(previous, key)
        write_varint(key_bytes, shared)
        suffix = key[shared:]
        write_varint(key_bytes, len(suffix))
        key_bytes.write(suffix)
        write_varint(key_bytes, entry_index)
        previous = key

    header = io.BytesIO()
    header.write(MAGIC)
    header.write(bytes([FORMAT_VERSION, TIERS.index(tier)]))
    header.write(frame_size.to_bytes(2, "little"))
    header.write(restart_interval.to_bytes(2, "little"))
    for value in (entry_count, len(keys), frames.tell(), frame_offsets.tell(), payloads.tell(),
                  restarts.tell(), key_bytes.tell()):
        write_varint(header, value)
    return b"".join((header.getvalue(), frames.getvalue(), frame_offsets.getvalue(),
                     payloads.getvalue(), restarts.getvalue(), key_bytes.getvalue()))


def _shared_prefix(previous: bytes, current: bytes) -> int:
    limit = min(len(previous), len(current))
    shared = 0
    while shared < limit and previous[shared] == current[shared]:
        shared += 1
    return shared


def _write_metadata(path: Path, blob_path: Path, index_path: Path, metadata: dict,
                    report: BuildReport, *, tier: str, frame_size: int, restart_interval: int) -> None:
    """The third file: everything the interface needs without opening the other two.

    Licence and attribution are repeated here rather than only in the catalogue, because §9's
    obligation is to show them wherever an entry is rendered, and a rendered entry comes from the
    artifact.
    """
    document = {
        **metadata,
        "schemaVersion": FORMAT_VERSION,
        "tier": tier,
        "frameSize": frame_size,
        "restartInterval": restart_interval,
        "entryCount": report.entry_count,
        "keyCount": report.key_count,
        "frameCount": report.frame_count,
        "blobBytes": report.blob_bytes,
        "indexBytes": report.index_bytes,
        "mergedEntries": report.merged_entries,
        "droppedFields": sorted(report.dropped_fields),
        "unmappedPartsOfSpeech": sorted(report.unmapped_pos),
        "checksums": {
            blob_path.name: _sha256(blob_path),
            index_path.name: _sha256(index_path),
        },
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_artifact_entry(blob: bytes, index: bytes, word: str) -> bytes | None:
    """One lookup over an artifact held in memory: what the tests use to prove the format round-trips."""
    return _payload(parse_index(index), blob, word)


def _payload(layout: "IndexLayout", blob: bytes | mmap.mmap, word: str) -> bytes | None:
    entry = layout.find(word)
    if entry is None:
        return None
    frame_number, offset, length = entry
    start = layout.frame_starts[frame_number]
    frame = zlib.decompressobj(-15).decompress(blob[start:start + layout.frame_lengths[frame_number]])
    return frame[offset:offset + length]


class Artifact:
    """An installed artifact, opened once for the server's lookups.

    The index is parsed once and the blob is mapped rather than read, so a lookup decodes one frame
    and the process never holds a dictionary of a hundred megabytes. Reads only: safe across threads.
    """

    def __init__(self, blob_path: Path, index_path: Path) -> None:
        self.layout = parse_index(index_path.read_bytes())
        with open(blob_path, "rb") as handle:
            self._blob = (mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
                          if blob_path.stat().st_size else b"")

    def payload(self, word: str) -> bytes | None:
        return _payload(self.layout, self._blob, word)


@dataclass
class IndexLayout:
    frame_size: int
    restart_interval: int
    entry_count: int
    frame_lengths: list[int]
    frame_starts: list[int]
    payload_index_offsets: list[int]
    payloads: bytes
    restart_offsets: list[int]
    keys: bytes

    def find(self, word: str) -> tuple[int, int, int] | None:
        """Locate `word`, returning `(frame number, offset within the frame, payload length)`."""
        target = word.encode("utf-8")
        entry_index = self._lookup(target)
        if entry_index is None:
            import unicodedata

            folded = unicodedata.normalize("NFC", word).casefold().encode("utf-8")
            entry_index = self._lookup(folded) if folded != target else None
        if entry_index is None:
            return None
        frame_number = entry_index // self.frame_size
        cursor = self.payload_index_offsets[frame_number]
        offset = 0
        for position in range(frame_number * self.frame_size, entry_index + 1):
            length, cursor = read_varint(self.payloads, cursor)
            if position == entry_index:
                return frame_number, offset, length
            offset += length
        return None

    def _lookup(self, target: bytes) -> int | None:
        if not self.restart_offsets:
            return None
        low, high = 0, len(self.restart_offsets) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if self._restart_key(middle) <= target:
                low = middle
            else:
                high = middle - 1
        return self._scan(low, target)

    def _restart_key(self, restart: int) -> bytes:
        offset = self.restart_offsets[restart]
        _, offset = read_varint(self.keys, offset)          # shared prefix, always zero here
        length, offset = read_varint(self.keys, offset)
        return self.keys[offset:offset + length]

    def _scan(self, restart: int, target: bytes) -> int | None:
        offset = self.restart_offsets[restart]
        limit = (self.restart_offsets[restart + 1] if restart + 1 < len(self.restart_offsets)
                 else len(self.keys))
        previous = b""
        while offset < limit:
            shared, offset = read_varint(self.keys, offset)
            length, offset = read_varint(self.keys, offset)
            key = previous[:shared] + self.keys[offset:offset + length]
            offset += length
            entry_index, offset = read_varint(self.keys, offset)
            if key == target:
                return entry_index
            if key > target:
                return None
            previous = key
        return None


def parse_index(index: bytes) -> IndexLayout:
    if index[:4] != MAGIC:
        raise ValueError("not an Acervo dictionary index")
    version, tier = index[4], index[5]
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported index version {version}")
    frame_size = int.from_bytes(index[6:8], "little")
    restart_interval = int.from_bytes(index[8:10], "little")
    offset = 10
    values = []
    for _ in range(7):
        value, offset = read_varint(index, offset)
        values.append(value)
    (entry_count, _key_count, frames_len, frame_offsets_len, payloads_len,
     restarts_len, _keys_len) = values

    frame_lengths = list(_varints(index, offset, frames_len))
    offset += frames_len
    payload_index_offsets = list(_varints(index, offset, frame_offsets_len))
    offset += frame_offsets_len
    payloads = index[offset:offset + payloads_len]
    offset += payloads_len
    restart_offsets = list(_varints(index, offset, restarts_len))
    offset += restarts_len
    keys = index[offset:]

    frame_starts, running = [], 0
    for length in frame_lengths:
        frame_starts.append(running)
        running += length
    assert tier in (0, 1)
    return IndexLayout(frame_size, restart_interval, entry_count, frame_lengths, frame_starts,
                       payload_index_offsets, payloads, restart_offsets, keys)


def _varints(data: bytes, start: int, length: int) -> Iterator[int]:
    offset, end = start, start + length
    while offset < end:
        value, offset = read_varint(data, offset)
        yield value
