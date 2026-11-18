"""One converter per source *format family*, not per dictionary.

Ported from `experiments/external-dictionaries/sources.py`, which measured 98.7-100 % of entries
mapping with nothing invented across every format tried (§11.3). That code was written to be
measured rather than shipped, so it is reviewed here rather than copied: the tier is chosen by the
catalogue instead of a call-site flag, entries stream rather than accumulate, and the payload is the
render-only `Entry` of `model.py` rather than an `ArticleDraft`.

A source is field-structured or it is opaque. Field-structured formats get one of the small
converters below and the `fields` tier; everything else goes through PyGlossary to the `html` tier
with no per-source code at all, which is what keeps adding a dictionary to a catalogue row.

PyGlossary is deliberately *not* used for the field-structured formats, even though 5.4.2 has
readers for all of them. Every one of its plugins emits HTML — the wiktextract reader builds an lxml
tree writing `<div class="pos"><font color="green">`, the presentational markup §11.4 says has to be
restyled — and it yields one entry per JSONL line with no headword grouping, so `gratis` would
arrive as separate adjective and adverb entries. Routing kaikki through it would turn the one
load-bearing structured source into an opaque one.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import tarfile
import zipfile
from html import escape
from pathlib import Path
from typing import Callable, Iterator

from .catalogue import CatalogueEntry
from .container import BuildReport, SourceEntry
from .model import GENDERS, GRAMMAR_TAGS, REGISTER_TAGS, Entry, Example, Sense, resolve_pos

Converter = Callable[[Path, CatalogueEntry, BuildReport], Iterator[Entry]]


# --------------------------------------------------------------------------------- opening sources

def open_text(path: Path):
    """Sources arrive plain or gzipped; nothing else needs special handling to read line by line."""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "rt", encoding="utf-8")


def open_source_text(path: Path, row: CatalogueEntry):
    """Text for a line-oriented converter, whether the source arrives plain, gzipped or zipped.

    Which of those a dictionary uses is an accident of who publishes it — CC-CEDICT ships a `.gz`
    and CC-Canto ships the same line grammar inside a `.zip` — so the converter should not have to
    care, and the catalogue's `member` option is all that distinguishes them.
    """
    member = row.option("member")
    if member and path.suffix in {".zip", ".tgz", ".tar", ".xz", ".gz"} and path.suffixes[-2:] != [".txt", ".gz"]:
        return io.TextIOWrapper(archive_member(path, member), encoding="utf-8")
    return open_text(path)


def archive_member(path: Path, suffix: str) -> io.BufferedReader:
    """The one file inside a tarball or zip whose name ends in `suffix`."""
    if path.suffix in {".zip"}:
        archive = zipfile.ZipFile(path)
        name = next(item for item in archive.namelist() if item.endswith(suffix))
        return archive.open(name)
    archive = tarfile.open(path, "r:*")
    member = next(item for item in archive.getmembers() if item.name.endswith(suffix))
    handle = archive.extractfile(member)
    if handle is None:
        raise ValueError(f"{path.name} has no readable member ending in {suffix!r}")
    return handle


# ------------------------------------------------------------------------------------ wiktextract

#: Keys wiktextract emits that a render-only entry has nowhere to put. Recorded in the artifact
#: metadata rather than dropped silently, per the Stage 1 requirement to say what was lost.
WIKTEXTRACT_DROP = {
    "etymology_text", "etymology_templates", "etymology_number", "head_templates", "hyphenation",
    "hyphenations", "forms", "categories", "topics", "wikipedia", "redirects", "descendants",
    "derived", "related", "synonyms", "antonyms", "hypernyms", "hyponyms", "holonyms", "meronyms",
    "coordinate_terms", "proverbs", "abbreviations", "translations", "inflection_templates",
    "info_templates", "instances", "troponyms", "form_of", "alt_of", "senseid", "wikidata",
}
SENSE_DROP = {
    "links", "categories", "id", "topics", "wikipedia", "derived", "related", "synonyms",
    "antonyms", "hypernyms", "hyponyms", "coordinate_terms", "form_of", "alt_of", "senseid",
    "wikidata", "qualifier", "raw_glosses", "instances", "info_templates", "head_nr",
}


def _kaikki_groups(path: Path, lang_code: str | None) -> Iterator[list[dict]]:
    """Group raw wiktextract lines by headword, streaming.

    One JSONL line is one (word, part of speech) pair, so `gratis` arrives as separate adjective and
    adverb lines and a lookup wants both. The dumps are not sorted, but every occurrence of a word
    *is* contiguous — verified in the spike over a 119k-line sample with zero non-contiguous
    reappearances — so grouping adjacent runs is exact and keeps memory flat over a 1.19 GB file.
    """
    group: list[dict] = []
    current: str | None = None
    with open_text(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if lang_code and record.get("lang_code") != lang_code:
                continue
            word = record.get("word")
            if not word:
                continue
            if word != current:
                if group:
                    yield group
                group, current = [], word
            group.append(record)
    if group:
        yield group


def _ipa_of(record: dict) -> str | None:
    sounds = record.get("sounds") or []
    for sound in sounds:
        raw = sound.get("ipa")
        if raw and raw.startswith("/"):
            return raw
    for sound in sounds:
        if sound.get("ipa"):
            return sound["ipa"]
    return None


def _ipas_of(group: list[dict]) -> list[str]:
    """Every distinct transcription of a headword, phonemic (`/…/`) before phonetic (`[…]`)."""
    found: list[str] = []
    for record in group:
        for sound in record.get("sounds") or []:
            raw = (sound.get("ipa") or "").strip()
            if raw and raw not in found:
                found.append(raw)
    return sorted(found, key=lambda item: not item.startswith("/"))


#: The gender letters of a Wiktionary headword line (`asco m (plural ascos)`, `соба́ка • (sobáka) f anim`).
_HEAD_GENDER = {"m": "masculine", "f": "feminine", "n": "neuter", "c": "common"}
_PARENTHESISED = re.compile(r"\([^()]*\)")
_NOUN_POS = {"noun", "name"}


def _genders_of(group: list[dict]) -> list[str]:
    """A headword's genders, from its noun records.

    wiktextract normalises gender into `tags`, on the record or on each sense, for most editions and
    languages; where it does not (Russian in the English edition tags 5 % of nouns), the headword
    line still shows it, so a record with no gender tag is read from its `head_templates` expansion:
    parenthesised parts removed, the headword's own words skipped, and the letters left mapped.
    """
    genders: list[str] = []
    for record in group:
        if record.get("pos") not in _NOUN_POS:
            continue
        tags = list(record.get("tags") or [])
        for sense in record.get("senses") or []:
            tags.extend(sense.get("tags") or [])
        found = [tag for tag in tags if tag in GENDERS]
        if not found:
            skip = len(str(record.get("word") or "").split())
            for template in record.get("head_templates") or []:
                line = str(template.get("expansion") or "")
                while _PARENTHESISED.search(line):
                    line = _PARENTHESISED.sub(" ", line)
                tokens = re.split(r"[\s,/]+", line.strip())[skip:]
                found.extend(_HEAD_GENDER[token] for token in tokens if token in _HEAD_GENDER)
        for gender in found:
            if gender not in genders:
                genders.append(gender)
    return genders


def convert_wiktextract(path: Path, row: CatalogueEntry, report: BuildReport) -> Iterator[Entry]:
    """The only load-bearing converter: ~20 Wiktionary editions and hundreds of languages.

    `definitionLang` is the honest part. The English edition's glosses are English even when the
    headwords are Spanish, so they are written as English definitions rather than pretending to be
    Spanish ones. The catalogue's `targetLang` is what says which.
    """
    language = row.sourceLang
    definition_lang = row.targetLang
    lang_code = row.option("langCode")
    for group in _kaikki_groups(path, lang_code):
        head = group[0]
        for record in group:
            report.dropped_fields |= set(record) & WIKTEXTRACT_DROP

        pos, pos_label = resolve_pos(head.get("pos"))
        if pos_label and not pos:
            report.unmapped_pos.add(pos_label)

        senses: list[Sense] = []
        register: str | None = None
        for record in group:
            for raw in record.get("senses") or []:
                report.dropped_fields |= set(raw) & SENSE_DROP
                glosses = raw.get("glosses") or []
                if not glosses:
                    continue
                tags = [tag.lower() for tag in (raw.get("tags") or [])]
                register = register or next((REGISTER_TAGS[tag] for tag in tags if tag in REGISTER_TAGS), None)
                sense = Sense(
                    definition=glosses[0],
                    domain=next((tag for tag in tags if tag in GRAMMAR_TAGS), None),
                )
                for sample in (raw.get("examples") or [])[:3]:
                    text = sample.get("text")
                    if not text:
                        continue
                    english = sample.get("english")
                    sense.examples.append(Example(
                        text=text, textLang=language,
                        translation=english, translationLang="en" if english else None,
                    ))
                senses.append(sense)

        if not senses:
            report.skipped += 1
            continue
        ipa = _ipa_of(head)
        ipas = _ipas_of(group)
        if ipa:
            ipas = [ipa, *(item for item in ipas if item != ipa)]
        yield Entry(
            headword=head["word"], lemma=head["word"], language=language,
            definitionLang=definition_lang, senses=senses,
            ipa=ipa, ipas=ipas if ipas != ([ipa] if ipa else []) else [],
            pos=pos, posLabel=pos_label, register=register, genders=_genders_of(group),
        )


# --------------------------------------------------------------------------------------- CC-CEDICT

#: CC-CEDICT is `traditional simplified [pinyin] /gloss/gloss/`. CC-Canto adds `{jyutping}` in
#: front of the glosses, which is the reading that actually matters for Cantonese — so it is
#: optional here and preferred when present, rather than being a second converter.
CEDICT_LINE = re.compile(
    r"^(\S+)\s+(\S+)\s+\[([^\]]*)\]\s+(?:\{([^}]*)\}\s+)?/(.*)/\s*$")


def convert_cc_cedict(path: Path, row: CatalogueEntry, report: BuildReport) -> Iterator[Entry]:
    """Traditional, simplified, `[pinyin]`, `/gloss/gloss/` — one line, fixed grammar.

    The traditional form becomes an alias rather than a second entry, so looking up either spelling
    reaches the same article. CC-CEDICT carries no part of speech at all, so the entry carries none
    either: the spike's first run invented `noun` here and §11.3 removed it.
    """
    with open_source_text(path, row) as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            match = CEDICT_LINE.match(line.strip())
            if not match:
                continue
            traditional, simplified, pinyin, jyutping, body = match.groups()
            glosses = [part for part in body.split("/") if part]
            if not glosses:
                report.skipped += 1
                continue
            yield Entry(
                headword=simplified, lemma=simplified, language=row.sourceLang,
                reading=jyutping or pinyin, definitionLang=row.targetLang,
                senses=[Sense(definition=text) for text in glosses],
                aliases=[traditional] if traditional != simplified else [],
            )


# ------------------------------------------------------------------------ jmdict-simplified JSON

JMDICT_POS = {
    "n": "noun", "v1": "verb", "v5u": "verb", "v5k": "verb", "v5s": "verb", "v5t": "verb",
    "v5n": "verb", "v5b": "verb", "v5m": "verb", "v5r": "verb", "v5g": "verb", "vs": "verb",
    "vk": "verb", "vi": "verb", "vt": "verb", "adj-i": "adj", "adj-na": "adj", "adj-no": "adj",
    "adv": "adv", "exp": "expression", "int": "expression",
}
JMDICT_DROP = {"priority", "common", "appliesToKanji", "related", "antonym", "field",
               "dialect", "languageSource"}


def convert_jmdict(path: Path, row: CatalogueEntry, report: BuildReport) -> Iterator[Entry]:
    """jmdict-simplified: sense-tagged, part-of-speech-tagged JSON.

    Read whole rather than streamed — it is ~100k entries and tens of MB, not a gigabyte — and the
    kana reading becomes `reading` only when the headword is kanji, because a kana headword is
    already its own reading.
    """
    member = row.option("member", ".json")
    with archive_member(path, member) if path.suffix in {".tgz", ".gz", ".tar", ".xz", ".zip"} else open(path, "rb") as handle:
        document = json.load(handle)
    for word in document.get("words", []):
        kanji = [item["text"] for item in word.get("kanji", []) if item.get("text")]
        kana = [item["text"] for item in word.get("kana", []) if item.get("text")]
        headword = kanji[0] if kanji else (kana[0] if kana else "")
        if not headword:
            report.skipped += 1
            continue
        report.dropped_fields |= JMDICT_DROP & _jmdict_keys(word)

        senses: list[Sense] = []
        labels: list[str] = []
        for sense in word.get("sense", []):
            glosses = [item["text"] for item in sense.get("gloss", []) if item.get("text")]
            if not glosses:
                continue
            labels.extend(sense.get("partOfSpeech", []))
            senses.append(Sense(definition="; ".join(glosses)))
        if not senses:
            report.skipped += 1
            continue

        pos = next((JMDICT_POS[label] for label in labels if label in JMDICT_POS), None)
        if labels and not pos:
            report.unmapped_pos |= set(labels)
        yield Entry(
            headword=headword, lemma=headword, language=row.sourceLang,
            definitionLang=row.targetLang, senses=senses,
            reading=kana[0] if kana and kanji else None,
            pos=pos, posLabel=labels[0] if labels else None,
            aliases=[form for form in kana + kanji if form != headword],
        )


def _jmdict_keys(word: dict) -> set[str]:
    keys = set(word)
    for sense in word.get("sense", []):
        keys |= set(sense)
    return keys


# --------------------------------------------------------------------------------- FreeDict TEI P5

TEI_NS = "{http://www.tei-c.org/ns/1.0}"
TEI_POS = {"n": "noun", "pn": "noun", "v": "verb", "adj": "adj", "adv": "adv",
           "int": "expression", "interjection": "expression",
           "phraseologicalUnit": "phrase", "proverb": "phrase", "idiom": "idiom"}


def convert_freedict_tei(path: Path, row: CatalogueEntry, report: BuildReport) -> Iterator[Entry]:
    """Semantic XML, streamed with `iterparse` so a large dictionary stays flat in memory."""
    import xml.etree.ElementTree as ET

    handle = archive_member(path, row.option("member", ".tei")) if path.suffix != ".tei" else open(path, "rb")
    with handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != f"{TEI_NS}entry":
                continue
            orth = element.find(f"{TEI_NS}form/{TEI_NS}orth")
            headword = (orth.text or "").strip() if orth is not None else ""
            pos_element = element.find(f"{TEI_NS}gramGrp/{TEI_NS}pos")
            source_label = (pos_element.text or "").strip() if pos_element is not None else ""
            quotes = [(quote.text or "").strip() for quote in element.iter(f"{TEI_NS}quote")
                      if (quote.text or "").strip()]
            element.clear()
            if not headword or not quotes:
                report.skipped += 1
                continue
            pos, pos_label = resolve_pos(source_label)
            if pos_label and not pos:
                report.unmapped_pos.add(pos_label)
            yield Entry(
                headword=headword, lemma=headword, language=row.sourceLang,
                definitionLang=row.targetLang, pos=pos, posLabel=pos_label,
                senses=[Sense(definition=text) for text in quotes],
            )


# ------------------------------------------------------------------------------------------ moedict

def convert_moedict(path: Path, row: CatalogueEntry, report: BuildReport) -> Iterator[Entry]:
    """MOE 重編國語辭典 — the monolingual Chinese answer, in traditional characters.

    Its shape is `heteronyms[] -> definitions[]`, where a heteronym is one reading of the character
    string. Readings are joined rather than split into separate entries: the reader looks a word up
    by its characters, and which pronunciation is meant is something the article shows.
    """
    document = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else json.load(archive_member(path, ".json"))
    for record in document:
        headword = (record.get("title") or "").strip()
        if not headword:
            report.skipped += 1
            continue
        senses: list[Sense] = []
        readings: list[str] = []
        labels: list[str] = []
        for heteronym in record.get("heteronyms") or []:
            reading = heteronym.get("bopomofo2") or heteronym.get("pinyin") or heteronym.get("bopomofo")
            if reading:
                readings.append(reading)
            for definition in heteronym.get("definitions") or []:
                text = (definition.get("def") or "").strip()
                if not text:
                    continue
                if definition.get("type"):
                    labels.append(definition["type"])
                sense = Sense(definition=text, domain=definition.get("type"))
                for quote in (definition.get("example") or [])[:3]:
                    sense.examples.append(Example(text=quote, textLang=row.sourceLang))
                senses.append(sense)
        if not senses:
            report.skipped += 1
            continue
        pos, pos_label = resolve_pos(labels[0] if labels else None)
        if pos_label and not pos:
            report.unmapped_pos.add(pos_label)
        yield Entry(
            headword=headword, lemma=headword, language=row.sourceLang,
            definitionLang=row.targetLang, senses=senses,
            reading=readings[0] if readings else None, pos=pos, posLabel=pos_label,
        )


# ------------------------------------------------------------------- everything opaque, via PyGlossary

#: Inline colours that would fight Acervo's theme in both light and dark (§11.4). The structure is
#: kept and restyled from class names where a source has them; only the presentation is stripped.
FONT_TAG = re.compile(r"</?font[^>]*>", re.IGNORECASE)
STYLE_ATTRIBUTE = re.compile(r'\s(?:style|color|bgcolor|face|size)="[^"]*"', re.IGNORECASE)


def restyle(markup: str) -> str:
    """Strip presentation, keep structure. Not sanitising — that is the renderer's job in Stage 3."""
    return STYLE_ATTRIBUTE.sub("", FONT_TAG.sub("", markup)).strip()


def convert_pyglossary(path: Path, row: CatalogueEntry, report: BuildReport) -> Iterator[Entry]:
    """The long tail: StarDict, slob, MDict, DSL, Zim, XDXF, Yomitan zips, and the rest.

    This is the generalisation worth having — a new dictionary in any of these formats is a
    catalogue row and no new code. The payload arrives as markup, so there is nothing to map and the
    tier is `html`; §11.4 measured this path as real but confirmed that extracting fields back out
    of presentational markup is unbounded maintenance for a source that renders fine as it is.
    """
    from pyglossary.glossary_v2 import Glossary

    Glossary.init()
    glossary = Glossary()
    source = _pyglossary_source(path, row)
    plugin = row.option("pyglossaryFormat")
    opened = (glossary.directRead(str(source), formatName=plugin) if plugin
              else glossary.directRead(str(source)))
    if not opened:
        raise RuntimeError(
            f"PyGlossary could not read {source.name}. It disables plugins silently when lxml is "
            f"missing — check that requirements/dictionaries.txt is installed."
        )
    for item in glossary:
        words = item.l_word
        if not words or not item.defi:
            report.skipped += 1
            continue
        yield Entry(
            headword=words[0], lemma=words[0], language=row.sourceLang,
            definitionLang=row.targetLang, aliases=list(words[1:]),
            senses=[Sense(definition=restyle(item.defi))],
        )


def _pyglossary_source(path: Path, row: CatalogueEntry) -> Path:
    """PyGlossary reads a file, so an archived source is unpacked beside its download first."""
    member = row.option("member")
    if not member:
        return path
    unpacked = path.parent / f"{path.name}.unpacked"
    if not unpacked.exists():
        unpacked.mkdir(parents=True)
        if path.suffix == ".zip":
            zipfile.ZipFile(path).extractall(unpacked)
        else:
            tarfile.open(path, "r:*").extractall(unpacked, filter="data")
    return next(unpacked.rglob(member))


CONVERTERS: dict[str, Converter] = {
    "wiktextract": convert_wiktextract,
    "cc-cedict": convert_cc_cedict,
    "jmdict": convert_jmdict,
    "freedict-tei": convert_freedict_tei,
    "moedict": convert_moedict,
    "pyglossary": convert_pyglossary,
}


def source_entries(path: Path, row: CatalogueEntry, report: BuildReport) -> Iterator[SourceEntry]:
    """Run the converter the catalogue names, and pack what it yields.

    The tier decides what a payload *is*: structured JSON for a field-structured source, a display
    fragment for an opaque one. §11.0a measured the two within 7 % once block-compressed, so the
    choice is about rendering rather than bytes.
    """
    converter = CONVERTERS.get(row.format or "")
    if converter is None:
        raise KeyError(f"{row.id}: no converter for format {row.format!r}")
    for entry in converter(path, row, report):
        payload = entry.payload() if row.tier == "fields" else _html_payload(entry)
        yield SourceEntry(key=entry.headword, payload=payload, aliases=tuple(entry.aliases))


def _html_payload(entry: Entry) -> bytes:
    """A display fragment for the `html` tier, restyled into Acervo's own markup."""
    parts = [f"<h1>{escape(entry.headword)}</h1>"]
    if entry.reading:
        parts.append(f'<p class="reading">{escape(entry.reading)}</p>')
    if entry.ipa:
        parts.append(f'<p class="ipa">{escape(entry.ipa)}</p>')
    if entry.posLabel:
        parts.append(f'<p class="pos">{escape(entry.posLabel)}</p>')
    body = "".join(f"<li>{sense.definition}</li>" for sense in entry.senses)
    parts.append(f"<ol>{body}</ol>")
    return "".join(parts).encode("utf-8")
