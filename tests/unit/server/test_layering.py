"""The layering, enforced by imports rather than by remembering it.

Four rules, each of which stops being true silently:

- `api/` may not import `jobs/`, because capture, review and the sync API must work with the
  orchestrator down and must not know one exists.
- Nothing outside `repository/` may touch the database — the server-side twin of the rule the
  interface already lives by.
- `jobs/` and `consumers/` reach the graph through `client.py`, against the service's own route:
  same validation and same revision allocation as a phone. One writer, one pipeline.
- Nothing that ships imports `experiments/`.
- `models/` stands alone: it is a provider package, not an Acervo one.
- An enrichment pipeline — `images/`, `clips/` — may import the provider package and the article
  view, and nothing else of Acervo's, which is what lets a route and a batch sweep share one
  pipeline instead of writing it twice.
- `article.py` itself imports nothing of Acervo's at all, which is what makes it safe to be the one
  thing every enrichment shares.
- `ocr/` turns an OCR engine's words into a page: the provider package and nothing else of Acervo's.
- `speech/` is the translation seam the corpus calls back through: the provider package and nothing
  else of Acervo's, and nothing at all of the retrieval service's.
- `repository/` stores; it does not know the catalogue.
- `work/` runs jobs by calling `services/`, never `api/`; `services/` knows nothing of jobs; and a
  route reaches jobs only through `repository.jobs`.
- The three modules every layer logs through — the request id, the log opener, the activity log —
  are leaves, which is what lets a repository, a service and a route all hold them.
- A companion service is told whose work a request is; a media file is removed in one place, which
  says so; and an error response is built in one place, which writes it down.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = REPOSITORY_ROOT / "src" / "acervo"


def imports_of(path: Path) -> set[str]:
    """Every module `path` imports, by absolute name.

    Relative imports are resolved rather than skipped. Reading only `level == 0` was a hole big
    enough to drive through: `from ...db import engine` inside `api/routes/` is the very thing two of
    these rules forbid, and it would have passed in silence.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = ["acervo", *path.relative_to(PACKAGE).parts[:-1]]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    found.add(node.module)
                continue
            # `level` counts how far up from this module's own package to start.
            base = package[: len(package) - node.level + 1]
            found.add(".".join([*base, node.module] if node.module else base))
    return found


def modules_under(*parts: str) -> list[Path]:
    return sorted((PACKAGE.joinpath(*parts)).rglob("*.py"))


def identify(path: Path) -> str:
    return str(path.relative_to(PACKAGE))


def test_the_import_reader_resolves_a_relative_import(tmp_path):
    """The rules below are only as good as this. Reading absolute imports alone was a hole: the
    forbidden reach — `from ...db import engine` inside `api/routes/` — is expressed relatively."""
    module = PACKAGE / "api" / "routes" / "__probe__.py"
    module.write_text(
        "from ...db import engine\n"
        "from ..errors import data\n"
        "from .graph import router\n"
        "from acervo.repository import graph\n"
        "import httpx\n",
        encoding="utf-8",
    )
    try:
        assert imports_of(module) == {
            "acervo.db",
            "acervo.api.errors",
            "acervo.api.routes.graph",
            "acervo.repository",
            "httpx",
        }
    finally:
        module.unlink()


def test_the_rules_below_are_not_vacuous():
    """A layering rule against a package that does not exist passes and means nothing — which is
    what `acervo.jobs` was before the batch work moved under it."""
    assert modules_under("jobs"), "no jobs/ modules: the batch-work rule would be vacuous"
    assert modules_under("consumers"), "no consumers/ modules"
    assert any(
        "acervo.client" in imports_of(path)
        for path in modules_under("jobs") + modules_under("consumers")
    ), "no batch module goes through acervo.client, so nothing exercises the write-path rule"
    assert modules_under("models"), "no models/ modules: the stands-alone rule would be vacuous"
    assert modules_under("images"), "no images/ modules: the stands-alone rule would be vacuous"
    assert modules_under("clips"), "no clips/ modules: the stands-alone rule would be vacuous"
    assert modules_under("loops"), "no loops/ modules: the stands-alone rule would be vacuous"
    assert modules_under("stories"), "no stories/ modules: the stands-alone rule would be vacuous"
    assert modules_under("pronunciation"), "no pronunciation/ modules: the stands-alone rule would be vacuous"
    assert modules_under("meaning"), "no meaning/ modules: the stands-alone rule would be vacuous"
    assert modules_under("ocr"), "no ocr/ modules: the stands-alone rule would be vacuous"
    assert (PACKAGE / "article.py").exists(), "no article.py: the shared-view rule would be vacuous"
    assert modules_under("speech"), "no speech/ modules: the stands-alone rule would be vacuous"
    assert modules_under("repository"), "no repository/ modules"


@pytest.mark.parametrize("path", modules_under("api"), ids=identify)
def test_the_request_path_does_not_import_batch_work(path):
    assert not any(name.startswith("acervo.jobs") for name in imports_of(path)), path


@pytest.mark.parametrize(
    "path", modules_under("api") + modules_under("services"), ids=identify
)
def test_only_the_repository_reaches_the_database(path):
    offenders = {name for name in imports_of(path) if name.startswith("acervo.db")}
    assert not offenders, f"{path} imports {sorted(offenders)}; go through acervo.repository"


def test_the_admin_cli_writes_through_the_repository_too():
    assert not any(name.startswith("acervo.db") for name in imports_of(PACKAGE / "admin.py"))


@pytest.mark.parametrize(
    "path", modules_under("jobs") + modules_under("consumers"), ids=identify
)
def test_batch_work_writes_the_graph_the_way_a_phone_does(path):
    """Not by reaching into the database, and not with a client of its own."""
    offenders = {
        name
        for name in imports_of(path)
        if name.startswith(("acervo.db", "acervo.repository", "acervo.api"))
    }
    assert not offenders, f"{path} imports {sorted(offenders)}; go through acervo.client"


STANDS_ALONE = (
    "acervo.settings",
    "acervo.errors",
    "acervo.repository",
    "acervo.client",
    "acervo.api",
    "acervo.db",
    "acervo.domain",
    "acervo.services",
    "acervo.jobs",
    "acervo.consumers",
)


@pytest.mark.parametrize("path", modules_under("models"), ids=identify)
def test_the_provider_package_stands_alone(path):
    """`models/` takes a catalogue and a chain, and nothing else.

    It is the one package here meant to be usable outside Acervo, and the split it rests on is that
    it decides *what kind of thing* went wrong while `services/models.py` decides what Acervo's wire
    calls that. One `from acervo.errors import ApiError` in `call.py` would collapse that split, and
    would do it invisibly — the code would work.
    """
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the provider package stands alone"


@pytest.mark.parametrize("path", modules_under("images"), ids=identify)
def test_the_image_pipeline_stands_on_the_provider_package_and_nothing_else(path):
    """An article in, a brief and a WebP out — and no idea whose article it is.

    This is why the pipeline is not under `jobs/`. `api/` may not import `acervo.jobs`, so while
    these modules lived there a picture could not be drawn from a route without either breaking that
    rule or writing the pipeline a second time. Standing alone is what lets `services/images.py` and
    `jobs/images/sweep.py` be two callers of one thing.

    `acervo.errors` is on the list for the same reason it is on `models/`'s: this package decides
    what a picture is, `services/images.py` decides what Acervo's wire calls a failure to draw one,
    and a single `ApiError` import here would merge them in code that still worked.
    """
    # `STANDS_ALONE` deliberately does not list `acervo.models` or `acervo.article`, which are the
    # two Acervo modules an enrichment pipeline may import: the provider package and the view of the
    # word being enriched. Both are pure, and neither knows whose word it is.
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the image pipeline stands alone"


@pytest.mark.parametrize("path", modules_under("stories"), ids=identify)
def test_the_story_pipeline_stands_on_the_provider_package_and_nothing_else(path):
    """Words and a kind of story in; parts, a translation and briefs out — and no idea whose words.

    The same argument as `images/`, which this package also *imports*: `illustrate.py` reaches for
    `images.render` and `images.styles` rather than copying a renderer and an art-direction table,
    and both of those already stand alone by this same rule. A story picture and a sense picture are
    drawn by one renderer in one style table, which is what stops "adding a way to draw a picture"
    from adding a second pipeline.

    `services/stories.py` is the binding layer that reads `Settings`, the graph and the owner's
    chain. One `from acervo.errors import ApiError` here would merge the two halves in code that
    still worked.
    """
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the story pipeline stands alone"


@pytest.mark.parametrize("path", modules_under("clips"), ids=identify)
def test_the_clip_pipeline_stands_on_the_provider_package_and_nothing_else(path):
    """Candidates in, a selection out — and no idea whose word it is, or where the corpus lives.

    The same argument as `images/`: `api/` may not import `acervo.jobs`, so a clip searched from a
    route and a clip searched by the sweep have to be two callers of one thing rather than two
    pipelines. `services/clips.py` is the binding layer that reads `Settings`, the owner's chain and
    the graph, and turns this package's answers into Acervo's wire vocabulary.
    """
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the clip pipeline stands alone"


@pytest.mark.parametrize("path", modules_under("loops"), ids=identify)
def test_the_loop_client_stands_on_httpx_and_nothing_else(path):
    """Words in, a track out — and no idea whose words they are, or what a job is.

    LexiBeat is a separate repository behind a version pin, exactly as the corpus is, and this is the
    only place its wire shape is read. `services/loops.py` is the binding layer that reads
    `Settings` and the graph and turns these refusals into Acervo's wire vocabulary; `work/loop.py`
    follows the operation. Neither belongs here, and nothing here may reach for either.

    `cli.py` is the one exception it does not need: it imports `acervo.client`, which is the write
    path every batch caller goes through, so it is excluded below rather than let through.
    """
    if path.name == "cli.py":
        return
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the loop client stands alone"


@pytest.mark.parametrize("path", modules_under("pronunciation"), ids=identify)
def test_the_pronunciation_pipeline_stands_on_the_provider_package_and_nothing_else(path):
    """Text and a language in, audio out — and no idea whose word it is or where the file goes.

    `services/pronunciations.py` is the binding layer that reads `Settings`, the owner's orders and
    voices, and the graph, and decides what Acervo's wire calls a clip that could not be recorded.
    """
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the pronunciation pipeline stands alone"


@pytest.mark.parametrize("path", modules_under("meaning"), ids=identify)
def test_the_meaning_map_stands_alone(path):
    """Senses and vectors in, a map out — and no idea whose words they are or where the map is kept.

    `services/meaning.py` is the binding layer that reads the graph, keeps the cache and the drawn
    map beside the database, and names the regions through the owner's text chain. Standing alone is
    what lets the map move to the discovery repository later without taking Acervo with it.
    """
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the meaning map stands alone"


@pytest.mark.parametrize("path", modules_under("ocr"), ids=identify)
def test_the_photo_reader_stands_on_the_provider_package_and_nothing_else(path):
    """An engine's words in, a page to tap out — and no idea whose photo it is or where it is kept.

    `services/photo.py` is the binding layer that reads `Settings`, the owner's `ocr` chain and
    vocabularies, and stores the photo.
    """
    offenders = {name for name in imports_of(path) if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the photo reader stands alone"


def test_the_article_view_imports_nothing_of_acervos():
    """The one module both enrichment packages import, so it may depend on nothing at all.

    A single `from acervo.settings import Settings` here would reach every pipeline that shares it,
    and the sharing is the whole point — this is what keeps `acervo.article` a view of wire-shaped
    records rather than a second way into the graph.
    """
    offenders = {name for name in imports_of(PACKAGE / "article.py") if name.startswith("acervo")}
    assert not offenders, f"acervo/article.py imports {sorted(offenders)}; it must stay pure"


@pytest.mark.parametrize("path", modules_under("speech"), ids=identify)
def test_the_translation_seam_stands_on_the_provider_package_and_nothing_else(path):
    """One structured call on the owner's chain, and no idea whose clip it is.

    This one runs in the *speech* container, which has no business reaching Acervo's database at
    all — so the chain arrives as `ACERVO_TEXT_CHAIN` rather than being looked up, the rule already
    stated for any work that cannot import `repository/`. It also imports nothing of the retrieval
    service's: the wiring that knows that package's prompts, schemas and exception types is
    `deploy/acervo/speech/serve.py`, which is what lets this be tested from a virtualenv that does
    not, and must not, carry FastAPI, uvicorn, yt-dlp and Stanza.
    """
    imported = imports_of(path)
    offenders = {name for name in imported if name.startswith(STANDS_ALONE)}
    assert not offenders, f"{path} imports {sorted(offenders)}; the translation seam stands alone"
    foreign = {name for name in imported if name.startswith("speech_retrieval")}
    assert not foreign, f"{path} imports {sorted(foreign)}; that belongs in the container's entry point"


@pytest.mark.parametrize("path", modules_under("repository"), ids=identify)
def test_the_storage_layer_does_not_know_the_catalogue(path):
    """`repository/` stores what it is given; which providers exist is `models/`'s question.

    Both halves would otherwise validate a chain, and two validators are one drift. It also keeps
    the storage layer usable for a catalogue it has never heard of, which is what a settings record
    that outlives a deployment fact has to be.
    """
    offenders = {name for name in imports_of(path) if name.startswith("acervo.models")}
    assert not offenders, f"{path} imports {sorted(offenders)}; validate in acervo.services.models"


def test_the_runner_rules_are_not_vacuous():
    assert modules_under("work"), "no work/ modules: the runner rules would be vacuous"
    assert (PACKAGE / "repository" / "jobs.py").exists(), "no repository/jobs.py"


@pytest.mark.parametrize("path", modules_under("work"), ids=identify)
def test_the_runner_never_reaches_back_into_the_request_path(path):
    """`work/` calls the services the routes call, and never a route: a job and a request are the
    same code, entered from two places, and neither place knows about the other."""
    offenders = {name for name in imports_of(path) if name.startswith("acervo.api")}
    assert not offenders, f"{path} imports {sorted(offenders)}; call acervo.services instead"


@pytest.mark.parametrize("path", modules_under("services"), ids=identify)
def test_the_services_know_nothing_of_jobs(path):
    """What makes a service safe to call from a route and a job alike is that it cannot tell which."""
    offenders = {
        name for name in imports_of(path)
        if name.startswith(("acervo.work", "acervo.repository.jobs"))
    }
    assert not offenders, f"{path} imports {sorted(offenders)}; services must not know about jobs"


@pytest.mark.parametrize(
    "path", [p for p in modules_under("api") if identify(p) != "api/app.py"], ids=identify
)
def test_routes_reach_jobs_only_through_the_repository(path):
    """A route queues a job and reads its record. Only the application itself starts the runner."""
    offenders = {name for name in imports_of(path) if name.startswith("acervo.work")}
    assert not offenders, f"{path} imports {sorted(offenders)}; go through acervo.repository.jobs"


def test_the_notification_hub_imports_nothing_of_acervos():
    """The repository, the runner and the event route all import it, so it may import none of them."""
    offenders = {name for name in imports_of(PACKAGE / "notify.py") if name.startswith("acervo")}
    assert not offenders, f"acervo/notify.py imports {sorted(offenders)}"


@pytest.mark.parametrize("path", modules_under(), ids=identify)
def test_nothing_that_ships_imports_the_experiments(path):
    """`experiments/` is outside `src/` and outside the distribution, so importing it would not even
    resolve where the service runs."""
    assert not any(name.split(".")[0] == "experiments" for name in imports_of(path)), path


def test_the_client_does_not_drag_the_services_configuration_along():
    """A client speaks to the service; it does not read the service's environment.

    `SCHEMA_VERSION` used to live in `settings.py`, so importing the client pulled in
    pydantic-settings — and the worker image, which has no reason to carry the service's
    configuration layer, could not run a job at all.
    """
    offenders = {
        name for name in imports_of(PACKAGE / "client.py") if name.startswith("acervo.settings")
    }
    assert not offenders, "acervo.client must not import the service's settings"


@pytest.mark.parametrize(
    "path", modules_under("jobs") + modules_under("consumers"), ids=identify
)
def test_batch_work_does_not_read_the_services_environment(path):
    assert not any(name.startswith("acervo.settings") for name in imports_of(path)), path


ALLOWED_HTTP = {
    # Third-party dictionary sources, downloaded to be compiled.
    "dictionaries/build.py",
    # Model providers and online dictionaries: outbound, not the Acervo API.
    "models/cloudflare.py",
    "services/dictionaries/online.py",
    # The service itself, which does not call itself over HTTP.
    "api/app.py",
    "api/static.py",
    "api/routes/mac_release.py",
    "client.py",
}


@pytest.mark.parametrize("path", modules_under(), ids=identify)
def test_only_the_client_speaks_http_to_the_acervo_api(path):
    """"Exactly one HTTP client against the Acervo API" as a test rather than a habit.

    A module that both names the API root and opens a connection is a second client, whatever it is
    called. The allow-list is for the callers that legitimately speak HTTP to somewhere that is not
    Acervo, and for the service's own route table.
    """
    if identify(path) in ALLOWED_HTTP:
        return
    source = path.read_text(encoding="utf-8")
    names = imports_of(path)
    opens_a_connection = any(
        name.startswith(("httpx", "urllib.request", "requests", "http.client")) for name in names
    )
    assert not (opens_a_connection and "/api/acervo" in source), (
        f"{path} names the Acervo API and opens its own connection; go through acervo.client"
    )


# ── observability: the rules that stop being true with one line ─────────────

LEAVES = ("trace.py", "activity.py", "logfiles.py")


@pytest.mark.parametrize("name", LEAVES)
def test_what_every_layer_logs_through_imports_nothing_else_of_acervos(name):
    """A repository, a service and a route all write to these. The moment one of them imports
    upward, something that may not import that layer cannot log."""
    allowed = {f"acervo.{leaf[:-3]}" for leaf in LEAVES} | {"acervo"}
    offenders = {
        found for found in imports_of(PACKAGE / name)
        if found.split(".")[0] == "acervo" and found not in allowed
    }
    assert not offenders, f"{name} imports {sorted(offenders)}"


# Modules that open a connection to somewhere that is not one of Acervo's own services: a model
# provider, a third-party dictionary. There is nobody on the other end to file anything under an id.
NOT_A_COMPANION = {
    "models/cloudflare.py",
    "models/google_auth.py",
    "services/dictionaries/online.py",
}


@pytest.mark.parametrize("path", modules_under(), ids=identify)
def test_a_companion_service_is_told_whose_work_it_is(path):
    """Every client of one of Acervo's own services sends the request id.

    A loop render failed on the deployed server with its cause in another container's log and
    nothing to match the two by. A new companion is a new module that imports `httpx`, and this is
    what makes it carry the id rather than relying on somebody remembering.
    """
    relative = path.relative_to(PACKAGE).as_posix()
    if relative in NOT_A_COMPANION or not any(name.split(".")[0] == "httpx" for name in imports_of(path)):
        return
    source = path.read_text(encoding="utf-8")
    assert "X-Request-ID" in source or "trace.HEADER" in source, (
        f"{relative} speaks HTTP and never sends the request id; see docs/architecture/observability.md"
    )


def test_the_companion_rule_is_not_vacuous():
    speakers = {
        path.relative_to(PACKAGE).as_posix() for path in modules_under()
        if any(name.split(".")[0] == "httpx" for name in imports_of(path))
    }
    assert {"loops/client.py", "clips/corpus.py", "services/speech.py", "client.py"} <= speakers
    assert NOT_A_COMPANION <= speakers, "an exemption names a module that no longer speaks HTTP"


@pytest.mark.parametrize("path", modules_under("services") + modules_under("api"), ids=identify)
def test_a_media_file_is_removed_in_one_place(path):
    """`services/media.remove` unlinks and says so. A bare `unlink` beside it is a file that
    vanishes with no line saying which or why."""
    if path == PACKAGE / "services" / "media.py":
        return
    assert ".unlink(" not in path.read_text(encoding="utf-8"), (
        f"{path.relative_to(PACKAGE)} unlinks a file itself; go through acervo.services.media.remove"
    )


@pytest.mark.parametrize("path", modules_under("api"), ids=identify)
def test_an_error_response_is_built_in_one_place(path):
    """The envelope's handlers are where a refusal is written down, so a route that answers an
    error itself is a failure the owner sees and the log does not."""
    if path == PACKAGE / "api" / "errors.py":
        return
    source = path.read_text(encoding="utf-8")
    assert '{"error"' not in source and "errors.error(" not in source and "import error" not in source, (
        f"{path.relative_to(PACKAGE)} builds an error response; raise ApiError instead"
    )
