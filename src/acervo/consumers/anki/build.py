"""The vocabulary as Anki notes: a manifest, and the files it names.

Three notes come from one word (`model.py` says what each tests):

* **one meaning note per example**, which asks you to recognise the meaning in that sentence;
* **one meaning note per sense**, which asks you to produce the word from its meaning and picture,
  and to recognise it bare when the sense has no example to show it in;
* **one word note**, which asks you to hear the word, made only when the headword has a recording.

**Examples are shown in order of trust**: the owner's own sentences first (drawn from an
attestation, or typed), then generated ones, then the dictionaries', and clips last. A clip is real
speech but the noisiest text — a subtitle cut mid-thought — so it is the sentence a sense is shown
in only when there is nothing else.

**The manifest's order is the order Anki introduces new cards in**, so it is arranged in rounds: every
word's first note, then every word's second, and so on. A word's notes run first example of each
sense, then each sense's own note, then the remaining examples, then the word's. On a first push
of a thousand words this keeps one word's seven cards from arriving on the same morning; Anki only
spaces siblings within one note, and these are different notes.

This reads the wire-shaped graph and nothing else, like every enrichment: it can be fed a
`pull_graph()` payload or a saved one.
"""

from __future__ import annotations

import html
import os
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from acervo.article import ArticleView, build_articles, live

from .naming import slugify_filename
from .progress import Progress

# A word put away, or not yet taken in, has no cards.
CARD_STATUSES = ("active", "learned")
DEFAULT_DECK = "{language}::Vocabulary"
LANGUAGE_NAMES = {
    "es": "Spanish", "en": "English", "ru": "Russian", "zh": "Chinese", "pt": "Portuguese",
    "fr": "French", "de": "German", "it": "Italian", "ja": "Japanese", "ko": "Korean",
}

# Lower is shown first. The owner's own words, then generated, then dictionaries', then clips.
ORIGIN_RANK = {"attestation": 0, "manual": 0, "llm": 1, "tatoeba": 2, "wiktionary": 2, "subtitle": 3}
SOURCE_TAGS = {
    "attestation": ("you", "Your sentence"),
    "manual": ("you", "Your sentence"),
    "llm": ("made", "Example"),
    "tatoeba": ("made", "Tatoeba"),
    "wiktionary": ("made", "Wiktionary"),
    "subtitle": ("clip", "Clip"),
}
GENDERS = {"masculine": "m", "feminine": "f", "common": "c", "neuter": "n"}
# The article a noun's headword is written with, shown quieter than the word itself.
ARTICLES = {
    "es": ("el", "la", "los", "las"),
    "pt": ("o", "a", "os", "as"),
    "it": ("il", "lo", "la", "i", "gli", "le"),
    "fr": ("le", "la", "les"),
    "de": ("der", "die", "das"),
}


@dataclass
class BuiltManifest:
    """A manifest's notes, and each media file it names: `media/<name>` → the file it is made from."""

    notes: list[dict[str, Any]] = field(default_factory=list)
    media: dict[str, Path] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def manifest(self) -> dict[str, Any]:
        return {"schema_version": 2, "notes": self.notes}


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def marked(text: str, form: str | None, replacement: str | None = None) -> tuple[str, bool]:
    """`text` as HTML with the first occurrence of `form` wrapped in <mark>, or replaced by
    `replacement` (already HTML). Case is matched exactly first and then loosely; a form that does
    not occur leaves the text plain, and says so."""
    if form:
        start = text.find(form)
        if start < 0:
            found = re.search(re.escape(form), text, flags=re.IGNORECASE)
            start = found.start() if found else -1
        if start >= 0:
            end = start + len(form)
            middle = replacement if replacement is not None else f"<mark>{_escape(text[start:end])}</mark>"
            return _escape(text[:start]) + middle + _escape(text[end:]), True
    return _escape(text), False


def split_article(lexeme: dict[str, Any]) -> tuple[str, str]:
    """A noun's article and the word, so the card can set the article quieter. Anything else, and a
    noun written without one, is all word."""
    headword = str(lexeme.get("headword") or "")
    if lexeme.get("pos") == "noun":
        language = str(lexeme.get("language") or "").split("-")[0]
        first, _, rest = headword.partition(" ")
        if rest and first.casefold() in ARTICLES.get(language, ()):
            return first, rest
    return "", headword


def grammar_of(lexeme: dict[str, Any]) -> str:
    parts = [str(lexeme.get("pos") or "")]
    if lexeme.get("gender") in GENDERS:
        parts.append(GENDERS[lexeme["gender"]])
    if lexeme.get("register") not in (None, "", "neutral"):
        parts.append(str(lexeme["register"]))
    return " · ".join(part for part in parts if part)


def glosses_of(sense: dict[str, Any], gloss_langs: list[str]) -> tuple[str, str]:
    """The first gloss language's terms, and every other language's after them."""
    glosses = [gloss for gloss in sense.get("glosses") or [] if gloss.get("terms")]
    if not glosses:
        return "", ""
    rank = {lang: index for index, lang in enumerate(gloss_langs)}
    glosses.sort(key=lambda gloss: rank.get(gloss.get("lang"), len(rank)))
    first, *rest = glosses
    return (", ".join(first["terms"]),
            " · ".join(", ".join(gloss["terms"]) for gloss in rest))


def by_trust(examples: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        examples,
        key=lambda example: (ORIGIN_RANK.get(example.get("origin"), 2),
                             example.get("createdAt") or "", example.get("id") or ""),
    )


def _timestamp(seconds: Any) -> str:
    total = int(float(seconds or 0))
    return f"{total // 60}:{total % 60:02d}"


class _Graph:
    """Lookups over the parts of the graph the notes draw on."""

    def __init__(self, changes: dict[str, list[dict]]):
        self.senses = {record["id"]: record for record in live(changes.get("senses", []))}
        self.attestations = {record["id"]: record for record in live(changes.get("attestations", []))}
        self.pictures: dict[str, dict] = {}
        for record in live(changes.get("imagePrompts", [])):
            if record.get("senseId") and record.get("imageRef") and not record.get("suppressed"):
                held = self.pictures.get(record["senseId"])
                if held is None or (record.get("editedAt") or "") > (held.get("editedAt") or ""):
                    self.pictures[record["senseId"]] = record
        self.recordings = {
            (record.get("targetKind"), record.get("targetId")): record
            for record in live(changes.get("pronunciations", []))
            if record.get("audioRef")
        }
        self.topics = {record["id"]: record for record in live(changes.get("topics", []))}

    def recording(self, kind: str, identifier: str, says: str) -> dict | None:
        """A field's recording while it still says what the field says; a stale one is not played."""
        record = self.recordings.get((kind, identifier))
        return record if record is not None and record.get("text") == says else None


class _Media:
    def __init__(self, root: Path | None, built: BuiltManifest):
        self.root = root
        self.built = built

    def add(self, reference: str | None) -> str | None:
        """The payload path for a stored file, or None when there is nothing to send."""
        if not reference or self.root is None:
            return None
        source = (self.root / reference).resolve()
        if not source.is_relative_to(self.root.resolve()) or not source.is_file():
            self.built.missing.append(reference)
            return None
        path = f"media/{source.name}"
        self.built.media[path] = source
        return path


def build(
    changes: dict[str, list[dict]],
    *,
    languages: Iterable[str] | None = None,
    media_root: Path | None = None,
    statuses: Iterable[str] = CARD_STATUSES,
    deck: str = DEFAULT_DECK,
) -> BuiltManifest:
    """Every note for these languages' words (all of them by default), in the order new cards
    should be introduced. Each language is its own deck."""
    graph = _Graph(changes)
    built = BuiltManifest()
    media = _Media(media_root, built)
    wanted = set(statuses)
    chosen = set(languages) if languages else None
    articles = [
        article for article in build_articles(changes)
        if article.lexeme.get("status") in wanted and (chosen is None or article.language in chosen)
    ]
    articles.sort(key=lambda article: (article.lexeme.get("createdAt") or "", article.id))
    rounds = [_notes_of(article, graph, media, deck) for article in articles]
    for index in range(max((len(notes) for notes in rounds), default=0)):
        built.notes.extend(notes[index] for notes in rounds if index < len(notes))
    return built


def _deck_for(article: ArticleView, deck: str) -> str:
    vocabulary = article.vocabulary or {}
    name = vocabulary.get("displayName") or LANGUAGE_NAMES.get(article.language.split("-")[0], article.language)
    return deck.format(language=name)


def _tags(article: ArticleView, graph: _Graph, note: str) -> list[str]:
    tags = {f"acervo::note::{note}"}
    for topic_id in article.lexeme.get("topicIds") or []:
        topic = graph.topics.get(topic_id)
        if topic is not None:
            tags.add(f"acervo::topic::{slugify_filename(topic.get('name') or '') or topic_id}")
    return sorted(tags)


def _notes_of(article: ArticleView, graph: _Graph, media: _Media, deck: str) -> list[dict[str, Any]]:
    lexeme = article.lexeme
    gloss_langs = article.gloss_langs
    deck_name = _deck_for(article, deck)
    article_word, bare = split_article(lexeme)
    headword_audio = media.add(
        (graph.recording("lexeme", article.id, lexeme.get("headword") or "") or {}).get("audioRef"))

    head = {
        "Language": _escape(article.language),
        "Article": _escape(article_word),
        "Headword": _escape(bare),
        "Reading": _escape(lexeme.get("reading")),
        "IPA": _escape(lexeme.get("ipa")),
        "Grammar": _escape(grammar_of(lexeme)),
    }
    head_media = {"HeadwordAudio": headword_audio} if headword_audio else {}

    senses = [graph.senses[view.id] for view in article.senses if view.id in graph.senses]
    pictures = {sense["id"]: media.add((graph.pictures.get(sense["id"]) or {}).get("imageRef"))
                for sense in senses}

    def chips(current: str) -> str:
        if len(senses) < 2:
            return ""
        return '<div class="srow">' + "".join(
            f'<span class="schip{" on" if sense["id"] == current else ""}"><span class="n">{number}</span>'
            f'{_escape(" ".join(filter(None, [sense.get("emoji"), glosses_of(sense, gloss_langs)[0]])))}</span>'
            for number, sense in enumerate(senses, start=1)
        ) + "</div>"

    first: list[dict] = []
    own: list[dict] = []
    later: list[dict] = []
    for number, (view, sense) in enumerate(zip(article.senses, senses), start=1):
        gloss, gloss_more = glosses_of(sense, gloss_langs)
        definition_audio = media.add(
            (graph.recording("sense", sense["id"], sense.get("definition") or "") or {}).get("audioRef"))
        meaning = {
            **head,
            "Gloss": _escape(gloss),
            "GlossMore": _escape(gloss_more),
            "Domain": _escape(" ".join(filter(None, [sense.get("emoji"), sense.get("domain")]))),
            "SenseLabel": f"sense {number} of {len(senses)}" if len(senses) > 1 else "",
            "Definition": _escape(sense.get("definition")),
            "Senses": chips(sense["id"]),
        }
        meaning_media = {**head_media}
        if definition_audio:
            meaning_media["DefinitionAudio"] = definition_audio
        if pictures[sense["id"]]:
            meaning_media["Picture"] = pictures[sense["id"]]

        examples = by_trust(view.examples)
        shown = [_sentence(example, article, graph, media) for example in examples]
        for index, (example, sentence) in enumerate(zip(examples, shown)):
            fields, sentence_media = sentence
            note = {
                "kind": "meaning", "note_id": example["id"], "lexeme_id": article.id,
                "sense_id": sense["id"], "deck": deck_name, "tags": _tags(article, graph, "example"),
                "fields": {**meaning, **fields, "Recognise": "y"},
                "media": {**meaning_media, **sentence_media},
            }
            (first if index == 0 else later).append(note)

        best_fields, best_media = shown[0] if shown else ({}, {})
        cloze = _cloze(examples[0], article) if examples else ""
        own.append({
            "kind": "meaning", "note_id": sense["id"], "lexeme_id": article.id,
            "sense_id": sense["id"], "deck": deck_name, "tags": _tags(article, graph, "sense"),
            "fields": {**meaning, **best_fields, "Cloze": cloze, "Produce": "y",
                       "Recognise": "" if examples else "y"},
            "media": {**meaning_media, **best_media},
        })

    notes = [*first, *own, *later]
    if headword_audio:
        notes.append({
            "kind": "word", "note_id": article.id, "lexeme_id": article.id, "deck": deck_name,
            "tags": _tags(article, graph, "word"),
            "fields": {**head, "Glosses": _escape(_summary(lexeme, senses, gloss_langs)),
                       "Senses": _sense_list(senses, pictures, gloss_langs),
                       "Note": "<br>".join(_escape(text) for text in lexeme.get("notes") or [])},
            "media": head_media,
        })
    return notes


def _sentence(
    example: dict[str, Any], article: ArticleView, graph: _Graph, media: _Media
) -> tuple[dict[str, str], dict[str, str]]:
    """An example's sentence, translation and provenance as meaning-note fields."""
    text = str(example.get("text") or "")
    sentence, _ = marked(text, example.get("matchedForm") or article.lemma)
    translation, _ = marked(str(example.get("translation") or ""), example.get("matchedTranslationForm"))
    style, label = SOURCE_TAGS.get(example.get("origin"), ("made", "Example"))
    where = ""
    if example.get("origin") == "subtitle" and example.get("videoRef"):
        where = " · ".join(filter(None, [example.get("videoChannel"), _timestamp(example.get("videoStart"))]))
    elif example.get("sourceAttestationId"):
        where = (graph.attestations.get(example["sourceAttestationId"]) or {}).get("sourceTitle") or ""
    fields = {
        "Sentence": sentence,
        "Translation": translation,
        "Source": f'<span class="tag {style}">{label}</span>' + (f" {_escape(where)}" if where else ""),
        "Note": _escape(example.get("note")),
    }
    audio = media.add((graph.recording("example", example["id"], text) or {}).get("audioRef"))
    return fields, ({"SentenceAudio": audio} if audio else {})


def _cloze(example: dict[str, Any], article: ArticleView) -> str:
    """The sentence with the word cut out, or nothing when the word cannot be found in it."""
    text, found = marked(str(example.get("text") or ""), example.get("matchedForm") or article.lemma,
                         replacement='<span class="gap"></span>')
    return text if found else ""


def _summary(lexeme: dict[str, Any], senses: list[dict], gloss_langs: list[str]) -> str:
    if lexeme.get("shortGloss"):
        return str(lexeme["shortGloss"])
    firsts = [glosses_of(sense, gloss_langs)[0].split(", ")[0] for sense in senses]
    return " · ".join(term for term in firsts if term)


def _sense_list(senses: list[dict], pictures: dict[str, str | None], gloss_langs: list[str]) -> str:
    items = []
    for sense in senses:
        picture = pictures.get(sense["id"])
        thumb = (f'<img src="{html.escape(picture)}" alt="">' if picture
                 else _escape(sense.get("emoji")))
        items.append(
            f'<div class="sitem"><div class="thumb">{thumb}</div><div>'
            f'<b>{_escape(glosses_of(sense, gloss_langs)[0])}</b>'
            f'<span>{_escape(sense.get("definition"))}</span></div></div>'
        )
    return '<div class="slist">' + "".join(items) + "</div>"


PICTURES = {".webp": "WEBP", ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
# Fewer pictures than this are scaled in the calling process: starting a pool costs more than it saves.
POOLED = 16


def write_payload(built: BuiltManifest, output: Path, *, picture_size: int | None = 768,
                  progress: Progress | None = None, workers: int | None = None) -> Path:
    """Write `manifest.json` and its media under `output`, pictures scaled down to `picture_size`
    pixels on the long side (None keeps the master). Returns the manifest's path.

    `output` may be kept from one push to the next, and the server keeps it: **a file already there
    is not made again**, and a file the manifest no longer names is removed. A master's name carries
    a digest of its bytes, so the name alone says whether what is there is still right, and nothing
    is ever invalidated. Each file is written under a temporary name and renamed into place, so an
    interrupted push never leaves a half-written file to be taken for a finished one.

    Scaling is most of a first push — thousands of pictures, each re-encoded — so a large batch runs
    on every core but one, leaving that one to the server on the same machine. The pool is started
    fresh (`spawn`), because forking a server process that has threads is not safe."""
    import json
    import multiprocessing

    progress = progress or Progress()
    media = output / "media"
    media.mkdir(parents=True, exist_ok=True)
    wanted = {output / relative for relative in built.media}
    for stale in media.iterdir():
        if stale.is_file() and stale not in wanted:
            stale.unlink()
    pictures = []
    for relative, source in built.media.items():
        destination = output / relative
        if destination.exists():
            continue
        if picture_size and source.suffix.lower() in PICTURES:
            pictures.append((source, destination, picture_size))
        else:
            _copied(source, destination)
    counter = progress.count(f"Shrinking pictures to {picture_size} px", len(pictures))
    workers = workers or max(1, (os.cpu_count() or 1) - 1)
    if workers == 1 or len(pictures) < POOLED:
        for picture in pictures:
            _scaled(picture)
            counter.step()
    else:
        with ProcessPoolExecutor(max_workers=workers,
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            for _ in pool.map(_scaled, pictures, chunksize=4):
                counter.step()
    path = output / "manifest.json"
    path.write_text(json.dumps(built.manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _partial(destination: Path) -> Path:
    return destination.with_name(f".partial-{destination.name}")


def _copied(source: Path, destination: Path) -> None:
    partial = _partial(destination)
    shutil.copy2(source, partial)
    os.replace(partial, destination)


def _scaled(picture: tuple[Path, Path, int]) -> None:
    from PIL import Image

    source, destination, size = picture
    with Image.open(source) as image:
        if max(image.size) <= size:
            _copied(source, destination)
            return
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        suffix = destination.suffix.lower()
        options = {"method": 6} if suffix == ".webp" else {}
        partial = _partial(destination)
        image.save(partial, format=PICTURES[suffix], quality=82, **options)
    os.replace(partial, destination)
