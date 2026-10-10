"""One rule for every test here: packaging never writes what a deployment streams.

The packager used to write a fixed `build/acervo-server.tar.gz`, and so did these tests — directly,
and through `deploy.sh`, which packages before it streams. Running the suite during a real
`./deploy.sh` therefore rewrote the archive mid-transfer. The remote found a complete gzip stream
with another process's bytes after it and failed with "the release archive has no Acervo installer",
which names nothing that happened; the same collision had already been dismissed three times as
"two test runs at once".

Set here rather than at each call site because there are seventeen of them, every one builds its own
environment with `os.environ.copy()`, and the eighteenth would forget. Setting it on `os.environ`
means every copy inherits it, whether the test runs the packager or `deploy.sh`.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def package_into_the_tests_own_directory(tmp_path_factory, monkeypatch):
    archive = tmp_path_factory.mktemp("release") / "acervo-server.tar.gz"
    monkeypatch.setenv("ACERVO_PACKAGE_ARCHIVE", str(archive))
    # And without the compiled dictionaries, which are the owner's own 800-odd MB and have nothing
    # to do with whether a stream reaches a server or a summary names the right address. Every test
    # here used to drag them in — harmless while they all overwrote one archive in `build/`, and
    # 24 GB of temporary directories once each test got its own. The two tests that *are* about
    # dictionary publishing point `ACERVO_DICTIONARY_ARTIFACTS` at a handful of fixture files, and
    # their own environment overrides this.
    monkeypatch.setenv("ACERVO_INCLUDE_DICTIONARIES", "false")
    # What a deploy remembers having sent lives under `build/` too, and for the same reason must not
    # be the real one: a test would otherwise teach this machine that its server holds dictionaries
    # it was never sent, and read back what the last real deploy recorded.
    monkeypatch.setenv("ACERVO_DEPLOY_STATE", str(tmp_path_factory.mktemp("deploy-state")))
    return archive
