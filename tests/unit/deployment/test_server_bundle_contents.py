"""The remote deployment builds its images from a packaged archive, not from a checkout.

So a directory a Dockerfile copies but the packaging script does not bundle builds fine locally and
fails on the server with `"/prompts": not found` — after the upload, at the least convenient moment.
Keeping the two lists in step is what this checks.
"""

import base64
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[3]
# Both images are built from the packaged archive, so both have to be checked. The worker one was
# added with the dictionary compiler, which copies `dictionaries/` for the catalogue.
DOCKERFILES = (
    ROOT / "deploy" / "acervo" / "server" / "Dockerfile",
    ROOT / "deploy" / "acervo" / "Dockerfile",
    # The corpus service, built from the pinned wheel in `vendor/speech/`. A Dockerfile absent from
    # this tuple is simply not checked, so the COPY-path guarantee stops applying without failing.
    ROOT / "deploy" / "acervo" / "speech" / "Dockerfile",
    # The loop generator, built the same way from `vendor/lexibeat/`.
    ROOT / "deploy" / "acervo" / "lexibeat" / "Dockerfile",
)
PACKAGER = ROOT / "scripts" / "package_acervo_server.sh"


def bundled_directories() -> set[str]:
    """What the tarball actually contains.

    The staged copy and the archive list are two statements of the same thing, so they are checked
    against each other first: copying a directory into the staging area but leaving it out of the tar
    is the same bug one step later.
    """
    script = PACKAGER.read_text()
    listed = re.search(r"^for directory in ([^;]+); do$", script, flags=re.MULTILINE)
    archived = re.search(r'^archive_entries="([^"]+)"$', script, flags=re.MULTILINE)
    assert listed and archived, "could not read the bundle contents out of the packaging script"
    entries = set(archived.group(1).split())
    assert set(listed.group(1).split()) <= entries, "a copied directory is missing from the archive"
    return entries


def copies(dockerfile: Path) -> list[tuple[list[str], list[str]]]:
    """Every `COPY` from the build context, as its flags and its sources."""
    found = []
    for line in re.findall(r"^COPY\s+(.+)$", dockerfile.read_text(encoding="utf-8"), flags=re.MULTILINE):
        words = line.split()
        flags = [word for word in words if word.startswith("--")]
        paths = [word for word in words if not word.startswith("--")]
        if any(flag.startswith("--from=") for flag in flags):
            continue
        found.append((flags, paths[:-1]))
    return found


def image_sources() -> set[str]:
    sources = set()
    for dockerfile in DOCKERFILES:
        for _flags, paths in copies(dockerfile):
            sources.update(PurePosixPath(source).parts[0] for source in paths)
    assert sources, "expected the Dockerfiles to copy something from the build context"
    return sources


def test_every_directory_the_image_copies_is_in_the_release_bundle():
    missing = image_sources() - bundled_directories()
    assert not missing, (
        f"{sorted(missing)} are copied by a deployment image but not packaged by "
        f"{PACKAGER.name}, so a remote deployment cannot build"
    )


def test_the_dictionary_catalogue_is_packaged_and_readable():
    """The worker image reads the catalogue at build time; an unpackaged one fails the same way."""
    assert "dictionaries" in bundled_directories()
    catalogue = json.loads((ROOT / "dictionaries" / "catalogue.json").read_text())
    assert catalogue["dictionaries"], "the shipped catalogue is empty"


def test_the_provider_catalogue_is_packaged_and_readable():
    """The service reads it on every capture and on every health check, so an unpackaged catalogue
    is a 500 on the first word rather than a build failure."""
    assert "models" in bundled_directories()
    catalogue = json.loads((ROOT / "models" / "catalogue.json").read_text())
    assert catalogue["providers"], "the shipped provider catalogue is empty"


def test_the_capture_prompts_are_packaged_and_named_as_the_service_reads_them():
    """The service reads prompts by name at request time; a renamed file is a runtime failure."""
    assert "prompts" in bundled_directories()
    named = set()
    for source in (ROOT / "src" / "acervo").rglob("*.py"):
        # Up to the name and no further: a call may pass options after it, and a pattern that
        # demanded the closing paren would stop matching — silently, which is the failure this
        # whole test exists to prevent.
        named.update(re.findall(r'prompt_text\([^,]+,\s*"([a-z_]+)"', source.read_text()))
    assert named, "expected the capture service to read prompts by name"
    for name in named:
        assert (ROOT / "prompts" / f"{name}.md").is_file(), f"prompts/{name}.md is missing"


def test_every_config_file_the_server_reads_is_copied_into_its_image():
    """`config/` is copied **file by file**, so a new one is missing until somebody says otherwise.

    This is `prompts/`'s failure a directory along, and worse: `COPY prompts /app/prompts` takes a
    new prompt for free, while `COPY config/image-styles.yaml …` takes nothing it is not told about.
    A config the server reads but the image lacks builds cleanly, deploys cleanly, passes the
    healthcheck, and fails at the first request that needs it.

    Found the hard way — `config/story-types.yaml` was written, read by `acervo.stories.types`, and
    would have shipped in an image that did not contain it.
    """
    wanted = set()
    for source in (ROOT / "src" / "acervo").rglob("*.py"):
        wanted.update(re.findall(r'"config"\s*/\s*"([A-Za-z0-9._-]+)"', source.read_text()))
    assert wanted, "expected the server to read at least one file out of config/"

    dockerfile = (ROOT / "deploy" / "acervo" / "server" / "Dockerfile").read_text()
    for name in sorted(wanted):
        assert (ROOT / "config" / name).is_file(), f"config/{name} is read but does not exist"
        assert f"config/{name}" in dockerfile, (
            f"config/{name} is read by the server but never copied into its image"
        )


def test_no_dockerfile_relies_on_a_bare_chmod_plus_x():
    """`+x` without a "who" is masked by the umask, and the installer extracts a release under
    `umask 077` — so the file arrives owner-only, stays owner-only, and the container, which runs as
    the deploying user against a root-owned copy, cannot open its own entry point. It surfaces as
    `/bin/sh: 0: cannot open …: Permission denied`, with nothing naming the cause.
    """
    for dockerfile in DOCKERFILES:
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            assert not re.search(r"chmod\s+(?:-\w+\s+)*\+x\b", line), (
                f"{dockerfile}: {line.strip()!r} is umask-dependent; say `a+rx`"
            )


def test_every_required_compose_variable_is_one_the_integration_test_supplies():
    """`${X:?…}` is checked when the file is *read*, so an absent one fails **every** command in the
    file — `build` included, and for services that have nothing to do with X.

    Requiring a variable is therefore a promise that every caller sets it, and the Docker
    integration test is the caller that sets the least: it starts the Anki services and knows
    nothing about the corpus. Making the corpus's operator token required broke `compose build`
    there with a message about a token, in a test about Anki.

    A credential that must exist belongs in the service that needs it, refusing to start — which is
    what the corpus does, because channel mutations are on and its host is not loopback.
    """
    compose = (ROOT / "deploy" / "acervo" / "compose.yaml").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z_]+):\?", compose))

    harness = (ROOT / "tests" / "integration" / "test_anki_sync_docker.py").read_text(encoding="utf-8")
    supplied = set(re.findall(r"\b(ACERVO_[A-Z_]+)=", harness))

    missing = sorted(required - supplied)
    assert not missing, (
        f"{missing} is required by compose but not set by the Docker integration test, so every "
        "compose command it runs fails. Either supply it there or stop requiring it."
    )


def test_every_fallback_volume_is_declared():
    """`${X:-some-volume}` names a volume compose must know about, or the whole file is invalid.

    It only bites when the caller leaves the variable unset — the installer always sets them, so
    this failed nowhere except the Docker integration test, which sets the least of any caller and
    is the one place a fresh deployment's defaults are actually exercised.
    """
    import yaml

    text = (ROOT / "deploy" / "acervo" / "compose.yaml").read_text(encoding="utf-8")
    # A mount, not a port: the `:` after the closing brace is what tells them apart.
    used = {name for name in re.findall(r"\$\{[A-Z_]+:-([a-z0-9-]+)\}:", text) if not name.isdigit()}
    declared = set(yaml.safe_load(text).get("volumes") or {})

    missing = sorted(used - declared)
    assert not missing, f"{missing} is mounted by name but not declared under `volumes:`"


# What a `COPY` may sit beside without being run again on every code change: instructions that only
# describe the image. Anything else after the first copy of Acervo's own files is a step a deploy
# pays for whenever those files change.
DESCRIPTIVE = ("COPY", "ENV", "EXPOSE", "CMD", "ENTRYPOINT", "FROM", "WORKDIR", "ARG")
# Pins and requirement lists, which change when a dependency does. A step after one of these is the
# install it names, and is meant to run again when it changes.
DEPENDENCY_INPUTS = ("vendor/", "requirements", "models/encoder.json", "models/segmenter.json")


def test_every_image_leaves_its_own_files_readable_by_the_user_it_runs_as():
    """The installer extracts a release under `umask 077` and `COPY` makes the result root-owned, so
    an image built from a release has owner-only files. Every container runs as the deploying user,
    which would then be unable to read its own entry point.

    On the `COPY` itself rather than a `chmod -R` at the end, which would be a step run again after
    every code change (the test below).
    """
    for dockerfile in DOCKERFILES:
        for flags, paths in copies(dockerfile):
            if all(source.startswith(DEPENDENCY_INPUTS) for source in paths):
                continue
            assert "--chmod=755" in flags, (
                f"{dockerfile}: COPY {' '.join(paths)} lands owner-only in an image built from a "
                "release; say `--chmod=755`"
            )


def test_nothing_runs_after_an_image_has_copied_acervos_own_files():
    """A layer is rebuilt when anything above it changed, and on the server every rebuilt layer costs
    seconds whatever its size. Measured: a `pip install` below the corpus image's copy of
    `acervo.models` reinstalled LiteLLM on every deploy that touched that package, and one code
    change rebuilt twenty-nine layers across four images — seven minutes for a megabyte of Python.
    So installs and directory set-up come first, and what a deploy changes comes last.
    """
    for dockerfile in DOCKERFILES:
        copied = False
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            words = line.split()
            if not words or words[0] not in ("RUN", *DESCRIPTIVE) or line[0].isspace():
                continue
            if words[0] == "COPY":
                paths = [word for word in words[1:] if not word.startswith("--")][:-1]
                copied = copied or not all(source.startswith(DEPENDENCY_INPUTS) for source in paths)
            assert not (copied and words[0] == "RUN"), (
                f"{dockerfile}: {line.strip()[:60]!r} runs after Acervo's own files are copied, so "
                "every code change runs it again; move it above them"
            )


def test_every_image_is_built_on_the_same_pinned_base():
    """A tag is a pointer upstream moves — three times in three weeks — and every move discarded the
    whole layer cache: torch, every requirement and 900 MB of model weights, reinstalled for a deploy
    that changed none of them. A digest does not move. One digest across all four, so the base
    layers are stored once and upgraded together.
    """
    bases = set()
    for dockerfile in DOCKERFILES:
        text = dockerfile.read_text(encoding="utf-8")
        external = [base for base in re.findall(r"^FROM\s+(\S+)", text, flags=re.MULTILINE)
                    if base not in re.findall(r"\bAS\s+(\S+)$", text, flags=re.MULTILINE)]
        assert external, f"{dockerfile} names no base image"
        for base in external:
            assert re.fullmatch(r"[\w./:-]+@sha256:[0-9a-f]{64}", base), (
                f"{dockerfile}: {base} is not pinned by digest"
            )
        bases.update(external)
    assert len(bases) == 1, f"the images are built on different bases: {sorted(bases)}"


def test_the_sync_server_is_built_without_acervos_code():
    """It runs `python -m anki.syncserver` and nothing of Acervo's, so its image stops at the stage
    before the code is copied: a code change leaves the image as it was, and compose leaves a
    container whose image has not changed running."""
    import yaml

    compose = yaml.safe_load((ROOT / "deploy" / "acervo" / "compose.yaml").read_text(encoding="utf-8"))
    target = compose["services"]["anki-sync-server"]["build"]["target"]
    dockerfile = (ROOT / "deploy" / "acervo" / "Dockerfile").read_text(encoding="utf-8")
    stage = dockerfile.split(f" AS {target}\n", 1)[1].split("\nFROM ", 1)[0]
    assert "COPY" not in stage, "the sync server's stage copies files a code change would alter"
    assert compose["services"]["acervo-worker"]["build"]["target"] != target


def test_the_suite_never_writes_the_archive_a_deployment_streams():
    """A regression test for a *deployment* failure, not a test failure.

    The packager used to write a fixed `build/acervo-server.tar.gz`, and these tests wrote it too —
    so running the suite during a `./deploy.sh` rewrote the archive while it was being streamed. The
    remote found a complete gzip stream with another process's bytes after it, reported trailing
    garbage and a tar child status 2, and failed with "the release archive has no Acervo installer":
    a message with nothing in it pointing at a second writer.

    Asserted against the environment every test here actually runs in, rather than against the text
    of a file: `conftest.py` sets this on `os.environ`, so it reaches the packager whether a test
    runs it directly or runs `deploy.sh`, which packages before it streams.
    """
    assert "ACERVO_PACKAGE_ARCHIVE" in PACKAGER.read_text(encoding="utf-8"), \
        "the archive path must be overridable"

    redirected = os.environ.get("ACERVO_PACKAGE_ARCHIVE", "")
    assert redirected, "conftest must redirect packaging away from build/"
    assert not Path(redirected).is_relative_to(ROOT / "build")


def test_the_lockfile_pins_the_released_tarball_rather_than_a_local_build():
    """The npm lockfile and `pin.json` have to name the same bytes, and they can drift silently.

    `npm pack` gzips with the building Node's zlib, so a tarball built on a laptop and the one
    attached to the release differ byte for byte while carrying identical contents. `pin.json`
    learned that once and switched to the release's digests; the lockfile was left behind, holding
    the integrity of a local build.

    Nothing caught it locally, because npm resolves a `file:` dependency from its cache when the
    integrity matches something already there. CI has no cache, hashed the file on disk, and failed
    the install with `EINTEGRITY` — after the push, at the least convenient moment.
    """
    pin = json.loads((ROOT / "deploy" / "acervo" / "speech" / "pin.json").read_text(encoding="utf-8"))
    tarball = ROOT / "vendor" / "speech" / pin["artifacts"]["react"]["file"]
    if not tarball.exists():
        pytest.skip("run scripts/fetch_speech.sh first; vendor/ is untracked on purpose")

    raw = tarball.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin["artifacts"]["react"]["sha256"], (
        "vendor/ holds a tarball the pin does not name; re-run scripts/fetch_speech.sh --force"
    )

    lock = json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
    entry = lock["packages"]["node_modules/@spoken-usage-retrieval/react"]
    expected = "sha512-" + base64.b64encode(hashlib.sha512(raw).digest()).decode()
    assert entry["integrity"] == expected, (
        "web/package-lock.json pins a different build of the player than pin.json does. "
        "Fetch the release's tarball and re-lock; do not take the digest from a local `npm pack`."
    )
