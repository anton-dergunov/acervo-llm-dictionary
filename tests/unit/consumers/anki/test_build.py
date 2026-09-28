"""The vocabulary as Anki notes, from one real word with three senses (`fixtures/obra-graph.json`)."""

import io
import json
from pathlib import Path

import pytest
from anki.collection import Collection
from PIL import Image

from acervo.consumers.anki.build import BuiltManifest, build, marked, split_article, write_payload
from acervo.consumers.anki.cli import main
from acervo.consumers.anki.manifest import SyncManifest
from acervo.consumers.anki.progress import Progress
from acervo.consumers.anki.model import create_notetypes
from acervo.consumers.anki.robot import AnkiRobot, RobotSettings

FIXTURE = Path(__file__).parent / "fixtures" / "obra-graph.json"
TEMPLATES = Path(__file__).resolve().parents[4] / "templates"
OBRA = "3vu6u4sqccfs6fl"


@pytest.fixture
def graph() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def media_root(tmp_path, graph) -> Path:
    """The files the graph names, as the server's media directory would hold them."""
    root = tmp_path / "media-root"
    for record in graph["imagePrompts"]:
        path = root / record["imageRef"]
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1024, 1024), (40, 90, 80)).save(path, format="WEBP")
    for record in graph["pronunciations"]:
        path = root / record["audioRef"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ID3-" + record["id"].encode())
    return root


def by_id(built) -> dict:
    return {note["note_id"]: note for note in built.notes}


def test_every_example_sense_and_heard_word_is_a_note_in_rounds(graph, media_root):
    built = build(graph, media_root=media_root)
    # Round one is each sense's first sentence; then each sense's own note; then the rest; then the
    # word. Among the theatre sense's two sentences the generated one comes before the clip.
    assert [note["note_id"] for note in built.notes] == [
        "exampleobraclip", "exampleobrallm1",
        "senseobraart001", "senseobrateatr1", "senseobraconst1",
        "exampleobraclp2",
        OBRA,
    ]


def test_a_word_not_yet_taken_in_has_no_cards(graph, media_root):
    assert all(note["lexeme_id"] == OBRA for note in build(graph, media_root=media_root).notes)


def test_clips_come_last_and_the_sense_shows_its_most_trusted_sentence(graph, media_root):
    notes = by_id(build(graph, media_root=media_root))
    theatre = notes["senseobrateatr1"]["fields"]
    assert theatre["Sentence"] == "La <mark>obra</mark> duró tres horas y me dormí."
    assert theatre["Cloze"] == 'La <span class="gap"></span> duró tres horas y me dormí.'
    assert theatre["Source"] == '<span class="tag made">Example</span>'
    clip = notes["exampleobraclp2"]["fields"]
    assert clip["Source"] == '<span class="tag clip">Clip</span> LUZU TV · 44:55'


def test_gates_say_which_cards_each_note_makes(graph, media_root):
    notes = by_id(build(graph, media_root=media_root))
    assert notes["exampleobraclip"]["fields"]["Recognise"] == "y"
    assert "Produce" not in notes["exampleobraclip"]["fields"]
    # Every sense produces; only the one with no sentence to show it in is recognised bare.
    assert [notes[sense]["fields"]["Produce"] for sense in
            ("senseobraart001", "senseobrateatr1", "senseobraconst1")] == ["y", "y", "y"]
    assert [notes[sense]["fields"]["Recognise"] for sense in
            ("senseobraart001", "senseobrateatr1", "senseobraconst1")] == ["", "", "y"]
    assert notes["senseobraconst1"]["fields"]["Cloze"] == ""


def test_the_word_is_heard_only_when_its_headword_has_a_recording(graph, media_root):
    assert OBRA in by_id(build(graph, media_root=media_root))
    assert OBRA not in by_id(build(graph, media_root=None))
    graph["pronunciations"][0]["text"] = "obra"   # recorded before the headword gained its article
    assert OBRA not in by_id(build(graph, media_root=media_root))


def test_a_stale_recording_is_not_played(graph, media_root):
    notes = by_id(build(graph, media_root=media_root))
    assert "SentenceAudio" not in notes["exampleobrallm1"]["media"]
    assert notes["senseobrateatr1"]["media"]["DefinitionAudio"].endswith("sense-4e5f6a7b.mp3")


def test_the_word_is_shown_whole_on_every_meaning(graph, media_root):
    notes = by_id(build(graph, media_root=media_root))
    fields = notes["exampleobraclp2"]["fields"]
    assert fields["Article"] == "la" and fields["Headword"] == "obra"
    assert fields["Grammar"] == "noun · f"
    assert fields["Gloss"] == "play" and fields["GlossMore"] == "пьеса, спектакль"
    assert fields["SenseLabel"] == "sense 2 of 3"
    assert fields["Senses"].count('class="schip') == 3
    assert '<span class="schip on"><span class="n">2</span>🎭 play</span>' in fields["Senses"]
    word = notes[OBRA]["fields"]
    assert word["Senses"].count('class="sitem"') == 3
    assert 'src="media/imgobraart00001-a1b2c3d4.webp"' in word["Senses"]


def test_decks_are_per_language_and_topics_are_tags(graph, media_root):
    note = build(graph, media_root=media_root).notes[0]
    assert note["deck"] == "Spanish::Vocabulary"
    assert note["tags"] == ["acervo::note::example", "acervo::topic::culture"]
    assert build(graph, media_root=media_root, languages=["fr"]).notes == []


def test_text_is_escaped_and_only_the_word_is_marked():
    assert marked("<b>Una</b> obra", "obra") == ("&lt;b&gt;Una&lt;/b&gt; <mark>obra</mark>", True)
    assert marked("Una Obra", "obra") == ("Una <mark>Obra</mark>", True)
    assert marked("Nada", "obra") == ("Nada", False)
    assert split_article({"headword": "la obra", "pos": "noun", "language": "es"}) == ("la", "obra")
    assert split_article({"headword": "la verdad", "pos": "phrase", "language": "es"}) == ("", "la verdad")


def test_the_payload_is_a_manifest_the_robot_takes_as_it_is(graph, media_root, tmp_path):
    path = write_payload(build(graph, media_root=media_root), tmp_path / "payload")
    manifest, directory = SyncManifest.load(path)
    with Image.open(directory / "media" / "imgobraart00001-a1b2c3d4.webp") as picture:
        assert max(picture.size) == 768

    (tmp_path / "robot").mkdir()
    robot = AnkiRobot(RobotSettings(
        endpoint="http://example.invalid/", username="u", password="p",
        collection_path=tmp_path / "robot" / "collection.anki2", backup_dir=tmp_path / "backups",
        template_dir=TEMPLATES,
    ))
    collection = Collection(str(robot.settings.collection_path))
    try:
        create_notetypes(collection, robot.design)
        report = robot._upsert(collection, manifest, directory)
        names = [collection.get_card(card).template()["name"]
                 for note in report["notes"] for card in note["card_ids"]]
        assert sorted(names) == sorted(["Recognise"] * 4 + ["Produce"] * 3 + ["Listen"])
        assert list(collection.media.check().unused) == []
    finally:
        collection.close()


def test_pictures_shrink_in_parallel_and_say_how_far_they_got(tmp_path):
    built = BuiltManifest()
    for name, side in (("a.webp", 1024), ("b.png", 1536), ("small.webp", 300)):
        source = tmp_path / "masters" / name
        source.parent.mkdir(exist_ok=True)
        Image.new("RGB", (side, side), (40, 90, 80)).save(source)
        built.media[f"media/{name}"] = source
    said = io.StringIO()

    write_payload(built, tmp_path / "payload", progress=Progress(said), workers=2)

    sizes = {}
    for name in ("a.webp", "b.png", "small.webp"):
        with Image.open(tmp_path / "payload" / "media" / name) as picture:
            sizes[name] = max(picture.size)
    assert sizes == {"a.webp": 768, "b.png": 768, "small.webp": 300}
    assert said.getvalue().splitlines()[-1].endswith("Shrinking pictures to 768 px: 3/3")


def test_build_manifest_reads_a_saved_graph(graph, media_root, tmp_path, capsys):
    saved = tmp_path / "graph.json"
    saved.write_text(json.dumps({"changes": graph}), encoding="utf-8")
    assert main(["build-manifest", str(tmp_path / "out"), "--graph", str(saved),
                 "--media-root", str(media_root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["examples"], report["senses"], report["words"]) == (3, 3, 1)
    assert (tmp_path / "out" / "manifest.json").is_file()


def test_a_bootstrap_the_server_would_refuse_is_refused_before_any_card_is_built(monkeypatch):
    from acervo.consumers.anki import cli
    from acervo.consumers.anki.robot import SyncSafetyError

    class Refusing:
        def check_bootstrap(self):
            raise SyncSafetyError("this one holds a collection")

    def built(*_):
        raise AssertionError("the cards were built for a bootstrap that could not happen")

    monkeypatch.setattr(cli, "build_payload", built)
    args = cli.build_parser().parse_args(["push-vocabulary", "--bootstrap"])
    with pytest.raises(SyncSafetyError, match="holds a collection"):
        cli.push_vocabulary(args, Refusing())
